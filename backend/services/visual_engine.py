import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
from ..config import OUTPUT_DIR
from .video_providers import ROUTER
from .media_tools import validate_job_id


def generate_scene_visuals(scenes: list[dict[str, Any]], project_id: str = "demo",
                           pexels_api_key: Optional[str] = None,
                           custom_clips: Optional[dict[str, str]] = None,
                           scene_providers: Optional[dict[str, str]] = None,
                           allow_photo_motion: bool = False,
                           pixabay_api_key: Optional[str] = None) -> list[str]:
    validate_job_id(project_id)
    work = OUTPUT_DIR / "jobs" / project_id
    work.mkdir(parents=True, exist_ok=True)
    paths = [None] * len(scenes)
    trace = []
    used = set()
    lock = threading.Lock()

    def _resolve_scene(index: int, scene: dict[str, Any]):
        key = f"scene_{scene.get('scene_number', index + 1)}"
        scene_trace = []
        with lock:
            current_used = set(used)
        path, provider = ROUTER.resolve_scene_clip(
            scene, work / f"broll_{index + 1:03d}.mp4", index,
            preferred_provider=(scene_providers or {}).get(key) or scene.get("provider"),
            custom_clips=custom_clips, pexels_api_key=pexels_api_key, used_clips=current_used,
            allow_photo_motion=allow_photo_motion, trace=scene_trace, pixabay_api_key=pixabay_api_key,
        )
        with lock:
            used.update(current_used)
            trace.extend(scene_trace)
        return index, str(path)

    worker_count = min(6, max(1, len(scenes)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_resolve_scene, index, scene) for index, scene in enumerate(scenes)]
        for future in as_completed(futures):
            idx, p = future.result()
            paths[idx] = p

    (work / "visual_report.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
    return paths

