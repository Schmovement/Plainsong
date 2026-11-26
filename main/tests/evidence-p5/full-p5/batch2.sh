#!/bin/bash
# one detached batch: (1) full repaired P5 on the frozen harness, (2) ONE unified 43-mutant run. New paths only.
cd /home/claude/p5
W=/home/claude/w5
{ date '+start %F %T %z'; sha256sum index.html style.css tests/phase5.test.js tests/mutants_5.py tests/make_rule_archives.py tests/mutant_verdict_5.py tests/run_mutants_5.sh tests/test_mutant_verdict_5.py; } > $W/frozen-identities-run2.txt
setsid python3 -I -m http.server 8765 --directory /home/claude/p5 > $W/server-8765-run2.log 2>&1 < /dev/null &
SRV=$!
sleep 2
PS_URL=http://localhost:8765/index.html node tests/phase5.test.js tests/fixtures-wav $W/work-full2 $W/res-full2.json > $W/run-full2.log 2>&1; echo "full-p5 exit $?" >> $W/run-full2.log
kill $SRV 2>/dev/null
bash tests/run_mutants_5.sh /home/claude/p5 $W/mut-ev-all43 $W/mut-work-all43 > $W/run-mut-all43.log 2>&1; echo "all43 exit $?" >> $W/run-mut-all43.log
{ date '+end %F %T %z'; sha256sum index.html style.css tests/phase5.test.js tests/mutants_5.py tests/make_rule_archives.py tests/mutant_verdict_5.py tests/run_mutants_5.sh; } > $W/frozen-identities-run2-after.txt
