"""Render three seconds of a local clip + captions + silent audio; no API calls."""
import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import OUTPUT_DIR
from backend.services.media_tools import executable, run_checked, validate_final
from backend.services.video_compositor import compose_final_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", type=Path, required=True, help="Existing local MP4/MOV/WEBM/MKV")
    args = parser.parse_args()
    clip = args.clip.expanduser().resolve()
    if not clip.is_file():
        parser.error("--clip must point to an existing video")
    job = "smoke_" + uuid.uuid4().hex[:8]
    audio = OUTPUT_DIR / f"{job}.wav"
    run_checked([executable("ffmpeg"), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                 "anullsrc=r=48000:cl=stereo", "-t", "3", str(audio)])
    try:
        words = [{"word": word, "start": i * 0.6, "end": (i + 1) * 0.6}
                 for i, word in enumerate("OFFLINE VIDEO LAYER CHECK PASSED".split())]
        final = compose_final_video(
            [{"scene_number": 1, "narration": "Offline video layer check passed",
              "roman_subtitles": "Offline video layer check passed"}],
            [{"audio_path": str(audio), "words": words, "duration": 3}],
            [str(clip)], project_id=job)
        info = validate_final(final, expected_duration=3, full_decode=True)
        print(f"PASS: {final}")
        print(f"1080x1920, 30 fps, video + silent diagnostic audio, {info['duration']:.3f}s")
        print("This tests rendering only, not Edge-TTS or stock/AI APIs.")
    finally:
        audio.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
