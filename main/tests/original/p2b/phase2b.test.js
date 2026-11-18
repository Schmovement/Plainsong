// Phase 2B tests: the restore flow (preview -> separate confirmation -> one atomic verified four-store replace -> rebuild).
// Isolated data only: generated WAV tones + generated archives in a throw-away browser profile. No live services.
// usage: node phase2b.test.js <fixtures-dir(wavs)> <work-dir> <results.json>
const { createRequire } = require('module');
const { chromium } = createRequire('/opt/npm-tools/package.json')('playwright');
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const URL = process.env.PS_URL || 'http://localhost:8765/index.html'; const ORIGIN = new (require('url').URL)(URL).origin;
const [FX, WORK, OUT] = process.argv.slice(2);
const HERE = __dirname, MAIN = path.join(HERE, 'fixtures', 'p1-main-backup.zip'), MIN = path.join(HERE, 'fixtures', 'p1-minimal-backup.zip');
const wavs = ['Artist A - Song One.wav', 'Artist B - Song Two.wav', 'Artist C - Song Three.wav'].map(f => path.join(FX, f));
fs.mkdirSync(WORK, { recursive: true });
const BAD = path.join(WORK, 'bad'); fs.rmSync(BAD, { recursive: true, force: true });
const SHOTS = path.join(WORK, 'shots'); fs.mkdirSync(SHOTS, { recursive: true });

const ONLY = (process.env.ONLY || '').split(',').filter(Boolean); const want = n => !ONLY.length || ONLY.includes(String(n));
const results = [];
const rec = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail: String(detail).slice(0, 800) }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (!ok && detail ? '  :: ' + String(detail).slice(0, 600) : '')); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const py = args => { const r = spawnSync('python3', ['-I', ...args], { encoding: 'utf-8', maxBuffer: 1 << 28 }); if (r.status !== 0) throw new Error(args[0] + ' failed: ' + r.stderr); return r.stdout; };
const truthOf = (tag, f) => { const o = path.join(WORK, tag + '.truth.json'); py([path.join(HERE, 'extract_expected.py'), f, o]); return JSON.parse(fs.readFileSync(o, 'utf-8')); };

// ---- page instrumentation (installed before the app loads) ----
const SPY = () => {
  window.__w = { tx: [], idbWrite: 0, ls: 0 }; window.__plays = 0;
  const T = IDBDatabase.prototype.transaction;
  IDBDatabase.prototype.transaction = function (s, m) { if (m && m !== 'readonly') window.__w.tx.push(String(s) + ':' + m); return T.apply(this, arguments); };
  for (const [C, ms] of [[IDBObjectStore, ['put', 'add', 'delete', 'clear']], [IDBCursor, ['update', 'delete']]])
    for (const m of ms) { const f = C.prototype[m]; C.prototype[m] = function () { window.__w.idbWrite++; return f.apply(this, arguments); }; }
  for (const m of ['setItem', 'removeItem', 'clear']) { const f = Storage.prototype[m]; Storage.prototype[m] = function () { window.__w.ls++; return f.apply(this, arguments); }; }
  document.addEventListener('play', () => { window.__plays++; }, true);   // media 'play' events do not bubble; capture sees them
};
const INJECT = () => {   // wraps the app's own readwrite transaction (not the app code) to inject failures
  window.__inj = { mode: null, puts: 0, nth: 3, log: [] };
  const real = DB.db.transaction.bind(DB.db);
  DB.db.transaction = function (stores, m, o) {
    const tx = real(stores, m, o), I = window.__inj;
    if (m !== 'readwrite' || !I.mode || !(Array.isArray(stores) && stores.length === 4)) return tx;   // only the restore's own four-store transaction (not the pre-commit session flush)
    if (I.mode === 'tx-throws') { try { tx.abort(); } catch (e) { } throw new DOMException('injected', 'InvalidStateError'); }
    const wrap = (os, name) => new Proxy(os, {
      get(t, k) {
        if (k === 'put') return function (v, key) {
          I.puts++; I.log.push(name);
          if (I.mode === 'put-throw' && I.puts === I.nth) throw new DOMException('injected quota failure', 'QuotaExceededError');
          if (I.mode === 'put-throw-blob' && name === 'blobs') throw new DOMException('injected quota failure', 'QuotaExceededError');
          if (I.mode === 'abort-after' && I.puts === I.nth) { const r = t.put(v, key); tx.abort(); return r; }
          if (I.mode === 'async-error' && I.puts === I.nth) { const r = t.put(v, key); t.add(v, key); return r; }
          if (I.mode === 'verify-drop' && name === 'tracks' && I.puts === 2) return {};
          if (I.mode === 'verify-truncate-blob' && name === 'blobs') return t.put(v.slice(0, Math.max(0, v.size - 1), v.type), key);
          if (I.mode === 'verify-mutate-record' && name === 'tracks') return t.put({ ...v, title: v.title + ' (tampered)' });
          if (I.mode === 'verify-mutate-kv' && name === 'kv' && key === 'session') return t.put({ ...v, vol: 0.123 }, key);
          return key === undefined ? t.put(v) : t.put(v, key);
        };
        const v = t[k]; return typeof v === 'function' ? v.bind(t) : v;
      }
    });
    return new Proxy(tx, { get(t, k) { if (k === 'objectStore') return n => wrap(t.objectStore(n), n); const v = t[k]; return typeof v === 'function' ? v.bind(t) : v; }, set(t, k, v) { t[k] = v; return true; } });
  };
};

async function newPage(browser, { noIdb, viewport } = {}) {
  const ctx = await browser.newContext({ viewport: viewport || { width: 1280, height: 800 }, acceptDownloads: true });
  await ctx.addInitScript(SPY);
  if (noIdb) await ctx.addInitScript(() => { Object.defineProperty(window, 'indexedDB', { value: undefined, configurable: true }); });
  const page = await ctx.newPage(); const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|net::/.test(m.text())) errs.push('console: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith(ORIGIN) ? r.continue() : r.abort());
  page.__dl = 0; page.on('download', () => { page.__dl++; });
  // The OS file chooser opens BEFORE any page modal. A persistent listener (attached at page creation, so interception is already on
  // long before any click) queues every chooser; nothing depends on a waitForEvent racing the key press.
  page.__fc = []; page.on('filechooser', fc => { page.__fc.push(fc); });
  return { ctx, page, errs };
}
async function boot(page, needDb = true) {
  await page.goto(URL);
  await page.waitForFunction(nd => document.querySelector('#libStat') && document.querySelector('#libStat').textContent.length > 0 && (!nd || (typeof DB !== 'undefined' && DB.ok)), needDb);
  await sleep(300);
  if (needDb) await page.evaluate(INJECT);
}
const wr = p => p.evaluate(() => JSON.parse(JSON.stringify(window.__w)));
const wrReset = p => p.evaluate(() => { window.__w = { tx: [], idbWrite: 0, ls: 0 }; });

// independent snapshot of everything (own code): all four stores incl. secret keys, blob sha256, all localStorage
const snap = (page, o = {}) => page.evaluate(async o => {
  const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  const tx = DB.db.transaction(['tracks', 'playlists', 'blobs', 'kv'], 'readonly'); const r = { tracks: [], playlists: [], kv: [], bl: [] };
  const cur = (n, f) => { const q = tx.objectStore(n).openCursor(); q.onsuccess = () => { const c = q.result; if (c) { f(c); c.continue(); } }; };
  cur('tracks', c => r.tracks.push(c.value)); cur('playlists', c => r.playlists.push(c.value)); cur('kv', c => { if (!(o.skipKv || []).includes(c.key)) r.kv.push({ key: c.key, value: c.value }); }); cur('blobs', c => r.bl.push({ key: c.key, b: c.value }));
  await new Promise(res => { tx.oncomplete = res; });
  const blobs = []; for (const x of r.bl) blobs.push({ key: x.key, size: x.b.size, type: x.b.type, sha256: hex(await crypto.subtle.digest('SHA-256', await x.b.arrayBuffer())) });
  const ls = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); ls[k] = localStorage.getItem(k); }
  return { tracks: r.tracks, playlists: r.playlists, kv: r.kv, blobs, ls };
}, o);
const J = v => JSON.stringify(v);
const sameSnap = (a, b) => J(a) === J(b);

// ---- UI helpers ----
const dlgText = p => p.evaluate(() => { const d = document.querySelector('#dlg'); return d && d.open ? d.innerText : ''; });
const waitText = (p, re, ms = 40000) => p.waitForFunction(r => { const d = document.querySelector('#dlg'); return d.open && new RegExp(r).test(d.innerText); }, re, { timeout: ms });
const END = 'Library restored|rolled back|Restore stopped|needs a reload|can’t be restored|isn’t available|Restore failed|Restore cancelled';
async function openFile(p, file) { await p.setInputFiles('#restoreIn', file); }
// Run `trigger` exactly ONCE (a click or one key press - never repeated) and wait for the chooser it opens.
// Returns { fc, inputClicks }: fc is null when no chooser was captured; inputClicks says whether the app DID call #restoreIn.click(),
// which separates "the app did not open the chooser" from "the chooser was not captured".
async function chooserVia(p, trigger, ms = 10000) {
  const n = p.__fc.length;
  await p.evaluate(() => { window.__rin = 0; const i = document.querySelector('#restoreIn'); if (!i.__probe) { i.__probe = true; i.addEventListener('click', () => { window.__rin++; }, true); } });
  await trigger();
  const t0 = Date.now(); while (p.__fc.length === n && Date.now() - t0 < ms) await sleep(40);
  return { fc: p.__fc.length > n ? p.__fc[n] : null, inputClicks: await p.evaluate(() => window.__rin), extra: p.__fc.length - n };
}
async function toPreview(p, file) { await openFile(p, file); await waitText(p, 'Restore preview|can’t be restored|isn’t available'); return dlgText(p); }
async function toConfirm(p, file) { const t = await toPreview(p, file); if (!/Restore preview/.test(t)) return t; await p.click('#dlg [data-bk="go"]'); await waitText(p, 'Replace your library'); return dlgText(p); }
async function replace(p) { const ack = await p.$('#rsAck'); if (ack) await ack.check(); await p.click('#dlg [data-bk="replace"]'); }
async function finish(p, ms = 60000) { await waitText(p, END, ms); const t = await dlgText(p); await p.click('#dlg [data-bk="ok"]'); await p.waitForFunction(() => !document.querySelector('#dlg').open); return t; }
async function fullRestore(p, file) { const t = await toConfirm(p, file); if (!/Replace your library/.test(t)) throw new Error('did not reach confirm: ' + t.slice(0, 200)); await replace(p); return finish(p); }
const dlgClosed = p => p.evaluate(() => !document.querySelector('#dlg').open);
const toastText = p => p.evaluate(() => document.querySelector('#toast').textContent);
const gate = (p, fn, nth = 1) => p.evaluate(([fn, nth]) => { const orig = window[fn]; let n = 0; window.__g = window.__g || {}; const g = window.__g[fn] = { entered: false, orig }; g.p = new Promise(r => { g.open = r; }); window[fn] = async function (...a) { n++; if (n === nth) { g.entered = true; await g.p; } return orig.apply(this, a); }; }, [fn, nth]);
const gateWait = (p, fn) => p.waitForFunction(fn => window.__g[fn].entered, fn, { timeout: 30000 });
const gateOpen = (p, fn) => p.evaluate(fn => { window.__g[fn].open(); window[fn] = window.__g[fn].orig; }, fn);
const inject = (p, mode, nth = 3) => p.evaluate(([m, n]) => { window.__inj.mode = m; window.__inj.nth = n; window.__inj.puts = 0; window.__inj.log = []; }, [mode, nth]);
const injected = p => p.evaluate(() => ({ puts: window.__inj.puts, log: window.__inj.log.slice() }));

// a populated, quiescent library of isolated test data: 3 WAV songs, a playlist, a liked song, a queued (paused) track,
// a secret kv key (must survive any restore), a custom kv key (must not), a light theme, volume .55
async function seedLib(page) {
  await page.setInputFiles('#fileIn', wavs); await page.waitForFunction(() => S.tracks.size >= 3, null, { timeout: 30000 }); await sleep(500);
  await page.evaluate(async () => {
    const ids = [...S.tracks.keys()];
    S.playlists.push({ id: 'pl-old', name: 'Old list', ids: ids.slice(0, 2), created: 1 }); await savePlaylists();
    const t = S.tracks.get(ids[0]); t.liked = true; t.plays = 7; await DB.put('tracks', t);
    await DB.put('kv', { token: 'SEKRET-VALUE-DO-NOT-LOSE' }, 'secret:lb-token'); await DB.put('kv', { a: 1 }, 'custom:old');
    localStorage.setItem('ps-theme', 'light'); document.documentElement.dataset.theme = 'light'; themeIcon();
    S.vol = .55; applyVol(); S.queue = ids.slice(); S.orig = ids.slice(); S.qi = 1; await loadCurrent(false);
  });
  await sleep(1500); await page.evaluate(() => settleSession()); await sleep(1500);
}
const OLD = { secret: { token: 'SEKRET-VALUE-DO-NOT-LOSE' } };

// ---- expectations against independent ground truth ----
function expectRestored(tag, s, truth, secretBefore) {
  const kvNoSecret = s.kv.filter(x => !x.key.toLowerCase().startsWith('secret:')), sec = s.kv.filter(x => x.key.toLowerCase().startsWith('secret:'));
  rec(`${tag}: songs identical to the backup (every field, key order)`, J(s.tracks) === J(truth.tracks), `${s.tracks.length} vs ${truth.tracks.length}`);
  rec(`${tag}: playlists identical (ids order kept)`, J(s.playlists) === J(truth.playlists));
  rec(`${tag}: saved settings identical (session, history, custom keys)`, J(kvNoSecret) === J(truth.kv), J(kvNoSecret.map(x => x.key)) + ' vs ' + J(truth.kv.map(x => x.key)));
  rec(`${tag}: ${truth.blobs.length} audio blobs identical (key, MIME, size, SHA-256) and no old audio left`, J(s.blobs.map(b => ({ key: b.key, type: b.type, size: b.size, sha256: b.sha256 }))) === J(truth.blobs));
  rec(`${tag}: this browser's secret: key survived untouched (value kept, never in a backup)`, J(sec) === J(secretBefore), J(sec));
}

(async () => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });   // so an autoplay bug WOULD play
  py([path.join(HERE, 'make_bad_archives.adapted.py'), MAIN, BAD, '--big']);
  const B = n => path.join(BAD, n + '.zip');
  const truthMain = truthOf('main', MAIN), truthMin = truthOf('min', MIN);

  // =================================================================== 1. happy path into a POPULATED library, via the real button
  if (want(1)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    const q0 = await snap(page); await sleep(1800); const q1 = await snap(page);
    rec('test library is quiescent (two snapshots 1.8 s apart identical)', sameSnap(q0, q1));
    rec('library has 3 songs, 3 audio blobs, secret key, custom key, theme light', q0.tracks.length === 3 && q0.blobs.length === 3 && q0.kv.some(x => x.key === 'secret:lb-token') && q0.kv.some(x => x.key === 'custom:old') && q0.ls['ps-theme'] === 'light');
    rec('restore buttons exist: sidebar and top bar, with accessible names', await page.evaluate(() => { const a = document.querySelector('.side-foot [data-act="restore"]'), b = document.querySelector('.top [data-act="restore"]'); return !!a && !!b && /Restore/.test(a.textContent) && /Restore/.test(b.getAttribute('aria-label')); }));
    await wrReset(page); await page.evaluate(() => { window.__plays = 0; });
    const c1 = await chooserVia(page, () => page.click('.side-foot [data-act="restore"]')), fc = c1.fc;
    rec('sidebar "Restore from backup…" opens exactly one file chooser (zip only)', !!fc && c1.extra === 1 && await page.evaluate(() => /zip/.test(document.querySelector('#restoreIn').accept)), J({ inputClicks: c1.inputClicks, choosers: c1.extra }));
    if (fc) await fc.setFiles(MAIN); else await openFile(page, MAIN); await waitText(page, 'Restore preview');
    const pv = await dlgText(page); await page.screenshot({ path: path.join(SHOTS, 'p2b-preview-desktop.png') });
    rec('preview says nothing has changed and lists file, songs (5 with audio + 1 web), 2 playlists, 6 audio files, orphan, queue, history, theme', /Nothing has been changed yet/.test(pv) && /p1-main-backup\.zip/.test(pv) && /6 \(5 with audio, 1 saved web\)/.test(pv) && /Playlists\s*2/.test(pv) && /6, .*MB.*1 with no song entry/.test(pv) && /queue of 4/.test(pv) && /2 plays/.test(pv) && /Theme\s*dark/.test(pv), pv);
    rec('preview shows the current library (3 songs, 1 playlist) and the web hosts the backup refers to', /Your library now[\s\S]*Songs\s*3[\s\S]*Playlists\s*1/.test(pv) && /audius\.co/.test(pv) && /example\.invalid/.test(pv));
    rec('preview: Cancel is focused first; there is no destructive button yet', await page.evaluate(() => document.activeElement.dataset.bk === 'no' && !document.querySelector('#dlg [data-bk="replace"]')));
    const w1 = await wr(page); rec('preview stage: zero writes so far', w1.tx.length === 0 && w1.idbWrite === 0 && w1.ls === 0, J(w1));
    rec('preview stage: database and localStorage byte-identical', sameSnap(await snap(page), q0));
    await page.click('#dlg [data-bk="go"]'); await waitText(page, 'Replace your library');
    const cf = await dlgText(page); await page.screenshot({ path: path.join(SHOTS, 'p2b-confirm-desktop.png') });
    rec('confirmation is a separate step naming what is deleted (3 songs, 1 playlist, 3 audio files, queue/history/settings), what replaces it, what is kept, and warns about other tabs', /permanently deletes/.test(cf) && /Deleted: 3 songs, 1 playlist, 3 audio files/.test(cf) && /Restored instead: 6 songs, 2 playlists, 6 audio files/.test(cf) && /Kept: logins or keys/.test(cf) && /other Plainsong tabs/.test(cf));
    rec('confirmation: Cancel focused; "Replace library" disabled until the checkbox is ticked', await page.evaluate(() => document.activeElement.dataset.bk === 'no' && document.querySelector('#dlg [data-bk="replace"]').disabled === true));
    await page.click('#dlg [data-bk="replace"]', { force: true, timeout: 800 }).catch(() => { });
    rec('clicking the disabled Replace button does nothing', /Replace your library/.test(await dlgText(page)) && sameSnap(await snap(page), q0));
    await page.check('#rsAck'); rec('ticking the checkbox enables Replace', await page.evaluate(() => !document.querySelector('#dlg [data-bk="replace"]').disabled));
    await page.click('#dlg [data-bk="replace"]');
    const res = await finish(page); await sleep(300);
    rec('result dialog: restored counts, "Nothing is playing", theme set to dark and described as a separate step', /Library restored/.test(res) && /6 songs, 2 playlists and 6 audio files/.test(res) && /Nothing is playing/.test(res) && /Theme set to dark/.test(res) && /Saved separately/.test(res), res);
    const s = await snap(page); expectRestored('restore into populated library', s, truthMain, q0.kv.filter(x => x.key === 'secret:lb-token'));
    rec('old songs, old playlist, old custom setting and old audio are gone', !s.tracks.some(t => q0.tracks.some(o => o.id === t.id)) && !s.playlists.some(p => p.id === 'pl-old') && !s.kv.some(x => x.key === 'custom:old'));
    rec('ps-theme: backup value dark applied to localStorage AFTER the database commit', s.ls['ps-theme'] === 'dark' && await page.evaluate(() => document.documentElement.dataset.theme === 'dark'));
    const st = await page.evaluate(() => ({ tr: S.tracks.size, pl: S.playlists.map(p => p.id), q: S.queue.length, cur: S.cur, qi: S.qi, vol: S.vol, view: S.view.name, stack: S.stack.length, paused: aL.paused && aW.paused, plays: window.__plays, lock: DB.lock, busy: [!!S.restoreBusy, !!S.restoring, !!S.backupBusy, !!S.importBusy], lib: document.querySelector('#libStat').innerText, bar: document.querySelector('#barTitle').textContent, src: aL.getAttribute('src') ? 'set' : 'none', tracksInView: document.querySelectorAll('#view .row[data-tid]').length }));
    const sessT = truthMain.kv.find(x => x.key === 'session').value;
    rec('rebuilt app state: 6 songs, playlists [pl-1,pl-2], queue and index from the session, volume from the session, home view', st.tr === 6 && J(st.pl) === J(['pl-1', 'pl-2']) && st.q === 4 && st.qi === sessT.qi && Math.abs(st.vol - sessT.vol) < 1e-9 && st.view === 'home' && st.stack === 0, J(st));
    rec('NO AUTOPLAY: both audio elements paused and zero media play events since the restore started (autoplay was allowed in this browser)', st.paused && st.plays === 0, J(st));
    rec('restored current track is loaded (not playing) and shown in the bar', st.src === 'set' && /Song One/.test(st.bar), st.bar);
    rec('locks released: DB.lock false, no busy flags, library counter shows 6 songs', st.lock === false && J(st.busy) === J([false, false, false, false]) && /6 songs/.test(st.lib), J(st));
    const w2 = await wr(page); rec('exactly one read-write transaction touched the database during the restore besides the pre-commit session flush', w2.tx.filter(x => x === 'tracks,playlists,blobs,kv:readwrite').length === 1, J(w2.tx));
    await sleep(1500); rec('nothing wrote over the restored data afterwards (snapshot 1.5 s later identical)', sameSnap(await snap(page), s));
    // restored local playback really works
    await page.click('#playBtn'); await page.waitForFunction(() => aL.currentTime > .4 && !aL.paused, null, { timeout: 15000 }).catch(() => { });
    const pl = await page.evaluate(() => ({ t: aL.currentTime, paused: aL.paused, err: aL.error && aL.error.code, dur: aL.duration }));
    rec('restored local song plays from the restored audio bytes (currentTime advances)', pl.t > .4 && !pl.paused && !pl.err, J(pl));
    await page.click('#playBtn'); await sleep(300);
    // other views and a normal write after restore
    await page.evaluate(() => { go('albums', {}); }); await sleep(200);
    await page.evaluate(async () => { const id = [...S.tracks.keys()][0]; const t = S.tracks.get(id); t.liked = !t.liked; await DB.put('tracks', t); });
    rec('normal writes work again after the restore (lock lifted)', await page.evaluate(async () => { try { await DB.put('kv', 1, 'after-restore'); await DB.del('kv', 'after-restore'); return true; } catch (e) { return false; } }));
    rec('page errors during the whole happy path', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 2. cancellation at every stage: byte-identical, nothing written
  if (want(2)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    const base = await snap(page); await wrReset(page);
    const unchanged = async tag => { const w = await wr(page); rec(`${tag}: nothing written (no write tx/put/delete/localStorage) and all stores byte-identical`, w.tx.length === 0 && w.idbWrite === 0 && w.ls === 0 && sameSnap(await snap(page), base), J(w)); };
    // a. validation stage, Cancel button (gated so the stage is observable)
    await gate(page, 'crcOfBlob'); await openFile(page, MAIN); await waitText(page, 'Checking backup file'); await gateWait(page, 'crcOfBlob');
    rec('validation stage shows a progress dialog with a Cancel button, focused', await page.evaluate(() => document.activeElement.id === 'bkCancel'));
    await page.click('#bkCancel'); await gateOpen(page, 'crcOfBlob'); await page.waitForFunction(() => !document.querySelector('#dlg').open, null, { timeout: 15000 });
    rec('cancel during validation: toast says nothing changed', /cancelled.*not changed/i.test(await toastText(page)), await toastText(page)); await unchanged('cancel during validation (button)');
    // b. validation, Escape
    await gate(page, 'crcOfBlob'); await openFile(page, MAIN); await waitText(page, 'Checking backup file'); await gateWait(page, 'crcOfBlob');
    await page.keyboard.press('Escape'); await gateOpen(page, 'crcOfBlob'); await page.waitForFunction(() => !document.querySelector('#dlg').open, null, { timeout: 15000 }); await unchanged('cancel during validation (Escape)');
    rec('after cancelled validation the next restore starts normally (no stuck busy flag)', await page.evaluate(() => !S.restoreBusy && RS === null));
    // c. preview: button and Escape
    await toPreview(page, MAIN); await page.click('#dlg [data-bk="no"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open); await unchanged('cancel on preview (button)');
    await toPreview(page, MAIN); await page.keyboard.press('Escape'); await page.waitForFunction(() => !document.querySelector('#dlg').open); await unchanged('dismiss preview (Escape)');
    // d. confirmation: button, Escape, unchecked box
    await toConfirm(page, MAIN); await page.click('#dlg [data-bk="no"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open); await unchanged('cancel on confirmation (button)');
    await toConfirm(page, MAIN); await page.keyboard.press('Escape'); await page.waitForFunction(() => !document.querySelector('#dlg').open); await unchanged('dismiss confirmation (Escape)');
    await toConfirm(page, MAIN); await page.click('#dlg [data-bk="replace"]', { force: true, timeout: 800 }).catch(() => { }); await sleep(300);
    rec('confirmation with the box unticked cannot be confirmed (still open, still Replace disabled)', /Replace your library/.test(await dlgText(page)) && await page.evaluate(() => document.querySelector('#dlg [data-bk="replace"]').disabled));
    await page.keyboard.press('Escape'); await page.waitForFunction(() => !document.querySelector('#dlg').open); await unchanged('unticked confirmation then Escape');
    rec('after all cancellations: busy flags clear, lock off, app state untouched', await page.evaluate(() => !S.restoreBusy && !S.restoring && DB.lock === false && S.tracks.size === 3 && S.playlists.length === 1));
    // e. back up first, then cancel
    await toConfirm(page, MAIN); const dl0 = page.__dl; await page.click('#dlg [data-bk="backup"]');
    await page.waitForSelector('#dlg[open] [data-bk="ok"]', { timeout: 30000 }); await page.click('#dlg [data-bk="ok"]');
    await waitText(page, 'Replace your library'); rec('"Back up current library first" downloads a backup and returns to the confirmation', page.__dl === dl0 + 1);
    await page.click('#dlg [data-bk="no"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    { const w = await wr(page); const s2 = await snap(page, { skipKv: ['session', 'hist'] }), b2 = await snap(page, { skipKv: ['session', 'hist'] }); rec('after backup-first then cancel: songs, playlists, audio, secret/custom settings and localStorage unchanged (the backup itself re-saves the session)', J(s2.tracks) === J(base.tracks) && J(s2.playlists) === J(base.playlists) && J(s2.blobs) === J(base.blobs) && J(s2.ls) === J(base.ls) && J(s2.kv.filter(x => !['session', 'hist'].includes(x.key))) === J(base.kv.filter(x => !['session', 'hist'].includes(x.key))), J(w)); }
    // f. writing stage cannot be cancelled by Escape
    await wrReset(page); await toConfirm(page, MAIN); await gate(page, 'settleSession'); await replace(page); await gateWait(page, 'settleSession');
    await page.keyboard.press('Escape'); await sleep(250);
    rec('writing stage: dialog says it cannot be cancelled and Escape does not close it', await page.evaluate(() => { const d = document.querySelector('#dlg'); return d.open && /Restoring your library/.test(d.innerText) && /can’t be cancelled/.test(d.innerText); }));
    await gateOpen(page, 'settleSession'); const rt = await finish(page); rec('...and the restore then completes normally', /Library restored/.test(rt), rt);
    rec('cancellation scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 3. refused files via the UI: message, nothing written, library untouched
  if (want(3)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    const base = await snap(page); await wrReset(page);
    const junk = path.join(WORK, 'not-a-backup.txt'); fs.writeFileSync(junk, 'hello, this is not a zip file\n'.repeat(30));
    const empty = path.join(WORK, 'empty.zip'); fs.writeFileSync(empty, '');
    const refuse = [['c-flip-audio', /damaged|checksum/i], ['c-truncated-tail', /end record|cut short/i], ['m-version-2', /format 2.*newer Plainsong/i], ['k-secret', /credentials/i], ['k-secret-case', /credentials/i], ['c-deflate', /compressed/i], ['c-duplicate-name', /same entry name twice/i], ['c-name-traversal', /never contain/i], ['d-web-url-js', /songs have invalid fields/i], ['ls-unknown-key', /browser-storage key/i], ['i-complete-but-empty-audio', /complete, but some songs have no audio/i]];
    for (const [id, re] of refuse) {
      const t = await toPreview(page, B(id)); rec(`UI refuses ${id}: "can’t be restored", reason shown, "Nothing was changed", no Continue/Replace button`, /can’t be restored/.test(t) && re.test(t) && /Nothing was changed/.test(t) && !(await page.$('#dlg [data-bk="go"]')) && !(await page.$('#dlg [data-bk="replace"]')), t.slice(0, 300));
      await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    }
    for (const [tag, f] of [['plain text file', junk], ['empty file', empty]]) { const t = await toPreview(page, f); rec(`UI refuses a ${tag}`, /can’t be restored/.test(t) && /Nothing was changed/.test(t), t.slice(0, 200)); await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open); }
    const t = await toPreview(page, B('i-incomplete')); await page.screenshot({ path: path.join(SHOTS, 'p2b-incomplete-refusal.png') });
    rec('INCOMPLETE backup: refused with an explanation (file intact, partial copy would replace the library), problem song listed, no way to continue', /INCOMPLETE/.test(t) && /partial copy/.test(t) && /All byte values/.test(t) && !(await page.$('#dlg [data-bk="go"]')), t.slice(0, 400));
    await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    const w = await wr(page); rec(`after ${refuse.length + 3} refused files: zero writes of any kind and all stores + localStorage byte-identical`, w.tx.length === 0 && w.idbWrite === 0 && w.ls === 0 && sameSnap(await snap(page), base), J(w));
    // the refusal text of a hostile key renders escaped
    const tx = await toPreview(page, B('k-secret-xss')); rec('refusal naming an HTML-payload credential key shows it as text, creating no element', /secret:<img src=x/.test(tx) && (await page.evaluate(() => document.querySelectorAll('#dlg img').length)) === 0);
    await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    rec('refusal scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 4. injected failures: complete rollback, byte-identical
  if (want(4)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    await page.evaluate(() => settleSession()); await sleep(300);
    const base = await snap(page);
    const modes = [
      ['put-throw', 3, 'a put throws QuotaExceededError synchronously (3rd record)', /QuotaExceededError|injected quota/],
      ['put-throw-blob', 1, 'the first audio put throws QuotaExceededError (all songs/playlists already queued, clears applied)', /QuotaExceededError|injected quota/],
      ['abort-after', 10, 'transaction aborted from outside right after the 10th put (mid-restore)', /abort/i],
      ['async-error', 4, 'an asynchronous request error (ConstraintError) after the 4th put', /Constraint|already exists|key/i],
      ['tx-throws', 1, 'opening the read-write transaction throws', /InvalidStateError|injected/],
      ['verify-drop', 1, 'one song silently not written: in-transaction verification must catch it', /Verification failed: songs differ/],
      ['verify-truncate-blob', 1, 'every audio blob written 1 byte short: verification must catch it', /Verification failed: audio files differ/],
      ['verify-mutate-record', 1, 'songs written with a changed title: verification must catch it', /Verification failed: songs differ/],
      ['verify-mutate-kv', 1, 'saved session written altered: verification must catch it', /Verification failed: saved settings differ/]
    ];
    for (const [mode, nth, desc, re] of modes) {
      await wrReset(page); await toConfirm(page, MAIN); await inject(page, mode, nth);
      await replace(page); const t = await finish(page); const ij = await injected(page); await inject(page, null);
      const s = await snap(page);
      rec(`ROLLBACK [${mode}] ${desc}: failure reported as rolled back, says the library was verified unchanged`, /The restore failed and was rolled back/.test(t) && re.test(t) && /Checked afterwards: every store holds exactly/.test(t) && /Your library is unchanged/.test(t), t.slice(0, 500));
      rec(`ROLLBACK [${mode}]: all four stores, secret/custom keys, theme and localStorage BYTE-IDENTICAL to before`, sameSnap(s, base), 'kvdiff ' + J(s.kv.map((x, i) => { const b = base.kv[i]; if (!b || J(x) === J(b)) return null; const o = {}; for (const k of new Set([...Object.keys(x.value || {}), ...Object.keys(b.value || {})])) if (J((x.value || {})[k]) !== J((b.value || {})[k])) o[k] = [(b.value || {})[k], (x.value || {})[k]]; return { key: x.key, o }; }).filter(Boolean)).slice(0, 500) + ' tracks ' + (J(s.tracks) === J(base.tracks)) + ' pl ' + (J(s.playlists) === J(base.playlists)) + ' kv ' + (J(s.kv) === J(base.kv)) + ' blobs ' + (J(s.blobs) === J(base.blobs)) + ' ls ' + (J(s.ls) === J(base.ls)));
      const st = await page.evaluate(() => ({ lock: DB.lock, busy: [S.restoreBusy, S.restoring], tr: S.tracks.size, pl: S.playlists.length, theme: document.documentElement.dataset.theme }));
      rec(`ROLLBACK [${mode}]: app state untouched (3 songs, 1 playlist, theme light), lock released`, st.lock === false && !st.busy[0] && !st.busy[1] && st.tr === 3 && st.pl === 1 && st.theme === 'light', J(st));
      if (['put-throw', 'abort-after', 'async-error', 'verify-drop', 'verify-mutate-kv'].includes(mode)) rec(`ROLLBACK [${mode}] is non-vacuous: the restore really had queued writes (${ij.puts} put calls) before failing`, ij.puts >= (mode === 'verify-drop' || mode === 'verify-mutate-kv' ? 8 : nth), J(ij));
    }
    // the injection harness itself must not break a normal restore (control)
    await wrReset(page); await toConfirm(page, MAIN); await inject(page, 'none', 1); await replace(page); const tc = await finish(page);
    rec('control: the same injection proxy in pass-through mode lets the restore succeed (the failures above come from the injected faults)', /Library restored/.test(tc), tc.slice(0, 200));
    const sc = await snap(page); expectRestored('control restore after the failed attempts', sc, truthMain, base.kv.filter(x => x.key === 'secret:lb-token'));
    rec('rollback scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 5. other failure points: flush failure, unreadable library, re-check failure, rebuild failure, theme storage failure
  if (want(5)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    const base = await snap(page);
    // a. session flush refused by storage before anything is destroyed
    await toConfirm(page, MAIN); await page.evaluate(() => { window.__dp = DB.put; DB.put = () => Promise.reject(new Error('disk full')); });
    await replace(page); let t = await finish(page); await page.evaluate(() => { DB.put = window.__dp; });
    rec('flush failure: "Restore stopped before changing anything", library unchanged, lock released', /Restore stopped before changing anything/.test(t) && /disk full/.test(t) && /was not changed/.test(t) && sameSnap(await snap(page), base) && await page.evaluate(() => !DB.lock && !S.restoring), t.slice(0, 300));
    // b. current library cannot be fingerprinted
    await toConfirm(page, MAIN); await page.evaluate(() => { window.__fp = window.rsFingerprint; let n = 0; window.rsFingerprint = (...a) => { n++; return n >= 1 ? Promise.reject(new Error('read refused')) : window.__fp(...a); }; });
    await replace(page); t = await finish(page); await page.evaluate(() => { window.rsFingerprint = window.__fp; });
    rec('unreadable current library: restore stops before the commit; nothing changed', /Restore stopped before changing anything/.test(t) && /read refused/.test(t) && sameSnap(await snap(page), base), t.slice(0, 300));
    // c. rollback happened but the re-check itself fails: must NOT claim "unchanged"
    await toConfirm(page, MAIN); await page.evaluate(() => { window.__fp = window.rsFingerprint; let n = 0; window.rsFingerprint = (...a) => { n++; return n >= 2 ? Promise.reject(new Error('recheck refused')) : window.__fp(...a); }; });
    await inject(page, 'put-throw', 2); await replace(page); t = await finish(page); await inject(page, null); await page.evaluate(() => { window.rsFingerprint = window.__fp; });
    rec('re-check failure after a rollback: message does not claim the library is unchanged and tells the user to reload and look', /rolled back/.test(t) && /could not re-check/.test(t) && !/Your library is unchanged/.test(t) && /Reload the page/.test(t), t.slice(0, 400));
    rec('...(and the database really is unchanged, by independent snapshot)', sameSnap(await snap(page), base));
    // d. screen refresh fails after a successful commit: truthful
    await toConfirm(page, MAIN); await page.evaluate(() => { window.__hy = window.hydrate; window.hydrate = async () => { throw new Error('refresh refused'); }; });
    await replace(page); t = await finish(page); await page.evaluate(() => { window.hydrate = window.__hy; });
    const sd = await snap(page); expectRestored('commit succeeded, rebuild failed', sd, truthMain, base.kv.filter(x => x.key === 'secret:lb-token'));
    rec('rebuild failure: message says the backup WAS written completely and the page needs a reload; locks released', /Restored, but the screen needs a reload/.test(t) && /written to browser storage completely/.test(t) && await page.evaluate(() => !DB.lock && !S.restoring && !S.restoreBusy), t.slice(0, 300));
    await page.reload(); await page.waitForFunction(() => typeof DB !== 'undefined' && DB.ok && document.querySelector('#libStat').textContent.length > 0); await sleep(500); await page.evaluate(INJECT);
    rec('after reloading, the restored library is what the app shows (6 songs, dark theme)', await page.evaluate(() => S.tracks.size === 6 && document.documentElement.dataset.theme === 'dark'));
    // e. localStorage refuses the theme: the library restore must still succeed and the message must say so
    await page.evaluate(() => { localStorage.setItem('ps-theme', 'light'); document.documentElement.dataset.theme = 'light'; });
    await toConfirm(page, MAIN); await page.evaluate(() => { window.__si = Storage.prototype.setItem; Storage.prototype.setItem = function (k, v) { if (k === 'ps-theme') throw new DOMException('blocked', 'QuotaExceededError'); return window.__si.apply(this, arguments); }; });
    await replace(page); t = await finish(page); await page.evaluate(() => { Storage.prototype.setItem = window.__si; });
    const se = await snap(page); rec('theme storage failure: library fully restored, result says the theme could not be saved and applies for this visit only', /Library restored/.test(t) && /wouldn’t save the theme setting/.test(t) && J(se.tracks) === J(truthMain.tracks) && se.ls['ps-theme'] === 'light', t.slice(0, 400));
    // f. backup without a theme leaves the current theme alone
    await page.evaluate(() => { localStorage.setItem('ps-theme', 'light'); document.documentElement.dataset.theme = 'light'; });
    t = await fullRestore(page, MIN); const sf = await snap(page);
    rec('backup with no theme: current theme (light) left alone and the result says so', /no saved theme/.test(t) && sf.ls['ps-theme'] === 'light' && await page.evaluate(() => document.documentElement.dataset.theme === 'light'), t.slice(0, 300));
    expectRestored('minimal backup (no kv at all) replaces a 6-song library', sf, truthMin, base.kv.filter(x => x.key === 'secret:lb-token'));
    rec('minimal backup: the old session and history are gone with no kv entries left; app shows 1 song, nothing queued, defaults restored', await page.evaluate(() => S.tracks.size === 1 && S.queue.length === 0 && S.cur === null && S.vol === .8 && S.rate === 1 && document.querySelector('#barTitle').textContent === 'Nothing playing') && sf.kv.filter(x => !x.key.startsWith('secret:')).length === 0);
    rec('failure-point scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 6. unavailable storage
  if (want(6)) {
    const { ctx, page, errs } = await newPage(browser, { noIdb: true }); await boot(page, false);
    await wrReset(page); const t = await toPreview(page, MAIN); const w = await wr(page);
    rec('IndexedDB unavailable: restore says it isn’t available in this browser mode and nothing was changed; no file is even read', /Restore isn’t available/.test(t) && /Nothing was changed/.test(t) && !(await page.$('#dlg [data-bk="go"]')) && w.tx.length === 0 && w.ls === 0, t.slice(0, 250));
    await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    rec('IndexedDB unavailable: busy flags clear afterwards, app still usable', await page.evaluate(() => !S.restoreBusy && DB.lock === false));
    rec('no-storage page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 7. concurrency and stale-write protection
  if (want(7)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    const base = await snap(page);
    // a. import / backup attempted while a restore is open (preview)
    await toPreview(page, MAIN);
    await page.evaluate(() => importFiles([new File([new Uint8Array(100)], 'x.mp3', { type: 'audio/mpeg' })])); await sleep(150);
    rec('import attempted during a restore is refused with a message', /restore is in progress/i.test(await toastText(page)) && await page.evaluate(() => S.tracks.size === 3), await toastText(page));
    await page.click('#dlg [data-bk="no"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    // b. restore refused while a backup runs
    await gate(page, 'crcOfBlob'); await page.evaluate(() => { window.__bk = runBackup(); }); await gateWait(page, 'crcOfBlob');
    await page.evaluate(() => { document.querySelector('#restoreIn').dispatchEvent(new Event('change')); }); // no file: ignored
    await page.setInputFiles('#restoreIn', MAIN); await sleep(300);
    rec('restore chosen while a backup is running is refused with a toast and opens nothing', /backup is running/i.test(await toastText(page)) && !(await page.evaluate(() => /Restore preview/.test(document.querySelector('#dlg').innerText))), await toastText(page));
    await gateOpen(page, 'crcOfBlob'); await page.waitForSelector('#dlg[open] [data-bk="ok"]', { timeout: 30000 }); await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    // c. restore chosen while an import runs (real import held inside readTags)
    const gw = path.join(WORK, 'Gate Test.wav'); fs.copyFileSync(wavs[1], gw);
    await gate(page, 'readTags'); await page.setInputFiles('#fileIn', [gw]); await gateWait(page, 'readTags');
    await page.setInputFiles('#restoreIn', MAIN); await sleep(300);
    rec('restore chosen while an import is running is refused with a toast and opens nothing', /import to finish/i.test(await toastText(page)) && !(await page.evaluate(() => /Restore preview/.test(document.querySelector('#dlg').innerText))), await toastText(page));
    await gateOpen(page, 'readTags'); await sleep(1200);
    await page.evaluate(() => settleSession()); await sleep(1200); const base2 = await snap(page);
    // d. while the commit phase is locked: backup, import, direct writes and stale-object resurrection are all refused
    await toConfirm(page, MAIN);
    const oldTrack = await page.evaluate(() => JSON.parse(JSON.stringify([...S.tracks.values()][0])));
    await gate(page, 'rsFingerprint', 1); await replace(page); await gateWait(page, 'rsFingerprint');
    const during = await page.evaluate(async oldTrack => {
      const o = { flags: [S.restoring, DB.lock, S.restoreBusy] };
      const rej = async p => { try { await p; return false; } catch (e) { return true; } };
      o.putKvRejected = await rej(DB.put('kv', { late: 1 }, 'late-key'));
      o.staleTrackRejected = await rej(DB.put('tracks', oldTrack));
      o.delRejected = await rej(DB.del('blobs', oldTrack.id));
      o.dbPutSwallowed = await dbPut('tracks', oldTrack).then(() => 'resolved-quietly');
      saveSession(); saveHist();                   // debounced saves queued during the lock
      o.t0 = document.querySelector('#toast').textContent; await runBackup(); o.backupToast = document.querySelector('#toast').textContent;
      await importFiles([new File([new Uint8Array(10)], 'y.mp3', { type: 'audio/mpeg' })]); o.importToast = document.querySelector('#toast').textContent;
      o.readOk = !!(await DB.get('kv', 'session'));
      return o;
    }, oldTrack);
    rec('during the locked commit phase: restoring/lock/busy flags are all set', J(during.flags) === J([true, true, true]), J(during.flags));
    rec('during the lock: direct kv write, stale-song write and delete are all REJECTED (stale-write protection); reads still work', during.putKvRejected && during.staleTrackRejected && during.delRejected && during.readOk, J(during));
    rec('during the lock: a backup is refused ("A restore is writing") and an import is refused', /restore is writing/i.test(during.backupToast) && /restore is in progress/i.test(during.importToast), J([during.backupToast, during.importToast]));
    { const a = await snap(page, { skipKv: ['session', 'hist'] }), b = await snap(page, { skipKv: ['session', 'hist'] }); rec('during the lock, before the commit: songs, playlists, audio, other settings and localStorage are still exactly the old library (only the pre-lock session flush may differ)', J(a) === J(b) && J(a.tracks) === J(base2.tracks) && J(a.blobs) === J(base2.blobs) && J(a.ls) === J(base2.ls)); }
    await gateOpen(page, 'rsFingerprint'); const done = await finish(page); await sleep(1500);
    const sd = await snap(page); expectRestored('restore with writes attempted during the lock', sd, truthMain, base2.kv.filter(x => x.key === 'secret:lb-token'));
    rec('stale writes did not survive: no late-key, old song not resurrected, queued debounced saves did not overwrite the restored session', !sd.kv.some(x => x.key === 'late-key') && !sd.tracks.some(t => t.id === oldTrack.id) && J(sd.kv.find(x => x.key === 'session')) === J(truthMain.kv.find(x => x.key === 'session')));
    rec('after unlock, writes work again', await page.evaluate(async () => { try { await DB.put('kv', 1, 'z'); await DB.del('kv', 'z'); return !DB.lock; } catch (e) { return false; } }));
    // e. restore while a song is PLAYING with unsaved debounced state
    await page.evaluate(() => { const id = [...S.tracks.values()].find(t => t.kind === 'local').id; playList([id], 0); });
    await page.waitForFunction(() => aL.currentTime > .5 && !aL.paused, null, { timeout: 15000 });
    await page.evaluate(() => { saveSession(); saveHist(); S.vol = .33; applyVol(); saveSession(); window.__plays = 0; });
    const baseP = await snap(page, { skipKv: ['session', 'hist'] });
    t = await fullRestore(page, B('ok-rebuilt')); await sleep(2500);
    const sp = await snap(page); const tr2 = truthOf('rebuilt', B('ok-rebuilt'));
    rec('restore while a song is playing: playback stopped (both elements paused), no play event after the restore started, restored session/history NOT overwritten by pending saves or by the old playhead', await page.evaluate(() => aL.paused && aW.paused) && J(sp.kv.find(x => x.key === 'session')) === J(tr2.kv.find(x => x.key === 'session')) && J(sp.kv.find(x => x.key === 'hist')) === J(tr2.kv.find(x => x.key === 'hist')), t.slice(0, 200));
    expectRestored('restore while playing', sp, tr2, base2.kv.filter(x => x.key === 'secret:lb-token'));
    rec('restoring the same backup twice gives an identical database (deterministic replace)', await (async () => { await fullRestore(page, B('ok-rebuilt')); await sleep(800); return sameSnap(await snap(page), sp); })());
    rec('concurrency scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 8. hostile text is displayed escaped everywhere
  if (want(8)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page);
    const evil = path.join(WORK, '<img src=x onerror=window.__pwned=9>.zip'); fs.copyFileSync(B('ok-hostile-text'), evil);
    const pv = await toPreview(page, evil); await page.screenshot({ path: path.join(SHOTS, 'p2b-preview-hostile.png') });
    rec('hostile file name and manifest text are shown as literal text in the preview (no element created, nothing executed)', /<img src=x onerror=window\.__pwned=9>\.zip/.test(pv) && /<b>Evil<\/b>/.test(pv) && /onerror="window\.__pwned=5"/.test(pv) && (await page.evaluate(() => document.querySelectorAll('#dlg img, #dlg b, #dlg script').length)) === 0 && (await page.evaluate(() => window.__pwned)) === undefined, pv.slice(0, 300));
    await page.click('#dlg [data-bk="go"]'); await waitText(page, 'Replace your library'); await replace(page); const t = await finish(page);
    rec('hostile-text backup restored', /Library restored/.test(t), t.slice(0, 200));
    await page.evaluate(() => { go('albums', {}); }); await sleep(250);
    const views = [['home (recent plays)', () => go('home', {})], ['library songs', () => go('library', { tab: 'songs' })], ['library artists', () => go('library', { tab: 'artists' })], ['library albums', () => go('library', { tab: 'albums' })], ['album page', () => go('album', { key: albumKey([...S.tracks.values()][0]) })], ['artist page', () => go('artist', { key: artistKey([...S.tracks.values()][0]) })], ['playlist', () => go('playlist', { id: 'pl-1' })], ['search', () => { $('#q').value = 'img'; $('#searchForm').dispatchEvent(new Event('submit', { cancelable: true })); }], ['now playing queue', () => setTab('queue', true)], ['lyrics tab', () => setTab('lyrics', true)], ['sound tab', () => setTab('sound', true)]];
    for (const [name, fn] of views) { await page.evaluate(fn).catch(() => { }); await sleep(250); }
    const dom = await page.evaluate(() => ({ pwned: window.__pwned, imgs: [...document.querySelectorAll('img')].filter(i => /^x$/.test(i.getAttribute('src') || '')).length, scripts: document.querySelectorAll('script').length, svgs: document.querySelectorAll('svg[onload]').length, onerr: document.querySelectorAll('[onerror]').length, text: document.body.innerText.includes('<img src=x onerror="window.__pwned=1">') }));
    rec('across home/library/album/artist/playlist/search/now-playing/lyrics views: window.__pwned never set, no injected <img>/<svg onload>/[onerror], and the payload is visible as plain text', dom.pwned === undefined && dom.imgs === 0 && dom.svgs === 0 && dom.onerr === 0 && dom.scripts === 1 && dom.text, J(dom));
    rec('hostile-text scenario: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 9. keyboard-only operation
  if (want(9)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    await page.focus('.side-foot [data-act="restore"]'); await sleep(400);
    // ONE real Enter press, no retry. A missing chooser is a recorded failure (with evidence), never a crash and never a second press.
    const c9 = await chooserVia(page, () => page.keyboard.press('Enter')), fc = c9.fc;
    rec('keyboard: ONE Enter on the focused "Restore from backup…" button opens exactly one file chooser', !!fc && c9.extra === 1, J({ inputClicks: c9.inputClicks, choosers: c9.extra }));
    if (fc) await fc.setFiles(MAIN); else { console.log('NOTE: no chooser captured; continuing the dialog-keyboard checks with setInputFiles (the FAIL above stays)'); await openFile(page, MAIN); }
    await waitText(page, 'Restore preview');
    rec('keyboard: preview opens with focus on Cancel; Tab reaches Continue; Escape cancels', await page.evaluate(() => document.activeElement.dataset.bk === 'no'));
    await page.keyboard.press('Tab'); rec('keyboard: Tab moves to Continue…', await page.evaluate(() => document.activeElement.dataset.bk === 'go'));
    await page.keyboard.press('Enter'); await waitText(page, 'Replace your library');
    rec('keyboard: Enter on Continue… reaches the confirmation, focus on Cancel (safe default)', await page.evaluate(() => document.activeElement.dataset.bk === 'no'));
    await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Shift+Tab');
    const order = []; for (let i = 0; i < 6; i++) { order.push(await page.evaluate(() => document.activeElement.id || document.activeElement.dataset.bk || document.activeElement.tagName)); await page.keyboard.press('Tab'); }
    rec('keyboard: confirmation focus order reaches the checkbox, Cancel and Back-up-first, and skips the disabled Replace button', ['rsAck', 'no', 'backup'].every(x => order.includes(x)) && !order.includes('replace'), J(order));
    rec('keyboard: Replace is skipped by Tab order while disabled, and Space on the checkbox enables it', await (async () => { await page.focus('#rsAck'); await page.keyboard.press('Space'); return page.evaluate(() => document.querySelector('#rsAck').checked && !document.querySelector('#dlg [data-bk="replace"]').disabled); })());
    await page.focus('#dlg [data-bk="replace"]'); await page.keyboard.press('Enter'); const t = await finish(page);
    rec('keyboard-only restore completes', /Library restored/.test(t) && await page.evaluate(() => S.tracks.size === 6), t.slice(0, 200));
    rec('keyboard scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 10. mobile layout (390 x 844), real button path, light theme
  if (want(10)) {
    const { ctx, page, errs } = await newPage(browser, { viewport: { width: 390, height: 844 } }); await boot(page); await seedLib(page);
    rec('mobile: top-bar restore button is visible and at least 32x32', await page.evaluate(() => { const b = document.querySelector('.top [data-act="restore"]').getBoundingClientRect(); return b.width >= 32 && b.height >= 32 && b.right <= innerWidth && b.left >= 0; }));
    const c10 = await chooserVia(page, () => page.click('.top [data-act="restore"]'));
    rec('mobile: the top-bar Restore button opens exactly one file chooser', !!c10.fc && c10.extra === 1, J({ inputClicks: c10.inputClicks }));
    if (c10.fc) await c10.fc.setFiles(MAIN); else await openFile(page, MAIN); await waitText(page, 'Restore preview');
    const geo = async () => page.evaluate(() => { const d = document.querySelector('#dlg').getBoundingClientRect(); return { l: Math.round(d.left), r: Math.round(d.right), t: Math.round(d.top), b: Math.round(d.bottom), vw: innerWidth, vh: innerHeight, hs: document.documentElement.scrollWidth > innerWidth, dlgScroll: document.querySelector('#dlg').scrollWidth > document.querySelector('#dlg').clientWidth }; });
    let g = await geo(); await page.screenshot({ path: path.join(SHOTS, 'p2b-preview-mobile.png') });
    rec('mobile preview: dialog inside the viewport, no horizontal page scroll, no sideways overflow in the dialog', g.l >= 0 && g.r <= g.vw && !g.hs && !g.dlgScroll, J(g));
    rec('mobile preview: Continue/Cancel buttons reachable on screen (dialog scrolls if taller than the viewport)', await page.evaluate(() => { const d = document.querySelector('#dlg'); return d.scrollHeight <= d.clientHeight + 1 || getComputedStyle(d).overflowY !== 'visible'; }));
    await page.click('#dlg [data-bk="go"]'); await waitText(page, 'Replace your library'); g = await geo(); await page.screenshot({ path: path.join(SHOTS, 'p2b-confirm-mobile.png') });
    rec('mobile confirmation: inside the viewport, no horizontal scroll', g.l >= 0 && g.r <= g.vw && !g.hs && !g.dlgScroll, J(g));
    await page.tap('#rsAck').catch(async () => { await page.check('#rsAck'); });
    await page.evaluate(() => document.querySelector('#dlg [data-bk="replace"]').scrollIntoView()); await page.click('#dlg [data-bk="replace"]'); const t = await finish(page);
    rec('mobile: full restore completes and the library shows 6 songs', /Library restored/.test(t) && await page.evaluate(() => S.tracks.size === 6), t.slice(0, 200));
    await page.screenshot({ path: path.join(SHOTS, 'p2b-after-mobile.png') });
    rec('mobile: no horizontal scroll after the restore', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    rec('mobile scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 11. large audio entry (64 MiB) through the whole flow
  if (want(11)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    const t0 = Date.now(); const t = await fullRestore(page, B('ok-big')); const ms = Date.now() - t0;
    const s = await snap(page), tb = truthOf('big', B('ok-big'));
    rec(`64 MiB audio entry restored through preview, confirmation and verified commit in ${ms} ms`, /Library restored/.test(t), t.slice(0, 200));
    expectRestored('64 MiB archive', s, tb, [{ key: 'secret:lb-token', value: OLD.secret }]);
    rec('large-entry scenario: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // =================================================================== 12. the two static-review risks: (a) runBackup during validation/preview/confirmation, (b) the old sleep timer
  if (want(12)) {
    const { ctx, page, errs } = await newPage(browser); await boot(page); await seedLib(page);
    const base = await snap(page);
    // a backup of this library made by the app itself (real, playable WAV audio) - the sleep-timer scenarios need playable songs, MAIN's audio is synthetic bytes
    const OWN = path.join(WORK, 's12-own.zip');
    { const [dl] = await Promise.all([page.waitForEvent('download'), page.evaluate(() => { window.__bkp = runBackup(); })]); await dl.saveAs(OWN); await page.waitForSelector('#dlg[open] [data-bk="ok"]', { timeout: 30000 }); await page.click('#dlg [data-bk="ok"]'); await page.evaluate(() => window.__bkp); await page.waitForFunction(() => !document.querySelector('#dlg').open); }
    const tryBackup = async () => {   // never awaits the backup forever: if the guard is missing a REAL backup starts and would wait for its OK dialog
      const dl = page.__dl; await page.evaluate(() => { window.__bkp = runBackup(); }); await sleep(900);
      const out = { toast: await toastText(page), dl: page.__dl - dl, busy: await page.evaluate(() => !!S.backupBusy), rb: await page.evaluate(() => S.restoreBusy) };
      if (out.busy) { await page.click('#dlg [data-bk="ok"]', { timeout: 6000 }).catch(() => { }); await sleep(300); }
      return out;
    };

    // (a1) during VALIDATION (the file is being checked, nothing is on screen but the progress dialog)
    await gate(page, 'crcOfBlob'); await openFile(page, MAIN); await waitText(page, 'Checking backup file'); await gateWait(page, 'crcOfBlob');
    let r = await tryBackup();
    rec('(a) backup requested during VALIDATION: refused with "A restore is in progress", no download, no backup state left set', /restore is in progress/i.test(r.toast) && r.dl === 0 && !r.busy && r.rb === true, J(r));
    await gateOpen(page, 'crcOfBlob'); await waitText(page, 'Restore preview');

    // (a2) during PREVIEW
    r = await tryBackup();
    rec('(a) backup requested during the PREVIEW: refused, no download, no backup state left set', /restore is in progress/i.test(r.toast) && r.dl === 0 && !r.busy && r.rb === true, J(r));
    await page.click('#dlg [data-bk="go"]'); await waitText(page, 'Replace your library');

    // (a3) during CONFIRMATION
    r = await tryBackup();
    rec('(a) backup requested during the CONFIRMATION: refused, no download, no backup state left set', /restore is in progress/i.test(r.toast) && r.dl === 0 && !r.busy && r.rb === true, J(r));

    // (a4) the explicit exception: the dialog's own "Back up current library first" still works, and returns to the confirmation
    const dl0 = page.__dl; await page.click('#dlg [data-bk="backup"]'); await page.waitForSelector('#dlg[open] [data-bk="ok"]', { timeout: 30000 }); await page.click('#dlg [data-bk="ok"]'); await waitText(page, 'Replace your library'); await sleep(300);
    rec('(a) the dialog\'s own "Back up current library first" is the one intended exception: it downloads and returns to the confirmation', page.__dl === dl0 + 1 && !(await page.evaluate(() => !!S.backupBusy)));

    // cancel, then everything is back to normal: the flag is clear, a normal backup works again, library untouched
    await page.click('#dlg [data-bk="no"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    rec('(a) after cancelling: restoreBusy is cleared and the library is byte-identical', (await page.evaluate(() => !S.restoreBusy)) && sameSnap(await snap(page, { skipKv: ['session', 'hist'] }), { ...base, kv: base.kv.filter(x => !['session', 'hist'].includes(x.key)) }));
    { const d0 = page.__dl; await page.evaluate(() => { window.__bkp = runBackup(); }); await page.waitForSelector('#dlg[open] [data-bk="ok"]', { timeout: 30000 }); await page.click('#dlg [data-bk="ok"]'); await page.evaluate(() => window.__bkp); await page.waitForFunction(() => !document.querySelector('#dlg').open);
      rec('(a) after cancelling, a normal backup works again (one download) and clears its busy flag', page.__dl === d0 + 1 && !(await page.evaluate(() => !!S.backupBusy))); }

    // (a5) the lock window itself (restoring=true) keeps its own message
    await toConfirm(page, MAIN); await gate(page, 'rsFingerprint', 1); await replace(page); await gateWait(page, 'rsFingerprint');
    r = await tryBackup(); rec('(a) backup requested inside the locked write window: refused with "A restore is writing", no download', /restore is writing/i.test(r.toast) && r.dl === 0 && !r.busy, J(r));
    await gateOpen(page, 'rsFingerprint'); await finish(page);

    // (b1) a sleep timer with a deadline set BEFORE the restore must not stop restored playback later
    await page.evaluate(() => { S.sleep = { at: Date.now() + 14000, min: 1 }; });
    await fullRestore(page, OWN);
    rec('(b) restore clears the old timed sleep timer (S.sleep null) and starts no playback', await page.evaluate(() => S.sleep === null && A.paused));
    await page.evaluate(() => A.play()); await sleep(500);
    const playing0 = await page.evaluate(() => !A.paused); await sleep(16500);   // well past the OLD deadline (14 s) plus its 2.4 s fade
    const late = await page.evaluate(() => ({ paused: A.paused, vol: ((typeof G !== 'undefined' && G) ? G.gain.gain.value : A.volume), want: S.muted ? 0 : Math.pow(S.vol, 1.6), toast: document.querySelector('#toast').textContent }));
    rec('(b) restored playback started after the restore is still playing, at its normal volume, long after the old deadline (not stopped, not faded)', playing0 && !late.paused && Math.abs(late.vol - late.want) < 0.02 && !/good night/i.test(late.toast), J(late));

    // (b2) an "after this song" sleep timer set before the restore must not stop the restored session at the next song end
    await page.evaluate(() => { A.pause(); S.sleep = { end: true }; });
    await fullRestore(page, OWN);
    rec('(b) restore clears an "after this song" sleep timer', await page.evaluate(() => S.sleep === null));
    const e = await page.evaluate(async () => { const qi0 = S.qi; A.dispatchEvent(new Event('ended')); await new Promise(r => setTimeout(r, 600)); return { qi0, qi: S.qi, n: S.queue.length, toast: document.querySelector('#toast').textContent }; });
    rec('(b) the restored session, when a song ends, advances normally instead of "Sleep timer: playback stopped"', !/playback stopped/i.test(e.toast) && (e.n < 2 || e.qi !== e.qi0), J(e));
    await page.evaluate(() => { A.pause(); });

    // (b3) a fade-out ALREADY IN FLIGHT when the restore rebuilds the player is abandoned and the volume put back
    await page.evaluate(async () => { applyVol(); await A.play().catch(() => { }); S.sleep = { at: Date.now() - 1, min: 1 }; });
    await page.waitForFunction(() => S.sleep === null, null, { timeout: 5000 });   // the 1 s interval has started the fade
    await sleep(500);
    const fadeVol = await page.evaluate(() => ((typeof G !== 'undefined' && G) ? G.gain.gain.value : A.volume));
    await page.evaluate(() => rsRebuild()); await page.evaluate(async () => { try { await A.play(); } catch (e) { } });
    await sleep(3600);   // longer than the whole 2.4 s fade
    const fl = await page.evaluate(() => ({ paused: A.paused, vol: ((typeof G !== 'undefined' && G) ? G.gain.gain.value : A.volume), want: S.muted ? 0 : Math.pow(S.vol, 1.6), toast: document.querySelector('#toast').textContent }));
    rec('(b) in-flight fade-out was running (volume below normal) when the rebuild happened', fadeVol < (await page.evaluate(() => Math.pow(S.vol, 1.6))) - 0.001, String(fadeVol));
    rec('(b) after the rebuild the abandoned fade does not pause the player or leave the volume lowered, and says no "good night"', !fl.paused && Math.abs(fl.vol - fl.want) < 0.02 && !/good night/i.test(fl.toast), J(fl));
    rec('(a)(b) scenarios: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  await browser.close();
  const fail = results.filter(r => !r.ok);
  fs.writeFileSync(OUT, JSON.stringify({ total: results.length, failed: fail.length, results }, null, 1));
  console.log(`\nPHASE 2B: ${results.length - fail.length} / ${results.length} pass`);
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
