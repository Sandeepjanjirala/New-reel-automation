"""Footage-first routing. Missing footage is an error, not a successful blank reel."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional
import requests

from dotenv import dotenv_values

from .. import config
from ..config import VIDEOS_DIR, OUTPUT_DIR
from .media_tools import MediaError, executable, probe_media, run_checked, safe_child

UPLOADS_DIR = OUTPUT_DIR / "uploads"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
MAX_MEDIA_BYTES = 250 * 1024 * 1024


def _read_env_var(name: str) -> str:
    val = os.environ.get(name) or getattr(config, name, "") or ""
    if not val:
        try:
            env_file = config.PROJECT_ROOT / ".env"
            if env_file.exists():
                vals = dotenv_values(env_file)
                val = vals.get(name, "") or ""
        except Exception:
            pass
    return str(val).strip()


def pexels_key(context: Optional[dict] = None) -> str:
    context = context or {}
    key = (context.get("pexels_api_key") or _read_env_var("PEXELS_API_KEY")).strip()
    # Pixabay keys format: numeric ID followed by hyphen and hex string (e.g. 57902083-76d185fe...)
    if re.match(r"^\d+-[0-9a-fA-F]+$", key):
        return ""
    return key


def pixabay_key(context: Optional[dict] = None) -> str:
    context = context or {}
    key = (context.get("pixabay_api_key") or _read_env_var("PIXABAY_API_KEY")).strip()
    if not key:
        # Check if user accidentally put their Pixabay key in PEXELS_API_KEY
        fallback = (context.get("pexels_api_key") or _read_env_var("PEXELS_API_KEY")).strip()
        if re.match(r"^\d+-[0-9a-fA-F]+$", fallback):
            return fallback
    return key


def library_manifest() -> dict:
    manifest = VIDEOS_DIR / "manifest.json"
    if manifest.exists():
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise MediaError("The library manifest is invalid JSON.") from exc
    # These two files in the submitted archive are known photo-animation demos.
    return {"facts_cosmos.mp4": {"kind": "photo_motion"},
            "facts_nebula.mp4": {"kind": "photo_motion"}}


def source_kind(path: Path) -> str:
    if path.resolve().parent == VIDEOS_DIR.resolve():
        return library_manifest().get(path.name, {}).get("kind", "user_library_video")
    return "uploaded_or_downloaded_video"


def resolve_custom_clip(value: str) -> Path:
    """Legacy absolute upload paths work only inside the approved upload locations."""
    candidate = Path(value)
    roots = [UPLOADS_DIR.resolve(), VIDEOS_DIR.resolve()]
    if candidate.is_absolute():
        resolved = candidate.resolve()
        allowed = any(resolved.parent == root for root in roots)
        allowed |= (resolved.parent == OUTPUT_DIR.resolve() and resolved.name.startswith("upload_scene_"))
        if not allowed:
            raise MediaError("Custom clips must be uploaded or selected from the local library.")
        if resolved.is_file() and resolved.suffix.lower() in VIDEO_EXTENSIONS:
            return resolved
        raise MediaError("The selected clip no longer exists or is not a supported video.")
    for root in [UPLOADS_DIR, VIDEOS_DIR]:
        path = safe_child(root, value)
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            return path
    raise MediaError("The selected clip is missing. Upload or select it again.")


class BaseVideoProvider:
    def __init__(self, provider_id: str, display_name: str):
        self.provider_id, self.name = provider_id, display_name

    def is_available(self, context=None):
        return False

    def generate_clip(self, scene, output_path, context=None):
        raise NotImplementedError


class CustomUploadProvider(BaseVideoProvider):
    def __init__(self):
        super().__init__("upload", "User-selected video")

    def is_available(self, context=None):
        context = context or {}
        return context.get("scene_key") in context.get("custom_clips", {})

    def generate_clip(self, scene, output_path, context=None):
        context = context or {}
        value = context.get("custom_clips", {}).get(context.get("scene_key"))
        return resolve_custom_clip(value) if value else None


class PexelsVideoProvider(BaseVideoProvider):
    def __init__(self):
        super().__init__("pexels", "Pexels stock video")

    def is_available(self, context=None):
        return bool(pexels_key(context))

    def generate_clip(self, scene, output_path, context=None):
        key = pexels_key(context)
        if not key:
            raise MediaError("Pexels API key is missing.")
        query = str(scene.get("search_keyword", "")).strip()
        if not query:
            raise MediaError("This scene needs an English stock-footage search keyword.")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {"Authorization": key, "User-Agent": "ShortsGenius/repair"}
        last_error = "No usable stock clip matched the scene."
        # Try portrait first, then any orientation; the compositor handles cropping.
        for orientation in ("portrait", None):
            params = {"query": query, "per_page": 8}
            if orientation:
                params["orientation"] = orientation
            with requests.get("https://api.pexels.com/v1/videos/search", params=params,
                              headers=headers, timeout=(5, 25)) as response:
                if response.status_code in (401, 403):
                    raise MediaError("Pexels rejected the key or account permissions.")
                if response.status_code == 429:
                    raise MediaError("Pexels rate limit reached; retry later or upload footage.")
                response.raise_for_status()
                videos = response.json().get("videos", [])
            choices = []
            used = (context or {}).get("used_clips", set())
            for video in videos:
                for item in video.get("video_files", []):
                    if item.get("file_type") == "video/mp4" and str(item.get("link", "")).startswith("https://"):
                        width, height = item.get("width") or 0, item.get("height") or 0
                        if width > 0 and height > 0:
                            # Prefer unused, near-full-HD files rather than always downloading 4K.
                            score = (f"pexels:{video.get('id')}" in used,
                                     abs(width * height - 1080 * 1920))
                            choices.append((score, video, item))
            for _, video, item in sorted(choices, key=lambda candidate: candidate[0])[:4]:
                partial = output_path.with_suffix(".download")
                try:
                    with requests.get(item["link"], stream=True, timeout=(5, 30)) as download:
                        download.raise_for_status()
                        size = 0
                        with partial.open("wb") as handle:
                            for chunk in download.iter_content(128 * 1024):
                                if not chunk:
                                    continue
                                size += len(chunk)
                                if size > MAX_MEDIA_BYTES:
                                    raise MediaError("Stock download exceeds 250 MB.")
                                handle.write(chunk)
                    probe_media(partial, require_video=True, decode=True)
                    partial.replace(output_path)
                    used.add(f"pexels:{video.get('id')}")
                    output_path.with_suffix(".source.json").write_text(json.dumps({
                        "provider": "pexels", "video_id": video.get("id"),
                        "source_url": video.get("url"), "creator": video.get("user", {}),
                    }, indent=2), encoding="utf-8")
                    return output_path
                except (requests.RequestException, MediaError, OSError) as exc:
                    last_error = str(exc)
                    partial.unlink(missing_ok=True)
        raise MediaError(last_error)


class PixabayVideoProvider(BaseVideoProvider):
    """Additional stock provider; all existing upload/compositor paths are retained."""
    def __init__(self):
        super().__init__("pixabay", "Pixabay stock video")

    def is_available(self, context=None):
        return bool(pixabay_key(context))

    def generate_clip(self, scene, output_path, context=None):
        from .pixabay_stock import PixabayClient
        context = context or {}
        used = context.get("used_clips")
        if used is None:
            used = set()
        client = PixabayClient(pixabay_key(context), OUTPUT_DIR / "stock_cache" / "pixabay")
        return client.fetch_scene(scene, Path(output_path), used)


class CuratedStockProvider(BaseVideoProvider):
    def __init__(self):
        super().__init__("curated", "Matched local library")

    def is_available(self, context=None):
        return VIDEOS_DIR.exists() and any(VIDEOS_DIR.glob("*.mp4"))

    def generate_clip(self, scene, output_path, context=None):
        context = context or {}
        query = set(re.findall(r"[a-z0-9]+", (str(scene.get("search_keyword", "")) + " " +
                                            str(scene.get("visual_prompt", ""))).lower()))
        categories = {
            "tech": {"tech", "technology", "ai", "software", "computer", "coding", "developer", "laptop"},
            "gym": {"gym", "fitness", "exercise", "barbell", "workout", "training"},
            "fashion": {"fashion", "runway", "outfit", "clothing", "streetwear", "model"},
            "facts": {"space", "cosmos", "galaxy", "nebula", "stars", "universe", "planet"},
        }
        for category, terms in categories.items():
            if query & terms:
                query.add(category)
        manifest, candidates = library_manifest(), []
        for clip in sorted(VIDEOS_DIR.glob("*.mp4")):
            info = manifest.get(clip.name, {})
            if info.get("kind") in {"photo_motion", "procedural"} and not context.get("allow_photo_motion"):
                continue
            tags = set(re.findall(r"[a-z0-9]+", clip.stem.lower()))
            tags.update(str(tag).lower() for tag in info.get("tags", []))
            score = len(query & tags)
            if score:
                candidates.append((score, clip))
        used = context.get("used_clips", set())
        for _, clip in sorted(candidates, key=lambda item: (item[1].name in used, -item[0], item[1].name)):
            try:
                probe_media(clip, require_video=True, decode=True)
                used.add(clip.name)
                return clip
            except MediaError:
                continue
        return None


class GenerativeAIVideoProvider(BaseVideoProvider):
    def __init__(self):
        super().__init__("ai_video", "AI video generation - not connected")

    def generate_clip(self, scene, output_path, context=None):
        raise MediaError("No actual AI video API is configured. Upload a generated MP4 instead.")


class ProceduralMotionProvider(BaseVideoProvider):
    """Explicit demonstration only. Never part of automatic footage fallback."""
    def __init__(self):
        super().__init__("procedural", "Demo gradient (not footage)")

    def is_available(self, context=None):
        return bool((context or {}).get("allow_photo_motion"))

    def generate_clip(self, scene, output_path, context=None):
        if not self.is_available(context):
            raise MediaError("Demo backgrounds require explicit opt-in.")
        duration = max(0.5, min(60.0, float(scene.get("duration_estimate_sec", 5))))
        run_checked([
            executable("ffmpeg"), "-nostdin", "-y", "-v", "error", "-f", "lavfi",
            "-i", "gradients=s=1080x1920:rate=30:c0=0x0F172A:c1=0x00F2FE:type=radial:speed=0.05",
            "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-threads", "2",
            "-pix_fmt", "yuv420p", str(output_path),
        ], timeout=max(120, duration * 20))
        return output_path


class WikimediaCommonsProvider(BaseVideoProvider):
    """Completely free open public domain media repository. Zero API key required."""
    def __init__(self):
        super().__init__("wikimedia", "Wikimedia Commons (Free Public Domain)")

    def is_available(self, context=None):
        return True

    def generate_clip(self, scene, output_path, context=None):
        query = str(scene.get("search_keyword", "")).strip() or "historic landscape"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "format": "json",
            "gsrlimit": 5
        }
        headers = {"User-Agent": "ShortsGeniusReels/2.0 (studio@shortsgenius.app)"}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=(5, 15))
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    info = page.get("imageinfo", [{}])[0]
                    img_url = info.get("url")
                    if img_url and img_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        dl = requests.get(img_url, headers=headers, timeout=(5, 20))
                        if dl.status_code == 200:
                            img_path = output_path.with_suffix(".jpg")
                            img_path.write_bytes(dl.content)
                            return img_path
        except Exception:
            pass
        return None


def unsplash_key(context=None):
    from ..config import UNSPLASH_ACCESS_KEY
    return (context or {}).get("unsplash_access_key") or os.getenv("UNSPLASH_ACCESS_KEY", UNSPLASH_ACCESS_KEY)


class UnsplashProvider(BaseVideoProvider):
    """High resolution photography with free developer API key."""
    def __init__(self):
        super().__init__("unsplash", "Unsplash Stock Visuals")

    def is_available(self, context=None):
        return bool(unsplash_key(context))

    def generate_clip(self, scene, output_path, context=None):
        key = unsplash_key(context)
        if not key:
            raise MediaError("Unsplash Access Key is missing.")
        query = str(scene.get("search_keyword", "")).strip() or "cinematic"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {"Authorization": f"Client-ID {key}"}
        params = {"query": query, "orientation": "portrait", "per_page": 5}
        try:
            res = requests.get("https://api.unsplash.com/search/photos", params=params, headers=headers, timeout=(5, 15))
            if res.status_code == 200:
                results = res.json().get("results", [])
                for item in results:
                    img_url = item.get("urls", {}).get("regular") or item.get("urls", {}).get("full")
                    if img_url:
                        dl = requests.get(img_url, timeout=(5, 20))
                        if dl.status_code == 200:
                            img_path = output_path.with_suffix(".jpg")
                            img_path.write_bytes(dl.content)
                            return img_path
        except Exception as exc:
            raise MediaError(f"Unsplash error: {exc}")
        return None


class VideoProviderRouter:
    def __init__(self):
        self.providers = {provider.provider_id: provider for provider in (
            CustomUploadProvider(), PexelsVideoProvider(), PixabayVideoProvider(),
            UnsplashProvider(), WikimediaCommonsProvider(), CuratedStockProvider(),
            GenerativeAIVideoProvider(), ProceduralMotionProvider(),
        )}

    def list_available_providers(self, context=None):
        return [{"id": key, "name": provider.name,
                 "is_available": provider.is_available(context)}
                for key, provider in self.providers.items()]

    def resolve_scene_clip(self, scene, output_path, scene_index, preferred_provider=None,
                           custom_clips=None, pexels_api_key=None, used_clips=None,
                           allow_photo_motion=False, trace=None, pixabay_api_key=None):
        number = scene.get("scene_number", scene_index + 1)
        context = {"scene_key": f"scene_{number}", "custom_clips": custom_clips or {},
                   "pexels_api_key": pexels_api_key, "pixabay_api_key": pixabay_api_key,
                   "allow_photo_motion": allow_photo_motion,
                   "used_clips": used_clips if used_clips is not None else set()}
        trace = trace if trace is not None else []

        def validate(path):
            if not path:
                raise MediaError("No matching usable footage found.")
            if source_kind(path) in {"photo_motion", "procedural"} and not allow_photo_motion:
                raise MediaError("This is a photo-animation demo. Upload footage or explicitly allow photo motion.")
            probe_media(path, require_video=True, decode=True)
            return Path(path)

        if self.providers["upload"].is_available(context):
            # A broken manual choice is an error; never silently replace the user's clip.
            clip = validate(self.providers["upload"].generate_clip(scene, output_path, context))
            trace.append({"scene_number": number, "provider": "upload", "status": "selected",
                          "file": clip.name, "kind": source_kind(clip)})
            return clip, self.providers["upload"].name

        preferred = (preferred_provider or "auto").strip().lower()
        if preferred not in {"auto", *self.providers.keys()}:
            raise MediaError(f"Unknown video provider: {preferred}")
        order = ["pexels", "pixabay", "unsplash", "wikimedia", "curated"] if preferred == "auto" else [preferred]
        failures = []
        for key in order:
            provider = self.providers[key]
            try:
                if not provider.is_available(context):
                    raise MediaError(f"{provider.name} is not configured or has no assets.")
                clip = validate(provider.generate_clip(scene, output_path, context))
                selected = {"scene_number": number, "provider": key, "status": "selected",
                            "file": clip.name, "kind": source_kind(clip)}
                if key in {"pexels", "pixabay"}:
                    selected["kind"] = "stock_video"
                    metadata = clip.with_suffix(".source.json")
                    if metadata.is_file():
                        try:
                            source = json.loads(metadata.read_text(encoding="utf-8"))
                            for field in ("source_url", "creator", "video_id", "width", "height", "reused", "query"):
                                if field in source:
                                    selected[field] = source[field]
                        except (ValueError, OSError):
                            pass
                trace.append(selected)
                return clip, provider.name
            except (MediaError, requests.RequestException, OSError, ValueError) as exc:
                failures.append(str(exc))
                trace.append({"scene_number": number, "provider": key, "status": "failed", "reason": str(exc)})
        raise MediaError(f"Scene {number} has no usable footage. Upload a clip or choose a configured "
                         "source. " + " | ".join(failures))


ROUTER = VideoProviderRouter()
