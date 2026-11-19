#!/usr/bin/env python3
"""Phase 3B mutation checks: writes one mutated copy of the app per safeguard (index.html with ONE safeguard removed or reverted to the earlier unsafe design, style.css unchanged) and mutants.json.
  python3 -I mutants_3b.py <project-dir> <out-dir>
tests/run_mutants_3b.sh serves each mutant and runs the scenario that must notice; a mutant counts as DETECTED only if that scenario FAILS on the intended check
(a mutant the suite does not notice is reported as such, never hidden)."""
import sys, os, json, shutil
proj, out = sys.argv[1], sys.argv[2]
src = open(os.path.join(proj, 'index.html'), encoding='utf-8').read()
M = []
def mut(mid, desc, scn, needle, *pairs):
    s = src
    for old, new in pairs:
        assert s.count(old) == 1, (mid, s.count(old), old[:70])
        s = s.replace(old, new)
    assert s != src, mid
    d = os.path.join(out, mid); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(s)
    shutil.copy(os.path.join(proj, 'style.css'), os.path.join(d, 'style.css'))
    M.append({'id': mid, 'desc': desc, 'scenario': scn, 'needle': needle})

# ---- write coordination (review issue 1)
mut('C1-cover-mutate-then-put', 'saveCover goes back to the earlier design: mutate the shared record first, then put it (a failed write leaves the uncommitted cover in memory and in other writers\' snapshots)', 9,
    'S9 reject: the failed cover save left NO trace',
    ("          const clone = structuredClone(t); apply(clone);   // only the cover fields differ from the shared record; the write is durable BEFORE the shared record is touched\n", "          apply(t); const clone = t;\n"))
mut('C2-meta-mutate-then-put', 'saveMeta goes back to the earlier design: mutate the shared record first, then put it', 9,
    'S9 meta: the failed 3A save left NO trace',
    ("          const clone = structuredClone(t); apply(clone);\n", "          apply(t); const clone = t;\n"))
mut('C3-no-per-track-queue', 'the per-track write queue is removed: every writer runs immediately', 9,
    'S9 release: RAW DATABASE equals',
    ("      const p = prev ? prev.then(task) : task();", "      const p = task();"))
mut('C4-snapshot-at-enqueue', 'queued whole-record writers (likes, plays...) take their snapshot when queued instead of when they run', 9,
    'S9 release: RAW DATABASE equals',
    ("    const dbPutTrack = t => trackWrite(t.id, async () => { if (S.tracks.get(t.id) !== t) return; await DB.put('tracks', t); }).catch(() => { });",
     "    const dbPutTrack = t => { const snap = structuredClone(t); return trackWrite(t.id, async () => { if (S.tracks.get(t.id) !== t) return; await DB.put('tracks', snap); }).catch(() => { }); };"))
mut('C5-stale-clone-applied', 'after a committed cover save the whole stale clone is copied over the shared record (newer likes/plays are overwritten)', 9,
    "S9 release: the newer writers' data is preserved",
    ("          if (S.tracks.get(tid) !== t || epoch !== S.epoch) return { ok: false, msg: 'This song is no longer in your library. Nothing was saved.' };\n        }\n        apply(t);\n        return { ok: true, memoryOnly: !DB.ok };",
     "          if (S.tracks.get(tid) !== t || epoch !== S.epoch) return { ok: false, msg: 'This song is no longer in your library. Nothing was saved.' };\n          Object.assign(t, clone);\n        }\n        apply(t);\n        return { ok: true, memoryOnly: !DB.ok };"))
mut('C6-no-runtime-basis-check', 'a queued cover save no longer re-checks, when it runs, that the cover it was based on is still the stored one', 9,
    'S9e release: the first save committed',
    ("if (epoch !== S.epoch || coverCur(t) !== base) return { ok: false, msg: 'This song changed while the editor was open. Close it and open it again. Nothing was saved.' };\n        if (DB.ok) {\n          const clone = structuredClone(t); apply(clone);   //", "if (false) return {};\n        if (DB.ok) {\n          const clone = structuredClone(t); apply(clone);   //"))
# ---- pending-save semantics (review issue 2)
mut('E1-cancel-not-blocked', 'Cancel stays enabled and works while a save is in flight', 10, 'do NOTHING while saving',
    ("pk.disabled = saving; no.disabled = saving;", "pk.disabled = saving;"), ("no.onclick = () => { if (!saving) d.close('no'); };", "no.onclick = () => { d.close('no'); };"))
mut('E2-escape-not-blocked', 'Escape / the native cancel request close the dialog while a save is in flight', 10, 'do NOTHING while saving',
    ("      d.addEventListener('cancel', e => { if (saving) e.preventDefault(); });", ""),
    ("window.addEventListener('keydown', escGuard, true); sync(); d.tabIndex", "sync(); d.tabIndex"))
mut('E2b-escape-guard-on-dialog-only', 'the Escape guard listens on the dialog element only (the earlier design: it misses the key once focus has left the dialog)', 10, 'synthetic body-target Escape is intercepted by the pending-save window guard',
    ("window.addEventListener('keydown', escGuard, true); sync(); d.tabIndex = -1; d.focus();", "d.addEventListener('keydown', escGuard); sync();"))
mut('E3-no-saving-state', 'the editor does not say "Saving…"', 10, 'state says "Saving…"',
    ("st.textContent = saving ? 'Saving…' : busy", "st.textContent = busy"))
mut('E4-stay-disabled-after-failure', 'after a failed save the controls stay disabled (the editor is stuck)', 10, 'after the FAILED save the dialog is still open',
    ("        saving = false; window.removeEventListener('keydown', escGuard, true); sync();", "        if (r.ok) { saving = false; window.removeEventListener('keydown', escGuard, true); } sync();"))
mut('E5-picked-file-accepted-while-saving', 'a file chosen while a save is in flight replaces the draft', 10, 'do NOTHING while saving',
    ("const f = fi.files && fi.files[0]; fi.value = ''; if (!f || saving) return;", "const f = fi.files && fi.files[0]; fi.value = ''; if (!f) return;"))
# ---- 3B core safeguards
mut('V1-origcover-overwritten', 'origCover is rewritten on every save instead of captured once', 4, 'second replacement (a JPEG 800x600): origCover is STILL exactly the first original',
    ("if (!has(o, 'origCover')) o.origCover = cur;", "o.origCover = cur;"))
mut('V2-jpeg-eoi-unchecked', 'a JPEG without its end marker is no longer refused by the byte check', 5, 'JPEG cut in half (no end marker)',
    ("        if (!(u8[n - 2] === 0xFF && u8[n - 1] === 0xD9)) return cut;   // a JPEG that was cut off does not end with the end-of-image marker\n", ""))
mut('V3-png-extra-data-accepted', 'data after IEND (polyglot) is accepted', 5, 'polyglot',
    ("? { type: 'image/png', w: be32(16), h: be32(20) } : { err: 'extra' };", "? { type: 'image/png', w: be32(16), h: be32(20) } : { type: 'image/png', w: be32(16), h: be32(20) };"))
mut('V4-size-limit-removed', 'the 8 MB file limit is removed', 5, 'a file just over the 8 MB limit',
    ("maxFile: 8 * 1024 ** 2,", "maxFile: 1e12,"))
mut('V5-min-dimension-removed', 'the 16 pixel minimum is removed', 5, 'below the 16 pixel minimum',
    ("minSide: 16,", "minSide: 1,"))
mut('V6-megapixel-limit-removed', 'the 40 megapixel limit is removed (decode would be attempted)', 5, '48 megapixels',
    ("maxPixels: 40e6,", "maxPixels: 1e12,"))
mut('V7-playback-restart', 'refreshing the screens after a cover edit seeks the playing song to 0', 2, 'playback position CONTINUED',
    ("if (S.cur === id) updateNowPlaying(t); else renderNP();   // art, media session", "if (S.cur === id) { updateNowPlaying(t); A.currentTime = 0; } else renderNP();   // art, media session"))
mut('V8-stale-async-pick-kept', 'a picture that finishes reading after the editor closed or after a newer pick is applied', 6, 'S6g',
    ("if (closed || mine !== tok || !d.open) return;", ""))
mut('V9-http-original-loaded', 'the editor loads an http(s) original as a picture (a network request, address leak)', 4, 'does NOT request it',
    ("else if (/^https?:/i.test(orig)) o.innerHTML =", "else if (false) o.innerHTML ="))
mut('V10-reader-origcover-unchecked', 'the strict reader no longer validates origCover', 8, 'S8 refused: bad-orig-number',
    ("if (t.origCover !== undefined && !(typeof t.origCover === 'string'", "if (false && !(typeof t.origCover === 'string'"))
mut('V11-coverok-removed', 'saveCover no longer validates the value it commits', 6, 'S6f: saveCover itself refuses',
    ("if (!coverOk(next, t)) return {", "if (false) return {"))
mut('V12-700k-cap-on-revert', 'a legacy original larger than 700,000 characters can no longer be restored by Revert (cap applied to originals)', 11, 'S11 L3: Revert gives back the legacy original EXACTLY',
    ("(v === coverOrig(t) || (COVER_NEW_RE.test(v)", "((v === coverOrig(t) && v.length <= COVER.maxData) || (COVER_NEW_RE.test(v)"))
json.dump(M, open(os.path.join(out, 'mutants.json'), 'w'), indent=1)
print(len(M), 'mutants written')
