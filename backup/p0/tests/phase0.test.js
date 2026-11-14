// Phase 0 baseline behaviour tests. Runs the real index.html in headless Chrome.
// External network is blocked on purpose (also tests offline fallbacks).
const { createRequire } = require('module');
const { chromium } = createRequire('/opt/npm-tools/package.json')('playwright');
const path = require('path');
const fs = require('fs');

const URL = 'http://localhost:8765/index.html';
const FX = process.argv[2];            // fixtures dir
const OUT = process.argv[3];           // results json path
const SHOTS = path.dirname(OUT);
const files = ['Artist A - Song One.wav', 'Artist B - Song Two.wav', 'Artist C - Song Three.wav'].map(f => path.join(FX, f));

const results = [];
const rec = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail: String(detail) }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? '  :: ' + detail : '')); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function newPage(browser, viewport) {
  const ctx = await browser.newContext({ viewport: viewport || { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|net::/.test(m.text())) errs.push('console: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith('http://localhost:8765') ? r.continue() : r.abort());
  return { ctx, page, errs };
}
const boot = async page => { await page.goto(URL); await page.waitForFunction(() => document.querySelector('#libStat') && document.querySelector('#libStat').textContent.length > 0 && typeof DB !== 'undefined' && DB.ok); await sleep(300); };

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
  const { ctx, page, errs } = await newPage(browser);
  try {
    // ---- T1 load + DB shape
    await boot(page);
    const dbinfo = await page.evaluate(() => new Promise(res => { const r = indexedDB.open('plainsong'); r.onsuccess = () => { const d = r.result; const o = { v: d.version, stores: [...d.objectStoreNames] }; o.kp = {}; o.stores.forEach(s => { const t = d.transaction(s).objectStore(s); o.kp[s] = t.keyPath; }); d.close(); res(o); }; }));
    rec('T1 page boots, no JS errors', errs.length === 0, errs.join(' | '));
    rec('T1 IndexedDB plainsong v1 with stores tracks/playlists/blobs/kv', dbinfo.v === 1 && ['blobs', 'kv', 'playlists', 'tracks'].every(s => dbinfo.stores.includes(s)), JSON.stringify(dbinfo));
    const offl = await page.evaluate(async () => { await new Promise(r => setTimeout(r, 2500)); return document.querySelector('#view').innerText.includes('reach Audius'); });
    rec('T8 offline: Audius shelf shows graceful "couldn\'t reach" message, app alive', offl);

    // ---- T2 import
    await page.setInputFiles('#fileIn', files);
    await page.waitForFunction(() => S.tracks.size === 3, null, { timeout: 30000 });
    await sleep(500);
    const lib = await page.evaluate(async () => {
      const ts = [...S.tracks.values()].map(t => ({ title: t.title, artist: t.artist, dur: Math.round(t.duration), kind: t.kind }));
      const cnt = s => DB.all(s).then(a => a.length);
      return { ts, tracks: await cnt('tracks'), blobs: await cnt('blobs') };
    });
    rec('T2 import 3 WAVs: titles/artists from filenames, durations probed', lib.ts.length === 3 && lib.ts.every(t => t.dur === 12 && t.artist.startsWith('Artist')), JSON.stringify(lib.ts));
    rec('T2 IndexedDB holds 3 track records + 3 audio blobs', lib.tracks === 3 && lib.blobs === 3, `tracks=${lib.tracks} blobs=${lib.blobs}`);
    await page.setInputFiles('#fileIn', files);
    await sleep(2500);
    rec('T2 re-import is de-duplicated', await page.evaluate(() => S.tracks.size) === 3);

    // ---- T3 play local
    await page.click('[data-nav="library"]');
    await page.waitForSelector('#songList .row[data-tid]');
    await page.click('#songList .row[data-tid] .r-main');
    await page.waitForFunction(() => !aL.paused && aL.currentTime > .4, null, { timeout: 10000 });
    const g = await page.evaluate(() => ({ A: A === aL, G: !!G, bands: G && G.bands.length, st: G && G.ctx.state, q: S.queue.length, qi: S.qi }));
    rec('T3 local playback starts; Web Audio graph (10 EQ bands) created on aL', g.A && g.G && g.bands === 10 && g.q === 3, JSON.stringify(g));

    // ---- T4 speed
    await page.click('#speedBtn');
    rec('T4 speed popover opens', await page.isVisible('#speedPop'));
    await page.evaluate(() => { const s = document.querySelector('.spd-slider'); s.value = 2; s.dispatchEvent(new Event('input', { bubbles: true })); });
    let sp = await page.evaluate(() => ({ r: aL.playbackRate, w: aW.playbackRate, d: aL.defaultPlaybackRate, btn: document.querySelector('#speedBtn').textContent, pp: aL.preservesPitch }));
    rec('T4 slider sets 2x on both elements, button label updates, pitch preserved by default', sp.r === 2 && sp.w === 2 && sp.d === 2 && sp.btn === '2×' && sp.pp === true, JSON.stringify(sp));
    await page.evaluate(() => { const c = document.querySelector('.spd-pitch'); c.checked = false; c.dispatchEvent(new Event('change', { bubbles: true })); });
    rec('T4 "Keep original pitch" off -> preservesPitch=false', await page.evaluate(() => aL.preservesPitch === false && S.pitch === false));
    await page.evaluate(() => { const c = document.querySelector('.spd-pitch'); c.checked = true; c.dispatchEvent(new Event('change', { bubbles: true })); });
    rec('T4 pitch toggle back on', await page.evaluate(() => aL.preservesPitch === true));
    await page.click('[data-act="rate"][data-v="0.5"]');
    rec('T4 preset chip 0.5x', await page.evaluate(() => aL.playbackRate === .5));
    await page.keyboard.press('Escape'); await page.click('body', { position: { x: 640, y: 300 } });
    rec('T4 Escape/outside click closes popover', !(await page.isVisible('#speedPop')));
    await page.keyboard.press('\\');
    let k = [await page.evaluate(() => S.rate)];
    await page.keyboard.press(']'); k.push(await page.evaluate(() => S.rate));
    await page.keyboard.press(']'); await page.keyboard.press('['); k.push(await page.evaluate(() => S.rate));
    rec('T4 keys: \\ resets to 1, ] +0.05, [ -0.05', k[0] === 1 && k[1] === 1.05 && k[2] === 1.05, JSON.stringify(k));
    const clampT = await page.evaluate(() => { setRate(.01); const lo = S.rate; setRate(9); const hi = S.rate; setRate(1); return [lo, hi]; });
    rec('T4 rate clamped to 0.25..3', clampT[0] === .25 && clampT[1] === 3, JSON.stringify(clampT));

    // ---- T5 A-B
    await page.evaluate(() => { setRate(2); A.pause(); });
    await page.evaluate(() => { A.currentTime = 2; }); await sleep(150);
    await page.keyboard.press('a');
    await page.evaluate(() => { A.currentTime = 4; }); await sleep(150);
    await page.keyboard.press('a');
    const ab1 = await page.evaluate(() => ({ a: S.ab.a, b: S.ab.b, txt: document.querySelector('#abBtn').textContent, live: document.querySelector('#abBtn').classList.contains('live'), lbl: document.querySelector('#abBtn').getAttribute('aria-label'), vis: ['#sbA', '#sbB', '#sbBand'].map(s => !document.querySelector(s).hidden), cur: A.currentTime }));
    rec('T5 A key sets start then end; button live; seek-bar bracket + band shown', ab1.a === 2 && ab1.b === 4 && ab1.live && ab1.txt === 'A–B' && ab1.vis.every(Boolean), JSON.stringify(ab1));
    rec('T5 setting B jumps playhead back to A', Math.abs(ab1.cur - 2) < .4, 'cur=' + ab1.cur);
    await page.evaluate(() => { A.play(); });
    const samples = [];
    for (let i = 0; i < 70; i++) { samples.push(await page.evaluate(() => A.currentTime)); await sleep(100); }
    const maxT = Math.max(...samples); const wraps = samples.filter((v, i) => i && samples[i - 1] - v > 1).length;
    rec('T5 loop holds playhead inside A..B at 2x for 7s', maxT < 4.6 && Math.min(...samples) > 1.8 && wraps >= 3, `max=${maxT.toFixed(2)} min=${Math.min(...samples).toFixed(2)} wraps=${wraps}`);
    // nudge UI
    await page.click('#npToggle'); await page.click('#npTabs [data-tab="sound"]');
    await page.waitForSelector('[data-act="abNudge"]');
    await page.click('[data-act="abNudge"][data-w="b"][data-dt="0.1"]');
    await page.click('[data-act="abNudge"][data-w="a"][data-dt="-0.1"]');
    const nud = await page.evaluate(() => ({ a: S.ab.a, b: S.ab.b, ta: document.querySelector('#abA').textContent, tb: document.querySelector('#abB').textContent }));
    rec('T5 0.1 s nudges move A earlier and B later, readouts update', nud.a === 1.9 && nud.b === 4.1 && nud.ta === '0:01.9' && nud.tb === '0:04.1', JSON.stringify(nud));
    await page.evaluate(() => { A.pause(); A.currentTime = 1; });
    const before = await page.evaluate(() => S.ab.b);
    await page.click('[data-act="abSet"][data-w="b"]');
    rec('T5 invalid B (before A) is rejected', await page.evaluate(() => S.ab.b) === before);
    await page.evaluate(() => { A.play(); });
    await page.keyboard.press('a');
    const cl = await page.evaluate(() => ({ a: S.ab.a, b: S.ab.b, txt: document.querySelector('#abBtn').textContent, vis: ['#sbA', '#sbB', '#sbBand'].map(s => !document.querySelector(s).hidden) }));
    rec('T5 third A press clears loop and hides bracket', cl.a === null && cl.b === null && cl.vis.every(v => !v) && cl.txt === 'A–B', JSON.stringify(cl));
    await page.evaluate(() => { setRate(1); abReset(); A.currentTime = 2; abSet('a'); A.currentTime = 4; abSet('b'); });
    await page.click('#nextBtn'); await sleep(400);
    rec('T5 A–B clears when the song changes', await page.evaluate(() => S.ab.a === null && S.ab.b === null));

    // ---- T6 queue / repeat / ended
    await page.evaluate(() => { A.pause(); });
    const q0 = await page.evaluate(() => S.qi);
    await page.click('#nextBtn'); await sleep(300);
    const q1 = await page.evaluate(() => S.qi);
    await page.evaluate(() => { A.currentTime = 1; });
    await page.click('#prevBtn'); await sleep(300);
    const q2 = await page.evaluate(() => S.qi);
    rec('T6 next/prev move through queue (prev <3s goes back)', q1 === q0 + 1 && q2 === q1 - 1, `q0=${q0} q1=${q1} q2=${q2}`);
    await page.evaluate(() => { jump(0); }); await sleep(500);
    await page.evaluate(() => { A.currentTime = A.duration - .6; A.play(); }); await sleep(1800);
    rec('T6 track end auto-advances to next queue item', await page.evaluate(() => S.qi) === 1);
    await page.evaluate(() => { jump(2); }); await sleep(500);
    await page.evaluate(() => { S.repeat = 0; A.currentTime = A.duration - .5; A.play(); }); await sleep(1800);
    const endq = await page.evaluate(() => ({ qi: S.qi, paused: A.paused }));
    rec('T6 repeat off: end of queue stops on last song', endq.qi === 2 && endq.paused, JSON.stringify(endq));
    await page.evaluate(() => { S.repeat = 1; A.currentTime = A.duration - .5; A.play(); }); await sleep(1800);
    rec('T6 repeat all: wraps to first song', await page.evaluate(() => S.qi) === 0);
    await page.evaluate(() => { S.repeat = 2; A.currentTime = A.duration - .5; A.play(); }); await sleep(1800);
    const r1 = await page.evaluate(() => ({ qi: S.qi, t: A.currentTime, p: A.paused }));
    rec('T6 repeat one: restarts same song', r1.qi === 0 && r1.t < 6 && !r1.p, JSON.stringify(r1));
    await page.evaluate(() => { S.repeat = 0; });

    // ---- T7 EQ + play counter + like
    await page.selectOption('#eqPreset', 'Bass boost');
    rec('T7 EQ preset applies to biquad gains', await page.evaluate(() => G.bands[0].gain.value === 6 && G.bands[1].gain.value === 5));
    await page.evaluate(() => { setRate(1); A.currentTime = 5.5; A.play(); }); await sleep(1800);
    const pc = await page.evaluate(async () => { const id = S.cur; const rec = await DB.get('tracks', id); return { plays: rec.plays, mem: curT().plays }; });
    rec('T7 play counter increments past threshold and persists to IndexedDB', pc.plays >= 1, JSON.stringify(pc));
    await page.keyboard.press('l');
    const lk = await page.evaluate(async () => (await DB.get('tracks', S.cur)).liked);
    rec('T7 L key likes song and persists', lk === true);

    // ---- T10 persistence across reload
    await page.evaluate(() => { setRate(1.5); S.pitch = false; applyRate(); syncSpeed(); S.vol = .55; applyVol(); saveSession(); jump(1); });
    await sleep(1500);
    await page.evaluate(() => { saveSession(); }); await sleep(1200);
    await page.reload(); await page.waitForFunction(() => typeof DB !== 'undefined' && DB.ok && S.tracks.size === 3); await sleep(800);
    const ps = await page.evaluate(() => ({ rate: S.rate, pitch: S.pitch, pp: aL.preservesPitch, pr: aL.playbackRate, btn: document.querySelector('#speedBtn').textContent, vol: S.vol, qi: S.qi, ql: S.queue.length, eq: S.eqPreset, liked: [...S.tracks.values()].filter(t => t.liked).length, ab: S.ab }));
    rec('T10 session restore: speed/pitch/volume/queue/EQ/likes survive reload', ps.rate === 1.5 && ps.pitch === false && ps.pr === 1.5 && ps.pp === false && ps.btn === '1.5×' && ps.vol === .55 && ps.qi === 1 && ps.ql === 3 && ps.eq === 'Bass boost' && ps.liked === 1, JSON.stringify(ps));
    rec('T10 A–B intentionally not persisted', ps.ab.a === null && ps.ab.b === null);
    await page.screenshot({ path: path.join(SHOTS, 'desktop.png') });

    // ---- T12 ID3 parser unit check + data inventory
    const id3 = await page.evaluate(async () => {
      const te = new TextEncoder(); const fr = (id, txt) => { const b = te.encode('\x00' + txt); const h = new Uint8Array(10); h.set(te.encode(id)); new DataView(h.buffer).setUint32(4, b.length); return [...h, ...b]; };
      const body = [...fr('TIT2', 'Hello Title'), ...fr('TPE1', 'Some Artist'), ...fr('TALB', 'Some Album'), ...fr('TRCK', '7/12')];
      const n = body.length; const hdr = [0x49, 0x44, 0x33, 3, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127];
      const f = new File([new Uint8Array([...hdr, ...body, 0, 0, 0, 0])], 'x.mp3'); return readTags(f);
    });
    rec('T12 ID3v2.3 parser reads title/artist/album/track', id3.title === 'Hello Title' && id3.artist === 'Some Artist' && id3.album === 'Some Album' && id3.track === 7, JSON.stringify(id3));
    const inv = await page.evaluate(async () => {
      const kv = await new Promise(res => { const r = indexedDB.open('plainsong'); r.onsuccess = () => { const d = r.result; const tx = d.transaction('kv'); const o = tx.objectStore('kv'); const q = o.getAllKeys(); tx.oncomplete = () => { d.close(); res(q.result); }; }; });
      const t = [...S.tracks.values()][0]; const b = await DB.get('blobs', t.id);
      const ss = await DB.get('kv', 'session');
      return { kvKeys: kv, trackFields: Object.keys(t), blobType: b && b.type, blobSize: b && b.size, sessionKeys: Object.keys(ss), ls: Object.keys(localStorage) };
    });
    fs.writeFileSync(path.join(SHOTS, 'inventory.json'), JSON.stringify(inv, null, 2));
    rec('T12 data inventory captured (kv keys, track fields, localStorage)', inv.kvKeys.includes('session'), JSON.stringify(inv));
    rec('T-final no uncaught JS errors across whole desktop run', errs.length === 0, errs.join(' | '));
  } catch (e) { rec('HARNESS exception (desktop)', false, e.stack || e.message); }
  await ctx.close();

  // ---- T9 mobile layout
  const m = await newPage(browser, { width: 390, height: 844 });
  try {
    await boot(m.page);
    const lay = await m.page.evaluate(() => { const r = s => document.querySelector(s).getBoundingClientRect(); const n = r('#nav'), b = r('#bar'); return { sw: document.scrollingElement.scrollWidth, iw: innerWidth, navVisible: n.height > 0 && n.bottom <= innerHeight + 1, barVisible: b.height > 0 && b.bottom <= innerHeight + 1, navButtons: document.querySelectorAll('#nav button').length }; });
    rec('T9 mobile 390px: no horizontal overflow, nav + player bar on screen', lay.sw <= lay.iw && lay.navVisible && lay.barVisible && lay.navButtons === 3, JSON.stringify(lay));
    await m.page.click('#speedBtn');
    const pop = await m.page.evaluate(() => { const r = document.querySelector('#speedPop').getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, iw: innerWidth, ih: innerHeight }; });
    rec('T9 mobile: speed popover stays inside viewport', pop.l >= 0 && pop.r <= pop.iw && pop.t >= 0 && pop.b <= pop.ih, JSON.stringify(pop));
    await m.page.keyboard.press('Escape');
    await m.page.screenshot({ path: path.join(SHOTS, 'mobile.png') });
    rec('T9 no uncaught JS errors on mobile run', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception (mobile)', false, e.stack || e.message); }
  await m.ctx.close();
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
  const fails = results.filter(r => !r.ok);
  console.log(`\nTOTAL ${results.length}  PASS ${results.length - fails.length}  FAIL ${fails.length}`);
  process.exit(0);
})();
