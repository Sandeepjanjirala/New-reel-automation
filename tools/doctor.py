"""Local diagnostics. Prints key presence only, never credential values."""
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import config
from backend.services.media_tools import check_tools, probe_media, MediaError
from backend.services.video_providers import source_kind


def main():
    report = {"python": sys.version.split()[0], "platform": platform.platform(),
              "project_root": str(ROOT), "keys": {
                  "pexels_present": bool(os.getenv("PEXELS_API_KEY", "")),
                  "pixabay_present": bool(os.getenv("PIXABAY_API_KEY", "")),
                  "gemini_present": bool(os.getenv("GEMINI_API_KEY", ""))},
              "media_tools": {}, "packages": {}, "library": [], "warnings": []}
    ok = True
    try:
        report["media_tools"] = check_tools()
    except MediaError as exc:
        ok = False
        report["media_tools"] = {"ok": False, "error": str(exc)}
    for name in ("fastapi", "uvicorn", "edge-tts", "pydantic", "python-multipart"):
        try:
            report["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report["packages"][name] = "MISSING"
            ok = False
    for path in sorted(config.VIDEOS_DIR.glob("*.mp4")):
        row = {"file": path.name, "kind": source_kind(path)}
        if report["media_tools"].get("ok"):
            try:
                info = probe_media(path, require_video=True, decode=True)
                row.update(valid=True, duration=info["duration"], width=info["video"]["width"], height=info["video"]["height"])
            except MediaError as exc:
                row.update(valid=False, error=str(exc))
        report["library"].append(row)
    if not (report["keys"]["pexels_present"] or report["keys"]["pixabay_present"]):
        report["warnings"].append("No stock-video key. Add a Pixabay or Pexels key, upload clips, or use a relevant local footage library.")
    if not any(item["kind"] != "photo_motion" for item in report["library"]):
        report["warnings"].append("Bundled library has only photo-animation demos. They require explicit opt-in.")
    report["warnings"].append("No online provider connectivity was tested by this diagnostic.")
    report["ok"] = ok
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
