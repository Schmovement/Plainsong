#!/usr/bin/env python3
"""Negative controls: the independent verifier must REJECT damaged archives.
usage: python3 -I negative_controls.py <good.zip> <good.expected.json> <scratch-dir>
Prints PASS/FAIL per control; a control passes when verify_backup.py exits non-zero on the damaged copy."""
import sys, os, re, json, zipfile, subprocess

good, exp, work = sys.argv[1:4]
here = os.path.dirname(os.path.abspath(__file__))
verify = os.path.join(here, 'verify_backup.py')
os.makedirs(work, exist_ok=True)
raw = bytearray(open(good, 'rb').read())
z = zipfile.ZipFile(good)
info = {i.filename: i for i in z.infolist()}
fails = 0


def run(tag, data, exp_path=exp, flags=()):
    global fails
    p = os.path.join(work, re.sub(r'[^a-z0-9]+', '-', tag.lower()).strip('-') + '.zip'); open(p, 'wb').write(bytes(data))
    r = subprocess.run([sys.executable, '-I', verify, p, exp_path, *flags], capture_output=True, text=True)
    rejected = r.returncode != 0
    if not rejected:
        fails += 1
    print(('PASS ' if rejected else 'FAIL ') + 'verifier rejects: ' + tag + ('' if rejected else '  :: it accepted a damaged archive'))


def data_off(name):
    i = info[name]; return i.header_offset + 30 + len(i.filename.encode()) + len(i.extra)


# 0. sanity: the untouched copy is accepted
r = subprocess.run([sys.executable, '-I', verify, good, exp], capture_output=True, text=True)
print(('PASS ' if r.returncode == 0 else 'FAIL ') + 'control baseline: the undamaged archive is accepted'); fails += r.returncode != 0

m = bytearray(raw); o = data_off('blobs/000001.bin') + 10; m[o] ^= 0xFF
run('one audio byte flipped (CRC/SHA mismatch)', m)
m = bytearray(raw); o = data_off('data/tracks.json') + 5; m[o] ^= 0x01
run('one byte flipped inside tracks.json', m)
run('archive truncated (end record lost)', raw[:len(raw) - 40])
run('empty file', b'')
# swap the stored CRC in the manifest only: rebuild zip with an altered manifest but valid zip CRC
p = os.path.join(work, 'forged.zip')
with zipfile.ZipFile(good) as src, zipfile.ZipFile(p, 'w', zipfile.ZIP_STORED) as dst:
    for i in src.infolist():
        data = src.read(i.filename)
        if i.filename == 'manifest.json':
            mj = json.loads(data); mj['blobs'][0]['crc32'] = '00000000'; data = json.dumps(mj, indent=2).encode()
        dst.writestr(i.filename, data)
run('manifest CRC-32 disagrees with the audio entry (forged manifest)', open(p, 'rb').read())
with zipfile.ZipFile(good) as src, zipfile.ZipFile(p, 'w', zipfile.ZIP_STORED) as dst:
    for i in src.infolist():
        if i.filename != 'blobs/000002.bin' and i.filename != 'manifest.json' or i.filename == 'manifest.json':
            dst.writestr(i.filename, src.read(i.filename))
run('an audio entry removed from the archive', open(p, 'rb').read())
with zipfile.ZipFile(good) as src, zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as dst:
    for i in src.infolist(): dst.writestr(i.filename, src.read(i.filename))
run('entries compressed instead of stored (format violation)', open(p, 'rb').read())
e = json.load(open(exp)); e['forbidden'] = [e['tracks'][0]['title']]
fp = os.path.join(work, 'forbid.expected.json'); json.dump(e, open(fp, 'w'))
run('a forbidden (secret) string present in the archive', raw, fp)
e = json.load(open(exp)); e['blobs'][0]['sha256'] = '0' * 64
fp = os.path.join(work, 'sha.expected.json'); json.dump(e, open(fp, 'w'))
run('audio bytes differ from the originals recorded in the database', raw, fp)
e = json.load(open(exp)); e['tracks'] = list(reversed(e['tracks']))
fp = os.path.join(work, 'order.expected.json'); json.dump(e, open(fp, 'w'))
run('track order differs from the database key order', raw, fp)
print('NEGATIVE CONTROLS %s' % ('OK' if not fails else 'FAILED'))
sys.exit(1 if fails else 0)
