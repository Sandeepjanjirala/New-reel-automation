import sys
import uvicorn
from pathlib import Path

# Force UTF-8 stdout on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure both current directory and parent directory are on sys.path
CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

if __name__ == "__main__":
    print("=================================================================")
    print("[ShortsGenius] Starting AI Video Studio...")
    print("[ShortsGenius] Web Studio URL: http://127.0.0.1:8080")
    print("=================================================================")
    
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8080,
        reload=True
    )

