import os
import uuid
import shutil
import asyncio
import requests
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import (
    BASE_DIR,
    PROJECT_ROOT,
    OUTPUT_DIR,
    MUSIC_DIR,
    VIDEOS_DIR,
    AVAILABLE_VOICES,
    DEFAULT_VOICE,
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    PEXELS_API_KEY,
    GEMINI_API_KEY
)
from .services.script_generator import generate_storyboard, Storyboard
from .services.voice_engine import _generate_scene_voices, synthesize_voice_with_timestamps
from .services.visual_engine import generate_scene_visuals
from .services.video_compositor import compose_final_video
from .services.media_tools import (MediaError, check_tools, detect_best_encoder, executable,
                                   probe_media, run_checked, safe_child, validate_final, validate_job_id)
from .services.video_providers import (ROUTER, UPLOADS_DIR, MAX_MEDIA_BYTES, VIDEO_EXTENSIONS,
                                      resolve_custom_clip, source_kind, pexels_key, pixabay_key,
                                      CuratedStockProvider)
from .services.pixabay_stock import PixabayClient
from .services.settings_store import update_env_keys, validate_key

app = FastAPI(
    title="ShortsGenius API",
    description="Autonomous AI Short-Form Video & Reel Generator Engine",
    version="1.1.0"
)

# Enable CORS for local web dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job Status Store
JOBS: Dict[str, Dict[str, Any]] = {}
RENDER_LOCK = asyncio.Semaphore(1)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _save_job(job_id: str):
    folder = OUTPUT_DIR / "jobs" / validate_job_id(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / "status.tmp"
    JOBS[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary.write_text(json.dumps(JOBS[job_id], indent=2), encoding="utf-8")
    temporary.replace(folder / "status.json")


def _validated_scenes(storyboard):
    scenes = storyboard.get("scenes", [])
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 40:
        raise MediaError("A storyboard must contain 1 to 40 scenes.")
    numbers = set()
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise MediaError(f"Scene {index} is not an object.")
        number = scene.get("scene_number", index)
        if isinstance(number, bool) or not isinstance(number, int) or number < 1 or number in numbers:
            raise MediaError("Scene numbers must be unique positive integers.")
        numbers.add(number)
        scene["scene_number"] = number
        text = scene.get("narration", "")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise MediaError(f"Scene {number} needs narration of 1 to 2000 characters.")
    return scenes


def _preflight(req):
    errors, warnings = [], []
    try:
        check_tools()
        scenes = _validated_scenes(req.storyboard)
    except (MediaError, ValueError) as exc:
        return {"ready": False, "errors": [str(exc)], "warnings": []}
    context = {"pexels_api_key": req.pexels_api_key, "pixabay_api_key": req.pixabay_api_key,
               "allow_photo_motion": req.allow_photo_motion}
    for scene in scenes:
        number = scene["scene_number"]
        key = f"scene_{number}"
        source = (req.scene_providers or {}).get(key) or scene.get("provider") or "auto"
        custom = (req.custom_clips or {}).get(key)
        try:
            if custom:
                path = resolve_custom_clip(custom)
                if source_kind(path) in {"photo_motion", "procedural"} and not req.allow_photo_motion:
                    raise MediaError("Selected library item is a photo-animation demo; enable photo motion explicitly or upload footage.")
                probe_media(path, require_video=True, decode=True)
            elif source == "auto" and (pexels_key(context) or pixabay_key(context)):
                warnings.append(f"Scene {number}: stock API connectivity and a usable match still need to be verified.")
            elif source in ("auto", "curated"):
                path = CuratedStockProvider().generate_clip(scene, OUTPUT_DIR / "unused.mp4", context)
                if not path:
                    raise MediaError("No matching allowed local footage. Upload a clip or configure a stock-video key.")
            elif source in ("pexels", "pixabay"):
                configured = pexels_key(context) if source == "pexels" else pixabay_key(context)
                if not configured:
                    raise MediaError(f"{source.title()} key is missing. Open API Keys & Sources or upload footage.")
                warnings.append(f"Scene {number}: {source.title()} connectivity and matching are checked during rendering.")
            elif source == "procedural" and req.allow_photo_motion:
                warnings.append(f"Scene {number}: a demo gradient was explicitly selected; this is not footage.")
            else:
                raise MediaError("Selected provider is not connected, or no upload is attached.")
        except (MediaError, ValueError) as exc:
            errors.append(f"Scene {number}: {exc}")
    return {"ready": not errors, "errors": errors, "warnings": warnings, "scene_count": len(scenes)}


class GenerateScriptRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    duration_sec: int = Field(default=40, ge=5, le=180)
    niche: str = "Tech & AI"
    language: str = "Telugu"


class RenderVideoRequest(BaseModel):
    storyboard: Dict[str, Any]
    voice_id: str = DEFAULT_VOICE
    music_track: Optional[str] = "lofi_chill"
    pexels_api_key: Optional[str] = None
    pixabay_api_key: Optional[str] = None
    custom_clips: Optional[Dict[str, str]] = None
    scene_providers: Optional[Dict[str, str]] = None
    subtitle_style: str = "hormozi_gold"
    subtitle_position: str = "bottom_safe"
    subtitle_format: str = "roman"
    allow_photo_motion: bool = False


class SettingsRequest(BaseModel):
    pexels_api_key: Optional[str] = None
    pixabay_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None


class VoicePreviewRequest(BaseModel):
    text: str
    voice_id: str = DEFAULT_VOICE


@app.get("/api/subtitle-styles")
def get_subtitle_styles():
    from .services.subtitle_engine import SUBTITLE_STYLES, POSITION_PRESETS
    return {
        "styles": list(SUBTITLE_STYLES.values()),
        "positions": list(POSITION_PRESETS.values())
    }


@app.get("/api/video-providers")
def get_video_providers():
    from .services.video_providers import ROUTER
    return ROUTER.list_available_providers()


@app.get("/api/voices")
def get_available_voices():
    return list(AVAILABLE_VOICES.values())


@app.get("/api/music")
def get_available_music():
    tracks = []
    if MUSIC_DIR.exists():
        for file in MUSIC_DIR.glob("*.mp3"):
            name = file.stem.replace("_", " ").title()
            tracks.append({"id": file.stem, "name": name})
    return tracks


@app.get("/api/broll-library")
def get_broll_library():
    """
    Returns built-in stock B-roll clips available in backend/assets/videos/
    """
    clips = []
    if VIDEOS_DIR.exists():
        for vid in sorted(VIDEOS_DIR.glob("*.mp4")):
            clips.append({
                "id": vid.stem,
                "filename": vid.name,
                "title": vid.stem.replace("_", " ").title(),
                "kind": source_kind(vid),
                "url": f"/api/video/asset/{vid.name}"
            })
    return clips


@app.get("/api/video/asset/{filename}")
def get_asset_video(filename: str):
    path = safe_child(VIDEOS_DIR, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset video not found")
    return FileResponse(path=str(path), media_type="video/mp4")


@app.get("/api/health")
def health():
    try:
        return check_tools()
    except MediaError as exc:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})


@app.post("/api/preflight")
async def preflight(req: RenderVideoRequest):
    return await asyncio.to_thread(_preflight, req)


@app.post("/api/upload-scene-video")
async def upload_scene_video(file: UploadFile = File(...), scene_number: int = Form(...)):
    if not 1 <= scene_number <= 1000:
        raise HTTPException(status_code=400, detail="Invalid scene number.")
    extension = Path(file.filename or "").suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Supported uploads: MP4, MOV, WEBM and MKV.")
    token = uuid.uuid4().hex
    target = UPLOADS_DIR / f"upload_{token}{extension}"
    preview = UPLOADS_DIR / f"preview_{token}.mp4"
    try:
        size = 0
        with target.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_MEDIA_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds 250 MB.")
                handle.write(chunk)
        metadata = await asyncio.to_thread(probe_media, target, require_video=True, decode=True)
        if metadata["duration"] > 600:
            raise HTTPException(status_code=400, detail="Upload must be no longer than 10 minutes.")
        # A small browser-compatible preview also works for MKV/MOV source containers.
        await asyncio.to_thread(run_checked, [
            executable("ffmpeg"), "-nostdin", "-y", "-v", "error", "-filter_threads", "2",
            "-i", str(target), "-t", str(min(5, metadata["duration"])), "-an",
            "-vf", "scale=360:640:force_original_aspect_ratio=increase:in_range=auto:out_range=tv,crop=360:640,setsar=1,fps=30",
            "-c:v", "libx264", "-preset", "veryfast", "-threads", "2", "-pix_fmt", "yuv420p", "-color_range", "tv",
            "-movflags", "+faststart", str(preview)], timeout=120)
        return {"status": "ok", "scene_key": f"scene_{scene_number}",
                "asset_id": target.name, "file_path": target.name, "filename": target.name,
                "preview_url": f"/api/upload-preview/{preview.name}",
                "duration": round(metadata["duration"], 3),
                "width": metadata["video"]["width"], "height": metadata["video"]["height"]}
    except Exception as exc:
        target.unlink(missing_ok=True)
        preview.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=f"Invalid upload: {exc}") from exc
    finally:
        await file.close()


@app.get("/api/upload-preview/{filename}")
def get_upload_preview(filename: str):
    try:
        path = safe_child(UPLOADS_DIR, filename)
    except MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file() or not filename.startswith("preview_") or path.suffix != ".mp4":
        raise HTTPException(status_code=404, detail="Preview not found.")
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/api/settings")
def get_settings():
    from . import config
    from dotenv import dotenv_values
    gemini = os.getenv("GEMINI_API_KEY", config.GEMINI_API_KEY)
    if not gemini:
        try:
            gemini = dotenv_values(PROJECT_ROOT / ".env").get("GEMINI_API_KEY", "")
        except Exception:
            pass
    enc = detect_best_encoder()
    return {
        "has_pexels_key": bool(pexels_key()),
        "has_pixabay_key": bool(pixabay_key()),
        "has_gemini_key": bool(gemini),
        "encoder": enc["name"],
        "is_hardware_accelerated": enc["is_hardware"],
        "automatic_source_order": ["pexels", "pixabay", "curated"],
        "build": "ShortsGenius_Repaired + Hardware Acceleration 2.0"
    }


@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    from . import config
    updates = {}
    try:
        for field, variable in (("pexels_api_key", "PEXELS_API_KEY"),
                                ("pixabay_api_key", "PIXABAY_API_KEY"),
                                ("gemini_api_key", "GEMINI_API_KEY")):
            value = getattr(req, field)
            if value is not None:
                updates[variable] = validate_key(value)
        update_env_keys(PROJECT_ROOT / ".env", updates)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid API-key settings or .env encoding. Use single-line keys and UTF-8.") from None
    except OSError:
        raise HTTPException(status_code=500, detail="Cannot save .env. Check folder permissions and free disk space.") from None
    # Only change the running process after the file has been saved successfully.
    for variable, value in updates.items():
        setattr(config, variable, value)
        os.environ[variable] = value
    return {"status": "ok", "message": "API keys saved. Existing FFmpeg and other settings were preserved."}


@app.post("/api/test-pixabay-key")
def api_test_pixabay_key(req: SettingsRequest):
    try:
        key = validate_key(req.pixabay_api_key) if req.pixabay_api_key is not None else pixabay_key()
        if not key:
            raise HTTPException(status_code=400, detail="Pixabay API key cannot be empty.")
        client = PixabayClient(key, OUTPUT_DIR / "stock_cache" / "pixabay")
        data, cached = client.search("technology", per_page=3)
        suffix = " (24-hour cached check)" if cached else ""
        return {"valid": True, "cached": cached,
                "message": f"Pixabay Video API accepted this key{suffix}. Save Configuration to use a newly entered key."}
    except (MediaError, ValueError) as exc:
        return {"valid": False, "message": str(exc)}
    except HTTPException:
        raise
    except OSError:
        return {"valid": False, "message": "Cannot use the Pixabay cache. Check output-folder permissions."}


@app.post("/api/test-pexels-key")
def api_test_pexels_key(req: Dict[str, Any]):
    api_key = str(req.get("pexels_api_key") or pexels_key()).strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Pexels API key cannot be empty.")
    if re.match(r"^\d+-[0-9a-fA-F]+$", api_key):
        return {
            "valid": False,
            "message": "This format looks like a Pixabay API key (starts with a numeric ID followed by a hyphen). Please paste it into the Pixabay API key field instead."
        }

    try:
        headers = {"Authorization": api_key, "User-Agent": "ShortsGenius/1.0"}
        res = requests.get(
            "https://api.pexels.com/v1/videos/search?query=technology&orientation=portrait&per_page=1",
            headers=headers,
            timeout=8
        )
        if res.status_code == 200:
            data = res.json()
            total = data.get("total_results", 0)
            return {
                "valid": True,
                "message": f"Pexels Video API is connected! Found {total} vertical stock clips."
            }
        elif res.status_code == 401:
            return {
                "valid": False,
                "message": "Pexels returned 401 Unauthorized. Please check your API key at pexels.com/api."
            }
        else:
            return {
                "valid": False,
                "message": f"Pexels API returned HTTP {res.status_code}."
            }
    except Exception as e:
        return {
            "valid": False,
            "message": f"Connection error: {str(e)}"
        }


@app.post("/api/generate-storyboard")
def api_generate_storyboard(req: GenerateScriptRequest):
    try:
        storyboard = generate_storyboard(
            topic=req.topic,
            duration_sec=req.duration_sec,
            niche=req.niche,
            language=req.language
        )
        return storyboard.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/render-video")
async def api_render_video(req: RenderVideoRequest, background_tasks: BackgroundTasks):
    readiness = await asyncio.to_thread(_preflight, req)
    if not readiness["ready"]:
        raise HTTPException(status_code=400, detail=" | ".join(readiness["errors"]))
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "status": "QUEUED",
        "progress": 5,
        "message": "Initializing generation pipeline...",
        "video_url": None,
        "error": None
    }

    _save_job(job_id)

    # Run rendering pipeline in background
    background_tasks.add_task(
        _execute_render_pipeline,
        job_id=job_id,
        storyboard_data=req.storyboard,
        voice_id=req.voice_id,
        music_track=req.music_track,
        pexels_api_key=req.pexels_api_key,
        pixabay_api_key=req.pixabay_api_key,
        custom_clips=req.custom_clips,
        scene_providers=req.scene_providers,
        subtitle_style=req.subtitle_style,
        subtitle_position=req.subtitle_position,
        subtitle_format=req.subtitle_format,
        allow_photo_motion=req.allow_photo_motion
    )

    return {"job_id": job_id, "status": "QUEUED"}


@app.get("/api/job/{job_id}")
def get_job_status(job_id: str):
    try:
        validate_job_id(job_id)
    except MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job_id in JOBS:
        return JOBS[job_id]
    status_file = OUTPUT_DIR / "jobs" / job_id / "status.json"
    if status_file.exists():
        job = json.loads(status_file.read_text(encoding="utf-8"))
        if job.get("status") not in ("COMPLETED", "FAILED"):
            job.update(status="FAILED", error="Server restarted during this job; submit it again.",
                       message="Interrupted render. Existing uploads are still available.")
        elif job.get("status") == "COMPLETED":
            try:
                validate_final(OUTPUT_DIR / f"{job_id}_final.mp4")
            except MediaError as exc:
                job.update(status="FAILED", error=str(exc), video_url=None)
        JOBS[job_id] = job
        _save_job(job_id)
        return job
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/video/{filename}")
def get_rendered_video(filename: str):
    video_path = safe_child(OUTPUT_DIR, filename)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=filename, content_disposition_type="inline"
    )


@app.get("/api/latest-video")
def get_latest_video():
    """
    Returns the most recently rendered reel for quick preview recovery.
    """
    videos = sorted(OUTPUT_DIR.glob("*_final.mp4"), key=os.path.getmtime, reverse=True)
    if not videos:
        return {"video_url": None, "filename": None}
    latest = videos[0]
    return {"video_url": f"/api/video/{latest.name}", "filename": latest.name}


@app.post("/api/preview-voice")
async def preview_voice(req: VoicePreviewRequest):
    """
    Synthesizes a short instant audio preview for a single scene's narration.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    preview_id = uuid.uuid4().hex[:8]
    output_filename = f"preview_{preview_id}.mp3"
    try:
        audio_path, _, duration, _ = await synthesize_voice_with_timestamps(
            text=req.text.strip(),
            voice=req.voice_id,
            output_filename=output_filename
        )
        return {
            "status": "ok",
            "audio_url": f"/api/audio/{output_filename}",
            "duration": round(duration, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice synthesis failed: {str(e)}")


@app.get("/api/audio/{filename}")
def get_audio_file(filename: str):
    path = safe_child(OUTPUT_DIR, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path=str(path), media_type="audio/mpeg", filename=filename)


@app.get("/api/reels")
def get_rendered_reels():
    """
    Returns list of recently generated Reels, sorted newest first.
    """
    reels = []
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.glob("*_final.mp4"), key=os.path.getmtime, reverse=True):
            stat = f.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            mtime = stat.st_mtime
            reels.append({
                "filename": f.name,
                "url": f"/api/video/{f.name}",
                "size_mb": size_mb,
                "created_at": mtime,
                "project_id": f.name.replace("_final.mp4", "")
            })
    return reels


async def _execute_render_pipeline(
    job_id: str, storyboard_data: Dict[str, Any], voice_id: str,
    music_track: Optional[str], pexels_api_key: Optional[str] = None,
    custom_clips: Optional[Dict[str, str]] = None,
    scene_providers: Optional[Dict[str, str]] = None,
    subtitle_style: str = "hormozi_gold", subtitle_position: str = "bottom_safe",
    subtitle_format: str = "roman", allow_photo_motion: bool = False,
    pixabay_api_key: Optional[str] = None,
):
    async with RENDER_LOCK:
        try:
            scenes = _validated_scenes(storyboard_data)
            JOBS[job_id].update(status="PROCESSING", progress=15,
                               message="Synthesizing narration voices and retrieving footage concurrently...")
            _save_job(job_id)

            visual_coro = asyncio.to_thread(
                generate_scene_visuals, scenes=scenes, project_id=job_id,
                pexels_api_key=pexels_api_key, custom_clips=custom_clips,
                scene_providers=scene_providers, allow_photo_motion=allow_photo_motion,
                pixabay_api_key=pixabay_api_key
            )
            voice_coro = _generate_scene_voices(scenes, voice_id, job_id)

            visual_paths, voices = await asyncio.gather(visual_coro, voice_coro)

            report = OUTPUT_DIR / "jobs" / job_id / "visual_report.json"
            if report.is_file():
                try:
                    JOBS[job_id]["visual_report"] = json.loads(report.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    pass

            JOBS[job_id].update(status="COMPOSITING", progress=60,
                               message="Rendering and compositing video scenes in parallel...")
            _save_job(job_id)
            final = await asyncio.to_thread(
                compose_final_video, scenes=scenes, voice_data=voices,
                visual_paths=visual_paths, music_track_name=music_track,
                project_id=job_id, subtitle_style=subtitle_style,
                subtitle_position=subtitle_position, subtitle_format=subtitle_format)
            validate_final(final)
            JOBS[job_id].update(status="COMPLETED", progress=100,
                               message="MP4 rendered and validated. Review the scene content before posting.",
                               video_url=f"/api/video/{final.name}")
            _save_job(job_id)
        except Exception as exc:
            JOBS[job_id].update(status="FAILED", error=str(exc), message=f"Pipeline error: {exc}", video_url=None)
            folder = OUTPUT_DIR / "jobs" / job_id
            folder.mkdir(parents=True, exist_ok=True)
            report = folder / "visual_report.json"
            if report.is_file():
                try:
                    JOBS[job_id]["visual_report"] = json.loads(report.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    pass
            (folder / "pipeline_error.log").write_text(traceback.format_exc(), encoding="utf-8")
            _save_job(job_id)


# Serve frontend static assets
frontend_dir = BASE_DIR.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
