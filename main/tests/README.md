# Plainsong test harness

Dev-only files; the app itself has no build step and no dependencies. Needs Node, Playwright (npm), Chrome/Chromium, Python 3, `curl` and GNU `timeout` (coreutils), which the matrix and mutant runners call (plus `unzip`, optional).

## Layout (read this first: ORIGINAL versus ADAPTED)

| Path | What it is |
|------|-----------|
| `phase0.test.js`, `phase1.test.js`, `verify_backup.py` | **ORIGINAL**, byte-identical to the p2a/p2b checkpoints. Never edit these. |
| `original/p2a/` (`phase2a.test.js`, `make_bad_archives.py`, `extract_expected.py`, `fixtures/`) | **ORIGINAL** Phase 2A harness, generator and its own fixtures, byte-identical to the p2a checkpoint. Never edit. |
| `original/p2b/` (`phase2b.test.js`, `make_bad_archives.adapted.py`, `extract_expected.py`, `fixtures/`, `SHA256SUMS-ORIGINAL-p2b.txt`) | **ORIGINAL** Phase 2B suite exactly as delivered in `plainsong-checkpoint-p2b.zip`. Never edit. Against the p2c app it fails exactly one assertion (landing view), see below. |
| `phase1.adapted.test.js` | **ADAPTED** copy of `phase1.test.js`: exactly ONE assertion (the S1 backup-success-dialog copy) differs, because 2B removed the sentence "isn’t built yet" that the original requires. |
| `phase2a.adapted.test.js`, `make_bad_archives.adapted.py` | **ADAPTED/strengthened** 2A suite and generator (non-vacuous generator cases, pinned refusal reasons, hostile-text controls, the obsolete "no restore UI" assertion replaced). A modified harness, never called an unmodified rerun. |
| `phase2b.adapted.test.js` | **ADAPTED** copy of the original 2B suite: exactly ONE assertion differs (after a restore the app lands on the **library** view, not home) plus a marked header line. `diff original/p2b/phase2b.test.js phase2b.adapted.test.js` shows only that. |
| `phase2c.test.js` | **(2C)** real-UI round-trip harness, scenarios 0 to 6. |
| `phase3a.test.js` | **NEW (3A)** song-info editor suite, scenarios S0 to S8 (354 checks): real UI, raw IndexedDB snapshots with SHA-256 of blobs, write spy on the tracks store, injected failures, backup -> oracle -> restore -> re-export. `ONLY=1,3` selects scenarios. |
| `make_meta_archives.py` | **NEW (3A)** stdlib helper used by S8: re-seals CRC/manifest/payloadBytes of the p1 fixture with valid and malformed `genre`/`origMeta` fields. |
| `phase4.test.js` | **NEW (4)** five-star rating suite, scenarios R0 to R11 (469 checks in the last full run; R11 = speed-preset shadowing and stale-delete-after-restore guards): legacy library untouched (no eager rewrite), every rating 1..5 and clear through the real UI with raw IndexedDB snapshots, likes independent, keyboard and the ⋯ menu, sort both directions with tie-breaks checked against an independent expectation, filters/counts/empty states, invalid input and no-ops, held/rejected/removed/restored interleavings through the `GATE` write-ordering model, playback continuity, backup -> oracle -> restore -> re-export (old archives, present 0 versus absent), and 24 generated archives. `ONLY=4,5` selects scenarios; `PHASE 4: P / T pass` is its last line. |
| `make_rating_archives.py` | **NEW (4)** independent stdlib generator used by R10: re-seals CRC/manifest/payloadBytes of a real rated export with 6 accepted and 18 hostile `rating` variants (6, -1, 2.5, 0.5, 5.000001, "3", "five", null, true, false, [3], {}, 1e308, 9007199254740993, -0, on a web song, in a history snapshot, in a session web song) plus `cases.json`. |
| `phase5.test.js` | **NEW (5)** smart-playlist suite, scenarios Q0 to Q10 (320 checks in the last full run; the first complete run had 317, all names retained): nothing seeded or written eagerly and handleAct label lint (Q0); rule engine against an independent Node expectation, 200 generated combinations, validator and duration-parser tables (Q1); deterministic ordering, ties and limits (Q2); real-UI presets, `Duration > 5:00` combinations, edit / rename / delete / reload and write counts (Q3); invalid-input groups, maxlength, the 8-condition cap, API refusals (Q4); dynamic membership after like / rating / metadata / removal / real playback / import / restore / reload (Q5); accessibility, keyboard, focus, empty and damaged states, mobile screenshots (Q6); queue and playback continuity (Q7); write safety through the `GATEP` playlist-write gate: held, rejected, raced, stale, busy, epoch, double submit (Q8); backup -> independent oracle -> restore round trip, old p1 archives and generated rule archives (Q9); manual-playlist, menu and queue non-regression (Q10). Its results JSON records `complete`, `scenariosSelected/Finished/Aborted`; an aborted scenario writes an explicit ABORT row and exit 3. `ONLY=3,4` selects scenarios; `PHASE 5: P / T pass` is its last line. |
| `make_rule_archives.py` | **NEW (5)** independent stdlib generator used by Q9: re-seals CRC/manifest/payloadBytes of a real export with 9 accepted and about 58 hostile `rule` variants (wrong version, unknown field/operator, bad value ranges, 9 conditions, rule with hand-picked ids, ...); every refusal must change nothing, every accept must restore exactly. |
| `mutants_5.py`, `run_mutants_5.sh`, `mutant_verdict_5.py`, `test_mutant_verdict_5.py` | **NEW (5)** 43 mutants (one safeguard removed or an unsafe design restored, in a copy of `index.html` each) run by the strict classifier on its own port (8792): classifier controls first, one unmutated control per scenario (every needle must resolve to exactly one passing check), then every mutant; ERROR/INCOMPLETE is never a detection. |
| `classifier-control-data/` | **NEW (4, after candidate 1's rejection)** the REAL candidate-1 raw results/logs of the four aborted mutant runs (F8, F9, B3, B4) and the R5/R9 controls they were judged against, used by `test_mutant_verdict_4.py` as negative controls (historical, older lifecycle-less format; never regenerated). |
| `mutants_4.py`, `run_mutants_4.sh`, `mutant_verdict_4.py`, `test_mutant_verdict_4.py` | **NEW (4)** 41 mutants (one safeguard removed or an unsafe design restored, in a copy of `index.html` each) run one at a time by the runner against the scenario that must notice; classified from the full validated results JSON (exit 2 / 124 / >=128 or invalid JSON = ERROR, never a detection); 100 classifier controls and an unmutated control run per scenario come first (exact one-check needle identities, exactly one summary line, an ABORT row / lifecycle record / exit 3 / any difference between the mutant run's check names and the valid control's is ERROR, an invalid control aborts before any mutant). The runner can leave a Python bytecode cache `tests/__pycache__` in the tree under test (`python3 -I` ignores `PYTHONDONTWRITEBYTECODE`); account for it, do not ship it. |
| `phase3b.test.js` | **NEW (3B)** custom-cover suite, scenarios S0 to S11 (600 checks): real UI, raw IndexedDB snapshots with SHA-256 of blobs, write spy, a model of IndexedDB write ordering (`GATE`: one put held, real like/play/3A-save/cover-save/removal writers interleaved, then rejected or released), injected failures, pending-save UI, hostile pictures, legacy GIF/WebP/oversize originals, backup -> oracle + independent Python reader + browser decode -> restore -> re-export. `ONLY=9,10` selects scenarios. Its results JSON carries `complete:true` and `only`. |
| `cover_check_3b.py` | **NEW (3B)** independent stdlib reader of `data/tracks.json` in a backup: per cover/origCover kind, declared MIME vs magic MIME, SHA-256, width x height from headers, canonical base64 and `container_ok` (container FRAMING only, not a decoder). |
| `make_cover_archives.py` | **NEW (3B)** stdlib helper used by S8: re-seals the p1 fixture with 19 `origCover`/`cover` cases (8 valid incl. GIF, WebP and a real >700,000-character PNG, 11 malformed). |
| `mutants_3b.py`, `run_mutants_3b.sh`, `mutant_verdict.py`, `test_mutant_verdict.py` | **NEW (3B)** 24 mutants (one safeguard removed or the earlier unsafe design restored, in a copy of `index.html` each; the runner can leave a Python bytecode cache `tests/__pycache__/` in the tree under test, which is not part of the release). The runner runs in the foreground on :8792, first runs the classifier's 26 negative/positive controls and one control run of the UNMUTATED app per scenario, then every mutant; a mutant is DETECTED only from a valid, complete, validated results JSON whose FAILED check names the intended safeguard; timeout/crash/signal/missing or inconsistent JSON is ERROR/INCOMPLETE, never a detection. |
| `mutants_3a.py`, `run_mutants_3a.sh` | **NEW (3A)** 9 mutants (one safeguard removed in a copy of `index.html` each); the runner serves a copy on :8791 and records which scenario fails. |
| `oracle_2c.py` | **NEW (2C)** the independent oracle: Python `zipfile`/`zlib`/`json`/`hashlib` only, no app code. `truth <zip> <out>` and `compare <A> <B> <out> [--b-theme light\|dark\|none] [--b-secret-keys 'k1\|k2'] [--time-unavailable]`. Exit: compare 0 = no failures, 1 = failures, 2 = oracle error. |
| `oracle_2c_controls.py` | **NEW (2C)** generates 42 altered archives plus `cases.json` (what each must make the oracle do). Run by scenario 0 itself. |
| `run_matrix.sh` | **NEW (2C)** runs the whole matrix sequentially for one project directory (a workspace or a fresh extract) and writes raw evidence outside it. |
| `extract_expected.py`, `negative_controls.py`, `make-fixtures.py`, `make_bad_archives.adapted.py` | Independent ground truth and generators carried from p2a/p2b. |
| `fixtures/` | Two p1-exporter archives (full six-track library with binary data; one-song minimal) + expected JSON. **Immutable.** |
| `fixtures-wav/` | Three 12 s WAV tones (the `<fixtures-dir>` argument of the suites). **Immutable.** |
| `evidence-p4/` | **CURRENT proof (4):** `candidate2/` (candidate 2: the full suite and the strict 41-mutant run on the final bytes, the focused repair runs, STATUS.txt) and `candidate1-REJECTED/` (candidate 1's evidence, kept as history, NOT proof of the current build; below, its former layout: `suite-run9/` the 469/469 suite, `matrix/` the 11-suite matrix with tree before/after and executables hashes, `mutants41/` the strict 41-mutant run, `history/` earlier states kept honestly: the speed-preset and stale-delete reproductions and R11 before/after, the first 31 DETECTED / 5 ERROR / 2 not-as-intended mutation run, the focused re-run of 8, the superseded six-failure matrix attempt, classifier controls). Generated export/mutant ZIPs are omitted and listed by hash in `OMITTED-*.txt`. The exact-final fresh-extract run is in the separate FINAL-EXTRACT-VERIFICATION-p4 text and its raw-proof archives. |
| `evidence-p3b/` | **CURRENT proof (3B):** `candidate-final3/` (the full 10-suite matrix and the 24-mutant run on the final3 bytes, raw logs and results JSON; generated export ZIPs omitted and hash-listed), `targeted-S10-probe-3x3/` (3 real-app and 3 E2b runs of the new S10 probes) and `before-final2-E2b-official-miss/` (the official final2 E2b miss and 6 supplemental misses, kept unchanged). EARLIER proof on the previous test bytes (596 checks, superseded for the counts): `candidate-matrix/` (the full 10-suite candidate run with exports and every oracle truth/compare JSON; NOT inside the p4 ZIP, which would exceed 30 MiB: it stays inside plainsong-checkpoint-p3b-final3.zip and is listed by hash in `OMITTED-candidate-matrix-SHA256.txt`), `mutants/` (the complete 24-mutant run: control runs, per-mutant logs and results JSON, summary; the generated mutant app copies and export ZIPs are NOT inside this ZIP: they are preserved externally and listed by hash where omitted, see `OMITTED-generated-exports-SHA256.txt` and `README-evidence.txt`), `repro-and-fixes/` (S9-S11 on the UNFIXED bytes 113/125, after the fix 125/125, and the repeated S10 runs that exposed the Escape-guard bug), `README-evidence.txt`. |
| `evidence-p3a/` | **CURRENT proof (3A):** `candidate-3a-full-run/` (the one full 3A run, 354/354, with the real-UI exports and every oracle truth/compare JSON), `candidate-regressions/` (the 8 regression suites on the p3a tree, sequential, with hash records and tree before/after), `mutants/` (9 mutant logs + summary), `earlier-partial-3a-runs/` (superseded partial logs, incl. the two real failures found and fixed), `interrupted-matrix-start/` (an interrupted run, INCOMPLETE, not a result). |
| `evidence-p2c/` | Historical p2 proof (p2c candidate run). Large generated parts were omitted from the p3a ZIP; their hashes are in `OMITTED-*-SHA256.txt` and the originals are in the verified p2 ZIP. Not current proof. |
| `evidence-p2b/`, `evidence-history/` | Evidence as delivered with p2b and earlier phases. Historical; not the p2c results. |

## Running (sequentially; each run builds up to ~900 MB under its WORK dir; delete it afterwards)

Whole matrix (what the release was verified with):

```
bash tests/run_matrix.sh <project-dir> <evidence-dir> <work-root>     # serves <project-dir> on :8765; MATRIX="p5 p4 p3b ..." selects suites; default now starts with p5 (12 suites)
```

Single suites (`phase0`/`phase1` hardcode `localhost:8765`; the others honour `PS_URL`):

```
PS_URL=http://localhost:8765/index.html node tests/phase3a.test.js tests/fixtures-wav <work-dir> <results.json>                # 3A: 354 checks; ONLY=0,1.. selects scenarios
bash tests/run_mutants_3a.sh <project-dir> <evidence-dir> <work-root>        # 9 mutants; each must make its intended check FAIL (see the script header)
PS_URL=http://localhost:8765/index.html node tests/phase5.test.js tests/fixtures-wav <work-dir> <results.json>                # 5: smart playlists, ONLY=0..10 selects scenarios
bash tests/run_mutants_5.sh <project-dir> <evidence-dir> <work-root>         # 43 mutants (about 20 minutes; run detached with setsid nohup and poll); exit 0 only if every control passed and every mutant is DETECTED
PS_URL=http://localhost:8765/index.html node tests/phase4.test.js tests/fixtures-wav <work-dir> <results.json>                # 4: ratings, ONLY=0..10 selects scenarios
bash tests/run_mutants_4.sh <project-dir> <evidence-dir> <work-root>         # 41 mutants in the FOREGROUND (about 25 minutes); exit 0 only if every control passed and every mutant is DETECTED
PS_URL=http://localhost:8765/index.html node tests/phase3b.test.js tests/fixtures-wav <work-dir> <results.json>                # 3B: 600 checks; ONLY=9,10 selects scenarios
bash tests/run_mutants_3b.sh <project-dir> <evidence-dir> <work-root>        # 24 mutants in the FOREGROUND (about 15 minutes); exit 0 only if every control passed and every mutant is DETECTED
```

```
python3 -I -m http.server 8765 --directory <project-dir> &
node tests/phase0.test.js tests/fixtures-wav <results.json>                                                    # ORIGINAL: 38 checks
node tests/phase1.test.js tests/fixtures-wav <work-dir> <results.json>                                         # ORIGINAL: 225 checks (224 pass, see below)
node tests/phase1.adapted.test.js tests/fixtures-wav <work-dir> <results.json>                                 # ADAPTED: 225 checks
PS_URL=http://localhost:8765/index.html node tests/original/p2a/phase2a.test.js tests/fixtures-wav <work-dir> <results.json>   # ORIGINAL: 216 (215 pass)
PS_URL=http://localhost:8765/index.html node tests/phase2a.adapted.test.js tests/fixtures-wav <work-dir> <results.json>        # ADAPTED: 217
PS_URL=http://localhost:8765/index.html node tests/original/p2b/phase2b.test.js tests/fixtures-wav <work-dir> <results.json>  # ORIGINAL: 189 (188 pass)
PS_URL=http://localhost:8765/index.html node tests/phase2b.adapted.test.js tests/fixtures-wav <work-dir> <results.json>        # ADAPTED: 189; ONLY=1,9 runs just those sections
PS_URL=http://localhost:8765/index.html node tests/phase2c.test.js tests/fixtures-wav <work-dir> <results.json>                # 2C: 510 checks; ONLY=0,1.. selects scenarios
python3 -I tests/negative_controls.py <good.zip> <good.expected.json> <work-dir>   # verifier must reject 10 damaged archives
python3 -I tests/verify_backup.py <backup.zip> <expected.json> [--incomplete] [--ignore-kv a,b]
```

Do not run two suites at once and do not run many in parallel: each generates its own archives (including a 64 MiB one) and a full disk kills the test server. The 2C suite refuses to delete anything that is not an empty, absent or marker-owned generated directory (see safe-delete controls) and moves earlier evidence aside instead of deleting it.

## Results against the p4 build (workspace runs; details in `evidence-p4/` and the ledger; the exact-final fresh-extract run of candidate 2, including the 11-suite matrix, is in the separate FINAL-EXTRACT-VERIFICATION-p4-c2.txt)

Provenance of this table: the Phase 4 suite row and the mutation row are from the CANDIDATE-2 tool/harness bytes (workspace). The other ten suite rows are from candidate 1's matrix (`evidence-p4/candidate1-REJECTED/matrix/`); the code of those ten suites is byte-identical in candidate 2, and the candidate-2 matrix is re-run in the fresh-extract verification, which is the authority.

| Suite | Result |
|-------|--------|
| 4 (`phase4.test.js`) | 469 / 469 |
| 3B (`phase3b.test.js`) | 600 / 600 |
| 3A (`phase3a.test.js`) | 354 / 354 |
| 2C (`phase2c.test.js`) | 510 / 510 |
| 2B ADAPTED | 189 / 189 |
| 2B ORIGINAL | **188 / 189**: "rebuilt app state: … home view" (obsolete by design, kept) |
| ORIGINAL p0 | 38 / 38 |
| ORIGINAL p1 | **224 / 225**: "S1 success dialog states restore is not built yet and shows counts" (obsolete copy, kept) |
| ADAPTED p1 | 225 / 225 |
| ORIGINAL 2A | **215 / 216**: "app boots without restore UI wired (no restore button/input exists yet)" (obsolete by design, kept) |
| ADAPTED 2A | 217 / 217 |
| 4 mutants (`run_mutants_4.sh`) | 41 / 41 DETECTED, 0 survivors, 0 ERROR (12 control runs of the unmutated app valid; classifier controls 100 / 100 (the candidate-1 run reported 41/41 but four runs were aborted scenarios; see the ledger). Earlier history kept in `evidence-p4/candidate1-REJECTED/history/`: the first run with the older tools was 31 DETECTED / 5 ERROR / 2 not as intended. |

## Results against the p3b build (candidate run on the final bytes: workspace, one suite at a time; details in `evidence-p3b/` and the ledger; the exact-final fresh-extract run is in the separate FINAL-EXTRACT-VERIFICATION-p3b.txt)

| Suite | Result |
|-------|--------|
| 3B (`phase3b.test.js`) | 600 / 600 |
| 3A (`phase3a.test.js`) | 354 / 354 |
| 2C (`phase2c.test.js`) | 510 / 510 |
| 2B ADAPTED | 189 / 189 |
| 2B ORIGINAL | **188 / 189**: "rebuilt app state: … home view" (the app lands on the library view, on purpose) |
| ORIGINAL p0 | 38 / 38 |
| ORIGINAL p1 | **224 / 225**: "S1 success dialog states restore is not built yet…" (obsolete copy) |
| ADAPTED p1 | 225 / 225 |
| ORIGINAL 2A | **215 / 216**: "app boots without restore UI wired…" (obsolete by design) |
| ADAPTED 2A | 217 / 217 |
| 3B mutants (`run_mutants_3b.sh`) | 24 / 24 DETECTED in the candidate run on these bytes (runner controls 26 / 26; 8 control runs of the unmutated app valid). Caveat: with the earlier test bytes (596 checks) the official fresh-extract run of final2 was 23 / 24 (E2b); S10's native focus/Escape check does not reliably tell a window-capture Escape guard from a dialog-only one, so E2b is now caught by a SUPPLEMENTARY synthetic body-target Escape probe (a dispatched KeyboardEvent, not native keyboard coverage). |

## Results against the p3a build (historical) (candidate run: workspace, one suite at a time; details in `evidence-p3a/` and the ledger; the fresh-extract run is in the separate FINAL-EXTRACT-VERIFICATION-p3a.txt)

| Suite | Result |
|-------|--------|
| 3A (`phase3a.test.js`) | 354 / 354 |
| 2C (`phase2c.test.js`) | 510 / 510 |
| 2B ADAPTED | 189 / 189 |
| 2B ORIGINAL | **188 / 189**: "rebuilt app state: … home view" (the app now lands on the library view, on purpose) |
| ORIGINAL p0 | 38 / 38 |
| ORIGINAL p1 | **224 / 225**: "S1 success dialog states restore is not built yet…" (obsolete copy) |
| ADAPTED p1 | 225 / 225 |
| ORIGINAL 2A | **215 / 216**: "app boots without restore UI wired…" (obsolete by design) |
| ADAPTED 2A | 217 / 217 |

The final-extract verification of the released ZIP is a separate text file delivered beside it (it cannot be inside the ZIP it verifies).

## Notes

- `oracle_2c.py` and `verify_backup.py` share no code with the app. Browser tests block all non-localhost network; every blocked request is recorded. Expected state is captured straight from IndexedDB by the harness, not by the app's backup code.
- The 2C suite's controls: 42 altered archives the oracle must reject or accept only with an exact allowance (including a `secret:` key in either file, large and small `session.time` jumps, manifest duplicates/reordering/extra keys/wrong counts, theme and warning rules, a flipped audio bit), a stale report, a signal-killed oracle, a timed-out oracle, and the safe-delete refusals.
- Phase 2A/2B pages are instrumented before load (`SPY`): every readwrite transaction, `put/add/delete/clear`, cursor `update/delete`, `Storage` write and database open/delete is counted. In 2B the app's own four-store transaction is also wrapped (`INJECT`) to inject failures; independent snapshots (`snap`, with SHA-256 of every audio blob) prove rollback.
- Chrome is launched with `--autoplay-policy=no-user-gesture-required` so that an autoplay bug would actually play (`HTMLMediaElement.prototype.play` is counted).
- File chooser: the page-creation listener queues every `filechooser`; the test triggers once, never repeats, and records a missing chooser as a failure.
- 2B section 12 mutation checks used separate copies of `index.html` with one safeguard removed (logs in `evidence-p2b/supporting-workspace-runs/mutants/`). 2A mutation results are in `evidence-history/phase2a-mutation-results.txt`. No mutation checks exist for the 2B rollback tests or for the 2C oracle beyond its 42 controls.
- 3A mutation checks: 9 mutants, all detected (`evidence-p3a/mutants/mutants-summary.txt`); M3's run exits 2 after the intended failures (the 3A runner is the old one: it slices names and does not validate JSON; the 3B runner replaced that design and the 3A mutants were not re-run with it).
- 3B mutation checks: the first 3B runner cut failing names to 125 characters before matching the needle (3 mutants were recorded as "not noticed" although their checks had failed) and counted a crashed run as a detection candidate. It was replaced by the validated-JSON classifier described above, with its own negative controls; the 24-mutant result is `evidence-p3b/mutants/`.
- Repeat flaky-looking checks: a pending-save Escape check that passed once failed in 2 of 3 repeats and exposed a real app bug (see the ledger); S10 was then run 9 times in a row (`evidence-p3b/repro-and-fixes/`).
- Not covered anywhere: IME/screen-reader editing, browsers other than desktop Chromium, a real OS file dialog, a real quota failure, other open tabs, a backup file changing on disk during a restore, libraries near the 2 GiB limit.
