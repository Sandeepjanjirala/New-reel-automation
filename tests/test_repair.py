"""Offline regressions: real FFmpeg, with mocked external speech/stock services."""
import asyncio
import json
import shutil
import sys
import subprocess
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from backend import app as api
from backend.services import media_tools as media
from backend.services import video_compositor as compositor
from backend.services import video_providers as providers
from backend.services import visual_engine, voice_engine, subtitle_engine


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    root = tmp_path_factory.mktemp("media")
    ff = media.executable("ffmpeg")
    for name, rate in [("clip.mp4", 24), ("clip.mkv", 25)]:
        media.run_checked([ff, "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
            f"testsrc2=size=320x180:rate={rate}", "-t", "1.2", "-c:v", "libx264",
            "-threads", "1", "-pix_fmt", "yuv420p", str(root / name)])
    for name in ("voice.wav", "voice.mp3", "music.mp3", "audio_only.mp4"):
        media.run_checked([ff, "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=44100", "-t", "1.2", str(root / name)])
    return root


@pytest.fixture
def work(tmp_path, monkeypatch):
    out, videos, music = tmp_path / "output", tmp_path / "videos", tmp_path / "music"
    uploads = out / "uploads"
    for path in (out, videos, music, uploads): path.mkdir(parents=True, exist_ok=True)
    for module in (api, compositor, visual_engine, voice_engine, providers):
        monkeypatch.setattr(module, "OUTPUT_DIR", out, raising=False)
    for module in (api, providers):
        monkeypatch.setattr(module, "UPLOADS_DIR", uploads)
        monkeypatch.setattr(module, "VIDEOS_DIR", videos)
    monkeypatch.setattr(compositor, "MUSIC_DIR", music)
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    api.JOBS.clear()
    monkeypatch.setattr(api, "RENDER_LOCK", asyncio.Semaphore(1))
    return SimpleNamespace(root=tmp_path, out=out, videos=videos, music=music, uploads=uploads)


def scene(number=1, keyword="gym workout"):
    return {"scene_number": number, "narration": "Visible footage behind captions",
            "roman_subtitles": "Visible footage behind captions", "search_keyword": keyword,
            "visual_prompt": keyword, "duration_estimate_sec": 1.2}


def voice(samples):
    return {"audio_path": str(samples / "voice.wav"), "duration": 1.2, "words": []}


def test_valid_media_probe(samples):
    info = media.probe_media(samples / "clip.mp4", require_video=True, decode=True)
    assert info["video"]["width"] == 320 and info["duration"] > 1


def test_corrupt_mp4_rejected(work):
    bad = work.uploads / "fake.mp4"
    bad.write_bytes(b"not a video" * 3000)
    with pytest.raises(media.MediaError): media.probe_media(bad, require_video=True)


def test_audio_only_mp4_is_not_footage(samples):
    with pytest.raises(media.MediaError, match="No video stream"):
        media.probe_media(samples / "audio_only.mp4", require_video=True)


def test_empty_scenes_rejected(work):
    with pytest.raises(media.MediaError, match="equal and non-zero"):
        compositor.compose_final_video([], [], [], project_id="empty")


def test_mismatched_scene_lists_rejected(work, samples):
    with pytest.raises(media.MediaError, match="equal and non-zero"):
        compositor.compose_final_video([scene(), scene(2)], [voice(samples)],
            [str(samples / "clip.mp4")], project_id="mismatch")
    assert not (work.out / "mismatch_final.mp4").exists()


def test_missing_input_cannot_return_success(work, samples):
    with pytest.raises(media.MediaError, match="Missing or empty"):
        compositor.compose_final_video([scene()], [voice(samples)],
            [str(work.root / "missing.mp4")], project_id="missing")
    assert not (work.out / "missing_final.mp4").exists()


def test_mkv_and_mixed_fps_get_normalized(work, samples):
    output = compositor.compose_final_video([scene(), scene(2)], [voice(samples), voice(samples)],
        [str(samples / "clip.mp4"), str(samples / "clip.mkv")], project_id="mixed")
    info = media.validate_final(output, 2.4, full_decode=True)
    assert info["video"]["r_frame_rate"] == "30/1"
    assert info["audio"]["sample_rate"] == "48000" and info["audio"]["channels"] == 2
    manifest = json.loads((work.out / "jobs/mixed/render_manifest.json").read_text())
    assert manifest["validated"] and len(manifest["scenes"]) == 2
    assert (work.out / "jobs/mixed/ffmpeg.log").exists()
    # Inspect the upper image region, excluding the lower caption area.
    frames = []
    for timestamp in ("0.2", "0.8"):
        decoded = subprocess.run([media.executable("ffmpeg"), "-v", "error", "-ss", timestamp,
            "-i", str(output), "-frames:v", "1", "-vf", "crop=1080:1000:0:0,scale=64:64,format=rgb24",
            "-f", "rawvideo", "-"], capture_output=True, check=True, timeout=30)
        frames.append(decoded.stdout)
    assert len(frames[0]) == 64 * 64 * 3
    assert max(frames[0]) - min(frames[0]) > 100
    assert sum(abs(a-b) for a, b in zip(frames[0], frames[1])) / len(frames[0]) > 0.5


def test_music_mix_keeps_video_and_audio(work, samples):
    shutil.copy2(samples / "music.mp3", work.music / "test.mp3")
    output = compositor.compose_final_video([scene()], [voice(samples)], [str(samples / "clip.mp4")],
        music_track_name="test", project_id="music")
    media.validate_final(output, 1.2, full_decode=True)


def test_command_error_is_raised_and_logged(work):
    log = work.root / "bad.log"
    with pytest.raises(media.MediaError):
        media.run_checked([media.executable("ffmpeg"), "-no_such_option_123"], log_path=log)
    assert "no_such_option_123" in log.read_text()


def test_custom_path_cannot_escape_storage(work, samples):
    with pytest.raises(media.MediaError, match="must be uploaded"):
        providers.resolve_custom_clip(str(samples / "clip.mp4"))
    with pytest.raises(media.MediaError): providers.resolve_custom_clip("../secret.mp4")


def test_manual_upload_wins(work, samples):
    target = work.uploads / "owned.mp4"
    shutil.copy2(samples / "clip.mp4", target)
    path, name = providers.ROUTER.resolve_scene_clip(scene(), work.out / "unused.mp4", 0,
        preferred_provider="curated", custom_clips={"scene_1": target.name})
    assert path == target and name == "User-selected video"


def test_missing_manual_upload_cannot_fallback(work):
    with pytest.raises(media.MediaError, match="missing"):
        providers.ROUTER.resolve_scene_clip(scene(), work.out / "unused.mp4", 0,
            custom_clips={"scene_1": "gone.mp4"})


def test_no_footage_does_not_generate_background(work):
    with pytest.raises(media.MediaError, match="no usable footage"):
        providers.ROUTER.resolve_scene_clip(scene(), work.out / "unused.mp4", 0)
    assert not (work.out / "unused.mp4").exists()


def test_unrelated_library_clips_not_selected(work, samples):
    shutil.copy2(samples / "clip.mp4", work.videos / "space_cosmos.mp4")
    assert providers.CuratedStockProvider().generate_clip(scene(), work.out / "unused.mp4", {}) is None


def test_photo_demo_requires_permission(work, samples):
    target = work.videos / "facts_cosmos.mp4"
    shutil.copy2(samples / "clip.mp4", target)
    with pytest.raises(media.MediaError, match="photo-animation demo"):
        providers.ROUTER.resolve_scene_clip(scene(), work.out / "unused.mp4", 0,
            custom_clips={"scene_1": target.name})
    path, _ = providers.ROUTER.resolve_scene_clip(scene(), work.out / "unused.mp4", 0,
        custom_clips={"scene_1": target.name}, allow_photo_motion=True)
    assert path == target


def test_ai_video_not_falsely_available():
    assert not providers.GenerativeAIVideoProvider().is_available()


def test_gradient_demo_is_explicit_and_30fps(work):
    provider = providers.ProceduralMotionProvider()
    with pytest.raises(media.MediaError): provider.generate_clip(scene(), work.out / "gradient.mp4", {})
    path = provider.generate_clip(scene(), work.out / "gradient.mp4", {"allow_photo_motion": True})
    assert media.probe_media(path, require_video=True)["video"]["r_frame_rate"] == "30/1"


def test_preflight_prevents_empty_footage_job(work):
    with TestClient(api.app) as client:
        payload = {"storyboard": {"scenes": [scene()]}}
        result = client.post("/api/preflight", json=payload)
        assert result.status_code == 200 and not result.json()["ready"]
        assert client.post("/api/render-video", json=payload).status_code == 400
        assert not api.JOBS


def test_mkv_upload_and_browser_preview(work, samples):
    with TestClient(api.app) as client:
        with (samples / "clip.mkv").open("rb") as handle:
            response = client.post("/api/upload-scene-video", data={"scene_number": "1"},
                files={"file": ("clip.mkv", handle, "video/x-matroska")})
        assert response.status_code == 200, response.text
        data = response.json()
        assert "/" not in data["asset_id"] and (work.uploads / data["asset_id"]).exists()
        preview = client.get(data["preview_url"], headers={"Range": "bytes=0-99"})
        assert preview.status_code in (200, 206) and preview.headers["content-type"] == "video/mp4"


def test_corrupt_and_unsupported_uploads_rejected(work):
    with TestClient(api.app) as client:
        for name in ("fake.mp4", "fake.exe"):
            response = client.post("/api/upload-scene-video", data={"scene_number": "1"},
                files={"file": (name, b"invalid" * 100, "video/mp4")})
            assert response.status_code == 400
    assert not list(work.uploads.iterdir())


def test_upload_size_limit_removes_partial(work, monkeypatch):
    monkeypatch.setattr(api, "MAX_MEDIA_BYTES", 100)
    with TestClient(api.app) as client:
        response = client.post("/api/upload-scene-video", data={"scene_number": "1"},
            files={"file": ("large.mp4", b"x" * 101, "video/mp4")})
        assert response.status_code == 413
    assert not list(work.uploads.iterdir())


def test_no_invented_demo_video_url(work):
    with TestClient(api.app) as client:
        assert client.get("/api/latest-video").json()["video_url"] is None


def test_roman_timing_is_bounded_without_overlap():
    words = subtitle_engine.align_roman_words([], "One two three four", duration=1.2)
    assert words[0]["start"] == 0 and words[-1]["end"] == pytest.approx(1.2)
    assert all(a["end"] <= b["start"] for a, b in zip(words, words[1:]))
    assert subtitle_engine._format_ass_time(59.999) == "0:01:00.00"


def test_ass_overrides_from_user_text_are_sanitized(work):
    path = work.root / "sub.ass"
    subtitle_engine.build_karaoke_ass_script([], "hello", 1.2, path, roman_text=r"hello {\alpha&HFF&} world")
    assert r"{\ALPHA" not in path.read_text()


def test_word_boundaries_requested_and_audio_probed(work, samples, monkeypatch):
    seen = {}
    class FakeCommunicate:
        def __init__(self, text, **kwargs): seen.update(kwargs)
        async def stream(self):
            yield {"type": "audio", "data": (samples / "voice.mp3").read_bytes()}
            yield {"type": "WordBoundary", "text": "Hello", "offset": 1_000_000, "duration": 3_000_000}
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=FakeCommunicate))
    path, words, duration, srt = asyncio.run(voice_engine.synthesize_voice_with_timestamps("Hello"))
    assert seen["boundary"] == "WordBoundary" and words[0].start_time == pytest.approx(0.1)
    assert words[0].end_time == pytest.approx(0.4) and path.exists() and duration > 1 and "Hello" in srt


def test_end_to_end_api_with_mock_speech_and_restart(work, samples, monkeypatch):
    target = work.uploads / "end_to_end.mp4"
    shutil.copy2(samples / "clip.mp4", target)
    async def offline_voices(scenes, voice_id, project_id): return [voice(samples) for _ in scenes]
    monkeypatch.setattr(api, "_generate_scene_voices", offline_voices)
    with TestClient(api.app) as client:
        response = client.post("/api/render-video", json={"storyboard": {"scenes": [scene()]},
            "music_track": None, "custom_clips": {"scene_1": target.name}})
        assert response.status_code == 200, response.text
        job_id = response.json()["job_id"]
        job = client.get(f"/api/job/{job_id}").json()
        assert job["status"] == "COMPLETED", job
        assert client.get(job["video_url"]).status_code == 200
        assert job["visual_report"][0]["provider"] == "upload"
        api.JOBS.clear()
        assert client.get(f"/api/job/{job_id}").json()["status"] == "COMPLETED"


def test_compositor_error_becomes_failed_job(work, samples, monkeypatch):
    target = work.uploads / "error_test.mp4"
    shutil.copy2(samples / "clip.mp4", target)
    async def offline_voices(scenes, voice_id, project_id): return [voice(samples)]
    def fail(**kwargs): raise media.MediaError("Simulated FFmpeg failure")
    monkeypatch.setattr(api, "_generate_scene_voices", offline_voices)
    monkeypatch.setattr(api, "compose_final_video", fail)
    with TestClient(api.app) as client:
        result = client.post("/api/render-video", json={"storyboard": {"scenes": [scene()]},
            "music_track": None, "custom_clips": {"scene_1": target.name}})
        job = client.get(f"/api/job/{result.json()['job_id']}").json()
        assert job["status"] == "FAILED" and job["video_url"] is None and "Simulated" in job["error"]


def test_pexels_current_endpoint_download_and_provenance(work, samples, monkeypatch):
    calls = []
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def raise_for_status(self): pass
        def json(self):
            return {"videos": [{"id": 123, "url": "https://www.pexels.com/video/test-123/",
                "user": {"name": "Test Creator"}, "video_files": [{"file_type": "video/mp4",
                    "width": 320, "height": 180, "link": "https://videos.pexels.com/test.mp4"}]}]}
        def iter_content(self, size): yield (samples / "clip.mp4").read_bytes()
    def get(url, **kwargs):
        calls.append(url)
        return Response()
    monkeypatch.setattr(providers.requests, "get", get)
    path = providers.PexelsVideoProvider().generate_clip(scene(), work.out / "download.mp4", {"pexels_api_key": "test-key"})
    assert calls[0] == "https://api.pexels.com/v1/videos/search"
    assert path.exists() and path.with_suffix(".source.json").exists()


def test_pexels_rate_limit_not_hidden(work, monkeypatch):
    class Response:
        status_code = 429
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(providers.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(media.MediaError, match="rate limit"):
        providers.PexelsVideoProvider().generate_clip(scene(), work.out / "x.mp4", {"pexels_api_key": "test-key"})


def test_full_range_upload_is_normalized_to_limited_yuv420p(work, samples):
    source = work.root / "full_range.mp4"
    media.run_checked([media.executable("ffmpeg"), "-nostdin", "-y", "-v", "error",
        "-i", str(samples / "clip.mp4"), "-vf", "scale=out_range=pc",
        "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuvj420p", "-color_range", "pc", str(source)])
    assert media.probe_media(source, require_video=True)["video"]["color_range"] == "pc"
    output = compositor.compose_final_video([scene()], [voice(samples)], [str(source)],
        project_id="full_range")
    info = media.validate_final(output, 1.2, full_decode=True)
    assert info["video"]["pix_fmt"] == "yuv420p"
    assert info["video"].get("color_range", "tv") != "pc"
    with TestClient(api.app) as client:
        with source.open("rb") as handle:
            response = client.post("/api/upload-scene-video", data={"scene_number": "1"},
                files={"file": ("full_range.mp4", handle, "video/mp4")})
        assert response.status_code == 200, response.text
        preview = work.uploads / response.json()["preview_url"].split("/")[-1]
        assert media.probe_media(preview, require_video=True)["video"]["pix_fmt"] == "yuv420p"
