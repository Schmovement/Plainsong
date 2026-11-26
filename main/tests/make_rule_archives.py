#!/usr/bin/env python3
"""Phase 5: builds internally consistent (CRC/manifest refreshed) variants of a backup that carries the additive optional playlist field `rule` (a smart playlist).
  python3 -I make_rule_archives.py <backup-with-a-smart-playlist.zip> <out-dir>
writes <out-dir>/<id>.zip and <out-dir>/cases.json = [{id, desc, file, expect: 'ACCEPT'|'REFUSE', needle}]. Stdlib only, no app code; the ACCEPT/REFUSE verdict of every case is
fixed HERE from the documented grammar (BACKUP_FORMAT.md), never read back from the app. Every REFUSE case must be refused naming `needle` and must change nothing."""
import sys, os, json, zipfile, zlib, collections, copy

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(src)
GOOD = collections.OrderedDict((i.filename, z.read(i.filename)) for i in z.infolist())
hexcrc = lambda d: '%08x' % (zlib.crc32(d) & 0xffffffff)
dump = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
NEG0 = '__NEG0__'    # placeholder replaced by the literal JSON text -0 (python can not dump that as a number)
base_pl = json.loads(GOOD['data/playlists.json'])
# The cases below must not depend on the app's own export being right (a defective export that drops the rule would otherwise stop the generator and hide every other case):
# when the base backup has no smart playlist (or no manual one) this generator adds a known-good record of its own.
if not any('rule' in p for p in base_pl):
    base_pl.append({'id': 'gen-smart-0', 'name': 'Generated smart', 'ids': [], 'created': 1, 'rule': {'v': 1, 'match': 'all', 'conds': [{'f': 'plays', 'op': 'gte', 'v': 1}], 'sort': {'by': 'plays', 'dir': 'desc'}, 'limit': 25}})
if not any('rule' not in p for p in base_pl):
    base_pl.append({'id': 'gen-manual-0', 'name': 'Generated manual', 'ids': [], 'created': 2})
if len(base_pl) != len(json.loads(GOOD['data/playlists.json'])): base_pl.sort(key=lambda p: p['id'])   # the reader wants ascending store-key order
GOOD['data/playlists.json'] = dump(base_pl)
SI = next(i for i, p in enumerate(base_pl) if 'rule' in p)       # the smart playlist all cases mutate
assert any('rule' not in p for p in base_pl), 'the base backup must also hold a manual playlist'


def build(cid, mut, raw_subs=()):
    e = collections.OrderedDict(GOOD)
    man = json.loads(e['manifest.json'])
    pls = json.loads(e['data/playlists.json'])
    mut(pls)
    pj = dump(pls)
    for a, b in raw_subs:
        assert a.encode() in pj, (cid, a)
        pj = pj.replace(a.encode(), b.encode())
    e['data/playlists.json'] = pj
    man['counts']['playlists'] = len(pls)
    for f in man['files']:
        if f['path'] in e:
            f['bytes'] = len(e[f['path']]); f['crc32'] = hexcrc(e[f['path']])
    man['payloadBytes'] = sum(len(d) for n, d in e.items() if n != 'manifest.json')
    e['manifest.json'] = (json.dumps(man, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with zipfile.ZipFile(os.path.join(out, cid + '.zip'), 'w', zipfile.ZIP_STORED) as zz:
        for n, d in e.items():
            zi = zipfile.ZipInfo(n, (2026, 11, 10, 0, 0, 0)); zi.compress_type = zipfile.ZIP_STORED; zz.writestr(zi, d)


cases = []
def case(cid, desc, mut, expect, subs=()):
    build(cid, mut, subs)
    cases.append({'id': cid, 'desc': desc, 'file': cid + '.zip', 'expect': expect, 'needle': 'Some playlists are invalid' if expect == 'REFUSE' else ''})

def rule(fn):
    def m(pls):
        fn(pls[SI]['rule'])
    return m
def pl(fn):
    def m(pls):
        fn(pls[SI])
    return m
def setrule(r):
    return pl(lambda p: p.__setitem__('rule', r))
def cond(f, op, v):
    return {'f': f, 'op': op, 'v': v}
def R(conds, match='all', by='added', dir='desc', limit=0):
    return {'v': 1, 'match': match, 'conds': conds, 'sort': {'by': by, 'dir': dir}, 'limit': limit}

# ---- accepted
case('ok-unchanged-resealed', 'the same data re-sealed by this helper (proves the helper yields an accepted archive; keeps every smart and manual playlist exactly)', lambda p: None, 'ACCEPT')
case('ok-old-archive-no-rule', 'an OLD-style archive: no playlist carries a rule (it restores with no rule invented anywhere)', lambda pls: [p.pop('rule', None) for p in pls] and None, 'ACCEPT')
allops = [cond('plays', o, 3) for o in ('eq', 'ne', 'gt', 'gte', 'lt', 'lte')] + [cond('rating', 'gte', 0), cond('duration', 'lte', 359999)]
case('ok-8-conditions-numeric', 'eight numeric conditions (the maximum), every numeric operator, rating 0 and duration 359999', setrule(R(allops, 'any', 'duration', 'asc', 500)), 'ACCEPT')
case('ok-time-text-bool-kind', 'time within/before at 1 and 3650 days, text contains/notContains/is (with non-ASCII), liked true/false, kind local/web, sort by every key kind', setrule(R([cond('added', 'within', 1), cond('last', 'before', 3650), cond('title', 'contains', 'ünï ✓'), cond('artist', 'notContains', 'x'), cond('album', 'is', 'Älbum'), cond('genre', 'contains', 'g'), cond('liked', 'is', False), cond('kind', 'is', 'web')], 'all', 'title', 'asc', 1)), 'ACCEPT')
case('ok-no-conditions', 'no conditions (the whole library), limit 0', setrule(R([])), 'ACCEPT')
case('ok-text-100-chars', 'a text value of exactly 100 characters', setrule(R([cond('title', 'contains', 'a' * 100)])), 'ACCEPT')
case('ok-sort-keys', 'sort by last, rating and album, ascending', setrule(R([], 'all', 'last', 'asc', 0)), 'ACCEPT')
case('ok-unknown-playlist-field', 'an unknown extra field on the smart playlist record (kept as for any record; not part of the rule)', pl(lambda p: p.__setitem__('x_future_5', {'n': [1, 2], 's': 'ß'})), 'ACCEPT')
case('ok-plays-3.0-literal', 'the JSON literal 3.0 for a value: JSON.parse reads the whole number 3 (documented tolerance)', setrule(R([cond('plays', 'gte', 3)])), 'ACCEPT', subs=[('"v":3}', '"v":3.0}')])

# ---- refused
def bad(cid, desc, r=None, mut=None, subs=()):
    case(cid, desc, mut or setrule(r), 'REFUSE', subs)
good = lambda: copy.deepcopy(R([cond('plays', 'gte', 1)], 'all', 'plays', 'desc', 25))
def withk(fn):
    def m(pls):
        r = good(); fn(r); pls[SI]['rule'] = r
    return m
bad('bad-rule-null', 'rule null', None)
bad('bad-rule-list', 'rule is a list', [])
bad('bad-rule-text', 'rule is text', 'most played')
bad('bad-rule-number', 'rule is a number', 7)
bad('bad-rule-empty-object', 'rule {} (every part missing)', {})
bad('bad-version-2', 'rule version 2', mut=withk(lambda r: r.__setitem__('v', 2)))
bad('bad-version-text', 'rule version "1" (text)', mut=withk(lambda r: r.__setitem__('v', '1')))
bad('bad-version-missing', 'rule without v', mut=withk(lambda r: r.pop('v')))
bad('bad-match-some', 'match "some"', mut=withk(lambda r: r.__setitem__('match', 'some')))
bad('bad-match-uppercase', 'match "ALL"', mut=withk(lambda r: r.__setitem__('match', 'ALL')))
bad('bad-match-missing', 'rule without match', mut=withk(lambda r: r.pop('match')))
bad('bad-extra-top-key', 'an extra key in the rule', mut=withk(lambda r: r.__setitem__('script', 'x')))
bad('bad-conds-not-list', 'conds is an object', mut=withk(lambda r: r.__setitem__('conds', {})))
bad('bad-conds-missing', 'rule without conds', mut=withk(lambda r: r.pop('conds')))
bad('bad-9-conditions', 'nine conditions (the maximum is eight)', mut=withk(lambda r: r.__setitem__('conds', [cond('plays', 'gte', i) for i in range(9)])))
bad('bad-cond-not-object', 'a condition that is a number', mut=withk(lambda r: r.__setitem__('conds', [5])))
bad('bad-cond-null', 'a condition that is null', mut=withk(lambda r: r.__setitem__('conds', [None])))
bad('bad-cond-missing-op', 'a condition without op', mut=withk(lambda r: r['conds'][0].pop('op')))
bad('bad-cond-missing-v', 'a condition without v', mut=withk(lambda r: r['conds'][0].pop('v')))
bad('bad-cond-missing-f', 'a condition without f', mut=withk(lambda r: r['conds'][0].pop('f')))
bad('bad-cond-extra-key', 'a condition with an extra key', mut=withk(lambda r: r['conds'][0].__setitem__('code', '1')))
bad('bad-field-unknown', 'unknown field "bpm"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('bpm', 'gt', 100))))
bad('bad-field-proto', 'field "__proto__"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('__proto__', 'eq', 1))))
bad('bad-field-constructor', 'field "constructor"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('constructor', 'eq', 1))))
bad('bad-field-number', 'field is a number', mut=withk(lambda r: r['conds'].__setitem__(0, cond(5, 'eq', 1))))
bad('bad-op-wrong-for-field', 'plays "contains"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'contains', 1))))
bad('bad-op-time-on-num', 'duration "within"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('duration', 'within', 5))))
bad('bad-op-text-gt', 'title "gt"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('title', 'gt', 'a'))))
bad('bad-op-unknown', 'plays "between"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'between', 1))))
bad('bad-op-bool-eq', 'liked "eq"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('liked', 'eq', True))))
bad('bad-plays-text', 'plays value "5" (text)', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'gte', '5'))))
bad('bad-plays-negative', 'plays value -1', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'gte', -1))))
bad('bad-plays-fraction', 'plays value 1.5', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'gte', 1.5))))
bad('bad-plays-neg-zero', 'plays value -0', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'gte', 99))), subs=[('"v":99}', '"v":-0}')])
bad('bad-plays-null', 'plays value null', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'gte', None))))
bad('bad-plays-bool', 'plays value true', mut=withk(lambda r: r['conds'].__setitem__(0, cond('plays', 'gte', True))))
bad('bad-rating-6', 'rating value 6', mut=withk(lambda r: r['conds'].__setitem__(0, cond('rating', 'eq', 6))))
bad('bad-duration-360000', 'duration value 360000', mut=withk(lambda r: r['conds'].__setitem__(0, cond('duration', 'gt', 360000))))
bad('bad-duration-text-5:00', 'duration value "5:00" (text; the rule stores whole seconds)', mut=withk(lambda r: r['conds'].__setitem__(0, cond('duration', 'gt', '5:00'))))
bad('bad-days-0', 'added within 0 days', mut=withk(lambda r: r['conds'].__setitem__(0, cond('added', 'within', 0))))
bad('bad-days-3651', 'added before 3651 days', mut=withk(lambda r: r['conds'].__setitem__(0, cond('added', 'before', 3651))))
bad('bad-days-fraction', 'last within 1.5 days', mut=withk(lambda r: r['conds'].__setitem__(0, cond('last', 'within', 1.5))))
bad('bad-text-empty', 'title contains ""', mut=withk(lambda r: r['conds'].__setitem__(0, cond('title', 'contains', ''))))
bad('bad-text-101-chars', 'a text value of 101 characters', mut=withk(lambda r: r['conds'].__setitem__(0, cond('title', 'contains', 'a' * 101))))
bad('bad-text-leading-space', 'a text value with a leading space (stored values are trimmed)', mut=withk(lambda r: r['conds'].__setitem__(0, cond('artist', 'is', ' x'))))
bad('bad-text-trailing-space', 'a text value with a trailing space', mut=withk(lambda r: r['conds'].__setitem__(0, cond('artist', 'is', 'x '))))
bad('bad-text-newline', 'a text value with a line break', mut=withk(lambda r: r['conds'].__setitem__(0, cond('album', 'contains', 'a\nb'))))
bad('bad-text-number', 'a text value that is a number', mut=withk(lambda r: r['conds'].__setitem__(0, cond('genre', 'contains', 5))))
bad('bad-liked-text', 'liked value "yes"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('liked', 'is', 'yes'))))
bad('bad-liked-number', 'liked value 1', mut=withk(lambda r: r['conds'].__setitem__(0, cond('liked', 'is', 1))))
bad('bad-kind-remote', 'kind "remote"', mut=withk(lambda r: r['conds'].__setitem__(0, cond('kind', 'is', 'remote'))))
bad('bad-sort-missing', 'rule without sort', mut=withk(lambda r: r.pop('sort')))
bad('bad-sort-not-object', 'sort is text', mut=withk(lambda r: r.__setitem__('sort', 'plays')))
bad('bad-sort-key-unknown', 'sort by "genre" (not an allowed sort field)', mut=withk(lambda r: r['sort'].__setitem__('by', 'genre')))
bad('bad-sort-key-liked', 'sort by "liked"', mut=withk(lambda r: r['sort'].__setitem__('by', 'liked')))
bad('bad-sort-dir', 'sort direction "up"', mut=withk(lambda r: r['sort'].__setitem__('dir', 'up')))
bad('bad-sort-extra-key', 'an extra key in sort', mut=withk(lambda r: r['sort'].__setitem__('nulls', 'last')))
bad('bad-limit-501', 'limit 501', mut=withk(lambda r: r.__setitem__('limit', 501)))
bad('bad-limit-negative', 'limit -1', mut=withk(lambda r: r.__setitem__('limit', -1)))
bad('bad-limit-fraction', 'limit 2.5', mut=withk(lambda r: r.__setitem__('limit', 2.5)))
bad('bad-limit-text', 'limit "5"', mut=withk(lambda r: r.__setitem__('limit', '5')))
bad('bad-limit-missing', 'rule without limit', mut=withk(lambda r: r.pop('limit')))
bad('bad-smart-with-songs', 'a smart playlist that also carries hand-picked ids', mut=pl(lambda p: p.__setitem__('ids', ['some-song-id'])))
bad('bad-smart-ids-text', 'a smart playlist whose ids is text', mut=pl(lambda p: p.__setitem__('ids', 'x')))

json.dump(cases, open(os.path.join(out, 'cases.json'), 'w'), indent=1)
print(len(cases), 'cases:', sum(c['expect'] == 'ACCEPT' for c in cases), 'accept,', sum(c['expect'] == 'REFUSE' for c in cases), 'refuse')
