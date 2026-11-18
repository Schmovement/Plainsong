#!/bin/bash
# Sequential regression matrix for ONE project directory (a workspace or a FRESH EXTRACT of a release zip).
#   usage: tests/run_matrix.sh <project-dir> <evidence-dir> <work-root>
#   env:   MATRIX="p2c p2b-adapted ..."  (default: all, in the order below)
# Serves <project-dir> on http://localhost:8765 (original p0/p1 hardcode that port), runs ONE suite at a time with its own WORK dir under <work-root>
# (each suite generates up to ~900 MB), copies the raw log/results/screenshots to <evidence-dir> FIRST, then deletes only that suite's generated WORK dir.
# The project tree is hashed before and after: a suite that modified the tree under test is reported, never hidden.
set -u
[ $# -eq 3 ] || { echo "usage: $0 <project-dir> <evidence-dir> <work-root>"; exit 2; }
P=$(cd "$1" && pwd) || exit 2; mkdir -p "$2" "$3" || exit 2; EV=$(cd "$2" && pwd); WR=$(cd "$3" && pwd)
case "$WR" in "$P"|"$P"/*|/|/home|/tmp) echo "refusing work-root $WR"; exit 2;; esac
case "$EV" in "$P"|"$P"/*) echo "evidence dir must be outside the project under test"; exit 2;; esac
PORT=8765; FX="$P/tests/fixtures-wav"; URL="http://localhost:$PORT/index.html"
MATRIX=${MATRIX:-"p2c p2b-adapted p2b-original p0-original p1-original p1-adapted p2a-original p2a-adapted"}
if curl -s -o /dev/null "http://localhost:$PORT/"; then echo "port $PORT already in use"; exit 2; fi
python3 -I -m http.server $PORT --directory "$P" >/dev/null 2>&1 & SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT
sleep 1; curl -sf "$URL" >/dev/null || { echo "server not up"; exit 2; }
( cd "$P" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > "$EV/tree-before.sha256"
( cd "$P" && sha256sum index.html style.css tests/*.js tests/*.py tests/original/*/*.js tests/original/*/*.py tests/run_matrix.sh ) > "$EV/executables-and-app.sha256"
{ echo "project: $P"; echo "served: $URL"; echo "start: $(date -u +%FT%TZ)"; echo "node: $(node --version) python: $(python3 --version 2>&1)"; } > "$EV/run-record.txt"
SUMMARY="$EV/matrix-summary.txt"; : > "$SUMMARY"
run() { # name, then the command (run from the project dir)
  local name=$1; shift; local w="$WR/$name" o="$EV/$name"; rm -rf "$w" "$o"; mkdir -p "$o"
  echo "== $name  $(date -u +%T)"; ( cd "$P" && timeout 3000 "$@" ) > "$o/run.log" 2>&1; local rc=$?
  local res; res=$(grep -E "^(PHASE|TOTAL) " "$o/run.log" | tail -n 1)
  { echo "$name | exit=$rc | $res"; grep -E "^(FAIL|✗)" "$o/run.log" | cut -c1-260 | sed 's/^/    /'; } | tee -a "$SUMMARY"
  [ -d "$w" ] && ls "$w"/*.png >/dev/null 2>&1 && { mkdir -p "$o/shots"; cp "$w"/*.png "$o/shots/"; }
  rm -rf "$w"
}
for m in $MATRIX; do case $m in
  p2c)          run p2c          env PS_URL=$URL node tests/phase2c.test.js "$FX" "$WR/p2c" "$EV/p2c/results.json" ;;
  p2b-adapted)  run p2b-adapted  env PS_URL=$URL node tests/phase2b.adapted.test.js "$FX" "$WR/p2b-adapted" "$EV/p2b-adapted/results.json" ;;
  p2b-original) run p2b-original env PS_URL=$URL node tests/original/p2b/phase2b.test.js "$FX" "$WR/p2b-original" "$EV/p2b-original/results.json" ;;
  p0-original)  run p0-original  node tests/phase0.test.js "$FX" "$EV/p0-original/results.json" ;;
  p1-original)  run p1-original  node tests/phase1.test.js "$FX" "$WR/p1-original" "$EV/p1-original/results.json" ;;
  p1-adapted)   run p1-adapted   node tests/phase1.adapted.test.js "$FX" "$WR/p1-adapted" "$EV/p1-adapted/results.json" ;;
  p2a-original) run p2a-original env PS_URL=$URL node tests/original/p2a/phase2a.test.js "$FX" "$WR/p2a-original" "$EV/p2a-original/results.json" ;;
  p2a-adapted)  run p2a-adapted  env PS_URL=$URL node tests/phase2a.adapted.test.js "$FX" "$WR/p2a-adapted" "$EV/p2a-adapted/results.json" ;;
  *) echo "unknown suite $m" | tee -a "$SUMMARY" ;;
esac; done
( cd "$P" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > "$EV/tree-after.sha256"
if cmp -s "$EV/tree-before.sha256" "$EV/tree-after.sha256"; then echo "project tree: UNCHANGED by the run" | tee -a "$SUMMARY"; else echo "project tree: CHANGED during the run (see diff)" | tee -a "$SUMMARY"; diff "$EV/tree-before.sha256" "$EV/tree-after.sha256" | tee -a "$SUMMARY"; fi
echo "end: $(date -u +%FT%TZ)" >> "$EV/run-record.txt"
