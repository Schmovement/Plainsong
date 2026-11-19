tests/evidence-p3a  (Phase 3A raw evidence; CURRENT proof for the p3a build)
candidate-3a-full-run/     ONE full run of tests/phase3a.test.js (S0-S8) on the final app bytes: PHASE 3A 354 / 354 (run.log, results.json). roundtrip-evidence/ has the real-UI exports
                           (two kept, the rest in OMITTED-generated-binaries-SHA256.txt) and EVERY oracle truth/compare JSON.
candidate-regressions/     the 8 regression suites (2C, 2B adapted/original, p0, p1 original/adapted, 2A original/adapted), sequential via tests/run_matrix.sh on the same tree:
                           matrix-summary.txt (one line per suite + failing check names), run.log/results.json per suite, tree-before/after.sha256 (identical), executables-and-app.sha256, run-record.txt.
mutants/                   9 mutant runs (logs, results JSON) and mutants-summary.txt.
earlier-partial-3a-runs/   superseded partial 3A logs (they contain the real failures found and fixed during development).
interrupted-matrix-start/  a candidate-matrix run that was interrupted during 2C: INCOMPLETE, NOT a result.
OMITTED-generated-binaries-SHA256.txt  hashes of export ZIPs left out to keep the ZIP under 30 MiB.
The fresh-extract verification of the released ZIP is a separate text file (a ZIP cannot contain its own hash).
