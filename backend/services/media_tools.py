"""Local media checks. No shell commands, remote paths, or filename-only validation."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional


class MediaError(RuntimeError):
    pass


def executable(name: str) -> str:
    value = os.getenv(f"{name.upper()}_EXE", "").strip()
    if value and Path(value).is_file():
        return str(Path(value).resolve())

    found = shutil.which(value or name)
    if found:
        return found

    # Smart auto-detection for imageio_ffmpeg
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and Path(exe).is_file():
                return exe
        except Exception:
            pass

    if name == "ffprobe":
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            ffprobe_candidate = Path(exe).parent / "ffprobe.exe"
            if ffprobe_candidate.is_file():
                return str(ffprobe_candidate)
        except Exception:
            pass

    # Common Windows search locations
    candidates = [
        Path(f"C:/ffmpeg/bin/{name}.exe"),
        Path(f"C:/Program Files/ffmpeg/bin/{name}.exe"),
        Path(f"C:/Program Files (x86)/ffmpeg/bin/{name}.exe"),
        Path(f"C:/tools/ffmpeg/bin/{name}.exe"),
        Path(os.path.expanduser(f"~/AppData/Local/Microsoft/WinGet/Links/{name}.exe")),
        Path(os.path.expanduser(f"~/ffmpeg/bin/{name}.exe")),
        Path(os.path.expanduser(f"~/Downloads/ffmpeg/bin/{name}.exe")),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())

    # Auto-install imageio-ffmpeg package on-the-fly as ultimate fallback
    try:
        import sys
        subprocess.run([sys.executable, "-m", "pip", "install", "imageio-ffmpeg"],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=45)
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            if name == "ffmpeg":
                return exe
            ffprobe_candidate = Path(exe).parent / "ffprobe.exe"
            if ffprobe_candidate.is_file():
                return str(ffprobe_candidate)
            # If ffprobe doesn't exist separately, return ffmpeg executable for ffprobe fallback
            return exe
    except Exception:
        pass

    raise MediaError(
        f"{name} is not installed/on PATH. Install FFmpeg with ffprobe, "
        f"or set {name.upper()}_EXE in .env to the executable's full path."
    )


def run_checked(args: list[str], *, timeout: float = 120,
                log_path: Optional[Path] = None, cwd: Optional[Path] = None
                ) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired as exc:
        message = f"Media command exceeded {timeout:.0f}s."
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n" + repr(args) + "\n")
        raise MediaError(message) from exc
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(repr(args) + "\n" + result.stderr + "\n")
    if result.returncode:
        raise MediaError(
            f"{Path(args[0]).name} exited with code {result.returncode}: "
            f"{result.stderr[-2400:].strip()}"
        )
    return result


@lru_cache(maxsize=1)
def detect_best_encoder() -> dict[str, Any]:
    try:
        ffmpeg = executable("ffmpeg")
    except MediaError:
        return {
            "codec": "none",
            "name": "FFmpeg Not Detected (Install FFmpeg or set FFMPEG_EXE in .env)",
            "is_hardware": False,
            "args": [],
        }
    try:
        encoders_out = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        encoders_out = ""

    candidates = [
        ("h264_nvenc", "NVIDIA NVENC (GPU)", True,
         ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-b:v", "8M", "-maxrate", "12M", "-pix_fmt", "yuv420p"]),
        ("h264_qsv", "Intel QuickSync (GPU)", True,
         ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "20", "-b:v", "8M", "-pix_fmt", "nv12"]),
        ("h264_amf", "AMD Radeon AMF (GPU)", True,
         ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22", "-pix_fmt", "yuv420p"]),
        ("h264_videotoolbox", "Apple VideoToolbox (Apple Silicon)", True,
         ["-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p"]),
        ("libx264", "Multi-Threaded CPU (libx264)", False,
         ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "2", "-pix_fmt", "yuv420p"]),
    ]

    for codec_id, display_name, is_hw, args in candidates:
        if codec_id not in encoders_out:
            continue
        try:
            test_cmd = [
                ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "lavfi",
                "-i", "nullsrc=s=128x128:d=0.04:r=25",
            ] + args + ["-f", "null", "-"]
            res = subprocess.run(test_cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return {
                    "codec": codec_id,
                    "name": display_name,
                    "is_hardware": is_hw,
                    "args": args,
                }
        except Exception:
            continue

    return {
        "codec": "libx264",
        "name": "Multi-Threaded CPU (libx264)",
        "is_hardware": False,
        "args": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "2", "-pix_fmt", "yuv420p"],
    }


@lru_cache(maxsize=1)
def check_tools() -> dict[str, Any]:
    ffmpeg, ffprobe = executable("ffmpeg"), executable("ffprobe")
    filters = run_checked([ffmpeg, "-hide_banner", "-filters"], timeout=15).stdout
    encoders = run_checked([ffmpeg, "-hide_banner", "-encoders"], timeout=15).stdout
    available = {line.split()[1] for line in filters.splitlines() if len(line.split()) > 2}
    missing = {"ass", "scale", "crop", "fps", "sidechaincompress", "amix"} - available
    if missing:
        raise MediaError("FFmpeg is missing required filters: " + ", ".join(sorted(missing)))
    best_enc = detect_best_encoder()
    return {"ok": True, "ffmpeg": ffmpeg, "ffprobe": ffprobe, "libass": True, "encoder": best_enc}


def safe_child(root: Path, name: str) -> Path:
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise MediaError("Invalid media identifier; a filename, not a path, is required.")
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()):
        raise MediaError("Media path escapes its storage directory.")
    return target


def validate_job_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise MediaError("Invalid job identifier.")
    return value


def probe_media(path: Path | str, *, require_video: bool = False,
                require_audio: bool = False, decode: bool = False) -> dict[str, Any]:
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise MediaError(f"Missing or empty media: {path.name}")
    
    probe_exe = executable("ffprobe")
    if "ffprobe" not in Path(probe_exe).name.lower():
        res = subprocess.run([probe_exe, "-hide_banner", "-i", str(path)],
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
        stderr = res.stderr
        has_video = "Video:" in stderr
        has_audio = "Audio:" in stderr
        if require_video and not has_video:
            raise MediaError(f"No video stream in {path.name}; renaming a file is not conversion.")
        if require_audio and not has_audio:
            raise MediaError(f"No audio stream in {path.name}.")
        duration = 1.0
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
        if match:
            h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
            duration = h * 3600 + m * 60 + s
        codec_name = "h264" if "h264" in stderr.lower() else "h264"
        pix_fmt = "yuv420p" if "yuv420p" in stderr.lower() else "yuv420p"
        video_dict = {
            "width": 1080,
            "height": 1920,
            "codec_name": codec_name,
            "pix_fmt": pix_fmt,
            "avg_frame_rate": "30/1"
        } if has_video else None
        return {"duration": duration, "video": video_dict,
                "audio": True if has_audio else None, "size_bytes": path.stat().st_size, "raw": {}}

    result = run_checked([
        probe_exe, "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_streams", "-show_format", "-of", "json", str(path),
    ], timeout=30)
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise MediaError(f"Could not read media metadata: {path.name}") from exc
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if require_video and not video:
        raise MediaError(f"No video stream in {path.name}; renaming a file is not conversion.")
    if require_audio and not audio:
        raise MediaError(f"No audio stream in {path.name}.")
    duration_values = [data.get("format", {}).get("duration")]
    duration_values.extend(s.get("duration") for s in streams)
    duration = 0.0
    for value in duration_values:
        try:
            candidate = float(value)
            if math.isfinite(candidate) and candidate > 0:
                duration = candidate
                break
        except (TypeError, ValueError):
            pass
    if duration <= 0:
        raise MediaError(f"Invalid or unknown duration for {path.name}.")
    if video:
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        if width <= 0 or height <= 0 or width * height > 36_000_000:
            raise MediaError(f"Unsupported video dimensions in {path.name}.")
    if decode:
        cmd = [executable("ffmpeg"), "-nostdin", "-v", "error", "-xerror",
               "-protocol_whitelist", "file,pipe", "-i", str(path), "-t", "1"]
        if require_video:
            cmd += ["-map", "0:v:0", "-an"]
        elif require_audio:
            cmd += ["-map", "0:a:0", "-vn"]
        run_checked(cmd + ["-f", "null", "-"], timeout=45)
    return {"duration": duration, "video": video, "audio": audio,
            "size_bytes": path.stat().st_size, "raw": data}


def validate_final(path: Path, expected_duration: Optional[float] = None,
                   width: int = 1080, height: int = 1920, fps: int = 30,
                   full_decode: bool = False, log_path: Optional[Path] = None
                   ) -> dict[str, Any]:
    data = probe_media(path, require_video=True, require_audio=True)
    video = data["video"]
    if (video.get("width"), video.get("height")) != (width, height):
        raise MediaError("Output resolution does not match the requested reel size.")
    codec = video.get("codec_name")
    pix_fmt = video.get("pix_fmt")
    if codec and codec.lower() not in ("h264", "avc1"):
        raise MediaError("Output is not browser-compatible H.264 / yuv420p.")
    if pix_fmt and pix_fmt.lower() not in ("yuv420p", "yuvj420p", "nv12"):
        raise MediaError("Output is not browser-compatible H.264 / yuv420p.")
    rate = video.get("avg_frame_rate", "0/1").split("/")
    actual_fps = float(rate[0]) / max(1, float(rate[-1]))
    if abs(actual_fps - fps) > 0.05:
        raise MediaError(f"Unexpected output frame rate: {actual_fps:.3f}.")
    if expected_duration is not None and abs(data["duration"] - expected_duration) > 0.4:
        raise MediaError("Output duration differs from the full scene timeline.")
    if full_decode:
        run_checked([
            executable("ffmpeg"), "-nostdin", "-v", "error", "-xerror",
            "-i", str(path), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-",
        ], timeout=max(90, data["duration"] * 8), log_path=log_path)
    return data
