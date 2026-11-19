tests/evidence-p2c  (Phase 2C raw evidence)
candidate-run/   ONE sequential run of all 8 suites by tests/run_matrix.sh against the workspace tree that became this release
                 (served on :8765). Per suite: run.log, results.json (+ shots/). p2c/roundtrip-evidence/ holds the real-UI exports E1-E4 (and S2..S6
                 first/second exports) with every oracle truth/compare JSON. matrix-summary.txt = one line per suite plus every failing check name.
                 executables-and-app.sha256 = hashes of the app + every test executable that ran; tree-before/after.sha256 = whole-tree hashes
                 (identical: no suite modified the project).
defect-before-fix/   the 492/493 run on the Home-landing build: its only failure was the network request during the restore flow.
OMITTED-superseded-history-SHA256.txt   hashes of earlier/duplicate generated runs (intermediate harness versions, a stale 107/115 run, earlier copies of
                 the same round-trip exports) that were kept in the session scratchpad but NOT packaged, to stay under the 30 MiB upload limit.
The final-extract verification of the released ZIP is a separate text file (it cannot live inside the ZIP it verifies).

p3a NOTE: the candidate-run export ZIPs and screenshots were removed from THIS copy (hashes in OMITTED-candidate-run-binaries-SHA256.txt; originals in the verified p2 ZIP). This directory is historical p2 proof, not p3a proof; the current proof is tests/evidence-p3a/.
