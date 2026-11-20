import json
base='/home/claude/w4/ev-mut41b/'
ms=json.load(open(base+'mutants.json.AS-GENERATED')); bad=0
ctl={s:json.load(open(base+f'control-R{s}.json')) for s in {m['scenario'] for m in ms}}
for s,c in ctl.items():
    assert c['complete'] and c['failed']==0 and c['scenariosAborted']==[] and not any('ABORTED with' in x['name'] for x in c['results']),s
for m in ms:
    d=json.load(open(base+m['id']+'.json')); c=ctl[m['scenario']]
    cn={x['name'] for x in c['results']}; dn={x['name'] for x in d['results']}
    ok = d['complete'] is True and d['scenariosAborted']==[] and d['scenariosFinished']==[m['scenario']] and dn==cn and len(dn)==d['total'] and not any('ABORTED with' in n for n in dn)
    fails={x['name'] for x in d['results'] if not x['ok']}
    res=lambda nd:[n for n in cn if nd in n]
    mf=all(len(res(n))==1 and res(n)[0] in fails for n in m['must_fail']); mp=all(len(res(n))==1 and res(n)[0] not in fails for n in m['must_pass'])
    if not(ok and mf and mp): bad+=1; print('PROBLEM',m['id'],ok,mf,mp)
print('independent re-check:',len(ms),'mutants,',bad,'problems; control sizes',{s:c['total'] for s,c in sorted(ctl.items())})
