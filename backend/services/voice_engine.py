"""Speech generation with actual word boundaries and probed audio duration."""
from __future__ import annotations

import asyncio
import importlib
import re
from pathlib import Path
from typing import Any
from ..config import DEFAULT_VOICE, OUTPUT_DIR
from .media_tools import MediaError, probe_media, safe_child, validate_job_id


class WordTimestamp:
    def __init__(self, word: str, start_time: float, end_time: float):
        self.word, self.start_time, self.end_time = word, start_time, end_time

    def to_dict(self) -> dict[str, Any]:
        return {"word": self.word, "start": round(self.start_time, 3), "end": round(self.end_time, 3)}


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


async def synthesize_voice_with_timestamps(text: str, voice: str = DEFAULT_VOICE,
                                          output_filename: str = "voiceover.mp3"):
    if not text.strip():
        raise MediaError("Narration cannot be empty.")
    try:
        edge_tts = importlib.import_module("edge_tts")
    except ImportError as exc:
        raise MediaError("edge-tts is missing. Install requirements.txt in your virtual environment.") from exc
    path = safe_child(OUTPUT_DIR, output_filename)
    partial = path.with_suffix(".part.mp3")
    boundaries = []
    # Newer edge-tts defaults to sentence boundaries unless this is requested.
    communicator = edge_tts.Communicate(
        text, voice=voice, rate="+5%", boundary="WordBoundary",
        connect_timeout=10, receive_timeout=45,
    )

    async def receive():
        with partial.open("wb") as audio:
            async for chunk in communicator.stream():
                if chunk.get("type") == "audio":
                    audio.write(chunk.get("data", b""))
                elif chunk.get("type") == "WordBoundary":
                    start = float(chunk.get("offset", 0)) / 10_000_000
                    end = start + float(chunk.get("duration", 0)) / 10_000_000
                    boundaries.append((str(chunk.get("text", "")), start, end))

    try:
        await asyncio.wait_for(receive(), timeout=150)
        metadata = await asyncio.to_thread(probe_media, partial, require_audio=True, decode=True)
        duration = metadata["duration"]
        words = [WordTimestamp(word, max(0, start), min(duration, end))
                 for word, start, end in boundaries if word and start < duration and end > start]
        # Do not advertise guessed boundaries as exact. The subtitle engine can
        # distribute text over the measured duration when no boundaries arrive.
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    srt = "\n\n".join(
        f"{index}\n{_srt_time(word.start_time)} --> {_srt_time(word.end_time)}\n{word.word}"
        for index, word in enumerate(words, 1)
    )
    return path, words, duration, srt


def generate_scene_voices_sync(scenes, voice=DEFAULT_VOICE, project_id="demo"):
    return asyncio.run(_generate_scene_voices(scenes, voice, project_id))


async def _generate_scene_voices(scenes, voice=DEFAULT_VOICE, project_id="demo"):
    validate_job_id(project_id)
    result = []
    for index, scene in enumerate(scenes, 1):
        path, words, duration, srt = await synthesize_voice_with_timestamps(
            scene["narration"], voice, f"{project_id}_scene_{index}.mp3")
        result.append({"scene_number": scene.get("scene_number", index), "audio_path": str(path),
                       "words": [word.to_dict() for word in words], "duration": duration,
                       "srt": srt, "timing_source": "word_boundaries" if words else "estimated"})
    return result
