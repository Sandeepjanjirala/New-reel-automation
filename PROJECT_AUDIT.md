# ShortsGenius project audit and repair

**Review date:** 6 October 2026  
**Input:** `shortsgenius - Copy.rar`  
**Deliverable:** repaired local prototype, regression tests, setup guide and diagnostic render.

## Executive finding

The project is not just a subtitle generator. It contains a storyboard editor, speech generation, visual-source router, per-scene uploads, caption generation and FFmpeg compositing. The video-compositing route can render actual input video; that was verified locally using your bundled media.

The central integration failure is that the original application does not make a valid visual source and validated output prerequisites for success. It can replace missing footage with unrelated clips or image/gradient backgrounds, and some FFmpeg failures do not propagate to the job status. Subtitles can therefore work while the visual result is absent, unrelated, static-looking or not exported successfully.

Your archive contains no failed final MP4 or runtime log from the incident you described. Consequently, this review proves several relevant defects and demonstrates repairs, but does not assert which exact defect occurred during your historical run. It also does not claim that every black-frame symptom is caused by the same problem.

Source references below use the ORIGINAL archive's file paths and line numbers. The repaired files have different line numbers. Evidence generated during this review is in `evidence/` and `TEST_RESULTS.md`.

## 1. What was inspected

Application routes/configuration, the single-page frontend, storyboard/voice/visual/subtitle/compositor services, provider selection, supplied asset-building utilities, dependency specifications, the existing test scripts and the supplied media files were inspected. The archived virtual environment and Git objects were inventoried, not executed or exhaustively dependency-audited.

The archive has 5,050 entries and includes a virtual environment and Git history. Only the relevant application and media content is needed to distribute and rebuild the app.

The usable supplied video directory contains exactly two MP4s: `facts_cosmos.mp4` and `facts_nebula.mp4`. Both are approximately six seconds, 1080x1920, H.264, 30 fps, with no audio. Frame inspection and the accompanying asset-building scripts identify them as animated space imagery. They are not a general stock library for the advertised niches.

The configuration contains a populated Gemini credential field and an empty Pexels key. Credential validity was not tested and no secret is printed in this report. The corrected package excludes the original `.env`.

## 2. Actual application flow

```text
Topic/niche/language
    -> Gemini storyboard request OR built-in template fallback
    -> scene narration and visual search terms
    -> Edge-TTS narration
    -> visual router (upload/preference/fallbacks)
    -> ASS captions
    -> FFmpeg scene rendering
    -> concat / optional music
    -> job completed / player URL
```

The original UI already submits scene uploads using FormData and passes their mappings to the backend. The problem is not simply that an upload button is missing. The pipeline needs reliable source selection, consistent media formats, strict error propagation and output verification.

There is also an important product distinction: generating a script, downloading a stock video, animating a photograph and generating new temporal video with a video model are four separate operations. The original labels blur these distinctions.

## 3. Prioritized findings

### P0 - A failed FFmpeg process can be reported as successful

**Locations:** `backend/services/video_compositor.py:105-109, 117-149, 155-167`; `backend/app.py:443-447`.

The scene encoder checks a return code only to print an error, then appends the expected scene path anyway. Concatenation and optional music subprocess results are not checked. The function returns the expected final filename without establishing that it contains a decodable video/audio stream. The route marks the job completed when the function returns.

**Reproduction:** the original compositor was given a nonexistent visual and an existing music track. It returned `invalid_input_final.mp4` with no exception, but the file did not exist. This reproduces false completion for that code path, not an assertion that every failure follows that path.

**Repair:** checked media commands, timeouts, persistent stderr logs, input probing, scene/output validation, full final decode, and atomic publication of the final filename only after validation. The API marks exceptions as FAILED and clears the video URL.

`ffprobe` exposes container and stream information in machine-readable form and reports unrecognized inputs as errors. The repair uses that capability rather than trusting filenames [1].

### P0 - There is no reliable supply of relevant footage

**Locations:** `.env` key presence; `video_providers.py:89-103, 168-190, 456-497`; `visual_engine.py:46-56`.

With an empty Pexels key, the online stock provider is unavailable. The supplied local library has only two space clips. Its original fallback selects a random local MP4 even if it does not match the topic. The router can subsequently fall back through image animation, photos and procedural backgrounds while the UI still describes video generation.

**Reproduction:** a fitness/gym scene selected `facts_cosmos.mp4`. That is a valid video file but an irrelevant visual. It demonstrates why "file exists" is insufficient as a content-quality test.

**Repair:** explicit upload priority; matching local metadata/filenames rather than random selection; photo-motion demos clearly labelled and opt-in; no automatic gradient/photo substitution when footage is missing; provider-attempt reports. An explicit provider selection now fails visibly rather than silently switching to a different content type.

Pexels currently documents `/v1/videos/` as the video endpoint prefix; the older prefix is scheduled for future deprecation, not proven already broken. The adapter was updated. Its API homepage also currently states new key issuance is paused, so an upload-first workflow is important [2][3].

### P1 - The provider named "Generative AI Video" does not generate video with a video model

**Location:** `video_providers.py:193-275`.

The implementation requests an image from Pollinations and runs FFmpeg zoom/pan on that still. Its availability method returns true without establishing service access. On image-request failure it tries curated stock. There is no video-model request, asynchronous video job, polling, model-output retrieval or quota handling.

**Repair:** the misleading AI-video option is disabled and labelled not connected. Already generated MP4s can still be uploaded. Known supplied photo animations remain usable only by explicit choice.

**Next stage, not implemented:** add a genuine provider adapter with request, operation status, timeout/cancellation, output download and normal media validation. Google's Veo documentation illustrates a distinct video-generation API workflow; using a text model for a storyboard does not implement that workflow [4].

### P1 - Scene lists are silently truncated

**Location:** `video_compositor.py:30`.

`zip(scenes, voice_data, visual_paths)` stops at the shortest list. A missing audio or visual entry can remove scenes without raising an exception.

**Reproduction:** two scenes with one audio and one visual produced a valid approximately 1.221-second, one-scene MP4, with no mismatch error.

**Repair:** equal nonzero list counts are required before rendering, along with unique positive scene IDs at request validation. Actual measured narration audio determines scene duration, rounded to an output frame boundary.

### P1 - Upload support is connected but inconsistent and undervalidated

**Locations:** `backend/app.py:135-153`; `video_providers.py:49-78`; `video_compositor.py:52-55`; `frontend/index.html:1140, 1291-1298, 1499-1525`.

The upload endpoint accepts MKV while the original compositor's video suffix list does not. Media validation relies heavily on extensions; uploaded file size, duration and video-stream presence are not adequately checked. Uploaded paths can also be supplied as arbitrary filesystem locations. Changing a scene's source selector does not remove its old custom upload mapping, which always wins at the router.

**Repair:** retain per-scene uploads and add MKV handling through stream inspection, a 250 MB/10-minute input cap, decode checks, safe asset identifiers, MP4 previews, remove/reassign controls, upload-in-progress protection, stable scene targeting, and "Use Clip for All Scenes". Scene IDs are used rather than assuming index+1 everywhere.

The package does not add a timeline trim editor or automatic highlights. Reusing one clip repeats it from the beginning for each scene. This limitation is documented rather than hidden.

### P1 - Inconsistent scene formats before stream-copy concatenation

**Locations:** `video_compositor.py:57-101, 111-127`.

Original uploaded video retains source-dependent timing characteristics; image animation is emitted at 30 fps. The final concat is stream-copy. The inputs are not explicitly normalized to one consistent frame rate, pixel aspect ratio, time base and audio format.

**Repair:** normalize scene outputs to 1080x1920, H.264, limited-range yuv420p, 30 fps, square pixels, common track timescale and 48 kHz stereo AAC. Then concatenate matching scene outputs. Mixed 24/25 fps MP4/MKV inputs are tested.

**Additional issue caught by this repair's real-asset smoke test:** your bundled full-range H.264 clip could retain the `pc`/`yuvj420p` range even when `-pix_fmt yuv420p` was requested. Explicit range conversion and output signalling were added to both scene renders and upload previews. The final bundled-asset smoke test passes. This is not claimed as the proven cause of the original incident.

FFmpeg provides the scale/crop/fps/subtitle/audio filter operations used here [5]. Merely forcing an `.mp4` filename is not a conversion or validation strategy.

### P1 - A procedural filter accidentally requests 650 fps

**Locations:** `video_providers.py:373-398`; also the original `backend/generate_broll_clips.py` helper.

The gradient filter specifies both `rate=30` and `r=650`. FFmpeg's local filter help confirms that `r` is an alias for frame rate, not a radius. The later value overrides the intended rate. The helper contains similar large `r` values. This can substantially increase work and is not actual scene footage.

**Repair:** a single 30 fps setting and a checked timeout. Procedural output is never the silent default for a missing clip. No benchmark of its impact on your computer was performed.

### P2 - Subtitle timing and voice assumptions need cleanup

**Locations:** `voice_engine.py:38, 65-88`; `subtitle_engine.py:98-131`; original `requirements.txt`.

The original speech request does not explicitly request word boundaries. The inspected edge-tts implementation defaults to sentence boundaries; allocating each sentence by character count is an estimate, not true word timing [6]. In one no-boundary Roman-caption fallback, all words are assigned the same initial five-second window. Other minimum-duration logic can overrun available scene time.

The original MoviePy dependency permits v1 even though a direct top-level import follows v2 usage. The archive's bundled v2 is not itself evidence of a version mismatch on your computer, but the dependency specification is not reproducible.

**Repair:** pin the inspected edge-tts version, request WordBoundary events explicitly, probe produced audio duration, label missing-boundary timing as estimated, create sequential bounded fallback timings, escape subtitle control text and support a configurable native-caption font. MoviePy is removed from the runtime path. Actual network speech generation and native Telugu glyph rendering were not tested here.

### P2 - Configuration, helper scripts and UI claims are misleading

**Locations:** `script_generator.py:96, 168`; original README; asset-generation scripts; `frontend/index.html:1021`; `backend/app.py:324-327`.

The script module can prefer its initially imported key over a subsequently changed environment value. Its URL embeds a key in the query, which can leak through exception logging. The Gemini model is hardcoded. Some asset helpers embed the author's absolute Windows or private image-library paths, and can print broad completion claims after individual failures. The default demo URL points to a file absent from this archive.

Claims of real generative video, GPU encoding, robust circuit breakers and audio ducking are not supported by the inspected implementation. The original music mixer uses fixed attenuation, not voice-driven ducking. Caption/hashtag export is not automatic Instagram publishing.

**Repair:** use updated runtime key values, a key header instead of a URL query, a configurable model, remove the nonexistent demo URL and exaggerated completion claims, and implement voice-driven music compression. The clean package omits machine-specific helper scripts rather than presenting them as portable tooling.

Current Google API documentation restricts 2.5-model access for new users and recommends newer models for new projects. The example configuration uses the documented `gemini-3.5-flash-lite`; live account entitlement, quota and generated output still require testing on your machine [7][8].

### P2 - State persistence and security are prototype-level

The original in-memory JOBS dictionary loses state on restart; multiple expensive jobs can contend for resources. The project has no authentication or production authorization boundary. The original ignore rules also omit plain `.env`.

**Repair:** persist JSON job status, save diagnostics, serialize rendering within a single server process, recover completed states and mark interrupted jobs failed. Restrict local file identifiers and local CORS origins; add `.env` to ignore rules; exclude secrets from the deliverable.

**Remaining:** this is not a hardened multi-user service. An in-process semaphore is not a cross-process lock, durable queue or distributed worker. Uploaded media processing should eventually be isolated with CPU, memory, disk and time limits. Add authentication, access controls, retention/cleanup, secret storage and dependency review before any internet deployment.

## 4. Evidence and acceptance checks

| Experiment | Original result | Repaired behavior |
|---|---|---|
| Valid local video + audio | Video rendered; basic compositor works | Video renders and is validated |
| Missing visual with music path | Returned final name, no final file | Error; no completed output |
| 2 scenes / 1 voice / 1 visual | Silently rendered one scene | Rejected before render |
| Gym request with supplied library | Selected space clip | No unrelated automatic selection |
| Missing footage/key | Can degrade to unrelated/demo media | Report missing visual source |
| MKV plus mixed source frame rates | Inconsistent suffix/format handling | Decoded, normalized and tested |
| Corrupt/audio-only MP4 upload | Insufficient input validation | Rejected with visible error |
| Full-range bundled footage | Compatibility not verified | Range normalized and export tested |

The final regression suite has **30 passing tests** using actual FFmpeg/ffprobe, FastAPI request tests and mocked external providers. Test code inspects changing pixels in the upper frame region, away from captions, to verify that a moving test background actually reaches the output. This is stronger than testing whether an output filename exists, but not a universal content-quality assessment.

A separate three-second diagnostic was rendered from your supplied `facts_cosmos.mp4`. It has 1080x1920 H.264/yuv420p video, 30 fps and a silent diagnostic audio track, approximately 3.021 seconds including container/audio padding. It was fully decoded and a frame was visually inspected. It is an export check, not newly generated AI footage or a live speech demo.

No live Gemini, Pexels or Edge-TTS request was validated. The environment lacked edge-tts and could not install it from the network; tests use a mocked speech module. No Windows runtime or full browser interaction test was available. JavaScript syntax was checked with Node. Tests ran on Linux, Python 3.13.5, FFmpeg/ffprobe 7.1.5. Version ranges still require installation testing on your target machine.

## 5. Best implementation path for your goal

### Stage A - Make uploaded-video automation dependable

Treat an uploaded clip as the known visual input. Prove offline composition first, then live voice, then a complete short storyboard. Do not add more visual providers until this route is repeatable. Keep the upload option permanently, even after automatic sourcing is added: it is a useful user control and recovery path.

### Stage B - Hybrid scene sourcing

Use a scene plan containing narration, visual search terms, desired duration and source selection. Resolve each scene to an uploaded clip, suitable local footage or validated stock result. Show the selected source and a playable preview; let the user replace it. A missing clip should put that scene into "needs footage", not silently turn it into a text card.

Improve relevance with a curated tagged library, multiple candidate retrieval, duplicate prevention across scenes, portrait-aware cropping and a short human approval step. Filename/tag matching in this repair is a baseline, not an intelligent semantic ranking engine. Keep creator/source/licensing metadata with each asset.

### Stage C - Genuine AI video as an optional source

Build a separate adapter only after the reliable video pipeline exists. Store the provider job ID, wait/poll correctly, handle content rejection and quotas, download the actual MP4 and feed it through the same validation path. Add budget controls and cache reuse. Do not describe a zoomed image as this feature. A paid or account-specific provider is not required for the upload-first version.

### Stage D - Unattended operation and production

Separate orchestration from rendering:

```text
UI / API
    -> stored job + storyboard
    -> durable queue
    -> media worker
       -> acquire/validate scene assets
       -> narrate and align captions
       -> render normalized scenes
       -> assemble/mix
       -> validate output
    -> review/approval
    -> optional scheduler/publishing adapter
```

FastAPI's documentation recommends external task tools for heavy computation that need separate workers or servers [9]. Use durable queue state, bounded retries, idempotent job steps, per-job storage, cancellation and cleanup. A database plus a worker queue is a later milestone; the repair's JSON files and single-process gate deliberately do not pretend to provide that infrastructure.

Automatic Instagram/YouTube publishing is a separate integration requiring the appropriate current platform APIs, account authorization and publishing checks. It has not been added. Do not schedule posting until render success is determined by validated media and a content-review policy, rather than a progress bar reaching 100%.

## 6. Recommended immediate sequence

Run the offline clip-render test. Then configure and test one voice. In the UI, choose a short storyboard and upload a known-good clip; apply it to all scenes for the first test. Confirm the actual saved MP4 plays with imagery and captions. Replace repeated clips with appropriate per-scene footage. Only then enable automatic stock retrieval and later true AI-generated clips.

This sequence isolates rendering, speech and sourcing instead of debugging all three external dependencies at once.

## References - primary documentation checked during this review

[1] FFprobe documentation: https://ffmpeg.org/ffprobe.html  
[2] Pexels API documentation: https://www.pexels.com/api/documentation/  
[3] Pexels API access notice: https://www.pexels.com/api/  
[4] Gemini API video generation: https://ai.google.dev/gemini-api/docs/video  
[5] FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html  
[6] edge-tts source: https://raw.githubusercontent.com/rany2/edge-tts/master/src/edge_tts/communicate.py  
[7] Gemini API model availability/deprecations: https://ai.google.dev/gemini-api/docs/deprecations  
[8] Gemini 3.5 Flash-Lite model reference: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite  
[9] FastAPI background-task guidance: https://fastapi.tiangolo.com/tutorial/background-tasks/
