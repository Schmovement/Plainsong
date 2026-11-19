# Plainsong backup format, version 1

Status: **export works (Phase 1), the strict reader works (Phase 2A, `readBackupZip`), restore works (Phase 2B, replace-only, with a preview and a separate confirmation), and export-restore-export round trips through the real UI were measured against an independent oracle (Phase 2C, see "Round trips").** Phase 2 is complete at the p2 checkpoint, with the limits listed at the end. **Phase 3A (song info editing) adds two optional fields to track records, `genre` and `origMeta`; see "Track metadata fields (Phase 3A)".** The ZIP layout, manifest and format version are unchanged. **Phase 3B (custom cover editing) adds one optional field to track records, `origCover`; see "Track cover fields (Phase 3B)".** Still no ZIP-format or format-version change.

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

## Reader rules (Phase 2A, implemented, read-only)

`readBackupZip(file, {ctl, onProgress, limits, allowIncomplete})` treats the file as hostile. It performs **no** IndexedDB or localStorage write, opens no database, makes no network request, and copies no audio into memory (the audio it returns is a list of lazy Blob slices of the user's file). It returns a package (`man, tracks, playlists, kv, ls, blobs[{key,size,type,crc32,blob}], orphans, missingLocal, warnings, summary`) only if **everything** below holds; otherwise it throws an error carrying a machine-readable `code` and a plain message ending "Nothing was changed."

**Container (exactly the documented layout):** end record at the very end of the file with no comment, no ZIP64 markers, one disk; directory size/offset consistent with the file size; every directory entry method 0 (stored), flags `0` or `0x0800` only, no extra field, no entry comment, version needed <= 20; names printable ASCII 1..64 bytes and exactly `manifest.json`, `data/tracks.json`, `data/playlists.json`, `data/kv.json`, `data/localstorage.json`, `blobs/NNNNNN.bin`; no duplicate names; entries in the documented order (manifest first, the four data files, then audio numbered consecutively from 000001); entries stored back to back from offset 0 to the directory with no gaps, overlaps or hidden bytes; every local header agrees with the directory (flags, method, CRC, sizes, name, no extra).

**Integrity:** CRC-32 of every entry recomputed from the real bytes and compared with the ZIP header and with the manifest; manifest sizes, `payloadBytes` and `audioBytes` recomputed; `counts` compared with the real record counts.

**Manifest:** `format` = `plainsong-backup`; `formatVersion` an integer equal to **1** (anything else is refused, with a "newer Plainsong" message for higher numbers); `source` = plainsong database version 1; `complete` boolean; valid `createdAt`; `files[]` exactly the four data files; `blobs[]` one per audio entry in order, with unique ascending string keys, exact `bytes`/`crc32`, and a MIME `type` that a Blob can store unchanged (printable ASCII, lower case); `problems`/`warnings`/`excluded` well formed; `complete:true` with problems listed is inconsistent.

**Data (JSON, strict UTF-8, no BOM):** tracks need unique ascending string `id`, `kind` local/web, text `title`/`artist`/`album`, numeric fields non-negative numbers, `liked` boolean, `cover` empty / embedded png-jpeg-gif-webp data URL / http(s) address, web songs an http(s) `url` (`javascript:`, `data:`, `file:` and others refused), `link` empty or http(s). Playlists need unique ascending `id`, text `name`, `ids` a list of text. `kv` entries are exactly `{key, value}` with unique ascending keys. `session` and `hist` are shape-checked (queue lists of ids, `qi` whole number, `vol` 0..1, `rate` 0.25..3, `eq` ten numbers, `npTab` one of queue/lyrics/sound, web snapshots as above). `localstorage.json` may contain only allow-listed keys (`ps-theme` = light/dark). Any object key `__proto__` or nesting deeper than 40 is refused. Unknown extra fields inside records are **kept** untouched (forward compatible); unknown top-level manifest fields are ignored.

**Credentials:** a `kv` key starting with `secret:` (any letter case) anywhere in a backup refuses the whole file: a genuine export never contains one, so the file is not genuine.

**Cross references:** every local song must have non-empty audio when `complete:true`; when `complete:false` every song without audio must be listed in `problems`. Audio whose key matches no song (orphan) and playlist entries pointing at unknown songs are accepted, reported in `warnings`/`summary`, and kept as they are.

**Incomplete backups:** after full validation a `complete:false` file is refused by default (`code: "incomplete"`, the validated package and problem list attached to the error). `allowIncomplete:true` returns it for inspection. The restore (Phase 2B) never uses that option: an incomplete backup is refused with an explanation.

**Refusal codes:** `not-zip eocd zip64 multidisk comment count directory cd-entry method flags extra name duplicate unexpected-entry layout order local-header limits read crc utf8 manifest-json manifest-shape format version db-version blob-type duplicate-key duplicate-id counts json shape secret localstorage reference incomplete`.

**Reader limits** (overridable only by tests): file <= 2 GiB + 16 MiB; payload <= 2 GiB; entries <= 60,000; each data JSON file <= 256 MiB (it is parsed in memory); manifest <= 4 MiB; entry name <= 64 bytes; keys/ids <= 1024 characters.

**What the reader cannot detect (be honest about this):** CRC-32 is not tamper-proof, so a file that was edited and re-sealed consistently (new CRCs, matching manifest) is accepted if it is well formed; duplicate property names inside one JSON object are not detected (`JSON.parse` keeps the last); a hostile but well-formed backup can contain any text (shown escaped by the UI) and may point saved web songs at any http(s) address, which the player contacts only when that song is played.

## Restore (Phase 2B, implemented)

Entry points: "Restore from backup…" in the sidebar footer and the top bar (both open a `.zip` file chooser). Everything is local; nothing is uploaded. The restore code makes no network request: it was measured with every non-local request blocked and counted (Phase 2C). It ends on the **Library** screen (since 2C; before that it ended on Home, see "Landing screen and network").

**Policy.** Replace-only (no merge). Incomplete (`complete:false`) backups are refused. A `secret:` credential anywhere in a file refuses the file. This browser's own `secret:` kv entries are never exported, never deleted and never overwritten by a restore (any other kv key absent from the backup is deleted). Orphan audio is restored exactly as stored. No autoplay, ever.

**Stages, in order.**
1. *Check* (cancellable): `readBackupZip` validates the whole file with no write of any kind. A refusal says "can't be restored", gives the reason, and says "Nothing was changed."
2. *Preview* (read-only, all file-derived text escaped): file name/size, creation time, generator and format version, song count (with audio / saved web), playlists, audio files and size, orphan audio, queue and history, theme, the library as it is now, the web sites the backup refers to (contacted only when those songs are viewed or played), and a storage-quota warning when `navigator.storage.estimate` says the audio may not fit. Buttons: Cancel (focused) and Continue…
3. *Confirmation* (separate dialog): states that the current library is permanently deleted, with the exact counts that will be deleted and restored; a checkbox must be ticked before "Replace library" is enabled (an empty library needs no tick); Cancel is focused; an optional "Back up current library first" runs the normal backup and returns to this dialog (it is the single intended exception to the rule that a backup is refused while a restore is open).
4. *Write* (not cancellable, all-or-nothing): audio paused, `settleSession()` flushes pending saves, then synchronously `DB.lock = true; S.restoring = true` and queued session/history saves are cancelled; the current library is fingerprinted (keys, record digests, audio key/size/MIME); then ONE read-write transaction over `tracks`, `playlists`, `blobs`, `kv` clears the first three stores, puts every record and audio Blob with its exact key, deletes non-`secret:` kv keys absent from the backup, and **verifies inside the same transaction** (records compared as JSON, each audio key/size/MIME compared, kv values compared). Any throw, request error, abort or verification mismatch aborts the transaction, which rolls every store back. Success is reported only after the transaction completes with `verified === true`.
5. *Theme* (a separate step, NOT part of the atomic commit): `localStorage` `ps-theme` is written only after the database commit and read back; the result dialog says whether it was saved. A backup without a theme leaves the current theme untouched. A crash between the commit and this write would leave the old theme; that window is real and is not hidden.
6. *Rebuild*: in-memory state is reset, audio elements are stopped, the library is re-read from the database, the saved queue is restored **paused**, the old sleep timer is cleared (and any fade-out already running is abandoned by an epoch check), and the **Library** screen is shown. Writes are unlocked before any message dialog is shown.

**Guards.** While `DB.lock` is set every non-read database call is rejected (stale-write protection). Importing songs is refused while a restore is open. A backup is refused during any restore stage ("A restore is in progress…", and "A restore is writing…" inside the locked window) except the confirmation dialog's own backup-first. A restore is refused while a backup or import is running or while another restore is open. If browser storage is unavailable (library held in memory only) the restore refuses with "isn't available in this browser mode".

**Failure messages (truthful, no guessing).** "The restore failed and was rolled back" (and states whether a re-check afterwards found every store identical to before); "Restore stopped before changing anything" (the pre-flush or fingerprint failed); "Restored, but the screen needs a reload" (committed, rebuild failed); "Restore failed" for anything unexpected (reload and check). 

**Limits (do not rely on more).** Other open Plainsong tabs cannot be detected; the dialog asks the user to close them. A real quota failure was only simulated by injected errors. A backup file that is modified or removed on disk between validation and the write was **not tested** (the audio is read lazily from the user's file; an unreadable slice should abort the transaction, but that is unverified). Only desktop Chromium was tested. Round trips are covered in the next section.

## Landing screen and network (found by Phase 2C, fixed)

After a restore the p2b build showed the **Home** screen. Home fetches public "discover" lists (Audius and Internet Archive trending) and Google Fonts whenever it renders, exactly as on any page load, so a restore ended with network requests to those hosts (the claim "no network request by the restore itself" was true of the restore code but not of the screen it ended on). 2C measured this with a blocked-and-counted network, and the app now lands on the **Library** screen (`rsRebuild`: `S.view = { name: 'library' }`), which shows the restored songs and makes no request of its own. One request can still occur: a restored song's own cover address, if it is an http(s) cover URL (and a web song's address only when it is played). The original p2b restore suite pins "home view", so it fails exactly that one assertion against p2c (see the ledger matrix).

## Round trips (Phase 2C, measured)

**Method.** Everything goes through the real UI: Back up button, download, Restore button, file chooser, preview, separate confirmation, verified replace, then Back up again. Each export is judged by an independent oracle (`tests/oracle_2c.py`: Python `zipfile`, `zlib`, `json`, `hashlib` only, no app code) and by raw IndexedDB snapshots taken by the harness with its own connection (SHA-256 of every audio blob). Scenarios: a chain E1 to E2 to E3 to E4 (populated source, a different populated library, a clean browser, a second populated target, plus a restore into the browser that made the backup), full to clean, light to dark theme target, absent theme, four minimal libraries (local only, web only, playlist only, orphan audio), and both p1 fixture archives. The oracle is itself tested by 42 deliberately damaged or altered archives that it must reject (or accept only with the exact stated allowance), and the harness is tested for stale reports, a killed oracle, a timed-out oracle and unsafe delete targets.

**Measured result.** Every comparison had **0 failures**. A re-export is byte-identical to the backup that was restored in: every ZIP entry name and order, `tracks.json`, `playlists.json`, every audio entry (key, MIME, size, SHA-256, compared in order), every `kv` value including `session` (queue, order, volume, speed, EQ, current song, **time**), `localstorage.json` when a theme is present, and the manifest apart from the entries below. The chain reaches a fixed point (E2, E3 and E4 have identical audio, tracks and playlists bytes). `session.time` was exact in every real round trip.

**The only differences the oracle accepts (everything else is a FAIL):**

| Difference | Rule | Why it is legitimate |
|------------|------|----------------------|
| `manifest.createdAt` | later than the first backup's | it is the time of the new export |
| `manifest.excluded.kv` | names equal exactly the `secret:` keys the exporting browser holds (read by the harness from its own database); names only | credentials are never exported; the list describes the browser that exports |
| `kv[session].time` | drift of at most 0.25 s, or exactly 0 only when the harness proved the current song cannot report a position (`--time-unavailable`) | the playhead moves; a large jump, a rewind, a negative or non-number value fails. Never needed in the scenarios |
| theme | only if the backup had **no** `ps-theme` and the restoring browser had one: `localstorage.json` gains exactly that theme | a backup without a theme leaves this browser's theme alone; derived: `counts.localStorage`, `files[data/localstorage.json].bytes/crc32`, `payloadBytes` (each allowed only together with that change) |
| `manifest.warnings` | removal of exactly the warning "ps-theme had an unrecognized value and was not exported" | an old browser held a bad theme value that the new browser does not have; the orphan-audio warning may never disappear |

A `secret:` key (any letter case) in either file, a missing or extra ZIP entry, a manifest with duplicate, reordered, missing or extra entries or wrong counts or byte totals, a changed MIME type, one flipped audio bit, reordered tracks, playlists or keys, and a changed `complete` flag are all failures (each has a control). Derived byte or CRC differences are accepted only when the change that causes them is itself allowed.

Raw proof: `tests/evidence-p2c/` (the exports E1 to E4, every oracle `truth` and `compare` JSON, the run logs).

## Track metadata fields (Phase 3A)

The song info editor (title, artist, album, genre) changes **only Plainsong's own record of a song**. It never rewrites the imported audio file or the tags inside it, never changes the audio blob, and never touches a song's `id`, `key`, `url`, `liked`, `plays`, `last`, `added`, `duration`, `size`, `cover`, lyrics, the queue, history or playlists. There is no database schema change (IndexedDB stays version 1) and no change to the ZIP format or `formatVersion`: the two fields below are ordinary, optional members of a track record in `data/tracks.json`, exactly like the other optional members, and older backups simply do not have them.

| Field | Meaning |
|-------|---------|
| `title`, `artist`, `album` (existing) | the **effective** values every list, search, sort, queue, now-playing bar and media session shows. An edit changes these in place. An empty artist or album is stored as `Unknown artist` / `Unknown album`, as import does |
| `genre` (new, optional text, at most 80 characters) | effective genre. **Absent** when empty (clearing the genre removes the key). Library search matches it |
| `origMeta` (new, optional) | a one-time snapshot of `{title, artist, album, genre}` (all four present, all text, `genre` is `""` if the song had none) taken **at the first save**, from the values as they were just before it. It is never rewritten afterwards. "Revert to originals" copies it back into the effective fields; the snapshot stays. A song counts as edited when any effective field differs from it |

Limits on what the editor stores: title, artist and album at most 200 characters, genre at most 80; control characters, line/paragraph separators, zero-width and bidirectional-override characters become spaces, runs of spaces collapse, the ends are trimmed, lone surrogates become U+FFFD. A value that is still too long is refused (never silently cut) and an empty title is refused. Saving with no net change writes nothing.

Persistence: one `put` of the song's record to the `tracks` store (the same in-memory object that likes and play counts use), after which the screens are refreshed without touching the audio element. If the write fails the exact previous record is restored in memory and the dialog stays open with the message "Nothing was changed". Saving is refused while a backup or restore is running, when the library was replaced since the editor opened, or when the song's values changed elsewhere since it opened.

**Strict reader (Phase 3A tightening, old files unaffected).** If present, `genre` must be text, and `origMeta` must be an object whose keys are exactly `title`, `artist`, `album`, `genre`, all text. Anything else ("genre must be text", "origMeta must be an object", "origMeta.genre must be text", "origMeta.rating is not a known field", ...) is reported under "Some songs have invalid fields" and the file is refused before any preview. Every other unknown field on a record is still kept and written back unchanged (an extra field on a record that has `origMeta` is kept too).

**Round trip (measured in Phase 3A).** A library edited through the real UI was backed up, the file was read by the independent oracle (the oracle's reading of `genre` and `origMeta` equals the live database record for record, in key order), restored into a clean browser and into a populated browser (live database equals the file: tracks, audio SHA-256, order, playlists, kv), and re-exported: the oracle compare showed 0 failures and only the allowed differences of the 2C table. After a restore the editor still shows the originals and "Revert to originals" works, and a re-export after that revert differs only in that one song. Both p1 archives (written before these fields existed) still restore unchanged, and their songs can be edited afterwards. Eight deliberately malformed `genre`/`origMeta` archives (built by an independent helper with correct CRCs and manifest) are refused with zero change to the target; two valid variants are accepted.

An older Plainsong (p2 or earlier) that reads a p3a backup keeps `genre` and `origMeta` untouched in the record (unknown fields are preserved) and shows the effective values; it has no editor for them.


## Track cover fields (Phase 3B)

The cover editor (library songs only: "Edit cover…" in the ⋯ menu) changes **only Plainsong's own record of a song**. A song's cover is one text field of its track record; there are no separate image blobs, no IndexedDB schema change (version 1) and no ZIP-format change. The audio blob, the file's own tags, `id`, `key`, `url`, `liked`, `plays`, `last`, `added`, `duration`, `size`, title/artist/album/genre, lyrics, the queue, history and playlists are never touched.

| Field | Meaning |
|-------|---------|
| `cover` (existing) | the **effective** cover every list, album/artist/playlist head, now-playing bar and media session shows. Either `""` (none), an embedded image `data:image/(png|jpeg|gif|webp);base64,…`, or an `http(s)` address (web songs). An edit replaces it in place |
| `origCover` (new, optional text) | the song's cover **as it was just before its first cover edit**, captured once at the first save and never rewritten. `""` if the song had none. It may be any value `cover` could hold (an embedded png/jpeg/gif/webp image of ANY size, or an http(s) address). "Revert to original" puts it back into `cover` (Save commits; Cancel discards); the field stays. A song counts as edited when `origCover` is present and `cover` differs from it |

What the editor stores as a NEW cover: always an embedded `data:image/png` (when the picture has transparency) or `data:image/jpeg`, at most 512 px on the long side and at most 700,000 characters. The uploaded file is validated **by its bytes**, never by its name or the browser's `File.type`: at most 8 MiB; PNG (chunk walk to an IEND that ends the file exactly), JPEG (markers, a start-of-frame, ending with EOI), GIF (trailer byte) or WebP (RIFF size = file size - 8, VP8/VP8L/VP8X) signatures only; header dimensions 16 to 8192 per side and at most 40 megapixels (checked BEFORE decoding); the browser must decode it and report the same size; it is then redrawn on a canvas and re-encoded. SVG, HTML, text, audio and every other type are refused. Animated GIF/WebP keep their first frame. The original upload bytes are not kept; an http(s) original is kept only as its address and is not loaded by the editor.

**The 700,000-character limit applies to NEW covers only.** Reverting to the stored `origCover` is always allowed whatever its size or type (a legacy GIF, WebP or an original larger than 700,000 characters is restored exactly), and the strict reader applies no size cap to `origCover` or `cover` (it never did for `cover`), so no existing snapshot becomes unreadable.

Persistence and write coordination: all writes of one track record (likes, play counter, duration, lyrics, the info editor, the cover editor, removal) run one after another per song, and each queued writer takes its snapshot when it RUNS. The cover editor (like the 3A info editor) does not touch the shared in-memory record before its write is durable: it puts a clone carrying only its own fields (`origCover` appended on the first save, then `cover`), and only after the write succeeds applies those same fields to the shared record. A failed write therefore leaves nothing to undo and cannot leak into any other writer's snapshot; a newer like or play count is never overwritten by an older copy. While a Save is in flight the editor shows "Saving…" and Save, Revert, Cancel and Choose image are disabled and Escape is ignored; after a failure the error is shown and everything works again. Saving is refused while a backup or restore is running, when the library was replaced since the editor opened, or when the song's cover changed elsewhere since it opened.

**Strict reader (Phase 3B tightening, old files unaffected).** If present, `origCover` must be `""`, an embedded png/jpeg/gif/webp data URL (the same pattern the reader already applies to `cover`) or an http(s) address. Anything else (a number, `null`, a list, an object, `true`, an SVG data URL, `javascript:`, `ftp:`, bad base64 characters, HTML text, ...) is reported under "Some songs have invalid fields" and the file is refused before any preview. Every other unknown field is still kept unchanged.

**Round trip (measured in Phase 3B).** A library whose songs had covers edited through the real UI (including repeated edits and an http original) was backed up; the file was read by the independent oracle (equal to the live database record for record) and by the independent stdlib reader `tests/cover_check_3b.py` (kind, declared MIME = magic-byte MIME, canonical base64, size, SHA-256 of the decoded bytes, width x height from the headers: equal to the live database; plus a CONTAINER-FRAMING check, `container_ok`: PNG chunk CRCs and IEND last, JPEG SOF and EOI, GIF trailer, WebP RIFF size. That check is **not a decoder**; real decodability is shown separately, by the browser itself decoding every embedded cover and origCover of the live library and matching the sizes the Python reader read from the file's headers). The file was restored into a clean and into a populated browser and re-exported (oracle compare 0 failures, only the allowed 2C differences), and Revert still works after a restore. Both p1 archives (no `origCover`) still restore unchanged and their songs get covers. 19 `origCover` archives built by an independent helper (`tests/make_cover_archives.py`, correct CRCs and manifest): 8 valid ones (unchanged data, `""`, png, GIF, WebP, a real PNG data URL over 700,000 characters, an http address, an unknown extra field) are accepted and carried as the exact string; 11 malformed ones are refused with zero change to the target.

An older Plainsong (p3a or earlier) that reads a p3b backup keeps `origCover` untouched in the record (unknown fields are preserved) and shows the effective `cover`; it has no editor for it.
