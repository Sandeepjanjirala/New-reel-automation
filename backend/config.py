import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
ASSETS_DIR = BASE_DIR / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
FONTS_DIR = ASSETS_DIR / "fonts"
VIDEOS_DIR = ASSETS_DIR / "videos"
OUTPUT_DIR = BASE_DIR / "output"

# Ensure runtime directories exist
for folder in [ASSETS_DIR, MUSIC_DIR, FONTS_DIR, VIDEOS_DIR, OUTPUT_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Load environment
load_dotenv(PROJECT_ROOT / ".env")

# Video Format Specifications (9:16 Vertical Video)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

# Available Neural Voices (Free, Zero API key required via Edge-TTS)
AVAILABLE_VOICES = {
    "mohan": {
        "id": "te-IN-MohanNeural",
        "name": "Mohan (Telugu Authoritative Male)",
        "language": "te-IN",
        "gender": "male",
        "style": "tech"
    },
    "shruti": {
        "id": "te-IN-ShrutiNeural",
        "name": "Shruti (Telugu Engaging Female)",
        "language": "te-IN",
        "gender": "female",
        "style": "storytelling"
    },
    "christopher": {
        "id": "en-US-ChristopherNeural",
        "name": "Christopher (Authoritative Male)",
        "language": "en-US",
        "gender": "male",
        "style": "documentary"
    },
    "guy": {
        "id": "en-US-GuyNeural",
        "name": "Guy (Energetic Male)",
        "language": "en-US",
        "gender": "male",
        "style": "hype"
    },
    "jenny": {
        "id": "en-US-JennyNeural",
        "name": "Jenny (Clear & Engaging Female)",
        "language": "en-US",
        "gender": "female",
        "style": "storytelling"
    },
    "aria": {
        "id": "en-US-AriaNeural",
        "name": "Aria (Dynamic & Expressive Female)",
        "language": "en-US",
        "gender": "female",
        "style": "modern"
    },
    "ryan": {
        "id": "en-GB-RyanNeural",
        "name": "Ryan (Sophisticated British)",
        "language": "en-GB",
        "gender": "male",
        "style": "intellectual"
    }
}

DEFAULT_VOICE = "te-IN-MohanNeural"

# API Keys (Optional with built-in intelligent fallbacks)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
