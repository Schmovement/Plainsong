#!/usr/bin/env python3
"""Negative/positive CONTROLS for tests/oracle_2c.py (Phase 2C). Shows that "zero failures" from the oracle means something.
  python3 -I oracle_2c_controls.py <good-backup.zip> <out-dir>
writes mutated, internally consistent (CRC/manifest refreshed where the control needs a valid file) archives into <out-dir> and <out-dir>/cases.json:
  [{id, desc, a, b, expect: 'FAIL'|'ALLOWED', must: [check-text prefixes], opts: {theme?, secrets?, timeUnavailable?}}]
FAIL controls   : the oracle must report >= 1 failure AND each prefix in `must` must start the text of a FAILED check (the intended check caught it).
ALLOWED controls: the oracle must report 0 failures and its non-exact results must be EXACTLY the `must` list (each prefix matches exactly one
                  non-exact result, all with status 'allowed'), so an unrelated relaxed rule cannot satisfy a control.
Mutations are byte-level edits so the formatting of every untouched file stays identical to the source.
"""
import sys, os, json, zipfile, zlib, collections

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(src)
GOOD = collections.OrderedDict((i.filename, z.read(i.filename)) for i in z.infolist())
hexcrc = lambda d: '%08x' % (zlib.crc32(d) & 0xffffffff)


def rep(data, old, new):
    assert data.count(old) == 1, (old, data.count(old))
    return data.replace(old, new)


def build(name, mut, refresh=True):
    e = collections.OrderedDict(GOOD)
    man = json.loads(e['manifest.json'])
    mut(e, man)
    if refresh:
        for f in man['files']:
            if f['path'] in e:
                f['bytes'] = len(e[f['path']]); f['crc32'] = hexcrc(e[f['path']])
        for b in man['blobs']:
            if b['path'] in e:
                b['bytes'] = len(e[b['path']]); b['crc32'] = hexcrc(e[b['path']])
        man['audioBytes'] = sum(len(e[b['path']]) for b in man['blobs'])
        man['payloadBytes'] = sum(len(d) for n, d in e.items() if n != 'manifest.json')
        man['counts'] = {'tracks': len(json.loads(e['data/tracks.json'])), 'playlists': len(json.loads(e['data/playlists.json'])), 'kv': len(json.loads(e['data/kv.json'])),
                         'blobs': len(man['blobs']), 'localStorage': len(json.loads(e['data/localstorage.json']))}
    e['manifest.json'] = (json.dumps(man, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    path = os.path.join(out, name + '.zip')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as zz:
        for n, d in e.items():
            zi = zipfile.ZipInfo(n, (2026, 11, 6, 0, 0, 0)); zi.compress_type = zipfile.ZIP_STORED; zz.writestr(zi, d)
    return path, e, man


def kvedit(old, new):
    return lambda e, m: e.__setitem__('data/kv.json', rep(e['data/kv.json'], old, new))


def derived(path_a, path_b, extra):
    """expected ALLOWED non-exact prefixes for a kv.json/localstorage.json change: crc32 always, bytes/payload when lengths differ."""
    za, zb = zipfile.ZipFile(path_a), zipfile.ZipFile(path_b)
    out = list(extra)
    for n in ('data/kv.json', 'data/localstorage.json'):
        a, b = za.read(n), zb.read(n)
        if a != b:
            out.append('manifest.files[%s].crc32' % n)
            if len(a) != len(b):
                out.append('manifest.files[%s].bytes' % n)
    pa = sum(i.file_size for i in za.infolist() if i.filename != 'manifest.json'); pb = sum(i.file_size for i in zb.infolist() if i.filename != 'manifest.json')
    if pa != pb:
        out.append('manifest.payloadBytes')
    return out


cases = []
GOODP = os.path.join(out, 'good.zip')
with open(GOODP, 'wb') as f:
    f.write(open(src, 'rb').read())


def case(cid, desc, b, expect, must, opts=None, a=None):
    cases.append({'id': cid, 'desc': desc, 'a': os.path.basename(a or GOODP), 'b': os.path.basename(b), 'expect': expect, 'must': must, 'opts': opts or {}})


# ---- data differences that MUST be caught
def flip(e, m):
    d = bytearray(e['blobs/000003.bin']); d[0] ^= 1; e['blobs/000003.bin'] = bytes(d)
p, *_ = build('c-audio-byte-flip', flip); case('audio-byte-flip', 'one bit of one audio entry flipped (file stays internally consistent)', p, 'FAIL', ['audio list identical', 'blobs/000003.bin byte-identical'])
p, *_ = build('c-session-vol', kvedit(b'"vol":0.8', b'"vol":0.7')); case('session-vol', 'session.vol 0.8 -> 0.7', p, 'FAIL', ['kv[session] differs in fields'])
p, *_ = build('c-tracks-key-order', lambda e, m: e.__setitem__('data/tracks.json', rep(e['data/tracks.json'], b'"title":"Song Three","artist":"Artist C"', b'"artist":"Artist C","title":"Song Three"')))
case('tracks-key-order', 'two keys of one track record swapped (same values)', p, 'FAIL', ['tracks records identical', 'data/tracks.json byte-identical'])
ids = b'"ids":["fb922971-a227-4d99-a9b1-11d2a0760f21","audius:TEST1","2b099514-30af-41b9-aad6-0d0ee10a3873","bin-1"]'
ids2 = b'"ids":["bin-1","2b099514-30af-41b9-aad6-0d0ee10a3873","audius:TEST1","fb922971-a227-4d99-a9b1-11d2a0760f21"]'
p, *_ = build('c-playlist-order', lambda e, m: e.__setitem__('data/playlists.json', rep(e['data/playlists.json'], ids, ids2)))
case('playlist-order', 'playlist song order reversed', p, 'FAIL', ['playlists records identical', 'data/playlists.json byte-identical'])
p, *_ = build('c-blob-mime', lambda e, m: m['blobs'][0].__setitem__('type', 'audio/mpeg')); case('blob-mime-manifest', 'one audio MIME type changed in the manifest', p, 'FAIL', ['audio list identical', 'manifest.blobs[blobs/000001.bin].type'])
p, *_ = build('c-kv-extra', kvedit(b'[\n{"key":"custom:pref"', b'[\n{"key":"aaa-extra","value":1},\n{"key":"custom:pref"')); case('kv-extra-key', 'an extra kv entry', p, 'FAIL', ['kv key set and order identical'])
p, *_ = build('c-ls-extra', lambda e, m: e.__setitem__('data/localstorage.json', b'{\n "other": "x",\n "ps-theme": "dark"\n}\n')); case('localstorage-extra-key', 'an extra localStorage key', p, 'FAIL', ['localstorage.json differs'])
p, *_ = build('c-extra-entry', lambda e, m: e.__setitem__('blobs/000007.bin', b'zz'), refresh=False); case('extra-zip-entry', 'an extra ZIP entry not in the manifest', p, 'FAIL', ['entry names and order identical', 'B self-check'])

# ---- secrets: any secret:-prefixed kv key (case-insensitive) in A or in B fails
sec = lambda k: kvedit(b'[\n{"key":"custom:pref"', ('[\n{"key":"%s","value":{"token":"x"}},\n{"key":"custom:pref"' % k).encode())
p, *_ = build('c-secret-b', sec('secret:lastfm')); case('secret-in-B', 'B carries a secret: key in kv.json', p, 'FAIL', ['B has no secret: key in kv.json', 'kv key set and order identical'])
p, *_ = build('c-secret-b-upper', sec('SECRET:Token')); case('secret-upper-in-B', 'B carries SECRET:Token (case-insensitive prefix)', p, 'FAIL', ['B has no secret: key in kv.json'])
case('secret-in-A', 'A carries a secret: key (compared with a clean B)', GOODP, 'FAIL', ['A has no secret: key in kv.json'], a=p)

# ---- session.time: exact/bounded drift only
tm = lambda v: kvedit(b'"time":3,', ('"time":%s,' % v).encode())
p, *_ = build('c-time-drift', tm('3.2'))
case('time-drift-bounded', 'session.time 3 -> 3.2 (drift 0.2 s, inside the 0.25 s bound)', p, 'ALLOWED', derived(GOODP, p, ['kv[session] identical except time']))
p, *_ = build('c-time-forward', tm('8')); case('time-jump-forward', 'session.time 3 -> 8', p, 'FAIL', ['kv[session].time changed beyond the allowance'])
p, *_ = build('c-time-zero', tm('0')); case('time-rewind-to-zero', 'session.time 3 -> 0 WITHOUT the explicit unavailable-position evidence flag', p, 'FAIL', ['kv[session].time changed beyond the allowance'])
case('time-rewind-to-zero-with-evidence', 'session.time 3 -> 0 WITH --time-unavailable (harness proved the current song cannot report a position)', p, 'ALLOWED', derived(GOODP, p, ['kv[session] identical except time']), {'timeUnavailable': True})
p, *_ = build('c-time-one', tm('1')); case('time-flag-but-not-zero', '--time-unavailable given but B.time is 1, not 0', p, 'FAIL', ['kv[session].time changed beyond the allowance'], {'timeUnavailable': True})
p, *_ = build('c-time-neg', tm('-1')); case('time-negative', 'session.time -1', p, 'FAIL', ['kv[session].time changed beyond the allowance'])
p, *_ = build('c-time-str', tm('"3"')); case('time-string', 'session.time "3" (a string)', p, 'FAIL', ['kv[session].time changed beyond the allowance'])
A120 = build('c-a-time-120', tm('120'))[0]; B60 = build('c-b-time-60', tm('60'))[0]
case('time-large-backward-jump', 'session.time 120 -> 60 (a large backward jump that is not zero), with the evidence flag given', B60, 'FAIL', ['kv[session].time changed beyond the allowance'], {'timeUnavailable': True}, a=A120)

# ---- createdAt
p, *_ = build('c-created-later', lambda e, m: m.__setitem__('createdAt', '2026-11-06T01:02:03.004Z')); case('createdAt-later', 'manifest.createdAt later than A', p, 'ALLOWED', ['manifest.createdAt'])
p, *_ = build('c-created-earlier', lambda e, m: m.__setitem__('createdAt', '2026-11-04T08:10:30.000Z')); case('createdAt-earlier', 'manifest.createdAt EARLIER than A', p, 'FAIL', ['manifest.createdAt'])

# ---- theme rule
NOTHEME = build('a-no-theme', lambda e, m: e.__setitem__('data/localstorage.json', b'{}\n'))[0]
DARK = build('b-dark-from-none', lambda e, m: None)[0]  # = good (dark); used with A = NOTHEME
case('theme-added-allowed', 'A has no theme; B carries the target browser\'s dark theme (--b-theme dark)', DARK, 'ALLOWED', derived(NOTHEME, DARK, ['localstorage.json: A had no ps-theme', 'manifest.counts.localStorage']), {'theme': 'dark'}, a=NOTHEME)
case('theme-added-wrong-b-theme', 'A has no theme; B has dark but the target\'s theme was light', DARK, 'FAIL', ['localstorage.json differs'], {'theme': 'light'}, a=NOTHEME)
case('theme-added-no-evidence', 'A has no theme; B has dark and no --b-theme was given', DARK, 'FAIL', ['localstorage.json differs'], {}, a=NOTHEME)
LIGHT = build('c-light', lambda e, m: e.__setitem__('data/localstorage.json', b'{\n "ps-theme": "light"\n}\n'))[0]
case('theme-changed', 'A has dark; B has light (a theme in the backup must be kept exactly)', LIGHT, 'FAIL', ['localstorage.json differs'], {'theme': 'light'})

# ---- manifest structure (files not refreshed: these are structural lies)
def mm(fn): return lambda e, m: fn(m)
p, *_ = build('c-man-dup-file', mm(lambda m: m['files'].append(dict(m['files'][0]))), refresh=False); case('manifest-duplicate-file-entry', 'manifest.files lists data/tracks.json twice', p, 'FAIL', ['B self-check'])
p, *_ = build('c-man-dup-blob', mm(lambda m: m['blobs'].append(dict(m['blobs'][0]))), refresh=False); case('manifest-duplicate-blob-entry', 'manifest.blobs lists blobs/000001.bin twice', p, 'FAIL', ['B self-check'])
p, *_ = build('c-man-top', mm(lambda m: m.__setitem__('x', 1)), refresh=False); case('manifest-extra-top-key', 'an extra top-level manifest key', p, 'FAIL', ['B self-check', 'manifest.x differs'])
p, *_ = build('c-man-nest-missing', mm(lambda m: m['counts'].pop('localStorage')), refresh=False); case('manifest-missing-nested-key', 'manifest.counts lost a key', p, 'FAIL', ['B self-check', 'manifest.counts.localStorage differs'])
p, *_ = build('c-man-nest-extra', mm(lambda m: m['excluded'].__setitem__('extra', 1)), refresh=False); case('manifest-extra-nested-key', 'manifest.excluded gained a key', p, 'FAIL', ['B self-check', 'manifest.excluded.extra differs'])
p, *_ = build('c-man-counts', mm(lambda m: m['counts'].__setitem__('tracks', 99)), refresh=False); case('manifest-counts-wrong', 'manifest.counts.tracks says 99', p, 'FAIL', ['B self-check', 'manifest.counts.tracks differs'])
p, *_ = build('c-man-blob-swap', mm(lambda m: m['blobs'].__setitem__(slice(0, 2), [m['blobs'][1], m['blobs'][0]])), refresh=False); case('manifest-blobs-reordered', 'two manifest.blobs entries swapped', p, 'FAIL', ['B self-check'])
p, *_ = build('c-man-excl-nonsecret', mm(lambda m: m['excluded'].__setitem__('kv', ['plain'])), refresh=False); case('manifest-excluded-not-a-secret', 'manifest.excluded.kv lists a non-secret name', p, 'FAIL', ['B self-check'])
p, *_ = build('c-man-complete', mm(lambda m: m.__setitem__('complete', False)), refresh=False); case('manifest-complete-flipped', 'manifest.complete true -> false', p, 'FAIL', ['manifest.complete differs'])
p, *_ = build('c-man-audio', mm(lambda m: m.__setitem__('audioBytes', m['audioBytes'] + 1)), refresh=False); case('manifest-audioBytes-lie', 'manifest.audioBytes off by one', p, 'FAIL', ['B self-check', 'manifest.audioBytes differs'])

# ---- manifest.excluded.kv names: exactly the exporting browser's secret keys
p, *_ = build('c-excl-ok', mm(lambda m: m['excluded'].__setitem__('kv', ['secret:zzz'])), refresh=False)
case('excluded-names-match-browser', 'excluded.kv names changed to the secret key this (harness-read) browser holds', p, 'ALLOWED', ['manifest.excluded.kv'], {'secrets': ['secret:zzz']})
case('excluded-names-not-the-browsers', 'excluded.kv lists secret:zzz but the browser holds secret:yyy', p, 'FAIL', ['manifest.excluded.kv'], {'secrets': ['secret:yyy']})
p, *_ = build('c-excl-empty', mm(lambda m: m['excluded'].__setitem__('kv', [])), refresh=False)
case('excluded-names-missing', 'excluded.kv is empty although the browser holds secret:lastfm', p, 'FAIL', ['manifest.excluded.kv'], {'secrets': ['secret:lastfm']})

# ---- manifest.warnings: only the removal of the old-browser theme warning is allowed
TW = 'ps-theme had an unrecognized value and was not exported'
WA = build('a-with-theme-warning', mm(lambda m: m['warnings'].append(TW)), refresh=False)[0]
case('warning-theme-dropped', 'A has [orphan warning, theme warning]; B (a restored browser) has only the orphan warning', GOODP, 'ALLOWED', ['manifest.warnings'], a=WA)
p, *_ = build('c-warn-none', mm(lambda m: m.__setitem__('warnings', [])), refresh=False)
case('warning-orphan-dropped', 'the orphan-audio warning disappeared (data-derived: must be a FAIL)', p, 'FAIL', ['manifest.warnings differs'])
case('warning-both-dropped', 'A has [orphan, theme]; B has none (the orphan warning may not vanish with it)', p, 'FAIL', ['manifest.warnings differs'], a=WA)
case('warning-theme-added', 'B gained the theme warning that A did not have', WA, 'FAIL', ['manifest.warnings differs'])

json.dump(cases, open(os.path.join(out, 'cases.json'), 'w'), indent=1)
print('controls written:', len(cases))
