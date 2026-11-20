#!/usr/bin/env python3
"""Strict classifier for the Phase 4 mutation runner (stdlib only). A mutant counts as DETECTED only when (1) the mutant run is VALID and COMPLETE, and (2) EVERY assertion named in the mutant's `must_fail`
(each resolved to ONE exact check name in the unmutated control run of the same scenario) is present in the mutant run and FAILED, and (3) every `must_pass` assertion (resolved the same way) is present and PASSED
(so the defect is shown to be the intended one and not just any failure nearby). Everything else is reported as what it is; nothing partial is ever a detection.

  mutant_verdict_4.py verdict <mutants.json> <id> <log> <results.json> <exit-code> <control-results.json>   -> one summary line (+ failing names, display-truncated only); exit 0 DETECTED, 1 SURVIVED/SURVIVED-OTHER, 3 ERROR
  mutant_verdict_4.py control <mutants.json> <scenario> <log> <results.json> <exit-code>                    -> the UNMUTATED app must pass the whole scenario validly and every must_fail/must_pass needle of that scenario must resolve to exactly ONE passing check

mutants.json schema (canonical, anything else is rejected): a non-empty list of objects with exactly the keys id (unique non-empty str), desc (str), scenario (int, not bool, >= 0), must_fail (non-empty list of non-empty str), must_pass (list of str, may be empty).
Run validity (any violation => ERROR/INCOMPLETE): the exit code is 0 or 1 (2 crash, 3 the harness reports an ABORTED scenario, 124 timeout, >=128 killed are ERROR even if a partial log shows the intended FAIL); results.json parses to an object with complete===true,
`scenariosSelected` == `scenariosFinished` == [scenario] and `scenariosAborted` == [] (the harness's own lifecycle record), and NO result row that is the explicit scenario-ABORT row ("Rn: the scenario ABORTED with an exception ...") -- an abort is an ERROR even when
complete is forged to true and the intended check also failed and every count agrees: the run did not execute the whole scenario;
`only` a string equal to the canonical decimal of the scenario, integer total/failed, a results list of exactly `total` entries each with a string name (UNIQUE across the run) and a boolean ok, `failed` equal to the number of ok:false;
the log has EXACTLY ONE "PHASE 4:" summary, it is the last non-empty line, has the form "PHASE 4: P / T pass" and agrees with the JSON; exit 0 exactly when failed==0 and 1 exactly when failed>0.
FULL COVERAGE: a mutant run is classifiable only if its set of check names EQUALS the set of the (valid, fully passing, abort-free) unmutated control run of the same scenario: a self-consistent run that never reached some non-target case
(missing names) or that produced names the control does not have is INCOMPLETE/ERROR, never a detection. Check names are canonical identities: counts, hosts and comparison statistics live in the detail, not in the name."""
import sys, os, json, re

class SchemaError(Exception): pass
ABORT_ROW = re.compile(r'R\d+: the scenario ABORTED with an exception')

def is_int(x): return isinstance(x, int) and not isinstance(x, bool)

def load_mutants(path):
    try: ms = json.load(open(path, encoding='utf-8'))
    except Exception as e: raise SchemaError(f'mutants.json does not parse ({e})')
    if not isinstance(ms, list) or not ms: raise SchemaError('mutants.json is not a non-empty list')
    seen = set()
    for m in ms:
        if not isinstance(m, dict): raise SchemaError('a mutant entry is not an object')
        if set(m) != {'id', 'desc', 'scenario', 'must_fail', 'must_pass'}: raise SchemaError(f"mutant {m.get('id')!r}: keys are {sorted(m)}, expected id, desc, scenario, must_fail, must_pass")
        if not (isinstance(m['id'], str) and m['id'] and isinstance(m['desc'], str)): raise SchemaError('a mutant has a non-string or empty id/desc')
        if m['id'] in seen: raise SchemaError(f"duplicate mutant id {m['id']!r}")
        seen.add(m['id'])
        if not (is_int(m['scenario']) and m['scenario'] >= 0): raise SchemaError(f"mutant {m['id']}: scenario must be a non-negative integer (not text, not a bool), got {m['scenario']!r}")
        for k, nonempty in (('must_fail', True), ('must_pass', False)):
            v = m[k]
            if not (isinstance(v, list) and all(isinstance(x, str) and x for x in v) and (v or not nonempty)): raise SchemaError(f"mutant {m['id']}: {k} must be a list of non-empty strings" + (' (at least one)' if nonempty else ''))
    return ms

def validate(scn, log_text, json_path, exit_code):
    """returns (ok, reason, data). scn must be an int."""
    if not is_int(scn): return False, f'scenario {scn!r} is not an integer', None
    try: rc = int(exit_code)
    except Exception: return False, f'exit code {exit_code!r} is not a number', None
    if rc not in (0, 1): return False, f'exit code {rc} ({"timeout" if rc == 124 else "uncaught crash" if rc == 2 else "the harness reports an ABORTED scenario" if rc == 3 else "killed by a signal" if rc >= 128 else "unexpected"}): the run did not end by its own assertions', None
    if not os.path.isfile(json_path): return False, 'results JSON is missing (the run did not reach the end)', None
    try: d = json.load(open(json_path, encoding='utf-8'))
    except Exception as e: return False, f'results JSON does not parse ({e})', None
    ok, why = check_doc(d, scn)
    if not ok: return False, why, None
    t, f = d['total'], d['failed']
    lines = [l for l in log_text.splitlines() if l.strip()]
    marks = [l for l in lines if 'PHASE 4:' in l]
    if len(marks) != 1: return False, f'the log has {len(marks)} "PHASE 4:" summary lines, expected exactly one', None
    if lines[-1] != marks[0]: return False, 'the "PHASE 4:" summary is not the last line of the log', None
    m = re.fullmatch(r'PHASE 4: (\d+) / (\d+) pass', marks[0].strip())
    if not m: return False, f'the summary line {marks[0][:60]!r} is not of the form "PHASE 4: P / T pass"', None
    if int(m.group(2)) != t or int(m.group(1)) != t - f: return False, f'the log says {m.group(1)} / {m.group(2)} but the JSON says {t - f} / {t}', None
    if (rc == 0) != (f == 0): return False, f'exit code {rc} disagrees with failed={f}', None
    return True, 'valid and complete', d

def check_doc(d, scn):
    if not isinstance(d, dict): return False, 'results JSON is not an object'
    if d.get('complete') is not True: return False, 'results JSON has no completion marker'
    if not (isinstance(d.get('only'), str) and d['only'] == str(scn)): return False, f"results JSON is for scenario {d.get('only')!r}, expected the string {str(scn)!r}"
    t, f, r = d.get('total'), d.get('failed'), d.get('results')
    if not (is_int(t) and is_int(f) and isinstance(r, list)): return False, 'results JSON has wrong types for total/failed/results'
    if len(r) != t: return False, f'results JSON total={t} but {len(r)} results'
    if t == 0: return False, 'no checks were run'
    for x in r:
        if not (isinstance(x, dict) and isinstance(x.get('name'), str) and isinstance(x.get('ok'), bool)): return False, 'a result lacks a string name or a boolean ok'
    names = [x['name'] for x in r]
    if len(set(names)) != len(names): return False, 'check names are not unique within the run, so an assertion identity would be ambiguous'
    nf = sum(1 for x in r if not x['ok'])
    if nf != f: return False, f'results JSON failed={f} but {nf} results are not ok'
    ab = [n for n in names if ABORT_ROW.match(n)]
    if ab: return False, f'the run contains the explicit scenario-ABORT row {ab[0][:90]!r}: the scenario did not execute to its last check (an abort is never a detection and never a pass)'
    for k in ('scenariosSelected', 'scenariosFinished', 'scenariosAborted'):
        if not (isinstance(d.get(k), list) and all(is_int(x) for x in d[k])): return False, f'results JSON has no valid {k} lifecycle record'
    if d['scenariosAborted']: return False, f"the harness lists aborted scenario(s) {d['scenariosAborted']}"
    if d['scenariosSelected'] != [scn] or d['scenariosFinished'] != [scn]: return False, f"lifecycle record says selected {d['scenariosSelected']} finished {d['scenariosFinished']}, expected exactly [{scn}] for both"
    return True, 'ok'

def resolve(needle, names):
    """the ONE exact check name containing `needle`; raises SchemaError unless exactly one matches"""
    hits = [n for n in names if needle in n]
    if len(hits) != 1: raise SchemaError(f'needle {needle[:70]!r} matches {len(hits)} checks in the unmutated run (it must match exactly one)')
    return hits[0]

def verdict(mutant, exit_code, log_text, json_path, control_json):
    ok, why, d = validate(mutant['scenario'], log_text, json_path, exit_code)
    if not ok: return 'ERROR', why, []
    try:
        c = json.load(open(control_json, encoding='utf-8')); cok, cwhy = check_doc(c, mutant['scenario'])
        if not cok or c['failed'] != 0: return 'ERROR', f'the control results for this scenario are not a valid, fully passing run ({cwhy if not cok else "it has failed checks"})', []
        cnames = [x['name'] for x in c['results']]
        want_fail = [resolve(n, cnames) for n in mutant['must_fail']]; want_pass = [resolve(n, cnames) for n in mutant['must_pass']]
    except SchemaError as e: return 'ERROR', str(e), []
    except Exception as e: return 'ERROR', f'control results unreadable ({e})', []
    mnames = {x['name'] for x in d['results']}; cset = set(cnames)
    if mnames != cset:
        miss, extra = sorted(cset - mnames), sorted(mnames - cset)
        return 'ERROR', f"INCOMPLETE execution: the mutant run is not the same set of checks as the valid control ({len(d['results'])} vs {len(cnames)}): {len(miss)} expected case(s) never ran" + (f" (first: {miss[0][:80]!r})" if miss else '') + f", {len(extra)} unexpected case(s)" + (f" (first: {extra[0][:80]!r})" if extra else ''), []
    by = {x['name']: x['ok'] for x in d['results']}; failed = [x['name'] for x in d['results'] if not x['ok']]
    if not failed: return 'SURVIVED', 'the scenario passed completely on the mutant', []
    nf = [n for n in want_fail if n not in by]; nok = [n for n in want_fail if by.get(n) is True]
    pf = [n for n in want_pass if by.get(n) is not True]
    if not nf and not nok and not pf: return 'DETECTED', f'{len(failed)} check(s) failed, including EVERY intended assertion ({len(want_fail)}) and with {len(want_pass)} isolation check(s) still passing', failed
    parts = []
    if nf: parts.append(f'{len(nf)} intended assertion(s) never ran')
    if nok: parts.append(f'{len(nok)} intended assertion(s) PASSED')
    if pf: parts.append(f'{len(pf)} isolation check(s) did not pass')
    return 'SURVIVED-OTHER', f'{len(failed)} other check(s) failed but the intended assertion identity is not proven: ' + '; '.join(parts), failed

def control(mutants, scn, exit_code, log_text, json_path):
    ok, why, d = validate(scn, log_text, json_path, exit_code)
    if not ok: return False, 'control run invalid: ' + why
    if d['failed']: return False, f"the UNMUTATED app fails {d['failed']} check(s) of scenario {scn}: " + '; '.join(x['name'][:90] for x in d['results'] if not x['ok'])[:400]
    names = [x['name'] for x in d['results']]; bad = []
    for m in mutants:
        if m['scenario'] != scn: continue
        for n in m['must_fail'] + m['must_pass']:
            try: resolve(n, names)
            except SchemaError as e: bad.append(f"{m['id']}: {e}")
    if bad: return False, 'needle resolution failed: ' + ' | '.join(bad)
    return True, f"unmutated app passed all {d['total']} checks; every needle of the scenario resolves to exactly one passing check"

if __name__ == '__main__':
    mode = sys.argv[1]
    try:
        if mode == 'verdict':
            mp, mid, lg, js, rc, cj = sys.argv[2:8]
            ms = load_mutants(mp); m = [x for x in ms if x['id'] == mid][0]; text = open(lg, encoding='utf-8', errors='replace').read() if os.path.isfile(lg) else ''
            v, why, failed = verdict(m, rc, text, js, cj)
            try: dd = json.load(open(js)); extra = f" total={dd.get('total')} failed={dd.get('failed')}"
            except Exception: extra = ' total=? failed=?'
            print(f"{mid}: scenario R{m['scenario']} exit={rc}{extra} VERDICT={v} ({why}) | {m['desc']}")
            for n in failed[:5]: print('      failed:', n[:170] + ('…' if len(n) > 170 else ''))   # display truncation ONLY
            sys.exit({'DETECTED': 0, 'SURVIVED': 1, 'SURVIVED-OTHER': 1, 'ERROR': 3}[v])
        if mode == 'control':
            mp, scn, lg, js, rc = sys.argv[2:7]
            if not re.fullmatch(r'0|[1-9]\d*', scn): raise SchemaError(f'scenario argument {scn!r} is not a canonical integer')
            text = open(lg, encoding='utf-8', errors='replace').read() if os.path.isfile(lg) else ''
            ok, why = control(load_mutants(mp), int(scn), rc, text, js)
            print(f"control R{scn}: {'OK' if ok else 'ERROR'} - {why}"); sys.exit(0 if ok else 3)
    except SchemaError as e:
        print(f'ERROR: {e}'); sys.exit(3)
    sys.exit(2)
