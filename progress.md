# Plainsong — Patch Notes

## Phase 2 — Library backup restore
- Restore a version 1 library backup from a local ZIP, with a preview and clear replace confirmation.
- Validate backup contents before changing the library; restore supported tracks, audio, playlists, listening session and theme settings.
- Keep the restore local and safe: reject incomplete or invalid backups, protect saved credentials, and land in the Library after restoring.

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
