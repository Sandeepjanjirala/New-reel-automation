# ShortsGenius - repaired local prototype

This is a focused repair of the project you supplied, not a new text-to-video model or a production hosting service. The original scene editor, upload workflow, narration controls, subtitle themes, music selection and reel export are retained.

The main rule is now: **no valid visual for a scene means no completed reel**. Missing footage and failed media commands must be visible errors, not silently substituted backgrounds or false success messages.

Read `PROJECT_AUDIT.md` for the original failure locations, reproduced bugs, implementation changes and next-stage architecture. Original source line references refer to your uploaded archive, not these edited files.

## 1. Start in a NEW folder

Keep your original project as a backup. Extract this package into a separate directory. Do not copy the old `venv`, `.git`, `.env` or old render outputs into it.

The original archive contained a populated Gemini credential field. Rotate/revoke that credential as a precaution before using a replacement. This package contains only a blank `.env.example`; it does not contain your secret.

## 2. Prerequisites

Use Python 3.10 or newer and a system FFmpeg installation containing BOTH `ffmpeg` and `ffprobe`. The FFmpeg build must include `libx264`, AAC and the `ass` subtitle filter. The supplied renderer no longer relies on MoviePy or an FFmpeg binary bundled in the archived virtual environment.

Official FFmpeg download information: https://ffmpeg.org/download.html

On Windows, put the directory containing `ffmpeg.exe` and `ffprobe.exe` on PATH, or set their full paths in your new `.env`. Example:

```dotenv
FFMPEG_EXE=C:/ffmpeg/bin/ffmpeg.exe
FFPROBE_EXE=C:/ffmpeg/bin/ffprobe.exe
```

Check in PowerShell:

```powershell
ffmpeg -version
ffprobe -version
```

## 3. Install and start - Windows PowerShell

Run these commands inside the extracted `ShortsGenius_Repaired` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe tools\doctor.py
.\.venv\Scripts\python.exe run_server.py
```

Open `http://127.0.0.1:8080` in your browser. Using the virtual environment's Python directly avoids PowerShell activation-policy problems. Do not run `Copy-Item` over an existing configured `.env` later.

For Linux/macOS, use `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, `cp .env.example .env`, then `.venv/bin/python run_server.py`. Install a system FFmpeg build first.

## 4. Prove that the video layer works WITHOUT any API

Run the offline rendering diagnostic before testing online narration or automatic footage:

```powershell
.\.venv\Scripts\python.exe tools\smoke_test.py --clip "C:\Videos\my_clip.mp4"
```

The result is a three-second 1080x1920, 30 fps MP4 containing the supplied clip, diagnostic captions and a silent audio stream. The command prints its exact output path. Silence is intentional: this check does not contact Edge-TTS, Gemini, Pexels or any other external provider.

The two supplied library demos can also verify rendering:

```powershell
.\.venv\Scripts\python.exe tools\smoke_test.py --clip backend\assets\videos\facts_cosmos.mp4
```

These particular MP4s are camera-animated space photographs, not newly generated AI video or live-action footage. The smoke tool accepts an explicitly supplied path and does not apply the automatic provider-selection rules.

## 5. First full reel: use your OWN uploaded video

Generate a storyboard, review/edit the narration, and select an appropriate voice. For an initial UI test, select the shortest offered target duration (25 seconds).

Use **Upload Clip** on a scene. Wait for validation and its video preview. Then either upload a different clip for each scene, or use **Use Clip for All Scenes** to cover the storyboard with the first clip while testing. Preview the narration using the voice preview control, then render.

Uploads support MP4, MOV, WEBM and MKV, up to 250 MB and 10 minutes each. A filename extension alone does not establish a video: the backend verifies streams, duration and sample decoding. An MP4 preview is created even for an MKV source. **Remove Clip** detaches an assignment; it does not delete the saved source file. Selecting another provider also clears the previous manual override.

A clip assigned to several scenes starts at the beginning for each scene. Short clips loop; long clips are trimmed to narration duration. There is no intelligent highlight extraction, trim editor or continuous source-timeline offset yet. The original uploaded clip's audio is not retained in the final reel; generated narration and optional background music are used.

Your normal UI render still needs internet access for Edge-TTS. Gemini is optional for template-based storyboard fallback; a live Gemini key/model is needed for the model-generated script path. No Pexels key is required when every scene uses an upload or matching local footage.

## 6. Visual sources and explicit fallback policy

| Choice | Behavior |
|---|---|
| Uploaded clip | Used for its assigned scene; invalid/missing uploads cause an error. |
| Auto | Tries configured Pexels footage, then a matching local library clip. |
| Matched Local Library | Uses related filename/manifest tags; does not pick a random unrelated clip. |
| Pexels | Requires an existing key and usable results; a selected provider's failure is reported. |
| Included photo-animation demos | Require the explicit `Allow photo-animation demos` checkbox in the UI. |
| AI video | Disabled honestly: no text-to-video provider is connected in this repair. A generated MP4 from elsewhere can still be uploaded. |

There is no automatic fallback from missing footage to a gradient, photograph or fake "AI video". The procedural provider is retained only as an explicitly requested demonstration mode in the backend.

The supplied library contains ONLY `facts_cosmos.mp4` and `facts_nebula.mp4`. Their `manifest.json` labels them as `photo_motion`. Do not expect them to supply technology, fitness, fashion or other general footage. Add suitable clips you are entitled to use under `backend/assets/videos/`, with descriptive filenames and optional manifest tags. A tag match is not a semantic-quality guarantee; review the result.

### Pexels

Pexels currently states that new API key issuance is paused (checked 2026-10-06). Use an existing authorized key, or start with uploads/local footage. Do not assume a new key can be obtained immediately.

The adapter uses `https://api.pexels.com/v1/videos/search`, validates downloaded video and preserves provider/source metadata in a `.source.json` file. HTTP authorization/rate-limit failures are surfaced. This is not a production retry/circuit-breaker system. The UI includes Pexels attribution; preserve applicable source credits when publishing.

Sources: https://www.pexels.com/api/ and https://www.pexels.com/api/documentation/

### Gemini

Set `GEMINI_API_KEY` locally. `GEMINI_MODEL` is configurable; the example uses `gemini-3.5-flash-lite`, an officially documented text-output model. The original hardcoded `gemini-2.5-flash` has access restrictions for new users according to Google's current Gemini API documentation. A supported model is not a guarantee that your particular account has quota or access. Live API calls were not validated in this environment.

Sources: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite and https://ai.google.dev/gemini-api/docs/deprecations

### Native Telugu captions

Romanized subtitles do not require a Telugu font. For native Telugu, install a suitable font locally and set `SUBTITLE_FONT_NATIVE` to its family name. Defaults are `Nirmala UI` on Windows and `Noto Sans Telugu` on other platforms; actual availability depends on your computer and FFmpeg's font discovery. No font files are redistributed in this package.

## 7. Diagnostics and status

`tools/doctor.py` checks local media tools, installed packages and library clips. It prints only whether keys are present, not their contents. Its readiness result does not test external services or prove that a topic has suitable footage.

`POST /api/preflight` verifies the submitted scene assignments before a render job is accepted. Online availability is checked during the job, not assumed from key presence.

Per-job files are stored under `backend/output/jobs/<job_id>/`:

- `status.json`: persisted progress and final state.
- `visual_report.json`: selected sources and provider attempts.
- `ffmpeg.log`: executed commands and media errors.
- `render_manifest.json`: scene durations and successful validation details.
- `sub_*.ass`: captions used for the render.
- `pipeline_error.log`: available after a pipeline exception.

Completed reels are saved as `backend/output/<job_id>_final.mp4` only after output validation. After a restart, completed states can be recovered; interrupted jobs become failed and must be submitted again. This is not resumable distributed processing.

## 8. Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The supplied regression suite has 30 tests. It exercises real FFmpeg/ffprobe processing and FastAPI request handling, including visible moving backgrounds, mixed frame rates, full-range source conversion, MKV uploads, corrupt media, missing footage, scene-count mismatch, rendering failures, final validation and state recovery. Speech and Pexels responses are mocked.

Review `TEST_RESULTS.md` for exactly what was and was not tested. A local test pass is not proof of live API connectivity or browser compatibility on every system.

## 9. Scope and remaining work

This package remains a single-user, loopback-only prototype with one in-process render slot. It does not include authentication, a durable worker queue, billing, scheduled runs, automatic social publishing, a true AI-video integration, speech alignment for uploaded narration, full timeline editing or production security hardening. Do not expose it directly on the public internet.

The project preserves the relevant core application and your supplied media assets. The original virtual environment, Git history, secret `.env`, machine-specific asset-building helper scripts and old ad hoc network tests are intentionally omitted. Rebuild dependencies rather than copying another computer's virtual environment.
