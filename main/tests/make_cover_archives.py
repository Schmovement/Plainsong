#!/usr/bin/env python3
"""Phase 3B: builds internally consistent (CRC/manifest refreshed) variants of a backup that carries the additive `origCover` track field.
  python3 -I make_cover_archives.py <backup-with-origCover.zip> <out-dir>
writes <out-dir>/<id>.zip and <out-dir>/cases.json = [{id, desc, file, expect: 'ACCEPT'|'REFUSE', needle}]. Stdlib only, no app code.
The strict reader must ACCEPT valid origCover values ('' / png-jpeg data URL / http(s) URL) and REFUSE every malformed one ("invalid fields")."""
import sys, os, json, zipfile, zlib, collections, base64

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(src)
GOOD = collections.OrderedDict((i.filename, z.read(i.filename)) for i in z.infolist())
hexcrc = lambda d: '%08x' % (zlib.crc32(d) & 0xffffffff)
dump = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
PNG1 = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='


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
    with zipfile.ZipFile(os.path.join(out, cid + '.zip'), 'w', zipfile.ZIP_STORED) as zz:
        for n, d in e.items():
            zi = zipfile.ZipInfo(n, (2026, 11, 7, 0, 0, 0)); zi.compress_type = zipfile.ZIP_STORED; zz.writestr(zi, d)


def first(tracks, key):
    for t in tracks:
        if key in t:
            return t
    raise SystemExit('no track with ' + key)


cases = []
def case(cid, desc, mut, expect):
    build(cid, mut); cases.append({'id': cid, 'desc': desc, 'file': cid + '.zip', 'expect': expect, 'needle': 'invalid fields' if expect == 'REFUSE' else ''})

def setk(fn):
    def m(tr):
        fn(first(tr, 'origCover'))
    return m

case('ok-unchanged-resealed', 'the same data, re-sealed by this helper (proves the helper yields an accepted archive)', lambda tr: None, 'ACCEPT')
case('ok-orig-empty', "origCover is '' (the song had no cover before the first edit)", setk(lambda t: t.__setitem__('origCover', '')), 'ACCEPT')
case('ok-orig-png-data', 'origCover is an embedded png data URL', setk(lambda t: t.__setitem__('origCover', PNG1)), 'ACCEPT')
case('ok-orig-http', 'origCover is an http(s) address', setk(lambda t: t.__setitem__('origCover', 'https://example.invalid/original.jpg')), 'ACCEPT')
GIF1 = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
WEBP1 = 'data:image/webp;base64,UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA=='
def _big_png():
    import zlib, hashlib, struct
    w = h = 520; rows = []; ctr = 0
    for y in range(h):
        r = bytearray([0])
        while len(r) < w * 3 + 1:
            r += hashlib.sha256(b'3b-big-%d' % ctr).digest(); ctr += 1
        rows.append(bytes(r[:w * 3 + 1]))
    def ch(k, d):
        return struct.pack('>I', len(d)) + k + d + struct.pack('>I', zlib.crc32(k + d) & 0xffffffff)
    return 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(b''.join(rows), 1)) + ch(b'IEND', b'')).decode()
BIG = _big_png()
assert len(BIG) > 700000
case('ok-orig-gif-data', 'legacy origCover is an embedded GIF data URL', setk(lambda t: t.__setitem__('origCover', GIF1)), 'ACCEPT')
case('ok-orig-webp-data', 'legacy origCover is an embedded WebP data URL', setk(lambda t: t.__setitem__('origCover', WEBP1)), 'ACCEPT')
case('ok-orig-over-700k', 'legacy origCover is a real PNG data URL of more than 700,000 characters (the cap applies only to NEW covers)', setk(lambda t: t.__setitem__('origCover', BIG)), 'ACCEPT')
case('ok-unknown-extra-field', 'an unknown extra field next to origCover is kept as for any record', setk(lambda t: t.__setitem__('x_future_3b', {'n': [1, 2], 's': 'ß'})), 'ACCEPT')
case('bad-orig-number', 'origCover is a number', setk(lambda t: t.__setitem__('origCover', 5)), 'REFUSE')
case('bad-orig-null', 'origCover is null', setk(lambda t: t.__setitem__('origCover', None)), 'REFUSE')
case('bad-orig-array', 'origCover is a list', setk(lambda t: t.__setitem__('origCover', ['x'])), 'REFUSE')
case('bad-orig-object', 'origCover is an object', setk(lambda t: t.__setitem__('origCover', {'data': PNG1})), 'REFUSE')
case('bad-orig-bool', 'origCover is true', setk(lambda t: t.__setitem__('origCover', True)), 'REFUSE')
case('bad-orig-svg-data', 'origCover is an SVG data URL (script inside)', setk(lambda t: t.__setitem__('origCover', 'data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+')), 'REFUSE')
case('bad-orig-javascript', 'origCover is a javascript: address', setk(lambda t: t.__setitem__('origCover', 'javascript:alert(1)')), 'REFUSE')
case('bad-orig-ftp', 'origCover is an ftp: address', setk(lambda t: t.__setitem__('origCover', 'ftp://example.invalid/a.png')), 'REFUSE')
case('bad-orig-base64-chars', 'origCover is a png data URL with characters outside base64', setk(lambda t: t.__setitem__('origCover', 'data:image/png;base64,@@@@')), 'REFUSE')
case('bad-orig-html', 'origCover is html text', setk(lambda t: t.__setitem__('origCover', '<img src=x onerror=alert(1)>')), 'REFUSE')
case('bad-cover-svg-data', 'cover itself is an SVG data URL (the existing rule must still refuse it)', setk(lambda t: t.__setitem__('cover', 'data:image/svg+xml;base64,PHN2Zy8+')), 'REFUSE')
json.dump(cases, open(os.path.join(out, 'cases.json'), 'w'), indent=1)
print(len(cases), 'archives written')
