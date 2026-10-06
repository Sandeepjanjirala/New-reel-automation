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
    # 35-45s Reels standard: 6 to 8 modular 5-second scenes
    scene_count = max(5, min(8, duration_sec // 5))
    is_telugu = (language.lower() == "telugu")

    lang_instruction = (
        "CRITICAL LANGUAGE & SUBTITLE RULE:\n"
        "1. Spoken 'narration' and 'hook': MUST be written in natural, engaging conversational spoken Telugu (తెలుగు) using Telugu Unicode script, exactly like a top Telugu tech creator speaking to the camera (e.g., 'రోజూ గంటల కొద్దీ పని చేసి అలసిపోతున్నారా? ఈ 3 AI టూల్స్ మీ సమయాన్ని ఆదా చేస్తాయి!'). This is sent to Microsoft Edge-TTS (te-IN-MohanNeural) so the voice sounds 100% natural, human, and authentic.\n"
        "2. 'roman_subtitles': MUST be the EXACT SAME spoken Telugu sentence transliterated into Roman English alphabet letters (Tenglish), as seen on viral Instagram Reels (e.g., 'Rojuvary panulatho alasipothunnara? Ee 3 AI tools mee samayanni aada chesthayi!'). Keep it clean, punchy, and formatted in natural Roman letters matching the spoken words word-for-word.\n"
        "3. 'visual_prompt': MUST ALWAYS be in English so generative AI video models can understand it.\n"
        "4. 'search_keyword': MUST be in English (1-2 clean words like 'artificial intelligence', 'coding developer').\n"
        "5. 'instagram_caption': Should be engaging in Telugu + English with bullet points and emojis."
        if is_telugu else
        "The spoken 'narration' and 'hook' must be in punchy, natural conversational English spoken to camera. 'roman_subtitles' should be identical to 'narration'. 'visual_prompt' in detailed English for video models."
    )

    prompt = f"""
    You are an elite viral Instagram Reels creator & director specializing in tech, productivity, and modern lifestyle content.
    Topic: "{topic}"
    Target Niche: {niche}
    Target Language: {language}
    Target Duration: {duration_sec} seconds across exactly {scene_count} modular scenes (around 4.5 to 5.5 seconds each).

    {lang_instruction}

    Scene Sequencing Rules (Modular 5-Second Blocks):
    - Scene 1 (Category: hook): 3-4 second scroll-stopping spoken hook with high curiosity.
    - Scenes 2 to {scene_count - 2} (Category: tool_presentation / demo): Introduce distinct tools or actionable steps with fast-paced visual instructions.
    - Scene {scene_count - 1} (Category: summary): 4 second quick recap showing all tools/tips together.
    - Scene {scene_count} (Category: cta): 4 second call-to-action asking viewers to save, share, and follow.

    Output STRICTLY valid JSON matching this schema with NO markdown wrapping:
    {{
      "title": "Clean Title",
      "topic": "{topic}",
      "niche": "{niche}",
      "language": "{language}",
      "music_mood": "lofi_chill",
      "total_duration_estimate_sec": {float(duration_sec)},
      "hook": "Spoken hook sentence",
      "scenes": [
        {{
          "scene_number": 1,
          "scene_category": "hook",
          "narration": "Spoken Telugu in native script (for voice)...",
          "roman_subtitles": "Spoken Telugu in Roman English letters (for subtitles)...",
          "visual_prompt": "Cinematic visual prompt in English for video generator model...",
          "search_keyword": "tech ai",
          "duration_estimate_sec": 4.5
        }}
      ],
      "instagram_caption": "Viral formatted IG caption with bullet points & CTA",
      "instagram_hashtags": ["#telugutech", "#ai", "#reels", "#trending", "..."]
    }}
    """

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("Invalid GEMINI_MODEL setting")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.7
        }
    }

    res = requests.post(url, json=payload, headers={"x-goog-api-key": api_key}, timeout=40)
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    clean = re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    data = json.loads(clean)
    for sc in data.get("scenes", []):
        if is_telugu and not sc.get("roman_subtitles"):
            sc["roman_subtitles"] = convert_telugu_to_roman(sc.get("narration", ""))
    return Storyboard(**data)


def _generate_semantic_storyboard(
    topic: str,
    duration_sec: int,
    niche: str,
    language: str = "Telugu"
) -> Storyboard:
    """
    Intelligent semantic intent engine for offline/fallback mode with full Telugu support.
    """
    is_telugu = (language.lower() == "telugu")
    scene_count = max(5, min(8, duration_sec // 5))
    per_scene = round(duration_sec / scene_count, 1)

    t_lower = topic.lower()

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
