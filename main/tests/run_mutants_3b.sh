#!/bin/bash
# usage: tests/run_mutants_3b.sh <project-dir> <evidence-dir> <work-root>     (one mutant at a time, in the FOREGROUND; own port 8792; deletes only its own work dirs)
# 1. the classifier's own negative controls must pass (tests/test_mutant_verdict.py), 2. for every scenario the UNMUTATED app is run once and must pass completely and every needle must match a PASSING
# check, 3. every mutant is run and classified by tests/mutant_verdict.py from the FULL, validated results JSON: DETECTED / SURVIVED / SURVIVED-OTHER / ERROR. A mutant whose run timed out, crashed, was
# killed, or left no valid complete JSON is ERROR, never a detection, even if its partial log shows the intended FAIL.
# exit: 0 only if every control passed and every mutant is DETECTED; 1 if some mutant survived; 3 if any control or mutant run is ERROR/INCOMPLETE.
set -u
P=$(cd "$1" && pwd); mkdir -p "$2" "$3"; EV=$(cd "$2" && pwd); WR=$(cd "$3" && pwd); PORT=8792; SRV=
trap '[ -n "$SRV" ] && kill $SRV 2>/dev/null' EXIT
SUM="$EV/mutants-summary.txt"; : > "$SUM"
echo "== runner controls (classifier negative/positive controls)" | tee -a "$SUM"
python3 -I "$P/tests/test_mutant_verdict.py" > "$EV/runner-controls.log" 2>&1; rc=$?; tail -1 "$EV/runner-controls.log" | tee -a "$SUM"
[ $rc -eq 0 ] || { echo "runner controls FAILED: no verdict can be trusted" | tee -a "$SUM"; exit 3; }
rm -rf "$WR/mut"; python3 -I "$P/tests/mutants_3b.py" "$P" "$WR/mut" || exit 2
MJ="$WR/mut/mutants.json"
serve() { python3 -I -m http.server $PORT --directory "$1" >/dev/null 2>&1 & SRV=$!; sleep 1; }
stop() { kill $SRV 2>/dev/null; wait $SRV 2>/dev/null; SRV=; }
runscn() { # <scenario> <served-dir> <log> <json>   -> sets RC
  rm -f "$4"; rm -rf "$WR/mw"; serve "$2"
  (cd "$P" && ONLY=$1 PS_URL=http://localhost:$PORT/index.html timeout 900 node tests/phase3b.test.js tests/fixtures-wav "$WR/mw" "$4" > "$3" 2>&1); RC=$?
  stop; rm -rf "$WR/mw"; }
echo "== controls on the UNMUTATED app (one per scenario used by a mutant)" | tee -a "$SUM"; CTL_BAD=0
for scn in $(python3 -I -c "import json;print(' '.join(sorted({str(m['scenario']) for m in json.load(open('$MJ'))},key=int)))"); do
  runscn $scn "$P" "$EV/control-S$scn.log" "$EV/control-S$scn.json"
  python3 -I "$P/tests/mutant_verdict.py" control "$MJ" $scn "$EV/control-S$scn.log" "$EV/control-S$scn.json" $RC | tee -a "$SUM" || CTL_BAD=$((CTL_BAD+1))
done
[ $CTL_BAD -eq 0 ] || { echo "$CTL_BAD control run(s) invalid: mutant verdicts below are NOT trustworthy" | tee -a "$SUM"; }
echo "== mutants" | tee -a "$SUM"; DET=0; SURV=0; ERR=0
for id in $(python3 -I -c "import json;print(' '.join(m['id'] for m in json.load(open('$MJ'))))"); do
  scn=$(python3 -I -c "import json;print([m for m in json.load(open('$MJ')) if m['id']=='$id'][0]['scenario'])")
  runscn $scn "$WR/mut/$id" "$EV/$id.log" "$EV/$id.json"
  python3 -I "$P/tests/mutant_verdict.py" verdict "$MJ" $id "$EV/$id.log" "$EV/$id.json" $RC | tee -a "$SUM"; v=${PIPESTATUS[0]}
  case $v in 0) DET=$((DET+1));; 1) SURV=$((SURV+1));; *) ERR=$((ERR+1));; esac
done
TOTAL=$((DET+SURV+ERR)); echo "TOTAL: $TOTAL mutants | DETECTED (valid, complete, intended check failed): $DET | SURVIVED or intended check not failed: $SURV | ERROR/INCOMPLETE: $ERR | control runs invalid: $CTL_BAD" | tee -a "$SUM"
[ $ERR -eq 0 ] && [ $CTL_BAD -eq 0 ] || exit 3
[ $SURV -eq 0 ] || exit 1
exit 0
