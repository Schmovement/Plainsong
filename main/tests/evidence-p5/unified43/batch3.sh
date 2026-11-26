#!/bin/bash
# ONE unified 43-mutant run on the frozen current harness/catalog, NEW paths; before/after identities of all 8 files.
cd /home/claude/p5; W=/home/claude/w5
IDS="index.html style.css tests/phase5.test.js tests/mutants_5.py tests/make_rule_archives.py tests/mutant_verdict_5.py tests/run_mutants_5.sh tests/test_mutant_verdict_5.py"
{ date '+start %F %T %z'; uptime -s | sed 's/^/boot /'; sha256sum $IDS; } > $W/frozen-identities-all43b-before.txt
bash tests/run_mutants_5.sh /home/claude/p5 $W/mut-ev-all43b $W/mut-work-all43b > $W/run-mut-all43b.log 2>&1; echo "all43b exit $?" >> $W/run-mut-all43b.log
{ date '+end %F %T %z'; sha256sum $IDS; } > $W/frozen-identities-all43b-after.txt
