import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

SUBTITLE_STYLES: Dict[str, Dict[str, Any]] = {
    "hormozi_gold": {
        "id": "hormozi_gold",
        "name": "Alex Hormozi (Viral Gold Pop)",
        "highlight_color": "&H00D7FF&",   # Vibrant Gold / Yellow (BGR format)
        "normal_color": "&HFFFFFF&",      # Pure White
        "outline_color": "&H00000000&",   # Solid Black Outline
        "shadow_color": "&H80000000&",    # Semi-transparent Black Shadow
        "font_size": 60,
        "outline_width": 5.5,
        "shadow_depth": 2.5,
        "scale_pop": 115,                 # 115% active word pop
        "sample_color": "#FFD700"
    },
    "mrbeast_yellow": {
        "id": "mrbeast_yellow",
        "name": "MrBeast (High-Voltage Neon)",
        "highlight_color": "&H00FFFF&",   # High-Voltage Neon Yellow
        "normal_color": "&HFFFFFF&",      # Pure White
        "outline_color": "&H00000000&",   # Pure Black Outline
        "shadow_color": "&H90000000&",    # Deep Black Shadow
        "font_size": 62,
        "outline_width": 6.0,
        "shadow_depth": 3.0,
        "scale_pop": 120,                 # 120% active word pop
        "sample_color": "#FFFF00"
    },
    "cyberpunk_cyan": {
        "id": "cyberpunk_cyan",
        "name": "Cyberpunk (Electric Cyan)",
        "highlight_color": "&HFFFF00&",   # Electric Cyan (BGR 0x00FFFF -> &HFFFF00&)
        "normal_color": "&HFFFFFF&",      # Pure White
        "outline_color": "&H00000000&",   # Deep Black
        "shadow_color": "&H80000000&",
        "font_size": 58,
        "outline_width": 5.0,
        "shadow_depth": 2.0,
        "scale_pop": 112,
        "sample_color": "#00F2FE"
    },
    "emerald_lime": {
        "id": "emerald_lime",
        "name": "Emerald Lime (Growth Hook)",
        "highlight_color": "&H00FF66&",   # Vibrant Emerald Lime
        "normal_color": "&HFFFFFF&",
        "outline_color": "&H00000000&",
        "shadow_color": "&H80000000&",
        "font_size": 58,
        "outline_width": 5.0,
        "shadow_depth": 2.0,
        "scale_pop": 112,
        "sample_color": "#00FF66"
    },
    "crimson_impact": {
        "id": "crimson_impact",
        "name": "Crimson Impact (Urgent Warning)",
        "highlight_color": "&H302EFF&",   # Vibrant Crimson Fire
        "normal_color": "&HFFFFFF&",
        "outline_color": "&H00000000&",
        "shadow_color": "&H90000000&",
        "font_size": 60,
        "outline_width": 5.5,
        "shadow_depth": 2.5,
        "scale_pop": 118,
        "sample_color": "#FF2E30"
    },
    "royal_purple": {
        "id": "royal_purple",
        "name": "Royal Violet (Neon Lavender)",
        "highlight_color": "&HFC84C0&",   # Neon Lavender (BGR for #C084FC)
        "normal_color": "&HFFFFFF&",
        "outline_color": "&H00000000&",
        "shadow_color": "&H80000000&",
        "font_size": 58,
        "outline_width": 5.0,
        "shadow_depth": 2.0,
        "scale_pop": 112,
        "sample_color": "#C084FC"
    },
    "clean_minimal": {
        "id": "clean_minimal",
        "name": "Clean Minimalist (Soft Gold)",
        "highlight_color": "&H00E6FF&",   # Soft Gold
        "normal_color": "&HFFFFFF&",
        "outline_color": "&H00000000&",
        "shadow_color": "&H60000000&",
        "font_size": 54,
        "outline_width": 3.5,
        "shadow_depth": 1.5,
        "scale_pop": 108,
        "sample_color": "#FFE600"
    }
}

POSITION_PRESETS: Dict[str, Dict[str, Any]] = {
    "bottom_safe": {
        "id": "bottom_safe",
        "name": "Instagram Safe Zone (Lower Third)",
        "alignment": 2,     # Bottom-Center
        "margin_v": 340,    # 340px above bottom to avoid Instagram UI overlays
        "description": "Safe from Reels description, sound title & engagement buttons"
    },
    "center_eye": {
        "id": "center_eye",
        "name": "Focal Center (Eye-Level)",
        "alignment": 5,     # Direct Screen Center
        "margin_v": 0,
        "description": "Centered directly at screen midpoint for high retention"
    },
    "upper_third": {
        "id": "upper_third",
        "name": "Upper Hook Zone (Top)",
        "alignment": 8,     # Top-Center
        "margin_v": 360,    # 360px below top notch
        "description": "Positioned at upper third, ideal for hook-first formats"
    }
}

# Contextual high-impact retention keyword to emoji mapping
KEYWORD_EMOJIS: Dict[str, str] = {
    "money": "💰", "cash": "💰", "dollar": "💵", "dollars": "💵", "rich": "🤑", "wealth": "💰",
    "profit": "📈", "crypto": "🪙", "bitcoin": "🪙", "crore": "💰", "lakh": "💰", "earn": "💸",
    "rocket": "🚀", "fast": "⚡", "launch": "🚀", "boost": "🚀", "speed": "⚡", "scale": "📈",
    "growth": "📈", "ai": "🧠", "artificial": "🧠", "intelligence": "🧠", "smart": "🧠",
    "brain": "🧠", "mind": "🧠", "idea": "💡", "think": "💡", "robot": "🤖", "computer": "💻",
    "code": "💻", "coding": "💻", "software": "💻", "server": "🖥️", "tech": "⚙️",
    "danger": "⚠️", "warning": "⚠️", "caution": "⚠️", "stop": "🛑", "risk": "⚠️",
    "mistake": "❌", "error": "❌", "never": "🚫", "worst": "⚠️", "alert": "🚨",
    "fire": "🔥", "hot": "🔥", "viral": "🔥", "trend": "🔥", "trending": "🔥", "secret": "🤫",
    "insane": "🤯", "crazy": "🤯", "win": "🏆", "winner": "🏆", "top": "🔝", "best": "⭐",
    "star": "⭐", "success": "🏆", "first": "🥇", "gold": "🥇", "love": "❤️", "heart": "❤️",
    "target": "🎯", "goal": "🎯", "focus": "🎯", "plan": "📋", "time": "⏱️", "clock": "⏱️",
    "hour": "⏳", "lock": "🔒", "unlock": "🔓", "100": "💯", "world": "🌍", "global": "🌍",
    "power": "⚡", "energy": "⚡", "electric": "⚡", "shield": "🛡️", "safe": "🛡️", "protect": "🛡️"
}


def get_contextual_emoji(word_str: str) -> Optional[str]:
    """
    Returns an appropriate contextual emoji if the word matches high-impact retention terms.
    """
    clean = re.sub(r'[^a-zA-Z0-9]', '', word_str).lower()
    if clean in KEYWORD_EMOJIS:
        return KEYWORD_EMOJIS[clean]
    # Check simple suffix stems
    for suffix in ("ing", "ed", "s", "es", "ly"):
        if clean.endswith(suffix) and len(clean) > len(suffix) + 2:
            stem = clean[:-len(suffix)]
            if stem in KEYWORD_EMOJIS:
                return KEYWORD_EMOJIS[stem]
    return None


def align_roman_words(spoken_words: List[Dict[str, Any]], roman_text: str, duration: float = 5.0) -> List[Dict[str, Any]]:
    """
    Aligns spoken word timestamps (from Edge-TTS) with Roman Telugu / English words.
    Returns words with Roman text and synchronized timestamps.
    """
    roman_words = [w.strip() for w in re.split(r'\s+', roman_text) if w.strip()]
    if not roman_words:
        return spoken_words

    if not spoken_words:
        total_chars = sum(len(w) for w in roman_words) or 1
        elapsed = 0.0
        result = []
        for word in roman_words:
            end = elapsed + duration * len(word) / total_chars
            result.append({"word": word.upper(), "start": elapsed, "end": min(duration, end)})
            elapsed = end
        return result

    total_start = spoken_words[0]["start"]
    total_end = spoken_words[-1]["end"]
    total_duration = max(0.5, total_end - total_start)

    # 1:1 match
    if len(spoken_words) == len(roman_words):
        result = []
        for sw, rw in zip(spoken_words, roman_words):
            result.append({"word": rw.upper(), "start": sw["start"], "end": sw["end"]})
        return result

    # Proportional character distribution
    total_chars = sum(len(w) for w in roman_words) or len(roman_words)
    curr_time = total_start
    result = []
    for w in roman_words:
        fraction = len(w) / total_chars
        w_dur = total_duration * fraction
        w_end = min(total_end, curr_time + w_dur)
        result.append({"word": w.upper(), "start": round(curr_time, 3), "end": round(w_end, 3)})
        curr_time = w_end
    return result


def build_karaoke_ass_script(
    words: List[Dict[str, Any]],
    narration: str,
    duration: float,
    output_path: Path,
    style_id: str = "hormozi_gold",
    position_id: str = "bottom_safe",
    roman_text: Optional[str] = None,
    script_format: str = "roman"
) -> Path:
    """
    Constructs an Advanced SubStation Alpha (.ass) subtitle file featuring
    Phase 3 Next-Gen kinetic bounce transforms, contextual emojis, and safe-zone enforcement.
    Specifically optimized for 1080x1920 vertical Instagram Reels and YouTube Shorts.
    """
    style = SUBTITLE_STYLES.get(style_id, SUBTITLE_STYLES["hormozi_gold"])
    pos = POSITION_PRESETS.get(position_id, POSITION_PRESETS["bottom_safe"])

    h_color = style["highlight_color"]
    n_color = style["normal_color"]
    out_color = style["outline_color"]
    shd_color = style["shadow_color"]
    f_size = style["font_size"]
    out_w = style["outline_width"]
    shd_d = style["shadow_depth"]
    scale_pop = style["scale_pop"]

    alignment = pos["alignment"]
    margin_v = pos["margin_v"]

    # Select typography based on script format
    font_name = "Arial Black"
    active_words = words

    if script_format == "roman":
        font_name = "Arial Black"
        f_size = style["font_size"] + 6  # 64-68px for punchy uppercase text
        if roman_text and roman_text.strip():
            active_words = align_roman_words(words, roman_text.strip(), duration)
        elif words:
            try:
                from .script_generator import convert_telugu_to_roman
                roman_fallback = convert_telugu_to_roman(" ".join(w.get("word", "") for w in words))
                active_words = align_roman_words(words, roman_fallback, duration)
            except Exception:
                pass
    else:
        font_name = os.getenv("SUBTITLE_FONT_NATIVE", "Nirmala UI" if os.name == "nt" else "Noto Sans Telugu")
        f_size = style["font_size"]

    header = f"""[Script Info]
Title: ShortsGenius Kinetic Karaoke Subtitles (Phase 3)
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ReelStyle,{font_name},{f_size},&H00FFFFFF,&H000000FF,{out_color},{shd_color},-1,0,0,0,100,100,0,0,1,{out_w},{shd_d},{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines = []

    if active_words and len(active_words) > 0:
        # Group words into high-retention 3-word punchy chunks
        chunk_size = 3
        chunks = [active_words[i:i + chunk_size] for i in range(0, len(active_words), chunk_size)]

        for chunk in chunks:
            for word_idx, active_word in enumerate(chunk):
                w_start = max(0.0, float(active_word["start"]))
                w_end = min(duration, float(active_word["end"]))
                if w_start >= duration or w_end <= w_start:
                    continue

                if w_end <= w_start:
                    w_end = w_start + 0.25

                start_str = _format_ass_time(w_start)
                end_str = _format_ass_time(w_end)

                # Build line where the active word has kinetic elastic bounce + highlight color + contextual emoji
                line_parts = []
                for idx, w_obj in enumerate(chunk):
                    raw_word = str(w_obj["word"])
                    w_text = _safe_ass_text(raw_word)
                    emoji = get_contextual_emoji(raw_word)
                    emoji_str = f" {emoji}" if emoji else ""

                    if idx == word_idx:
                        # Active spoken word: Kinetic elastic pop transform (125% -> 115%) + Highlight Color
                        bounce_tag = f"\\t(0,75,\\fscx{scale_pop + 10}\\fscy{scale_pop + 10})\\t(75,150,\\fscx{scale_pop}\\fscy{scale_pop})"
                        line_parts.append(f"{{{bounce_tag}\\c{h_color}}}{w_text}{emoji_str}{{\\r}}")
                    else:
                        # Inactive word in current chunk: clean white with outline
                        line_parts.append(f"{{\\c{n_color}}}{w_text}{{\\r}}")

                formatted_text = " ".join(line_parts)
                dialogue_lines.append(f"Dialogue: 0,{start_str},{end_str},ReelStyle,,0,0,0,,{formatted_text}")
    elif narration and narration.strip():
        # Fallback if no word timestamps: display full sentence chunk with pop
        start_str = _format_ass_time(0.0)
        end_str = _format_ass_time(duration)
        text_clean = _safe_ass_text(roman_text.upper() if (script_format == "roman" and roman_text) else narration.strip())
        dialogue_lines.append(f"Dialogue: 0,{start_str},{end_str},ReelStyle,,0,0,0,,{{\\c{h_color}}}{text_clean}{{\\r}}")

    full_ass_content = header + "\n".join(dialogue_lines) + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_ass_content)

    return output_path


def _safe_ass_text(text: str) -> str:
    """Prevent text from breaking ASS override syntax."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").replace("\r", " ")


def _format_ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, rest = divmod(centiseconds, 360000)
    minutes, rest = divmod(rest, 6000)
    seconds, centiseconds = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
