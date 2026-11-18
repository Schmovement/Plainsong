# Plainsong test harness

Dev-only files; the app itself has no build step and no dependencies. Needs Node, Playwright (npm), Chrome/Chromium, Python 3 (plus `unzip`, optional).

## Layout (read this first: ORIGINAL versus ADAPTED)

| Path | What it is |
|------|-----------|
| `phase0.test.js`, `phase1.test.js`, `verify_backup.py` | **ORIGINAL**, byte-identical to the p2a/p2b checkpoints. Never edit these. |
| `original/p2a/` (`phase2a.test.js`, `make_bad_archives.py`, `extract_expected.py`, `fixtures/`) | **ORIGINAL** Phase 2A harness, generator and its own fixtures, byte-identical to the p2a checkpoint. Never edit. |
| `original/p2b/` (`phase2b.test.js`, `make_bad_archives.adapted.py`, `extract_expected.py`, `fixtures/`, `SHA256SUMS-ORIGINAL-p2b.txt`) | **ORIGINAL** Phase 2B suite exactly as delivered in `plainsong-checkpoint-p2b.zip`. Never edit. Against the p2c app it fails exactly one assertion (landing view), see below. |
| `phase1.adapted.test.js` | **ADAPTED** copy of `phase1.test.js`: exactly ONE assertion (the S1 backup-success-dialog copy) differs, because 2B removed the sentence "isn’t built yet" that the original requires. |
| `phase2a.adapted.test.js`, `make_bad_archives.adapted.py` | **ADAPTED/strengthened** 2A suite and generator (non-vacuous generator cases, pinned refusal reasons, hostile-text controls, the obsolete "no restore UI" assertion replaced). A modified harness, never called an unmodified rerun. |
| `phase2b.adapted.test.js` | **ADAPTED** copy of the original 2B suite: exactly ONE assertion differs (after a restore the app lands on the **library** view, not home) plus a marked header line. `diff original/p2b/phase2b.test.js phase2b.adapted.test.js` shows only that. |
| `phase2c.test.js` | **NEW (2C)** real-UI round-trip harness, scenarios 0 to 6. |
| `oracle_2c.py` | **NEW (2C)** the independent oracle: Python `zipfile`/`zlib`/`json`/`hashlib` only, no app code. `truth <zip> <out>` and `compare <A> <B> <out> [--b-theme light\|dark\|none] [--b-secret-keys 'k1\|k2'] [--time-unavailable]`. Exit: compare 0 = no failures, 1 = failures, 2 = oracle error. |
| `oracle_2c_controls.py` | **NEW (2C)** generates 42 altered archives plus `cases.json` (what each must make the oracle do). Run by scenario 0 itself. |
| `run_matrix.sh` | **NEW (2C)** runs the whole matrix sequentially for one project directory (a workspace or a fresh extract) and writes raw evidence outside it. |
| `extract_expected.py`, `negative_controls.py`, `make-fixtures.py`, `make_bad_archives.adapted.py` | Independent ground truth and generators carried from p2a/p2b. |
| `fixtures/` | Two p1-exporter archives (full six-track library with binary data; one-song minimal) + expected JSON. **Immutable.** |
| `fixtures-wav/` | Three 12 s WAV tones (the `<fixtures-dir>` argument of the suites). **Immutable.** |
| `evidence-p2c/` | Raw evidence of the p2c candidate run (every suite's log and results JSON, the 2C round-trip exports E1 to E4 and every oracle `truth`/`compare` JSON, hash records). |
| `evidence-p2b/`, `evidence-history/` | Evidence as delivered with p2b and earlier phases. Historical; not the p2c results. |

## Running (sequentially; each run builds up to ~900 MB under its WORK dir; delete it afterwards)

Whole matrix (what the release was verified with):

```
bash tests/run_matrix.sh <project-dir> <evidence-dir> <work-root>     # serves <project-dir> on :8765; MATRIX="p2c p2b-adapted ..." selects suites
```

Single suites (`phase0`/`phase1` hardcode `localhost:8765`; the others honour `PS_URL`):

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

## Results against the p2c build (candidate run: workspace, one suite at a time; details in `evidence-p2c/` and the ledger)

| Suite | Result |
|-------|--------|
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
- Not covered anywhere: browsers other than desktop Chromium, a real OS file dialog, a real quota failure, other open tabs, a backup file changing on disk during a restore, libraries near the 2 GiB limit.
