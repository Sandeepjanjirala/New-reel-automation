"""Pixabay stock footage for user-requested reels, not a video-generation model.

Official contract: https://pixabay.com/api/docs/#api_search_videos
Successful searches (including zero results) are cached for 24 hours. Queries
stay on the server; API keys are never put in diagnostics or cache documents.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import re
import requests

from .media_tools import MediaError, probe_media

API_URL = "https://pixabay.com/api/videos/"
CACHE_SECONDS = 24 * 60 * 60
MIN_REQUEST_INTERVAL = 0.7  # below the documented 100 requests/minute, per process
MAX_MEDIA_BYTES = 250 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 120
_REQUEST_LOCK = threading.RLock()
_LAST_REQUEST: dict[str, float] = {}
_COOLDOWN: dict[str, float] = {}


def _number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else default
    except (TypeError, ValueError):
        return default


def _trusted_url(value: str, *, media: bool = False) -> bool:
    try:
        parts = urlsplit(value)
        hosts = {"cdn.pixabay.com"} if media else {"pixabay.com", "www.pixabay.com"}
        return (parts.scheme == "https" and parts.hostname in hosts
                and parts.port in (None, 443) and not parts.username and not parts.password)
    except (ValueError, TypeError):
        return False


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class PixabayClient:
    def __init__(self, key: str, cache_dir: Path):
        self.key = (key or "").strip()
        self.cache_dir = Path(cache_dir)
        # This digest is used internally only, never a reversible key prefix.
        self._auth_id = hashlib.sha256(self.key.encode()).hexdigest()

    def search(self, query: str, *, per_page: int = 20) -> tuple[dict, bool]:
        """Return (API data, cache_hit). No unbounded paging or automated crawling."""
        if not self.key:
            raise MediaError("Pixabay API key is missing. Open API Keys & Sources to add it.")
        query = " ".join(str(query or "").split())
        if not query:
            raise MediaError("This scene needs an English stock-footage search keyword.")
        if len(query) > 100:
            raise MediaError("Pixabay search keywords must be 100 characters or fewer.")
        if not 3 <= per_page <= 20:
            raise MediaError("Pixabay request size must be between 3 and 20 results.")
        params = {"q": query, "per_page": per_page, "safesearch": "true", "lang": "en"}
        cache_id = hashlib.sha256((self._auth_id + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        cache = self.cache_dir / f"{cache_id}.json"
        # Serializing search requests also stops simultaneous identical queries.
        with _REQUEST_LOCK:
            try:
                saved = json.loads(cache.read_text(encoding="utf-8"))
                age = time.time() - float(saved["saved_at"])
                if 0 <= age < CACHE_SECONDS and isinstance(saved["data"].get("hits"), list):
                    return saved["data"], True
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                pass
            now = time.monotonic()
            cooldown = _COOLDOWN.get(self._auth_id, 0) - now
            if cooldown > 0:
                raise MediaError(f"Pixabay rate limit reached. Wait about {math.ceil(cooldown)} seconds or upload a clip.")
            delay = MIN_REQUEST_INTERVAL - (now - _LAST_REQUEST.get(self._auth_id, 0))
            if delay > 0:
                time.sleep(delay)
            try:
                _LAST_REQUEST[self._auth_id] = time.monotonic()
                with requests.get(API_URL, params={"key": self.key, **params},
                                  headers={"User-Agent": "ShortsGenius/Pixabay-Update"},
                                  timeout=(5, 25), allow_redirects=False) as response:
                    status = response.status_code
                    if status == 429:
                        headers = response.headers
                        wait = max(1.0, _number(headers.get("Retry-After"),
                                   _number(headers.get("X-RateLimit-Reset"), 60.0)))
                        _COOLDOWN[self._auth_id] = time.monotonic() + wait
                        raise MediaError(f"Pixabay rate limit reached. Wait about {math.ceil(wait)} seconds or upload a clip.")
                    if status in (400, 401, 403):
                        raise MediaError(f"Pixabay rejected the key or request (HTTP {status}). Check your Pixabay key and account access.")
                    if status != 200:
                        raise MediaError(f"Pixabay search returned HTTP {status}. Retry later or upload footage.")
                    data = response.json()
                    if not isinstance(data, dict) or not isinstance(data.get("hits"), list):
                        raise MediaError("Pixabay returned an unexpected response; no footage was selected.")
                    # Only retain fields needed for the integration. Never retain request URLs.
                    data = {"totalHits": int(_number(data.get("totalHits"))),
                            "hits": [h for h in data["hits"][:per_page] if isinstance(h, dict)]}
                    if str(response.headers.get("X-RateLimit-Remaining", "")) == "0":
                        _COOLDOWN[self._auth_id] = time.monotonic() + max(
                            1, _number(response.headers.get("X-RateLimit-Reset"), 60))
            except requests.Timeout:
                raise MediaError("Pixabay search timed out. Check your connection or upload footage.") from None
            except requests.RequestException:
                # requests exceptions may embed the URL, including the API key.
                raise MediaError("Cannot connect to Pixabay. Check your internet connection or upload footage.") from None
            except ValueError:
                raise MediaError("Pixabay returned invalid JSON; retry later or upload footage.") from None
            try:
                _write_json(cache, {"saved_at": time.time(), "data": data})
            except OSError:
                # Do not keep hitting the API when its mandatory cache cannot be stored.
                raise MediaError("Cannot save the Pixabay search cache. Check free disk space and output-folder permissions.") from None
            return data, False

    def _download(self, url: str, target: Path) -> dict:
        if not _trusted_url(url, media=True):
            raise MediaError("Pixabay returned an unsupported video-download host.")
        partial = target.with_name(target.name + "." + uuid.uuid4().hex + ".download")
        target.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + MAX_DOWNLOAD_SECONDS
        try:
            # Check redirect destinations before requesting them; do not permit arbitrary URLs.
            for _ in range(4):
                with requests.get(url, stream=True, timeout=(5, 30), allow_redirects=False) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers.get("Location", ""))
                        if not _trusted_url(url, media=True):
                            raise MediaError("Pixabay video redirected to an unsupported host.")
                        continue
                    if response.status_code != 200:
                        raise MediaError(f"Pixabay video download returned HTTP {response.status_code}.")
                    if _number(response.headers.get("Content-Length")) > MAX_MEDIA_BYTES:
                        raise MediaError("Pixabay video exceeds the 250 MB download limit.")
                    size = 0
                    with partial.open("wb") as output:
                        for chunk in response.iter_content(128 * 1024):
                            if time.monotonic() > deadline:
                                raise MediaError("Pixabay video download exceeded its time limit.")
                            if not chunk:
                                continue
                            size += len(chunk)
                            if size > MAX_MEDIA_BYTES:
                                raise MediaError("Pixabay video exceeds the 250 MB download limit.")
                            output.write(chunk)
                    info = probe_media(partial, require_video=True, decode=True)
                    if info["duration"] > 600:
                        raise MediaError("Pixabay video exceeds the 10-minute input limit.")
                    partial.replace(target)
                    return info
            raise MediaError("Too many Pixabay video-download redirects.")
        except requests.Timeout:
            raise MediaError("Pixabay video download timed out; retry later or upload a clip.") from None
        except requests.RequestException:
            raise MediaError("Pixabay video download failed; check your connection or upload a clip.") from None
        finally:
            partial.unlink(missing_ok=True)

    def fetch_scene(self, scene: dict, output_path: Path, used: set) -> Path:
        raw_query = " ".join(str(scene.get("search_keyword", "")).split())
        candidate_queries = [raw_query] if raw_query else []
        words = [w for w in re.findall(r'[a-zA-Z0-9]+', raw_query.lower()) if len(w) >= 3]
        if len(words) >= 3:
            candidate_queries.append(" ".join(words[:2]))
            candidate_queries.append(" ".join(words[-2:]))
        for w in words:
            if w not in {"the", "and", "for", "with", "from", "video", "footage", "clip"}:
                candidate_queries.append(w)

        # Contextual prompt keywords fallback
        v_prompt = str(scene.get("visual_prompt", "")).lower()
        prompt_words = [w for w in re.findall(r'[a-zA-Z]{4,}', v_prompt) if w not in {"cinematic", "atmospheric", "footage", "representing", "high", "production", "value", "scene"}]
        if prompt_words:
            candidate_queries.append(" ".join(prompt_words[:2]))
            candidate_queries.append(prompt_words[0])
            
        candidate_queries.extend(["cinematic aerial", "nature landscape", "city street night"])

        # Deduplicate while preserving priority order
        seen_queries = set()
        unique_queries = []
        for q in candidate_queries:
            q_clean = " ".join(q.split())
            if q_clean and q_clean not in seen_queries:
                seen_queries.add(q_clean)
                unique_queries.append(q_clean)

        errors = []
        for query in unique_queries:
            try:
                data, from_cache = self.search(query)
            except MediaError as me:
                errors.append(f"{query}: {me}")
                continue

            choices = []
            for rank, hit in enumerate(data.get("hits", [])):
                video_id = hit.get("id")
                if isinstance(video_id, bool) or not isinstance(video_id, int) or video_id < 1:
                    continue
                if _number(hit.get("duration")) > 600:
                    continue
                variants = []
                renditions = hit.get("videos")
                if not isinstance(renditions, dict):
                    continue
                for variant in renditions.values():
                    if not isinstance(variant, dict):
                        continue
                    width, height = _number(variant.get("width")), _number(variant.get("height"))
                    if width <= 0 or height <= 0 or not _trusted_url(variant.get("url", ""), media=True):
                        continue
                    if _number(variant.get("size")) > MAX_MEDIA_BYTES:
                        continue
                    # Select near-full-HD instead of blindly downloading 4K.
                    variants.append((abs(width * height - 1080 * 1920), variant))
                if not variants:
                    continue
                variant = min(variants, key=lambda v: v[0])[1]
                width, height = _number(variant["width"]), _number(variant["height"])
                # Prefer unused clips and vertical orientation if available
                score = (f"pixabay:{video_id}" in used, height < width, rank)
                choices.append((score, hit, variant))

            if not choices:
                continue

            for _, hit, variant in sorted(choices, key=lambda row: row[0])[:3]:
                target = Path(output_path)
                token = f"pixabay:{hit['id']}"
                try:
                    info = self._download(variant["url"], target)
                    source_url = str(hit.get("pageURL", ""))
                    if not _trusted_url(source_url):
                        source_url = f"https://pixabay.com/videos/id-{hit['id']}/"
                    metadata = {
                        "provider": "pixabay", "video_id": hit["id"], "source_url": source_url,
                        "creator": {"name": str(hit.get("user", "")), "id": hit.get("user_id")},
                        "query": query, "width": info["video"]["width"], "height": info["video"]["height"],
                        "duration": info["duration"], "reused": token in used,
                        "search_cached": from_cache, "license_url": "https://pixabay.com/service/license-summary/",
                    }
                    _write_json(target.with_suffix(".source.json"), metadata)
                    used.add(token)
                    return target
                except (MediaError, OSError) as exc:
                    target.unlink(missing_ok=True)
                    errors.append(str(exc))

        raise MediaError(f'No Pixabay video matched "{raw_query}" or fallback queries. ' + " | ".join(errors[:3]))
