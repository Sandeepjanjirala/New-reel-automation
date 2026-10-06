# Pixabay update verification

Date: 6 October 2026. Base: ShortsGenius_Repaired. Update: 1.1.0-pixabay-additive.

## Recorded results

| Check | Result | Scope |
|---|---|---|
| Application pytest suite | 67 passed | Original 30 tests unchanged, plus 37 new tests |
| Updater pytest suite | 12 passed | Standard-library installer/restore logic |
| Inline frontend JavaScript | node --check passed | Syntax only |
| Offline Chromium DOM checks | 5 grouped checks passed; no uncaught JavaScript errors | Simulated fetch responses; no live services |
| Core-file/media preservation | All listed hashes match base | See preserved_files.json |

The full application suite completed in 29.05 seconds in this environment. Time is not a Windows performance guarantee.

## Application checks

The added tests cover video API parameters, portrait/rendition preference, reuse signalling, 24-hour cached responses and expiration, credential-specific cache identity, missing/invalid key errors, JSON failures, rate-limit cooldown, safe errors that do not expose keys, blocked download hosts/redirects, corrupt/oversized media, upload precedence, automatic provider order, explicit provider failures, key settings and retention of partial source reports.

A real three-scene FFmpeg test combines an uploaded clip, a Pixabay-adapter clip supplied through mocked HTTP, and the uploaded clip again. It retains the Telugu voice selection and Roman subtitle content, mixes a real diagnostic music/audio input, validates the 1080x1920 / 30 fps output and fully decodes it. Narration audio is generated locally for the test; it is not a live Edge-TTS result. Pixabay media bytes are a test fixture, not a claim of a successful live download.

Settings tests verify that saving a new key preserves Windows FFmpeg paths, other API keys, BOM/newline handling and unrelated configuration. Tests reject multiline/injected key values and confirm that Test Key does not save an unsaved key.

## Installer checks

Backups, no change to .env/media/core, idempotent install, local-source conflicts, BOM/CRLF-only changes, write-failure rollback, restoration, refusal to erase newer source edits, damaged payload rejection, protected-path rejection, missing base files, new-file collisions and running-server detection are exercised across 12 tests.

The bundle also includes a post-build verification report for installation/reinstallation/restoration using its actual payload on a disposable copy of the base. This is separate from native Windows batch execution.

## Browser scope

Chromium loaded the HTML with page.set_content and simulated API replies. It checked Pixabay test/save/status, reuse of an upload across eight scenes, a mixed upload/Pixabay selection, editable keywords, all-scenes provider selection, existing Telugu voice and Roman caption controls, literal rendering of untrusted creator text and rejection of unsafe source links.

A real browser navigation to a test server was blocked by this environment's browser policy. No network-policy bypass was attempted. API behavior was tested with FastAPI's test client separately; full live browser-to-server operation remains to be checked on the target machine.

## Unverified

Live Pixabay/Pexels/Gemini/Edge-TTS connectivity, account entitlement/quota, actual network speech timing, Windows launcher execution, target Python 3.14 runtime compatibility beyond the preserved dependency configuration, native Telugu font glyphs, performance under long clips, and multi-user production behavior are not validated by these results.

## Reproduce

From the application folder, using its installed development dependencies:

```text
python -m pytest -q
```

From the extracted update folder, with pytest installed:

```text
python -m pytest -q test_update_installer.py
```

Tests are not required for applying the update. Installation adds no dependencies. Run the normal doctor tool for your local FFmpeg setup and the UI Test Key control for a real account check. Do not send API keys in diagnostic screenshots.

## Evidence files

- application_pytest.txt: complete summary output for the 67 application tests.
- installer_pytest.txt: complete summary output for the 12 updater tests.
- offline_browser_results.json: grouped Chromium DOM results and JavaScript error count.
- preserved_files.json: SHA-256 verification of unchanged core/source/media files.
- PIXABAY_CHANGES.patch: text diff against the reviewed repaired base (not a separate installer).
