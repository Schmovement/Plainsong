#!/usr/bin/env python3
"""Phase 5 mutation checks: writes one mutated copy of the app per safeguard (index.html with ONE safeguard removed or reverted to an unsafe design, style.css unchanged) and mutants.json.
  python3 -I mutants_5.py <project-dir> <out-dir>
tests/run_mutants_5.sh serves each mutant and runs the scenario that must notice; a mutant counts as DETECTED only if EVERY check named in must_fail FAILS on it (each is an exact check name resolved in the unmutated control run)
and every must_pass check still passes (the defect is the intended one). A mutant the suite does not notice is reported as such, never hidden."""
import sys, os, json, shutil, re
proj, out = sys.argv[1], sys.argv[2]
src = open(os.path.join(proj, 'index.html'), encoding='utf-8').read()
M = []
BAD = []
def mut(mid, desc, scn, needle, *pairs, must_pass=()):
    # each pair is (old, new) or (old, new, count): old must occur exactly count times (default 1)
    assert isinstance(scn, int) and not isinstance(scn, bool)
    s = src
    for p in pairs:
        old, new, cnt = (p + (1,))[:3]
        if s.count(old) != cnt:
            BAD.append((mid, s.count(old), cnt, old[:90])); return
        s = s.replace(old, new)
    assert s != src, mid
    d = os.path.join(out, mid); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(s)
    shutil.copy(os.path.join(proj, 'style.css'), os.path.join(d, 'style.css'))
    M.append({'id': mid, 'desc': desc, 'scenario': scn, 'must_fail': [needle] if isinstance(needle, str) else list(needle), 'must_pass': list(must_pass)})

# ---- rule engine (Q1 / Q2)
NUM6 = 'Q1: plays, rating and duration × the six numeric operators'
mut('E1-gt-is-gte', 'the numeric operator "greater than" behaves as "at least"', 1, [NUM6, 'Q1: Duration > 5:00 AND plays ≥ 1 selects exactly', 'Q1: exact boundaries: duration 300 s'],
    ("gt: t => smNum(t, f) > v, gte:", "gt: t => smNum(t, f) >= v, gte:"), must_pass=['Q1: added and last × within / before × day boundaries', 'Q1: liked yes / no and song type'])
mut('E2-within-edge-exclusive', 'a song added exactly N days ago is no longer "within" N days (the edge flips)', 1, 'Q1: added and last × within / before with the clock at the exact stamp moment',
    ("return c.op === 'within' ? t => { const x = smTime(t, f); return x > 0 && x >= edge; }", "return c.op === 'within' ? t => { const x = smTime(t, f); return x > 0 && x > edge; }"), must_pass=[NUM6])
mut('E2b-before-edge-inclusive', 'a song exactly N days old counts as "more than" N days old (the other edge flips)', 1, 'Q1: added and last × within / before with the clock at the exact stamp moment',
    ("return x > 0 && x < edge; };", "return x > 0 && x <= edge; };"), must_pass=[NUM6])
mut('E3-text-case-sensitive', 'text conditions become case-sensitive', 1, 'Q1: title, artist, album and genre × contains / notContains / is',
    ("contains: t => smText(t, f).toLowerCase().includes(q), notContains: t => !smText(t, f).toLowerCase().includes(q), is: t => smText(t, f).toLowerCase() === q",
     "contains: t => smText(t, f).includes(v), notContains: t => !smText(t, f).includes(v), is: t => smText(t, f) === v"), must_pass=[NUM6])
mut('E4-no-tie-break', 'equal sort values are left in library order (no title, artist, id tie-break)', 2, 'Q2: the order of the stored library does not matter',
    ("return (a, b) => sg * smText(a, k).localeCompare(smText(b, k)) || byRateTie(a, b);", "return (a, b) => sg * smText(a, k).localeCompare(smText(b, k));"),
    ("      return (a, b) => sg * (val(a) - val(b)) || byRateTie(a, b);", "      return (a, b) => sg * (val(a) - val(b));"), must_pass=['Q2: the limit applies AFTER sorting'])
mut('E5-desc-reverses-ties', 'descending order reverses the tie-break as well (ties come out in reverse id order)', 2, ['Q2: ties break by title, artist, id ascending in BOTH directions', 'Q2: descending is NOT simply the reverse of ascending'],
    ("      return (a, b) => sg * (val(a) - val(b)) || byRateTie(a, b);", "      return (a, b) => sg * ((val(a) - val(b)) || byRateTie(a, b));"))
mut('E6-limit-before-sort', 'the limit is applied before sorting (the first N songs of the library, then sorted)', 2, 'Q2: the limit applies AFTER sorting',
    ("      keep.sort(smSorter(rule.sort));\n      return rule.limit ? keep.slice(0, rule.limit) : keep;", "      const cut = rule.limit ? keep.slice(0, rule.limit) : keep; cut.sort(smSorter(rule.sort));\n      return cut;"))
mut('E7-missing-number-not-zero', 'a missing play count is not treated as 0 (undefined propagates)', 1, ['Q1: exact boundaries: duration 300 s', NUM6],
    (": (Number.isFinite(x) && x > 0 ? x : 0); };", ": x; };"))
mut('E8-all-any-swapped', 'match "all" and "any" are swapped', 1, 'Q1: 200 generated combinations',
    ("(rule.match === 'all' ? tests.every(f => f(t)) : tests.some(f => f(t)))", "(rule.match === 'any' ? tests.every(f => f(t)) : tests.some(f => f(t)))"), must_pass=[NUM6])
mut('E9-nine-conditions-valid', 'the validator stops checking conditions beyond the 8th (nine conditions pass)', 1, 'Q1: the validator rejects every invalid rule',
    ("if (r.conds.length > SM.maxConds) bad.push(`A rule can have at most ${SM.maxConds} conditions.`);", ""), must_pass=['Q1: the validator accepts every valid rule shape'])
mut('E10-negative-zero-valid', 'the validator accepts -0 as a number', 1, 'Q1: the validator rejects every invalid rule',
    ("typeof v === 'number' && Number.isInteger(v) && !Object.is(v, -0) && v >= lo && v <= hi", "typeof v === 'number' && Number.isInteger(v) && v >= lo && v <= hi"), must_pass=['Q1: the validator accepts every valid rule shape'])
mut('E11-untrimmed-text-valid', 'the validator accepts untrimmed text values', 1, 'Q1: the validator rejects every invalid rule',
    ("typeof v !== 'string' || v !== v.trim() || v.length < 1", "typeof v !== 'string' || v.length < 1"), must_pass=['Q1: the validator accepts every valid rule shape'])
mut('E12-duration-parser-minutes-as-hours', 'the duration input treats m:ss as h:mm (5:00 becomes 18000 s)', 1, 'Q1: duration input: 5:00 = 300',
    ("else if ((m = /^([0-9]{1,4}):([0-5][0-9])$/.exec(s))) n = +m[1] * 60 + +m[2];", "else if ((m = /^([0-9]{1,4}):([0-5][0-9])$/.exec(s))) n = +m[1] * 3600 + +m[2] * 60;"), must_pass=[NUM6])

# ---- editor, presets (Q3 / Q4)
mut('U1-preset-long-off-by-one', 'the "Long songs" preset uses "at least" 5:00 instead of "greater than"', 3, 'Q3: preset "Long songs"',
    ("{ key: 'long', name: 'Long songs', rule: { v: 1, match: 'all', conds: [{ f: 'duration', op: 'gt', v: 300 }]", "{ key: 'long', name: 'Long songs', rule: { v: 1, match: 'all', conds: [{ f: 'duration', op: 'gte', v: 300 }]"), must_pass=['Q3: preset "Most played"', 'Q3: preset "Recently added"'])
mut('U2-duration-stored-as-typed-minutes', 'the editor stores "5:00" as 5 (minutes) instead of 300 seconds', 3, 'Q3: "Duration > 5:00" AND "plays ≥ 1" typed in the editor',
    ("else if (kind === 'dur') { v = parseDur(raw); if (v === null)", "else if (kind === 'dur') { v = parseDur(raw); if (v !== null && /^[0-9]+:[0-5][0-9]$/.test(raw)) v = Math.floor(v / 60); if (v === null)"), must_pass=['Q3: preset "Most played"'])
GROUPS = ['Q4: the name that is invalid', 'Q4: a Duration value that is invalid', 'Q4: a plays / rating value that is invalid', 'Q4: a number of days that is invalid', 'Q4: a text value that is invalid', 'Q4: the limit that is invalid']
mut('U3-aria-invalid-not-set', 'invalid fields are not marked aria-invalid', 4, GROUPS + ['Q4: several problems are all listed together'],
    ("r.errs.forEach(x => { const n = document.getElementById(x.id); if (n && d.contains(n)) n.setAttribute('aria-invalid', 'true'); });", ""), must_pass=['Q4: the editor stops at 8 conditions'])
mut('U4-focus-not-moved-to-error', 'after a refused Save the focus stays on the Save button (not moved to the first problem)', 4, GROUPS,
    ("(n && d.contains(n) ? n : errEl).focus(); return;", "return;"), must_pass=['Q4: several problems are all listed together', 'Q4: the editor stops at 8 conditions'])
mut('U5-add-condition-unbounded', 'the editor allows more than 8 conditions', 4, 'Q4: the editor stops at 8 conditions',
    ("$('#spAdd', d).disabled = st.conds.length >= SM.maxConds;", ""), ("if (st.conds.length >= SM.maxConds) return; st.conds.push", "st.conds.push"), must_pass=['Q4: removing a condition re-enables'])
mut('U6-double-submit-allowed', 'the editor can be submitted twice at once (two playlists)', 8, 'Q8: submitting the editor twice at once creates exactly one playlist',
    ("e.preventDefault(); if (busy) return; syncModel();", "e.preventDefault(); syncModel();"), must_pass=['Q8: once the flags are cleared a save works again'])

# ---- dynamic membership (Q5)
mut('D1-like-does-not-refresh-list', 'a like toggled in a smart list does not refresh the list', 5, ['Q5: un-liking a song in the list makes it leave the list at once', 'Q5: after that un-like the header says 2 songs'],
    ("      if (!t.liked && S.view.name === 'library' && S.view.tab === 'liked') refresh();\n      smartTouch();\n", "      if (!t.liked && S.view.name === 'library' && S.view.tab === 'liked') refresh();\n"), must_pass=['Q5: a song liked in the Songs tab appears'])
mut('D2-rating-does-not-refresh-list', 'a rating changed in a smart list does not refresh the list', 5, ['Q5: giving a song 1 star in the list removes it', 'Q5: giving another song 5 stars re-orders the list'],
    ("      refreshRatingUI(tid); smartTouch();\n", "      refreshRatingUI(tid);\n"), must_pass=['Q5: un-liking a song in the list makes it leave'])
mut('D3-edit-does-not-refresh-list', 'a title edit does not refresh a smart list (BOTH independent refresh paths removed: the smartTouch call and the playlist-view re-render inside metaRefresh; either one alone is redundant with the other, which is why a single-path mutant survived)', 5, 'Q5: renaming a song to "Omega" through Edit info removes it',
    ("        if (t) metaRefresh(t, r.before);\n        smartTouch();\n", "        if (t) metaRefresh(t, r.before);\n"),
    ("v.key = artistKey(t);\n      if (['library', 'album', 'artist', 'playlist'].includes(v.name)) render(true);", "v.key = artistKey(t);\n      if (['library', 'album', 'artist', 'playlist'].includes(v.name) && !(v.name === 'playlist' && isSmart(S.playlists.find(p => p.id === v.id)))) render(true);"), must_pass=['Q5: giving a song 1 star in the list removes it'])
mut('D4-library-change-does-not-refresh-list', 'a song saved into the library (libStat) does not refresh an open smart list (import itself also refreshes, so only the web-song save path depends on this hook)', 5, 'Q5: a web song saved into the library while the "everything" list is open appears in it by itself',
    ("    function libStat() {\n      setTimeout(smartTouch, 0);\n", "    function libStat() {\n"), must_pass=['Q5: removing a song from the library'])
mut('D5-play-count-does-not-refresh-list', 'a play counted in the background does not refresh an open smart list', 5, ['Q5: when a song has really been played long enough to count', 'Q5: that play was counted once (plays 0 → 1) with a last-played time'],
    ("        saveHist(); smartTouch();\n", "        saveHist();\n"), must_pass=['Q5: importing two songs by "Tgt Artist"'])
mut('D6-membership-stored-at-creation', 'a smart playlist keeps the song ids it had when it was created (membership is stored, not live)', 3, ['Q3: editing "Most played"', 'Q3: after a reload the smart view shows the same songs'],
    ("      const pl = { id: uid(), name: nm.v, ids: [], created: Date.now(), rule: structuredClone(rule) };", "      const pl = { id: uid(), name: nm.v, ids: ruleRun(rule).map(t => t.id), created: Date.now(), rule: structuredClone(rule) };"))

# ---- queue (Q7)
mut('Q1-play-queues-reverse-order', 'Play queues the smart list in reverse order', 7, 'Q7: Play queues the smart list as it is at the click', 
    ("if (inf.tracks.length) playList(inf.tracks.map(t => t.id), 0, { shuffle: !!d.shuffle });", "if (inf.tracks.length) playList(inf.tracks.map(t => t.id).reverse(), 0, { shuffle: !!d.shuffle });"), must_pass=['Q7: liking and rating songs while the list is playing changes nothing'])

# ---- write safety (Q8)
mut('S1-writes-not-queued', 'smart-playlist update and delete are not queued per playlist (they run at once)', 8, 'Q8: a delete asked while a save is still held waits for it',
    ("      const apply = o => { if ('name' in next) o.name = next.name; if ('rule' in next) o.rule = structuredClone(next.rule); };\n      return trackWrite('pl:' + pid, async () => {", "      const apply = o => { if ('name' in next) o.name = next.name; if ('rule' in next) o.rule = structuredClone(next.rule); };\n      return (async () => {"),
    ("        apply(pl);\n        return { ok: true, pl, memoryOnly: !DB.ok };\n      });", "        apply(pl);\n        return { ok: true, pl, memoryOnly: !DB.ok };\n      })();"),
    ("      return trackWrite('pl:' + pid, async () => {\n        if (S.playlists.find(p => p.id === pid) !== pl) return { ok: false, msg: 'This playlist no longer exists.' };", "      return (async () => {\n        if (S.playlists.find(p => p.id === pid) !== pl) return { ok: false, msg: 'This playlist no longer exists.' };"),
    ("        S.playlists = S.playlists.filter(p => p !== pl);\n        return { ok: true, memoryOnly: !DB.ok };\n      });", "        S.playlists = S.playlists.filter(p => p !== pl);\n        return { ok: true, memoryOnly: !DB.ok };\n      })();"),
    must_pass=['Q8: creating through the library function stores the record'])
mut('S2-apply-before-write', 'the shared record is changed before the write is durable (a failed write leaves the new rule in memory)', 8, ['Q8: while the save is still being written', 'Q8: a REJECTED write reports "Nothing was changed"'],
    ("          const clone = structuredClone(pl); apply(clone);\n          try { await DB.put('playlists', clone); }", "          apply(pl); const clone = structuredClone(pl);\n          try { await DB.put('playlists', clone); }"), must_pass=['Q8: once the write is durable both the shared record'])
mut('S3-clone-made-before-queue', 'the record written is copied when the save is asked for, not when it runs (a queued rename overwrites an earlier rule save)', 8, 'Q8: a rename queued behind a rule save applies on top of it',
    ("      return trackWrite('pl:' + pid, async () => {\n        if (S.playlists.find(p => p.id === pid) !== pl) return { ok: false, msg: SM_GONE };", "      const early = structuredClone(pl);\n      return trackWrite('pl:' + pid, async () => {\n        if (S.playlists.find(p => p.id === pid) !== pl) return { ok: false, msg: SM_GONE };"),
    ("          const clone = structuredClone(pl); apply(clone);\n          try { await DB.put('playlists', clone); }", "          const clone = early; apply(clone);\n          try { await DB.put('playlists', clone); }"), must_pass=['Q8: two saves made from the same editor basis', 'Q8: a REJECTED write reports'])
mut('S4-basis-not-checked', 'a save no longer checks that the playlist is still as the editor saw it', 8, ['Q8: two saves made from the same editor basis', 'Q8: an editor opened before another change refuses to save over it'],
    ("        if (('name' in next && pl.name !== base.name) || ('rule' in next && JSON.stringify(pl.rule) !== base.rule)) return { ok: false, msg: 'This playlist changed while the editor was open. Close it and open it again. Nothing was saved.' };\n", ""), must_pass=['Q8: a REJECTED write reports'])
mut('S5-epoch-ignored', 'a library replaced by a restore is not noticed by smart-playlist saves', 8, 'Q8: with the epoch of the library that was replaced, create, update and delete are all refused',
    ("if (epoch !== S.epoch) return { ok: false, msg: SM_NEWLIB };", "if (false) return { ok: false, msg: SM_NEWLIB };", 8), ("|| epoch !== S.epoch) return { ok: false, msg: SM_NEWLIB };", ") return { ok: false, msg: SM_NEWLIB };"), must_pass=['Q8: a real restore of the earlier backup finishes'])
mut('S6-busy-guard-removed', 'smart-playlist writes are allowed while a backup or restore runs', 8, ['Q8: while a backup, a restore (either flag) or the database lock is on', 'Q8: while a backup or restore runs the editor does not even open'],
    ("const smBusy = () => S.restoreBusy || S.restoring || S.backupBusy || DB.lock;", "const smBusy = () => false;"), ("if (smBusy()) { toast('A backup or restore is running. Try again when it finishes.', 3200); return; }", ""), must_pass=['Q8: submitting the editor twice at once creates exactly one playlist'])
mut('S7-queued-save-resurrects-deleted', 'a save queued behind a delete does not notice the playlist is gone (it writes the record back)', 8, 'Q8: a save queued behind a held delete is refused when its turn comes',
    ("      return trackWrite('pl:' + pid, async () => {\n        if (S.playlists.find(p => p.id === pid) !== pl) return { ok: false, msg: SM_GONE };\n", "      return trackWrite('pl:' + pid, async () => {\n"), must_pass=['Q8: a save that comes after the delete is refused'])

# ---- backup reader (Q9)
ids = re.findall(r"^bad\('(bad-[^']+)'", open(os.path.join(proj, 'tests', 'make_rule_archives.py'), encoding='utf-8').read(), re.M)
ids = [i for i in ids if i != 'bad-smart-with-songs' and i != 'bad-smart-ids-text']
assert len(ids) >= 55, len(ids)
mut('V1-reader-ignores-rule', 'the strict reader does not validate a playlist rule at all', 9, [f'Q9 refuse {i}:' for i in ids],
    ("          const rp = ruleProblems(p.rule); if (rp.length) add('rule: ' + rp[0]);\n", ""), must_pass=['Q9 refuse bad-smart-with-songs:', 'Q9 refuse bad-smart-ids-text:', 'Q9 accept ok-8-conditions-numeric:'])
mut('V2-reader-allows-songs-with-rule', 'the strict reader accepts a smart playlist that also carries hand-picked ids', 9, 'Q9 refuse bad-smart-with-songs:',
    ("          if (Array.isArray(p.ids) && p.ids.length) add('a smart playlist (it has a rule) must have an empty ids list');\n", ""), must_pass=['Q9 refuse bad-smart-ids-text:', 'Q9 refuse bad-version-2:'])
mut('V3-export-drops-rule', 'the backup is written without the playlist rules', 9, ['Q9: the oracle\'s reading of the backup has the live playlists exactly', 'Q9: in the backup the smart playlists carry the rule and ids [] and the manual ones carry no rule key'],
    ("mk('data/playlists.json', jsonArrayBlob(snap.playlists))", "mk('data/playlists.json', jsonArrayBlob(snap.playlists.map(({ rule, ...p }) => p)))"))

# ---- manual compatibility (Q10)
mut('C1-add-menu-lists-smart', 'the "Add to playlist" menu also lists smart playlists', 10, 'Q10: the "Add to playlist" menu lists only the manual playlists',
    ("S.playlists.filter(p => !isSmart(p)).map(p => ({ label: p.name, icon: 'library', fn: () => addToPlaylist(p.id, tid) }));", "S.playlists.map(p => ({ label: p.name, icon: 'library', fn: () => addToPlaylist(p.id, tid) }));"), must_pass=['Q10: adding a song to a manual playlist from a smart list changes that manual record only'])
mut('C2-add-to-smart-allowed', 'addToPlaylist and plRemove can change a smart playlist\'s ids', 10, 'Q10: addToPlaylist and plRemove on a smart playlist do nothing',
    ("if (!pl || !t || isSmart(pl)) return;", "if (!pl || !t) return;"), must_pass=['Q10: a manual playlist still shows its songs'])
mut('C3-smart-menu-has-remove', 'songs in a smart playlist offer "Remove from this playlist"', 10, 'Q10: in a smart playlist the song menu has NO "Remove from this playlist"',
    ("ctx: 'sm:' + pl.id }", "ctx: 'pl:' + pl.id }"), must_pass=['Q10: in a manual playlist the song menu offers "Remove from this playlist"'])

# ---- accessibility (Q6)
mut('A1-remove-button-unnamed', 'the remove-condition buttons lose their accessible names', 6, ['Q6: each condition row is a labelled group', 'Q6: removing the middle condition renumbers the rest'],
    ('aria-label="Remove condition ${i + 1}"', 'aria-label=""'), must_pass=['Q6: every control in the editor has an accessible name'])
mut('A2-focus-lost-after-remove', 'removing a condition drops the keyboard focus', 6, ['Q6: removing the middle condition renumbers the rest', 'Q6: removing the last condition moves focus'],
    ("const nx = $$('.sp-rm', d)[Math.min(i, st.conds.length - 1)]; (nx || $('#spAdd', d)).focus(); update();", "update();"), must_pass=['Q6: each condition row is a labelled group'])
mut('A3-status-not-live', 'the live match count is not a live region', 6, 'Q6: the live status is a polite status region',
    ('<p class="sp-live" id="spStatus" role="status" aria-live="polite"></p>', '<p class="sp-live" id="spStatus"></p>'), must_pass=['Q6: the editor opens as a modal dialog labelled by its heading'])
mut('A4-dialog-unlabelled', 'the editor dialog loses its label', 6, 'Q6: the editor opens as a modal dialog labelled by its heading',
    (' novalidate aria-labelledby="spTitle">', ' novalidate>'), must_pass=['Q6: the live status is a polite status region'])
for b in BAD: print('ANCHOR MISMATCH', b)
if BAD: sys.exit(1)
json.dump(M, open(os.path.join(out, 'mutants.json'), 'w'), indent=1)
print(len(M), 'mutants written')
