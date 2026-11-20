#!/usr/bin/env python3
"""Phase 4: builds internally consistent (CRC/manifest refreshed) variants of a backup that carries the additive optional track field `rating`.
  python3 -I make_rating_archives.py <backup-with-ratings.zip> <out-dir>
writes <out-dir>/<id>.zip and <out-dir>/cases.json = [{id, desc, file, expect: 'ACCEPT'|'REFUSE', needle, ratings: {track-id: value-or-null}}]. Stdlib only, no app code.
`ratings` is what the strict reader must store for an ACCEPT case (null = the field must stay ABSENT, 0 = present zero). Every REFUSE case must be refused naming `needle` (track records: "invalid fields"; session/history snapshots: "saved session or history is invalid") and the `reason` text."""
import sys, os, json, zipfile, zlib, collections

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(src)
GOOD = collections.OrderedDict((i.filename, z.read(i.filename)) for i in z.infolist())
hexcrc = lambda d: '%08x' % (zlib.crc32(d) & 0xffffffff)
dump = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
NEG0, FLOAT3 = '__NEG0__', '__FLOAT3__'    # placeholders replaced by the literal JSON text -0 / 3.0 (python can not dump those as numbers)


def build(cid, mut, raw_subs=()):
    e = collections.OrderedDict(GOOD)
    man = json.loads(e['manifest.json'])
    tracks = json.loads(e['data/tracks.json']); kv = json.loads(e['data/kv.json'])
    mut(tracks, kv)
    tj, kj = dump(tracks), dump(kv)
    for a, b in raw_subs:
        tj = tj.replace(a.encode(), b.encode()); kj = kj.replace(a.encode(), b.encode())
    e['data/tracks.json'], e['data/kv.json'] = tj, kj
    for f in man['files']:
        if f['path'] in e:
            f['bytes'] = len(e[f['path']]); f['crc32'] = hexcrc(e[f['path']])
    man['payloadBytes'] = sum(len(d) for n, d in e.items() if n != 'manifest.json')
    e['manifest.json'] = (json.dumps(man, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with zipfile.ZipFile(os.path.join(out, cid + '.zip'), 'w', zipfile.ZIP_STORED) as zz:
        for n, d in e.items():
            zi = zipfile.ZipInfo(n, (2026, 11, 8, 0, 0, 0)); zi.compress_type = zipfile.ZIP_STORED; zz.writestr(zi, d)
    return {t['id']: (t['rating'] if 'rating' in t and isinstance(t['rating'], int) and not isinstance(t['rating'], bool) else None) for t in tracks}


cases = []
def case(cid, desc, mut, expect, subs=(), ratings=None, needle='invalid fields'):
    r = build(cid, mut, subs)
    if ratings is not None: r = ratings(r)
    cases.append({'id': cid, 'desc': desc, 'file': cid + '.zip', 'expect': expect, 'needle': needle if expect == 'REFUSE' else '', 'reason': 'rating must be a whole number from 0 to 5' if expect == 'REFUSE' else '', 'ratings': r if expect == 'ACCEPT' else None})

def on(i, fn):
    def m(tr, kv):
        fn(tr[i])
    return m
def setr(i, v):
    return on(i, lambda t: t.__setitem__('rating', v))

case('ok-unchanged-resealed', 'the same data re-sealed by this helper (proves the helper yields an accepted archive; keeps present, zero and absent exactly)', lambda tr, kv: None, 'ACCEPT')
def allvals(tr, kv):
    for i, t in enumerate(tr):
        t.pop('rating', None)
    for i, v in enumerate([0, 1, 2, 3, 4, 5]):
        if i < len(tr): tr[i]['rating'] = v
case('ok-all-values', 'ratings 0,1,2,3,4,5 on the first six songs (the source has 8), the others absent', allvals, 'ACCEPT')
case('ok-no-rating-anywhere', 'an OLD-style archive: no song carries a rating (it must restore with no rating field invented)', lambda tr, kv: [t.pop('rating', None) for t in tr] and None, 'ACCEPT')
case('ok-rating-zero-present', 'rating 0 on a song that had none (present zero is kept as zero, not dropped)', setr(0, 0), 'ACCEPT')
case('ok-rating-3.0-literal', 'the JSON literal 3.0 for a rating: JSON.parse reads it as the whole number 3, so the browser accepts it and stores 3 (documented tolerance; the Python reference reads a float)', setr(0, FLOAT3), 'ACCEPT', subs=[('"' + FLOAT3 + '"', '3.0')], ratings=lambda r: {k: (3 if i == 0 else v) for i, (k, v) in enumerate(r.items())})
case('ok-unknown-extra-field', 'an unknown extra field next to rating is kept as for any record', on(0, lambda t: (t.__setitem__('rating', 4), t.__setitem__('x_future_4', {'n': [1, 2], 's': 'ß'}))), 'ACCEPT')
for cid, desc, v in [('bad-rating-6', 'rating 6 (above the range)', 6), ('bad-rating-neg1', 'rating -1', -1), ('bad-rating-2.5', 'rating 2.5', 2.5), ('bad-rating-0.5', 'rating 0.5', 0.5), ('bad-rating-5.000001', 'rating 5.000001', 5.000001),
                     ('bad-rating-text-3', 'rating "3" (text)', '3'), ('bad-rating-text-five', 'rating "five"', 'five'), ('bad-rating-null', 'rating null', None), ('bad-rating-true', 'rating true', True), ('bad-rating-false', 'rating false', False),
                     ('bad-rating-array', 'rating [3]', [3]), ('bad-rating-object', 'rating {"stars":3}', {'stars': 3}), ('bad-rating-1e308', 'rating 1e308 (a whole number far out of range)', 1e308), ('bad-rating-bigint', 'rating 9007199254740993', 9007199254740993)]:
    case(cid, desc, setr(0, v), 'REFUSE')
case('bad-rating-neg-zero', 'rating -0 (the literal -0)', setr(0, NEG0), 'REFUSE', subs=[('"' + NEG0 + '"', '-0')])
case('bad-rating-on-web-song', 'a saved web song with rating 7', setr(len(json.loads(GOOD['data/tracks.json'])) - 1, 7), 'REFUSE')
def histsnap(tr, kv):
    for e in kv:
        if e['key'] == 'hist':
            for x in e['value']:
                if 'snap' in x: x['snap']['rating'] = 9; return
    raise SystemExit('no history snapshot in the source backup')
case('bad-rating-in-history-snapshot', 'a history entry\'s saved web-song snapshot carries rating 9 (the same track rule applies to snapshots)', histsnap, 'REFUSE', needle='saved session or history is invalid')
def sessweb(tr, kv):
    for e in kv:
        if e['key'] == 'session' and e['value'].get('webs'):
            e['value']['webs'][0]['rating'] = 'x'; return
    raise SystemExit('no session web song in the source backup')
case('bad-rating-in-session-web', 'the saved session\'s queued web song carries rating "x"', sessweb, 'REFUSE', needle='saved session or history is invalid')
json.dump(cases, open(os.path.join(out, 'cases.json'), 'w'), indent=1)
print(len(cases), 'archives written')
