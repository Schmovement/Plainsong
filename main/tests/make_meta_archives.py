#!/usr/bin/env python3
"""Phase 3A: builds internally consistent (CRC/manifest refreshed) variants of a backup that carries the new additive track fields.
  python3 -I make_meta_archives.py <backup-with-origMeta.zip> <out-dir>
writes <out-dir>/<id>.zip and <out-dir>/cases.json = [{id, desc, file, expect: 'ACCEPT'|'REFUSE', needle}]. Stdlib only, no app code.
The strict reader must ACCEPT the unknown-extra-field and valid variants and REFUSE every malformed genre/origMeta variant ("invalid fields")."""
import sys, os, json, zipfile, zlib, collections, copy

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(src)
GOOD = collections.OrderedDict((i.filename, z.read(i.filename)) for i in z.infolist())
hexcrc = lambda d: '%08x' % (zlib.crc32(d) & 0xffffffff)
dump = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def build(cid, mut):
    e = collections.OrderedDict(GOOD)
    man = json.loads(e['manifest.json'])
    tracks = json.loads(e['data/tracks.json'])
    mut(tracks)
    e['data/tracks.json'] = dump(tracks)
    for f in man['files']:
        if f['path'] in e:
            f['bytes'] = len(e[f['path']]); f['crc32'] = hexcrc(e[f['path']])
    man['payloadBytes'] = sum(len(d) for n, d in e.items() if n != 'manifest.json')
    e['manifest.json'] = (json.dumps(man, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    path = os.path.join(out, cid + '.zip')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as zz:
        for n, d in e.items():
            zi = zipfile.ZipInfo(n, (2026, 11, 6, 0, 0, 0)); zi.compress_type = zipfile.ZIP_STORED; zz.writestr(zi, d)


def first(tracks, key):
    for t in tracks:
        if key in t:
            return t
    raise SystemExit('no track with ' + key)


cases = []
def case(cid, desc, mut, expect):
    build(cid, mut); cases.append({'id': cid, 'desc': desc, 'file': cid + '.zip', 'expect': expect, 'needle': 'invalid fields' if expect == 'REFUSE' else ''})

def setk(key, fn):
    def m(tr):
        t = first(tr, key); fn(t)
    return m

case('ok-unchanged-resealed', 'the same data, re-sealed by this helper (proves the helper itself yields an accepted archive)', lambda tr: None, 'ACCEPT')
case('ok-unknown-extra-field', 'an unknown extra field on a track that also has origMeta/genre is kept, as for any record', setk('origMeta', lambda t: t.__setitem__('x_future_3a', {'n': [1, 2], 's': 'ß'})), 'ACCEPT')
case('bad-origmeta-number', 'origMeta is a number', setk('origMeta', lambda t: t.__setitem__('origMeta', 5)), 'REFUSE')
case('bad-origmeta-null', 'origMeta is null', setk('origMeta', lambda t: t.__setitem__('origMeta', None)), 'REFUSE')
case('bad-origmeta-array', 'origMeta is a list', setk('origMeta', lambda t: t.__setitem__('origMeta', ['a', 'b', 'c', 'd'])), 'REFUSE')
case('bad-origmeta-missing-genre', 'origMeta lacks genre', setk('origMeta', lambda t: t['origMeta'].pop('genre')), 'REFUSE')
case('bad-origmeta-title-number', 'origMeta.title is a number', setk('origMeta', lambda t: t['origMeta'].__setitem__('title', 7)), 'REFUSE')
case('bad-origmeta-extra-key', 'origMeta has an unknown key', setk('origMeta', lambda t: t['origMeta'].__setitem__('rating', 'x')), 'REFUSE')
case('bad-genre-number', 'genre is a number', setk('genre', lambda t: t.__setitem__('genre', 5)), 'REFUSE')
case('bad-genre-null', 'genre is null', setk('genre', lambda t: t.__setitem__('genre', None)), 'REFUSE')
json.dump(cases, open(os.path.join(out, 'cases.json'), 'w'), indent=1)
print(len(cases), 'archives written')
