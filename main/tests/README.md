# Plainsong test harness

Dev-only files; the app itself has no build step and no dependencies. Needs Node, Playwright (npm), Google Chrome and Python 3 (plus `unzip`, optional).

```
python3 -I tests/make-fixtures.py <fixtures-dir>              # three 12 s WAV tones
python3 -I -m http.server 8765 --directory <project-dir> &    # serve index.html + style.css
node tests/phase0.test.js <fixtures-dir> <phase0-results.json>              # 38 baseline checks (speed, A-B, queue, persistence, mobile)
node tests/phase1.test.js <fixtures-dir> <work-dir> <phase1-results.json>   # backup export: 50 browser checks + 175 verifier checks
python3 -I tests/negative_controls.py <good.zip> <good.expected.json> <work-dir>   # verifier must reject 10 damaged archives
python3 -I tests/verify_backup.py <backup.zip> <expected.json> [--incomplete] [--ignore-kv a,b]
```

- `verify_backup.py` shares no code with the app (Python `zipfile`, `zlib`, `hashlib`, and `unzip -t`).
- Browser tests block all non-localhost network, so offline behaviour is exercised and no real service is contacted.
- Expected state for the verifier is captured straight from IndexedDB by the harness, not by the app's backup code.
- `fixtures/` holds two archives produced by the p1 build (a full six-track library with binary data, playlists, session and history, and a one-song minimal one), with the expected-state JSON for the full one. Phase 2 can use them as restore round-trip inputs.
