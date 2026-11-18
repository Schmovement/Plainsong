#!/usr/bin/env python3
"""Independent oracle for the Phase 2C round-trip suite. Shares NO code with the app: Python zipfile / zlib / json / hashlib only.

  python3 -I oracle_2c.py truth   <backup.zip> <out.json> [--forbid STRING ...]
  python3 -I oracle_2c.py compare <A.zip> <B.zip> <out.json> [--b-theme light|dark|none] [--b-secret-keys 'k1|k2'] [--time-unavailable]

Exit status: compare 0 = valid report with 0 failures, 1 = valid report with failures, 2 = oracle error (no report is trusted). truth 0 / 2.

truth   : what a correct reader must see in one backup (manifest, tracks, playlists, kv, localStorage block, every audio entry's key/MIME/size/
          SHA-256) plus a SELF-CHECK: documented layout and entry order, stored (uncompressed) entries, CRC-32 of every entry recomputed against
          the ZIP header AND the manifest, sizes, payloadBytes/audioBytes, and STRICT MANIFEST VALIDATION (exact top-level key list and order,
          exact nested key sets, files = the four documented entries once each in order, blobs = blobs/000001.bin.. once each in order with unique
          keys, counts equal the real numbers, excluded.kv unique secret: names). For every --forbid string it counts occurrences in the raw
          file and per entry (credential-leak scan).
compare : B (made after a restore of A) must equal A. EVERYTHING must be equal except the narrow differences below, each with its reason and
          the constraint it must satisfy; any other difference, anywhere, including a missing or extra manifest key at any depth, is a FAIL.
          A or B holding any secret:-prefixed key (case-insensitive) in kv.json is itself a FAIL.

ALLOWED differences (nothing else is ignored; no whole field is skipped):
  manifest.createdAt            wall-clock export time; valid UTC ISO-8601 and B >= A.
  kv "session".time             the live <audio> position when the export ran. Normally equal. Allowed: |B - A| <= 0.25 s (seek rounding);
                                B == 0 ONLY with --time-unavailable, which the harness passes only after proving from the browser state that the
                                saved current song cannot report a position (a web song while offline). No other value, rewind or jump is allowed.
  manifest derived numbers      files[kv.json|localstorage.json].bytes/crc32 and payloadBytes: only when that file differs for an allowed reason
                                above/below; B's numbers are proven against B's real bytes by the self-check.
  manifest.warnings             only the removal of the single warning 'ps-theme had an unrecognized value and was not exported' (it describes the
                                OLD exporting browser's localStorage, which a restore never recreates). Any other change to warnings is a FAIL.
  manifest.excluded.kv          names (never values) of the EXPORTING browser's secret: keys; must equal exactly --b-secret-keys (read straight
                                from IndexedDB by the harness).
  localstorage.json             when A has NO ps-theme the restore leaves the target's own theme alone, so B may carry exactly the target's theme
                                (--b-theme). If A has a ps-theme, B must carry the same one. manifest.counts.localStorage follows and must equal
                                the real number of keys in B.
"""
import sys, json, zipfile, hashlib, zlib, datetime, math

SCHEMA = 'oracle_2c.compare.v1'
LAYOUT = ['manifest.json', 'data/tracks.json', 'data/playlists.json', 'data/kv.json', 'data/localstorage.json']
TOP = ['format', 'formatVersion', 'createdAt', 'generator', 'complete', 'source', 'counts', 'audioBytes', 'payloadBytes', 'integrity', 'files', 'blobs', 'excluded', 'problems', 'warnings', 'limits']
NESTED = {'source': ['database', 'databaseVersion'], 'counts': ['tracks', 'playlists', 'kv', 'blobs', 'localStorage'], 'integrity': ['algorithm', 'note'], 'excluded': ['kv', 'localStorage', 'credentials'], 'limits': ['maxBytes', 'maxEntries']}
FILE_KEYS = ['path', 'bytes', 'crc32']; BLOB_KEYS = ['key', 'path', 'bytes', 'type', 'crc32']
TIME_TOL = 0.25
THEME_WARNING = 'ps-theme had an unrecognized value and was not exported'


def is_secret(k):
    return isinstance(k, str) and k.lower().startswith('secret:')


def hexcrc(d):
    return '%08x' % (zlib.crc32(d) & 0xffffffff)


def validate_manifest(man, infos, tracks, playlists, kv, ls, nblobs):
    bad = []
    if list(man.keys()) != TOP:
        bad.append('manifest top-level keys %s != documented %s' % (list(man.keys()), TOP))
    for k, ks in NESTED.items():
        if not isinstance(man.get(k), dict) or list(man[k].keys()) != ks:
            bad.append('manifest.%s keys %s != documented %s' % (k, list(man[k].keys()) if isinstance(man.get(k), dict) else man.get(k), ks))
    if man.get('formatVersion') != 1 or man.get('format') != 'plainsong-backup':
        bad.append('format/formatVersion not plainsong-backup/1')
    files = man.get('files')
    if not isinstance(files, list) or [f.get('path') for f in files if isinstance(f, dict)] != LAYOUT[1:] or any(list(f.keys()) != FILE_KEYS for f in files):
        bad.append('manifest.files is not the four documented entries, each once, in order, with exactly path/bytes/crc32')
    blobs = man.get('blobs')
    if not isinstance(blobs, list) or any(not isinstance(b, dict) or list(b.keys()) != BLOB_KEYS for b in blobs):
        bad.append('manifest.blobs entries do not have exactly key/path/bytes/type/crc32')
    else:
        if [b['path'] for b in blobs] != ['blobs/%06d.bin' % (i + 1) for i in range(len(blobs))]:
            bad.append('manifest.blobs paths are not blobs/000001.bin.. once each in order')
        if len(set(b['key'] for b in blobs)) != len(blobs):
            bad.append('manifest.blobs has duplicate keys')
        if len(blobs) != nblobs:
            bad.append('manifest.blobs has %d entries but the ZIP holds %d audio entries' % (len(blobs), nblobs))
    real = {'tracks': len(tracks), 'playlists': len(playlists), 'kv': len(kv), 'blobs': nblobs, 'localStorage': len(ls)}
    if isinstance(man.get('counts'), dict) and man['counts'] != real:
        bad.append('manifest.counts %s != real %s' % (man['counts'], real))
    ex = man.get('excluded', {}).get('kv') if isinstance(man.get('excluded'), dict) else None
    if not isinstance(ex, list) or len(set(ex)) != len(ex) or not all(is_secret(x) for x in ex):
        bad.append('manifest.excluded.kv is not a list of unique secret: names: %r' % (ex,))
    if not isinstance(man.get('problems'), list) or not isinstance(man.get('warnings'), list):
        bad.append('manifest.problems / warnings are not lists')
    return bad


def selfcheck(z, infos, man, tracks, playlists, kv, ls):
    bad = []
    names = [i.filename for i in infos]
    exp = LAYOUT + ['blobs/%06d.bin' % (n + 1) for n in range(len(infos) - len(LAYOUT))]
    if names != exp:
        bad.append('entry names/order differ from the documented layout: %s' % names[:8])
    for i in infos:
        if i.compress_type != 0:
            bad.append('entry %s is not stored' % i.filename)
        data = z.read(i.filename)
        if (zlib.crc32(data) & 0xffffffff) != i.CRC:
            bad.append('zip header CRC wrong for %s' % i.filename)
        if len(data) != i.file_size:
            bad.append('size wrong for %s' % i.filename)
    if z.testzip() is not None:
        bad.append('zipfile.testzip failed')
    nblobs = max(0, len(infos) - len(LAYOUT))
    bad += validate_manifest(man, infos, tracks, playlists, kv, ls, nblobs)
    for f in (man.get('files') or []):
        if isinstance(f, dict) and f.get('path') in names:
            data = z.read(f['path'])
            if len(data) != f.get('bytes') or hexcrc(data) != f.get('crc32'):
                bad.append('manifest size/crc wrong for %s' % f['path'])
    audio = 0
    for b in (man.get('blobs') or []):
        if isinstance(b, dict) and b.get('path') in names:
            data = z.read(b['path']); audio += len(data)
            if len(data) != b.get('bytes') or hexcrc(data) != b.get('crc32'):
                bad.append('manifest size/crc wrong for %s' % b['path'])
    pay = sum(i.file_size for i in infos if i.filename != 'manifest.json')
    if man.get('payloadBytes') != pay:
        bad.append('payloadBytes %s != %s' % (man.get('payloadBytes'), pay))
    if man.get('audioBytes') != audio:
        bad.append('audioBytes %s != %s' % (man.get('audioBytes'), audio))
    return bad


def truth(path, forbid):
    raw = open(path, 'rb').read()
    z = zipfile.ZipFile(path)
    infos = z.infolist()
    man = json.loads(z.read('manifest.json'))
    tracks, playlists = json.loads(z.read('data/tracks.json')), json.loads(z.read('data/playlists.json'))
    kv, ls = json.loads(z.read('data/kv.json')), json.loads(z.read('data/localstorage.json'))
    res = {
        'schema': 'oracle_2c.truth.v1', 'file': path, 'fileSha256': hashlib.sha256(raw).hexdigest(), 'fileBytes': len(raw),
        'entries': [{'name': i.filename, 'size': i.file_size, 'crc32': '%08x' % i.CRC, 'sha256': hashlib.sha256(z.read(i.filename)).hexdigest()} for i in infos],
        'manifest': man, 'tracks': tracks, 'playlists': playlists, 'kv': kv, 'ls': ls, 'blobs': [],
    }
    for b in man['blobs']:
        d = z.read(b['path'])
        res['blobs'].append({'key': b['key'], 'type': b['type'], 'size': len(d), 'sha256': hashlib.sha256(d).hexdigest(), 'path': b['path']})
    res['selfcheck'] = selfcheck(z, infos, man, tracks, playlists, kv, ls)
    hits = {}
    for s in forbid:
        sb = s.encode('utf-8')
        per = {i.filename: z.read(i.filename).count(sb) for i in infos}
        hits[s] = {'raw': raw.count(sb), 'entries': {k: v for k, v in per.items() if v}}
    res['forbiddenHits'] = hits
    res['secretKeysInKv'] = [x['key'] for x in kv if is_secret(x.get('key'))]
    return res


def parse_iso(s):
    return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)


def label(path, man):
    out = 'manifest'
    for i, p in enumerate(path):
        if isinstance(p, int):
            tag = None
            if path[0] == 'files' and i == 1 and isinstance(man.get('files'), list) and p < len(man['files']) and isinstance(man['files'][p], dict):
                tag = man['files'][p].get('path')
            elif path[0] == 'blobs' and i == 1 and isinstance(man.get('blobs'), list) and p < len(man['blobs']) and isinstance(man['blobs'][p], dict):
                tag = man['blobs'][p].get('path')
            out += '[%s]' % (tag if tag else p)
        else:
            out += '.' + str(p)
    return out


def jdiff(a, b, path=()):
    """Recursive diff of two JSON values: list of (path, a, b). Missing/extra keys and length changes are differences. excluded.kv is a leaf."""
    if path in (('excluded', 'kv'), ('warnings',)):
        return [] if a == b else [(path, a, b)]
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in list(a.keys()) + [k for k in b.keys() if k not in a]:
            if k not in a or k not in b:
                out.append((path + (k,), a.get(k, '<missing>'), b.get(k, '<missing>')))
            else:
                out += jdiff(a[k], b[k], path + (k,))
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = [] if len(a) == len(b) else [(path + ('<length>',), len(a), len(b))]
        for i in range(min(len(a), len(b))):
            out += jdiff(a[i], b[i], path + (i,))
        return out
    return [] if (type(a) is type(b) and a == b) else [(path, a, b)]


def leaves(v):
    if isinstance(v, dict):
        return sum(leaves(x) for x in v.values()) or 1
    if isinstance(v, list):
        return sum(leaves(x) for x in v) or 1
    return 1


def compare(pa, pb, b_theme, b_secret_keys, time_unavailable):
    A, B = truth(pa, []), truth(pb, [])
    out = []

    def add(check, status, detail=''):
        out.append({'check': check, 'status': status, 'detail': detail})

    for tag, T in (('A', A), ('B', B)):
        add('%s self-check (layout, stored, CRC-32 vs ZIP header and manifest, sizes, STRICT manifest shape: key lists/order, files once each, blobs once each, counts, excluded names)' % tag, 'exact' if not T['selfcheck'] else 'FAIL', '; '.join(T['selfcheck']))
        add('%s has no secret: key in kv.json (case-insensitive): %s' % (tag, T['secretKeysInKv']), 'exact' if not T['secretKeysInKv'] else 'FAIL', '' if not T['secretKeysInKv'] else 'credentials must never be in an export')
    an, bn = [e['name'] for e in A['entries']], [e['name'] for e in B['entries']]
    add('entry names and order identical (%d entries)' % len(an), 'exact' if an == bn else 'FAIL', '' if an == bn else '%s vs %s' % (an, bn))
    ea, eb = {e['name']: e for e in A['entries']}, {e['name']: e for e in B['entries']}
    for n in an:
        if n in ('manifest.json', 'data/kv.json', 'data/localstorage.json') or n not in eb:
            continue
        same = ea[n]['sha256'] == eb[n]['sha256'] and ea[n]['size'] == eb[n]['size']
        add('%s byte-identical (sha256 %s)' % (n, ea[n]['sha256'][:12]), 'exact' if same else 'FAIL', '' if same else 'sha256 %s vs %s' % (ea[n]['sha256'], eb[n]['sha256']))
    ka = [(b['key'], b['type'], b['size'], b['sha256']) for b in A['blobs']]
    kb = [(b['key'], b['type'], b['size'], b['sha256']) for b in B['blobs']]
    add('audio list identical in order: key, MIME, size, SHA-256 for all %d entries' % len(ka), 'exact' if ka == kb else 'FAIL', '' if ka == kb else '%s vs %s' % (ka, kb))
    for k in ('tracks', 'playlists'):
        same = json.dumps(A[k], ensure_ascii=False) == json.dumps(B[k], ensure_ascii=False)
        add('%s records identical, same order and same key order (%d records)' % (k, len(A[k])), 'exact' if same else 'FAIL')
    # kv
    kva, kvb = {x['key']: x['value'] for x in A['kv']}, {x['key']: x['value'] for x in B['kv']}
    ordk = [x['key'] for x in A['kv']] == [x['key'] for x in B['kv']]
    add('kv key set and order identical: %s' % [x['key'] for x in A['kv']], 'exact' if ordk and set(kva) == set(kvb) else 'FAIL', '' if ordk else '%s vs %s' % ([x['key'] for x in A['kv']], [x['key'] for x in B['kv']]))
    kv_changed = False
    for key in kva:
        if key not in kvb:
            continue
        a, b = kva[key], kvb[key]
        if json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False):
            add('kv[%s] identical' % key, 'exact')
            continue
        if key == 'session' and isinstance(a, dict) and isinstance(b, dict) and list(a.keys()) == list(b.keys()):
            diff = [f for f in a if json.dumps(a[f], ensure_ascii=False) != json.dumps(b[f], ensure_ascii=False)]
            if diff == ['time']:
                ta, tb = a['time'], b['time']
                num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
                if num(ta) and num(tb) and abs(tb - ta) <= TIME_TOL:
                    add('kv[session] identical except time (A %r, B %r): bounded drift <= %s s' % (ta, tb, TIME_TOL), 'allowed', 'seek rounding of the live <audio> position')
                    kv_changed = True
                elif time_unavailable and num(ta) and tb == 0:
                    add('kv[session] identical except time (A %r, B 0): position unavailable' % (ta,), 'allowed', 'explicit harness evidence (--time-unavailable): the saved current song cannot report a position offline')
                    kv_changed = True
                else:
                    add('kv[session].time changed beyond the allowance (A %r, B %r)' % (ta, tb), 'FAIL', 'only |B-A| <= %s, or B == 0 with explicit --time-unavailable evidence' % TIME_TOL)
                continue
            add('kv[session] differs in fields %s' % diff, 'FAIL', json.dumps({f: [a[f], b[f]] for f in diff}, ensure_ascii=False)[:600])
            continue
        add('kv[%s] differs' % key, 'FAIL', json.dumps([a, b], ensure_ascii=False)[:600])
    # localStorage block
    ls_allowed = False
    la, lb = A['ls'], B['ls']
    if la == lb:
        add('localstorage.json identical %s' % json.dumps(la), 'exact')
    elif 'ps-theme' not in la and b_theme in ('light', 'dark') and lb == {'ps-theme': b_theme}:
        ls_allowed = True
        add('localstorage.json: A had no ps-theme; B carries the target browser\'s own theme %r' % b_theme, 'allowed', 'a backup without a theme leaves the target\'s theme alone, so its re-export contains that theme')
    else:
        add('localstorage.json differs', 'FAIL', '%s vs %s (b-theme %r)' % (la, lb, b_theme))
    # manifest: recursive diff; every difference must match a named rule
    ma, mb = A['manifest'], B['manifest']
    diffs = jdiff(ma, mb)
    add('manifest compared leaf by leaf (%d values in A): %d differ (each listed below)' % (leaves(ma), len(diffs)), 'exact')
    for path, a, b in diffs:
        lab = label(path, ma)
        fpath = ma['files'][path[1]]['path'] if path[0] == 'files' and len(path) > 2 and isinstance(path[1], int) and path[1] < len(ma['files']) else None
        if path == ('createdAt',):
            try:
                ok = parse_iso(b) >= parse_iso(a)
            except Exception:
                ok = False
            add('%s (A %s, B %s)' % (lab, a, b), 'allowed' if ok else 'FAIL', 'wall-clock time of the export' if ok else 'B must be a valid later time')
        elif path == ('payloadBytes',) and (kv_changed or ls_allowed):
            add('%s (A %s, B %s)' % (lab, a, b), 'allowed', 'derived from an allowed file difference; B\'s number is proven against B\'s real bytes by the self-check')
        elif fpath == 'data/kv.json' and path[2] in ('bytes', 'crc32') and kv_changed:
            add('%s (A %s, B %s)' % (lab, a, b), 'allowed', 'derived from the allowed kv session.time difference; proven against B\'s real bytes by the self-check')
        elif fpath == 'data/localstorage.json' and path[2] in ('bytes', 'crc32') and ls_allowed:
            add('%s (A %s, B %s)' % (lab, a, b), 'allowed', 'derived from the allowed theme difference; proven against B\'s real bytes by the self-check')
        elif path == ('counts', 'localStorage') and ls_allowed and b == len(B['ls']):
            add('%s (A %s, B %s)' % (lab, a, b), 'allowed', 'follows the allowed theme difference and equals the real number of keys in B')
        elif path == ('warnings',) and isinstance(a, list) and isinstance(b, list) and THEME_WARNING in a and b == [w for w in a if w != THEME_WARNING]:
            add('%s (A %s, B %s)' % (lab, a, b), 'allowed', 'the warning describes the OLD exporting browser\'s state (a ps-theme value that was deliberately not exported), so a restored browser cannot repeat it; only that exact warning, only its removal')
        elif path == ('excluded', 'kv') and b_secret_keys is not None and sorted(b) == sorted(b_secret_keys) and sorted(a) != sorted(b):
            add('%s (A %s, B %s)' % (lab, a, b), 'allowed', 'names only (never values) of the secret: keys the EXPORTING browser really holds (read from IndexedDB by the harness)')
        else:
            add('%s differs (A %s, B %s)' % (lab, json.dumps(a, ensure_ascii=False)[:120], json.dumps(b, ensure_ascii=False)[:120]), 'FAIL', 'not an allowed difference')
    if b_secret_keys is not None and sorted(mb['excluded']['kv']) != sorted(b_secret_keys):
        add('manifest.excluded.kv must list exactly the secret: keys the exporting browser holds %s' % b_secret_keys, 'FAIL', 'B lists %s' % mb['excluded']['kv'])
    elif b_secret_keys is not None:
        add('manifest.excluded.kv equals the secret: key names the exporting browser holds %s' % b_secret_keys, 'exact')
    return {'schema': SCHEMA, 'A': pa, 'B': pb, 'options': {'bTheme': b_theme, 'bSecretKeys': b_secret_keys, 'timeUnavailable': time_unavailable}, 'results': out,
            'fail': sum(1 for r in out if r['status'] == 'FAIL'), 'allowed': sum(1 for r in out if r['status'] == 'allowed'), 'exact': sum(1 for r in out if r['status'] == 'exact')}


def main():
    cmd = sys.argv[1]
    if cmd == 'truth':
        args = sys.argv[2:]
        forbid = []
        if '--forbid' in args:
            i = args.index('--forbid'); forbid = args[i + 1:]; args = args[:i]
        r = truth(args[0], forbid)
        json.dump(r, open(args[1], 'w'), ensure_ascii=False)
        print('ok', len(r['tracks']), 'tracks', len(r['blobs']), 'blobs', 'selfcheck-problems=%d' % len(r['selfcheck']))
        return 0
    if cmd == 'compare':
        args = sys.argv[2:]
        theme = None; sk = None; tu = False
        if '--time-unavailable' in args:
            tu = True; args.remove('--time-unavailable')
        if '--b-theme' in args:
            i = args.index('--b-theme'); theme = args[i + 1]; args = args[:i] + args[i + 2:]
        if '--b-secret-keys' in args:
            i = args.index('--b-secret-keys'); sk = [x for x in args[i + 1].split('|') if x]; args = args[:i] + args[i + 2:]
        r = compare(args[0], args[1], theme, sk, tu)
        json.dump(r, open(args[2], 'w'), ensure_ascii=False, indent=1)
        print('exact=%d allowed=%d FAIL=%d' % (r['exact'], r['allowed'], r['fail']))
        for x in r['results']:
            if x['status'] != 'exact':
                print(' ', x['status'], x['check'], '::', x['detail'][:200])
        return 1 if r['fail'] else 0
    sys.stderr.write('usage\n'); return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        sys.stderr.write('ORACLE ERROR: %s: %s\n' % (type(e).__name__, e)); sys.exit(2)
