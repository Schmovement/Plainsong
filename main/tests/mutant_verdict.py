#!/usr/bin/env python3
"""Classifier for the Phase 3B mutation runner (stdlib only). A mutant counts as DETECTED only when the run finished in a VALID, COMPLETE way and a check that names the
intended safeguard FAILED. Everything else is reported as what it is; nothing partial is ever a detection.

  mutant_verdict.py verdict <mutants.json> <id> <log> <results.json> <exit-code>     -> prints one summary line (+ failing names, display-truncated only); exit 0 DETECTED, 1 SURVIVED/SURVIVED-OTHER, 3 ERROR
  mutant_verdict.py control <mutants.json> <scenario> <log> <results.json> <exit-code> -> the UNMUTATED app must pass the whole scenario, validly, and every needle of that scenario must match a PASSING check

Validity rules (any violation => ERROR/INCOMPLETE, never a detection): results.json exists and parses; has complete===true, `only` equal to the selected scenario, integer total/failed,
a results list of exactly `total` entries each with a string name and a boolean ok, `failed` equal to the number of ok:false entries; the log has the line "PHASE 3B: P / T pass" agreeing
with the JSON; the exit code is 0 exactly when failed==0 and 1 exactly when failed>0 (2 = uncaught crash, 124 = timeout, >=128 = killed: all ERROR even if the partial log shows the intended FAIL)."""
import sys, os, json, re

def load_mutant(path, mid):
    return [m for m in json.load(open(path)) if m['id'] == mid][0]

def validate(scn, log_text, json_path, exit_code):
    """returns (ok, reason, data)"""
    try: rc = int(exit_code)
    except Exception: return False, f'exit code {exit_code!r} is not a number', None
    if rc not in (0, 1): return False, f'exit code {rc} ({"timeout" if rc == 124 else "uncaught crash" if rc == 2 else "killed by a signal" if rc >= 128 else "unexpected"}): the run did not end by its own assertions', None
    if not os.path.isfile(json_path): return False, 'results JSON is missing (the run did not reach the end)', None
    try: d = json.load(open(json_path, encoding='utf-8'))
    except Exception as e: return False, f'results JSON does not parse ({e})', None
    if not isinstance(d, dict): return False, 'results JSON is not an object', None
    if d.get('complete') is not True: return False, 'results JSON has no completion marker', None
    if str(d.get('only', '')) != str(scn): return False, f"results JSON is for scenario {d.get('only')!r}, expected {scn!r}", None
    t, f, r = d.get('total'), d.get('failed'), d.get('results')
    if not (isinstance(t, int) and not isinstance(t, bool) and isinstance(f, int) and not isinstance(f, bool) and isinstance(r, list)): return False, 'results JSON has wrong types for total/failed/results', None
    if len(r) != t: return False, f'results JSON total={t} but {len(r)} results', None
    for x in r:
        if not (isinstance(x, dict) and isinstance(x.get('name'), str) and isinstance(x.get('ok'), bool)): return False, 'a result lacks a string name or a boolean ok', None
    nf = sum(1 for x in r if not x['ok'])
    if nf != f: return False, f'results JSON failed={f} but {nf} results are not ok', None
    m = re.search(r'PHASE 3B: (\d+) / (\d+) pass', log_text)
    if not m: return False, 'the log has no final "PHASE 3B: P / T pass" line', None
    if int(m.group(2)) != t or int(m.group(1)) != t - f: return False, f'the log says {m.group(1)} / {m.group(2)} but the JSON says {t - f} / {t}', None
    if (rc == 0) != (f == 0): return False, f'exit code {rc} disagrees with failed={f}', None
    if t == 0: return False, 'no checks were run', None
    return True, 'valid and complete', d

def verdict(mutant, exit_code, log_text, json_path):
    ok, why, d = validate(mutant['scenario'], log_text, json_path, exit_code)
    if not ok: return 'ERROR', why, []
    failed = [x['name'] for x in d['results'] if not x['ok']]
    if not failed: return 'SURVIVED', 'the scenario passed completely on the mutant', []
    if any(mutant['needle'] in n for n in failed): return 'DETECTED', f'{len(failed)} check(s) failed, including the intended one', failed   # FULL names, never truncated
    return 'SURVIVED-OTHER', f'{len(failed)} other check(s) failed but NONE names the intended safeguard', failed

def control(mutants, scn, exit_code, log_text, json_path):
    ok, why, d = validate(scn, log_text, json_path, exit_code)
    if not ok: return False, 'control run invalid: ' + why
    if d['failed']: return False, f"the UNMUTATED app fails {d['failed']} check(s) of scenario {scn}: " + '; '.join(x['name'][:90] for x in d['results'] if not x['ok'])[:400]
    passing = [x['name'] for x in d['results']]
    miss = [m['id'] for m in mutants if str(m['scenario']) == str(scn) and not any(m['needle'] in n for n in passing)]
    if miss: return False, 'needle matches no passing check for: ' + ', '.join(miss)
    return True, f"unmutated app passed all {d['total']} checks; every needle of the scenario matches a passing check"

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'verdict':
        mp, mid, lg, js, rc = sys.argv[2:7]
        m = load_mutant(mp, mid); text = open(lg, encoding='utf-8', errors='replace').read() if os.path.isfile(lg) else ''
        v, why, failed = verdict(m, rc, text, js)
        extra = ''
        try: dd = json.load(open(js)); extra = f" total={dd.get('total')} failed={dd.get('failed')}"
        except Exception: extra = ' total=? failed=?'
        print(f"{mid}: scenario S{m['scenario']} exit={rc}{extra} VERDICT={v} ({why}) | {m['desc']}")
        for n in failed[:5]: print('      failed:', n[:170] + ('…' if len(n) > 170 else ''))   # display truncation ONLY
        sys.exit({'DETECTED': 0, 'SURVIVED': 1, 'SURVIVED-OTHER': 1, 'ERROR': 3}[v])
    if mode == 'control':
        mp, scn, lg, js, rc = sys.argv[2:7]
        text = open(lg, encoding='utf-8', errors='replace').read() if os.path.isfile(lg) else ''
        ok, why = control(json.load(open(mp)), scn, rc, text, js)
        print(f"control S{scn}: {'OK' if ok else 'ERROR'} - {why}"); sys.exit(0 if ok else 3)
    sys.exit(2)
