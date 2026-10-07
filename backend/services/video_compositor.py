"""Validated, multi-threaded CPU/GPU-ready FFmpeg renderer. A final filename means validation passed."""
from __future__ import annotations

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
from PIL import Image

from ..config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, OUTPUT_DIR, MUSIC_DIR
from .subtitle_engine import build_karaoke_ass_script
from .media_tools import (MediaError, check_tools, detect_best_encoder, executable,
                          probe_media, run_checked, safe_child, validate_final, validate_job_id)


def _render_single_scene_worker(
    index: int, scene: dict[str, Any], voice: dict[str, Any], visual: str,
    work: Path, ffmpeg: str, subtitle_style: str, subtitle_position: str,
    subtitle_format: str
) -> tuple[int, Path, float, dict[str, Any]]:
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
        probe_media(source, require_video=True, decode=True)

    subtitle = work / f"sub_{index:03d}.ass"
    build_karaoke_ass_script(
        words=voice.get("words", []), narration=scene.get("narration", ""),
        duration=duration, output_path=subtitle, style_id=subtitle_style,
        position_id=subtitle_position, roman_text=scene.get("roman_subtitles"),
        script_format=subtitle_format,
    )

    scale_filter = (f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase:in_range=auto:out_range=tv,"
                    f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1")
    motion_mode = index % 2
    if is_image:
        if motion_mode == 0:
            motion_filter = (f",zoompan=z='min(zoom+0.0015,1.15)':"
                             f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
                             f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}")
        else:
            motion_filter = (f",zoompan=z='min(1.0+on*0.0006,1.07)':"
                             f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                             f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}")
    else:
        # Kinetic push-in on even scenes, pull-out on odd scenes for professional Gen Z video pacing
        if motion_mode == 0:
            motion_filter = (f",zoompan=z='min(zoom+0.0012,1.14)':d=1:"
                             f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                             f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}")
        else:
            motion_filter = (f",zoompan=z='if(lte(zoom,1.0),1.12,max(1.001,zoom-0.0012))':d=1:"
                             f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                             f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}")

    # Pro Instagram Reel Grade: Enhanced contrast + saturation pop + subtle corner vignette
    cinematic_grade = ",eq=contrast=1.06:brightness=0.01:saturation=1.14,vignette=angle=PI/24:mode=forward"

    ass_path = str(subtitle).replace("\\", "/").replace(":", "\\:")
    vf = f"{scale_filter}{motion_filter}{cinematic_grade},ass='{ass_path}'"
    af_vocal = "aresample=48000,apad,asetpts=PTS-STARTPTS"
    scene_out = work / f"scene_{index:03d}.mp4"

    encoder_info = detect_best_encoder()
    enc_args = encoder_info["args"]
    command = [ffmpeg, "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
               "-filter_threads", "2"]
    command += ["-loop", "1"] if is_image else ["-stream_loop", "-1"]
    command += ["-i", str(source), "-i", str(audio),
                "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration),
                "-vf", vf, "-af", af_vocal]
    command += enc_args
    command += ["-color_range", "tv", "-r", str(VIDEO_FPS),
                "-video_track_timescale", "90000", "-c:a", "aac", "-b:a", "192k",
                "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(scene_out)]
    log = work / f"ffmpeg_scene_{index:03d}.log"

    try:
        run_checked(command, timeout=max(120, duration * 20), log_path=log, cwd=work)
    except MediaError:
        if encoder_info.get("is_hardware"):
            # Automatic resilient fallback to CPU libx264
            fb_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "2", "-pix_fmt", "yuv420p"]
            fb_cmd = [ffmpeg, "-nostdin", "-y", "-hide_banner", "-loglevel", "error", "-filter_threads", "2"]
            fb_cmd += ["-loop", "1"] if is_image else ["-stream_loop", "-1"]
            fb_cmd += ["-i", str(source), "-i", str(audio),
                       "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration),
                       "-vf", vf, "-af", af_vocal]
            fb_cmd += fb_args + ["-color_range", "tv", "-r", str(VIDEO_FPS),
                                 "-video_track_timescale", "90000", "-c:a", "aac", "-b:a", "192k",
                                 "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(scene_out)]
            run_checked(fb_cmd, timeout=max(120, duration * 20), log_path=log, cwd=work)
        else:
            raise

    validate_final(scene_out, duration, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS)
    
    manifest_entry = {
        "scene_number": scene.get("scene_number", index),
        "visual": str(source), "audio": str(audio),
        "duration": duration, "image_animation": is_image
    }
    return index, scene_out, duration, manifest_entry


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

    # Parallelize scene rendering with ThreadPoolExecutor
    max_workers = min(4, max(1, os.cpu_count() or 2), len(scenes))
    results = [None] * len(scenes)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _render_single_scene_worker,
                index=idx + 1,
                scene=scenes[idx],
                voice=voice_data[idx],
                visual=visual_paths[idx],
                work=work,
                ffmpeg=ffmpeg,
                subtitle_style=subtitle_style,
                subtitle_position=subtitle_position,
                subtitle_format=subtitle_format,
            )
            for idx in range(len(scenes))
        ]
        for future in as_completed(futures):
            idx, scene_out, duration, entry = future.result()
            results[idx - 1] = (scene_out, duration, entry)

    clips = [r[0] for r in results]
    expected_duration = sum(r[1] for r in results)
    manifest["scenes"] = [r[2] for r in results]
    (work / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Instant Stream-Copy Concat Demuxer
    playlist = work / "concat.txt"
    playlist.write_text("".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
    raw = work / "assembled.mp4"
    run_checked([
        ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "1",
        "-i", str(playlist), "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
        "-movflags", "+faststart", str(raw),
    ], timeout=max(90, expected_duration * 3), log_path=log, cwd=work)

    # Dynamic Audio Sidechain Ducking & Studio Mastering (Phase 4)
    if music_track_name and music_track_name != "none":
        music = safe_child(MUSIC_DIR, music_track_name + ".mp3")
        probe_media(music, require_audio=True)
        # Studio audio chain: vocal isolation + sidechain compression + master peak limiter
        mix = ("[0:a]asplit=2[voice][side];"
               "[1:a]aresample=48000,volume=0.18,highpass=f=30,lowpass=f=15000[bed];"
               "[bed][side]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=280:link=average[ducked];"
               "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
               "alimiter=limit=0.92:attack=5:release=50:asc=1[a]")
        run_checked([
            ffmpeg, "-nostdin", "-y", "-v", "error", "-filter_complex_threads", "2",
            "-i", str(raw), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex", mix, "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", str(expected_duration), "-movflags", "+faststart", str(pending),
        ], timeout=max(120, expected_duration * 4), log_path=log)
    else:
        # Master limiter for vocal-only reels
        run_checked([
            ffmpeg, "-nostdin", "-y", "-v", "error",
            "-i", str(raw), "-af", "aresample=48000,alimiter=limit=0.92:attack=5:release=50:asc=1",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", str(expected_duration), "-movflags", "+faststart", str(pending),
        ], timeout=max(120, expected_duration * 4), log_path=log)

    checked = validate_final(pending, expected_duration, VIDEO_WIDTH, VIDEO_HEIGHT,
                             VIDEO_FPS, full_decode=True, log_path=log)
    manifest.update({"validated": True, "duration": checked["duration"],
                     "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT, "fps": VIDEO_FPS,
                     "output": final.name})
    (work / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    # Atomic publication
    pending.replace(final)
    for clip in clips:
        clip.unlink(missing_ok=True)
    raw.unlink(missing_ok=True)
    return final

