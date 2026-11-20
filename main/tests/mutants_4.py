#!/usr/bin/env python3
"""Phase 4 mutation checks: writes one mutated copy of the app per safeguard (index.html with ONE safeguard removed or reverted to an unsafe design, style.css unchanged) and mutants.json.
  python3 -I mutants_4.py <project-dir> <out-dir>
tests/run_mutants_4.sh serves each mutant and runs the scenario that must notice; a mutant counts as DETECTED only if that scenario FAILS on the intended check
(a mutant the suite does not notice is reported as such, never hidden)."""
import sys, os, json, shutil
proj, out = sys.argv[1], sys.argv[2]
src = open(os.path.join(proj, 'index.html'), encoding='utf-8').read()
M = []
def mut(mid, desc, scn, needle, *pairs, must_pass=()):
    # needle: one substring (or a list of them) that resolves, in the UNMUTATED run of the scenario, to exactly ONE check name each; ALL of them must FAIL on the mutant.
    # must_pass: substrings of checks that must still PASS on the mutant (isolation: the defect is the intended one, not a nearby one).
    assert isinstance(scn, int) and not isinstance(scn, bool)
    s = src
    for old, new in pairs:
        assert s.count(old) == 1, (mid, s.count(old), old[:90])
        s = s.replace(old, new)
    assert s != src, mid
    d = os.path.join(out, mid); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(s)
    shutil.copy(os.path.join(proj, 'style.css'), os.path.join(d, 'style.css'))
    M.append({'id': mid, 'desc': desc, 'scenario': scn, 'must_fail': [needle] if isinstance(needle, str) else list(needle), 'must_pass': list(must_pass)})

GUARD = "if (S.restoreBusy || S.restoring || S.backupBusy || DB.lock) return { ok: false, msg: 'A backup or restore is running. Try again when it finishes. Nothing was saved.' };"
GONE = "if (S.tracks.get(tid) !== t || epoch !== S.epoch) return { ok: false, msg: 'This song is no longer in your library. Nothing was saved.' };"

# ---- model: absent vs 0, independence from likes, no-ops, validation
mut('M1-zero-counts-as-absent-on-clear', 'clearing a song that was never rated writes a 0 (missing turned into 0)', 0, 'R0: clearing a song that was never rated is a no-op',
    ("        if (before === value) return { ok: true, none: true, value };", "        if (before === value && (value !== 0 || 'rating' in t)) return { ok: true, none: true, value };"))
mut('M2-no-noop-shortcut', 'setting the value a song already has still writes', 6, 'R6: setting the value a song already has',
    ("        if (before === value) return { ok: true, none: true, value };\n", ""))
mut('M3-validation-removed', 'setRating no longer validates the value (NaN, 6, "3", -0 ... are stored)', 6, 'R6: every invalid rating',
    ("      if (!Number.isInteger(value) || value < 0 || value > 5 || Object.is(value, -0)) return { ok: false, msg: 'A rating must be a whole number from 0 to 5. Nothing was saved.' };\n", ""))
mut('M4-rating-toggles-like', 'rating a song also likes it', 2, 'R2: rating an unliked song 5 stars does not like it',
    ("      const apply = o => { o.rating = value; };", "      const apply = o => { o.rating = value; o.liked = true; };"))
mut('M5-backup-restore-guard-removed', 'a rating can be written while a backup or restore runs (both guards removed)', 6, 'R6: while a backup or restore is running',
    ("      " + GUARD + "\n      const epoch = S.epoch;\n", "      const epoch = S.epoch;\n"),
    ("        " + GUARD + "\n        const before = ratingOf(t);", "        const before = ratingOf(t);"))
mut('M6-clear-click-sets', 'clicking the star a song already has sets it again instead of clearing', 1, ['R1 local L1: clicking the current star clears', 'R1 saved web W1: clicking the current star clears'],
    ("return applyRating(tid, ratingOf(t) === n ? 0 : n); }", "return applyRating(tid, n); }"))
mut('M7-eager-legacy-rewrite', 'showing the library list rewrites legacy songs with an explicit rating 0', 0, 'R0: sorting by rating both ways and trying every filter makes NO write',
    ("      const tk = tokens(v.filter || ''), rf = v.rate || 'any', all = S.tracks.size;\n      const ts = [...S.tracks.values()].filter(t => matches(t, tk) && rateMatch(t, rf))",
     "      const tk = tokens(v.filter || ''), rf = v.rate || 'any', all = S.tracks.size;\n      if (rf !== 'any' || /^rating/.test(v.sort || '')) for (const t0 of S.tracks.values()) if (t0.rating === undefined) { t0.rating = 0; dbPutTrack(t0); }\n      const ts = [...S.tracks.values()].filter(t => matches(t, tk) && rateMatch(t, rf))"))

# ---- write coordination
mut('W1-mutate-then-put', 'setRating mutates the shared record first and then writes it (a failed write leaves the uncommitted rating in memory and in other writers\' snapshots)', 7, 'R7b: after the REJECTED rating write nothing of the rating exists anywhere',
    ("          const clone = structuredClone(t); apply(clone);\n          try { await DB.put('tracks', clone); }\n          catch (e) { return { ok: false, msg: `Couldn’t save the rating", "          apply(t); const clone = t;\n          try { await DB.put('tracks', clone); }\n          catch (e) { return { ok: false, msg: `Couldn’t save the rating"))
mut('W2-no-per-track-queue', 'the per-track write queue is removed: every writer runs immediately', 7, 'R7a: the like is queued behind the held rating write',
    ("      const p = prev ? prev.then(task) : task();", "      const p = task();"))
mut('W3-stale-clone-applied', 'after a committed rating write the whole stale clone is copied over the shared record (a like made while the write was pending is overwritten)', 7, 'R7a: after the release BOTH changes are in the raw DB',
    ("          " + GONE + "\n        }\n        apply(t);\n        return { ok: true, value, before, memoryOnly", "          " + GONE + "\n          Object.assign(t, clone);\n        }\n        apply(t);\n        return { ok: true, value, before, memoryOnly"))
mut('W4-removed-song-resurrected', 'a rating write that finishes after the song was removed still reports success and touches the detached record', 7, 'R7e: removing the song while its rating write is held',
    ("          " + GONE + "\n        }\n        apply(t);\n        return { ok: true, value, before, memoryOnly", "          if (epoch !== S.epoch) return { ok: false, msg: 'This song is no longer in your library. Nothing was saved.' };\n        }\n        apply(t);\n        return { ok: true, value, before, memoryOnly"))
mut('W5-epoch-ignored', 'a library replaced by a restore while the write was pending is not noticed', 7, 'R7f: if the library epoch changed while the write was pending',
    ("          " + GONE + "\n        }\n        apply(t);\n        return { ok: true, value, before, memoryOnly", "          if (S.tracks.get(tid) !== t) return { ok: false, msg: 'This song is no longer in your library. Nothing was saved.' };\n        }\n        apply(t);\n        return { ok: true, value, before, memoryOnly"))

# ---- playback continuity
mut('P1-rating-seeks-playing-song', 'rating a song seeks the playing song back to 0', 8, 'R8: click star 3 on the PLAYING song: the playback position (currentTime) was not reset',
    ("      refreshRatingUI(tid);\n      const v = S.view, t = S.tracks.get(tid);", "      refreshRatingUI(tid); if (S.cur === tid) A.currentTime = 0;\n      const v = S.view, t = S.tracks.get(tid);"),
    must_pass=['R8: click star 3 on the PLAYING song: the same audio source keeps playing', 'R8: click star 3 on the PLAYING song: current song, queue position'])
mut('P2-rating-skips-queue', 'rating the playing song advances the queue', 8, 'R8: click star 3 on the PLAYING song: current song, queue position',
    ("      refreshRatingUI(tid);\n      const v = S.view, t = S.tracks.get(tid);", "      refreshRatingUI(tid); if (S.cur === tid) S.qi = Math.min(S.queue.length - 1, S.qi + 1);\n      const v = S.view, t = S.tracks.get(tid);"),
    must_pass=['R8: click star 3 on the PLAYING song: the same audio source keeps playing', 'R8: click star 3 on the PLAYING song: the playback position (currentTime) was not reset'])

# ---- sort and filter
mut('F1-sort-no-ties', 'rating sort has no tie-break (ties keep an arbitrary earlier order)', 4, 'R4: "Rating: high to low" shows the order',
    ("SORTS.ratingHigh = (a, b) => ratingOf(b) - ratingOf(a) || byRateTie(a, b);", "SORTS.ratingHigh = (a, b) => ratingOf(b) - ratingOf(a);"))
mut('F2-low-reverses-ties', 'low-to-high is the exact reverse of high-to-low (ties reversed too)', 4, 'R4: "Rating: low to high" shows the independently computed order',
    ("SORTS.ratingLow = (a, b) => ratingOf(a) - ratingOf(b) || byRateTie(a, b);", "SORTS.ratingLow = (a, b) => ratingOf(a) - ratingOf(b) || byRateTie(b, a);"))
mut('F3-high-direction-swapped', 'high-to-low sorts ascending', 4, 'R4: "Rating: high to low" shows the order',
    ("SORTS.ratingHigh = (a, b) => ratingOf(b) - ratingOf(a) || byRateTie(a, b);", "SORTS.ratingHigh = (a, b) => ratingOf(a) - ratingOf(b) || byRateTie(a, b);"))
mut('F4-unrated-only-absent', 'the Unrated filter matches only songs with no rating field (a cleared 0 is not unrated)', 5, 'R5: filter "unrated"',
    ("return f === 'unrated' ? r === 0 :", "return f === 'unrated' ? t.rating === undefined :"))
mut('F5-rated-includes-zero', 'the Rated filter includes unrated songs', 5, 'R5: filter "rated"',
    ("f === 'rated' ? r >= 1 :", "f === 'rated' ? r >= 0 :"))
mut('F6-four-plus-exact', 'the "4 stars and up" filter matches only exactly 4', 5, 'R5: filter "4"',
    ("(f === '4' || f === '3' || f === '2') ? r >= +f : true; };", "(f === '4' || f === '3' || f === '2') ? (f === '4' ? r === 4 : r >= +f) : true; };"))
mut('F7-count-wrong', 'the count line shows the number shown out of the number shown', 5, 'R5: filter "5"',
    ("`${ts.length} of ${all} song${all === 1 ? '' : 's'}` :", "`${ts.length} of ${ts.length} song${ts.length === 1 ? '' : 's'}` :"))
mut('F8-empty-state-generic', 'the empty state no longer says which filters match nothing', 5, 'R5: an empty result says which filters match nothing',
    ("          : `<div class=\"empty\">No songs match “${esc(lab)}”${tk.length ? ` and “${esc(v.filter || '')}”` : ''}.<div class=\"btn-row\"><button class=\"btn\" data-act=\"libClear\">Clear the filters</button></div></div>`;",
     "          : `<div class=\"empty\">Nothing here.</div>`;"))
mut('F9-text-filter-ignored-with-rating', 'a rating filter replaces the text filter instead of combining with it', 5, 'R5: the rating filter combines with the text filter',
    ("filter(t => matches(t, tk) && rateMatch(t, rf))", "filter(t => (rf === 'any' ? matches(t, tk) : rateMatch(t, rf)))"))
mut('F10-list-not-refreshed', 'rating a song while a rating filter is on leaves the list as it was', 5, 'R5: rating E1 while the "Unrated" filter is on removes it from the list',
    ("        fillSongs();   // the song may move or drop out of the list: re-read it, and keep the keyboard where it was\n", ""))
mut('F11-focus-lost', 'after the list is re-read the keyboard focus is dropped', 5, 'the keyboard focus stays on that song\'s star group',
    ("if (b) b.focus(); }\n      }\n      toast(value", "if (b) b.blur(); }\n      }\n      toast(value"))

# ---- UI semantics and keyboard
mut('U1-group-unlabelled', 'the star group has no accessible name', 0, 'R0: each of the 3 local and 2 saved web songs shows a labelled 5-star radio group',
    ("role=\"radiogroup\" aria-label=\"Rating for ${esc(t.title)}\">", "role=\"radiogroup\">"))
mut('U2-stars-on-unsaved-song', 'a song that is only shown (not in the library) also gets stars', 0, 'R0: a song that is only SHOWN',
    ("      if (!S.tracks.has(t.id)) return '';   // only songs that are in the library can be rated (a search result that is not saved cannot)\n", ""))
mut('U3-arrow-keys-leak', 'arrow keys on a star also reach the global shortcuts (volume / seek)', 3, 'R3: ArrowUp moves focus on (star 4) and does not change the volume',
    ("      if (to >= 0) { e.preventDefault(); e.stopPropagation(); btns.forEach(", "      if (to >= 0) { e.preventDefault(); btns.forEach("))
mut('U4-all-tab-stops', 'every star is a tab stop (no roving tabindex)', 3, 'R3: before any key press the unrated star group of each of the 5 songs has exactly ONE tab stop',
    ("aria-label=\"${n} star${n === 1 ? '' : 's'}\" title=\"${n === r ? 'Click again to clear the rating' : `${n} star${n === 1 ? '' : 's'}`}\" tabindex=\"${n === f ? 0 : -1}\">", "aria-label=\"${n} star${n === 1 ? '' : 's'}\" title=\"${n === r ? 'Click again to clear the rating' : `${n} star${n === 1 ? '' : 's'}`}\" tabindex=\"0\">"))

# ---- backup / restore
mut('B1-export-writes-zero', 'the backup writes rating 0 for songs that never had one (missing turned into 0)', 9, 'R9 E0: the backup of a library in which nothing was ever rated carries NO rating',
    ("mk('data/tracks.json', jsonArrayBlob(snap.tracks))", "mk('data/tracks.json', jsonArrayBlob(snap.tracks.map(t => ('rating' in t) ? t : { ...t, rating: 0 })))"))
mut('B2-restore-normalises-zero', 'restore drops a present rating 0 (zero turned into missing)', 9, 'R9 E1 -> clean: tracks identical to the backup',
    ("      if (iss.length) throw dbad('shape', 'Some songs have invalid fields.', iss);\n", "      if (iss.length) throw dbad('shape', 'Some songs have invalid fields.', iss);\n      tracks.forEach(t => { if (t.rating === 0) delete t.rating; });\n"))
mut('B3-reader-rejects-zero', 'the strict reader refuses a present rating 0', 9, 'R9 E1 -> clean: real UI restore finished',
    ("Number.isInteger(t.rating) && t.rating >= 0 && t.rating <= 5", "Number.isInteger(t.rating) && t.rating >= 1 && t.rating <= 5"))
mut('B4-reader-requires-rating', 'the strict reader refuses archives that carry no rating (old backups)', 9, 'R9 E0 (old-style, no rating) -> clean: real UI restore finished',
    ("if (t.rating !== undefined && !(Number.isInteger", "if (t.rating === undefined || !(Number.isInteger"))
mut('B5-reader-unchecked', 'the strict reader no longer validates rating', 10, 'R10 refused: bad-rating-6 ',
    ("if (t.rating !== undefined && !(Number.isInteger", "if (false && !(Number.isInteger"))
mut('B6-reader-accepts-fraction', 'the strict reader accepts any number (2.5, 0.5, 5.000001)', 10, 'R10 refused: bad-rating-2.5 ',
    ("Number.isInteger(t.rating) && t.rating >= 0 && t.rating <= 5", "typeof t.rating === 'number' && t.rating >= 0 && t.rating <= 5"))
mut('B7-reader-coerces-text', 'the strict reader coerces text and booleans to numbers ("3", true, null)', 10, 'R10 refused: bad-rating-text-3 ',
    ("Number.isInteger(t.rating) && t.rating >= 0 && t.rating <= 5", "Number.isInteger(+t.rating) && +t.rating >= 0 && +t.rating <= 5"))
mut('B8-reader-range-widened', 'the strict reader accepts ratings above 5', 10, 'R10 refused: bad-rating-6 ',
    ("Number.isInteger(t.rating) && t.rating >= 0 && t.rating <= 5", "Number.isInteger(t.rating) && t.rating >= 0 && t.rating <= 50"))
mut('B9-reader-negzero-accepted', 'the strict reader accepts the JSON literal -0', 10, 'R10 refused: bad-rating-neg-zero ',
    (" && !Object.is(t.rating, -0))) add('rating must be", ")) add('rating must be"))

# ---- regressions found by review of the work-in-progress (R11)
mut('X1-star-action-shadows-speed-preset', 'the star action reuses the name of the playback-speed preset action (the first matching case wins, so the speed presets stop working)', 11, 'R11a: clicking the 1.5x speed preset sets the speed',
    ('role="radio" data-act="rateSong" data-v="${n}"', 'role="radio" data-act="rate" data-v="${n}"'),
    ("        case 'rateSong': rateAct(tidOf(a), +d.v); break;   // NOT 'rate': that is the playback-speed preset action below", "        case 'rate': rateAct(tidOf(a), +d.v); break;"),
    must_pass=['R11b: a real restore of the earlier backup'])
mut('X2-stale-delete-after-restore', 'a queued track delete still runs after a restore replaced the library (it erases the restored song with the same id)', 11, 'R11b: after the slow write ends, the stale delete did NOT erase the restored song',
    ("trackWrite(id, async () => { if (epoch !== S.epoch) return false; await DB.del('tracks', id); return true; })", "trackWrite(id, async () => { await DB.del('tracks', id); return true; })"),
    must_pass=['R11b: a real restore of the earlier backup', 'R11a: clicking the 1.5x speed preset sets the speed'])
mut('X3-old-removal-touches-restored-library', 'the removal continues after the library was replaced: it deletes the restored audio and edits the restored playlists and queue', 11, 'R11b: the old removal did not touch the restored library either',
    ("      if (epoch !== S.epoch) return;   // a restore replaced the library while the delete waited: nothing of this removal may touch the restored one (its song, audio, playlists or queue)\n      await dbDel('blobs', id);\n      if (epoch !== S.epoch) return;   // (same, if the restore came while the audio delete was running)\n", "      await dbDel('blobs', id);\n"),
    must_pass=['R11b: a real restore of the earlier backup'])
json.dump(M, open(os.path.join(out, 'mutants.json'), 'w'), indent=1)
print(len(M), 'mutants written')
