#!/usr/bin/env python3
"""Independent ground truth for the Phase 2A reader test.
usage: python3 -I extract_expected.py <backup.zip> <out.json>
Reads a p1 backup with Python's zipfile/json/hashlib only (no app code) and writes what a correct reader must return:
manifest, tracks, playlists, kv, localStorage, and for every audio entry its manifest key, MIME type, size and SHA-256."""
import sys, json, zipfile, hashlib

zip_path, out = sys.argv[1:3]
z = zipfile.ZipFile(zip_path)
assert z.testzip() is None, 'zip CRC failure'
man = json.loads(z.read('manifest.json'))
res = {
    'manifest': man,
    'tracks': json.loads(z.read('data/tracks.json')),
    'playlists': json.loads(z.read('data/playlists.json')),
    'kv': json.loads(z.read('data/kv.json')),
    'ls': json.loads(z.read('data/localstorage.json')),
    'blobs': [],
}
for b in man['blobs']:
    data = z.read(b['path'])
    res['blobs'].append({'key': b['key'], 'type': b['type'], 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
json.dump(res, open(out, 'w'), ensure_ascii=False)
print('ok', len(res['tracks']), 'tracks', len(res['blobs']), 'blobs')
