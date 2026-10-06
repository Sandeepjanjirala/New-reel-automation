"""Validated, CPU-based FFmpeg renderer. A final filename means validation passed."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional
from PIL import Image

from ..config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, OUTPUT_DIR, MUSIC_DIR
from .subtitle_engine import build_karaoke_ass_script
from .media_tools import (MediaError, check_tools, executable, probe_media,
                          run_checked, safe_child, validate_final, validate_job_id)


def compose_final_video(
    scenes: list[dict[str, Any]], voice_data: list[dict[str, Any]],
    visual_paths: list[str], music_track_name: Optional[str] = None,
    project_id: str = "demo", subtitle_style: str = "hormozi_gold",
    subtitle_position: str = "bottom_safe", subtitle_format: str = "roman",
) -> Path:
    validate_job_id(project_id)
    if not scenes or not (len(scenes) == len(voice_data) == len(visual_paths)):
        raise MediaError("Scene, audio and visual counts must be equal and non-zero.")
    check_tools()
    ffmpeg = executable("ffmpeg")
    work = (OUTPUT_DIR / "jobs" / project_id).resolve()
    work.mkdir(parents=True, exist_ok=True)
    log = work / "ffmpeg.log"
    final = OUTPUT_DIR / f"{project_id}_final.mp4"
    pending = work / "validated_pending.mp4"
    manifest = {"job_id": project_id, "scenes": [], "validated": False}
    clips: list[Path] = []
    expected_duration = 0.0

    for index, (scene, voice, visual) in enumerate(zip(scenes, voice_data, visual_paths), 1):
        source = Path(visual).resolve()
        audio = Path(voice["audio_path"]).resolve()
        audio_info = probe_media(audio, require_audio=True, decode=True)
        # Audio is the timeline source of truth, not an estimated script duration.
        duration = math.ceil(audio_info["duration"] * VIDEO_FPS) / VIDEO_FPS
        if duration > 180:
            raise MediaError(f"Scene {index} narration exceeds the 180-second limit.")
        is_image = source.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        if is_image:
            try:
                with Image.open(source) as image:
                    image.verify()
            except Exception as exc:
                raise MediaError(f"Invalid image for scene {index}: {source.name}") from exc
        else:
            # Container/stream inspection also correctly handles .mkv uploads.
            probe_media(source, require_video=True, decode=True)
        subtitle = work / f"sub_{index:03d}.ass"
        build_karaoke_ass_script(
            words=voice.get("words", []), narration=scene.get("narration", ""),
            duration=duration, output_path=subtitle, style_id=subtitle_style,
            position_id=subtitle_position, roman_text=scene.get("roman_subtitles"),
            script_format=subtitle_format,
        )
        vf = (f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase:in_range=auto:out_range=tv,"
              f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1")
        if is_image:
            vf += (f",zoompan=z='min(1+on*0.0015,1.2)':d=1:"
                   f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
                   f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}")
        # A safe relative subtitle filename avoids Windows drive/space escaping bugs.
        vf += f",fps={VIDEO_FPS},setpts=PTS-STARTPTS,format=yuv420p,ass='{subtitle.name}'"
        scene_out = work / f"scene_{index:03d}.mp4"
        command = [ffmpeg, "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
                   "-filter_threads", "2"]
        command += ["-loop", "1"] if is_image else ["-stream_loop", "-1"]
        command += ["-i", str(source), "-i", str(audio),
                    "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration),
                    "-vf", vf, "-af", "aresample=48000,apad,asetpts=PTS-STARTPTS",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-threads", "2", "-pix_fmt", "yuv420p", "-color_range", "tv", "-r", str(VIDEO_FPS),
                    "-video_track_timescale", "90000", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(scene_out)]
        run_checked(command, timeout=max(120, duration * 20), log_path=log, cwd=work)
        validate_final(scene_out, duration, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS)
        clips.append(scene_out)
        expected_duration += duration
        manifest["scenes"].append({"scene_number": scene.get("scene_number", index),
                                   "visual": str(source), "audio": str(audio),
                                   "duration": duration, "image_animation": is_image})
        (work / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    playlist = work / "concat.txt"
    playlist.write_text("".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
    raw = work / "assembled.mp4"
    run_checked([
        ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "1",
        "-i", str(playlist), "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
        "-movflags", "+faststart", str(raw),
    ], timeout=max(90, expected_duration * 3), log_path=log, cwd=work)

    if music_track_name and music_track_name != "none":
        music = safe_child(MUSIC_DIR, music_track_name + ".mp3")
        probe_media(music, require_audio=True)
        mix = ("[0:a]asplit=2[voice][side];"
               "[1:a]aresample=48000,volume=0.15[bed];"
               "[bed][side]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=250[ducked];"
               "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
               "alimiter=limit=0.95[a]")
        run_checked([
            ffmpeg, "-nostdin", "-y", "-v", "error", "-filter_complex_threads", "2",
            "-i", str(raw), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex", mix, "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", str(expected_duration), "-movflags", "+faststart", str(pending),
        ], timeout=max(120, expected_duration * 4), log_path=log)
    else:
        raw.replace(pending)

    checked = validate_final(pending, expected_duration, VIDEO_WIDTH, VIDEO_HEIGHT,
                             VIDEO_FPS, full_decode=True, log_path=log)
    manifest.update({"validated": True, "duration": checked["duration"],
                     "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT, "fps": VIDEO_FPS,
                     "output": final.name})
    (work / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Atomic publication: incomplete outputs are never listed as completed reels.
    pending.replace(final)
    for clip in clips:
        clip.unlink(missing_ok=True)
    raw.unlink(missing_ok=True)
    # ASS files and diagnostics deliberately remain available after success/failure.
    return final
