# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches
"""
Audio Masterclass Factory (统一版) —— 合并自 youtube_compare.py (V18) / youtube_one.py (V29) / youtube_long.py (V90)

流水线: YouTube 字幕 -> Map(洞察提取) -> Reduce(概念去重) -> 文案生成 -> (可选)渲染 -> (可选)上传

预设 (--preset):
  dense      V18 高密度去重: 无 Hook/Outro, 单段不足 500 词则 CONTINUE 续写, 同时生成 SEO 元数据
  architect  V29 Pure Architect: Hook + 6 段(含强制例子, 字数校验自动重写) + Outro; 静态背景视频渲染
  long       V90 Ultimate: 导演矩阵(HUMAN/ENVIRONMENT/SYMBOLIC) + 生图 + 动画 + 母带 + NVENC + YouTube 上传

模式 (--mode): script(只出文案) | render(出文案并渲染成片). 默认: dense/long=script, architect=render
所有 Prompt 保持原文。

环境变量: GEMINI_API_KEY, OPENAI_API_KEY; long 渲染另需 RUNNINGHUB_API_KEY; 上传需 client_secret.json
"""

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# =====================================================================
# 1. 导演矩阵 (long 预设, 原文)
# =====================================================================
CASTING_POOL = [
    "a weary middle-aged man in a slightly oversized shirt",
    "an exhausted elderly artisan with wrinkled hands",
    "a frustrated teenage boy in a simple hoodie",
    "a tired young parent looking overwhelmed",
    "a stressed corporate professional with a loosened tie",
    "a contemplative older woman with elegant silver hair",
    "a young male university student with tired eyes",
    "a burnt-out freelance artist in a messy studio",
    "a lonely late-night convenience store clerk",
    "a quiet researcher surrounded by towering stacks of books"
]

LOCATION_POOL = [
    "a quiet, rain-streaked empty train carriage",
    "a sun-drenched, dusty old kitchen corner",
    "a long, silent corporate hallway with leading lines",
    "an empty, dimly lit laundromat at 3 AM",
    "a peaceful balcony overlooking distant city lights",
    "a vast, quiet public library aisle",
    "a lonely bus shelter under a single streetlight",
    "a messy but cozy attic studio with a high window",
    "an empty botanical greenhouse with glass panes",
    "a quiet, overgrown garden path at dusk"
]

CAMERA_POOL = [
    "Cinematic Wide Shot, capturing the scale of the environment",
    "Low-angle shot from the floor, looking up with a sense of weight",
    "Extreme Close-up, focusing on fine textures and micro-expressions",
    "Over-the-shoulder shot, creating a sense of intimacy",
    "Bird's-eye view from the ceiling, looking down at the layout",
    "Profile shot, capturing a thoughtful silhouette against the light",
    "Macro shot, focusing on a single tiny detail in sharp focus",
    "Medium shot, perfectly balanced with natural leading lines",
    "Tilted Dutch angle, subtly suggesting internal instability",
    "Golden hour back-lit shot, creating a strong glowing rim light"
]

METAPHOR_POOL = [
    "intricate shadows cast by a window lattice",
    "a single, heavy water droplet about to fall from a tap",
    "distorted reflections in a rain puddle on the ground",
    "a vintage mechanical clock's exposed, slow-moving gears",
    "dust motes dancing in a single, sharp beam of light",
    "a long, clean railway track receding into the horizon",
    "a discarded, crumpled map left on an empty bench",
    "ripples slowly smoothing out in a dark pool of water",
    "a heavy iron pendulum swinging with silent precision",
    "the soft, colorful refraction of light through a glass prism"
]

# =====================================================================
# 2. Prompt (原文, 按预设分组)
# =====================================================================
PROMPTS_DENSE = {
    "STEP1_MAP": """Extract ONLY concrete, specific insights from this segment.

        Each insight MUST:
        - Be a distinct, non-overlapping idea
        - Preserve original terminology where possible
        - Include the context (why it matters or how it works)

        STRICT RULES:
        - NO vague summaries
        - NO repetition of similar ideas
        - Each line must represent a UNIQUE insight

        IGNORE:
        - sponsor reads
        - intros/outros
        - calls to action

        Segment:
        {chunk}""",

    "STEP2_REDUCE": """Review the insights pool and perform concept deduplication.

        STEP 1: Identify the SINGLE overarching topic.
        STEP 2: Cluster similar ideas together and REMOVE redundancy.
        STEP 3: Select 5 to 6 concepts that are:
        - Conceptually DISTINCT (no overlap)
        - Each represents a DIFFERENT mechanism or perspective
        - Not rephrasings of the same idea

        STRICT RULES:
        - If two concepts are similar -> merge them.
        - Each concept must answer a DIFFERENT question.
        - Avoid semantic overlap at all costs.

        Return strictly in JSON format: 
        {{ 
            "topic": "The exact topic of the text", 
            "concepts": [
                {{"point": "Distinct Concept 1", "details": "Context and explanation"}}
            ] 
        }}
        Insights Pool: {insights}""",

    "STEP3_SCRIPT_SINGLE": """You are an expert thinker explaining a concept in a long-form audio monologue.

        IMPORTANT:
        This is NOT a motivational speech.
        This is NOT a repetitive podcast script.
        Your goal is to make the listener genuinely understand the concept deeply.

        STRUCTURE (internal, do NOT make it obvious):
        - Start directly with the idea (NO generic hooks like "Imagine..." unless truly necessary).
        - Expand the logic step by step.
        - Use ONE strong, concrete example (not multiple repetitive ones).
        - Conclude naturally with insight and implication.

        ANTI-REPETITION RULES (CRITICAL):
        - Do NOT restate the same idea in different words.
        - Each paragraph must introduce NEW information.
        - Avoid filler transitions like "Now let's...", "Think about this...", "Imagine you...".

        STYLE:
        - Calm, intelligent, slightly reflective.
        - Minimal fluff. No exaggerated emotional tone.
        - Speak like explaining to a smart adult.
        - Use '...' frequently to indicate deliberate, thoughtful pauses.

        CONSTRAINT:
        - Stay grounded in the provided details. Do NOT invent theories.
        - Avoid generic self-help language.

        Length target: ~500 to 600 words.
        Output: ONE continuous spoken monologue (NO markdown, NO headers, NO bullet points).
        
        Topic: {topic}
        Concept: {point}
        Details: {details}""",

    "STEP3_SCRIPT_CONTINUE": """The following audio script segment needs to be slightly longer.
        
        Continue ONLY by adding:
        - ONE new perspective OR
        - ONE deeper implication OR
        - ONE more precise real-world scenario

        DO NOT:
        - Repeat previous explanations.
        - Rephrase the same idea.
        - Use Markdown or bullet points.

        Keep it tight, additive, and maintain the calm, intelligent, slow-paced tone with '...' pauses.
        
        Previous text to continue from:
        {text}""",

    # 原脚本中为内联 f-string, 这里改为模板占位符 {topic}, 文字不变
    "SEO_INLINE": "Generate JSON SEO metadata (title, description, tags) for a highly intelligent audio masterclass about {topic}. No cliches.",
}

PROMPTS_ARCHITECT = {
    "STEP1_MAP": """Extract ONLY concrete, specific insights from this segment.
        Each insight MUST be a distinct, non-overlapping idea.
        Preserve original terminology where possible.
        Segment: {chunk}""",

    "STEP2_REDUCE": """Review the insights pool and perform concept deduplication.

        STEP 1: Identify the SINGLE overarching topic.
        STEP 2: Select EXACTLY 6 concepts that are conceptually DISTINCT (no overlap). You MUST provide 6.
        STEP 3: For EVERY concept, invent ONE highly specific, visceral, gritty modern-day example to illustrate it. 
        - DO NOT use generic examples (like "a student studying").
        - EVERY EXAMPLE MUST BE COMPLETELY DIFFERENT FROM THE OTHERS.

        Return strictly in JSON format: 
        {{ 
            "topic": "The exact topic of the text", 
            "concepts": [
                {{
                    "point": "Distinct Concept 1", 
                    "details": "Context and explanation",
                    "specific_example": "One unique, gritty, everyday scenario illustrating this."
                }}
            ] 
        }}
        Insights Pool: {insights}""",

    "STEP3_HOOK": """You are the host of a deeply hypnotic, slow-paced late-night audio masterclass.
        
        The overarching topic of tonight's session is: {topic}.
        Here are the core concepts we will explore tonight:
        {concepts}

        YOUR TASK:
        Write a gripping, philosophical, and empathetic OPENING HOOK (approx 150-200 words) that sets the stage for these exact concepts.
        1. Start by describing a universal, painful human feeling related to this specific journey.
        2. Subtly hint at the journey we will take, promising clarity and peace.
        3. Do NOT say "Welcome to the podcast". Just start speaking directly into their soul.
        4. Tone: Calm, slow, intimate. NO markdown.""",

    "STEP3_SCRIPT_SINGLE": """You are recording ONE segment of a long, deeply educational, slow-paced audio masterclass.

        Topic: {topic}
        Concept to explain: {point}
        Core Logic: {details}
        MANDATORY EXAMPLE TO USE: {example}

        YOUR TASK:
        Write a deep, hypnotic, and profoundly intelligent spoken monologue explaining this concept. 

        CRITICAL WRITING RULES:
        1. USE THE EXACT EXAMPLE PROVIDED: Dive deep into the psychology of that specific moment.
        2. NO POETRY, NO MELODRAMA: Be grounded and psychologically sharp.
        3. TONE & PACING: Calm, incredibly slow, and thoughtful. Use '...' frequently for 2-second breathing pauses.
        4. NO CLUNKY TRANSITIONS: Just start exploring the idea immediately.

        FORMAT:
        - Output ONE continuous spoken monologue.
        - NO markdown, NO headers, NO bullet points.
        - Target Length: MUST be approximately {target_words} words. Expand deeply on the psychology to hit this length.""",

    "STEP3_OUTRO": """You are concluding this deeply hypnotic, slow-paced late-night audio masterclass.
        The overarching topic was: {topic}.

        YOUR TASK:
        Write a beautiful, grounding OUTRO and a high-class CALL TO ACTION (CTA) (approx 150-200 words).
        1. Summarize the overarching philosophy gently. Bring the listener back to a state of peace.
        2. Add a soft CTA: Invite them to subscribe and comment their struggle.
        3. Tone: Extremely comforting. NO markdown."""
}

PROMPTS_LONG = {
    "STEP1_MAP": """
    TASK: Extract core knowledge from the provided segment.
    
    --- RULES ---
    1. Extract ONLY concrete, specific insights, frameworks, and hard knowledge.
    2. Each insight MUST be a distinct, non-overlapping idea.
    3. Preserve the original terminology where possible.
    4. Ignore fluff, filler words, and redundant examples.
    
    --- INPUT SEGMENT ---
    {chunk}
    """,

    "STEP2_REDUCE": """
    TASK: Review the insights pool and perform concept deduplication.
    
    --- OUTPUT REQUIREMENTS ---
    1. Identify the SINGLE overarching topic of the entire pool.
    2. Extract EXACTLY 6 conceptually DISTINCT concepts.
    3. You MUST return the result strictly in valid JSON format.
    
    --- INSIGHTS POOL ---
    {insights}
    """,

    "STEP3_HOOK": """
    PERSONA: You are the host of a deeply hypnotic, slow-paced late-night audio masterclass.
    
    --- CONTEXT ---
    - Topic of tonight's session: {topic}
    - Core Concepts to be covered: {concepts}
    
    --- TASK & GUIDELINES ---
    - Write a gripping OPENING HOOK to draw the listener in.
    - Target Length: Approximately 150-200 words.
    - Tone: Calm, slow, intimate, and deeply resonant.
    
    --- STRICT PROHIBITIONS (CRITICAL) ---
    - DO NOT use the word 'you' or 'your' (keep it universal and atmospheric).
    - DO NOT use ellipses (...) anywhere in the text.
    - DO NOT use markdown formatting (no bold, italics, or headers).
    """,

    "STEP3_SCRIPT_SINGLE": """
    PERSONA: You are recording ONE segment of a slow-paced audio masterclass.
    
    --- SEGMENT CONTEXT ---
    - Topic: {topic}
    - Core Concept: {point}
    - Logic/Details: {details}
    - Example: {example}
    
    --- TASK & GUIDELINES ---
    - Write a deep, hypnotic spoken monologue exploring this specific concept.
    - 80/20 KNOWLEDGE RULE: Dive deep into the psychological mechanics rather than surface-level advice.
    - TONE: Match the emotion exactly -> [{emotion_tone}].
    - PACING: Use periods and commas strategically to force breathing pauses for the TTS engine.
    - Target Length: Approximately ~{target_words} words.
    
    --- STRICT PROHIBITIONS (CRITICAL) ---
    - ABSOLUTELY NO ellipses (...).
    - DO NOT use the word 'you' or 'your'.
    - DO NOT use markdown formatting.
    """,

    "STEP3_OUTRO": """
    PERSONA: You are concluding a deeply hypnotic, slow-paced audio masterclass.
    
    --- CONTEXT ---
    - Topic: {topic}
    
    --- TASK & GUIDELINES ---
    - Write a grounding OUTRO and a gentle Call-To-Action (CTA).
    - Target Length: Approximately 150-200 words.
    - Tone: Extremely comforting, bringing the listener back to a state of peace.
    
    --- STRICT PROHIBITIONS (CRITICAL) ---
    - DO NOT use the word 'you' or 'your'.
    - DO NOT use ellipses (...).
    - DO NOT use markdown formatting.
    """,

    "STEP4_METADATA": """
    TASK: Generate YouTube metadata for a highly engaging, atmospheric audio masterclass.
    
    --- CONTEXT ---
    Topic of the Masterclass: {topic}
    
    --- OUTPUT REQUIREMENTS ---
    1. title: A captivating, high-CTR title (max 65 chars). Should evoke curiosity and calmness.
    2. description: A compelling 2-paragraph description of the video's psychological theme, ending with a gentle CTA to subscribe.
    3. tags: An array of 10-15 highly relevant SEO tags.
    4. You MUST return the result strictly in valid JSON format.
    """,

    "VISUAL_ANCHOR_GEN": (
        "Studio Ghibli animation style, beautiful vibrant colors, "
        "highly detailed, serene everyday life, natural sunlight, cinematic anime still."
    ),

    "SCENE_PROMPT_HUMAN": """
    PERSONA: You are a cinematic visual executor for a high-end documentary.
    TASK: Integrate the provided SCRIPT SEGMENT into the FIXED VISUAL FRAMEWORK below.
    
    --- FIXED VISUAL FRAMEWORK (DO NOT CHANGE) ---
    - SCENE TYPE: {forced_visual_type}
    - LOCATION: {location}
    - CAMERA: {camera}
    - CHARACTER: {subject}
    - OVERALL AESTHETIC: Follow the visual anchor exactly.
    
    --- SCRIPT SEGMENT (FOR DETAIL & MOOD) ---
    {text}
    
    --- EXECUTION RULES ---
    1. Focus entirely on the CHARACTER within the specified LOCATION. 
    2. Translate the emotion from the script into their subtle body language and facial expression.
    3. Output ONLY the final English image prompt string.
    4. You MUST append exactly [{anchor}] at the very end. DO NOT use markdown.
    """,

    "SCENE_PROMPT_ENVIRONMENT": """
    PERSONA: You are a cinematic visual executor for a high-end documentary.
    TASK: Integrate the provided SCRIPT SEGMENT into the FIXED VISUAL FRAMEWORK below.
    
    --- FIXED VISUAL FRAMEWORK (DO NOT CHANGE) ---
    - SCENE TYPE: {forced_visual_type}
    - LOCATION: {location}
    - CAMERA: {camera}
    - OVERALL AESTHETIC: Follow the visual anchor exactly.
    
    --- SCRIPT SEGMENT (FOR MOOD & ATMOSPHERE) ---
    {text}
    
    --- EXECUTION RULES (CRITICAL) ---
    1. ABSOLUTELY NO HUMANS ALLOWED. No faces, no hands, no silhouettes.
    2. The subject is the LOCATION ITSELF. Focus purely on architecture, depth, and spatial emptiness.
    3. Translate the emotion from the script through lighting, shadows, dust motes, and weather.
    4. Output ONLY the final English image prompt string.
    5. You MUST append exactly [{anchor}] at the very end. DO NOT use markdown.
    """,

    "SCENE_PROMPT_SYMBOLIC": """
    PERSONA: You are a cinematic visual executor for a high-end documentary.
    TASK: Integrate the provided SCRIPT SEGMENT into the FIXED VISUAL FRAMEWORK below.
    
    --- FIXED VISUAL FRAMEWORK (DO NOT CHANGE) ---
    - SCENE TYPE: {forced_visual_type}
    - FOCAL METAPHOR: {subject}
    - CAMERA: {camera}
    - BACKGROUND: A minimal, dark, or abstract macro studio setting to isolate the metaphor.
    - OVERALL AESTHETIC: Follow the visual anchor exactly.
    
    --- SCRIPT SEGMENT (FOR THEMATIC TONE) ---
    {text}
    
    --- EXECUTION RULES (CRITICAL) ---
    1. ABSOLUTELY NO HUMANS ALLOWED.
    2. DO NOT place the metaphor in a complex room (like a kitchen or train). The background must be beautifully blurred and indistinct to keep pure focus on the FOCAL METAPHOR.
    3. Translate the concept purely through the physical interaction of the object, light, and macro details.
    4. Output ONLY the final English image prompt string.
    5. You MUST append exactly [{anchor}] at the very end. DO NOT use markdown.
    """
}

EMOTION_CURVE = [
    "Painful Truth, Tension, and Discomfort",
    "Confusion, Overwhelm, and Lost Direction",
    "Curiosity, Seeking, and Shifting Perspective",
    "Profound Realization and Epiphany",
    "Release, Action, and Letting Go",
    "Deep Calm, Integration, but Lingering Thought"
]

# =====================================================================
# 3. 预设
# =====================================================================
PRESETS = {
    "dense": {
        "desc": "V18 高密度去重: 无 Hook/Outro, 不足 500 词续写, 生成 SEO",
        "prompts": PROMPTS_DENSE,
        "video_id": "rDdoUbCFn24",
        "base_path": "D:/AIGen/MasterFactory_V18",
        "default_mode": "script",
        "g_model": "gemini-2.0-pro-exp-02-05", "o_model": "gpt-4o-mini",
        "voice": "en-AU-WilliamNeural", "voice_rate": "-15%", "voice_pitch": "-5Hz",
        "clean": "filler",
        "map_unit": ("words", 4000, True),
        "script_mode": "dense",
        "strip_markdown": True,
        "render": "simple",
        "assets": {
            "videos": ["D:/Assets/V/Sleep.mp4", "D:/Assets/V/Zen.mp4", "D:/Assets/V/Library.mp4", "D:/Assets/V/Mountain.mp4"],
            "audios": ["D:/Assets/A/Rain.mp3", "D:/Assets/A/Zen.mp3", "D:/Assets/A/Ambient.mp3", "D:/Assets/A/Wind.mp3"],
            "prompts": [
                "Studio Ghibli style, dark cozy bedroom at night, heavy rain outside",
                "Studio Ghibli style, peaceful abandoned temple, glowing moon",
                "Studio Ghibli style, ancient library, single candle burning",
                "Studio Ghibli style, high mountain peak, starry night sky"
            ],
        },
    },
    "architect": {
        "desc": "V29 Pure Architect: Hook + 6 段(强制例子/字数校验) + Outro, 静态背景渲染",
        "prompts": PROMPTS_ARCHITECT,
        "video_id": "rDdoUbCFn24",
        "base_path": "D:/AIGen/MasterFactory_V29",
        "default_mode": "render",
        "g_model": "gemini-2.5-pro", "o_model": "gpt-4o-mini",
        "voice": "en-AU-WilliamNeural", "voice_rate": "-15%", "voice_pitch": "-5Hz",
        "clean": "filler",
        "map_unit": ("words", 4000, True),
        "script_mode": "architect",
        "strip_markdown": True,
        "render": "simple",
        "assets": {
            "videos": ["D:/Assets/V/wind.mp4", "D:/Assets/V/bedroom.mp4", "D:/Assets/V/rain.mp4", "D:/Assets/V/tent.mp4"],
            "audios": ["D:/Assets/A/wind.mp3", "D:/Assets/A/bedroom.mp3", "D:/Assets/A/rain.mp3", "D:/Assets/A/tent.mp3"],
            "prompts": [
                "Studio Ghibli style, cozy bedroom at night, windy snow outside",
                "Studio Ghibli style, warm livingroom with fireplace, rainy night outside",
                "Studio Ghibli style, forest cabin with light strings, starry night sky",
                "Studio Ghibli style, corner desk with candle light, windy leaves outside"
            ],
        },
    },
    "long": {
        "desc": "V90 Ultimate: 导演矩阵 + 生图 + 动画 + 母带 + NVENC + YouTube 上传",
        "prompts": PROMPTS_LONG,
        "video_id": "rOYlOdDgYUU",
        "base_path": "D:/AIGen/MasterFactory_V49",
        "default_mode": "script",
        "g_model": "gemini-2.5-pro", "o_model": "gpt-4o-mini",
        "voice": "en-GB-SoniaNeural", "voice_rate": "-20%", "voice_pitch": "-10Hz",
        "clean": "basic",
        "map_unit": ("chars", 6000, False),
        "script_mode": "long",
        "strip_markdown": False,
        "render": "matrix",
        "assets": {
            "audios": ["D:/Assets/A/rain.mp3", "D:/Assets/A/wind.mp3"],
            "overlays": ["D:/Assets/V/ghibli_dust.mp4", "D:/Assets/V/light_rays.mp4"],
        },
    },
}

PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 5.0, "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -18.0, "COMP_RATIO": 3.0, "LIMIT_DB": -3.0,
}
RUNNINGHUB_CONFIG = {"WF_T2I": "2014487614874718210", "T2I_NODE": "111"}
YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secret.json'
TARGET_WORDS = 600
MIN_REQUIRED_WORDS = 450
MAX_RETRIES = 3
RETRY_DELAY = 2


class Ctx:
    """运行期上下文"""
    preset = None
    args = None
    assets = {}


# =====================================================================
# 4. 工具
# =====================================================================
def log_status(stage: str, msg: str, status: str = "INFO"):
    time_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{time_str}] [{stage:<10}] [{status:<5}] {msg}")


def save_file(filepath: str, content: str) -> bool:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        log_status("FILE", f"Saved successfully: {os.path.basename(filepath)}", "OK")
        return True
    except Exception as e:
        log_status("FILE", f"Failed to save {os.path.basename(filepath)}: {e}", "ERROR")
        return False


def safe_folder_name(topic: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", topic)[:30].strip()


def extract_image_url(data) -> str:
    keys = ['fileUrl', 'url', 'image_url', 'file_url']
    if isinstance(data, dict):
        for k, v in data.items():
            if k in keys and isinstance(v, str) and v.startswith('http'):
                return v
            res = extract_image_url(v)
            if res:
                return res
    elif isinstance(data, list):
        for item in data:
            res = extract_image_url(item)
            if res:
                return res
    return ""


def text_wrap_for_image(text: str, font, max_width: int):
    lines, words = [], text.split()
    while words:
        line = ''
        while words and font.getlength(line + words[0]) <= max_width:
            line += (words.pop(0) + ' ')
        lines.append(line.strip())
    return lines


def get_text_paragraphs(master_script: str) -> list:
    return [p.strip() for p in master_script.split('\n\n') if len(p.strip()) > 20]


def clean_md(text: str, full: bool = True) -> str:
    """原脚本的 Markdown 清理: ** / # / '- ' (full=False 时不清理 '- ')"""
    text = text.replace("**", "").replace("#", "")
    return text.replace("- ", "") if full else text


def setup_session(base_path: str) -> str:
    try:
        os.makedirs(base_path, exist_ok=True)
        session_dir = os.path.join(base_path, datetime.now().strftime('%Y%m%d_%H%M'))
        os.makedirs(session_dir, exist_ok=True)
        log_status("ENV", f"Workspace created at {session_dir}", "OK")
        return session_dir
    except Exception as e:
        log_status("ENV", f"Failed to create workspace: {e}", "ERROR")
        return ""


# =====================================================================
# 5. 外部 API
# =====================================================================
def _retrying(fn):
    from tenacity import retry, stop_after_attempt, wait_exponential
    return retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)(fn)


async def robust_gemini_call(prompt: str) -> str:
    from google import genai

    @_retrying
    async def _call():
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        res = await asyncio.to_thread(client.models.generate_content, model=Ctx.args.g_model, contents=prompt)
        return res.text
    return await _call()


async def robust_openai_call(prompt: str, json_mode: bool = False) -> str:
    from openai import AsyncOpenAI

    @_retrying
    async def _call():
        o_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        kw = {"response_format": {"type": "json_object"}} if json_mode else {}
        res = await o_client.chat.completions.create(
            model=Ctx.args.o_model, messages=[{"role": "user", "content": prompt}], **kw)
        return res.choices[0].message.content
    return await _call()


def fetch_transcript_raw(video_id: str) -> list:
    """兼容多个 youtube_transcript_api 版本: fetch() -> get_transcript() -> list_transcripts()"""
    from youtube_transcript_api import YouTubeTranscriptApi
    errors = []
    try:
        return YouTubeTranscriptApi().fetch(video_id, languages=['en']).to_raw_data()
    except Exception as e:
        errors.append(f"fetch: {e}")
    try:
        return YouTubeTranscriptApi.get_transcript(video_id)
    except Exception as e:
        errors.append(f"get_transcript: {e}")
    try:
        return YouTubeTranscriptApi.list_transcripts(video_id).find_transcript(['en']).fetch()
    except Exception as e:
        errors.append(f"list_transcripts: {e}")
    log_status("SOURCE", "Transcript fetch failed: " + " | ".join(errors), "ERROR")
    return []


def clean_transcript(raw_ts: list, mode: str) -> str:
    log_status("CLEAN", "Cleaning transcript...", "INFO")
    try:
        texts = [re.sub(r'\[.*?\]', '', e['text'] if isinstance(e, dict) else e.text) for e in raw_ts]
        full_text = " ".join(texts)
        if mode == "basic":                               # V90
            return " ".join(full_text.split())
        for f in [r'\bum\b', r'\buh\b', r'\byou know\b']:  # V18 / V29
            full_text = re.sub(f, '', full_text, flags=re.IGNORECASE)
        words = re.sub(r'\s+', ' ', full_text).strip().split()
        if len(words) > 25000:
            log_status("CLEAN", "Truncating to 25000 words.", "WARN")
            words = words[:25000]
        log_status("CLEAN", f"Final length: {len(words)} words", "OK")
        return " ".join(words)
    except Exception as e:
        log_status("CLEAN", f"Cleaning failed: {e}", "ERROR")
        return ""


# =====================================================================
# 6. Map-Reduce 认知层
# =====================================================================
def split_text(text: str, unit: str, size: int):
    if unit == "words":
        words = text.split()
        return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    return [text[i:i + size] for i in range(0, len(text), size)]


async def map_insights(clean_text: str, session_dir: str) -> str:
    P = Ctx.preset["prompts"]
    unit, size, concurrent = Ctx.preset["map_unit"]
    save_file(os.path.join(session_dir, "1_clean_transcript.txt"), clean_text)
    chunks = split_text(clean_text, unit, size)
    log_status("MAP", f"Processing {len(chunks)} chunks ({'concurrently' if concurrent else 'sequentially'})...", "INFO")

    async def map_chunk(c):
        try:
            return await robust_gemini_call(P["STEP1_MAP"].format(chunk=c))
        except Exception as e:
            log_status("MAP", f"Chunk generation error: {e}", "ERROR")
            return ""

    if concurrent:
        results = await asyncio.gather(*[map_chunk(c) for c in chunks])
        combined = "\n---\n".join(t for t in results if t)
    else:
        results = []
        for c in chunks:
            r = await map_chunk(c)
            if not r:
                return ""
            results.append(r)
        combined = "\n".join(results)

    if not combined.strip():
        log_status("MAP", "No insights extracted.", "ERROR")
        return ""
    save_file(os.path.join(session_dir, "2_map_insights_pool.txt"), combined)
    log_status("MAP", "Global map insights extracted.", "OK")
    return combined


async def reduce_concepts(insights: str, session_dir: str):
    """返回 (topic, concepts, folder)"""
    P = Ctx.preset["prompts"]
    log_status("REDUCE", "Deduplicating concepts...", "INFO")
    try:
        res = await robust_gemini_call(P["STEP2_REDUCE"].format(insights=insights))
        m = re.search(r'\{.*\}', res, re.DOTALL)
        data = json.loads(m.group()) if m else json.loads(res)
        topic = data.get("topic", "Unknown Topic")
        concepts = data.get("concepts", [])
        if not concepts:
            log_status("REDUCE", "Concepts list is empty.", "ERROR")
            return "", [], ""
        log_status("REDUCE", f"Topic discovered: {topic}", "OK")
        folder = os.path.join(session_dir, safe_folder_name(topic))
        os.makedirs(folder, exist_ok=True)
        save_file(os.path.join(folder, "3_reduce_principles.json"),
                  json.dumps({"topic": topic, "concepts": concepts}, indent=4, ensure_ascii=False))
        if Ctx.preset["script_mode"] == "long":
            save_file(os.path.join(folder, "0_visual_anchor.txt"), P["VISUAL_ANCHOR_GEN"])
        return topic, concepts, folder
    except Exception as e:
        log_status("REDUCE", f"Reduce phase failed: {e}", "ERROR")
        return "", [], ""


def load_cached_plan(folder: str):
    try:
        with open(os.path.join(folder, "3_reduce_principles.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        topic = data.get("topic", data.get("Topic", "Unknown"))
        concepts = data.get("concepts", data.get("Concepts", []))
        log_status("CACHE", f"Loaded plan from: {folder}", "OK")
        return topic, concepts
    except Exception as e:
        log_status("CACHE", f"Plan load failed: {e}", "ERROR")
        return "", []


# =====================================================================
# 7. 文案生成 (三种模式)
# =====================================================================
async def script_dense(topic: str, concepts: list) -> str:
    """V18: 逐概念, 不足 500 词 CONTINUE 一次"""
    P = Ctx.preset["prompts"]
    master = ""
    log_status("SCRIPT", f"Expanding {len(concepts)} deduplicated concepts...", "INFO")
    for i, c in enumerate(concepts):
        point, details = c.get('point', ''), c.get('details', '')
        log_status("SCRIPT", f"Processing Seg {i+1}/{len(concepts)}: {point[:30]}...", "INFO")
        try:
            text = clean_md(await robust_openai_call(
                P["STEP3_SCRIPT_SINGLE"].format(topic=topic, point=point, details=details)))
            wc = len(text.split())
            log_status("SCRIPT", f"Seg {i+1} initial words: {wc}", "OK")
            if wc < 500:
                log_status("SCRIPT", f"Seg {i+1} is under 500 words. Expanding...", "WARN")
                more = clean_md(await robust_openai_call(
                    P["STEP3_SCRIPT_CONTINUE"].format(text=text[-500:])), full=False)
                text += f" ... {more}"
                log_status("SCRIPT", f"Seg {i+1} expanded to {len(text.split())} words.", "OK")
            master += f"\n\n{text}\n\n"
        except Exception as e:
            log_status("SCRIPT", f"Failed generating Seg {i+1}: {e}", "ERROR")
    return master


async def script_architect(topic: str, concepts: list) -> str:
    """V29: Hook + 逐概念(字数校验重写) + Outro"""
    P = Ctx.preset["prompts"]
    master = ""
    try:
        concepts_str = "\n".join(f"- {c.get('point', 'Concept')}" for c in concepts)
        hook = clean_md(await robust_openai_call(P["STEP3_HOOK"].format(topic=topic, concepts=concepts_str)))
        master += f"{hook}\n\n"
        log_status("SCRIPT", "Hook generated successfully.", "OK")
    except Exception as e:
        log_status("SCRIPT", f"Hook generation failed: {e}", "ERROR")
        return ""

    total = len(concepts)
    for i, c in enumerate(concepts):
        prompt = P["STEP3_SCRIPT_SINGLE"].format(
            topic=topic, point=c.get('point', ''), details=c.get('details', ''),
            example=c.get('specific_example', 'A relatable scenario.'), target_words=TARGET_WORDS)
        seg = ""
        for attempt in range(1, MAX_RETRIES + 1):
            log_status("SCRIPT", f"Seg {i+1}/{total} Attempt {attempt} starting...", "INFO")
            try:
                text = clean_md(await robust_openai_call(prompt))
                wc = len(text.split())
                if wc >= MIN_REQUIRED_WORDS:
                    log_status("SCRIPT", f"Judgment passed: Seg {i+1} generated {wc} words.", "OK")
                    seg = f"{text}\n\n"
                    break
                log_status("SCRIPT", f"Judgment failed: Seg {i+1} short ({wc} < {MIN_REQUIRED_WORDS}). Discarding.", "WARN")
            except Exception as e:
                log_status("SCRIPT", f"Exception on Seg {i+1} attempt {attempt}: {e}", "ERROR")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
        if not seg:
            log_status("SCRIPT", f"Critical Failure: Seg {i+1} exhausted retries. Continuing anyway...", "ERROR")
        master += seg

    try:
        outro = clean_md(await robust_openai_call(P["STEP3_OUTRO"].format(topic=topic)))
        master += f"{outro}\n\n"
    except Exception as e:
        log_status("SCRIPT", f"Outro generation failed: {e}", "ERROR")
    return master


async def script_long(topic: str, concepts: list) -> str:
    """V90: Hook + 逐概念(情绪曲线) + Outro (禁用 you/ellipsis)"""
    P = Ctx.preset["prompts"]
    try:
        hook = await robust_openai_call(P["STEP3_HOOK"].format(topic=topic, concepts=str(concepts)))
        parts = []
        for idx, p in enumerate(concepts):
            tone = EMOTION_CURVE[idx % len(EMOTION_CURVE)]
            parts.append(await robust_openai_call(P["STEP3_SCRIPT_SINGLE"].format(
                topic=topic, point=p.get('point', ''), details=p.get('details', ''),
                example=p.get('specific_example', ''), emotion_tone=tone,
                target_words=TARGET_WORDS // len(concepts))))
        outro = await robust_openai_call(P["STEP3_OUTRO"].format(topic=topic))
        return f"{hook}\n\n" + "\n\n".join(parts) + f"\n\n{outro}"
    except Exception as e:
        log_status("SCRIPT", f"Script generation failed: {e}", "ERROR")
        return ""


async def generate_script(topic: str, concepts: list, folder: str) -> str:
    log_status("SCRIPT", "Drafting Master Script...", "INFO")
    mode = Ctx.preset["script_mode"]
    fn = {"dense": script_dense, "architect": script_architect, "long": script_long}[mode]
    script = await fn(topic, concepts)
    if not script.strip():
        return ""
    wc = len(script.split())
    log_status("PIPELINE", f"Master script assembled! Total Length: {wc} words.", "OK")
    save_file(os.path.join(folder, "master_script.txt"), script)
    save_file(os.path.join(folder, "4_script_review.txt"),
              f"--- TITLE: {topic} ---\n--- TOTAL WORDS: {wc} ---\n{script}")
    return script


# =====================================================================
# 8. 元数据 / 上传
# =====================================================================
async def generate_metadata(topic: str, folder: str) -> dict:
    P = Ctx.preset["prompts"]
    log_status("SEO", "Generating YouTube Metadata...", "INFO")
    try:
        if "STEP4_METADATA" in P:      # V90
            res = await robust_openai_call(P["STEP4_METADATA"].format(topic=topic))
            m = re.search(r'\{.*\}', res, re.DOTALL)
            data = json.loads(m.group()) if m else json.loads(res)
        else:                          # V18
            res = await robust_openai_call(P["SEO_INLINE"].format(topic=topic), json_mode=True)
            data = json.loads(res)
        with open(os.path.join(folder, "youtube_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_status("SEO", "Metadata saved.", "OK")
        return data
    except Exception as e:
        log_status("SEO", f"Metadata generation failed: {e}", "WARN")
        return {"title": topic, "description": "Audio masterclass.", "tags": "education"}


def get_authenticated_service():
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', YOUTUBE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)


def upload_video_to_youtube(file_path: str, title: str, description: str, tags):
    from googleapiclient.http import MediaFileUpload
    log_status("UPLOAD", f"Starting upload for: {title}", "INFO")
    try:
        youtube = get_authenticated_service()
        body = {
            'snippet': {'title': title, 'description': description, 'tags': tags, 'categoryId': '27'},
            'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False},
        }
        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log_status("UPLOAD", f"Upload progress: {int(status.progress() * 100)}%", "INFO")
        log_status("UPLOAD", f"Upload Complete! Video ID: {response.get('id')}", "SUCCESS")
    except Exception as e:
        log_status("UPLOAD", f"Upload failed: {e}", "ERROR")


# =====================================================================
# 9. 渲染 A: simple (V18 / V29) —— 整段 TTS + 封面 + 背景循环混流
# =====================================================================
async def generate_tts_audio(script: str, folder: str) -> str:
    import edge_tts
    pr = Ctx.preset
    log_status("TTS", "Generating audio pieces...", "INFO")
    parts = [script[i:i + 800] for i in range(0, len(script), 800)]
    flist = []
    for i, p in enumerate(parts):
        p_path = os.path.join(folder, f"p{i}.mp3")
        try:
            await edge_tts.Communicate(p, pr["voice"], rate=pr["voice_rate"], pitch=pr["voice_pitch"]).save(p_path)
            flist.append(p_path)
        except Exception as e:
            log_status("TTS", f"Segment {i} generation error: {e}", "ERROR")
            return ""
    merged = os.path.join(folder, "voice_full.mp3")
    clist = os.path.join(folder, "clist.txt")
    try:
        with open(clist, "w", encoding="utf-8") as f:
            for p in flist:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', clist, '-c', 'copy', merged],
                       capture_output=True, check=True)
        log_status("TTS", "Audio rendering complete.", "OK")
        return merged
    except subprocess.CalledProcessError as e:
        log_status("TTS", f"FFmpeg concat error: {e.stderr.decode() if e.stderr else str(e)}", "ERROR")
        return ""


async def generate_video_cover(topic: str, img_prompt: str, folder: str) -> str:
    from google import genai
    from PIL import Image, ImageDraw, ImageFont
    log_status("COVER", f"Generating cover for: {topic[:20]}...", "INFO")
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = await asyncio.to_thread(client.models.generate_image, model="gemini-3-flash-image", prompt=img_prompt)
        bg_p = os.path.join(folder, "bg.png")
        response.save(bg_p)
        img = Image.open(bg_p).resize((1280, 720))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 60)
        except OSError:
            font = ImageFont.load_default()
        lines = text_wrap_for_image(f"AUDIO MASTERCLASS:\n{topic.upper()}", font, 1100)
        y_pos = 600 - (len(lines) * 80)
        for line in lines:
            draw.text((80, y_pos), line, fill=(255, 255, 255), font=font, stroke_width=4, stroke_fill=(0, 0, 0))
            y_pos += 80
        thumb_path = os.path.join(folder, "thumb.jpg")
        img.convert('RGB').save(thumb_path)
        log_status("COVER", "Thumbnail successfully created.", "OK")
        return thumb_path
    except Exception as e:
        # 原脚本此处失败会中止整个渲染; 封面只是缩略图, 这里降级为警告
        log_status("COVER", f"Generation error (non-fatal): {e}", "WARN")
        return ""


async def render_simple(topic: str, script: str, folder: str):
    assets = Ctx.assets
    selected_v = random.choice(assets["videos"])
    selected_a = random.choice(assets["audios"])
    selected_p = random.choice(assets["prompts"])

    voice_path = await generate_tts_audio(script, folder)
    await generate_video_cover(topic, selected_p, folder)
    if not voice_path:
        log_status("PIPELINE", "Voice track missing. Aborting render.", "ERROR")
        return

    final_v = os.path.join(folder, "final.mp4")
    cmd = ['ffmpeg', '-y', '-stream_loop', '-1', '-i', selected_v, '-i', voice_path, '-stream_loop', '-1', '-i', selected_a,
           '-filter_complex', "[1:a]showwaves=s=1280x100:mode=line:colors=white@0.2[w]; [0:v][w]overlay=0:H-100[v]; [1:a]volume=1.2[va]; [2:a]volume=0.25[ba]; [va][ba]amix=inputs=2:duration=first[a]",
           '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'ultrafast', '-shortest', final_v]
    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode == 0:
            log_status("PIPELINE", f"FFmpeg Render Success: {final_v}", "SUCCESS")
            return final_v
        log_status("PIPELINE", f"FFmpeg Error: {stderr.decode()}", "ERROR")
    except Exception as e:
        log_status("PIPELINE", f"Render exception: {e}", "ERROR")
    return None


# =====================================================================
# 10. 渲染 B: matrix (V90) —— 导演矩阵 + 生图 + 分段动画
# =====================================================================
class MatrixDirector:
    def __init__(self):
        self.last_state = {"cast": None, "loc": None, "cam": None, "meta": None}

    def get_unique(self, pool: list, key: str) -> str:
        available = [x for x in pool if x != self.last_state[key]] or pool
        choice = random.choice(available)
        self.last_state[key] = choice
        return choice

    def get_visual_config(self, forced_type: str) -> dict:
        config = {"type": forced_type, "camera": self.get_unique(CAMERA_POOL, "cam")}
        if forced_type == "HUMAN":
            config["location"] = self.get_unique(LOCATION_POOL, "loc")
            config["subject"] = self.get_unique(CASTING_POOL, "cast")
        elif forced_type == "ENVIRONMENT":
            config["location"] = self.get_unique(LOCATION_POOL, "loc")
            config["subject"] = ""
        elif forced_type == "SYMBOLIC":
            config["location"] = ""
            config["subject"] = self.get_unique(METAPHOR_POOL, "meta")
        return config


def get_visual_type(idx: int, total: int) -> str:
    if idx == 0:
        return "ENVIRONMENT"
    if idx == total - 1:
        return "SYMBOLIC"
    if idx % 3 == 1:
        return "HUMAN"
    return random.choice(["ENVIRONMENT", "SYMBOLIC"])


async def process_single_segment(idx, para_text, visual_anchor, folder, movement, forced_type, v_config):
    import edge_tts
    import requests
    from pydub import AudioSegment
    from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
    from pedalboard.io import AudioFile

    pr, P, args = Ctx.preset, Ctx.preset["prompts"], Ctx.args
    log_status("SEGMENT", f"--- Building Block {idx:02d} | [{forced_type}] ---", "INFO")
    seg_dir = os.path.join(folder, "segments")
    os.makedirs(seg_dir, exist_ok=True)
    raw_wav = os.path.join(seg_dir, f"s{idx:02d}_raw.mp3")
    mastered_wav = os.path.join(seg_dir, f"s{idx:02d}_mastered.wav")
    img_path = os.path.join(seg_dir, f"s{idx:02d}_img.png")
    clip_path = os.path.join(seg_dir, f"s{idx:02d}_clip.mp4")

    # 1. AUDIO
    duration = 0.0
    if args.reuse_tts and os.path.exists(mastered_wav):
        try:
            duration = len(AudioSegment.from_file(mastered_wav)) / 1000.0
            log_status("AUDIO", f"Block {idx:02d} Reusing cached audio.", "OK")
        except Exception as e:
            log_status("AUDIO", f"Block {idx:02d} Cache read failed: {e}", "ERROR")
    else:
        try:
            log_status("AUDIO", f"Block {idx:02d} Synthesizing TTS...", "INFO")
            await edge_tts.Communicate(para_text, pr["voice"], rate=pr["voice_rate"], pitch=pr["voice_pitch"]).save(raw_wav)
            with AudioFile(raw_wav) as f:
                audio_data, samplerate = f.read(f.frames), f.samplerate
            board = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=150, gain_db=PEDALBOARD_CONFIG["LOW_SHELF_GAIN"]),
                HighShelfFilter(cutoff_frequency_hz=6000, gain_db=PEDALBOARD_CONFIG["HIGH_SHELF_GAIN"]),
                Compressor(threshold_db=PEDALBOARD_CONFIG["COMP_THRESHOLD"], ratio=PEDALBOARD_CONFIG["COMP_RATIO"]),
                Gain(gain_db=2.0),
                Limiter(threshold_db=PEDALBOARD_CONFIG["LIMIT_DB"])
            ])
            processed = board(audio_data, samplerate)
            with AudioFile(mastered_wav, 'w', samplerate, processed.shape[0]) as f:
                f.write(processed)
            duration = len(AudioSegment.from_file(mastered_wav)) / 1000.0
            log_status("AUDIO", f"Block {idx:02d} Audio mastering complete.", "OK")
        except Exception as e:
            log_status("AUDIO", f"Block {idx:02d} Processing failed: {e}", "ERROR")
            return "", ""

    # 2. IMAGE
    if not os.path.exists(img_path):
        try:
            log_status("IMAGE", f"Block {idx:02d} Routing prompt via Matrix ({forced_type})...", "INFO")
            if forced_type == "HUMAN":
                full_prompt = P["SCENE_PROMPT_HUMAN"].format(
                    forced_visual_type=forced_type, location=v_config["location"],
                    camera=v_config["camera"], subject=v_config["subject"], text=para_text, anchor=visual_anchor)
            elif forced_type == "ENVIRONMENT":
                full_prompt = P["SCENE_PROMPT_ENVIRONMENT"].format(
                    forced_visual_type=forced_type, location=v_config["location"],
                    camera=v_config["camera"], text=para_text, anchor=visual_anchor)
            else:
                full_prompt = P["SCENE_PROMPT_SYMBOLIC"].format(
                    forced_visual_type=forced_type, subject=v_config["subject"],
                    camera=v_config["camera"], text=para_text, anchor=visual_anchor)
            img_prompt = (await robust_gemini_call(full_prompt)).replace("\n", "").strip()
            with open(os.path.join(folder, "visual_prompts_log.txt"), "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [Block {idx:02d} | Routing: {forced_type}]\n{img_prompt}\n\n")
        except Exception as e:
            log_status("IMAGE", f"Block {idx:02d} Prompt generation failed: {e}", "ERROR")
            return "", mastered_wav

        rh_key = os.getenv("RUNNINGHUB_API_KEY")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {rh_key}"}
        task_id = None
        log_status("IMAGE", f"Block {idx:02d} Requesting T2I...", "INFO")
        for _ in range(60):
            try:
                payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": img_prompt}]}
                resp = requests.post(f"https://www.runninghub.ai/openapi/v2/run/workflow/{RUNNINGHUB_CONFIG['WF_T2I']}",
                                     headers=headers, json=payload, timeout=60)
                r_json = resp.json()
                if str(r_json.get("errorCode")) == "421":
                    await asyncio.sleep(10)
                    continue
                task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
                if task_id:
                    break
            except Exception as e:
                log_status("IMAGE", f"Block {idx:02d} API request error: {e}", "WARN")
                await asyncio.sleep(5)

        img_url = ""
        if task_id:
            t0 = time.time()
            while time.time() - t0 < 600:
                try:
                    q = requests.post("https://www.runninghub.ai/openapi/v2/query", headers=headers,
                                      json={"taskId": task_id}, timeout=60).json()
                    status = (q.get("status") or q.get("data", {}).get("status", "")).upper()
                    if status == "SUCCESS":
                        img_url = extract_image_url(q)
                        break
                    elif status == "FAILED":
                        log_status("IMAGE", f"Block {idx:02d} T2I Task failed on server.", "ERROR")
                        break
                except Exception:
                    pass
                await asyncio.sleep(10)

        if img_url:
            try:
                with requests.get(img_url, stream=True, timeout=60) as r:
                    with open(img_path, "wb") as f:
                        shutil.copyfileobj(r.raw, f)
                log_status("IMAGE", f"Block {idx:02d} Image downloaded.", "OK")
            except Exception as e:
                log_status("IMAGE", f"Block {idx:02d} Download failed: {e}", "ERROR")
                return "", mastered_wav
        else:
            log_status("IMAGE", f"Block {idx:02d} Timeout waiting for URL.", "ERROR")

    # 3. FFMPEG
    if not os.path.exists(img_path):
        return "", mastered_wav

    log_status("FFMPEG", f"Block {idx:02d} Rendering video segment...", "INFO")
    overlays = Ctx.assets.get("overlays", [])
    selected_overlay = random.choice(overlays) if overlays else None
    fps = 25
    frames = max(1, int(duration * fps))
    base_filter = "crop=1920:1080,scale=3840:2160"
    end_filter = "scale=1920:1080"
    if movement == "zoom_in":
        zp = f"{base_filter},zoompan=z='1.001+0.15*(on/{frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end_filter}"
    elif movement == "zoom_out":
        zp = f"{base_filter},zoompan=z='1.15-0.15*(on/{frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end_filter}"
    elif movement == "pan_right":
        zp = f"{base_filter},zoompan=z='1.1+0.0001*on':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end_filter}"
    else:
        zp = f"{base_filter},zoompan=z='1.1+0.0001*on':x='(iw-iw/zoom)*(1 - on/{frames})':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end_filter}"

    enc = args.encoder
    enc_opts = ['-preset', 'p4'] if 'nvenc' in enc else ['-preset', 'veryfast']
    if selected_overlay and os.path.exists(selected_overlay):
        cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path,
               '-stream_loop', '-1', '-t', str(duration), '-i', selected_overlay,
               '-filter_complex', f"[0:v]format=yuv420p,{zp},format=gbrp[bg];[1:v]format=yuv420p,scale=1920x1080,format=gbrp[ovl];[bg][ovl]blend=all_mode='screen':all_opacity=0.6,format=yuv420p[v]",
               '-map', '[v]', '-c:v', enc, *enc_opts, '-pix_fmt', 'yuv420p', clip_path]
    else:
        cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path,
               '-vf', f"format=yuv420p,{zp}", '-c:v', enc, *enc_opts, '-pix_fmt', 'yuv420p', clip_path]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        log_status("FFMPEG", f"Block {idx:02d} Video segment encoded.", "OK")
    except Exception as e:
        log_status("FFMPEG", f"Block {idx:02d} Encoding failed: {e}", "ERROR")
        return "", mastered_wav
    await asyncio.sleep(1)
    return clip_path, mastered_wav


def assemble_final_masterpiece(valid_clips: list, valid_audios: list, folder: str):
    log_status("STUDIO", f"Assembling {len(valid_clips)} blocks into final cut...", "INFO")
    v_concat = os.path.join(folder, "concat_v.txt")
    a_concat = os.path.join(folder, "concat_a.txt")
    try:
        with open(v_concat, "w") as f:
            for p in valid_clips:
                f.write(f"file '{os.path.abspath(p)}'\n")
        with open(a_concat, "w") as f:
            for p in valid_audios:
                f.write(f"file '{os.path.abspath(p)}'\n")
        video_track = os.path.join(folder, "master_video.mp4")
        audio_track = os.path.join(folder, "master_audio.wav")
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', video_track], capture_output=True, check=True)
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', audio_track], capture_output=True, check=True)

        final_output = os.path.join(folder, "FINAL_MASTERPIECE.mp4")
        audios_list = Ctx.assets.get("audios", [])
        bgm = random.choice(audios_list) if audios_list else None
        enc = Ctx.args.encoder
        enc_opts = ['-preset', 'p4'] if 'nvenc' in enc else ['-preset', 'veryfast']
        if bgm and os.path.exists(bgm):
            cmd_mux = ['ffmpeg', '-y', '-i', video_track, '-i', audio_track, '-stream_loop', '-1', '-i', bgm,
                       '-filter_complex', "[1:a]volume=1.0[va]; [2:a]volume=0.25[ba]; [va][ba]amix=inputs=2:duration=first[a]",
                       '-map', '0:v', '-map', '[a]', '-c:v', enc, *enc_opts, '-c:a', 'aac', '-shortest', final_output]
        else:
            cmd_mux = ['ffmpeg', '-y', '-i', video_track, '-i', audio_track,
                       '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_output]
        subprocess.run(cmd_mux, capture_output=True, check=True)
        log_status("SYSTEM", f"=== PIPELINE COMPLETE! FILE: {final_output} ===", "SUCCESS")
        return final_output
    except Exception as e:
        log_status("STUDIO", f"Final assembly failed: {e}", "ERROR")
        return None


def cleanup_temp_files(folder: str):
    try:
        seg_dir = os.path.join(folder, "segments")
        if os.path.exists(seg_dir):
            shutil.rmtree(seg_dir, ignore_errors=True)
        for f in ["concat_v.txt", "concat_a.txt", "master_video.mp4", "master_audio.wav", "bg.png"]:
            fp = os.path.join(folder, f)
            if os.path.exists(fp):
                os.remove(fp)
    except Exception as e:
        log_status("CLEANUP", f"Cleanup failed: {e}", "WARN")


async def render_matrix(topic: str, script: str, folder: str):
    P = Ctx.preset["prompts"]
    visual_anchor = P["VISUAL_ANCHOR_GEN"]
    anchor_file = os.path.join(folder, "0_visual_anchor.txt")
    if os.path.exists(anchor_file):
        with open(anchor_file, "r", encoding="utf-8") as f:
            visual_anchor = f.read().strip() or visual_anchor

    paragraphs = get_text_paragraphs(script)
    total = len(paragraphs)
    log_status("PIPELINE", f"Ready to process {total} execution blocks.", "INFO")
    director = MatrixDirector()
    valid_clips, valid_audios = [], []
    prev_mv = None
    mv_pool = ["zoom_in", "zoom_out", "pan_right", "pan_left"]
    for idx, para in enumerate(paragraphs):
        forced_type = get_visual_type(idx, total)
        v_config = director.get_visual_config(forced_type)
        movement = random.choice([m for m in mv_pool if m != prev_mv])
        prev_mv = movement
        v_path, a_path = await process_single_segment(idx + 1, para, visual_anchor, folder, movement, forced_type, v_config)
        if v_path and a_path:
            valid_clips.append(v_path)
            valid_audios.append(a_path)
    if not valid_clips:
        log_status("SYSTEM", "No valid media to assemble.", "ERROR")
        return None
    final = assemble_final_masterpiece(valid_clips, valid_audios, folder)
    if Ctx.args.cleanup:
        cleanup_temp_files(folder)
    return final


# =====================================================================
# 11. 主控
# =====================================================================
async def pipeline(args):
    pr = Ctx.preset
    log_status("SYSTEM", f"--- MASTERCLASS FACTORY [{args.preset}] START ---", "START")

    # --- 计划 (plan) ---
    if args.reuse_folder:
        if not os.path.exists(args.reuse_folder):
            log_status("SYSTEM", "--reuse-folder does not exist!", "ERROR")
            return
        folder = args.reuse_folder
        topic, concepts = load_cached_plan(folder)
        if not concepts:
            return
    else:
        session_dir = setup_session(args.base_path or pr["base_path"])
        if not session_dir:
            return
        log_status("SOURCE", f"Fetching transcript for {args.video}...", "INFO")
        raw = fetch_transcript_raw(args.video)
        if not raw:
            log_status("SYSTEM", "Transcript data missing.", "STOP")
            return
        clean_text = clean_transcript(raw, pr["clean"])
        if not clean_text:
            log_status("SYSTEM", "Cleaned text is empty.", "STOP")
            return
        insights = await map_insights(clean_text, session_dir)
        if not insights:
            log_status("SYSTEM", "Map insights failed.", "STOP")
            return
        topic, concepts, folder = await reduce_concepts(insights, session_dir)
        if not concepts:
            log_status("SYSTEM", "Reduce principles failed.", "STOP")
            return

    # --- 文案 ---
    script_file = os.path.join(folder, "master_script.txt")
    if args.reuse_script and os.path.exists(script_file):
        with open(script_file, "r", encoding="utf-8") as f:
            script = f.read().strip()
        log_status("CACHE", "Loaded Master Script.", "OK")
    else:
        script = await generate_script(topic, concepts, folder)
    if not script:
        log_status("SYSTEM", "Script generation failed.", "STOP")
        return

    if args.mode == "script":
        log_status("SYSTEM", "Script mode: halting before render.", "STOP")
        if pr["script_mode"] == "dense" or args.upload:
            await generate_metadata(topic, folder)
        return

    # --- 渲染 ---
    final = await (render_matrix if pr["render"] == "matrix" else render_simple)(topic, script, folder)

    # --- SEO / 上传 ---
    if args.upload:
        meta = await generate_metadata(topic, folder)
        if final and meta and os.path.exists(final):
            upload_video_to_youtube(final, meta.get("title", topic), meta.get("description", ""), meta.get("tags", []))
    log_status("SYSTEM", "--- FACTORY MISSION COMPLETE ---", "DONE")


def main():
    ap = argparse.ArgumentParser(description="Audio Masterclass Factory: dense(V18) / architect(V29) / long(V90)")
    ap.add_argument("--preset", choices=list(PRESETS), default="long")
    ap.add_argument("--list", action="store_true", help="列出预设")
    ap.add_argument("--video", default="", help="YouTube 视频 ID (默认取预设值)")
    ap.add_argument("--mode", choices=["script", "render"], default="", help="script 只出文案 / render 渲染成片")
    ap.add_argument("--base-path", default="")
    ap.add_argument("--reuse-folder", default="", help="复用已有主题目录(含 3_reduce_principles.json)")
    ap.add_argument("--reuse-script", action="store_true", help="复用目录中的 master_script.txt")
    ap.add_argument("--reuse-tts", action="store_true", help="(long) 复用已母带处理的音频")
    ap.add_argument("--upload", action="store_true", help="渲染后生成元数据并上传 YouTube (私享)")
    ap.add_argument("--cleanup", action="store_true", help="(long) 渲染后清理临时文件")
    ap.add_argument("--encoder", default="h264_nvenc", help="(long) 视频编码器, 无 NVIDIA 时用 libx264")
    ap.add_argument("--assets-json", default="", help="覆盖素材池的 JSON 文件")
    ap.add_argument("--g-model", default="")
    ap.add_argument("--o-model", default="")
    args = ap.parse_args()

    if args.list:
        for k, v in PRESETS.items():
            print(f"  {k:10s} {v['desc']}")
        return

    pr = PRESETS[args.preset]
    args.video = args.video or pr["video_id"]
    args.mode = args.mode or pr["default_mode"]
    args.g_model = args.g_model or pr["g_model"]
    args.o_model = args.o_model or pr["o_model"]
    Ctx.preset, Ctx.args = pr, args
    Ctx.assets = dict(pr["assets"])
    if args.assets_json:
        with open(args.assets_json, "r", encoding="utf-8") as f:
            Ctx.assets.update(json.load(f))

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(pipeline(args))
    except Exception as e:
        log_status("SYSTEM", f"Critical Pipeline Failure: {e}", "CRITICAL")


if __name__ == "__main__":
    main()
