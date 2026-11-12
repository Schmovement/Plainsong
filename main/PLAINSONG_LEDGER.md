# Plainsong phase ledger

Updated: Wed 2026-11-04 10:05 (UTC+07:00), end of Phase 0
Baseline label: **p0-baseline** (source = attached files from the ORIGINAL chat's speed + A-B message)
Next checkpoint label: p1 (after Phase 1). Labels: p0-baseline, p1, p2 ... p18.
Checkpoint archive: `plainsong-checkpoint-p0-baseline.zip` (contains this ledger, both sources, hashes, tests)

## Phase table

| # | Phase | Status |
|---|-------|--------|
| 0 | Baseline audit / recovery / ledger | **DONE** |
| 1 | Versioned full backup export incl. binary data | **NEXT** (starts on "Continue") |
| 2 | Safe restore: validate, preview, round-trip tests | Queued |
| 3 | Metadata and custom-cover editing | Queued |
| 4 | Five-star ratings, sort/filter, keep likes | Queued |
| 5 | Dynamic smart playlists and rule UI | Queued |
| 6 | Custom accent / LED colors and reset | Queued |
| 7 | Extra visualizers and selector | Queued |
| 8 | Mini-player / PiP with capability fallback | Queued |
| 9 | Local lyrics and LRC sync editor | Queued |
| 10 | Dual-deck / transition groundwork | Queued, now judged REQUIRED (see plan notes) |
| 11 | Crossfade and best-supported gapless | Queued |
| 12 | Local loudness analysis / normalization | Queued |
| 13 | A-B trim and EQ-applied export | Queued |
| 14 | Reverb / spatial presets, optional vinyl texture | Queued |
| 15 | ListenBrainz scrobbling | Queued |
| 16 | Last.fm scrobbling | Queued |
| 17 | Infinite radio | Queued |
| 18 | Final integration / regression / README | Queued |

Blocked: none.

## Source identification

| File | Bytes | Lines | SHA-256 |
|------|-------|-------|---------|
| index.html | 99,826 | 1,376 | ba12c54dadadfe0c80c14493ba3f812d78b2d2ad1cbf3d2b212ba01b4b4e8b68 |
| style.css | 25,333 | 1,661 | d5685d2aea568729befe4a03a88eafd27cc9e04966e409bc692188bafccb8322 |

Sizes match what Russell reported. Both files are used unmodified in this checkpoint. App is one inline `<script>` in index.html plus style.css; no build step, no dependencies. Only external resources: Google Fonts (cosmetic, falls back to system fonts) and the Audius / Internet Archive / LRCLIB APIs. No license file (none selected). No service worker or manifest.

I verified the features below are present and working in these files. I cannot independently prove they are byte-identical to the original chat's cards; I'm relying on Russell's report of how they were recovered.

## Storage architecture (IndexedDB `plainsong`, version 1)

| Store | Key | Contents |
|-------|-----|----------|
| `tracks` | keyPath `id` | One record per library track (local files AND saved web tracks) |
| `playlists` | keyPath `id` | `{id, name, ids[], created}` |
| `blobs` | out-of-line key = track id | Audio `Blob` for local tracks only |
| `kv` | out-of-line string keys | `session` (queue, orig, qi, time, shuffle, repeat, vol, muted, rate, pitch, eq, eqPreset, np, npTab, webs[]), `hist` (play history, max 300, web entries carry a `snap`) |

- **There are FOUR stores, not three.** The audio lives in `blobs`, separate from `tracks`. A full backup must cover `blobs` as well as kv/playlists/tracks.
- Local track record fields: `id, kind:'local', key, title, artist, album, track, duration, cover, lyrics, size, added, plays, liked`. Fetched lyrics add `lrc, lyrics, lyricsFrom:'lrclib'`, or `noLyrics` (timestamp). `last` is set on play.
- Web tracks saved to the library are `kind:'web'` records with `url`, `src` ('audius'|'archive'), `srcId`, `link`, and **no blob**.
- `cover` is a downscaled (max 480 px) JPEG **data URL stored inside the track record**, not a blob. Web covers are remote URLs.
- Import de-dupe key is `name|size|lastModified`.
- localStorage holds only `ps-theme` (written when the theme button is used). Everything else is IndexedDB.
- No migration framework. `onupgradeneeded` only creates the four stores. Additive record fields and new kv keys need no version bump; a new store or index would require bumping to v2.
- If IndexedDB is unavailable the app runs in-memory (`S.mem` holds blobs) and nothing persists. Backup must handle that mode.
- Tag reading: ID3v2.2/2.3/2.4 (title, artist, album, track, APIC cover, USLT lyrics) and ID3v1 only. m4a/flac/ogg/opus files have no tag parsing and fall back to filename parsing.

## Audio architecture

- Two `<audio>` elements. **`aL` = local files, `aW` = web streams.** `A` points at the active one. Only one is active at a time; `load()` pauses and clears the other.
- **Only `aL` is in the Web Audio graph:** `MediaElementSource(aL) → 10 BiquadFilters (EQ) → AnalyserNode → GainNode → destination`. Created lazily on first local play (`ensureGraph`). `aL.volume` is pinned to 1 and the GainNode carries volume (`vol^1.6`).
- **`aW` streams bypass Web Audio completely:** no EQ, no meter, volume via `element.volume`. The Sound tab already says so.
- Local-to-local track changes reuse the same `aL` element: new blob URL, new `src`. This is a hard cut with an audible gap (no preload of the next track, no overlap).
- `applyRate()` sets `defaultPlaybackRate`, `playbackRate` and `preservesPitch` (plus moz/webkit variants) on both elements.
- Play counter: counts once per load when `currentTime > min(10 s, 50% of duration)`. This is NOT a Last.fm / ListenBrainz eligibility rule; those get checked against provider docs in Phases 15-16.
- Meter: 28-bar LED canvas, runs only while the now-playing panel is open.

## Feature baseline (what exists today)

Library/playback: local import (files + folder + drag-drop), albums/artists/playlists/liked/history, queue with drag-reorder, shuffle, repeat off/all/one, sleep timer, Media Session, lyrics from tags + LRCLIB synced lyrics, Audius + Internet Archive browse/search/stream, 10-band EQ with 5 presets, LED meter, light/dark theme (the only "themes" today), keyboard shortcuts (Space, arrows, M, L, S, R, A, [ ], \, Q, /, ?).
Speed: 0.25x-3x in 0.05 steps, presets, pitch-preservation toggle, popover + Sound tab, `[` `]` `\`, persisted.
A-B: `A` key cycle, Set A/B buttons, 0.1 s nudges, seek-bar bracket + band, clears on song change, not persisted (by design).

## Test evidence

Method labels: **SYNTAX** = parsed only. **AUTO** = automated headless Chrome (Playwright, real index.html over http://localhost, external network blocked so offline fallbacks were exercised). **UNVERIFIED** = not tested.

| Check | Class | Result |
|-------|-------|--------|
| Inline JS parses (`node --check`) | SYNTAX | pass |
| No duplicate ids; every `$('#id')` target exists in HTML or is created by JS; CSS braces balanced; all speed/A-B CSS classes present | SYNTAX | pass |
| Boot with no JS errors; DB v1 with 4 stores | AUTO | pass |
| Import 3 WAVs: titles/artists, durations, 3 records + 3 blobs, re-import de-duped | AUTO | pass |
| Local playback, 10-band graph created, context running | AUTO | pass |
| Speed: slider, chips, 2x on both elements, pitch toggle, `[ ] \`, clamp 0.25-3, popover open/close | AUTO | pass |
| A-B: set A/B by key, bracket shown, loop held 7 s at 2x (max overshoot 0.03 s), 0.1 s nudges, invalid B rejected, clear, clears on song change | AUTO | pass |
| Queue: next/prev, auto-advance, repeat off/all/one at queue end | AUTO | pass |
| EQ preset sets biquad gains; play counter + like persist | AUTO | pass |
| Reload restores speed/pitch/volume/queue/EQ/likes | AUTO | pass |
| ID3v2.3 title/artist/album/track parse (synthetic tag) | AUTO | pass |
| Offline: Audius shelf shows "Couldn't reach", app stays usable | AUTO | pass |
| Mobile 390x844: no horizontal overflow, nav + bar on screen, speed popover in viewport | AUTO | pass |

38 of 38 pass. Repeat with: `python3 -I tests/make-fixtures.py <dir>`, serve the project folder on port 8765, then `node tests/phase0.test.js <fixtures-dir> <results.json>` (needs Playwright + Chrome).

**Not verified (do not treat as tested):**
- Actual audible output, and whether pitch preservation sounds right (only the `preservesPitch` property and `playbackRate` were checked).
- Any remote stream playback, CORS behaviour, or the live Audius / Archive / LRCLIB responses (network was blocked).
- Real MP3/FLAC/M4A/Ogg decoding (fixtures were WAV tones); ID3v2.2/2.4, embedded cover art, USLT lyrics.
- Firefox, Safari, real touch devices; only desktop Chromium plus one emulated phone viewport.
- A-B overshoot at 3x; IndexedDB quota-full and in-memory fallback paths.
- Sleep-timer fade: it sets `el.volume` and the GainNode to the same value on `aL`, which may attenuate twice. Not measured; low severity, left unchanged.

## Plan notes (baseline evidence vs the proposed segments)

1. **Phase 10 is now required, not optional.** There is a single local element, and local track changes hard-cut. Crossfade/gapless needs a second local deck feeding the same EQ chain.
2. **Streams are outside the audio graph.** EQ, visualizers, loudness analysis, reverb, A-B export and the PiP visualizer will work for local files only. Stream support would need CORS-enabled audio and is unverified; crossfading a stream can only use `element.volume`. Each phase will say so in the UI.
3. **Backup scope** = IndexedDB `tracks`, `playlists`, `blobs`, `kv` + localStorage `ps-*` keys. No secrets exist today; none will be added by default.
4. **Prefer additive fields and new kv keys; avoid a DB version bump** unless a phase truly needs a new store.
5. **Metadata editing (Phase 3):** the only stored copy of original tags is the track record itself, so overrides need a separate `orig` snapshot or override object to keep "database edit" distinct from the untouched audio file. To be designed in Phase 3.
6. **Accent colors (Phase 6):** `--sel` is a hard-coded rgba of the default amber and `--accent-text` / `--on-accent` are separate variables; LED colors are read once by `readLeds()` on theme change. All three need handling.

## Decisions needed from Russell

None blocking. Phase 1 will use a single versioned JSON file with audio blobs embedded as base64 unless there's a reason to prefer ZIP; I'll state the size limits and confirm in that phase's report.

## Recovery

If the workspace resets: re-attach `plainsong-checkpoint-p0-baseline.zip` (or the latest `pN` zip) and say "restore from checkpoint". Verify files against `SHA256SUMS.txt` before any work.

## Exact next action

On Russell's "Continue": build Phase 1 only (versioned full backup export covering all four stores, local blobs, custom artwork, lyrics, ratings fields when they exist, localStorage `ps-*` prefs, no integration secrets), test it in the browser harness, and deliver `index.html` / `style.css` changes plus a `p1` checkpoint zip. No other phase starts.
