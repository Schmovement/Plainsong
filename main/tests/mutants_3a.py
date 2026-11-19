#!/usr/bin/env python3
"""Phase 3A mutation checks: writes one mutated copy of the app per safeguard (index.html with ONE safeguard removed, style.css unchanged) and mutants.json.
  python3 -I mutants_3a.py <project-dir> <out-dir>
tests/run_mutants_3a.sh serves each mutant and runs the scenario that must notice; the run passes only if that scenario FAILS on the intended check."""
import sys, os, json, shutil
proj, out = sys.argv[1], sys.argv[2]
src = open(os.path.join(proj, 'index.html'), encoding='utf-8').read()
M = []
def mut(mid, desc, scn, needle, old, new):
    assert src.count(old) == 1, (mid, src.count(old))
    d = os.path.join(out, mid); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(src.replace(old, new))
    shutil.copy(os.path.join(proj, 'style.css'), os.path.join(d, 'style.css'))
    M.append({'id': mid, 'desc': desc, 'scenario': scn, 'needle': needle})

mut('M1-no-rollback', 'a failed save no longer restores the previous record', 6, 'in-memory record is EXACTLY as before',
    """        t.title = prev.cur.title; t.artist = prev.cur.artist; t.album = prev.cur.album;
        if (prev.hadGenre) t.genre = prev.cur.genre; else delete t.genre;
        if (prev.hadOrig) t.origMeta = prev.orig; else delete t.origMeta;
""", "")
mut('M2-no-stale-check', 'the stale-epoch / changed-while-open check is removed', 6, 'S6c:',
    "if (epoch !== S.epoch || META.fields.some(f => cur[f] !== base[f])) return", "if (false) return")
mut('M3-no-busy-guard', 'Save no longer refuses during a backup/restore/write lock', 6, 'S6b: while a backup is running Save is refused',
    "if (S.restoreBusy || S.restoring || S.backupBusy || DB.lock) return { ok: false, msg: 'A backup or restore is running. Try again when it finishes. Nothing was saved.' };", "if (false) return {};")
mut('M4-snapshot-overwritten', 'origMeta is rewritten on every save instead of captured once', 4, 'snapshot is stable',
    "if (!prev.hadOrig) t.origMeta = { ...cur };", "t.origMeta = { ...cur };")
mut('M5-unescaped-originals', 'original values are inserted into the editor as HTML', 5, 'hostile ORIGINAL values',
    "${orig[f] ? esc(orig[f]) : '<span class=\"dim\">(empty)</span>'}", "${orig[f] ? orig[f] : '<span class=\"dim\">(empty)</span>'}")
mut('M6-playback-restart', 'refreshing the screens after an edit seeks the playing song to 0', 2, 'playback position CONTINUED',
    "if (S.cur === id) updateNowPlaying(t); else renderNP();", "if (S.cur === id) { updateNowPlaying(t); A.currentTime = 0; } else renderNP();")
mut('M7-search-refetch', 'saving from the search view re-renders it (refetching Audius/Archive)', 1, 'saving from the search view makes NO network request',
    "else if (v.name === 'search' && $('#sLibBody')) { $('#sLibBody').innerHTML = searchLocal(v.q || '', (v.src || 'all') === 'all'); }", "else if (v.name === 'search') render(true);")
mut('M8-reader-origmeta-unchecked', 'the strict reader no longer validates origMeta', 8, 'S8 refused: bad-origmeta',
    "if (t.origMeta !== undefined) {   // Phase 3A", "if (false) {   // Phase 3A")
mut('M9-reader-genre-unchecked', 'the strict reader no longer validates genre', 8, 'S8 refused: bad-genre',
    "if (t.genre !== undefined && typeof t.genre !== 'string') add('genre must be text');", "")
json.dump(M, open(os.path.join(out, 'mutants.json'), 'w'), indent=1)
print(len(M), 'mutants written')
