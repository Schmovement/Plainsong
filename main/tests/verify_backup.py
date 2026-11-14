#!/usr/bin/env python3
"""Independent verifier for Plainsong backup archives (format plainsong-backup v1).

Uses only the Python standard library plus `unzip -t` (if installed); shares no code with the app.

  python3 -I verify_backup.py <backup.zip> <expected.json> [--incomplete] [--ignore-kv a,b]
  python3 -I verify_backup.py --extract <backup.zip> <entry-name>      (prints the entry to stdout)

expected.json (written by the browser test harness from the live IndexedDB state):
  tracks[], playlists[], kv[{key,value}] (credential keys already removed), ls{}, blobs[{key,size,type,sha256}] in store key order,
  excludedKv[], forbidden[] (strings that must not appear anywhere in the archive), problemIds[] (only for --incomplete)
Prints one "PASS name" / "FAIL name :: detail" line per check. Exit code 0 only if every check passed.
"""
import sys, json, zipfile, hashlib, subprocess, shutil, datetime, zlib

if len(sys.argv) >= 4 and sys.argv[1] == '--extract':
    with zipfile.ZipFile(sys.argv[2]) as z:
        sys.stdout.buffer.write(z.read(sys.argv[3]))
    sys.exit(0)

zip_path, exp_path = sys.argv[1], sys.argv[2]
incomplete = '--incomplete' in sys.argv
ignore_kv = set()
if '--ignore-kv' in sys.argv:
    ignore_kv = set(sys.argv[sys.argv.index('--ignore-kv') + 1].split(','))
exp = json.load(open(exp_path, encoding='utf-8'))
fails = 0


def chk(name, ok, detail=''):
    global fails
    if not ok:
        fails += 1
    print(('PASS ' if ok else 'FAIL ') + name + (('  :: ' + str(detail)[:400]) if detail != '' else ''))


raw = open(zip_path, 'rb').read()
chk('zip: is a valid ZIP file', zipfile.is_zipfile(zip_path))
z = zipfile.ZipFile(zip_path)
chk('zip: Python testzip() finds no bad CRC', z.testzip() is None, z.testzip())
if shutil.which('unzip'):
    r = subprocess.run(['unzip', '-tq', zip_path], capture_output=True, text=True)
    chk('zip: `unzip -t` (independent tool) reports no errors', r.returncode == 0, r.stdout + r.stderr)
infos = z.infolist()
names = [i.filename for i in infos]
chk('zip: entry names are unique', len(set(names)) == len(names))
chk('zip: every entry is stored (no compression) with UTF-8 flag', all(i.compress_type == 0 and (i.flag_bits & 0x800) for i in infos))
chk('zip: no comment, no encryption, no ZIP64 extras', not z.comment and all(not (i.flag_bits & 1) and not i.extra for i in infos))
chk('zip: manifest.json is the first entry', names[:1] == ['manifest.json'], names[:3])
man = json.loads(z.read('manifest.json').decode('utf-8'))
chk('manifest: format and version', man.get('format') == 'plainsong-backup' and man.get('formatVersion') == 1, (man.get('format'), man.get('formatVersion')))
try:
    ts = datetime.datetime.fromisoformat(man['createdAt'].replace('Z', '+00:00'))
    chk('manifest: createdAt is a recent ISO-8601 UTC time', abs((datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds()) < 3600, man['createdAt'])
except Exception as e:
    chk('manifest: createdAt is a recent ISO-8601 UTC time', False, e)
chk('manifest: complete flag is %s' % (not incomplete), man.get('complete') is (not incomplete), man.get('complete'))
chk('manifest: source database is plainsong v1', man.get('source') == {'database': 'plainsong', 'databaseVersion': 1}, man.get('source'))
chk('manifest: integrity declares crc32 with a plain-language caveat', man['integrity']['algorithm'] == 'crc32' and 'tampering' in man['integrity']['note'])

DATA = ['data/tracks.json', 'data/playlists.json', 'data/kv.json', 'data/localstorage.json']
blob_names = ['blobs/%06d.bin' % (i + 1) for i in range(len(exp['blobs']))]
chk('zip: exactly the expected entries, in order', names == ['manifest.json'] + DATA + blob_names, names[:8])
by = {i.filename: i for i in infos}
bad = []
for f in man['files']:
    i = by.get(f['path'])
    if not i or i.file_size != f['bytes'] or i.CRC != int(f['crc32'], 16) or zlib.crc32(z.read(f['path'])) != int(f['crc32'], 16):
        bad.append(f['path'])
chk('manifest: data file sizes and CRC-32 match the archive (recomputed here)', not bad and [f['path'] for f in man['files']] == DATA, bad)

tracks = json.loads(z.read('data/tracks.json'))
playlists = json.loads(z.read('data/playlists.json'))
kv = json.loads(z.read('data/kv.json'))
ls = json.loads(z.read('data/localstorage.json'))
chk('data/tracks.json equals the database records, same order', tracks == exp['tracks'], 'got %d expected %d' % (len(tracks), len(exp['tracks'])))
chk('data/playlists.json equals the database records, same order', playlists == exp['playlists'])
kv_f = [x for x in kv if x['key'] not in ignore_kv]
kv_e = [x for x in exp['kv'] if x['key'] not in ignore_kv]
chk('data/kv.json equals the database (credential keys removed), same key order', kv_f == kv_e, [x['key'] for x in kv])
if ignore_kv:
    chk('kv ignored keys are still present in the archive', all(any(x['key'] == k for x in kv) for k in ignore_kv if any(y['key'] == k for y in exp['kv'])))
chk('data/localstorage.json equals the allow-listed prefs', ls == exp['ls'], ls)

mb = man['blobs']
chk('manifest: blob keys equal the database blob keys in store order (exact strings)', [b['key'] for b in mb] == [b['key'] for b in exp['blobs']], [b['key'] for b in mb][:6])
bad = []
for b, e, n in zip(mb, exp['blobs'], blob_names):
    data = z.read(n)
    if (b['path'] != n or b['bytes'] != e['size'] or len(data) != e['size'] or hashlib.sha256(data).hexdigest() != e['sha256']
            or b['type'] != e['type'] or b['crc32'] != '%08x' % zlib.crc32(data)):
        bad.append(b['key'])
chk('every audio entry: byte-identical (SHA-256), same size, same MIME, CRC-32 matches manifest', not bad and len(mb) == len(exp['blobs']), bad)
chk('exercise: at least one blob is binary non-audio-looking data, one has empty MIME', any(b['type'] == '' for b in mb) and any(b['bytes'] > 1000 for b in mb) if exp.get('expectBinary') else True)

c = man['counts']
chk('manifest: counts match archive contents', c == {'tracks': len(tracks), 'playlists': len(playlists), 'kv': len(kv), 'blobs': len(mb), 'localStorage': len(ls)}, c)
chk('manifest: audioBytes and payloadBytes add up', man['audioBytes'] == sum(b['bytes'] for b in mb) and man['payloadBytes'] == man['audioBytes'] + sum(f['bytes'] for f in man['files']))
chk('manifest: excluded kv key names recorded, values absent', man['excluded']['kv'] == exp['excludedKv'], man['excluded'])
chk('manifest: states credentials are never exported', 'never exported' in man['excluded']['credentials'])
hits = [s for s in exp.get('forbidden', []) if s.encode('utf-8') in raw]
chk('no credential / non-allow-listed secret strings anywhere in the archive bytes', not hits, hits)
if incomplete:
    chk('manifest: problems list names exactly the broken tracks', sorted(p['id'] for p in man['problems']) == sorted(exp.get('problemIds', [])), man['problems'])
else:
    chk('manifest: no problems recorded for a complete backup', man['problems'] == [], man['problems'])
chk('manifest: limits recorded', man['limits']['maxBytes'] >= 1 and man['limits']['maxEntries'] >= 1, man['limits'])
chk('order: track ids preserved exactly (strings, no coercion)', [t['id'] for t in tracks] == [t['id'] for t in exp['tracks']])

print('RESULT %s (%d failed)' % ('OK' if not fails else 'FAILED', fails))
sys.exit(1 if fails else 0)
