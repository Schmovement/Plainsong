#!/usr/bin/env python3
"""Phase 3B independent cover reader (Python stdlib only, shares no code with the app or the Node harness).
  python3 -I cover_check_3b.py <backup.zip> <out.json>
Reads data/tracks.json straight out of the backup ZIP and, for every track and for each of its `cover` and `origCover` fields, reports what is really there:
  kind  absent | empty | url | data | other     (data = an embedded image)
  for data: declared MIME (from the data: prefix), MIME by magic bytes, whether they agree, base64 canonical?, byte size, SHA-256 of the DECODED bytes,
            width/height read from the image header, and a CONTAINER-FRAMING check (PNG: every chunk CRC-32 correct and IEND is the last chunk; JPEG: SOF found and the
            data ends with EOI; GIF: trailer byte; WebP: RIFF size = file size - 8). This is NOT a decoder: it does not prove that the pixel data decompresses.
            (Decodability is proven separately by the browser itself, see decodeMatches in phase3b.test.js.)
Exit 0 and a report; exit 2 on a usage/IO error. The Node harness compares this report with what it read from IndexedDB itself."""
import sys, json, zipfile, zlib, base64, hashlib, re, struct


def png_check(b):
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    o, last, w, h, ok = 8, None, 0, 0, True
    while o + 12 <= len(b):
        n = struct.unpack('>I', b[o:o + 4])[0]; typ = b[o + 4:o + 8]
        if o + 12 + n > len(b):
            ok = False; break
        if zlib.crc32(b[o + 4:o + 8 + n]) & 0xffffffff != struct.unpack('>I', b[o + 8 + n:o + 12 + n])[0]:
            ok = False
        if typ == b'IHDR':
            w, h = struct.unpack('>II', b[o + 8:o + 16])
        last = typ; o += 12 + n
        if typ == b'IEND':
            break
    return {'mime': 'image/png', 'w': w, 'h': h, 'container_ok': ok and last == b'IEND' and o == len(b)}


def jpeg_check(b):
    if b[:3] != b'\xff\xd8\xff':
        return None
    o, dims = 2, None
    while o + 4 <= len(b):
        if b[o] != 0xFF:
            break
        while o < len(b) and b[o] == 0xFF:
            o += 1
        m = b[o]; o += 1
        if m == 0xD9:
            break
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            continue
        n = struct.unpack('>H', b[o:o + 2])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            dims = (struct.unpack('>H', b[o + 5:o + 7])[0], struct.unpack('>H', b[o + 3:o + 5])[0])
        if m == 0xDA:
            break
        o += n
    return {'mime': 'image/jpeg', 'w': dims[0] if dims else 0, 'h': dims[1] if dims else 0, 'container_ok': bool(dims) and b[-2:] == b'\xff\xd9'}


def gif_check(b):
    if b[:6] not in (b'GIF87a', b'GIF89a'):
        return None
    w, h = struct.unpack('<HH', b[6:10]); return {'mime': 'image/gif', 'w': w, 'h': h, 'container_ok': b[-1:] == b'\x3b'}


def webp_check(b):
    if b[:4] != b'RIFF' or b[8:12] != b'WEBP':
        return None
    w = h = 0; k = b[12:16]
    if k == b'VP8 ' and len(b) >= 30 and b[23:26] == b'\x9d\x01\x2a':
        w, h = struct.unpack('<HH', b[26:30]); w &= 0x3fff; h &= 0x3fff
    elif k == b'VP8L' and len(b) >= 25 and b[20] == 0x2f:
        v = struct.unpack('<I', b[21:25])[0]; w = (v & 0x3fff) + 1; h = ((v >> 14) & 0x3fff) + 1
    elif k == b'VP8X' and len(b) >= 30:
        w = int.from_bytes(b[24:27], 'little') + 1; h = int.from_bytes(b[27:30], 'little') + 1
    return {'mime': 'image/webp', 'w': w, 'h': h, 'container_ok': struct.unpack('<I', b[4:8])[0] == len(b) - 8}


def describe(v):
    if v is None:
        return {'kind': 'absent'}
    if not isinstance(v, str):
        return {'kind': 'other', 'type': type(v).__name__}
    if v == '':
        return {'kind': 'empty'}
    if re.match(r'^https?://', v):
        return {'kind': 'url', 'value': v}
    m = re.match(r'^data:(image/[a-z+.-]+);base64,(.*)$', v, re.S)
    if not m:
        return {'kind': 'other', 'type': 'str'}
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        return {'kind': 'data', 'declared': m.group(1), 'decodes': False}
    info = png_check(raw) or jpeg_check(raw) or gif_check(raw) or webp_check(raw) or {'mime': None, 'w': 0, 'h': 0, 'container_ok': False}
    return {'kind': 'data', 'declared': m.group(1), 'decodes': True, 'magic_mime': info['mime'], 'agree': info['mime'] == m.group(1),
            'canonical_b64': base64.b64encode(raw).decode() == m.group(2), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'w': info['w'], 'h': info['h'], 'container_ok': info['container_ok']}


def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(2)
    z = zipfile.ZipFile(sys.argv[1])
    tracks = json.loads(z.read('data/tracks.json'))
    out = {'schema': 'cover_check_3b.v1', 'file': sys.argv[1], 'tracks': [
        {'id': t['id'], 'cover': describe(t.get('cover')), 'origCover': describe(t.get('origCover')), 'has_origCover': 'origCover' in t} for t in tracks]}
    json.dump(out, open(sys.argv[2], 'w'), indent=1)
    print(len(tracks), 'tracks read')


main()
