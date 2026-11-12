# Plainsong progress log

Updated: 2026-11-12 (UTC+07:00)

## Version and push history

The dates and subjects below are taken from Git history. Every listed commit is reachable from the repository's remote `main` at the review starting point (`cccaee6745488939d99aceb3e0ca59c689b8b3b6`). Git does not record push timestamps, so these are commit timestamps, not claimed push times.

| Git commit timestamp (UTC+07:00) | Commit | Subject | Remote status at review start |
|---|---|---|---|
| 2026-10-03 08:44:07 | `dc259d0cadaa014ecc01993faa4a3e4ed45ad376` | A local music player that can browse online music (limited tho) | Present on remote `main` |
| 2026-10-03 08:56:31 | `71023e4a5fe3b3106a0f60e324f73bdada31c7b3` | Cleaned a few lines... | Present on remote `main` |
| 2026-11-09 18:08:19 | `d93319b0b9c9d3ccb359aceb5121cd64cd3d72ee` | README.md file | Present on remote `main` |
| 2026-11-09 18:12:17 | `a2783ced0512994a0c4d38e93f67a7dda2bb30d1` | Feature update | Present on remote `main` (baseline repository commit) |
| 2026-11-12 09:08:09 | `cccaee6745488939d99aceb3e0ca59c689b8b3b6` | Move existing site files into main directory | Present on remote `main` (layout-move commit; review starting point) |

## P0 — prepared, pending owner approval

- Starting commit: `cccaee6745488939d99aceb3e0ca59c689b8b3b6`.
- The supplied `plainsong-checkpoint-p0-baseline.zip` was copied into `main/` in full (10 files, including the ledger, checksum manifest, tests, inventory, and archived test screenshots). Its SHA-256 is `30cc98eb4a899f4467c7f3e1bd8098a003dc977adf492456c76a023ba5a3bb9b`.
- The three files formerly in `main/`—`README.md`, `index.html`, and `style.css`—were moved to `backup/` unchanged. `backup/.gitkeep` remains.
- Added this root `progress.md` to track prior versions and this prepared P0 update.
- Status: **prepared for review; pending owner approval**. Not staged, committed, or pushed.

### Validation

- All six entries in the archive's `SHA256SUMS.txt` passed `sha256sum -c`; the unlisted archive files were also retained in `main/`.
- `main/index.html` and `main/style.css` are byte-identical to the archive copies.
- The inline JavaScript passed `node --check`; CSS braces are balanced (252 open / 252 close).
- `backup/README.md`, `backup/index.html`, and `backup/style.css` are byte-identical to the files at the starting commit.
- The documented Chromium Phase 0 suite passed **38/38** checks. Generated fixtures, Playwright test dependency, run results, and run screenshots are outside the repository in the review workspace.
- Runtime DOM inspection found no duplicate IDs at startup or with the Sound/A–B panel open; the A/B control IDs are created when that panel is rendered.
