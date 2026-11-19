#!/bin/bash
# usage: tests/run_mutants_3a.sh <project-dir> <evidence-dir> <work-root>     (one mutant at a time; own port 8791; deletes only its own work dirs)
set -u
P=$(cd "$1" && pwd); mkdir -p "$2" "$3"; EV=$(cd "$2" && pwd); WR=$(cd "$3" && pwd); PORT=8791
rm -rf "$WR/mut"; python3 -I "$P/tests/mutants_3a.py" "$P" "$WR/mut" || exit 2
: > "$EV/mutants-summary.txt"
for id in $(python3 -I -c "import json;print(' '.join(m['id'] for m in json.load(open('$WR/mut/mutants.json'))))"); do
  scn=$(python3 -I -c "import json;print([m for m in json.load(open('$WR/mut/mutants.json')) if m['id']=='$id'][0]['scenario'])")
  python3 -I -m http.server $PORT --directory "$WR/mut/$id" >/dev/null 2>&1 & SRV=$!; sleep 1
  rm -rf "$WR/mw"; (cd "$P" && ONLY=$scn PS_URL=http://localhost:$PORT/index.html timeout 900 node tests/phase3a.test.js tests/fixtures-wav "$WR/mw" "$EV/$id.json" > "$EV/$id.log" 2>&1); rc=$?
  kill $SRV 2>/dev/null; rm -rf "$WR/mw"
  python3 -I - "$WR/mut/mutants.json" "$id" "$EV/$id.log" "$rc" >> "$EV/mutants-summary.txt" <<'PY'
import sys, json
m = [x for x in json.load(open(sys.argv[1])) if x['id'] == sys.argv[2]][0]; log = open(sys.argv[3], encoding='utf-8', errors='replace').read().split('\n')
fails = [l[5:130] for l in log if l.startswith('FAIL ')]
hit = any(m['needle'] in l for l in fails)
print(f"{m['id']}: scenario S{m['scenario']} exit={sys.argv[4]} failing checks={len(fails)} intended check failed={'YES' if hit else 'NO  <-- the test did not notice this mutant'}  | {m['desc']}")
for l in fails[:4]: print('     ', l)
PY
done
cat "$EV/mutants-summary.txt"
