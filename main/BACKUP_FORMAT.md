# Plainsong backup format, version 1

Status: **export only.** Plainsong p1 can write this format. It cannot read it back; restore is Phase 2 and is not implemented.

Produced by the "Back up library" buttons (top bar icon and sidebar). Everything happens in the browser; nothing is uploaded.

## Container

A standard **ZIP** file with every entry **stored** (method 0, no compression, because audio is already compressed). UTF-8 names, no ZIP64, no encryption, no archive comment, no data descriptors. Any ZIP tool can open it.

```
plainsong-backup-YYYYMMDD-HHMMSS.zip            (local time in the name)
plainsong-backup-INCOMPLETE-YYYYMMDD-HHMMSS.zip (only if some audio was missing, see "Incomplete backups")
  manifest.json            first entry
  data/tracks.json         IndexedDB store "tracks"
  data/playlists.json      IndexedDB store "playlists"
  data/kv.json             IndexedDB store "kv" (minus excluded keys)
  data/localstorage.json   allow-listed localStorage keys
  blobs/000001.bin ...     IndexedDB store "blobs": original audio Blob bytes, one entry per stored Blob
```

## What is captured

| Source | Where | Exactness |
|--------|-------|-----------|
| `tracks` store (local tracks and saved web tracks) | `data/tracks.json`, array in store key order | every record as stored, including `cover` data URL, `lyrics`, `lrc`, `lyricsFrom`, `plays`, `last`, `liked`, `added` |
| `playlists` store | `data/playlists.json`, array in key order | every record, `ids` order preserved |
| `kv` store | `data/kv.json`, array of `{ "key", "value" }` in key order | includes `session` (queue, speed, EQ, volume, `webs` snapshots of unsaved web tracks) and `hist` (history with web `snap` snapshots) |
| `blobs` store | `blobs/NNNNNN.bin` plus `manifest.blobs[]` | **byte-identical** to the stored Blob; the exact store key and the Blob MIME type (possibly empty) are kept in the manifest, never in the entry name |
| localStorage | `data/localstorage.json` | only `ps-theme`, and only if its value is `light` or `dark` |

The audio entry number (`000001`) is the position in store key order. The authoritative key is `manifest.blobs[i].key`. Keys may contain any characters (the tests use `orphan/ü key 🎧`).

## manifest.json

```json
{
  "format": "plainsong-backup",
  "formatVersion": 1,
  "createdAt": "2026-11-04T08:10:00.000Z",
  "generator": "Plainsong",
  "complete": true,
  "source": { "database": "plainsong", "databaseVersion": 1 },
  "counts": { "tracks": 6, "playlists": 2, "kv": 3, "blobs": 6, "localStorage": 1 },
  "audioBytes": 0, "payloadBytes": 0,
  "integrity": { "algorithm": "crc32", "note": "..." },
  "files": [ { "path": "data/tracks.json", "bytes": 0, "crc32": "8 hex digits" } ],
  "blobs": [ { "key": "<store key>", "path": "blobs/000001.bin", "bytes": 0, "type": "audio/mpeg", "crc32": "8 hex digits" } ],
  "excluded": { "kv": ["secret:..."], "localStorage": "only these keys are exported: ps-theme", "credentials": "integration credentials are never exported by default" },
  "problems": [ { "id": "<track id>", "title": "...", "reason": "..." } ],
  "warnings": [ "..." ],
  "limits": { "maxBytes": 2147483648, "maxEntries": 60000 }
}
```

- `formatVersion` is an integer. A reader must refuse a version it does not know.
- `payloadBytes` = sum of every non-manifest entry; `audioBytes` = sum of audio entries.
- `excluded.kv` lists excluded key **names** only, never values.
- `warnings` are informational (for example an audio blob with no library entry, which is included as-is).

## Integrity

- Every entry has a byte length and **CRC-32** in the ZIP headers and again in the manifest (for everything except the manifest itself). They must agree.
- CRC-32 detects accidental corruption and truncation. It does **not** detect deliberate tampering; a backup file should be treated as untrusted input by any restore.
- The exporter reads every audio byte once to compute its CRC, assembles the ZIP from references to the original Blobs, then self-checks the ZIP structure (end record, central directory, local headers, sizes, CRCs) before offering the download.

## Consistency

The exporter first writes any pending session/history save (a debounced save that has not reached the database yet, plus a fresh playhead position), then reads all four stores in **one read-only IndexedDB transaction**. That transaction is a single snapshot: later writes (playback counters, imports, deletions) cannot change or mix into it. Audio is held as immutable Blob handles, so later changes cannot alter the bytes either. Imports are blocked while a backup runs, and a backup is refused while an import runs.

## Credentials

Never exported by default:

- `kv` keys starting with `secret:` are skipped (key names are listed in `excluded.kv`).
- localStorage is allow-list only. Adding a key means editing `BACKUP.lsAllow` on purpose.

**Binding rule for later phases (scrobbling, Phases 15-16):** any token, session key, password or API secret must be stored under a `kv` key that starts with `secret:` (or outside the app's storage), never in a normal `kv` key or an allow-listed localStorage key. A Last.fm signing secret must never be shipped inside this client-only app; that needs a protected signing boundary (to be confirmed against the provider documentation in Phase 16).

## Limits (explicit, checked before anything is written)

| Limit | Value | Behaviour when exceeded |
|-------|-------|--------------------------|
| Total payload (audio + data files) | 2 GiB (`BACKUP_LIMITS.maxBytes`) | refused with a message; the audio read stops as soon as the limit is passed; no file is produced |
| Entries | 60,000 entries including the 5 non-audio ones (`BACKUP_LIMITS.maxEntries`), so at most 59,995 audio files; the ZIP32 entry-count ceiling (65,535) is a hard upper bound | refused with a message |
| ZIP size | ZIP64 is not implemented, so the 4 GiB ZIP32 ceiling applies (2 GiB cap keeps well under it) | refused |

Splitting a bigger library over several files is not built. The memory behaviour with multi-gigabyte libraries and the download of very large Blobs on iOS/Safari have **not** been tested (largest tested entry: 64 MiB).

## Refusals (no file is produced, nothing is called complete)

- IndexedDB unavailable, so the library lives only in memory.
- Songs shown in the library that are not in browser storage.
- Saved values that JSON cannot represent exactly (NaN, Infinity, Date, Map, typed arrays, ...). `undefined` object properties are dropped (equivalent for this app); `undefined` list slots are refused.
- Non-string store keys, non-Blob audio values, too many entries, over the size limit.
- A stored audio Blob that cannot be read.
- Empty library (no tracks, no playlists, no audio): "Nothing to back up yet".

## Incomplete backups

If a local track has no usable audio (missing or zero bytes) the user is asked. **Cancel** produces nothing. **Export incomplete backup** produces a file named `plainsong-backup-INCOMPLETE-...zip` with `"complete": false` and the affected tracks in `problems[]`. A restore must treat `complete: false` as a partial backup and say so.

## Notes for Phase 2 (restore) - not implemented

A restore must: parse and validate the whole archive (version, CRC-32 and size of every entry, JSON shape, blob keys vs entries, size and entry limits) before touching the database; show a preview; replace or merge inside a single transaction with a rollback path; never trust paths or keys from the file beyond the manifest mapping; and respect `complete: false`.
