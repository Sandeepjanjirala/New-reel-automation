# Test results and limitations

Review environment: Linux; Python 3.13.5; FFmpeg/ffprobe 7.1.5.

## Latest suite

```text
..............................                                           [100%]
30 passed in 10.33s
```

The final delivery suite is `tests/test_repair.py`. It contains 30 offline regression tests. FastAPI is exercised through TestClient, not through an actual graphical browser.

Real processing: generated test clips/audio, FFmpeg encoding, ffprobe inspection, whole-output decoding, upper-frame pixel variation, mixed-rate MP4/MKV rendering, full-range input conversion, multipart uploads and preview generation, music mixing, request validation and on-disk state recovery.

Mocked: Pexels HTTP replies/downloads and edge-tts speech metadata/audio events. These test the integration contract, not the availability of live external services.

A separate real-asset smoke render used the supplied facts_cosmos.mp4. Result: 1080x1920, 30 fps, H.264/yuv420p, approximately 3.021 seconds, captions and intentionally silent diagnostic audio. Full decode passed and a rendered frame was visually inspected. This sample is based on your animated photograph, not a newly generated video-model result.

JavaScript: extracted inline script passed `node --check`.

Not verified: live Gemini/Pexels/Edge-TTS calls; external credentials; Windows installation/runtime; full browser interaction; native Telugu font availability/rendering; long production jobs; concurrent multi-process workers; social-media publishing; full security or licensing audit. edge-tts was unavailable in the review environment and installation was blocked by network resolution, so real speech requests could not be exercised.

Original compositor experiments are preserved in `evidence/ORIGINAL_REPRODUCTION.json`. They show a valid input producing a video, a missing input returning a nonexistent final filename, a mismatched scene list silently shortening the result, and a gym scene receiving an unrelated space asset.
