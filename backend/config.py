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
        "name": "Mohan (Telugu Natural Male)",
        "language": "te-IN",
        "gender": "male",
        "style": "authoritative"
    },
    "shruti": {
        "id": "te-IN-ShrutiNeural",
        "name": "Shruti (Telugu Natural Female)",
        "language": "te-IN",
        "gender": "female",
        "style": "storytelling"
    },
    "andrew": {
        "id": "en-US-AndrewNeural",
        "name": "Andrew (Conversational Warm Male - Ultra Natural)",
        "language": "en-US",
        "gender": "male",
        "style": "conversational"
    },
    "ava": {
        "id": "en-US-AvaNeural",
        "name": "Ava (Expressive Natural Female - Ultra Natural)",
        "language": "en-US",
        "gender": "female",
        "style": "warm"
    },
    "aria": {
        "id": "en-US-AriaNeural",
        "name": "Aria (Dynamic & Expressive Female)",
        "language": "en-US",
        "gender": "female",
        "style": "modern"
    },
    "brian": {
        "id": "en-US-BrianNeural",
        "name": "Brian (Casual Authentic Young Male)",
        "language": "en-US",
        "gender": "male",
        "style": "casual"
    },
    "emma": {
        "id": "en-US-EmmaNeural",
        "name": "Emma (Friendly Storyteller Female)",
        "language": "en-US",
        "gender": "female",
        "style": "storytelling"
    },
    "christopher": {
        "id": "en-US-ChristopherNeural",
        "name": "Christopher (Authoritative Documentary Male)",
        "language": "en-US",
        "gender": "male",
        "style": "documentary"
    },
    "jenny": {
        "id": "en-US-JennyNeural",
        "name": "Jenny (Clear & Engaging Female)",
        "language": "en-US",
        "gender": "female",
        "style": "podcast"
    },
    "guy": {
        "id": "en-US-GuyNeural",
        "name": "Guy (Energetic & Punchy Male)",
        "language": "en-US",
        "gender": "male",
        "style": "hype"
    },
    "eric": {
        "id": "en-US-EricNeural",
        "name": "Eric (Calm & Informative Male)",
        "language": "en-US",
        "gender": "male",
        "style": "calm"
    },
    "ryan": {
        "id": "en-GB-RyanNeural",
        "name": "Ryan (Sophisticated British Male)",
        "language": "en-GB",
        "gender": "male",
        "style": "intellectual"
    },
    "sonia": {
        "id": "en-GB-SoniaNeural",
        "name": "Sonia (Polished British Female)",
        "language": "en-GB",
        "gender": "female",
        "style": "elegant"
    },
    "neerja": {
        "id": "en-IN-NeerjaNeural",
        "name": "Neerja (Natural Indian English Female)",
        "language": "en-IN",
        "gender": "female",
        "style": "warm"
    },
    "prabhat": {
        "id": "en-IN-PrabhatNeural",
        "name": "Prabhat (Natural Indian English Male)",
        "language": "en-IN",
        "gender": "male",
        "style": "confident"
    },
    "swara": {
        "id": "hi-IN-SwaraNeural",
        "name": "Swara (Natural Hindi Female)",
        "language": "hi-IN",
        "gender": "female",
        "style": "expressive"
    },
    "madhur": {
        "id": "hi-IN-MadhurNeural",
        "name": "Madhur (Natural Hindi Male)",
        "language": "hi-IN",
        "gender": "male",
        "style": "conversational"
    }
}

DEFAULT_VOICE = "te-IN-ShrutiNeural"

# API Keys (Optional with built-in intelligent fallbacks)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
