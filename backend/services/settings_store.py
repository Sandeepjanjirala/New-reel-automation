"""Update only requested API keys, preserving existing FFmpeg and other settings."""
from __future__ import annotations

import os
import re
import threading
import uuid
from pathlib import Path

_ALLOWED_KEYS = {"PIXABAY_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY"}
_LOCK = threading.Lock()


def validate_key(value: str) -> str:
    value = value.strip()
    if len(value) > 512 or any(c.isspace() or c in "\x00#'\"\\" for c in value):
        raise ValueError("API keys must be a single value without spaces, quotes or line breaks.")
    return value


def update_env_keys(path: Path, updates: dict[str, str]) -> None:
    """Atomic update, no rewriting unrelated values or erasing unsubmitted keys."""
    if not updates:
        return
    if not set(updates).issubset(_ALLOWED_KEYS):
        raise ValueError("Only API key settings can be changed here.")
    updates = {name: validate_key(value) for name, value in updates.items()}
    path = Path(path)
    with _LOCK:
        original = path.read_bytes() if path.exists() else b""
        bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
        text = original.decode("utf-8-sig")
        newline = "\r\n" if "\r\n" in text else "\n"
        lines, seen = [], set()
        for line in text.splitlines(keepends=True):
            match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            name = match.group(1) if match else None
            if name in updates:
                if name not in seen:
                    lines.append(f"{name}={updates[name]}{newline}")
                    seen.add(name)
                # Remove duplicate definitions of just the updated keys.
            else:
                lines.append(line)
        content = "".join(lines)
        for name, value in updates.items():
            if name not in seen:
                if content and not content.endswith(("\n", "\r")):
                    content += newline
                content += f"{name}={value}{newline}"
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            # Restrictive permissions on Unix. Windows inherits the folder ACL.
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(bom + content.encode("utf-8"))
            if path.exists() and os.name != "nt":
                os.chmod(temporary, path.stat().st_mode & 0o777)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
