# Plainsong — Patch Notes

## Phase 1 — Full library backup export
- Added “Back up library” actions in the sidebar and mobile top bar, with progress feedback and cancellation.
- Exports a versioned ZIP containing library records, playlists, saved session/history, allow-listed theme preference, and original binary audio data; credentials are excluded.
- Adds archive integrity checks and clear handling for missing audio, size/entry limits, and explicitly marked incomplete exports.
- Export only: restoring a backup is not included in this phase.

## Phase 0 — Baseline
- Local music library and playback
- Playback queue
- Web sources
- Equalizer
- Playback-speed controls
- A–B loop
