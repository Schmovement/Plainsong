#!/usr/bin/env python3
"""Negative and positive controls for the mutation runner's classifier (tests/mutant_verdict_5.py) and for the runner's control/abort behaviour (tests/run_mutants_5.sh, run end-to-end
against a small STUB project: stub suite, stub mutants). Prints PASS/FAIL per control; exit 0 only if all pass. The runner executes this BEFORE any mutant: if it fails, no mutant verdict is trusted."""
import os, sys, json, tempfile, importlib.util, subprocess, shutil, re
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('mv', os.path.join(here, 'mutant_verdict_5.py')); mv = importlib.util.module_from_spec(spec); spec.loader.exec_module(mv)
LONG = 'S10 reject: Escape (twice), a click on Cancel, on Revert and on Choose image, and choosing another file do NOTHING while saving: the dialog stays open'
NEEDLE = 'do NOTHING while saving'
assert LONG.index(NEEDLE) + len(NEEDLE) > 125   # the very first runner cut names at 125 characters: this needle lies beyond that
def mutant(**kw):
    m = {'id': 'X', 'desc': 'd', 'scenario': 10, 'must_fail': [NEEDLE], 'must_pass': []}; m.update(kw); return m
def lifecycle(only):
    sc = [int(only)] if re.fullmatch(r'0|[1-9]\d*', str(only)) else []
    return {'scenariosSelected': sc, 'scenariosFinished': sc, 'scenariosAborted': []}
def cdoc(results, only='10', **over):
    d = {'complete': True, 'only': only, **lifecycle(only), 'total': len(results), 'failed': sum(1 for r in results if not r['ok']), 'results': results}; d.update(over); return d
def wj(doc=None, raw=None):
    d = tempfile.mkdtemp(); js = os.path.join(d, 'r.json'); open(js, 'w').write(raw if raw is not None else json.dumps(doc)); return js
CTL = [{'name': 'a', 'ok': True}, {'name': LONG, 'ok': True}, {'name': 'b', 'ok': True}, {'name': 'iso check', 'ok': True}]
DEF = [{'name': 'a', 'ok': True}, {'name': LONG, 'ok': False}, {'name': 'b', 'ok': True}, {'name': 'iso check', 'ok': True}]
def log_for(results, extra=''):
    t = len(results); f = sum(1 for r in results if not r['ok']); return f'{extra}PHASE 5: {t - f} / {t} pass\n'
def run(results=None, exit_code=1, only='10', log=None, raw=None, mutate=None, write=True, m=None, control_results=None, control_raw=None):
    results = DEF if results is None else results; doc = cdoc(results, only)
    if mutate: mutate(doc)
    js = wj(doc, raw) if write else os.path.join(tempfile.mkdtemp(), 'none.json')
    cj = wj(cdoc(CTL if control_results is None else control_results), control_raw)
    return mv.verdict(m or mutant(), exit_code, log if log is not None else log_for(results, f'FAIL {LONG[:100]}\n'), js, cj)[0]
def ctl(results, mutants, rc=0, log=None, only='10', scn=10, mutate=None):
    doc = cdoc(results, only)
    if mutate: mutate(doc)
    return mv.control(mutants, scn, rc, log if log is not None else log_for(results), wj(doc))
def schema_bad(ms):
    p = wj(ms)
    try: mv.load_mutants(p); return False
    except mv.SchemaError: return True
ok_res = [{'name': 'a', 'ok': True}, {'name': 'b', 'ok': True}]
cases = [
 # ---- plain classification
 ('valid, exit 1, the intended assertion (resolved from a name longer than 125 chars) failed, isolation check passed -> DETECTED', lambda: run(m=mutant(must_pass=['iso check'])) == 'DETECTED'),
 ('valid, exit 1, only OTHER checks failed -> SURVIVED-OTHER (not a detection)', lambda: run(results=[{'name': 'a', 'ok': True}, {'name': LONG, 'ok': True}, {'name': 'b', 'ok': False}, {'name': 'iso check', 'ok': True}]) == 'SURVIVED-OTHER'),
 ('valid, exit 0, nothing failed -> SURVIVED', lambda: run(results=CTL, exit_code=0) == 'SURVIVED'),
 # ---- exact causal identity
 ('NEGATIVE (P1-like): a different failure in the same scenario (not the intended seek/position assertion) -> SURVIVED-OTHER', lambda: run(results=[{'name': 'a', 'ok': True}, {'name': LONG, 'ok': True}, {'name': 'b', 'ok': False}, {'name': 'iso check', 'ok': True}]) == 'SURVIVED-OTHER'),
 ('NEGATIVE: the intended check never ran (scenario aborted early) while another check failed -> never a detection (stricter since candidate 2: ERROR, incomplete coverage; formerly SURVIVED-OTHER)', lambda: run(results=[{'name': 'a', 'ok': True}, {'name': 'b', 'ok': False}]) == 'ERROR'),
 ('NEGATIVE: a DIFFERENT failing check whose name merely contains the needle (a variant) is not the resolved assertion -> never a detection (stricter since candidate 2: ERROR, the set of checks differs from the control; formerly SURVIVED-OTHER)', lambda: run(results=[{'name': 'a', 'ok': True}, {'name': LONG + ' (variant)', 'ok': False}, {'name': 'iso check', 'ok': True}]) == 'ERROR'),
 ('NEGATIVE: an isolation check (must_pass) also fails -> SURVIVED-OTHER (the defect is not shown to be the intended one)', lambda: run(m=mutant(must_pass=['iso check']), results=[{'name': 'a', 'ok': True}, {'name': LONG, 'ok': False}, {'name': 'b', 'ok': True}, {'name': 'iso check', 'ok': False}]) == 'SURVIVED-OTHER'),
 ('NEGATIVE: an isolation check (must_pass) never ran -> never a detection (stricter since candidate 2: ERROR, incomplete coverage; formerly SURVIVED-OTHER)', lambda: run(m=mutant(must_pass=['iso check']), results=[{'name': 'a', 'ok': True}, {'name': LONG, 'ok': False}]) == 'ERROR'),
 ('two intended assertions, BOTH failed -> DETECTED', lambda: run(m=mutant(must_fail=[NEEDLE, 'iso check']), results=[{'name': 'a', 'ok': True}, {'name': LONG, 'ok': False}, {'name': 'b', 'ok': True}, {'name': 'iso check', 'ok': False}]) == 'DETECTED'),
 ('NEGATIVE: two intended assertions, only ONE failed -> SURVIVED-OTHER', lambda: run(m=mutant(must_fail=[NEEDLE, 'iso check'])) == 'SURVIVED-OTHER'),
 ('NEGATIVE: the needle matches TWO checks in the unmutated run (ambiguous identity) -> ERROR', lambda: run(m=mutant(must_fail=['a']), control_results=[{'name': 'a', 'ok': True}, {'name': 'ab', 'ok': True}]) == 'ERROR'),
 ('NEGATIVE: the needle matches no check in the unmutated run (typo) -> ERROR', lambda: run(m=mutant(must_fail=['no such check'])) == 'ERROR'),
 ('NEGATIVE: the unmutated control results contain a failure -> ERROR', lambda: run(control_results=DEF) == 'ERROR'),
 ('NEGATIVE: the unmutated control results are for another scenario -> ERROR', lambda: (lambda cj: mv.verdict(mutant(), 1, log_for(DEF), wj(cdoc(DEF)), cj)[0])(wj(cdoc(CTL, only='9'))) == 'ERROR'),
 ('NEGATIVE: the unmutated control results are unreadable -> ERROR', lambda: run(control_raw='{') == 'ERROR'),
 # ---- crash / timeout / partial output is never a detection
 ('NEGATIVE: partial log shows the intended FAIL, no JSON, exit 2 (uncaught crash) -> ERROR', lambda: run(exit_code=2, write=False) == 'ERROR'),
 ('NEGATIVE: partial log shows the intended FAIL, no JSON, exit 124 (timeout) -> ERROR', lambda: run(exit_code=124, write=False) == 'ERROR'),
 ('NEGATIVE: complete-looking JSON but exit 124 (timeout) -> ERROR', lambda: run(exit_code=124) == 'ERROR'),
 ('NEGATIVE: complete-looking JSON but exit 137 (killed) -> ERROR', lambda: run(exit_code=137) == 'ERROR'),
 ('NEGATIVE: complete-looking JSON but exit 2 -> ERROR', lambda: run(exit_code=2) == 'ERROR'),
 ('NEGATIVE: exit code not a number -> ERROR', lambda: run(exit_code='') == 'ERROR'),
 # ---- results JSON schema
 ('NEGATIVE: JSON truncated mid-way -> ERROR', lambda: run(raw='{"complete": true, "only": "10", "total": 3, "failed": 2, "results": [{"name": "a", "ok"') == 'ERROR'),
 ('NEGATIVE: JSON is a list -> ERROR', lambda: run(raw='[]') == 'ERROR'),
 ('NEGATIVE: no completion marker -> ERROR', lambda: run(mutate=lambda d: d.pop('complete')) == 'ERROR'),
 ('NEGATIVE: completion marker is not boolean true -> ERROR', lambda: run(mutate=lambda d: d.__setitem__('complete', 'yes')) == 'ERROR'),
 ('NEGATIVE: JSON is for another scenario -> ERROR', lambda: run(only='9') == 'ERROR'),
 ('NEGATIVE: scenario identity as a number (10) instead of the string "10" -> ERROR (no str() coercion)', lambda: run(mutate=lambda d: d.__setitem__('only', 10)) == 'ERROR'),
 ('NEGATIVE: scenario identity with whitespace " 10" -> ERROR', lambda: run(only=' 10') == 'ERROR'),
 ('NEGATIVE: scenario identity "010" -> ERROR', lambda: run(only='010') == 'ERROR'),
 ('NEGATIVE: total does not equal the number of results -> ERROR', lambda: run(mutate=lambda d: d.__setitem__('total', 99)) == 'ERROR'),
 ('NEGATIVE: failed does not equal the number of failed results -> ERROR', lambda: run(mutate=lambda d: d.__setitem__('failed', 0)) == 'ERROR'),
 ('NEGATIVE: total is a boolean -> ERROR', lambda: run(mutate=lambda d: d.__setitem__('total', True)) == 'ERROR'),
 ('NEGATIVE: a result has a non-boolean ok -> ERROR', lambda: run(results=[{'name': LONG, 'ok': 'false'}, {'name': 'b', 'ok': False}], mutate=lambda d: d.__setitem__('failed', 1)) == 'ERROR'),
 ('NEGATIVE: a result has no name -> ERROR', lambda: run(results=[{'ok': False}], mutate=lambda d: None) == 'ERROR'),
 ('NEGATIVE: two results with the same name (ambiguous identity) -> ERROR', lambda: run(results=[{'name': LONG, 'ok': True}, {'name': LONG, 'ok': False}]) == 'ERROR'),
 ('NEGATIVE: zero checks -> ERROR', lambda: run(results=[], exit_code=0, log='PHASE 5: 0 / 0 pass\n') == 'ERROR'),
 ('NEGATIVE: exit 0 although checks failed -> ERROR', lambda: run(exit_code=0) == 'ERROR'),
 ('NEGATIVE: exit 1 although nothing failed -> ERROR', lambda: run(results=CTL, exit_code=1) == 'ERROR'),
 # ---- log summary
 ('NEGATIVE: log has no PHASE summary line -> ERROR', lambda: run(log=f'FAIL {LONG[:100]}\n') == 'ERROR'),
 ('NEGATIVE: log PHASE line disagrees with the JSON -> ERROR', lambda: run(log='PHASE 5: 3 / 3 pass\n') == 'ERROR'),
 ('NEGATIVE: an EARLIER passing summary and a later contradictory one (two summaries) -> ERROR, never the first', lambda: run(log='PHASE 5: 4 / 4 pass\nPHASE 5: 3 / 4 pass\n') == 'ERROR'),
 ('NEGATIVE: two identical consistent summaries -> ERROR (exactly one is required)', lambda: run(log='PHASE 5: 3 / 4 pass\nPHASE 5: 3 / 4 pass\n') == 'ERROR'),
 ('NEGATIVE: the consistent summary is not the LAST line (output after it) -> ERROR', lambda: run(log='PHASE 5: 3 / 4 pass\nTypeError: late failure\n') == 'ERROR'),
 ('NEGATIVE: summary text with extra words ("pass, then crashed") -> ERROR', lambda: run(log='PHASE 5: 3 / 4 pass, then crashed\n') == 'ERROR'),
 ('summary preceded by ordinary lines and followed by a blank line -> accepted', lambda: run(log='PASS x\nFAIL y\nPHASE 5: 3 / 4 pass\n\n') == 'DETECTED'),
 # ---- mutants.json schema
 ('schema: a well-formed mutants.json loads', lambda: not schema_bad([mutant()])),
 ('NEGATIVE schema: scenario as text "10" -> rejected', lambda: schema_bad([mutant(scenario='10')])),
 ('NEGATIVE schema: scenario as a boolean -> rejected', lambda: schema_bad([mutant(scenario=True)])),
 ('NEGATIVE schema: scenario as a float 10.0 -> rejected', lambda: schema_bad([mutant(scenario=10.0)])),
 ('NEGATIVE schema: negative scenario -> rejected', lambda: schema_bad([mutant(scenario=-1)])),
 ('NEGATIVE schema: legacy single "needle" key instead of must_fail -> rejected', lambda: schema_bad([{'id': 'X', 'desc': 'd', 'scenario': 10, 'needle': 'x'}])),
 ('NEGATIVE schema: empty must_fail -> rejected', lambda: schema_bad([mutant(must_fail=[])])),
 ('NEGATIVE schema: must_fail is a string, not a list -> rejected', lambda: schema_bad([mutant(must_fail='abc')])),
 ('NEGATIVE schema: an extra key -> rejected', lambda: schema_bad([dict(mutant(), extra=1)])),
 ('NEGATIVE schema: duplicate ids -> rejected', lambda: schema_bad([mutant(), mutant()])),
 ('NEGATIVE schema: empty list -> rejected', lambda: schema_bad([])),
 # ---- control mode
 ('CONTROL run: unmutated app passed everything; every needle resolves to exactly one check -> OK', lambda: ctl(CTL, [mutant(must_pass=['iso check'])])[0] is True),
 ('NEGATIVE control run: the unmutated app fails a check -> not OK', lambda: ctl(DEF, [mutant()], rc=1)[0] is False),
 ('NEGATIVE control run: a needle that matches no check (typo) -> not OK', lambda: ctl(CTL, [mutant(must_fail=['zzz'])])[0] is False),
 ('NEGATIVE control run: a needle that matches two checks -> not OK', lambda: ctl([{'name': 'x1', 'ok': True}, {'name': 'x2', 'ok': True}], [mutant(must_fail=['x'])])[0] is False),
 ('NEGATIVE control run: duplicate check names -> not OK', lambda: ctl([{'name': 'a', 'ok': True}, {'name': 'a', 'ok': True}], [mutant(must_fail=['a'])])[0] is False),
 ('NEGATIVE control run: scenario given as text -> not OK', lambda: mv.control([mutant()], '10', 0, log_for(CTL), wj(cdoc(CTL)))[0] is False),
 ('NEGATIVE control run: crash exit 2 even with a complete-looking JSON -> not OK', lambda: ctl(CTL, [mutant()], rc=2)[0] is False),
]


# ---- ABORT / partial-execution controls (added after candidate 1 counted four aborted runs as DETECTED)
DATA = os.path.join(here, 'classifier-control-data')
import re as _re
def _rn(x): return _re.sub(r'^R(\d+)', r'Q\1', x) if isinstance(x, str) else x
def load(name):
    d = json.load(open(os.path.join(DATA, name), encoding='utf-8'))
    if isinstance(d, dict) and 'results' in d:
        for r in d['results']: r['name'] = _rn(r['name'])
    if isinstance(d, list):
        for m in d: m['must_fail'] = [_rn(x) for x in m['must_fail']]; m['must_pass'] = [_rn(x) for x in m['must_pass']]
    return d
def text(name): return _re.sub(r'(?m)^(PASS |FAIL )R(\d+)', r'\1Q\2', open(os.path.join(DATA, name), encoding='utf-8').read()).replace('PHASE ' + '4:', 'PHASE 5:')
REAL4 = {m['id']: m for m in load('mutants-candidate1-four.json')}
ABORT_NAME = 'Q9: the scenario ABORTED with an exception before its last check (a test or app fault, not a pass)'
def real(mid, patch=None, rc=1, with_lifecycle=True, strip_abort=False):
    """the REAL candidate-1 results of an aborted mutant run, classified against the REAL control of its scenario"""
    m = REAL4[mid]; scn = m['scenario']; d = load(mid + '.json'); c = load(f'control-R{scn}.json')
    if with_lifecycle: d.update(lifecycle(str(scn))); c.update(lifecycle(str(scn)))   # isolate the abort/coverage rules from the new lifecycle fields
    if strip_abort:   # delete the ABORT row and keep every count self-consistent: the run still never reached its remaining checks
        d['results'] = [x for x in d['results'] if 'the scenario ABORTED' not in x['name']]; d['total'] = len(d['results']); d['failed'] = sum(1 for x in d['results'] if not x['ok'])
    if patch: patch(d)
    log = text(mid + '.log')
    if strip_abort or patch:   # keep the log consistent with the (edited) JSON so only the rule under test can reject it
        lines = [l for l in log.splitlines() if 'PHASE 5:' not in l]; log = '\n'.join(lines) + f"\nPHASE 5: {d['total'] - d['failed']} / {d['total']} pass\n"
    return mv.verdict(m, rc, log, wj(d), wj(c))
def old_validity(mid):   # the OLD classifier's validity criteria (complete, counts, log summary) are all satisfied by the real file: it is the shape that was wrongly accepted
    d = load(mid + '.json'); return d['complete'] is True and d['total'] == len(d['results']) and d['failed'] == sum(1 for x in d['results'] if not x['ok'])
def real4_cases():
    out = []
    for mid in REAL4:
        short = mid.split('-')[0]
        out += [
         (f'REAL candidate-1 shape {short}: the run has complete:true, the intended check FAILED, counts and log agree (old classifier: DETECTED) -> now ERROR (explicit scenario ABORT row)', lambda mid=mid: old_validity(mid) and real(mid)[0] == 'ERROR' and 'ABORT' in real(mid)[1]),
         (f'REAL candidate-1 shape {short}: as recorded (no lifecycle fields) -> ERROR', lambda mid=mid: real(mid, with_lifecycle=False)[0] == 'ERROR'),
         (f'REAL candidate-1 shape {short}: forge the lifecycle record to claim finished and aborted=[] and complete:true, ABORT row kept -> still ERROR', lambda mid=mid: real(mid)[0] == 'ERROR'),
         (f'REAL candidate-1 shape {short}: the ABORT row removed and every count made self-consistent, but the missing non-target cases remain -> ERROR (incomplete coverage, no ABORT row needed)', lambda mid=mid: (lambda v: v[0] == 'ERROR' and 'INCOMPLETE' in v[1] and 'never ran' in v[1])(real(mid, strip_abort=True))),
         (f'REAL candidate-1 shape {short}: even with exit code 3 (the new harness exit for an aborted scenario) -> ERROR', lambda mid=mid: real(mid, rc=3)[0] == 'ERROR'),
        ]
    return out
FULL = [{'name': 'a', 'ok': True}, {'name': LONG, 'ok': True}, {'name': 'b', 'ok': True}, {'name': 'c', 'ok': True}, {'name': 'iso check', 'ok': True}]
def mut_full(results, rc=1, patch=None, ctl_results=None, m=None):
    d = cdoc(results); 
    if patch: patch(d)
    return mv.verdict(m or mutant(must_pass=['iso check']), rc, log_for(results), wj(d), wj(cdoc(FULL if ctl_results is None else ctl_results)))
FULLDEF = [dict(x) for x in FULL]; FULLDEF[1] = {'name': LONG, 'ok': False}
cases += real4_cases() + [
 ('NEGATIVE: forged complete:true + intended FAIL + ABORT row + isolation PASS, every count and the log consistent, lifecycle forged clean -> ERROR', lambda: mut_full([FULLDEF[0], FULLDEF[1], FULLDEF[4], {'name': ABORT_NAME, 'ok': False}])[0] == 'ERROR'),
 ('NEGATIVE: the same forged shape with the ABORT row present and ALL control cases present (it is the abort row alone that rejects it) -> ERROR', lambda: mut_full(FULLDEF + [{'name': ABORT_NAME, 'ok': False}])[0] == 'ERROR'),
 ('NEGATIVE: self-consistent run, intended FAIL present, isolation PASS present, ONE non-target case of the control never ran, NO abort row -> ERROR (missing coverage)', lambda: (lambda v: v[0] == 'ERROR' and 'never ran' in v[1])(mut_full([FULLDEF[0], FULLDEF[1], FULLDEF[2], FULLDEF[4]]))),
 ('NEGATIVE: self-consistent run that has every control case plus ONE unexpected extra case -> ERROR (the identities must be equal)', lambda: mut_full(FULLDEF + [{'name': 'something the control never had', 'ok': True}])[0] == 'ERROR'),
 ('POSITIVE: the same shape with exactly the control\'s set of cases, intended FAIL + isolation PASS -> DETECTED', lambda: mut_full(FULLDEF)[0] == 'DETECTED'),
 ('NEGATIVE: lifecycle says a scenario ABORTED although no abort row exists and complete is true -> ERROR', lambda: mut_full(FULLDEF, patch=lambda d: d.__setitem__('scenariosAborted', [10]))[0] == 'ERROR'),
 ('NEGATIVE: lifecycle record missing entirely -> ERROR', lambda: mut_full(FULLDEF, patch=lambda d: [d.pop(k) for k in ('scenariosSelected', 'scenariosFinished', 'scenariosAborted')])[0] == 'ERROR'),
 ('NEGATIVE: lifecycle says the scenario was selected but NOT finished -> ERROR', lambda: mut_full(FULLDEF, patch=lambda d: d.__setitem__('scenariosFinished', []))[0] == 'ERROR'),
 ('NEGATIVE: lifecycle names a different scenario -> ERROR', lambda: mut_full(FULLDEF, patch=lambda d: d.__setitem__('scenariosFinished', [9]))[0] == 'ERROR'),
 ('NEGATIVE: exit code 3 (the harness reports an aborted scenario) with an otherwise perfect-looking run -> ERROR', lambda: mut_full(FULLDEF, rc=3)[0] == 'ERROR'),
 ('NEGATIVE: the UNMUTATED control itself contains an ABORT row (even with every other check passing) -> the control is not valid, the verdict is ERROR', lambda: mut_full(FULLDEF, ctl_results=FULL + [{'name': ABORT_NAME, 'ok': True}])[0] == 'ERROR'),
 ('NEGATIVE control run: the unmutated app\'s run contains the ABORT row -> not OK', lambda: ctl([{'name': 'a', 'ok': True}, {'name': ABORT_NAME.replace('Q9', 'Q10'), 'ok': False}], [mutant(must_fail=['a'])], rc=1)[0] is False),
 ('NEGATIVE control run: lifecycle record missing -> not OK', lambda: ctl(CTL, [mutant()], mutate=lambda d: d.pop('scenariosFinished'))[0] is False),
 ('REAL candidate-1 controls R5 and R9 (the unmutated runs) are themselves valid, abort-free and have every needle resolve -> OK (the controls were fine, the MUTANT runs were partial)', lambda: all(mv.control([REAL4[m] for m in REAL4 if REAL4[m]['scenario'] == sc], sc, 0, text(f'control-R{sc}.log'), wj({**load(f'control-R{sc}.json'), **lifecycle(str(sc))}))[0] for sc in (5, 9))),
]

# ---- the runner itself, end to end on a stub project (stub suite + stub mutants); it must ABORT on an invalid control and must classify nothing then
STUB_SUITE = r"""
const fs = require('fs'), http = require('http');
const [,, , , out] = process.argv, only = process.env.ONLY, mode = process.env.STUB_MODE || fs.readFileSync(__dirname + '/mode.txt', 'utf-8').trim();
http.get(process.env.PS_URL, res => { let b = ''; res.on('data', c => b += c); res.on('end', () => {
  const mutated = /STUB-MUTANT/.test(b); const res_ = [{ name: 'R0: stub intended check', ok: !(mutated) }, { name: 'R0: stub isolation check', ok: true }];
  if (mode === 'badcontrol' && !mutated) res_[1].ok = false;                // the UNMUTATED app fails a check: the control is invalid
  const failed = res_.filter(r => !r.ok).length;
  if (mode === 'crashcontrol' && !mutated) { console.log('partial output'); process.exit(2); }
  fs.writeFileSync(out, JSON.stringify({ complete: true, only, scenariosSelected: [Number(only)], scenariosFinished: [Number(only)], scenariosAborted: [], total: res_.length, failed, results: res_ }));
  for (const r of res_) console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name);
  console.log(`\nPHASE 5: ${res_.length - failed} / ${res_.length} pass`); process.exit(failed ? 1 : 0);
}); });
"""
STUB_MUTANTS = r"""
import sys, os, json
proj, out = sys.argv[1], sys.argv[2]
d = os.path.join(out, 'S1'); os.makedirs(d, exist_ok=True)
open(os.path.join(d, 'index.html'), 'w').write('<html>STUB-MUTANT</html>'); open(os.path.join(d, 'style.css'), 'w').write('')
json.dump([{'id': 'S1', 'desc': 'stub', 'scenario': 0, 'must_fail': ['R0: stub intended check'], 'must_pass': ['R0: stub isolation check']}], open(os.path.join(out, 'mutants.json'), 'w'))
"""
def stub_runner(mode):
    root = tempfile.mkdtemp(); proj = os.path.join(root, 'proj'); ev = os.path.join(root, 'ev'); wr = os.path.join(root, 'wr'); os.makedirs(os.path.join(proj, 'tests', 'fixtures-wav'))
    for f in ('mutant_verdict_5.py', 'run_mutants_5.sh'): shutil.copy(os.path.join(here, f), os.path.join(proj, 'tests', f))
    open(os.path.join(proj, 'tests', 'test_mutant_verdict_5.py'), 'w').write('print("RUNNER CONTROLS: 1 / 1 pass")\n')   # stub: no recursion
    open(os.path.join(proj, 'tests', 'mutants_5.py'), 'w').write(STUB_MUTANTS); open(os.path.join(proj, 'tests', 'phase5.test.js'), 'w').write(STUB_SUITE); open(os.path.join(proj, 'tests', 'mode.txt'), 'w').write(mode)
    open(os.path.join(proj, 'index.html'), 'w').write('<html>unmutated</html>'); open(os.path.join(proj, 'style.css'), 'w').write('')
    env = {k: v for k, v in os.environ.items() if k != 'MUT_ONLY'}   # a focused outer run (MUT_ONLY set) must not filter the stub project's own mutant away
    r = subprocess.run(['bash', os.path.join(proj, 'tests', 'run_mutants_5.sh'), proj, ev, wr], capture_output=True, text=True, timeout=120, env=env)
    summ = open(os.path.join(ev, 'mutants-summary.txt')).read() if os.path.isfile(os.path.join(ev, 'mutants-summary.txt')) else ''
    shutil.rmtree(root, ignore_errors=True); return r.returncode, summ
def runner_ok(): rc, s = stub_runner('good'); return rc == 0 and 'VERDICT=DETECTED' in s and 'DETECTED (valid, complete, intended check failed): 1' in s
def runner_abort(mode): rc, s = stub_runner(mode); return rc == 3 and 'ABORTED before any mutant was run or classified' in s and 'VERDICT=' not in s and '== mutants' not in s
cases += [
 ('RUNNER end to end (stub project): valid control + mutant that fails the intended check -> DETECTED, exit 0', runner_ok),
 ('NEGATIVE RUNNER (stub project): the unmutated control FAILS a check -> the runner ABORTS with exit 3 and classifies NO mutant (no VERDICT line, no "== mutants" section)', lambda: runner_abort('badcontrol')),
 ('NEGATIVE RUNNER (stub project): the unmutated control run CRASHES (exit 2) -> the runner ABORTS with exit 3 and classifies NO mutant', lambda: runner_abort('crashcontrol')),
]
bad = 0
for name, fn in cases:
    try: r = bool(fn())
    except Exception as e: r = False; name += f'  [exception {e!r}]'
    print(('PASS ' if r else 'FAIL ') + name); bad += (not r)
print(f'RUNNER CONTROLS: {len(cases) - bad} / {len(cases)} pass'); sys.exit(1 if bad else 0)
