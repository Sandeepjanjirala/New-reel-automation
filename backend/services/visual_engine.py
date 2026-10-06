import json
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
    paths, trace, used = [], [], set()
    work = OUTPUT_DIR / "jobs" / project_id
    work.mkdir(parents=True, exist_ok=True)
    try:
        for index, scene in enumerate(scenes):
            key = f"scene_{scene.get('scene_number', index + 1)}"
            path, provider = ROUTER.resolve_scene_clip(
                scene, work / f"broll_{index + 1:03d}.mp4", index,
                preferred_provider=(scene_providers or {}).get(key) or scene.get("provider"),
                custom_clips=custom_clips, pexels_api_key=pexels_api_key, used_clips=used,
                allow_photo_motion=allow_photo_motion, trace=trace, pixabay_api_key=pixabay_api_key,
            )
            paths.append(str(path))
    finally:
        (work / "visual_report.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
    return paths
