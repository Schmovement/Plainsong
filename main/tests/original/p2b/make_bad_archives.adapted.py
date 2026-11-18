#!/usr/bin/env python3
"""ADAPTED generator (the ORIGINAL is tests/original/p2a/make_bad_archives.py). Adds a replace= guard against vacuous cases, fixed lambdas, ok-hostile-text and k-secret-xss cases.
Generate hostile / corrupt / unsupported backup archives for the Phase 2A reader tests.
usage: python3 -I make_bad_archives.adapted.py <good-backup.zip> <out-dir>
Writes <out-dir>/<id>.zip for every case plus <out-dir>/cases.json:
  [{ "id", "desc", "expect": "<reason code>" | ["codes"...] | "ok" , "limits": {optional reader limit overrides} }]
A raw ZIP builder (no zipfile writer) lets each case damage exactly one thing, with every other CRC/size kept
valid, so a rejection can only come from the check that case is aimed at. "ok" cases must be ACCEPTED."""
import sys, os, json, zlib, struct, copy

good, outdir = sys.argv[1:3]
os.makedirs(outdir, exist_ok=True)

import zipfile
with zipfile.ZipFile(good) as z:
    ORDER = [i.filename for i in z.infolist()]
    FILES = {n: z.read(n) for n in ORDER}
DATA = ['data/tracks.json', 'data/playlists.json', 'data/kv.json', 'data/localstorage.json']
cases = []


def crc(b): return zlib.crc32(b) & 0xFFFFFFFF
def hx(n): return '%08x' % n
def J(o): return json.dumps(o, ensure_ascii=False, indent=1).encode('utf-8')


def build(entries, *, comment=b'', eocd=None, trailing=b'', pad=None):
    """entries: dicts with name(bytes), data, and optional overrides:
    cd_crc, lh_crc, cd_size, lh_size, cd_usize, flags, lh_flags, method, lh_method, cd_extra, lh_extra, cd_comment,
    lh_name, off (forced CD offset), ver"""
    out = bytearray(); cd = bytearray(); offs = []
    for e in entries:
        name = e['name'] if isinstance(e['name'], bytes) else e['name'].encode('utf-8')
        data = e['data']
        if pad and pad.get(e['name']): out += pad[e['name']]
        off = len(out); offs.append(off)
        c = crc(data); size = len(data)
        fl = e.get('flags', 0x0800); lfl = e.get('lh_flags', fl)
        lhn = e.get('lh_name', name)
        lh_extra = e.get('lh_extra', b'')
        out += struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, lfl, e.get('lh_method', e.get('method', 0)), 0, 0x21, e.get('lh_crc', c), e.get('lh_size', size), e.get('lh_size', size), len(lhn), len(lh_extra)) + lhn + lh_extra + data
        cd_extra = e.get('cd_extra', b''); cd_comment = e.get('cd_comment', b'')
        cd += struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 20, e.get('ver', 20), fl, e.get('method', 0), 0, 0x21, e.get('cd_crc', c), e.get('cd_size', size), e.get('cd_usize', e.get('cd_size', size)), len(name), len(cd_extra), len(cd_comment), 0, 0, 0, e.get('off', off)) + name + cd_extra + cd_comment
    cdoff = len(out); n = len(entries)
    e = dict(disk=0, cddisk=0, here=n, total=n, cdsize=len(cd), cdoff=cdoff); e.update(eocd or {})
    out += cd + struct.pack('<IHHHHIIH', 0x06054b50, e['disk'], e['cddisk'], e['here'], e['total'], e['cdsize'], e['cdoff'], len(comment)) + comment + trailing
    return bytes(out)


def entries_of(files, order=None):
    return [{'name': n, 'data': files[n]} for n in (order or list(files))]


def recompute(files, man_mut=None):
    """Return files with a manifest that agrees with the data (then optionally mutated to forge)."""
    f = dict(files); man = json.loads(files['manifest.json'])
    for p in DATA:
        for x in man['files']:
            if x['path'] == p: x['bytes'] = len(f[p]); x['crc32'] = hx(crc(f[p]))
    bl = sorted(n for n in f if n.startswith('blobs/'))
    for x, n in zip(man['blobs'], bl):
        x['path'] = n; x['bytes'] = len(f[n]); x['crc32'] = hx(crc(f[n]))
    try:
        man['counts']['tracks'] = len(json.loads(f['data/tracks.json'])); man['counts']['playlists'] = len(json.loads(f['data/playlists.json']))
        man['counts']['kv'] = len(json.loads(f['data/kv.json'])); man['counts']['localStorage'] = len(json.loads(f['data/localstorage.json']))
    except Exception: pass
    man['audioBytes'] = sum(len(f[n]) for n in bl); man['payloadBytes'] = sum(len(v) for k, v in f.items() if k != 'manifest.json')
    if man_mut: man_mut(man)
    f['manifest.json'] = J(man)
    return f


def add(cid, desc, expect, raw, limits=None):
    open(os.path.join(outdir, cid + '.zip'), 'wb').write(raw)
    c = {'id': cid, 'desc': desc, 'expect': expect}
    if limits: c['limits'] = limits
    cases.append(c)


def mut_json(name, fn, man_mut=None, files=None, replace=False):
    f = dict(files or FILES); v = json.loads(f[name]); r = fn(v)
    if r is not None and not replace: raise SystemExit('generator bug: the mutator for %s returned a value (list comprehension?) which would replace the whole file; pass replace=True if intended' % name)
    v = v if r is None else r
    f[name] = J(v); return recompute(f, man_mut)


def mut_tracks(fn, **k): return mut_json('data/tracks.json', fn, **k)
def mut_kv(fn, **k): return mut_json('data/kv.json', fn, **k)
def mut_man(fn): f = dict(FILES); return recompute(f, fn)
def ok_zip(f): return build(entries_of(f))
def kvmap(kv): return {x['key']: x for x in kv}


raw = open(good, 'rb').read()
# ---------------------------------------------------------------- accepted controls
add('ok-original', 'the untouched p1 archive', 'ok', raw)
add('ok-rebuilt', 'same content rebuilt by the raw builder (proves the builder is not the cause of rejections)', 'ok', ok_zip(FILES))
add('ok-extra-manifest-field', 'unknown extra manifest field is tolerated (forward compatible)', 'ok', ok_zip(mut_man(lambda m: m.update({'futureField': {'x': 1}}))))
add('ok-unknown-kv-key', 'an unknown, non-secret kv key is carried through as data', 'ok', ok_zip(mut_kv(lambda kv: kv.insert(0, {'key': 'aaa:new-setting', 'value': {'z': [1, 2]}}))))
add('ok-empty-ls', 'localstorage.json with no keys', 'ok', ok_zip(mut_json('data/localstorage.json', lambda v: {}, replace=True)))

# ---------------------------------------------------------------- container / ZIP structure
add('c-empty', 'empty file', 'not-zip', b'')
add('c-tiny', '10 bytes', 'not-zip', b'PK\x03\x04' + b'\0' * 6)
add('c-text', 'a text file', 'eocd', (b'this is not a zip file at all\n' * 20))
add('c-truncated-tail', 'last 40 bytes cut off', 'eocd', raw[:-40])
add('c-truncated-half', 'cut in the middle of the audio', 'eocd', raw[:len(raw) // 2])
add('c-trailing-junk', 'extra bytes after the end record', 'eocd', raw + b'JUNK')
add('c-comment', 'archive comment present (end record no longer at the tail)', 'eocd', build(entries_of(FILES), comment=b'hello'))
add('c-comment-len', 'end record at the tail but its comment length is non-zero', 'comment', raw[:-2] + b'\x05\x00')
add('c-zip64-count', 'ZIP64 marker in the entry count', 'zip64', build(entries_of(FILES), eocd={'here': 0xFFFF, 'total': 0xFFFF}))
add('c-zip64-offset', 'ZIP64 marker in the directory offset', 'zip64', build(entries_of(FILES), eocd={'cdoff': 0xFFFFFFFF}))
add('c-multidisk', 'disk number set', 'multidisk', build(entries_of(FILES), eocd={'disk': 1}))
add('c-count-mismatch', 'end record claims one more entry', ['cd-entry', 'directory', 'count'], build(entries_of(FILES), eocd={'here': len(FILES) + 1, 'total': len(FILES) + 1}))
add('c-count-too-few', 'end record claims only 3 entries', 'count', build(entries_of(FILES), eocd={'here': 3, 'total': 3}))
add('c-cdoff-wrong', 'directory offset wrong', 'directory', build(entries_of(FILES), eocd={'cdoff': 100}))
add('c-cdsize-wrong', 'directory size wrong', 'directory', build(entries_of(FILES), eocd={'cdsize': 10}))
b = bytearray(raw); i = raw.rfind(b'PK\x01\x02'); b[i + 2] = 0x09
add('c-cd-signature', 'central directory signature corrupted', 'cd-entry', bytes(b))
add('c-deflate', 'entries compressed (method 8)', 'method', build([dict(e, method=8) for e in entries_of(FILES)]))
add('c-encrypted', 'encryption flag set', 'flags', build([dict(e, flags=0x0801) for e in entries_of(FILES)]))
add('c-data-descriptor', 'data-descriptor flag set', 'flags', build([dict(e, flags=0x0808) for e in entries_of(FILES)]))
add('c-ver-high', 'version needed 63', 'flags', build([dict(e, ver=63) for e in entries_of(FILES)]))
es = entries_of(FILES); es[1] = dict(es[1], cd_extra=b'\x01\x02\x00\x00')
add('c-cd-extra', 'extra field in a directory entry', 'extra', build(es))
es = entries_of(FILES); es[2] = dict(es[2], cd_comment=b'note')
add('c-entry-comment', 'entry comment', 'extra', build(es))
es = entries_of(FILES); es[1] = dict(es[1], lh_extra=b'\x01\x02\x00\x00')
add('c-lh-extra', 'extra field in a local header (shifts the tiling, so the layout check fires first)', 'layout', build(es))
es = entries_of(FILES); es.insert(3, {'name': 'data/kv.json', 'data': FILES['data/kv.json']})
add('c-duplicate-name', 'the same entry name twice', 'duplicate', build(es))
for cid, nm, code in [('c-name-traversal', '../evil.json', 'unexpected-entry'), ('c-name-absolute', '/etc/passwd', 'unexpected-entry'), ('c-name-backslash', 'blobs\\000099.bin', 'unexpected-entry'), ('c-name-extra', 'data/extra.json', 'unexpected-entry'), ('c-name-dotdot-blob', 'blobs/../manifest.json', 'unexpected-entry'), ('c-name-space', 'data/tracks .json', 'name'), ('c-name-nonascii', 'data/tracksé.json', 'name')]:
    es = entries_of(FILES) + [{'name': nm, 'data': b'{}'}]
    add(cid, f'extra entry named {nm!r}', code, build(es))
add('c-name-long', 'a 200-byte entry name', 'name', build(entries_of(FILES) + [{'name': 'blobs/' + 'a' * 200, 'data': b'x'}]))
es = entries_of(FILES); es[1] = dict(es[1], lh_name=b'data/trackz.json')
add('c-lh-name', 'local header name differs from directory', 'local-header', build(es))
es = entries_of(FILES); es[1] = dict(es[1], lh_crc=0x12345678)
add('c-lh-crc', 'local header CRC differs from directory', 'local-header', build(es))
es = entries_of(FILES); es[1] = dict(es[1], lh_size=7)
add('c-lh-size', 'local header size differs from directory', 'local-header', build(es))
es = entries_of(FILES); es[2] = dict(es[2], lh_flags=0)
add('c-lh-flags', 'local header flags differ from directory', 'local-header', build(es))
add('c-gap', '16 junk bytes hidden between entries (offsets stay consistent)', 'layout', build(entries_of(FILES), pad={'data/playlists.json': b'HIDDEN-DATA-0123'}))
es = entries_of(FILES); es[2] = dict(es[2], off=0)
add('c-overlap', 'two entries claim the same offset', 'layout', build(es))
add('c-manifest-not-first', 'manifest.json is not the first entry', 'order', build(entries_of(FILES, ORDER[1:] + ['manifest.json'])))
add('c-order-swapped-data', 'data/playlists.json and data/kv.json swapped', 'order', build(entries_of(FILES, [ORDER[0], ORDER[1], ORDER[3], ORDER[2]] + ORDER[4:])))
add('c-blob-gap', 'audio entries numbered 1,2,3,4,5,7', 'order', build([dict(e, name=('blobs/000007.bin' if e['name'] == 'blobs/000006.bin' else e['name'])) for e in entries_of(FILES)]))
add('c-missing-data', 'data/kv.json missing', 'order', build(entries_of({k: v for k, v in FILES.items() if k != 'data/kv.json'})))
add('c-missing-blob-entry', 'last audio entry missing (manifest still lists it)', 'manifest-shape', build(entries_of(recompute({k: v for k, v in FILES.items() if k != 'blobs/000006.bin'}, None))))
def data_off(name):  # true offset of an entry's data, from the ZIP directory (not a text search)
    with zipfile.ZipFile(good) as zz: i = zz.getinfo(name); return i.header_offset + 30 + len(i.filename.encode()) + len(i.extra)
b = bytearray(raw); b[data_off('blobs/000001.bin') + 50] ^= 0xFF
add('c-flip-audio', 'one audio byte flipped (ZIP + manifest CRC no longer match)', 'crc', bytes(b))
b = bytearray(raw); b[data_off('data/tracks.json') + 30] ^= 0x01
add('c-flip-json', 'one byte flipped inside tracks.json', 'crc', bytes(b))
b = bytearray(raw); b[data_off('manifest.json') + 10] ^= 0x01
add('c-flip-manifest', 'one byte flipped inside manifest.json', 'crc', bytes(b))
b = bytearray(raw); b[data_off('blobs/000006.bin') + 1] ^= 0x80
add('c-flip-audio-last', 'one byte flipped in the last (4-byte orphan) audio entry', 'crc', bytes(b))
f = dict(FILES); f['blobs/000002.bin'] = f['blobs/000002.bin'][:-1] + bytes([f['blobs/000002.bin'][-1] ^ 1])
add('c-audio-changed-consistent-zip', 'audio changed and ZIP CRC repaired, but the manifest CRC still describes the original', 'manifest-shape', ok_zip({**f, 'manifest.json': FILES['manifest.json']}))
add('c-stale-manifest-payload', 'manifest sizes do not add up', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'payloadBytes': m['payloadBytes'] + 1}))))

# ---------------------------------------------------------------- limits (reader limits lowered by the test)
add('l-payload', 'payload over the (lowered) byte limit', 'limits', raw, limits={'maxBytes': 2_000_000})
add('l-entries', 'more entries than the (lowered) limit', 'limits', raw, limits={'maxEntries': 8})
add('l-json', 'a data file over the (lowered) JSON limit', 'limits', raw, limits={'maxJson': 1000})
add('l-manifest', 'manifest over the (lowered) limit', 'limits', raw, limits={'maxManifest': 500})
add('l-file', 'file bigger than limit + overhead', 'limits', raw, limits={'maxBytes': 1000, 'overhead': 10})

# ---------------------------------------------------------------- manifest
def fixraw(name, data):  # manifest replaced with non-JSON bytes, zip valid
    f = dict(FILES); f[name] = data; return ok_zip(f)
add('m-not-json', 'manifest is not JSON', 'manifest-json', fixraw('manifest.json', b'{ not json'))
add('m-not-object', 'manifest is a list', 'manifest-shape', fixraw('manifest.json', b'[1,2,3]'))
add('m-bad-utf8', 'manifest contains invalid UTF-8', 'utf8', fixraw('manifest.json', FILES['manifest.json'] + b'\xff\xfe'))
add('m-bom', 'manifest starts with a UTF-8 BOM', 'manifest-json', fixraw('manifest.json', b'\xef\xbb\xbf' + FILES['manifest.json']))
add('m-wrong-format', 'format marker wrong', 'format', ok_zip(mut_man(lambda m: m.update({'format': 'other-backup'}))))
for cid, v, code in [('m-version-2', 2, 'version'), ('m-version-99', 99, 'version'), ('m-version-0', 0, 'version'), ('m-version-str', '1', 'version'), ('m-version-float', 1.5, 'version'), ('m-version-null', None, 'version')]:
    add(cid, f'formatVersion = {v!r}', code, ok_zip(mut_man(lambda m, v=v: m.update({'formatVersion': v}))))
add('m-version-missing', 'formatVersion absent', 'version', ok_zip(mut_man(lambda m: m.pop('formatVersion'))))
add('m-dbversion-2', 'source.databaseVersion = 2', 'db-version', ok_zip(mut_man(lambda m: m['source'].update({'databaseVersion': 2}))))
add('m-dbname', 'source.database = other', 'db-version', ok_zip(mut_man(lambda m: m['source'].update({'database': 'other'}))))
add('m-complete-str', 'complete is a string', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'complete': 'true'}))))
add('m-created-bad', 'createdAt not a date', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'createdAt': 'yesterday-ish'}))))
add('m-counts-wrong', 'counts.tracks off by one', 'counts', ok_zip(mut_man(lambda m: m['counts'].update({'tracks': m['counts']['tracks'] + 1}))))
add('m-counts-neg', 'counts.kv negative', 'manifest-shape', ok_zip(mut_man(lambda m: m['counts'].update({'kv': -1}))))
add('m-files-short', 'files[] lists only 3 data files', 'manifest-shape', ok_zip(mut_man(lambda m: m['files'].pop())))
add('m-files-crc', 'files[] CRC forged for kv.json', 'manifest-shape', ok_zip(mut_man(lambda m: m['files'][2].update({'crc32': '00000000'}))))
add('m-files-path', 'files[] path renamed', 'manifest-shape', ok_zip(mut_man(lambda m: m['files'][1].update({'path': 'data/other.json'}))))
add('m-blob-crc', 'blobs[0].crc32 forged', 'manifest-shape', ok_zip(mut_man(lambda m: m['blobs'][0].update({'crc32': '00000000'}))))
add('m-blob-bytes', 'blobs[1].bytes forged', 'manifest-shape', ok_zip(mut_man(lambda m: m['blobs'][1].update({'bytes': 1}))))
add('m-blob-path', 'blobs[2].path points at another entry', 'manifest-shape', ok_zip(mut_man(lambda m: m['blobs'][2].update({'path': 'blobs/000001.bin'}))))
add('m-blob-dupkey', 'two audio items with the same key', 'duplicate-key', ok_zip(mut_man(lambda m: m['blobs'][3].update({'key': m['blobs'][2]['key']}))))
def swapkeys(m): m['blobs'][0]['key'], m['blobs'][1]['key'] = m['blobs'][1]['key'], m['blobs'][0]['key']
add('m-blob-order', 'audio keys not in ascending order (paths/CRCs consistent)', 'order', ok_zip(mut_man(swapkeys)))
add('m-blob-key-int', 'audio key is a number', 'manifest-shape', ok_zip(mut_man(lambda m: m['blobs'][0].update({'key': 5}))))
add('m-blob-type-upper', 'MIME type with upper case (would be altered by Blob)', 'blob-type', ok_zip(mut_man(lambda m: m['blobs'][0].update({'type': 'Audio/WAV'}))))
add('m-blob-type-nonascii', 'MIME type with non-ASCII', 'blob-type', ok_zip(mut_man(lambda m: m['blobs'][0].update({'type': 'audio/wäv'}))))
add('m-blob-type-int', 'MIME type not text', 'blob-type', ok_zip(mut_man(lambda m: m['blobs'][0].update({'type': 7}))))
add('m-payload', 'audioBytes wrong', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'audioBytes': 1}))))
add('m-problems-shape', 'problems entry malformed', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'problems': [{'id': 1}]}))))
add('m-complete-with-problems', 'complete:true but problems listed', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'problems': [{'id': 'bin-1', 'title': 't', 'reason': 'r'}]}))))
add('m-warnings-shape', 'warnings not text', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'warnings': [1]}))))
add('m-excluded-shape', 'excluded.kv not a list of text', 'manifest-shape', ok_zip(mut_man(lambda m: m.update({'excluded': {'kv': [1]}}))))

# ---------------------------------------------------------------- incomplete archives
def make_incomplete(f):
    """claim INCOMPLETE and drop the audio of one local track (empty blob), consistently."""
    f = dict(f); man = json.loads(f['manifest.json']); tr = json.loads(f['data/tracks.json'])
    tid = 'bin-1'; idx = [b['key'] for b in man['blobs']].index(tid); name = man['blobs'][idx]['path']
    f[name] = b''
    def mm(m): m['complete'] = False; m['problems'] = [{'id': tid, 'title': 'All byte values', 'reason': 'audio file is empty'}]
    return recompute(f, mm)
INC = make_incomplete(FILES)
add('i-incomplete', 'valid archive marked complete:false (an INCOMPLETE export)', 'incomplete', ok_zip(INC))
add('i-incomplete-unaccounted', 'incomplete, but a missing song is not listed in problems', 'reference', ok_zip(recompute(INC, lambda m: m.update({'problems': [{'id': 'zzz', 'title': 'x', 'reason': 'r'}]}))))
f = dict(FILES); f['blobs/000004.bin'] = b''
add('i-complete-but-empty-audio', 'complete:true but a local song has an empty audio entry', 'reference', ok_zip(recompute(f)))
f = {k: v for k, v in FILES.items()}
man = json.loads(f['manifest.json']); keep = [b for b in man['blobs'] if b['key'] != 'bin-2']
f2 = {k: v for k, v in f.items() if not k.startswith('blobs/')}
for i, b in enumerate(keep): f2['blobs/%06d.bin' % (i + 1)] = f[b['path']]
def drop_blob(m): m['blobs'] = [dict(x, path='blobs/%06d.bin' % (i + 1)) for i, x in enumerate(keep)]; m['counts']['blobs'] = len(keep)
add('i-complete-missing-audio', 'complete:true but a local song has no audio entry at all', 'reference', ok_zip(recompute(f2, drop_blob)))

# ---------------------------------------------------------------- data shapes
def tk(i): return lambda t: t.__setitem__(i, t[i])
add('d-tracks-not-list', 'tracks.json is an object', 'shape', ok_zip(mut_json('data/tracks.json', lambda v: {'a': 1}, replace=True)))
add('d-track-not-object', 'a track is a string', 'shape', ok_zip(mut_tracks(lambda t: t.__setitem__(0, 'x'))))
add('d-track-no-id', 'a track without id', 'shape', ok_zip(mut_tracks(lambda t: (t[0].pop('id'), None)[1])))
add('d-track-id-int', 'a track with numeric id', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'id': 5}))))
add('d-track-id-empty', 'a track with empty id', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'id': ''}))))
add('d-track-dup-id', 'two tracks share an id', 'duplicate-id', ok_zip(mut_tracks(lambda t: t[1].update({'id': t[0]['id']}))))
add('d-track-order', 'tracks not in key order', 'order', ok_zip(mut_tracks(lambda t: t.reverse())))
add('d-track-kind', 'kind = "remote"', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'kind': 'remote'}))))
add('d-track-title-int', 'title is a number', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'title': 9}))))
add('d-track-title-missing', 'title missing', 'shape', ok_zip(mut_tracks(lambda t: (t[0].pop('title'), None)[1])))
add('d-track-duration-str', 'duration is text', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'duration': '12'}))))
add('d-track-plays-neg', 'plays negative', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'plays': -1}))))
add('d-track-liked-int', 'liked = 1', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'liked': 1}))))
add('d-track-cover-js', 'cover = javascript: URL', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'cover': 'javascript:alert(1)'}))))
add('d-track-cover-svg', 'cover = data:image/svg+xml', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'cover': 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4='}))))
add('d-track-cover-file', 'cover = file: URL', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'cover': 'file:///etc/passwd'}))))
add('d-web-url-js', 'web song url = javascript:', 'shape', ok_zip(mut_tracks(lambda t: [x.update({'url': 'javascript:alert(1)'}) for x in t if x['kind'] == 'web'] and None)))
add('d-web-url-data', 'web song url = data: audio', 'shape', ok_zip(mut_tracks(lambda t: [x.update({'url': 'data:audio/wav;base64,AAAA'}) for x in t if x['kind'] == 'web'] and None)))
add('d-web-url-missing', 'web song without url', 'shape', ok_zip(mut_tracks(lambda t: [x.pop('url') for x in t if x['kind'] == 'web'] and None)))
add('d-web-link-js', 'web song link = javascript:', 'shape', ok_zip(mut_tracks(lambda t: [x.update({'link': 'javascript:alert(1)'}) for x in t if x['kind'] == 'web'] and None)))
add('d-track-proto', 'a track carries a __proto__ key', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'__proto__': {'polluted': 1}}))))
def deep(n): return '[' * n + ']' * n
add('d-deep-nesting', 'a field nested 60 levels deep', 'shape', ok_zip(mut_tracks(lambda t: t[0].update({'x': json.loads(deep(60))}))))
add('d-track-ok-unknown-field', 'a track with an unknown extra field is accepted and kept', 'ok', ok_zip(mut_tracks(lambda t: t[0].update({'futureRating': 4.5, 'meta': {'a': [1]}}))))
add('d-badutf8-tracks', 'tracks.json contains invalid UTF-8 (ZIP CRC repaired)', 'utf8', ok_zip(recompute({**FILES, 'data/tracks.json': FILES['data/tracks.json'] + b'\xc3\x28'})))
add('d-json-trailing', 'tracks.json has trailing garbage', 'json', ok_zip(recompute({**FILES, 'data/tracks.json': FILES['data/tracks.json'] + b'xx'})))
add('d-tracks-empty-count', 'tracks.json emptied but manifest counts say otherwise', 'counts', ok_zip({**FILES, 'data/tracks.json': b'[]', 'manifest.json': J({**json.loads(FILES['manifest.json']), 'files': [dict(x, bytes=2, crc32=hx(crc(b'[]'))) if x['path'] == 'data/tracks.json' else x for x in json.loads(FILES['manifest.json'])['files']], 'payloadBytes': json.loads(FILES['manifest.json'])['payloadBytes'] - len(FILES['data/tracks.json']) + 2})}))

def mut_pl(fn, **k): return mut_json('data/playlists.json', fn, **k)
add('p-dup-id', 'two playlists share an id', 'duplicate-id', ok_zip(mut_pl(lambda p: p[1].update({'id': p[0]['id']}))))
add('p-ids-not-list', 'playlist ids is a string', 'shape', ok_zip(mut_pl(lambda p: p[0].update({'ids': 'abc'}))))
add('p-ids-nonstring', 'playlist ids contains a number', 'shape', ok_zip(mut_pl(lambda p: p[0]['ids'].append(5))))
add('p-name-int', 'playlist name is a number', 'shape', ok_zip(mut_pl(lambda p: p[0].update({'name': 5}))))
add('p-order', 'playlists out of key order', 'order', ok_zip(mut_pl(lambda p: p.reverse())))
add('p-dangling-ok', 'playlist referencing an unknown song id is accepted (kept as-is, warned)', 'ok', ok_zip(mut_pl(lambda p: p[1]['ids'].append('no-such-song'))))

add('k-not-list', 'kv.json is an object', 'shape', ok_zip(mut_json('data/kv.json', lambda v: {'a': 1}, replace=True)))
add('k-no-value', 'kv entry without value', 'shape', ok_zip(mut_kv(lambda kv: (kv[0].pop('value'), None)[1])))
add('k-extra-prop', 'kv entry with a third property', 'shape', ok_zip(mut_kv(lambda kv: kv[0].update({'extra': 1}))))
add('k-key-int', 'kv key is a number', 'shape', ok_zip(mut_kv(lambda kv: kv[0].update({'key': 3}))))
add('k-dup', 'duplicate kv keys', 'duplicate-key', ok_zip(mut_kv(lambda kv: kv.insert(1, dict(kv[0])))))
add('k-order', 'kv keys not ascending', 'order', ok_zip(mut_kv(lambda kv: kv.reverse())))
add('k-secret', 'kv contains secret:listenbrainz-token', 'secret', ok_zip(mut_kv(lambda kv: kv.append({'key': 'secret:listenbrainz-token', 'value': 'abc123'}))))
add('k-secret-xss', 'credential key whose name is an HTML payload (must be shown escaped)', 'secret', ok_zip(mut_kv(lambda kv: kv.append({'key': 'secret:<img src=x onerror=alert(1)>', 'value': 'x'}))))
add('k-secret-case', 'kv contains Secret:lastfm-session (case variant)', 'secret', ok_zip(mut_kv(lambda kv: kv.insert(0, {'key': 'Secret:lastfm-session', 'value': 'zzz'}))))
def sess(fn):
    def m(kv):
        s = kvmap(kv)['session']['value']; fn(s)
    return ok_zip(mut_kv(m))
add('s-queue-not-list', 'session.queue is a string', 'shape', sess(lambda s: s.update({'queue': 'x'})))
add('s-queue-nonstring', 'session.queue holds numbers', 'shape', sess(lambda s: s.update({'queue': [1, 2]})))
add('s-qi-float', 'session.qi = 1.5', 'shape', sess(lambda s: s.update({'qi': 1.5})))
add('s-vol-range', 'session.vol = 7', 'shape', sess(lambda s: s.update({'vol': 7})))
add('s-rate-range', 'session.rate = 100', 'shape', sess(lambda s: s.update({'rate': 100})))
add('s-eq-length', 'session.eq has 9 bands', 'shape', sess(lambda s: s.update({'eq': [0] * 9})))
add('s-eq-str', 'session.eq has text', 'shape', sess(lambda s: s.update({'eq': ['a'] * 10})))
add('s-repeat', 'session.repeat = 5', 'shape', sess(lambda s: s.update({'repeat': 5})))
add('s-tab', 'session.npTab = "<script>"', 'shape', sess(lambda s: s.update({'npTab': '<script>alert(1)</script>'})))
add('s-web-url', 'session.webs[0].url = javascript:', 'shape', sess(lambda s: s['webs'][0].update({'url': 'javascript:alert(1)'}) if s.get('webs') else s.update({'webs': [{'id': 'x', 'kind': 'web', 'title': 't', 'artist': 'a', 'album': 'b', 'url': 'javascript:1'}]})))
add('s-not-object', 'session is a list', 'shape', sess(lambda s: None) if False else ok_zip(mut_kv(lambda kv: kvmap(kv)['session'].update({'value': [1]}))))
add('h-not-list', 'hist is an object', 'shape', ok_zip(mut_kv(lambda kv: kvmap(kv)['hist'].update({'value': {'a': 1}}))))
add('h-entry', 'hist entry without time', 'shape', ok_zip(mut_kv(lambda kv: (kvmap(kv)['hist']['value'][0].pop('t'), None)[1])))
add('h-snap-url', 'hist snapshot url = javascript:', 'shape', ok_zip(mut_kv(lambda kv: kvmap(kv)['hist']['value'][0]['snap'].update({'url': 'javascript:1'}))))
add('ls-unknown-key', 'localstorage.json carries a key outside the allow-list', 'localstorage', ok_zip(mut_json('data/localstorage.json', lambda v: {**v, 'lastfm-session': 'zzz'}, replace=True)))
add('ls-bad-theme', 'ps-theme = "purple"', 'localstorage', ok_zip(mut_json('data/localstorage.json', lambda v: {'ps-theme': 'purple'}, replace=True)))
add('ls-not-object', 'localstorage.json is a list', 'shape', ok_zip(mut_json('data/localstorage.json', lambda v: ['dark'], replace=True)))

# ---------------------------------------------------------------- hostile TEXT that must be accepted and shown escaped
HOST = '<img src=x onerror="window.__pwned=1">'
def hostile_text():
    f = mut_tracks(lambda t: [x.update({'title': HOST + ' T' + str(i), 'artist': '"><script>window.__pwned=2</script>', 'album': "'; window.__pwned=3;//", 'lyrics': '<svg onload="window.__pwned=4">'}) for i, x in enumerate(t)] and None)
    f = mut_json('data/playlists.json', lambda p: [x.update({'name': HOST + ' list'}) for x in p] and None, files=f)
    def kvf(kv):
        for x in kv:
            if x['key'] == 'hist': x['value'][0]['snap']['title'] = HOST + ' hist'
    f = mut_json('data/kv.json', kvf, files=f)
    def mm(m): m['generator'] = '<b>Evil</b>'; m['warnings'] = ['<img src=x onerror="window.__pwned=5">']
    return ok_zip(recompute(f, mm))
add('ok-hostile-text', 'hostile HTML/script text in titles, artists, albums, lyrics, playlist names, history, generator and warnings: accepted, must only ever be displayed escaped', 'ok', hostile_text())

if '--big' in sys.argv:  # 64 MiB random audio entry: accepted, timing and memory sanity
    f = dict(FILES); name = 'blobs/000006.bin'; f[name] = os.urandom(64 << 20)
    add('ok-big', 'a 64 MiB random audio entry', 'ok', ok_zip(recompute(f)))

json.dump(cases, open(os.path.join(outdir, 'cases.json'), 'w'), indent=1)
print(len(cases), 'cases written to', outdir)
