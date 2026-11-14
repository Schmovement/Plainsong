// Phase 1 (backup EXPORT) tests. Runs the real index.html in headless Chrome and verifies every produced archive
// with tests/verify_backup.py (independent Python implementation + `unzip -t`).
// usage: node phase1.test.js <fixtures-dir> <work-dir> <results.json>
const { createRequire } = require('module');
const { chromium } = createRequire('/opt/npm-tools/package.json')('playwright');
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const URL = 'http://localhost:8765/index.html';
const [FX, WORK, OUT] = process.argv.slice(2);
const HERE = __dirname;
const VERIFY = path.join(HERE, 'verify_backup.py');
const wavs = ['Artist A - Song One.wav', 'Artist B - Song Two.wav', 'Artist C - Song Three.wav'].map(f => path.join(FX, f));
fs.mkdirSync(WORK, { recursive: true });

const results = [];
const rec = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail: String(detail).slice(0, 600) }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail && !ok ? '  :: ' + String(detail).slice(0, 400) : '')); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function newPage(browser, { viewport, noIdb } = {}) {
  const ctx = await browser.newContext({ viewport: viewport || { width: 1280, height: 800 }, acceptDownloads: true });
  if (noIdb) await ctx.addInitScript(() => { Object.defineProperty(window, 'indexedDB', { value: undefined, configurable: true }); });
  const page = await ctx.newPage(); const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|net::/.test(m.text())) errs.push('console: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith('http://localhost:8765') ? r.continue() : r.abort());
  page.__dl = 0; page.on('download', () => { page.__dl++; });
  return { ctx, page, errs };
}
async function boot(page, needDb = true) {
  await page.goto(URL);
  await page.waitForFunction(nd => document.querySelector('#libStat') && document.querySelector('#libStat').textContent.length > 0 && (!nd || (typeof DB !== 'undefined' && DB.ok)), needDb);
  await sleep(250);
}
const importWavs = async (page, files) => { const n = files.length; await page.setInputFiles('#fileIn', files); await page.waitForFunction(k => S.tracks.size >= k, n, { timeout: 30000 }); await sleep(400); };
const TOP = '.top [data-act="backup"]', SIDE = '.side-foot [data-act="backup"]';
const dlgText = page => page.evaluate(() => { const d = document.querySelector('#dlg'); return d && d.open ? d.innerText : ''; });
const waitDlg = (page, re, ms = 20000) => page.waitForFunction(r => { const d = document.querySelector('#dlg'); return d && d.open && new RegExp(r).test(d.innerText); }, re, { timeout: ms });
async function exportOk(page, sel, saveTo) {
  const p = page.waitForEvent('download', { timeout: 60000 });
  await page.click(sel);
  const dl = await p; await dl.saveAs(saveTo);
  await page.waitForSelector('#dlg[open] [data-bk="ok"]', { timeout: 20000 });
  const text = await dlgText(page); await page.click('#dlg [data-bk="ok"]');
  await page.waitForFunction(() => !document.querySelector('#dlg').open);
  return { name: dl.suggestedFilename(), text };
}
async function expectNoDownload(page, ms = 1800) { const n0 = page.__dl; await sleep(ms); return page.__dl === n0; }

// Independent capture of the DB state (does not use the app's backup code).
function capture(page, forbidden) {
  return page.evaluate(async forbidden => {
    const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
    const tx = DB.db.transaction(['tracks', 'playlists', 'blobs', 'kv'], 'readonly');
    const o = { tracks: [], playlists: [], kv: [], blobsRaw: [] };
    const ga = (n, k) => { const r = tx.objectStore(n).getAll(); r.onsuccess = () => { o[k] = r.result; }; };
    const cur = (n, f) => { const r = tx.objectStore(n).openCursor(); r.onsuccess = () => { const c = r.result; if (c) { f(c); c.continue(); } }; };
    ga('tracks', 'tracks'); ga('playlists', 'playlists'); cur('kv', c => o.kv.push({ key: c.key, value: c.value })); cur('blobs', c => o.blobsRaw.push({ key: c.key, blob: c.value }));
    await new Promise(res => { tx.oncomplete = res; });
    const blobs = [];
    for (const x of o.blobsRaw) blobs.push({ key: x.key, size: x.blob.size, type: x.blob.type, sha256: hex(await crypto.subtle.digest('SHA-256', await x.blob.arrayBuffer())) });
    const norm = v => JSON.parse(JSON.stringify(v));
    const th = localStorage.getItem('ps-theme');
    return { tracks: norm(o.tracks), playlists: norm(o.playlists), kv: norm(o.kv.filter(x => !x.key.startsWith('secret:'))), excludedKv: o.kv.filter(x => x.key.startsWith('secret:')).map(x => x.key), ls: th === 'light' || th === 'dark' ? { 'ps-theme': th } : {}, blobs, forbidden: forbidden || [], expectBinary: false };
  }, forbidden);
}
function verify(tag, zip, expected, flags = []) {
  const ef = path.join(WORK, tag + '.expected.json'); fs.writeFileSync(ef, JSON.stringify(expected));
  const r = spawnSync('python3', ['-I', VERIFY, zip, ef, ...flags], { encoding: 'utf-8', maxBuffer: 1 << 26 });
  let n = 0;
  for (const line of (r.stdout || '').split('\n')) { const m = line.match(/^(PASS|FAIL) (.*)$/); if (m) { n++; rec(`${tag} verifier: ${m[2].split('  :: ')[0]}`, m[1] === 'PASS', m[2].split('  :: ')[1] || ''); } }
  if (!n || r.status === null) rec(`${tag} verifier ran`, false, (r.stderr || '') + (r.stdout || ''));
  return r.status === 0;
}
const extract = (zip, entry) => JSON.parse(spawnSync('python3', ['-I', VERIFY, '--extract', zip, entry], { encoding: 'utf-8', maxBuffer: 1 << 26 }).stdout);
const installGate = page => page.evaluate(() => { window.__orig = window.crcOfBlob; window.__entered = false; window.__gate = new Promise(r => { window.__open = r; }); window.crcOfBlob = async (...a) => { window.__entered = true; await window.__gate; return window.__orig(...a); }; });
const openGate = page => page.evaluate(() => { window.__open(); window.crcOfBlob = window.__orig; });

async function seedMain(page) {
  await page.evaluate(async () => {
    const ids = [...S.tracks.keys()], sleep = ms => new Promise(r => setTimeout(r, ms));
    const c = document.createElement('canvas'); c.width = c.height = 24; const g = c.getContext('2d'); g.fillStyle = '#c33'; g.fillRect(0, 0, 24, 24);
    const t0 = S.tracks.get(ids[0]); Object.assign(t0, { cover: c.toDataURL('image/jpeg', .8), lyrics: 'Line one\nLínea dos ✓ 日本語', lrc: '[00:01.00]Line one\n[00:03.50]Línea dos ✓', lyricsFrom: 'lrclib', last: 1730000000000, plays: 4, liked: true }); await DB.put('tracks', t0);
    const mkBin = (id, bytes, type, n) => { const t = { id, kind: 'local', key: `${id}|${bytes.length}|1`, title: n, artist: 'Test Artist ✓', album: 'Binary', track: 1, duration: 1, cover: '', lyrics: '', size: bytes.length, added: 5, plays: 3, liked: false }; return [t, new Blob([bytes], { type })]; };
    const all = new Uint8Array(1 << 20); for (let i = 0; i < all.length; i++) all[i] = i & 255;
    const rnd = new Uint8Array(3 << 20); for (let o = 0; o < rnd.length; o += 65536) crypto.getRandomValues(rnd.subarray(o, o + 65536));
    for (const [t, b] of [mkBin('bin-1', all, 'application/x-test', 'All byte values'), mkBin('bin-2', rnd, '', 'Random bytes, empty MIME')]) { await DB.put('blobs', b, t.id); await DB.put('tracks', t); S.tracks.set(t.id, t); }
    await DB.put('blobs', new Blob([new Uint8Array([0, 255, 1, 254])], { type: 'audio/ogg' }), 'orphan/ü key 🎧');
    const w = { id: 'audius:TEST1', kind: 'web', src: 'audius', srcId: 'TEST1', title: 'Web Song ✓', artist: 'Web Artist', album: 'Rock', duration: 200, cover: 'https://example.invalid/c.jpg', url: 'https://example.invalid/stream', link: 'https://audius.co/x', added: 0, plays: 0, liked: false };
    reg(w); saveWeb(w); toggleLike(w.id);
    const q = { id: 'audius:QUEUE1', kind: 'web', src: 'audius', srcId: 'QUEUE1', title: 'Queued only', artist: 'Q', album: 'Q', duration: 100, cover: '', url: 'https://example.invalid/q', link: '', added: 0, plays: 0, liked: false }; reg(q);
    await sleep(300);
    const pls = [{ id: 'pl-1', name: 'Mix ü 🎧', ids: [ids[0], 'audius:TEST1', ids[2], 'bin-1'], created: 1000 }, { id: 'pl-2', name: 'Empty', ids: [], created: 2000 }];
    for (const p of pls) { S.playlists.push(p); await DB.put('playlists', p); }
    await DB.put('kv', { sk: 'SECRET-SESSION-KEY-7d41', user: 'bob' }, 'secret:lastfm');
    await DB.put('kv', { a: 1, b: [1, 2, { c: null }], s: 'ü', f: 0.1 + 0.2 }, 'custom:pref');
    S.hist.unshift({ id: 'audius:HIST1', t: 1730000001000, snap: strip({ ...w, id: 'audius:HIST1', title: 'History-only web song' }) }, { id: ids[1], t: 1730000002000, snap: undefined }); saveHist();
    localStorage.setItem('ps-theme', 'dark'); localStorage.setItem('ps-lastfm-sk', 'TOKEN-LS-5b2e'); localStorage.setItem('unrelated', 'UNRELATED-VALUE-9f3a');
    playList([ids[0], 'audius:TEST1', ids[1]], 0); enqueue('audius:QUEUE1', false);
  });
  await page.waitForFunction(() => !aL.paused && aL.currentTime > .3, null, { timeout: 15000 });
  await page.evaluate(() => { setRate(1.25); A.pause(); A.currentTime = 3; });
  await sleep(300);
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
  const FORBID = ['SECRET-SESSION-KEY-7d41', 'TOKEN-LS-5b2e', 'UNRELATED-VALUE-9f3a'];

  // ================= S1 main: non-empty library, binary fixtures, all four stores =================
  let m = await newPage(browser), page = m.page, ids;
  try {
    await boot(page); await importWavs(page, wavs); await seedMain(page);
    ids = await page.evaluate(() => [...S.tracks.keys()].filter(k => !k.startsWith('bin-') && !k.startsWith('audius:')));
    const before = await capture(page, FORBID);
    rec('S1 fixture sanity: 3 imported + 2 binary + 1 web track, 2 playlists, orphan blob, secret kv', before.tracks.length === 6 && before.playlists.length === 2 && before.blobs.length === 6 && before.excludedKv.length === 1, `tracks=${before.tracks.length} blobs=${before.blobs.length}`);
    const z1 = path.join(WORK, 'main.zip');
    rec('S1 both Back up buttons exist with accessible names', await page.evaluate(() => [...document.querySelectorAll('[data-act="backup"]')].length === 2 && document.querySelector('.top [data-act="backup"]').getAttribute('aria-label') === 'Back up library'));
    const r1 = await exportOk(page, SIDE, z1);
    rec('S1 download filename is plainsong-backup-YYYYMMDD-HHMMSS.zip', /^plainsong-backup-\d{8}-\d{6}\.zip$/.test(r1.name), r1.name);
    rec('S1 success dialog states restore is not built yet and shows counts', /Backup downloaded/.test(r1.text) && /isn’t built yet/.test(r1.text) && /6 songs, 2 playlists/.test(r1.text), r1.text.replace(/\n/g, ' '));
    const after = await capture(page, FORBID); after.expectBinary = true;
    verify('S1', z1, after);
    rec('S1 originals preserved: tracks and every audio blob (SHA-256) unchanged by exporting', JSON.stringify(before.tracks) === JSON.stringify(after.tracks) && JSON.stringify(before.blobs) === JSON.stringify(after.blobs));
    const man = extract(z1, 'manifest.json');
    rec('S1 manifest: 6 tracks, 6 blobs (incl. orphan), 2 playlists, ps-theme only', man.counts.tracks === 6 && man.counts.blobs === 6 && man.counts.playlists === 2 && man.counts.localStorage === 1 && man.excluded.kv[0] === 'secret:lastfm', JSON.stringify(man.counts));
    rec('S1 manifest warns about the orphan audio blob', man.warnings.some(w => /no library entry/.test(w)), JSON.stringify(man.warnings));
    const kv = extract(z1, 'data/kv.json'), sess = kv.find(x => x.key === 'session').value, hist = kv.find(x => x.key === 'hist').value;
    rec('S1 session captured: queue incl. unsaved web track snapshot, rate 1.25, qi 0', sess.rate === 1.25 && sess.queue.length === 4 && sess.webs.length === 1 && sess.webs[0].id === 'audius:QUEUE1' && sess.qi === 0, JSON.stringify({ rate: sess.rate, q: sess.queue.length, webs: sess.webs.length }));
    rec('S1 history captured incl. web snapshot; undefined snap dropped', hist.length === 2 && hist[0].snap.title === 'History-only web song' && !('snap' in hist[1]));
    const tr = extract(z1, 'data/tracks.json'), t0 = tr.find(t => t.id === ids[0]);
    rec('S1 artwork data URL, lyrics (plain+LRC, unicode), likes, plays preserved in tracks.json', /^data:image\/jpeg;base64,/.test(t0.cover) && t0.lyrics.includes('日本語') && t0.lrc.includes('[00:03.50]') && t0.liked === true && t0.plays === 4);
    rec('S1 app state unaffected: speed 1.25, no A-B, busy flag cleared, nothing playing started', await page.evaluate(() => S.rate === 1.25 && S.ab.a === null && !S.backupBusy && aL.paused));
    fs.copyFileSync(z1, path.join(WORK, 'p1-main-backup.zip')); fs.writeFileSync(path.join(WORK, 'p1-main-backup.expected.json'), JSON.stringify(after));
    await page.screenshot({ path: path.join(WORK, 'p1-ui-desktop.png') });

    // ================= S2 settle: pending debounced saves must be in the archive =================
    await page.evaluate(id => { A.currentTime = 7.3; setRate(1.75); S.vol = .33; applyVol(); saveSession(); S.hist.unshift({ id, t: 123456789, snap: undefined }); saveHist(); }, ids[2]);
    rec('S2 precondition: session and history saves are pending (not yet in DB)', await page.evaluate(() => saveSession.pending() && saveHist.pending()));
    const z2 = path.join(WORK, 'settle.zip'); await exportOk(page, TOP, z2);
    const kv2 = extract(z2, 'data/kv.json'), s2 = kv2.find(x => x.key === 'session').value, h2 = kv2.find(x => x.key === 'hist').value;
    // (the seek past the midpoint also makes the baseline app log a real play at the front of history; both must be present)
    rec('S2 settle: archive holds the latest speed, volume, playhead and the pending history entry', s2.rate === 1.75 && s2.vol === .33 && Math.abs(s2.time - 7.3) < .05 && h2.some(h => h.id === ids[2] && h.t === 123456789) && h2.length === 4, JSON.stringify({ r: s2.rate, v: s2.vol, t: s2.time, n: h2.length }));
    rec('S2 pending timers were consumed, nothing left to overwrite later', await page.evaluate(() => !saveSession.pending() && !saveHist.pending()));

    // ================= S3 snapshot isolation: writes racing the snapshot must not leak in =================
    const victim = ids[1];
    const pre = await capture(page, ['LATE-PLAYLIST-NAME', 'late-kv-VALUE', 'MUTATED-AFTER']);
    await page.evaluate(([v, other]) => {
      const db = DB.db, orig = db.transaction.bind(db); window.__inj = 0; window.__injDone = false;
      db.transaction = function (stores, mode, ...rest) {
        const tx = orig(stores, mode, ...rest);
        if (mode === 'readonly' && Array.isArray(stores) && stores.length === 4 && !window.__inj) {
          window.__inj = 1; const w = orig(['tracks', 'playlists', 'blobs', 'kv'], 'readwrite');
          w.objectStore('tracks').delete(v); w.objectStore('blobs').delete(v);
          w.objectStore('playlists').put({ id: 'late-pl', name: 'LATE-PLAYLIST-NAME', ids: [], created: 9 });
          w.objectStore('kv').put({ v: 'late-kv-VALUE' }, 'late-kv');
          w.objectStore('tracks').put({ ...S.tracks.get(other), title: 'MUTATED-AFTER' });
          w.oncomplete = () => { window.__injDone = true; };
        }
        return tx;
      };
    }, [victim, ids[0]]);
    const z3 = path.join(WORK, 'isolation.zip'); await exportOk(page, TOP, z3);
    await page.waitForFunction(() => window.__injDone);
    const live = await page.evaluate(async v => ({ gone: (await DB.get('tracks', v)) === undefined && (await DB.get('blobs', v)) === undefined, late: !!(await DB.get('kv', 'late-kv')) }), victim);
    rec('S3 isolation precondition: the racing writes really committed afterwards (test is not vacuous)', live.gone && live.late, JSON.stringify(live));
    verify('S3', z3, pre, ['--ignore-kv', 'session']);
    const tr3 = extract(z3, 'data/tracks.json');
    rec('S3 snapshot is internally consistent: deleted track AND its audio both still present, old title kept', tr3.some(t => t.id === victim) && extract(z3, 'manifest.json').blobs.length === pre.blobs.length && !tr3.some(t => t.title === 'MUTATED-AFTER'));
    await page.evaluate(() => { delete DB.db.transaction; });
    rec('S1-S3 no uncaught JS errors', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception S1-S3', false, e.stack || e.message); }
  await m.ctx.close();

  // ================= S4 missing local audio blob =================
  m = await newPage(browser); page = m.page;
  try {
    await boot(page); await importWavs(page, wavs.slice(0, 2));
    const [id1, id2, title1] = await page.evaluate(() => { const a = [...S.tracks.values()]; return [a[0].id, a[1].id, a[0].title]; });
    await page.evaluate(id => DB.del('blobs', id), id1);
    await page.click(TOP); await waitDlg(page, 'fully backed up');
    const txt = await dlgText(page);
    rec('S4 missing blob: dialog names the song and the reason and offers Cancel / Export incomplete', txt.includes(title1) && /audio missing/.test(txt) && /INCOMPLETE/.test(txt) && !!(await page.$('#dlg [data-bk="no"]')) && !!(await page.$('#dlg [data-bk="yes"]')), txt.replace(/\n/g, ' '));
    await page.screenshot({ path: path.join(WORK, 'p1-ui-problem.png') });
    await page.click('#dlg [data-bk="no"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    rec('S4 choosing Cancel produces no file and says so', await expectNoDownload(page) && /Backup cancelled/.test(await page.textContent('#toast')) && await page.evaluate(() => !S.backupBusy));
    const z4 = path.join(WORK, 'incomplete.zip'); await page.click(TOP); await waitDlg(page, 'fully backed up');
    const p = page.waitForEvent('download'); await page.click('#dlg [data-bk="yes"]'); const dl = await p; await dl.saveAs(z4);
    rec('S4 incomplete export is named INCOMPLETE', /^plainsong-backup-INCOMPLETE-\d{8}-\d{6}\.zip$/.test(dl.suggestedFilename()), dl.suggestedFilename());
    await page.waitForSelector('#dlg[open] [data-bk="ok"]'); const t4 = await dlgText(page); await page.click('#dlg [data-bk="ok"]');
    rec('S4 final dialog says Incomplete and that 1 song had no audio', /Incomplete backup downloaded/.test(t4) && /INCOMPLETE: 1 song/.test(t4), t4.replace(/\n/g, ' '));
    const e4 = await capture(page, []); e4.problemIds = [id1]; verify('S4', z4, e4, ['--incomplete']);
    rec('S4 the surviving song is still fully included', extract(z4, 'manifest.json').blobs.length === 1 && extract(z4, 'manifest.json').blobs[0].key === id2);
    rec('S4 no JS errors', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception S4', false, e.stack || e.message); }
  await m.ctx.close();

  // ================= S5 limits =================
  m = await newPage(browser); page = m.page;
  try {
    await boot(page); await importWavs(page, wavs.slice(0, 2));
    const cases = [['audio larger than the limit (aborts the snapshot early)', () => { BACKUP_LIMITS.maxBytes = 1000; }, /too big for one backup file/], ['audio fits but audio+metadata does not', () => { BACKUP_LIMITS.maxBytes = 1058500; }, /too big for one backup file/], ['too many entries', () => { BACKUP_LIMITS.maxEntries = 6; }, /Too many songs/]];
    for (const [label, setter, re] of cases) {
      await page.evaluate(setter); const n0 = page.__dl; await page.click(TOP); await waitDlg(page, 'OK');
      const t = await dlgText(page);
      rec(`S5 limit: ${label} -> clear error, no file`, re.test(t) && /Nothing was written/.test(t) && page.__dl === n0, t.replace(/\n/g, ' '));
      if (label.startsWith('audio larger')) await page.screenshot({ path: path.join(WORK, 'p1-ui-toobig.png') });
      await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
      await page.evaluate(() => { BACKUP_LIMITS.maxBytes = 2 * 1024 ** 3; BACKUP_LIMITS.maxEntries = 60000; });
    }
    rec('S5 library untouched after refused exports', await page.evaluate(async () => (await DB.all('tracks')).length === 2 && (await DB.all('blobs')).length === 2));
    const z5 = path.join(WORK, 'afterlimit.zip'); await exportOk(page, TOP, z5); verify('S5', z5, await capture(page, []));
    rec('S5 no JS errors', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception S5', false, e.stack || e.message); }
  await m.ctx.close();

  // ================= S6 IndexedDB unavailable: in-memory-only library =================
  m = await newPage(browser, { noIdb: true }); page = m.page;
  try {
    await boot(page, false); await importWavs(page, wavs.slice(0, 1));
    rec('S6 precondition: IndexedDB unavailable and the song lives only in memory', await page.evaluate(() => DB.ok === false && S.mem.size === 1));
    await page.click(TOP); await waitDlg(page, 'OK'); const t = await dlgText(page);
    rec('S6 in-memory-only library: refuses with a clear explanation, no file', /available in this browser mode/.test(t) && /memory/.test(t) && /No backup file was created/.test(t) && page.__dl === 0, t.replace(/\n/g, ' '));
    await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    rec('S6 app still usable afterwards', await page.evaluate(() => !S.backupBusy && S.tracks.size === 1));
    rec('S6 no uncaught JS errors', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception S6', false, e.stack || e.message); }
  await m.ctx.close();

  // ================= S7 empty library, then minimal library =================
  m = await newPage(browser); page = m.page;
  try {
    await boot(page);
    await page.click(SIDE); await waitDlg(page, 'OK'); const t = await dlgText(page);
    rec('S7 empty library: says there is nothing to back up, no file', /Nothing to back up yet/.test(t) && page.__dl === 0, t.replace(/\n/g, ' '));
    await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    rec('S7 empty export attempt wrote nothing to the database', await page.evaluate(async () => (await DB.get('kv', 'session')) === undefined && (await DB.all('kv')).length === 0));
    await importWavs(page, wavs.slice(0, 1));
    await page.evaluate(() => { localStorage.setItem('ps-theme', 'neon'); localStorage.setItem('ps-lastfm-sk', 'TOKEN-LS-5b2e'); });
    const z7 = path.join(WORK, 'minimal.zip'); await exportOk(page, TOP, z7);
    const e7 = await capture(page, ['TOKEN-LS-5b2e']); verify('S7', z7, e7);
    const m7 = extract(z7, 'manifest.json');
    rec('S7 minimal library: empty playlists/kv/prefs files are valid, bad ps-theme value skipped with a warning', extract(z7, 'data/kv.json').length === 0 && extract(z7, 'data/playlists.json').length === 0 && Object.keys(extract(z7, 'data/localstorage.json')).length === 0 && m7.warnings.some(w => /ps-theme/.test(w)), JSON.stringify(m7.warnings));
    rec('S7 exporting without playback did not create a session record', await page.evaluate(async () => (await DB.get('kv', 'session')) === undefined));
    fs.copyFileSync(z7, path.join(WORK, 'p1-minimal-backup.zip'));
    rec('S7 no JS errors', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception S7', false, e.stack || e.message); }
  await m.ctx.close();

  // ================= S9 data that cannot be represented exactly =================
  m = await newPage(browser); page = m.page;
  try {
    await boot(page); await importWavs(page, wavs.slice(0, 1));
    await page.evaluate(() => DB.put('tracks', { id: 'bad-1', kind: 'web', src: 'audius', title: 'Bad', artist: 'x', album: 'x', duration: NaN, when: new Date(), added: 0, plays: 0, liked: false }));
    await page.click(TOP); await waitDlg(page, 'OK'); const t = await dlgText(page);
    rec('S9 non-JSON-safe values (NaN, Date): refused, offending paths listed, no file', /written exactly/.test(t) && /tracks\/bad-1\.duration/.test(t) && /tracks\/bad-1\.when/.test(t) && page.__dl === 0, t.replace(/\n/g, ' '));
    await page.click('#dlg [data-bk="ok"]');
    rec('S9 no JS errors', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception S9', false, e.stack || e.message); }
  await m.ctx.close();

  // ================= S8 cancel paths (gate holds the export mid-run) + large binary =================
  m = await newPage(browser); page = m.page;
  try {
    await boot(page); await importWavs(page, wavs.slice(0, 1));
    const cnt = () => page.evaluate(async () => [(await DB.all('tracks')).length, (await DB.all('blobs')).length]);
    const c0 = await cnt();
    await installGate(page); await page.click(TOP); await page.waitForFunction(() => window.__entered);
    rec('S8 progress dialog is open with a Cancel button and progressbar semantics', await page.evaluate(() => { const d = document.querySelector('#dlg'); return d.open && !!d.querySelector('#bkCancel') && d.querySelector('[role="progressbar"]').getAttribute('aria-valuenow') !== null; }));
    await page.screenshot({ path: path.join(WORK, 'p1-ui-progress.png') });
    // guards while a backup is running
    await page.evaluate(() => { runBackup(); }); const files = wavs.slice(1, 2);
    await page.evaluate(() => { importFiles([new File([new Uint8Array(10)], 'x.wav', { type: 'audio/wav' })]); });
    rec('S8 second backup click is ignored; an import is refused with a message while a backup runs', /backup is running/.test(await page.textContent('#toast')) && await page.evaluate(() => S.tracks.size === 1));
    await page.click('#bkCancel'); await openGate(page);
    await page.waitForFunction(() => !document.querySelector('#dlg').open && !S.backupBusy);
    rec('S8 Cancel button: no file, message shown, library untouched', await expectNoDownload(page, 1200) && /Backup cancelled/.test(await page.textContent('#toast')) && JSON.stringify(await cnt()) === JSON.stringify(c0));
    await installGate(page); await page.click(TOP); await page.waitForFunction(() => window.__entered);
    await page.keyboard.press('Escape'); await openGate(page);
    await page.waitForFunction(() => !document.querySelector('#dlg').open && !S.backupBusy);
    rec('S8 Escape key cancels too: no file, state reset', await expectNoDownload(page, 1200) && JSON.stringify(await cnt()) === JSON.stringify(c0));
    // import guard: backup refused while an import is running
    await page.evaluate(() => { S.importBusy = true; }); await page.click(TOP);
    rec('S8 backup refused while an import is running (toast, no dialog)', /import/.test(await page.textContent('#toast')) && !(await page.evaluate(() => document.querySelector('#dlg').open)));
    await page.evaluate(() => { S.importBusy = false; });
    // large binary entry (64 MiB patterned data), real export path with the 4 MiB chunk size
    await page.evaluate(async () => {
      const b = new Uint8Array(64 << 20); for (let i = 0; i < b.length; i++) b[i] = (i * 31 + (i >> 8)) & 255;
      const t = { id: 'big-1', kind: 'local', key: 'big|1|1', title: 'Large binary 64 MiB', artist: 'T', album: 'T', track: 0, duration: 1, cover: '', lyrics: '', size: b.length, added: 9, plays: 0, liked: false };
      await DB.put('blobs', new Blob([b], { type: 'audio/x-large' }), t.id); await DB.put('tracks', t); S.tracks.set(t.id, t);
    });
    const z8 = path.join(WORK, 'large.zip'); const t0 = Date.now(); await exportOk(page, TOP, z8); const ms = Date.now() - t0;
    verify('S8', z8, await capture(page, []));
    rec('S8 large 64 MiB entry exported byte-exactly (timing recorded)', true, `${ms} ms`);
    rec('S8 no JS errors', m.errs.length === 0, m.errs.join(' | '));
  } catch (e) { rec('HARNESS exception S8', false, e.stack || e.message); }
  await m.ctx.close();

  // ================= S11 keyboard + mobile layout of the new UI =================
  m = await newPage(browser); page = m.page;
  try {
    await boot(page); await importWavs(page, wavs.slice(0, 1)); await installGate(page);
    await page.focus(TOP); await page.keyboard.press('Enter'); await page.waitForFunction(() => window.__entered);
    rec('S11 keyboard: focusing the Back up button and pressing Enter starts the export; Escape cancels', await page.evaluate(() => document.querySelector('#dlg').open));
    await page.keyboard.press('Escape'); await openGate(page); await page.waitForFunction(() => !document.querySelector('#dlg').open && !S.backupBusy);
    const ctxM = await newPage(browser, { viewport: { width: 390, height: 844 } }); const pm = ctxM.page;
    await boot(pm); await importWavs(pm, wavs.slice(0, 1));
    const lay = await pm.evaluate(() => { const r = s => document.querySelector(s).getBoundingClientRect(), b = r('.top [data-act="backup"]'); return { sw: document.scrollingElement.scrollWidth, iw: innerWidth, btn: b.width > 0 && b.right <= innerWidth && b.left >= 0, side: getComputedStyle(document.querySelector('.side-foot')).display }; });
    rec('S11 mobile 390px: top-bar Back up button visible, no horizontal overflow, (sidebar copy hidden by existing layout)', lay.btn && lay.sw <= lay.iw && lay.side === 'none', JSON.stringify(lay));
    await installGate(pm); await pm.click(TOP); await pm.waitForFunction(() => window.__entered);
    const dr = await pm.evaluate(() => { const r = document.querySelector('#dlg').getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, iw: innerWidth, ih: innerHeight }; });
    rec('S11 mobile: progress dialog fits the viewport', dr.l >= 0 && dr.r <= dr.iw && dr.t >= 0 && dr.b <= dr.ih, JSON.stringify(dr));
    await pm.screenshot({ path: path.join(WORK, 'p1-ui-mobile.png') });
    await pm.click('#bkCancel'); await openGate(pm); await pm.waitForFunction(() => !document.querySelector('#dlg').open);
    // light theme readability of the dialog (screenshot for review)
    await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; }); await installGate(page); await page.click(TOP); await page.waitForFunction(() => window.__entered);
    await page.screenshot({ path: path.join(WORK, 'p1-ui-progress-light.png') }); await page.keyboard.press('Escape'); await openGate(page);
    rec('S11 no JS errors', m.errs.length === 0 && ctxM.errs.length === 0, m.errs.concat(ctxM.errs).join(' | '));
    await ctxM.ctx.close();
  } catch (e) { rec('HARNESS exception S11', false, e.stack || e.message); }
  await m.ctx.close();

  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
  const fails = results.filter(r => !r.ok);
  console.log(`\nTOTAL ${results.length}  PASS ${results.length - fails.length}  FAIL ${fails.length}`);
  process.exit(0);
})();
