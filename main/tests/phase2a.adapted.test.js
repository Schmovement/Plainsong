// ADAPTED Phase 2A suite (NOT the original; the ORIGINAL is tests/original/p2a/, byte-identical to the p2a checkpoint). Differences: generator guard/fixes, pinned refusal reasons, hostile-text control, the obsolete "no restore UI" assertion replaced. See tests/README.md.
// Phase 2A tests: the READ-ONLY backup reader (readBackupZip). No restore UI exists yet.
// usage: node phase2a.adapted.test.js <fixtures-dir(wavs)> <work-dir> <results.json>
// Needs: python3 tests/make_bad_archives.adapted.py, tests/extract_expected.py, app served on http://localhost:8765
const { createRequire } = require('module');
const { chromium } = createRequire('/opt/npm-tools/package.json')('playwright');
const { spawnSync } = require('child_process');
const assert = require('assert');
const path = require('path');
const fs = require('fs');

const URL = process.env.PS_URL || 'http://localhost:8765/index.html'; const ORIGIN = new (require('url').URL)(URL).origin;
const [FX, WORK, OUT] = process.argv.slice(2);
const HERE = __dirname, FIX = path.join(HERE, 'fixtures');
const MAIN = path.join(FIX, 'p1-main-backup.zip'), MIN = path.join(FIX, 'p1-minimal-backup.zip');
const wavs = ['Artist A - Song One.wav', 'Artist B - Song Two.wav', 'Artist C - Song Three.wav'].map(f => path.join(FX, f));
fs.mkdirSync(WORK, { recursive: true });
const BAD = path.join(WORK, 'bad'); fs.rmSync(BAD, { recursive: true, force: true });


// every "shape" refusal must be for the SPECIFIC reason the case is aimed at (a refusal for any other reason would be vacuous)
const REASON = {
  'd-tracks-not-list': /tracks\.json must be a list/, 'd-track-not-object': /not an object/, 'd-track-no-id': /id must be a non-empty text/, 'd-track-id-int': /id must be a non-empty text/, 'd-track-id-empty': /id must be a non-empty text/,
  'd-track-kind': /kind must be/, 'd-track-title-int': /title must be text/, 'd-track-title-missing': /title must be text/, 'd-track-duration-str': /duration must be a non-negative number/, 'd-track-plays-neg': /plays must be a non-negative number/, 'd-track-liked-int': /liked must be true or false/,
  'd-track-cover-js': /cover must be/, 'd-track-cover-svg': /cover must be/, 'd-track-cover-file': /cover must be/, 'd-web-url-js': /a web song needs an http\(s\) url/, 'd-web-url-data': /a web song needs an http\(s\) url/, 'd-web-url-missing': /a web song needs an http\(s\) url/, 'd-web-link-js': /link must be empty or an http\(s\) address/,
  'd-track-proto': /forbidden key __proto__/, 'd-deep-nesting': /nested too deeply/, 'p-ids-not-list': /ids must be a list of song ids/, 'p-ids-nonstring': /ids must be a list of song ids/, 'p-name-int': /name must be text/,
  'k-not-list': /kv\.json must be a list/, 'k-no-value': /must be \{key, value\}/, 'k-extra-prop': /must be \{key, value\}/, 'k-key-int': /must be \{key, value\}/,
  's-queue-not-list': /queue must be a list of ids/, 's-queue-nonstring': /queue must be a list of ids/, 's-qi-float': /qi must be a whole number/, 's-vol-range': /vol must be between 0 and 1/, 's-rate-range': /rate must be between/, 's-eq-length': /eq must be 10 numbers/, 's-eq-str': /eq must be 10 numbers/, 's-repeat': /repeat must be 0, 1 or 2/, 's-tab': /npTab is not a known tab/, 's-web-url': /a web song needs an http\(s\) url/, 's-not-object': /kv\/session: not an object/,
  'h-not-list': /kv\/hist: must be a list/, 'h-entry': /needs a text id and a time/, 'h-snap-url': /a web song needs an http\(s\) url/, 'ls-not-object': /localstorage\.json must be an object/
};

const results = [];
const rec = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail: String(detail).slice(0, 700) }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (!ok && detail ? '  :: ' + String(detail).slice(0, 500) : '')); };
const J = v => JSON.stringify(v);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const py = (args) => { const r = spawnSync('python3', ['-I', ...args], { encoding: 'utf-8', maxBuffer: 1 << 28 }); if (r.status !== 0) throw new Error(args[0] + ' failed: ' + r.stderr + r.stdout); return r.stdout; };

// every write primitive the page could use is counted; reads are not
const SPY = () => {
  window.__w = { tx: [], idbWrite: 0, ls: 0, open: 0 };
  const T = IDBDatabase.prototype.transaction;
  IDBDatabase.prototype.transaction = function (s, m) { if (m && m !== 'readonly') window.__w.tx.push(String(s) + ':' + m); return T.apply(this, arguments); };
  for (const [C, ms] of [[IDBObjectStore, ['put', 'add', 'delete', 'clear']], [IDBCursor, ['update', 'delete']]])
    for (const m of ms) { const f = C.prototype[m]; C.prototype[m] = function () { window.__w.idbWrite++; return f.apply(this, arguments); }; }
  for (const m of ['setItem', 'removeItem', 'clear']) { const f = Storage.prototype[m]; Storage.prototype[m] = function () { window.__w.ls++; return f.apply(this, arguments); }; }
  for (const m of ['open', 'deleteDatabase']) { const f = IDBFactory.prototype[m]; IDBFactory.prototype[m] = function () { window.__w.open++; return f.apply(this, arguments); }; }
};
async function newPage(browser, { noIdb } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, acceptDownloads: true });
  await ctx.addInitScript(SPY);
  if (noIdb) await ctx.addInitScript(() => { Object.defineProperty(window, 'indexedDB', { value: undefined, configurable: true }); });
  const page = await ctx.newPage(); const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|net::/.test(m.text())) errs.push('console: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith(ORIGIN) ? r.continue() : r.abort());
  return { ctx, page, errs };
}
async function boot(page, needDb = true) {
  await page.goto(URL);
  await page.waitForFunction(nd => document.querySelector('#libStat') && document.querySelector('#libStat').textContent.length > 0 && (!nd || (typeof DB !== 'undefined' && DB.ok)), needDb);
  await sleep(300);
  await page.evaluate(() => { const i = document.createElement('input'); i.type = 'file'; i.id = '__t'; i.hidden = true; document.body.appendChild(i); });
}
const writes = page => page.evaluate(() => JSON.parse(JSON.stringify(window.__w)));
const resetW = page => page.evaluate(() => { window.__w = { tx: [], idbWrite: 0, ls: 0, open: 0 }; });

// parse a file in the page exactly as a user-chosen File would arrive (disk-backed, via an <input type=file>)
async function parse(page, file, opts = {}, full = false) {
  await page.setInputFiles('#__t', file);
  return page.evaluate(async ({ opts, full }) => {
    const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
    const f = document.getElementById('__t').files[0];
    const o = { ...opts }; if (opts.cancelAfterGate) { o.ctl = window.__ctl = { cancel: false }; delete o.cancelAfterGate; }
    const t0 = performance.now();
    try {
      const k = await readBackupZip(f, o);
      const out = { ok: true, ms: Math.round(performance.now() - t0), complete: k.complete, summary: k.summary, warnings: k.warnings, nblobs: k.blobs.length };
      if (full) {
        out.man = k.man; out.tracks = k.tracks; out.playlists = k.playlists; out.kv = k.kv; out.ls = k.ls; out.orphans = k.orphans; out.blobs = [];
        for (const b of k.blobs) out.blobs.push({ key: b.key, type: b.type, size: b.size, sha256: hex(await crypto.subtle.digest('SHA-256', await b.blob.arrayBuffer())), blobType: b.blob.type, blobSize: b.blob.size, isBlob: b.blob instanceof Blob });
      }
      return out;
    } catch (e) {
      return { ok: false, code: e.code, cancel: typeof BackupCancel !== 'undefined' && e instanceof BackupCancel, title: e.bk && e.bk.title, msg: e.message, lines: e.bk && e.bk.lines, hasPkg: !!e.pkg, pkgComplete: e.pkg && e.pkg.complete, pkgProblems: e.pkg && e.pkg.man.problems.length, ms: Math.round(performance.now() - t0), other: e.bk ? undefined : String(e && e.stack || e) };
    }
  }, { opts, full });
}

// independent DB + storage snapshot (own code, not the app's)
const snap = page => page.evaluate(async () => {
  const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  const tx = DB.db.transaction(['tracks', 'playlists', 'blobs', 'kv'], 'readonly'); const o = { tracks: [], playlists: [], kv: [], bl: [] };
  const cur = (n, f) => { const r = tx.objectStore(n).openCursor(); r.onsuccess = () => { const c = r.result; if (c) { f(c); c.continue(); } }; };
  cur('tracks', c => o.tracks.push(c.value)); cur('playlists', c => o.playlists.push(c.value)); cur('kv', c => o.kv.push({ k: c.key, v: c.value })); cur('blobs', c => o.bl.push({ k: c.key, b: c.value }));
  await new Promise(r => { tx.oncomplete = r; });
  const blobs = []; for (const x of o.bl) blobs.push({ k: x.k, size: x.b.size, type: x.b.type, sha: hex(await crypto.subtle.digest('SHA-256', await x.b.arrayBuffer())) });
  const ls = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); ls[k] = localStorage.getItem(k); }
  return JSON.stringify({ tracks: o.tracks, playlists: o.playlists, kv: o.kv, blobs, ls });
});

async function compareFull(tag, file, r) {
  const ef = path.join(WORK, tag + '.truth.json'); py([path.join(HERE, 'extract_expected.py'), file, ef]);
  const X = JSON.parse(fs.readFileSync(ef, 'utf-8'));
  rec(`${tag}: parsed OK`, r.ok, r.msg || r.other || '');
  if (!r.ok) return;
  const same = (a, b) => { try { assert.deepStrictEqual(a, b); return JSON.stringify(a) === JSON.stringify(b); } catch (e) { return false; } };
  rec(`${tag}: manifest identical to independent extraction`, same(r.man, X.manifest));
  rec(`${tag}: tracks identical (every field, order)`, same(r.tracks, X.tracks), `${r.tracks.length} vs ${X.tracks.length}`);
  rec(`${tag}: playlists identical (incl. ids order)`, same(r.playlists, X.playlists));
  rec(`${tag}: kv identical (session, hist, custom keys, floats)`, same(r.kv, X.kv));
  rec(`${tag}: localStorage block identical`, same(r.ls, X.ls));
  rec(`${tag}: ${X.blobs.length} audio blobs: key, MIME, size, SHA-256 identical and in order`, same(r.blobs.map(b => ({ key: b.key, type: b.type, size: b.size, sha256: b.sha256 })), X.blobs));
  rec(`${tag}: returned Blobs report the exact MIME and size`, r.blobs.every((b, i) => b.isBlob && b.blobType === X.blobs[i].type && b.blobSize === X.blobs[i].size));
  const man = X.manifest, loc = X.tracks.filter(t => t.kind === 'local').length;
  rec(`${tag}: summary matches manifest counts`, r.summary.local === loc && r.summary.web === X.tracks.length - loc && r.summary.playlists === man.counts.playlists && r.summary.audioFiles === man.counts.blobs && r.summary.audioBytes === man.audioBytes && r.summary.complete === true, JSON.stringify(r.summary));
}

(async () => {
  const browser = await chromium.launch();
  // ===== 1. both bundled p1 archives: byte-exact vs independent extraction, and zero storage writes =====
  {
    const { ctx, page, errs } = await newPage(browser); await boot(page);
    rec('app boots with the restore entry points present (2B) and the reader is a global function', await page.evaluate(() => !!document.querySelector('[data-act="restore"]') && !!document.querySelector('#restoreIn') && typeof readBackupZip === 'function'));
    await resetW(page); const before = await snap(page);
    for (const [tag, f] of [['main-fixture', MAIN], ['minimal-fixture', MIN]]) {
      const r = await parse(page, f, {}, true); await compareFull(tag, f, r);
      if (tag === 'main-fixture') {
        rec('main fixture: orphan blob with unicode key "orphan/ü key 🎧" is reported as an orphan and kept', r.ok && r.orphans.length === 1 && r.orphans[0] === 'orphan/ü key 🎧' && r.summary.orphans === 1);
        rec('main fixture: secret key stayed out (kv holds only custom:pref, hist, session)', r.ok && JSON.stringify(r.kv.map(x => x.key)) === JSON.stringify(['custom:pref', 'hist', 'session']));
        rec('main fixture: 1 MiB all-bytes blob (custom MIME) and 3 MiB blob (empty MIME) keep their exact MIME', r.ok && r.blobs.find(b => b.key === 'bin-1').type === 'application/x-test' && r.blobs.find(b => b.key === 'bin-2').type === '', r.ok ? JSON.stringify(r.blobs.filter(b => b.key.startsWith('bin-')).map(b => [b.key, b.type])) : '');
      }
      rec(`${tag}: parsing took ${r.ms} ms`, r.ok);
    }
    const w = await writes(page);
    rec('fixtures parse: zero IndexedDB write transactions, zero put/add/delete/clear, zero localStorage writes, no database open/delete', w.tx.length === 0 && w.idbWrite === 0 && w.ls === 0 && w.open === 0, JSON.stringify(w));
    rec('fixtures parse: database and localStorage byte-identical afterwards', (await snap(page)) === before);
    rec('fixtures parse: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // ===== 2. hostile / corrupt / unsupported / incomplete / credential archives on a POPULATED library =====
  py([path.join(HERE, 'make_bad_archives.adapted.py'), MAIN, BAD, '--big']);
  const cases = JSON.parse(fs.readFileSync(path.join(BAD, 'cases.json'), 'utf-8'));
  {
    const { ctx, page, errs } = await newPage(browser); await boot(page);
    await page.setInputFiles('#fileIn', wavs); await page.waitForFunction(() => S.tracks.size >= 3, null, { timeout: 30000 });
    await page.click('#themeBtn'); await sleep(2800); // theme write + debounced session save flushed before the baseline
    await resetW(page);
    // non-vacuity: the spies really see a write
    await page.evaluate(() => dbPut('kv', { x: 1 }, 'probe-key')); await sleep(200);
    let w = await writes(page);
    rec('spy control: a real kv write is counted (spies are not vacuous)', w.tx.includes('kv:readwrite') && w.idbWrite >= 1, JSON.stringify(w));
    await page.evaluate(() => dbDel('kv', 'probe-key')); await sleep(200);
    await page.evaluate(() => localStorage.setItem('probe', '1')); w = await writes(page);
    rec('spy control: a real localStorage write is counted', w.ls >= 1);
    await page.evaluate(() => localStorage.removeItem('probe')); await sleep(300);
    await resetW(page); const before = await snap(page);
    rec('baseline library for the no-write proof has 3 songs, 3 audio blobs and a saved theme', (() => { const b = JSON.parse(before); return b.tracks.length === 3 && b.blobs.length === 3 && !!b.ls['ps-theme']; })());

    const expectOf = c => Array.isArray(c.expect) ? c.expect : [c.expect];
    let nRej = 0, nOk = 0;
    for (const c of cases) {
      const f = path.join(BAD, c.id + '.zip');
      const r = await parse(page, f, c.limits ? { limits: c.limits } : {}, c.expect === 'ok');
      if (c.expect === 'ok') {
        nOk++;
        let pass = r.ok, why = r.ok ? '' : `${r.code}: ${r.msg}`;
        if (pass && c.id !== 'ok-big') { const ef = path.join(WORK, 'case-' + c.id + '.json'); py([path.join(HERE, 'extract_expected.py'), f, ef]); const X = JSON.parse(fs.readFileSync(ef, 'utf-8'));
          try { assert.deepStrictEqual(r.tracks, X.tracks); assert.deepStrictEqual(r.playlists, X.playlists); assert.deepStrictEqual(r.kv, X.kv); assert.deepStrictEqual(r.ls, X.ls); assert.deepStrictEqual(r.blobs.map(b => ({ key: b.key, type: b.type, size: b.size, sha256: b.sha256 })), X.blobs); assert.strictEqual(JSON.stringify(r.tracks), JSON.stringify(X.tracks)); } catch (e) { pass = false; why = 'accepted but output differs from independent extraction: ' + String(e.message).slice(0, 200); } }
        rec(`ACCEPT ${c.id}: ${c.desc}${c.id === 'ok-big' ? ` (${r.ms} ms)` : ''}`, pass, why);
      } else {
        nRej++;
        const pinned = REASON[c.id], why = [r.msg, ...(r.lines || [])].join(' | '), reasonOk = c.expect === 'shape' ? (!!pinned && pinned.test(why)) : (!pinned || pinned.test(why));
        const good = !r.ok && !r.cancel && expectOf(c).includes(r.code) && r.title === 'This backup can’t be restored' && /Nothing was changed\.$/.test(r.msg) && !r.other && reasonOk;
        rec(`REJECT ${c.id} [${expectOf(c).join('|')}]: ${c.desc}`, good, r.ok ? 'ACCEPTED a hostile archive' : `got code=${r.code} msg=${(r.msg || '').slice(0, 160)} lines=${J(r.lines || []).slice(0, 200)} ${r.other || ''}`);
      }
    }
    rec(`all ${nRej} rejection cases and ${nOk} acceptance controls ran`, nRej >= 130 && nOk >= 6, `${nRej} / ${nOk}`);

    // incomplete archives: refused by default with the facts attached; validated and returned only on explicit request
    const inc = path.join(BAD, 'i-incomplete.zip');
    const r1 = await parse(page, inc, {}); rec('incomplete: refused by default (code incomplete) and the error carries the validated package + problem list', !r1.ok && r1.code === 'incomplete' && r1.hasPkg && r1.pkgComplete === false && r1.pkgProblems === 1 && /INCOMPLETE/.test(r1.msg) && (r1.lines || []).some(l => /All byte values/.test(l)), JSON.stringify(r1).slice(0, 300));
    const r2 = await parse(page, inc, { allowIncomplete: true }, true); rec('incomplete: with allowIncomplete the same file is returned with complete:false and the missing song listed', r2.ok && r2.complete === false && r2.summary.problems === 1 && r2.blobs.find(b => b.key === 'bin-1').size === 0);

    // nothing was ever written, across every case above
    w = await writes(page);
    rec(`no-write proof over ${cases.length} archives: zero write transactions, zero put/add/delete/clear/update, zero localStorage writes, no open/delete of any database`, w.tx.length === 0 && w.idbWrite === 0 && w.ls === 0 && w.open === 0, JSON.stringify(w));
    rec('no-write proof: all four IndexedDB stores (records, keys, order, blob bytes+MIME) and localStorage are byte-identical to before', (await snap(page)) === before);
    rec('existing library still works: 3 songs still listed in the app state', await page.evaluate(() => S.tracks.size === 3 && document.querySelector('#libStat').textContent.includes('3 songs')));

    // cancel mid-validation: gate the first CRC pass, set cancel, release
    await page.evaluate(() => { window.__orig = window.crcOfBlob; window.__entered = false; window.__gate = new Promise(r => { window.__open = r; }); window.crcOfBlob = async (...a) => { window.__entered = true; await window.__gate; return window.__orig(...a); }; });
    await page.setInputFiles('#__t', MAIN);
    const pr = page.evaluate(async () => { window.__ctl = { cancel: false }; try { await readBackupZip(document.getElementById('__t').files[0], { ctl: window.__ctl }); return 'resolved'; } catch (e) { return e instanceof BackupCancel ? 'cancelled' : 'other:' + e.message; } });
    await page.waitForFunction(() => window.__entered, null, { timeout: 15000 });
    await page.evaluate(() => { window.__ctl.cancel = true; window.__open(); window.crcOfBlob = window.__orig; });
    rec('cancel during validation: reader stops with BackupCancel (nothing returned)', (await pr) === 'cancelled');
    w = await writes(page); rec('cancel during validation: still zero writes and storage unchanged', w.tx.length === 0 && w.idbWrite === 0 && w.ls === 0 && (await snap(page)) === before);
    // a clean parse still works afterwards (no stuck state)
    const r3 = await parse(page, MIN, {}); rec('reader is reusable after a cancel', r3.ok);
    rec('hostile archives: no page errors, no unhandled rejections', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // ===== 3. archives produced by THIS build's exporter (populated library, then incomplete) are readable =====
  {
    const { ctx, page, errs } = await newPage(browser); await boot(page);
    await page.setInputFiles('#fileIn', wavs); await page.waitForFunction(() => S.tracks.size >= 3, null, { timeout: 30000 }); await sleep(500);
    await page.evaluate(() => { S.playlists.push({ id: 'pl-x', name: 'Mix <b>x</b>', ids: [...S.tracks.keys()].reverse(), created: 5 }); return savePlaylists(); });
    const ex = async (name) => { const p = page.waitForEvent('download', { timeout: 60000 }); await page.click('.top [data-act="backup"]'); const dl = await p; const to = path.join(WORK, name); await dl.saveAs(to); await page.waitForSelector('#dlg[open] [data-bk="ok"]'); await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open); return to; };
    const live = await ex('live-export.zip');
    await compareFull('live-export', live, await parse(page, live, {}, true));
    // make one song lose its audio, then export incomplete
    const lost = await page.evaluate(async () => { const id = [...S.tracks.keys()][0]; await DB.del('blobs', id); return id; });
    const p = page.waitForEvent('download', { timeout: 60000 }); await page.click('.top [data-act="backup"]');
    await page.waitForSelector('#dlg[open] [data-bk="yes"]'); await page.click('#dlg [data-bk="yes"]'); const dl = await p; const incf = path.join(WORK, 'live-incomplete.zip'); await dl.saveAs(incf);
    await page.waitForSelector('#dlg[open] [data-bk="ok"]'); await page.click('#dlg [data-bk="ok"]'); await page.waitForFunction(() => !document.querySelector('#dlg').open);
    const a = await parse(page, incf, {}); rec('live INCOMPLETE export (written by this build) is refused as incomplete, file intact', !a.ok && a.code === 'incomplete' && a.hasPkg && a.pkgProblems === 1, JSON.stringify(a).slice(0, 250));
    const b = await parse(page, incf, { allowIncomplete: true }, true); rec('live INCOMPLETE export with allowIncomplete: accepted, complete:false, missing song accounted for', b.ok && b.complete === false && b.summary.problems === 1);
    if (b.ok) { const ef = path.join(WORK, 'live-incomplete.truth.json'); py([path.join(HERE, 'extract_expected.py'), incf, ef]); const X = JSON.parse(fs.readFileSync(ef, 'utf-8')); let same = false; try { assert.deepStrictEqual(b.tracks, X.tracks); assert.deepStrictEqual(b.blobs.map(q => ({ key: q.key, type: q.type, size: q.size, sha256: q.sha256 })), X.blobs); same = true; } catch (e) { } rec('live INCOMPLETE export: parsed records and audio identical to independent extraction', same); }
    rec('live exports: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // ===== 4. reader works with no IndexedDB at all (it must not depend on the database) =====
  {
    const { ctx, page, errs } = await newPage(browser, { noIdb: true }); await boot(page, false);
    const r = await parse(page, MAIN, {}, false); const w = await writes(page);
    rec('IndexedDB unavailable: reader still validates the archive and performs no storage writes', r.ok && w.tx.length === 0 && w.idbWrite === 0, JSON.stringify(w) + (r.msg || ''));
    const bad = await parse(page, path.join(BAD, 'c-flip-audio.zip'), {}); rec('IndexedDB unavailable: corrupt archive still rejected with a code', !bad.ok && bad.code === 'crc');
    await ctx.close();
  }

  // ===== 5. untrusted text is escaped when shown; limits table; error text =====
  {
    const { ctx, page, errs } = await newPage(browser); await boot(page);
    const r = await parse(page, path.join(BAD, 'k-secret-xss.zip'), {});
    const html = await page.evaluate(l => bkLines(l), r.lines || []);
    rec('credential key named like an HTML payload: refused, and the offending name renders escaped (no live <img>)', !r.ok && r.code === 'secret' && (r.lines || []).some(l => l.includes('<img')) && !/<img/i.test(html) && /&lt;img/.test(html), html.slice(0, 200));
    await page.evaluate(h => { const d = document.createElement('div'); d.id = '__x'; d.innerHTML = h; document.body.appendChild(d); }, html);
    rec('rendered refusal text creates no element from archive text', await page.evaluate(() => document.querySelectorAll('#__x img').length === 0));
    rec('limits in force are the documented ones', await page.evaluate(() => RESTORE_LIMITS.maxBytes === 2147483648 && RESTORE_LIMITS.maxEntries === 60000 && RESTORE_LIMITS.maxJson === 268435456));
    rec('page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  await browser.close();
  const fail = results.filter(r => !r.ok);
  fs.writeFileSync(OUT, JSON.stringify({ total: results.length, failed: fail.length, results }, null, 1));
  console.log(`\nPHASE 2A: ${results.length - fail.length} / ${results.length} pass`);
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
