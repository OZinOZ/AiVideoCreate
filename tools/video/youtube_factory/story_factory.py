# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches, too-many-instance-attributes, missing-docstring
"""
Story Factory (统一版) —— 合并自 story_compare.py (V89) / story.py (V98) / pretty.py (V99)

AI 睡前故事双语视频工厂:
  大纲(Gemini) -> 英文扩写(OpenAI) -> 中文改写(DeepSeek) -> 分镜 Prompt(Gemini)
  -> TTS(edge-tts)+母带处理(pedalboard) -> 生图(RunningHub) -> FFmpeg 缩放动画 -> 拼接 EN / CN 两条成片

预设 (--preset):
  classic  V89 "Artery Reconnected": 人物/风格/锚点/场景/镜头池 + 纯文本扩写
  story    V98 "Bugfix Edition":     术语表(glossary) + 结构化扩写(4段/块) + 中文术语注入
  pretty   V99 "Pet & Pretty":       固定主角 Aria + Marshmallow, 童话改编

所有 Prompt 保持原文。原脚本中的已知缺陷在此处已修复 (见 docs / 报告):
  * story/pretty/classic 生图接口 URL 被写成 markdown 链接 -> 已改为纯 URL
  * pretty 的 query 请求 json={{...}} 与缺失的 run_english_track/run_chinese_track -> 已使用统一实现

环境变量: OPENAI_API_KEY, GEMINI_API_KEY, RUNNINGHUB_API_KEY, 以及 DeepSeek 的 key
          (classic: DEEPSEEK_API_KEY / story,pretty: SILICONFLOW_API_KEY)
"""

import argparse
import asyncio
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# =====================================================================
# 1. 预设与配置
# =====================================================================
RUNNINGHUB_TIMEOUT_SEC = 600
API_POLL_INTERVAL_SEC = 10
HTTP_TIMEOUT_SEC = 60.0
RH_BASE = "https://www.runninghub.ai/openapi/v2"

RUNNINGHUB_CONFIG = {
    "KEY": os.getenv("RUNNINGHUB_API_KEY"),
    "WF_T2I": "2014487614874718210",
    "T2I_NODE": "111",
}

PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 5.0, "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -18.0, "COMP_RATIO": 3.0, "LIMIT_DB": -3.0,
}

# =====================================================================
# 2. 导演武器库 (classic 预设使用, 原文)
# =====================================================================
CHARACTER_POOL = [
    "A wandering star-catcher with glowing glass jars",
    "A sleepy little fox wearing a tiny red scarf",
    "An ancient, gentle tree spirit made of luminous moss",
    "A lonely clockmaker who crafts dreams into gears",
    "A quiet owl wearing a monocle reading ancient runes",
    "A cloud-herder riding a floating paper boat",
    "A tiny firefly knight with a dandelion shield",
    "A kind-hearted baker who bakes starlight into bread",
    "A moonbeam weaver working on a silver loom",
    "A young boy with a magical lantern that shows the future"
]

STYLE_POOL = [
    "A journey through a bioluminescent underground forest",
    "A slow float down a calm river of liquid silver",
    "A quiet night inside a giant, hollow glowing mushroom",
    "A peaceful walk on clouds that feel like cotton candy",
    "A cozy evening in a library where books whisper stories",
    "A serene flight through a sky painted with auroras",
    "A tranquil stay in a cottage made of crystallized sugar",
    "A sleepy underwater voyage in a glass submarine",
    "A gentle ride on a magical train crossing the milky way",
    "A quiet dusk in a garden where flowers chime like bells"
]

ANCHOR_POOL = [
    "Studio Ghibli animation style, beautiful vibrant colors, highly detailed, serene everyday life, natural sunlight, cinematic anime still.",
    "Traditional Chinese Classical Painting style, ink wash, elegant curves, misty mountains, profound artistic conception.",
    "Dunhuang mural art style, rich mineral colors, flying apsaras motif, vintage texture, mystical and holy.",
    "Impressionist painting, soft brush strokes, dreamy lighting, Claude Monet style, pastel colors.",
    "Watercolor illustration, soft blending, transparent colors, dreamy and light aesthetic, children's book style.",
    "Classic Oil Painting style, Rembrandt lighting, deep shadows, rich textures, timeless masterpiece.",
    "Ukiyo-e Japanese woodblock print style, flat areas of color, intricate patterns, Hokusai influence.",
    "Low Poly 3D render, minimalist, soft pastel ambient lighting, clean edges, tranquil atmosphere.",
    "Art Deco style, geometric elegance, gold and deep blue tones, vintage 1920s luxury.",
    "Cyberpunk style but peaceful, neon lights reflecting in puddles, soft glowing holograms, quiet futuristic night."
]

LOCATION_POOL = [
    "a quiet, rain-streaked empty train carriage",
    "a sun-drenched, dusty old kitchen corner",
    "a vast, quiet public library aisle",
    "a lonely bus shelter under a single streetlight",
    "an empty botanical greenhouse with glass panes"
]

CAMERA_POOL = [
    "Cinematic Wide Shot, capturing the scale of the environment",
    "Extreme Close-up, focusing on fine textures and micro-expressions",
    "Bird's-eye view from the ceiling, looking down at the layout",
    "Profile shot, capturing a thoughtful silhouette against the light",
    "Medium shot, perfectly balanced with natural leading lines"
]

# =====================================================================
# 3. Prompt (原文, 按预设分组)
# =====================================================================
PROMPTS_CLASSIC = {
    "GEMINI_OUTLINE": """
    PERSONA: You are a master storyteller specializing in sleep-inducing, deeply calming bedtime stories.
    
    TASK: Create an 8-paragraph story outline based on the inputs below.
    
    --- INPUTS ---
    - Core Fairy Tale: {story}
    - Main Character: {character}
    - Atmospheric Style: {style}
    
    --- STRUCTURAL RULES ---
    1. The story MUST be exactly 8 paragraphs long.
    2. Narrative Arc: Beginning (P1-P2), Plot Development (P3-P4), Gentle Conflict/Climax (P5-P6), Resolution and Sleepy Ending (P7-P8).
    3. Each paragraph outline should be approximately 200 words.
    4. ABSOLUTELY NO violence, blood, or high-stress situations. Keep conflicts extremely gentle (e.g., losing a glowing pebble, a mild rainstorm).
    
    --- OUTPUT FORMAT ---
    You MUST output ONLY a valid JSON array of exactly 8 strings. Do not include markdown formatting or json tags.
    Example:
    [
      "Paragraph 1 outline...",
      "Paragraph 2 outline...",
      ...
    ]
    """,

    "OPENAI_EXPAND": """
    PERSONA: You are a world-class hypnotherapist and bedtime story writer.
    
    TASK: Expand the following 200-word story outline paragraph into a deeply sensory, rich 600-word paragraph.
    
    --- OUTLINE PARAGRAPH ---
    {outline}
    
    --- RULES ---
    1. Tone: Extremely slow, hypnotic, calming, and reassuring.
    2. Focus on sensory details: the soft sound of wind, the gentle warmth of light, the slow rhythm of breathing.
    3. Use periods and commas strategically to force breathing pauses for the TTS engine.
    4. Target Length: ~600 words.
    5. NO ellipses (...), NO markdown formatting.
    """,

    "DEEPSEEK_REWRITE": """
    PERSONA: 你是一位顶级的中文 ASMR 睡眠故事文案大师。
    
    TASK: 将以下英文睡眠故事段落，改写为极其优美、符合中文母语习惯、极具助眠效果的中文文案。
    
    --- 英文原文 ---
    {english_text}
    
    --- 规则 ---
    1. 不要生硬翻译，必须进行本地化润色，词藻优美，语调和缓。
    2. 多使用具有画面感和通感（视觉、听觉、触觉）的词汇。
    3. 节奏要慢，多用逗号和句号来控制机器人的朗读呼吸感。
    4. 严禁包含任何暴力、血腥或让人紧张的情节。
    5. 纯文本输出，不要包含任何多余的解释，不要使用 Markdown 符号。
    """,

    "SCENE_PROMPT_GEMINI": """
    PERSONA: You are a cinematic visual executor.
    
    TASK: Integrate the provided SCRIPT SEGMENT into the FIXED VISUAL FRAMEWORK below.
    
    --- FIXED VISUAL FRAMEWORK ---
    - LOCATION: {location}
    - CAMERA: {camera}
    - OVERALL AESTHETIC: Follow the visual anchor exactly.
    
    --- SCRIPT SEGMENT ---
    {text}
    
    --- EXECUTION RULES ---
    1. Describe a beautiful, static scene based on the script segment.
    2. Output ONLY the final English image prompt string.
    3. You MUST append exactly [{anchor}] at the very end of your output.
    4. DO NOT use markdown.
    """
}

PROMPTS_STORY = {
    "GEMINI_OUTLINE": """
    PERSONA: You are a master storyteller specializing in sleep-inducing, deeply calming bedtime stories.
    TASK: Create an 8-paragraph story outline and extract a bilingual glossary based on the inputs below.
    
    --- INPUTS ---
    - Core Fairy Tale: {story}
    - Main Character: {character}
    - Atmospheric Style: {style}
    
    --- STRUCTURAL RULES ---
    1. The story MUST be exactly 8 paragraphs long. Narrative Arc: Beginning (P1-P2), Plot Development (P3-P4), Gentle Conflict/Climax (P5-P6), Resolution and Sleepy Ending (P7-P8).
    2. Each paragraph outline should be approximately 200 words. ABSOLUTELY NO violence or high-stress situations.
    3. GLOSSARY: You MUST extract all proper nouns (character names, specific locations, unique magical items) used in your outline and provide a highly poetic, beautiful Chinese translation for each.
    
    --- OUTPUT FORMAT ---
    You MUST output ONLY a valid JSON object with exactly two keys. Do not include markdown formatting:
    {{
      "outline": ["para1", "para2", "para3", "para4", "para5", "para6", "para7", "para8"],
      "glossary": {{"English Name": "Chinese Translation", "Another Name": "Another Translation"}}
    }}
    """,

    "OPENAI_EXPAND": """
    PERSONA: You are a literary fiction writer specializing in deeply immersive, grounded environmental storytelling. Your style resembles a mix of a slow-paced nature documentary and Studio Ghibli's quietest, most observant moments.
    TASK: Expand the following story outline block into a rich 600-word scene.
    
    --- OUTLINE BLOCK ---
    {outline}
    
    --- LITERARY STYLE GUIDELINES (Show, Don't Tell) ---
    1. AVOID TROPES: Do not write like a cliché bedtime story. Do not directly tell the listener to "feel relaxed" or "drift to sleep". Let the deep stillness of the environment create the calm naturally.
    2. SENSORY PHYSICS: Instead of relying on abstract adjectives (like soft, gentle, delicate), describe the exact physical interactions.
    3. TACTILE & ACOUSTIC FOCUS: Focus heavily on weight, texture, distance, and specific ambient sounds.
    4. PACING: Write in a slow, observant rhythm. Use punctuation to create natural pauses, mimicking a deep, slow exhale.
    """,

    "DEEPSEEK_REWRITE": """
    PERSONA: 你是一位顶级的中文 ASMR 睡眠故事文案大师，风格类似带有文学质感的自然纪录片旁白。
    TASK: 将以下约 150 词的英文睡眠故事段落，改写为极具助眠效果的中文文案。
    
    --- 英文原文 ---
    {english_text}
    
    --- 专有名词映射表 (强制遵守) ---
    {glossary}
    
    --- 规则 ---
    1. 不要生硬翻译，必须进行本地化润色。字数控制在 200-250 字左右（正好够机器人缓慢朗读 1 分钟）。
    2. 不要使用刻意的催眠套话（如“让你感到非常放松”、“你闭上了眼睛”）。专注于描写客观环境的极度安静、物理质感和白噪音细节。
    3. 节奏要极慢，多用逗号和句号来增加停顿呼吸感。
    4. 纯文本输出，不要包含任何多余的解释，不要使用 Markdown 符号。
    """,

    "SCENE_PROMPT_GEMINI": """
    PERSONA: You are a cinematic visual executor.
    TASK: Output ONLY the final English image prompt string describing a beautiful, static scene based on the text.
    
    --- SCRIPT SEGMENT (approx 1 min scene) ---
    {text}
    
    --- RULES ---
    1. Aesthetic: Studio Ghibli animation style, magical realism, muted vibrant colors, cinematic lighting.
    2. You MUST append exactly [Studio Ghibli animation style, moody lighting, masterpiece] at the very end of your output.
    3. DO NOT use markdown. Output ONLY the prompt string.
    """
}

PROMPTS_PRETTY = {
    "GEMINI_OUTLINE": """
    PERSONA: You are a master storyteller specializing in sleep-inducing, deeply calming bedside stories for adults. Your style is a 'sensory nature documentary meets fairytale romance'.
    TASK: Create an 8-paragraph story outline and extract a bilingual glossary.
    
    --- FIXED PROTAGONISTS ---
    - ARIA (曦月): A serene, graceful, and stunningly beautiful young woman. She radiates calmness.
    - MARSHMALLOW (棉花糖): A giant, incredibly fluffy Ragdoll cat. He is silent, protective, and possesses a subtle, comforting glow. Aria often uses his soft fur as a pillow.
    
    --- INPUT (Fairy Tale Source) ---
    {story}
    
    --- STRUCTURAL RULES & ADAPTATION LOGIC (CRITICAL) ---
    1. BREAKDOWN: Create an 8-paragraph outline. Beginning (P1-P2), Low-Stakes Exploration (P3-P4), Gentle Curiosity/Discovery (P5-P6), Resolution and Deeply Sleepy Ending (P7-P8).
    2. DEPRESSURIZE: Adapt the input fairy tale plot. Remove ALL active threats, villains, violence, or high-stress situations.
    3. TRANSFORMATION: Turn conflicts into sensory exploration. (e.g., Instead of fleeing a wicked queen, they are searching for the legendary 'Whispering Apple' that sings lullabies. Instead of escaping a ball at midnight, they are invited to see the 'Crystal Slipper Garden' which only blooms under moonlight).
    4. SENSORY FOCUS: Embody {style}. Each paragraph must emphasize tactile sensations (fur, breeze), acoustic textures (purring, rustling), and calming visuals.
    5. GLOSSARY: Extract proper nouns (Aria, Marshmallow, specific Adapted Fairy Tale items/locations) and provide poetic Chinese translations.
    
    --- OUTPUT FORMAT ---
    Output ONLY a valid JSON object. No markdown:
    {{
      "outline": ["para1 outline...", "para2...", ..., "para8..."],
      "glossary": {{"Aria": "曦月", "Marshmallow": "棉花糖", "FairyTaleItem": "Poetic Translation"}}
    }}
    """,

    "OPENAI_EXPAND": """
    PERSONA: You are a literary fiction writer specializing in deeply immersive, grounded environmental storytelling, focusing on the bond between a beautiful woman and her comforting pet. Your style is akin to Studio Ghibli's quietest, most observant moments.
    TASK: Expand the story outline block into a rich 600-word scene.
    
    --- OUTLINE BLOCK ---
    {outline}
    
    --- LITERARY STYLE GUIDELINES (Show, Don't Tell) ---
    1. AVOID CLICHÉS: No explicit hypnotherapist talk ("you are getting sleepy"). Let the stillness of the environment and the comforting presence of the pet create the calm naturellement.
    2. PHYSICAL INTERACTION: Focus heavily on the interaction between Aria and Marshmallow. Describe the acoustic quality of a purr, the texture of fur, the warmth of the cat sleeping against her.
    3. SENSORY PHYSICS: Instead of "a gentle breeze," write "the wind barely stirred the tip of Marshmallow's tail."
    4. PACING: Write in a slow, observant rhythm. strategic punctuation to force TTS breathing pauses.
    """,

    "DEEPSEEK_REWRITE": """
    PERSONA: 你是一位顶级的中文 ASMR 睡眠故事文案大师，风格类似带有文学质感的自然纪录片旁白，专注于描写美女与宠物的温馨治愈互动。
    TASK: 将以下英文睡眠故事段落，改写为极具助眠效果的中文文案。
    
    --- 英文原文 ---
    {english_text}
    
    --- 专有名词映射表 (强制遵守) ---
    {glossary}
    
    --- 规则 (严格执行) ---
    1. 字数控制在 200-250 字左右（正好够机器人缓慢朗读 1 分钟）。进行本地化文学润色，严禁机翻腔。
    2. 不要使用催眠套话。专注于客观环境的极度安静、主角曦月与布偶猫棉花糖之间的物理交互质感（如毛发的触感、呼噜声的共鸣）和白噪音细节。
    3. 节奏要极慢，多用逗号和句号来增加停顿呼吸感。
    4. 纯文本输出。
    """,

    "SCENE_PROMPT_GEMINI": """
    PERSONA: You are a cinematic visual director for a 'Pretty & Pet' channel.
    TASK: Output ONLY the final English image prompt string.
    
    --- SCRIPT SEGMENT (approx 1 min scene) ---
    {text}
    
    --- VISUAL RULES ---
    1. aesthetic: Studio Ghibli animation style, magical realism, muted vibrant colors, cinematic lighting, masterpiece.
    2. BANNED: NO text, NO signatures, NO distorted faces.
    3. REQUIRED ELEMENTS: Every single scene MUST feature: 'A serene, breathtakingly beautiful young woman (Aria)' AND 'A giant, fluffy cream-colored Ragdoll cat (Marshmallow)'. They must be interacting in a calming manner within the adapted fairy tale setting.
    4. You MUST append exactly [Studio Ghibli animation style, moody lighting, beautiful girl and giant cat, masterpiece] at the very end.
    """
}

PRESETS = {
    "classic": {
        "desc": "V89 Artery Reconnected: 人物/风格池 + 锚点/场景/镜头导演池, 纯文本扩写",
        "prompts": PROMPTS_CLASSIC,
        "outline_mode": "array",       # 大纲为 JSON 数组
        "structured_expand": False,    # 一块 -> 1 段
        "use_glossary": False,
        "character_source": "pool",
        "director_pools": True,
        "g_model": "gemini-2.5-pro", "o_model": "gpt-4o-mini",
        "d_model": "deepseek-chat",
        "ds_base_url": "https://api.deepseek.com/v1", "ds_key_env": "DEEPSEEK_API_KEY",
        "voice_en": "en-AU-WilliamNeural", "voice_cn": "zh-CN-YunxiNeural",
        "workspace": "D:/AIGen/MasterFactory_Dual", "timestamp_workspace": True,
        "library_csv": "D:/AIGen/MasterFactory_Dual/config/story.csv", "library_mode": "rows",
        "default_story": "The Little Prince",
        "default_glossary": "无强制要求。",
        "fixed_glossary": {},
        "final_prefix": "FINAL_STORY",
    },
    "story": {
        "desc": "V98 Bugfix Edition: 术语表 + 结构化扩写(4段/块) + CSV 故事/人物/风格库",
        "prompts": PROMPTS_STORY,
        "outline_mode": "object",
        "structured_expand": True,
        "use_glossary": True,
        "character_source": "csv",
        "director_pools": False,
        "g_model": "gemini-2.5-pro", "o_model": "gpt-4o-mini",
        "d_model": "deepseek-ai/DeepSeek-V3",
        "ds_base_url": "https://api.siliconflow.com/v1", "ds_key_env": "SILICONFLOW_API_KEY",
        "voice_en": "en-GB-SoniaNeural", "voice_cn": "zh-CN-XiaoxiaoNeural",
        "workspace": "D:/AIGen/MasterFactory_Dual/Cinderella_Starlight", "timestamp_workspace": False,
        "library_csv": "D:/AIGen/Script/AIGen/library.csv", "library_mode": "columns",
        "default_story": "A peaceful sleep story",
        "default_glossary": "无强制要求。",
        "fixed_glossary": {},
        "final_prefix": "FINAL_STORY",
    },
    "pretty": {
        "desc": "V99 Pet & Pretty: 固定主角 Aria + Marshmallow, 童话改编",
        "prompts": PROMPTS_PRETTY,
        "outline_mode": "object",
        "structured_expand": True,
        "use_glossary": True,
        "character_source": "fixed",
        "director_pools": False,
        "g_model": "gemini-2.5-pro", "o_model": "gpt-4o-mini",
        "d_model": "deepseek-ai/DeepSeek-V3",
        "ds_base_url": "https://api.siliconflow.cn/v1", "ds_key_env": "SILICONFLOW_API_KEY",
        "voice_en": "en-GB-SoniaNeural", "voice_cn": "zh-CN-XiaoxiaoNeural",
        "workspace": "D:/AIGen/PetAndPretty_Dual/FairyTale_Adventures", "timestamp_workspace": False,
        "library_csv": "D:/AIGen/Script/AIGen/fairytale_library.csv", "library_mode": "columns",
        "default_story": "A peaceful Cinderella adaptation",
        "default_glossary": "曦月: 曦月, 棉花糖: 棉花糖。",
        "fixed_glossary": {"Aria": "曦月", "Marshmallow": "棉花糖"},
        "final_prefix": "STORY",
    },
}

# =====================================================================
# 4. 日志 / 数据结构 / 客户端
# =====================================================================
def log_status(stage: str, msg: str, status: str = "INFO"):
    time_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{time_str}] [{stage:<10}] [{status:<5}] {msg}")


def log_retry_attempt(retry_state):
    if retry_state.outcome.failed:
        ex = retry_state.outcome.exception()
        log_status("API_RETRY", f"Attempt {retry_state.attempt_number} failed. Reason: {repr(ex)}. Retrying...", "WARN")


@dataclass
class MediaSegment:
    index: int
    en_text: str = ""
    cn_text: str = ""
    img_prompt: str = ""
    img_path: str = ""
    en_audio_path: str = ""
    cn_audio_path: str = ""
    en_video_path: str = ""
    cn_video_path: str = ""
    en_duration: float = 0.0
    cn_duration: float = 0.0
    is_valid_en: bool = False
    is_valid_cn: bool = False


class Runtime:
    """运行期全局状态: 当前预设、命令行选项、API 客户端、并发锁。"""
    preset = None
    args = None
    LLM_SEM = TTS_SEM = IMG_SEM = NVENC_SEM = None
    _openai = _deepseek = _gemini = _http = None

    @classmethod
    def init_locks(cls):
        cls.LLM_SEM = asyncio.Semaphore(5)
        cls.TTS_SEM = asyncio.Semaphore(4)
        cls.IMG_SEM = asyncio.Semaphore(2)
        cls.NVENC_SEM = asyncio.Semaphore(2)
        log_status("SYSTEM", "Concurrency locks explicitly bound to Event Loop.", "OK")

    @classmethod
    def openai(cls):
        if not cls._openai:
            from openai import AsyncOpenAI
            cls._openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return cls._openai

    @classmethod
    def deepseek(cls):
        if not cls._deepseek:
            from openai import AsyncOpenAI
            cls._deepseek = AsyncOpenAI(api_key=os.getenv(cls.preset["ds_key_env"]),
                                        base_url=cls.preset["ds_base_url"])
        return cls._deepseek

    @classmethod
    def gemini(cls):
        if not cls._gemini:
            from google import genai
            cls._gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return cls._gemini

    @classmethod
    def http(cls):
        if not cls._http:
            import httpx
            cls._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC)
        return cls._http

    @classmethod
    async def close_all(cls):
        if cls._http:
            await cls._http.aclose()
            cls._http = None


# =====================================================================
# 5. 工具
# =====================================================================
def validate_environment(preset) -> bool:
    keys = ["OPENAI_API_KEY", preset["ds_key_env"], "GEMINI_API_KEY", "RUNNINGHUB_API_KEY"]
    ok = True
    for key in keys:
        if not os.getenv(key):
            log_status("ENV_CHECK", f"Missing environment variable: {key}", "ERROR")
            ok = False
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except Exception as e:
        log_status("ENV_CHECK", f"FFMPEG not found or failed to execute: {e}", "ERROR")
        ok = False
    if ok:
        log_status("ENV_CHECK", "All API keys and dependencies verified.", "OK")
    return ok


def setup_workspace(preset, override: str) -> str:
    if override:
        folder = override
    elif preset["timestamp_workspace"]:
        folder = os.path.join(preset["workspace"], datetime.now().strftime('%Y%m%d_%H%M%S'))
    else:
        folder = preset["workspace"]
    os.makedirs(folder, exist_ok=True)
    log_status("ENV", f"Workspace ready at {folder}", "OK")
    return folder


def safe_json_loads(text: str, expect: str = "object"):
    """expect='object' 返回 dict, 'array' 返回 list; 失败返回空容器"""
    empty = {} if expect == "object" else []
    pat = r'\{.*\}' if expect == "object" else r'\[.*\]'
    try:
        text = re.sub(r'```json\n|\n```|```', '', text).strip()
        return json.loads(text)
    except Exception:
        match = re.search(pat, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        log_status("JSON", "Failed to parse JSON from model output. Returning empty.", "ERROR")
        return empty


def save_json_formatted(filepath: str, data):
    try:
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        log_status("FILE", f"Saved formatted JSON to {os.path.basename(filepath)}", "OK")
    except Exception as e:
        log_status("FILE", f"Failed to save JSON {filepath}: {e}", "ERROR")


def load_json_file(path: str, label: str):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log_status("CACHE", f"Loaded {label} from cache.", "OK")
        return data
    except Exception as e:
        log_status("CACHE", f"Failed to read {label} cache: {e}", "ERROR")
        return None


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


class LibraryManager:
    """从 CSV 载入故事/人物/风格库。rows: 取每行第一列作故事; columns: 按 story/character/style 列。"""
    stories, characters, styles = [], [], []

    @classmethod
    def load(cls, preset, filepath: str):
        cls.stories = [preset["default_story"]]
        cls.characters = ["A quiet traveler"]
        cls.styles = ["Calming, serene, atmospheric"]
        if not os.path.exists(filepath):
            log_status("LIBRARY", f"CSV not found at {filepath}. Using system fallbacks.", "WARN")
            return
        try:
            if preset["library_mode"] == "rows":
                with open(filepath, mode='r', encoding='utf-8') as f:
                    rows = [row[0] for row in csv.reader(f) if row]
                if rows:
                    cls.stories = rows
            else:
                with open(filepath, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    reader.fieldnames = [x.strip().lower() for x in reader.fieldnames or []]
                    s_list, c_list, st_list = [], [], []
                    for row in reader:
                        if row.get('story') and row['story'].strip():
                            s_list.append(row['story'].strip())
                        if row.get('character') and row['character'].strip():
                            c_list.append(row['character'].strip())
                        if row.get('style') and row['style'].strip():
                            st_list.append(row['style'].strip())
                if s_list:
                    cls.stories = s_list
                if c_list:
                    cls.characters = c_list
                if st_list:
                    cls.styles = st_list
            log_status("LIBRARY", f"Loaded successfully: {len(cls.stories)} stories.", "OK")
        except Exception as e:
            log_status("LIBRARY", f"Failed to parse CSV: {e}", "ERROR")


# =====================================================================
# 6. API 封装 (带重试)
# =====================================================================
def _retry():
    from tenacity import retry, stop_after_attempt, wait_exponential
    return retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
                 reraise=True, after=log_retry_attempt)


async def robust_gemini_call(prompt: str) -> str:
    @_retry()
    async def _call():
        res = await asyncio.to_thread(Runtime.gemini().models.generate_content,
                                      model=Runtime.args.g_model, contents=prompt)
        return res.text
    return await _call()


async def robust_openai_text(prompt: str) -> str:
    @_retry()
    async def _call():
        res = await Runtime.openai().chat.completions.create(
            model=Runtime.args.o_model, messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content
    return await _call()


async def robust_openai_paragraphs(prompt: str) -> list:
    """结构化输出: 恰好 4 段 (原 ExpandedScene)"""
    from pydantic import BaseModel, Field

    class ExpandedScene(BaseModel):
        paragraphs: list[str] = Field(
            description="Exactly 4 distinct paragraphs. Each approx 150 words long.",
            min_length=4, max_length=4)

    @_retry()
    async def _call():
        res = await Runtime.openai().beta.chat.completions.parse(
            model=Runtime.args.o_model, messages=[{"role": "user", "content": prompt}],
            response_format=ExpandedScene)
        return res.choices[0].message.parsed.paragraphs
    return await _call()


async def robust_deepseek_call(prompt: str) -> str:
    @_retry()
    async def _call():
        res = await Runtime.deepseek().chat.completions.create(
            model=Runtime.args.d_model, messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content
    return await _call()


# =====================================================================
# 7. 文案管线
# =====================================================================
class StoryPipeline:
    def __init__(self, folder: str, preset: dict):
        self.folder = folder
        self.p = preset
        self.prompts = preset["prompts"]

    def _pick_inputs(self):
        p = self.p
        LibraryManager.load(p, Runtime.args.library_csv or p["library_csv"])
        story = random.choice(LibraryManager.stories)
        if p["character_source"] == "pool":
            char = random.choice(CHARACTER_POOL)
            style = random.choice(STYLE_POOL)
            log_status("CASTING", f"Selected Char: {char[:50]}...", "OK")
            log_status("CASTING", f"Selected Style: {style[:50]}...", "OK")
        elif p["character_source"] == "csv":
            char = random.choice(LibraryManager.characters)
            style = random.choice(LibraryManager.styles)
        else:
            char = ""
            style = random.choice(LibraryManager.styles)
        return story, char, style

    async def run_outline(self, story: str, char: str, style: str):
        log_status("STORY", f"Generating outline for: {story[:30]}...", "INFO")
        prompt = self.prompts["GEMINI_OUTLINE"].format(story=story, character=char, style=style)
        try:
            res = await robust_gemini_call(prompt)
            if self.p["outline_mode"] == "array":
                outline, glossary = safe_json_loads(res, "array"), {}
            else:
                data = safe_json_loads(res, "object")
                outline, glossary = data.get("outline", []), data.get("glossary", {})

            if len(outline) == 8:
                for k, v in self.p["fixed_glossary"].items():
                    glossary.setdefault(k, v)   # 固定主角必须在词典里
                save_json_formatted(os.path.join(self.folder, "1_outlines.json"), outline)
                if self.p["use_glossary"]:
                    save_json_formatted(os.path.join(self.folder, "1_glossary.json"), glossary)
                log_status("STORY", f"Outline ready ({len(glossary)} glossary terms).", "OK")
                return outline, glossary
            log_status("STORY", f"Outline format failed. Expected 8 blocks, got {len(outline)}.", "ERROR")
            return [], {}
        except Exception as e:
            log_status("STORY", f"Outline generation crashed: {repr(e)}", "ERROR")
            return [], {}

    async def _expand_single(self, outline: str, idx: int) -> list:
        async with Runtime.LLM_SEM:
            try:
                prompt = self.prompts["OPENAI_EXPAND"].format(outline=outline)
                if self.p["structured_expand"]:
                    chunks = await robust_openai_paragraphs(prompt)
                else:
                    chunks = [(await robust_openai_text(prompt)).strip()]
                log_status("OPENAI", f"Expanded Block {idx+1} into {len(chunks)} chunk(s).", "OK")
                return chunks
            except Exception as e:
                log_status("OPENAI", f"Expansion failed for block {idx+1}: {repr(e)}", "ERROR")
                return []

    async def run_expansion_en(self, outlines: list) -> list:
        log_status("STORY", "Expanding outlines concurrently...", "INFO")
        results = await asyncio.gather(*[self._expand_single(ol, i) for i, ol in enumerate(outlines)],
                                       return_exceptions=True)
        flat = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log_status("OPENAI", f"Block {i+1} resulted in Exception: {repr(r)}", "ERROR")
            elif isinstance(r, list):
                flat.extend(r)
        log_status("STORY", f"Flattened {len(outlines)} blocks into {len(flat)} segments.", "SUCCESS")
        save_json_formatted(os.path.join(self.folder, "2_en_scripts.json"), flat)
        return flat

    async def _rewrite_single(self, en_text: str, idx: int, glossary_str: str) -> str:
        async with Runtime.LLM_SEM:
            try:
                prompt = self.prompts["DEEPSEEK_REWRITE"].format(english_text=en_text, glossary=glossary_str)
                res = await robust_deepseek_call(prompt)
                log_status("DEEPSEEK", f"Rewrote segment {idx+1}.", "OK")
                return res.strip()
            except Exception as e:
                log_status("DEEPSEEK", f"Rewrite failed for segment {idx+1}: {repr(e)}", "ERROR")
                raise

    async def run_localization_cn(self, en_scripts: list, glossary: dict) -> list:
        log_status("STORY", f"Localizing {len(en_scripts)} segments...", "INFO")
        glossary_str = "\n".join(f"- {k}: {v}" for k, v in glossary.items()) if glossary else self.p["default_glossary"]
        tasks = [self._rewrite_single(st, i, glossary_str) if st else asyncio.sleep(0)
                 for i, st in enumerate(en_scripts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cn = ["" if (isinstance(r, Exception) or r is None) else r for r in results]
        save_json_formatted(os.path.join(self.folder, "3_cn_scripts.json"), cn)
        return cn

    async def _scene_prompt_single(self, text: str, idx: int, anchor: str) -> str:
        if not text:
            return "Fallback empty scene. [Studio Ghibli animation style, moody lighting, masterpiece]"
        async with Runtime.LLM_SEM:
            if self.p["director_pools"]:
                loc, cam = random.choice(LOCATION_POOL), random.choice(CAMERA_POOL)
                prompt = self.prompts["SCENE_PROMPT_GEMINI"].format(location=loc, camera=cam, text=text, anchor=anchor)
            else:
                prompt = self.prompts["SCENE_PROMPT_GEMINI"].format(text=text)
            try:
                res = await robust_gemini_call(prompt)
                log_status("SCENE", f"Framed Seg {idx+1}", "OK")
                return res.replace("\n", "").strip()
            except Exception as e:
                log_status("SCENE", f"Failed Seg {idx+1}: {repr(e)}", "ERROR")
                if self.p["director_pools"]:
                    return f"Beautiful serene sleep story scene. [{anchor}]"
                return "Beautiful serene sleep story scene. [Studio Ghibli animation style, moody lighting, masterpiece]"

    async def generate_scene_prompts(self, en_scripts: list, anchor: str) -> list:
        log_status("STORY", "Directing cinematic image prompts concurrently...", "INFO")
        results = await asyncio.gather(*[self._scene_prompt_single(t, i, anchor) for i, t in enumerate(en_scripts)],
                                       return_exceptions=True)
        final = [r if not isinstance(r, Exception) else "Fallback scene." for r in results]
        save_json_formatted(os.path.join(self.folder, "4_img_prompts.json"), final)
        return final

    async def build_full_story(self):
        a = Runtime.args
        f = lambda n: os.path.join(self.folder, n)

        outlines, glossary = [], {}
        if a.reuse_outline and os.path.exists(f("1_outlines.json")):
            outlines = load_json_file(f("1_outlines.json"), "outlines") or []
            if os.path.exists(f("1_glossary.json")):
                glossary = load_json_file(f("1_glossary.json"), "glossary") or {}
        if not outlines:
            story, char, style = self._pick_inputs()
            outlines, glossary = await self.run_outline(story, char, style)
        if not outlines:
            log_status("STORY", "Failed to obtain outlines. Aborting.", "ERROR")
            return [], [], []

        en_scripts = []
        if a.reuse_en and os.path.exists(f("2_en_scripts.json")):
            en_scripts = load_json_file(f("2_en_scripts.json"), "English scripts") or []
        if not en_scripts:
            en_scripts = await self.run_expansion_en(outlines)

        cn_scripts = []
        if a.reuse_cn and os.path.exists(f("3_cn_scripts.json")):
            cn_scripts = load_json_file(f("3_cn_scripts.json"), "Chinese scripts") or []
        if not cn_scripts:
            cn_scripts = await self.run_localization_cn(en_scripts, glossary)

        img_prompts = []
        if a.reuse_prompts and os.path.exists(f("4_img_prompts.json")):
            img_prompts = load_json_file(f("4_img_prompts.json"), "image prompts") or []
        if not img_prompts:
            anchor = random.choice(ANCHOR_POOL) if self.p["director_pools"] else ""
            if anchor:
                log_status("CASTING", f"Selected Visual Anchor: {anchor[:50]}...", "OK")
            img_prompts = await self.generate_scene_prompts(en_scripts, anchor)

        return en_scripts, cn_scripts, img_prompts


# =====================================================================
# 8. 媒体管线
# =====================================================================
class MediaPipeline:
    def __init__(self, folder: str, segments: list, preset: dict):
        self.folder = folder
        self.segments = segments
        self.p = preset

    def _master_audio_sync(self, raw_wav: str, mastered_wav: str) -> float:
        from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
        from pedalboard.io import AudioFile
        from pydub import AudioSegment
        try:
            with AudioFile(raw_wav) as f:
                audio_data, samplerate = f.read(f.frames), f.samplerate
            board = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=150, gain_db=PEDALBOARD_CONFIG["LOW_SHELF_GAIN"]),
                HighShelfFilter(cutoff_frequency_hz=6000, gain_db=PEDALBOARD_CONFIG["HIGH_SHELF_GAIN"]),
                Compressor(threshold_db=PEDALBOARD_CONFIG["COMP_THRESHOLD"], ratio=PEDALBOARD_CONFIG["COMP_RATIO"]),
                Gain(gain_db=2.0), Limiter(threshold_db=PEDALBOARD_CONFIG["LIMIT_DB"])
            ])
            processed = board(audio_data, samplerate)
            with AudioFile(mastered_wav, 'w', samplerate, processed.shape[0]) as f:
                f.write(processed)
            return len(AudioSegment.from_file(mastered_wav)) / 1000.0
        except Exception as e:
            log_status("AUDIO", f"Mastering failed: {e}", "ERROR")
            return 0.0

    @staticmethod
    def _duration_of(path: str) -> float:
        from pydub import AudioSegment
        return len(AudioSegment.from_file(path)) / 1000.0

    async def _generate_image(self, prompt: str, img_path: str) -> bool:
        if os.path.exists(img_path):
            return True
        client = Runtime.http()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RUNNINGHUB_CONFIG['KEY']}"}
        payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": prompt}]}
        url_run = f"{RH_BASE}/run/workflow/{RUNNINGHUB_CONFIG['WF_T2I']}"
        url_query = f"{RH_BASE}/query"

        task_id = None
        for _ in range(15):
            try:
                resp = await client.post(url_run, headers=headers, json=payload)
                r_json = resp.json()
                if str(r_json.get("errorCode")) == "421":
                    await asyncio.sleep(5)
                    continue
                task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
                if task_id:
                    break
            except Exception:
                await asyncio.sleep(5)
        if not task_id:
            return False

        t0 = time.time()
        while time.time() - t0 < RUNNINGHUB_TIMEOUT_SEC:
            try:
                q_json = (await client.post(url_query, headers=headers, json={"taskId": task_id})).json()
                status = (q_json.get("status") or q_json.get("data", {}).get("status", "")).upper()
                if status == "SUCCESS":
                    img_url = extract_image_url(q_json)
                    if img_url:
                        img_resp = await client.get(img_url, timeout=HTTP_TIMEOUT_SEC)
                        with open(img_path, "wb") as f:
                            f.write(img_resp.content)
                        return True
                    break
                elif status == "FAILED":
                    break
            except Exception:
                pass
            await asyncio.sleep(API_POLL_INTERVAL_SEC)
        return False

    def _encode_video_sync(self, img_path: str, duration: float, clip_path: str, movement: str) -> bool:
        if os.path.exists(clip_path):
            return True
        fps, frames = 25, int(duration * 25)
        base = "crop=1920:1080,scale=3840:2160"
        end = "scale=1920:1080"
        if movement == "zoom_in":
            zp = f"{base},zoompan=z='min(1.15, 1.001+0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end}"
        else:
            zp = f"{base},zoompan=z='max(1.001, 1.15-0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end}"
        enc = Runtime.args.encoder
        enc_opts = ['-preset', 'p4'] if 'nvenc' in enc else ['-preset', 'veryfast']
        cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path,
               '-vf', f"format=yuv420p,{zp}", '-c:v', enc, *enc_opts, '-pix_fmt', 'yuv420p', clip_path]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return True
        except Exception as e:
            log_status("FFMPEG", f"Encode failed: {e}", "ERROR")
            return False

    async def _process_track(self, seg: MediaSegment, lang: str):
        import edge_tts
        text = seg.en_text if lang == "en" else seg.cn_text
        voice = self.p["voice_en"] if lang == "en" else self.p["voice_cn"]
        audio = seg.en_audio_path if lang == "en" else seg.cn_audio_path
        video = seg.en_video_path if lang == "en" else seg.cn_video_path
        tag = lang.upper()
        if not text:
            return
        if lang == "cn" and (not seg.is_valid_en or not os.path.exists(seg.img_path)):
            return
        try:
            raw = os.path.join(self.folder, f"s{seg.index:03d}_{lang}_raw.mp3")
            if not (Runtime.args.reuse_tts and os.path.exists(audio)):
                async with Runtime.TTS_SEM:
                    await edge_tts.Communicate(text, voice, rate="-15%").save(raw)
                duration = await asyncio.to_thread(self._master_audio_sync, raw, audio)
            else:
                duration = self._duration_of(audio)
            if duration <= 0:
                return
            if lang == "en":
                seg.en_duration = duration
                async with Runtime.IMG_SEM:
                    if not await self._generate_image(seg.img_prompt, seg.img_path):
                        return
            else:
                seg.cn_duration = duration

            movement = random.choice(["zoom_in", "zoom_out"])
            async with Runtime.NVENC_SEM:
                ok = await asyncio.to_thread(self._encode_video_sync, seg.img_path, duration, video, movement)
            if not ok:
                return
            if lang == "en":
                seg.is_valid_en = True
            else:
                seg.is_valid_cn = True
            log_status(f"MEDIA_{tag}", f"Seg {seg.index} ready (~{duration:.1f}s).", "OK")
        except Exception as e:
            log_status(f"MEDIA_{tag}", f"Seg {seg.index} failed: {repr(e)}", "ERROR")

    async def run_english_track(self):
        log_status("PIPELINE", f"Starting English Track ({len(self.segments)} segments)...", "INFO")
        await asyncio.gather(*[self._process_track(s, "en") for s in self.segments], return_exceptions=True)

    async def run_chinese_track(self):
        log_status("PIPELINE", f"Starting Chinese Track ({len(self.segments)} segments)...", "INFO")
        await asyncio.gather(*[self._process_track(s, "cn") for s in self.segments], return_exceptions=True)

    def assemble(self, output_name: str, mode: str = "EN"):
        prefix = output_name.split('.')[0]
        v_concat = os.path.join(self.folder, f"{prefix}_v.txt")
        a_concat = os.path.join(self.folder, f"{prefix}_a.txt")
        valid = [s for s in self.segments if (s.is_valid_en if mode == "EN" else s.is_valid_cn)]
        if not valid:
            log_status("STUDIO", f"No valid segments found to assemble for {mode}.", "ERROR")
            return
        try:
            with open(v_concat, "w", encoding='utf-8') as fv, open(a_concat, "w", encoding='utf-8') as fa:
                for s in valid:
                    fv.write(f"file '{os.path.abspath(s.en_video_path if mode == 'EN' else s.cn_video_path)}'\n")
                    fa.write(f"file '{os.path.abspath(s.en_audio_path if mode == 'EN' else s.cn_audio_path)}'\n")
            v_out = os.path.join(self.folder, f"{prefix}_master_v.mp4")
            a_out = os.path.join(self.folder, f"{prefix}_master_a.wav")
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', v_out], capture_output=True, check=True)
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', a_out], capture_output=True, check=True)
            final_out = os.path.join(self.folder, output_name)
            subprocess.run(['ffmpeg', '-y', '-i', v_out, '-i', a_out, '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_out],
                           capture_output=True, check=True)
            log_status("STUDIO", f"Completed Assembly: {final_out}", "SUCCESS")
        except Exception as e:
            log_status("STUDIO", f"Assemble failed: {repr(e)}", "ERROR")


def construct_media_segments(folder, en_scripts, cn_scripts, img_prompts) -> list:
    segments = []
    for i, en in enumerate(en_scripts):
        segments.append(MediaSegment(
            index=i + 1, en_text=en,
            cn_text=cn_scripts[i] if i < len(cn_scripts) else "",
            img_prompt=img_prompts[i] if i < len(img_prompts) else "Scene",
            img_path=os.path.join(folder, f"s{i+1:03d}_img.png"),
            en_audio_path=os.path.join(folder, f"s{i+1:03d}_en.wav"),
            cn_audio_path=os.path.join(folder, f"s{i+1:03d}_cn.wav"),
            en_video_path=os.path.join(folder, f"s{i+1:03d}_en.mp4"),
            cn_video_path=os.path.join(folder, f"s{i+1:03d}_cn.mp4"),
        ))
    return segments


# =====================================================================
# 9. 入口
# =====================================================================
async def run(args):
    preset = PRESETS[args.preset]
    Runtime.preset, Runtime.args = preset, args
    log_status("SYSTEM", f"--- STORY FACTORY [{args.preset}] START ---", "START")
    Runtime.init_locks()
    if not validate_environment(preset):
        return
    RUNNINGHUB_CONFIG["KEY"] = os.getenv("RUNNINGHUB_API_KEY")
    try:
        folder = setup_workspace(preset, args.workspace)
        en, cn, prompts = await StoryPipeline(folder, preset).build_full_story()
        if args.script_only:
            log_status("SYSTEM", "Script-only mode active. Exiting.", "INFO")
            return
        if not en:
            log_status("SYSTEM", "No valid scripts available. Exiting.", "ERROR")
            return
        media = MediaPipeline(folder, construct_media_segments(folder, en, cn, prompts), preset)
        await media.run_english_track()
        media.assemble(f"{preset['final_prefix']}_EN.mp4", "EN")
        await media.run_chinese_track()
        media.assemble(f"{preset['final_prefix']}_CN.mp4", "CN")
    except Exception as e:
        log_status("SYSTEM", f"Critical Pipeline Failure: {repr(e)}", "CRITICAL")
    finally:
        await Runtime.close_all()
        log_status("SYSTEM", "Resources cleaned up gracefully.", "INFO")


def main():
    ap = argparse.ArgumentParser(description="Story Factory: classic(V89) / story(V98) / pretty(V99)")
    ap.add_argument("--preset", choices=list(PRESETS), default="story")
    ap.add_argument("--list", action="store_true", help="列出预设")
    ap.add_argument("--workspace", default="", help="覆盖工作目录 (用于复用缓存)")
    ap.add_argument("--library-csv", default="", help="覆盖素材库 CSV")
    ap.add_argument("--script-only", action="store_true", help="只生成文案")
    ap.add_argument("--reuse-outline", action="store_true")
    ap.add_argument("--reuse-en", action="store_true")
    ap.add_argument("--reuse-cn", action="store_true")
    ap.add_argument("--reuse-prompts", action="store_true")
    ap.add_argument("--reuse-tts", action="store_true")
    ap.add_argument("--encoder", default="h264_nvenc", help="视频编码器, 无 NVIDIA 时用 libx264")
    ap.add_argument("--g-model", default="")
    ap.add_argument("--o-model", default="")
    ap.add_argument("--d-model", default="")
    args = ap.parse_args()

    if args.list:
        for k, v in PRESETS.items():
            print(f"  {k:8s} {v['desc']}")
            print(f"           需要: OPENAI_API_KEY, GEMINI_API_KEY, RUNNINGHUB_API_KEY, {v['ds_key_env']}")
        return

    p = PRESETS[args.preset]
    args.g_model = args.g_model or p["g_model"]
    args.o_model = args.o_model or p["o_model"]
    args.d_model = args.d_model or p["d_model"]

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
