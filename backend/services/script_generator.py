import os
import json
import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import requests
from ..config import GEMINI_API_KEY, OPENAI_API_KEY


def convert_telugu_to_roman(text: str) -> str:
    """
    Phonetic converter translating native Telugu script into readable Roman Telugu (Tenglish).
    Preserves English words, numbers, and punctuation.
    """
    vowels = {
        'అ': 'a', 'ఆ': 'aa', 'ఇ': 'i', 'ఈ': 'ee', 'ఉ': 'u', 'ూ': 'oo', 'ఋ': 'ru',
        'ఎ': 'e', 'ఏ': 'ee', 'ఐ': 'ai', 'ఒ': 'o', 'ఓ': 'oo', 'ఔ': 'au', 'అం': 'am', 'అః': 'aha'
    }
    matras = {
        'ా': 'aa', 'ి': 'i', 'ీ': 'ee', 'ు': 'u', 'ూ': 'oo', 'ృ': 'ru',
        'ె': 'e', 'ే': 'ee', 'ై': 'ai', 'ొ': 'o', 'ో': 'oo', 'ౌ': 'au',
        'ం': 'm', 'ః': 'h', '్': ''
    }
    consonants = {
        'క': 'k', 'ఖ': 'kh', 'గ': 'g', 'ఘ': 'gh', 'ఙ': 'ng',
        'చ': 'ch', 'ఛ': 'chh', 'జ': 'j', 'ఝ': 'jh', 'ఞ': 'ny',
        'ట': 't', 'ఠ': 'th', 'డ': 'd', 'ఢ': 'dh', 'ణ': 'n',
        'త': 'th', 'థ': 'thh', 'ద': 'd', 'ధ': 'dh', 'న': 'n',
        'ప': 'p', 'ఫ': 'ph', 'బ': 'b', 'భ': 'bh', 'మ': 'm',
        'య': 'y', 'ర': 'r', 'ల': 'l', 'వ': 'v', 'శ': 'sh', 'ష': 'sh',
        'స': 's', 'హ': 'h', 'ళ': 'l', 'క్ష': 'ksh', 'ఱ': 'r'
    }
    res = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in vowels:
            res.append(vowels[c])
            i += 1
        elif c in consonants:
            cons = consonants[c]
            if i + 1 < n and text[i+1] in matras:
                next_c = text[i+1]
                m = matras[next_c]
                res.append(cons + m)
                i += 2
            else:
                res.append(cons + 'a')
                i += 1
        elif c in matras:
            res.append(matras[c])
            i += 1
        else:
            res.append(c)
            i += 1
    clean = ''.join(res)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


class Scene(BaseModel):
    scene_number: int
    narration: str                          # Native spoken Telugu for Edge-TTS AI voice
    roman_subtitles: Optional[str] = None   # Roman Telugu / English letters for modern Reel captions
    visual_prompt: str
    search_keyword: str
    scene_category: str = "demo"  # hook, tool_presentation, demo, summary, cta
    duration_estimate_sec: float = 5.0


class Storyboard(BaseModel):
    title: str
    topic: str
    niche: str
    language: str = "Telugu"
    music_mood: str = "lofi_chill"
    total_duration_estimate_sec: float = 40.0
    hook: str
    scenes: List[Scene]
    instagram_caption: str
    instagram_hashtags: List[str]


def generate_storyboard(
    topic: str,
    duration_sec: int = 40,
    niche: str = "Tech & AI",
    language: str = "Telugu"
) -> Storyboard:
    """
    Phase 1: Multi-Scene Decomposition Engine.
    Generates a structured 6-8 scene plan with exact ~5-second boundaries,
    native Telugu or English narration, English visual prompts, and Instagram kit.
    """
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if api_key:
        try:
            return _generate_with_gemini(topic, duration_sec, niche, language, api_key)
        except Exception as e:
            print(f"[ScriptGenerator] Gemini API error: {e}, falling back to semantic engine.")

    return _generate_semantic_storyboard(topic, duration_sec, niche, language)


def _generate_with_gemini(
    topic: str,
    duration_sec: int,
    niche: str,
    language: str,
    api_key: str
) -> Storyboard:
    # Gen Z High-Retention 3-Second Cut Standard: Rapid scene changes every ~2.5 to 3.2 seconds
    scene_count = max(8, min(20, round(duration_sec / 3.0)))
    per_scene = round(duration_sec / scene_count, 1)
    is_telugu = (language.lower() == "telugu")

    lang_instruction = (
        "CRITICAL GEN Z VIRAL EDITING & VISUAL SYNC RULES:\n"
        f"1. RAPID PACING: This reel MUST feature rapid Gen Z cuts every ~2.5 to 3.2 seconds across exactly {scene_count} scenes.\n"
        "2. SPOKEN DURATION: Each scene's spoken 'narration' MUST be ONE short, punchy thought (6 to 10 words maximum) that naturally takes ~2.8 to 3.2 seconds to speak. Never place long paragraphs in a single scene.\n"
        "3. 100% SCRIPT-TO-VISUAL SYNC: For EVERY scene, 'search_keyword' MUST be an ultra-specific 2-to-3-word English visual search query describing the EXACT physical subject, object, or action happening in THAT SPECIFIC 3-SECOND CLIP.\n"
        "   - Good examples: 'desert ruins aerial', 'abandoned stone houses', 'dark night footsteps', 'shocked face expression', 'ancient temple entrance', 'counting cash money', 'developer typing code'.\n"
        "   - Strictly FORBIDDEN keywords: 'mystery', 'facts', 'things', 'demo', 'tech', 'video' (too abstract, leads to mismatched clips).\n"
        "4. 'visual_prompt': Detailed cinematic description in English for AI video models.\n"
        "5. Spoken 'narration': Natural, conversational spoken Telugu (Unicode script) for voiceover.\n"
        "6. 'roman_subtitles': EXACT SAME sentence transliterated into uppercase Roman English alphabet letters (Tenglish) for high-impact on-screen captions.\n"
        if is_telugu else
        "CRITICAL GEN Z VIRAL EDITING & VISUAL SYNC RULES:\n"
        f"1. RAPID PACING: Rapid Gen Z cuts every ~2.5 to 3.2 seconds across exactly {scene_count} scenes.\n"
        "2. SPOKEN NARRATION: 6 to 10 words maximum per scene (punchy spoken delivery).\n"
        "3. 100% SCRIPT-TO-VISUAL SYNC: 'search_keyword' MUST be an ultra-specific 2-to-3-word English visual phrase matching the EXACT subject or action on screen (e.g. 'desert ruins aerial', 'empty town street', 'shocked face close up'). Never use abstract words.\n"
        "4. Spoken 'narration' & 'roman_subtitles': Punchy, conversational English spoken to camera. 'visual_prompt': detailed 4k cinematic prompt."
    )

    is_prewritten = len(topic.strip()) > 80 or "\n" in topic or topic.count(".") >= 2

    script_instruction = (
        "CRITICAL MODE: USER PROVIDED SCRIPT/STORY DECOMPOSITION.\n"
        "The user provided their own pre-written script or detailed story in the User Input.\n"
        "DO NOT invent an unrelated story! Your primary job is to PRESERVE their exact story and narrative progression,\n"
        f"dividing it sequentially into exactly {scene_count} rapid 2.5-3.5 second bite-sized scenes.\n"
        "Match each individual scene's visual search keyword directly to what is happening in THAT specific line of their story."
        if is_prewritten else
        f"CRITICAL MODE: TOPIC CONCEPT GENERATION.\n"
        f"Generate an engaging, viral high-retention reel script around the topic and niche '{niche}' with rapid 3-second scene progression."
    )

    prompt = f"""
    You are an elite viral Instagram Reels creator & director specializing in high-retention, fast-paced Gen Z video content for {niche}.
    User Input:
    \"\"\"{topic}\"\"\"

    Target Niche: {niche}
    Target Language: {language}
    Target Duration: {duration_sec} seconds across exactly {scene_count} fast modular scenes (each strictly ~2.5 to 3.2 seconds).

    {script_instruction}
    {lang_instruction}

    Scene Sequencing Rules (Gen Z High-Retention Rhythm):
    - Scene 1 (Category: hook): 2.5-3.0 second extreme curiosity scroll-stopper hook.
    - Scenes 2 to {scene_count - 1} (Category: story_development / evidence / reveal): Rapid story progression, switching visuals every ~3 seconds.
    - Scene {scene_count} (Category: cta): 2.5-3.0 second call-to-action asking viewers to save and follow.

    Output STRICTLY valid JSON matching this schema with NO markdown wrapping:
    {{
      "title": "Clean Viral Title",
      "topic": "{topic[:120]}",
      "niche": "{niche}",
      "language": "{language}",
      "music_mood": "lofi_chill",
      "total_duration_estimate_sec": {float(duration_sec)},
      "hook": "Spoken hook sentence",
      "scenes": [
        {{
          "scene_number": 1,
          "scene_category": "hook",
          "narration": "Short spoken sentence (6-10 words)...",
          "roman_subtitles": "Short sentence in Roman letters...",
          "visual_prompt": "Cinematic visual prompt in English...",
          "search_keyword": "concrete 2-3 word visual search query",
          "duration_estimate_sec": {per_scene}
        }}
      ],
      "instagram_caption": "Viral formatted IG caption with bullet points & CTA",
      "instagram_hashtags": ["#reels", "#viral", "#trending", "..."]
    }}
    """

    models_to_try = []
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    if env_model:
        models_to_try.append(env_model)
    for candidate in ["gemini-3.8-flash", "gemini-flash-latest"]:
        if candidate not in models_to_try:
            models_to_try.append(candidate)

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.7
        }
    }

    last_error = None
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            res = requests.post(url, json=payload, headers={"x-goog-api-key": api_key}, timeout=(3, 10))
            if res.status_code == 200:
                raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                clean = re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
                data = json.loads(clean)
                for sc in data.get("scenes", []):
                    if is_telugu and not sc.get("roman_subtitles"):
                        sc["roman_subtitles"] = convert_telugu_to_roman(sc.get("narration", ""))
                return Storyboard(**data)
            else:
                last_error = f"{model} returned HTTP {res.status_code}"
        except Exception as e:
            last_error = f"{model} error: {e}"
            continue

    print(f"[ScriptGenerator] Gemini unavailable ({last_error}), switching to instant semantic engine.")
    return _generate_semantic_storyboard(topic, duration_sec, niche, language)


def _segment_script_into_rapid_cuts(text: str) -> list[str]:
    """
    Decomposes any input script into punchy 5-to-9 word spoken thoughts (~2.5-3.2 seconds each).
    Enforces the Gen Z rapid cut rule: a new video cut appears every ~3 seconds.
    """
    raw_pieces = [p.strip() for p in re.split(r'(?:[\r\n]+|[.!?]+|(?<=[,;:])\s+)', text) if len(p.strip()) > 2]
    split_pieces = []
    for piece in raw_pieces:
        words = piece.split()
        if len(words) <= 9:
            split_pieces.append(piece)
        else:
            for k in range(0, len(words), 8):
                chunk_str = " ".join(words[k:k + 8])
                if chunk_str.strip():
                    split_pieces.append(chunk_str)

    merged = []
    curr = ""
    for p in split_pieces:
        w_cnt = len(p.split())
        if not curr:
            curr = p
        elif len(curr.split()) + w_cnt <= 9:
            curr = f"{curr} {p}"
        else:
            merged.append(curr)
            curr = p
    if curr:
        merged.append(curr)

    return merged if merged else [text[:80]]


def _generate_semantic_storyboard(
    topic: str,
    duration_sec: int,
    niche: str,
    language: str = "Telugu"
) -> Storyboard:
    """
    Intelligent semantic intent engine for rapid 3-second cuts with 100% script-to-visual matching.
    """
    is_telugu = (language.lower() == "telugu")
    t_lower = topic.lower()

    # 0. User Provided Script / Story Decomposition Mode (Rapid 3-Second Cut Standard)
    if len(topic.strip()) > 60 or "\n" in topic or topic.count(".") >= 2:
        cuts = _segment_script_into_rapid_cuts(topic)
        total_cuts = len(cuts)
        per_cut = round(max(2.5, min(3.5, duration_sec / max(1, total_cuts))), 1)

        # High-precision visual keyword mapper for 100% script-to-visual match
        kw_map = [
            (["village", "disappear", "vanish", "ghost"], "desert ghost town"),
            (["kuldhara", "rajasthan", "desert", "sand", "dune"], "rajasthan desert ruins"),
            (["temple", "ancient", "statue", "idol"], "ancient stone temple"),
            (["night", "dark", "moon", "midnight", "shadow"], "dark night atmosphere"),
            (["battle", "war", "soldier", "army", "sword"], "ancient battlefield dust"),
            (["escape", "flee", "running", "chase"], "running shadow night"),
            (["ruler", "king", "palace", "salim", "throne", "emperor"], "ancient palace throne"),
            (["curse", "cursed", "dead", "haunt", "blood", "kill"], "mysterious dark ruins"),
            (["today", "empty", "ruin", "house", "abandoned"], "abandoned stone ruins aerial"),
            (["morning", "wake", "sun", "sunrise", "dawn"], "morning desert dawn"),
            (["tax", "money", "wealth", "cash", "gold", "coins", "rich"], "counting money cash"),
            (["muscle", "gym", "workout", "fitness", "body", "lift"], "fitness workout gym"),
            (["dress", "outfit", "fashion", "style", "clothes", "model"], "fashion model street"),
            (["ai", "code", "software", "tool", "coding", "developer"], "coding developer screen"),
            (["space", "galaxy", "universe", "planet", "stars", "alien"], "deep galaxy stars"),
            (["food", "eat", "cooking", "chef", "restaurant"], "delicious food cooking"),
            (["car", "supercar", "race", "drive", "speed"], "supercar racing speed"),
            (["nature", "mountain", "forest", "tree", "river"], "majestic mountain aerial"),
            (["ocean", "sea", "beach", "water", "island"], "ocean waves beach aerial"),
            (["shock", "unbelievable", "secret", "truth", "crazy"], "shocked person face"),
            (["phone", "app", "save", "follow", "instagram", "screen"], "mobile phone app screen"),
        ]

        scenes = []
        for i, cut in enumerate(cuts):
            narration = cut
            roman_sub = convert_telugu_to_roman(narration) if is_telugu else narration
            category = "hook" if i == 0 else ("cta" if i == total_cuts - 1 else "story_development")

            # Map keyword based on exact spoken sentence content
            matched_kw = None
            narr_lower = narration.lower()
            for triggers, visual_kw in kw_map:
                if any(trig in narr_lower for trig in triggers):
                    matched_kw = visual_kw
                    break

            if not matched_kw:
                words = [w.lower() for w in re.findall(r'[A-Za-z0-9]{4,}', narration)]
                clean_kw = [w for w in words if w not in {"this", "that", "there", "about", "their", "where", "which", "could", "would", "because", "simply"}]
                matched_kw = " ".join(clean_kw[:2]) if len(clean_kw) >= 2 else (clean_kw[0] if clean_kw else (niche.lower().split()[0] if niche else "mystery"))

            scenes.append(Scene(
                scene_number=i + 1,
                scene_category=category,
                narration=narration,
                roman_subtitles=roman_sub,
                visual_prompt=f"Cinematic atmospheric footage representing {matched_kw}, 4k professional grading",
                search_keyword=matched_kw,
                duration_estimate_sec=per_cut
            ))

        return Storyboard(
            title=cuts[0][:50] if cuts else "Pro Reel Story",
            topic=topic[:120].strip(),
            niche=niche,
            language=language,
            music_mood="lofi_chill",
            total_duration_estimate_sec=round(len(scenes) * per_cut, 1),
            hook=scenes[0].narration,
            scenes=scenes,
            instagram_caption=f"{topic[:220]}...\n\n📌 Save this reel & share with friends!\n👇 Comment your thoughts below!",
            instagram_hashtags=["#reels", f"#{re.sub(r'[^a-zA-Z0-9]', '', niche.lower())}", "#viral", "#trending", "#story"]
        )

    # Concept Mode: calculate exact scene count for rapid ~3.0s cut rhythm
    scene_count = max(8, min(20, round(duration_sec / 3.0)))
    per_scene = round(duration_sec / scene_count, 1)

    # 1. Tech & AI Tools Intent
    if any(k in t_lower for k in ["ai", "tech", "tool", "tools", "code", "coding", "software", "chatgpt"]):
        if is_telugu:
            scenes_data = [
                ("hook", "రోజూ గంటల కొద్దీ కంప్యూటర్ ముందు పని చేస్తున్నారా? ఈ 3 AI టూల్స్ మీ సమయాన్ని సగానికి ఆదా చేస్తాయి!", "Fast futuristic AI office with neon holograms and floating screens", "artificial intelligence"),
                ("tool_presentation", "మొదటి టూల్: ChatGPT & Claude. మీ రీసెర్చ్ మరియు ఈమెయిల్స్ ని సెకన్లలో ఆటోమేట్ చేయండి.", "Modern programmer typing rapidly on dual glowing 4k monitors", "coding technology"),
                ("demo", "రెండో టూల్: Perplexity AI. గూగుల్ లాగా వందల లింక్స్ వెతకాల్సిన పనిలేదు, సూటిగా సమాధానం ఇస్తుంది.", "High-tech search engine interface showing real-time AI citation stream", "technology computer"),
                ("tool_presentation", "మూడో టూల్: Cursor & GitHub Copilot. మీ కోడింగ్ ప్రాజెక్టులను పది రెట్లు వేగంగా పూర్తి చేయండి.", "Close-up macro of code auto-completing on dark terminal screen", "software developer"),
                ("demo", "ఈ మూడు టూల్స్ వాడితే మీ ఉత్పాదకత ఊహించని రేంజ్ కి వెళ్తుంది.", "Futuristic glass tablet displaying AI workflows in motion", "future technology"),
                ("summary", "ఈ టూల్స్ వివరాలు కింద కామెంట్స్ మరియు కాప్షన్ లో ఇచ్చాను.", "Holographic dashboard summarizing top AI productivity applications", "cyberpunk matrix"),
                ("cta", "మరిన్ని డైలీ AI మరియు టెక్ అప్‌డేట్స్ కోసం ఇప్పుడే ఫాలో అవ్వండి, ఈ రీల్ ని సేవ్ చేసుకోండి!", "Futuristic Instagram save and follow icon animation on phone", "mobile phone app")
            ]
            title = "3 ఉచిత AI టూల్స్ మీ సమయాన్ని ఆదా చేస్తాయి"
            resolved_niche = "Tech & AI"
            ig_caption = (
                "రోజూ గంటల కొద్దీ సమయం ఆదా చేసే 3 అద్భుతమైన AI టూల్స్ 🤖⚡\n\n"
                "1️⃣ ChatGPT & Claude - మీ రీసెర్చ్, ఈమెయిల్స్ ని ఆటోమేట్ చేయడానికి\n"
                "2️⃣ Perplexity AI - వేగవంతమైన స్మార్ట్ సెర్చ్ కోసం\n"
                "3️⃣ Cursor & Copilot - మీ కోడింగ్ ని 10x వేగవంతం చేయడానికి\n\n"
                "📌 ఈ రీల్ ని ఇప్పుడే సేవ్ చేసుకోండి!\n"
                "👇 మీరు ఇప్పటికే ఏ టూల్ వాడుతున్నారు? కామెంట్ చేయండి!"
            )
            ig_tags = [
                "#telugutech", "#telugureels", "#ai", "#aitools", "#technologytelugu",
                "#telugutips", "#codingtelugu", "#chatgpt", "#reelsinstagram", "#explorepage"
            ]
        else:
            scenes_data = [
                ("hook", "Still spending hours on repetitive work? These 3 AI tools will cut your workload in half.", "Futuristic AI workspace with holographic data visualization", "artificial intelligence"),
                ("tool_presentation", "Tool one: Claude and ChatGPT. Automate research, documentation, and reporting in seconds.", "Developer working on dual glowing monitors in dark room", "coding technology"),
                ("demo", "Tool two: Perplexity AI. Skip endless Google tabs—get direct cited answers immediately.", "High-tech futuristic computer search interface with neural streams", "technology computer"),
                ("tool_presentation", "Tool three: Cursor IDE. Write clean production software ten times faster with agentic coding.", "Macro shot of code typing itself on dark terminal screen", "software developer"),
                ("demo", "Pairing these together creates an unfair productivity advantage in your daily workflow.", "Sleek glass tablet interface animating AI system pipelines", "future technology"),
                ("summary", "Links and prompt formulas are organized in the caption below.", "Futuristic glowing dashboard showing productivity metric graphs", "cyberpunk matrix"),
                ("cta", "Save this reel right now and follow for daily high-leverage AI breakdowns.", "Futuristic Instagram save and follow button pulse animation", "mobile phone app")
            ]
            title = "3 AI Tools That Save Hours of Work"
            resolved_niche = "Tech & AI"
            ig_caption = (
                "3 game-changing AI tools to 10x your output 🤖⚡\n\n"
                "1️⃣ ChatGPT / Claude - Instant research & workflow automation\n"
                "2️⃣ Perplexity AI - Direct answers with source verification\n"
                "3️⃣ Cursor - Multi-agent software generation\n\n"
                "📌 Save this reel before your next work sprint!"
            )
            ig_tags = [
                "#ai", "#aitools", "#technology", "#productivity", "#chatgpt",
                "#softwareengineer", "#coding", "#reels", "#reelsinstagram", "#techreels"
            ]

    # 2. Fashion & Style Intent
    elif any(k in t_lower for k in ["fashion", "outfit", "style", "dress", "clothes", "streetwear"]):
        if is_telugu:
            scenes_data = [
                ("hook", "మీరు వేసుకునే ఏ డ్రెస్ అయినా పది రెట్లు రిచ్‌గా కనిపించాలా? ఈ 3 స్టైల్ రూల్స్ పాటించండి!", "Fashion model in minimalist tailored designer outfit walking city street", "fashion model"),
                ("tool_presentation", "రూల్ వన్: ప్రపోర్షన్స్ సరిగ్గా ఉండాలి. మీ ప్యాంట్ వదులుగా ఉంటే, పైన షర్ట్ క్లీన్ మరియు ఫిట్ గా ఉండాలి.", "Stylish modern menswear streetwear fit check in daylight", "streetwear outfit"),
                ("demo", "రూల్ టూ: పెద్ద బ్రాండ్ లోగోలను వదిలేయండి. ఎర్త్ టోన్స్ మరియు నాణ్యమైన ఫ్యాబ్రిక్ మీ లుక్ ని ఎలివేట్ చేస్తాయి.", "Close-up of minimalist luxury watch, tailored cuff, and linen fabric", "luxury accessories"),
                ("tool_presentation", "రూల్ త్రీ: మీ షూస్ ఎప్పుడూ నీట్ గా మరియు క్లీన్ గా ఉండాలి. షూస్ మీ ఓవర్ ఆల్ ఇంప్రెషన్ ని నిర్ణయిస్తాయి.", "Crisp minimalist leather designer sneakers on pavement", "designer shoes"),
                ("summary", "సరైన ఫిట్టింగ్ మరియు కలర్ కాంబినేషన్ ఉంటే తక్కువ బడ్జెట్ లోనే లగ్జరీ లుక్ సొంతం చేసుకోవచ్చు.", "Confident stylish creator smiling in cinematic golden hour city", "fashion runway"),
                ("cta", "మీ నెక్స్ట్ షాపింగ్ కోసం ఈ రీల్ ని ఇప్పుడే సేవ్ చేసుకోండి, డైలీ స్టైల్ టిప్స్ కోసం ఫాలో అవ్వండి!", "Model holding modern smartphone tapping save button", "street style")
            ]
            title = "మీ అవుట్‌ఫిట్ ని రిచ్‌గా మార్చే 3 సీక్రెట్ రూల్స్"
            resolved_niche = "Fashion & Style"
            ig_caption = (
                "మీ డ్రెస్సింగ్ స్టైల్ ని ఎలివేట్ చేసే 3 గోల్డెన్ రూల్స్ 👔✨\n\n"
                "1️⃣ ప్రపోర్షన్స్ బ్యాలెన్స్ చేయండి\n"
                "2️⃣ లౌడ్ లోగోలు కాకుండా టెక్స్చర్ పై ఫోకస్ చేయండి\n"
                "3️⃣ క్లీన్ ఫుట్‌వేర్ ఎంచుకోండి\n\n"
                "📌 మీ నెక్స్ట్ అవుట్‌ఫిట్ చెక్ కోసం సేవ్ చేసుకోండి!\n"
                "👇 మీరు ఏ రూల్ మొదట పాటిస్తున్నారు?"
            )
            ig_tags = [
                "#telugufashion", "#telugustyle", "#fashiontips", "#ootd", "#mensfashiontelugu",
                "#reelsinstagram", "#telugureels", "#mensstyle", "#streetwear"
            ]
        else:
            scenes_data = [
                ("hook", "3 simple style rules that instantly make any outfit look ten times more expensive.", "Fashion model in clean tailored designer outfit walking city street", "fashion model"),
                ("tool_presentation", "Rule one: Master proportions. If your trousers are relaxed, keep your top clean and fitted.", "Stylish modern menswear streetwear fit check in daylight", "streetwear outfit"),
                ("demo", "Rule two: Ditch loud logos. Luxury aesthetics focus on neutral earth tones and rich textures.", "Close-up of minimalist luxury watch, tailored cuff, and wool fabric", "luxury accessories"),
                ("tool_presentation", "Rule three: Footwear makes or breaks the fit. Keep shoes immaculate and let one piece lead.", "Crisp minimalist leather designer sneakers on city pavement", "designer shoes"),
                ("summary", "Investing in timeless wardrobe staples pays compound dividends over fast fashion trends.", "Confident creator in cinematic golden hour urban background", "fashion runway"),
                ("cta", "Save this reel before your next outfit check, and follow for daily style upgrades.", "Model smiling holding smartphone with modern city backdrop", "street style")
            ]
            title = "3 Rules to Elevate Any Outfit"
            resolved_niche = "Fashion & Style"
            ig_caption = (
                "Elevate your daily fits with these 3 golden rules 👔✨\n\n"
                "1️⃣ Balance proportions\n"
                "2️⃣ Textures over loud brand logos\n"
                "3️⃣ Clean, intentional footwear\n\n"
                "📌 Save this for your next fit check!"
            )
            ig_tags = ["#fashion", "#mensfashion", "#styleinspo", "#ootd", "#streetwear", "#fashiontips", "#reels"]

    # 3. Default / Fitness / Facts
    else:
        if is_telugu:
            scenes_data = [
                ("hook", f"{topic} గురించి ఈ ఆశ్చర్యకరమైన నిజం మీకు ముందే తెలుసా?", "Mysterious glowing digital cosmos portal in dark space", "space universe"),
                ("tool_presentation", f"దీని వెనుక ఉన్న అసలైన శాస్త్రీయ కారణాన్ని పరిశీలిస్తే ఎవరైనా ఆశ్చర్యపోవాల్సిందే.", "High-tech science laboratory with glowing laser diagnostics", "science laboratory"),
                ("demo", "ప్రతిరోజూ మనం చూసే విషయాల వెనుక దాగి ఉన్న సైన్స్ మన ఆలోచనల కంటే ఎంతో లోతైనది.", "Golden geometric fractal smoothly rotating in atmospheric dark room", "abstract geometry"),
                ("summary", "ఈ నిజాన్ని తెలుసుకున్న తర్వాత మీ ఆలోచనా విధానం పూర్తిగా మారిపోతుంది.", "Deep galaxy spinning with millions of stars cinematic 4k", "galaxy stars"),
                ("cta", "ఈ మైండ్ బ్లోయింగ్ ఫ్యాక్ట్ నచ్చితే డబుల్ ట్యాప్ చేయండి, మరిన్ని సైన్స్ విషయాల కోసం ఫాలో అవ్వండి!", "Smartphone screen displaying glowing heart like animation", "mobile phone app")
            ]
            title = f"{topic} వెనుక ఉన్న అసలైన రహస్యం"
            resolved_niche = niche
            ig_caption = (
                f"{topic} గురించి మీకు తెలియని ఆసక్తికరమైన విషయాలు 🤯✨\n\n"
                "📌 ఇప్పుడే సేవ్ చేసుకోండి & మీ ఫ్రెండ్స్ కి షేర్ చేయండి!\n"
                "👇 మీ అభిప్రాయాన్ని కామెంట్ చేయండి!"
            )
            ig_tags = ["#telugufacts", "#teluguscience", "#telugureels", "#didyouknowtelugu", "#knowledge", "#reels"]
        else:
            scenes_data = [
                ("hook", f"You will never look at {topic.title()} the same way after hearing this.", "Dramatic mysterious glowing cosmic portal in dark space", "space universe"),
                ("tool_presentation", f"When you break down the real science behind {topic.title()}, the numbers defy standard intuition.", "High-tech research laboratory with glowing telemetry", "science laboratory"),
                ("demo", "Mastering this knowledge gives you an immediate unfair advantage in how you analyze the world.", "Golden geometric fractals smoothly rotating in dark atmosphere", "abstract geometry"),
                ("summary", "The deeper you investigate the data, the clearer the underlying patterns become.", "Deep galaxy spinning with millions of stars cinematic 4k", "galaxy stars"),
                ("cta", "Double tap if this blew your mind, and follow for more daily breakdowns.", "Modern smartphone interface showing save button pulse", "mobile phone app")
            ]
            title = f"The Truth Behind {topic.title()}"
            resolved_niche = niche
            ig_caption = f"Did you know this about {topic.title()}? 🤯✨\n\n📌 Save & double tap for more daily insights!"
            ig_tags = ["#facts", "#science", "#curiosity", "#didyouknow", "#mindblown", "#reels"]

    scenes = []
    for i in range(scene_count):
        idx = i % len(scenes_data)
        category, narration, visual_prompt, search_keyword = scenes_data[idx]
        roman_sub = convert_telugu_to_roman(narration) if is_telugu else narration
        scenes.append(Scene(
            scene_number=i + 1,
            scene_category=category,
            narration=narration,
            roman_subtitles=roman_sub,
            visual_prompt=visual_prompt,
            search_keyword=search_keyword,
            duration_estimate_sec=per_scene
        ))

    return Storyboard(
        title=title,
        topic=topic.strip(),
        niche=resolved_niche,
        language=language,
        music_mood="lofi_chill",
        total_duration_estimate_sec=float(duration_sec),
        hook=scenes[0].narration,
        scenes=scenes,
        instagram_caption=ig_caption,
        instagram_hashtags=ig_tags
    )
