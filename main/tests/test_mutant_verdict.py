#!/usr/bin/env python3
"""Negative and positive controls for the mutation runner's classifier (tests/mutant_verdict.py). Prints PASS/FAIL per control; exit 0 only if all pass.
The runner executes this BEFORE any mutant: if it fails, no mutant verdict is trusted."""
import os, sys, json, tempfile, importlib.util
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('mv', os.path.join(here, 'mutant_verdict.py')); mv = importlib.util.module_from_spec(spec); spec.loader.exec_module(mv)
M = {'id': 'X', 'scenario': 10, 'needle': 'do NOTHING while saving', 'desc': 'd'}
LONG = 'S10 reject: Escape (twice), a click on Cancel, on Revert and on Choose image, and choosing another file do NOTHING while saving: the dialog stays open'
assert LONG.index(M['needle']) + len(M['needle']) > 125   # the old runner cut names at 125 characters: this needle is cut off there
def run(results=None, exit_code=1, only='10', log=None, raw=None, mutate=None, write=True, mutant=M):
    d = tempfile.mkdtemp(); js = os.path.join(d, 'r.json')
    if results is None: results = [{'name': 'a', 'ok': True}, {'name': LONG, 'ok': False}, {'name': 'b', 'ok': False}]
    doc = {'complete': True, 'only': only, 'total': len(results), 'failed': sum(1 for r in results if not r['ok']), 'results': results}
    if mutate: mutate(doc)
    if write: open(js, 'w').write(raw if raw is not None else json.dumps(doc))
    if log is None: log = f"FAIL {LONG[:100]}\nPHASE 3B: {doc['total'] - doc['failed']} / {doc['total']} pass\n"
    return mv.verdict(mutant, exit_code, log, js)[0]
ok_res = [{'name': 'a', 'ok': True}, {'name': 'b', 'ok': True}]
cases = [
 ('valid, exit 1, intended check failed (name longer than 125 chars, needle beyond the old cut) -> DETECTED', lambda: run() == 'DETECTED'),
 ('valid, exit 1, only OTHER checks failed -> SURVIVED-OTHER (not a detection)', lambda: run(results=[{'name': 'a', 'ok': True}, {'name': 'zzz', 'ok': False}]) == 'SURVIVED-OTHER'),
 ('valid, exit 0, nothing failed -> SURVIVED', lambda: run(results=ok_res, exit_code=0, log='PHASE 3B: 2 / 2 pass\n') == 'SURVIVED'),
 ('NEGATIVE: partial log shows the intended FAIL, no JSON, exit 2 (uncaught crash) -> ERROR', lambda: run(exit_code=2, write=False) == 'ERROR'),
 ('NEGATIVE: partial log shows the intended FAIL, no JSON, exit 124 (timeout) -> ERROR', lambda: run(exit_code=124, write=False) == 'ERROR'),
 ('NEGATIVE: complete-looking JSON but exit 124 (timeout) -> ERROR', lambda: run(exit_code=124) == 'ERROR'),
 ('NEGATIVE: complete-looking JSON but exit 137 (killed) -> ERROR', lambda: run(exit_code=137) == 'ERROR'),
 ('NEGATIVE: complete-looking JSON but exit 2 -> ERROR', lambda: run(exit_code=2) == 'ERROR'),
 ('NEGATIVE: exit code not a number -> ERROR', lambda: run(exit_code='') == 'ERROR'),
 ('NEGATIVE: JSON truncated mid-way -> ERROR', lambda: run(raw='{"complete": true, "only": "10", "total": 3, "failed": 2, "results": [{"name": "a", "ok"') == 'ERROR'),
 ('NEGATIVE: JSON is a list -> ERROR', lambda: run(raw='[]') == 'ERROR'),
 ('NEGATIVE: no completion marker -> ERROR', lambda: run(mutate=lambda d: d.pop('complete')) == 'ERROR'),
 ('NEGATIVE: completion marker is not boolean true -> ERROR', lambda: run(mutate=lambda d: d.__setitem__('complete', 'yes')) == 'ERROR'),
 ('NEGATIVE: JSON is for another scenario -> ERROR', lambda: run(only='9') == 'ERROR'),
 ('NEGATIVE: total does not equal the number of results -> ERROR', lambda: run(mutate=lambda d: d.__setitem__('total', 99)) == 'ERROR'),
 ('NEGATIVE: failed does not equal the number of failed results -> ERROR', lambda: run(mutate=lambda d: d.__setitem__('failed', 0)) == 'ERROR'),
 ('NEGATIVE: a result has a non-boolean ok -> ERROR', lambda: run(results=[{'name': LONG, 'ok': 'false'}, {'name': 'b', 'ok': False}], mutate=lambda d: d.__setitem__('failed', 1)) == 'ERROR'),
 ('NEGATIVE: a result has no name -> ERROR', lambda: run(results=[{'ok': False}], mutate=lambda d: None) == 'ERROR'),
 ('NEGATIVE: log has no final PHASE line -> ERROR', lambda: run(log=f"FAIL {LONG[:100]}\n") == 'ERROR'),
 ('NEGATIVE: log PHASE line disagrees with the JSON -> ERROR', lambda: run(log='PHASE 3B: 3 / 3 pass\n') == 'ERROR'),
 ('NEGATIVE: exit 0 although checks failed -> ERROR', lambda: run(exit_code=0) == 'ERROR'),
 ('NEGATIVE: exit 1 although nothing failed -> ERROR', lambda: run(results=ok_res, exit_code=1, log='PHASE 3B: 2 / 2 pass\n') == 'ERROR'),
 ('NEGATIVE: zero checks -> ERROR', lambda: run(results=[], exit_code=0, log='PHASE 3B: 0 / 0 pass\n') == 'ERROR'),
 ('CONTROL run: unmutated app passed everything and the needle matches a passing check -> OK', lambda: (lambda d: mv.control([M], 10, 0, 'PHASE 3B: 2 / 2 pass\n', d))(_cj([{'name': LONG, 'ok': True}, {'name': 'b', 'ok': True}], '10'))[0] is True),
 ('NEGATIVE control run: the unmutated app fails a check -> not OK', lambda: (lambda d: mv.control([M], 10, 1, 'PHASE 3B: 1 / 2 pass\n', d))(_cj([{'name': LONG, 'ok': True}, {'name': 'b', 'ok': False}], '10'))[0] is False),
 ('NEGATIVE control run: a needle that matches no check (typo) -> not OK', lambda: (lambda d: mv.control([M], 10, 0, 'PHASE 3B: 1 / 1 pass\n', d))(_cj([{'name': 'a', 'ok': True}], '10'))[0] is False),
]
def _cj(results, only):
    d = tempfile.mkdtemp(); js = os.path.join(d, 'c.json'); json.dump({'complete': True, 'only': only, 'total': len(results), 'failed': sum(1 for r in results if not r['ok']), 'results': results}, open(js, 'w')); return js
bad = 0
for name, fn in cases:
    try: r = bool(fn())
    except Exception as e: r = False; name += f'  [exception {e!r}]'
    print(('PASS ' if r else 'FAIL ') + name); bad += (not r)
print(f'RUNNER CONTROLS: {len(cases) - bad} / {len(cases)} pass'); sys.exit(1 if bad else 0)
