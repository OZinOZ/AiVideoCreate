# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches, too-many-instance-attributes, missing-docstring
"""
AI Audio Masterclass Factory V99 - Pet & Pretty Edition
Features: Fixed Protagonists (Beauty & Giant Cat), Fairy Tale Adaptation Logic, ASMR Focus, Bugfixes.
"""

import os
import sys
import asyncio
import re
import json
import time
import subprocess
import csv
import random
from datetime import datetime
from dataclasses import dataclass

import httpx

# Models
from google import genai
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# Media
import edge_tts
from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
from pedalboard.io import AudioFile

# Engineering Tools
from tenacity import retry, stop_after_attempt, wait_exponential

# =====================================================================
# 1. GLOBAL CONFIGURATION (全局配置区)
# =====================================================================

ONLY_GENERATE_SCRIPT = False

# 缓存复用开关
REUSE_GEMINI_OUTLINE = True
REUSE_OPENAI_SCRIPT = False
REUSE_DEEPSEEK_SCRIPT = False
REUSE_IMAGE_PROMPT = False
REUSE_TTS = False

# 【重要】更改工作目录为 Pet & Pretty 频道
TARGET_WORKSPACE = "D:/AIGen/PetAndPretty_Dual/FairyTale_Adventures"
# 童话素材库 CSV
LIBRARY_CSV_PATH = "D:/AIGen/Script/AIGen/fairytale_library.csv"

RUNNINGHUB_TIMEOUT_SEC = 600
API_POLL_INTERVAL_SEC = 10
HTTP_TIMEOUT_SEC = 60.0

MODEL_CONFIG = {
    "G_MODEL": "gemini-2.5-pro",
    "O_MODEL": "gpt-4o-mini",
    "D_MODEL": "deepseek-ai/DeepSeek-V3",
    # 英国 Sonia 女声，温柔克制
    "VOICE_EN": "en-GB-SoniaNeural",
    # 中国晓晓女声，极具助眠质感
    "VOICE_CN": "zh-CN-XiaoxiaoNeural", 
}

RUNNINGHUB_CONFIG = {
    "KEY": os.getenv("RUNNINGHUB_API_KEY"),
    "WF_T2I": "2014487614874718210",
    "T2I_NODE": "111"
}

PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 5.0, "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -18.0, "COMP_RATIO": 3.0, "LIMIT_DB": -3.0
}

# =====================================================================
# 2. SCHEMA & PROMPTS (提示词核心升级)
# =====================================================================

class ExpandedScene(BaseModel):
    paragraphs: list[str] = Field(
        description="Exactly 4 distinct paragraphs. Each approx 150 words long.",
        min_items=4,
        max_items=4
    )

PROMPT_CONFIG = {
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

# =====================================================================
# 3. LOGGING, DATA STRUCTURES & SINGLETONS
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

class ConcurrencyManager:
    LLM_SEM = None
    TTS_SEM = None
    IMG_SEM = None
    NVENC_SEM = None

    @classmethod
    def init_locks(cls):
        cls.LLM_SEM = asyncio.Semaphore(5)
        cls.TTS_SEM = asyncio.Semaphore(4)
        cls.IMG_SEM = asyncio.Semaphore(2)
        cls.NVENC_SEM = asyncio.Semaphore(2)
        log_status("SYSTEM", "Concurrency locks explicitly bound to Event Loop.", "OK")

class APIClients:
    _openai = None
    _deepseek = None
    _gemini = None
    _http = None

    @classmethod
    def get_openai(cls):
        if not cls._openai: 
            cls._openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return cls._openai

    @classmethod
    def get_deepseek(cls):
        if not cls._deepseek: 
            cls._deepseek = AsyncOpenAI(
                api_key=os.getenv("SILICONFLOW_API_KEY"), 
                base_url="https://api.siliconflow.cn/v1"
            )
        return cls._deepseek

    @classmethod
    def get_gemini(cls):
        if not cls._gemini: 
            cls._gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return cls._gemini

    @classmethod
    def get_http(cls):
        if not cls._http: 
            cls._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC)
        return cls._http
        
    @classmethod
    async def close_all(cls):
        if cls._http: 
            await cls._http.aclose()
            cls._http = None

# =====================================================================
# 4. UTILITIES & DATA MANAGERS
# =====================================================================

def validate_environment() -> bool:
    keys = ["OPENAI_API_KEY", "SILICONFLOW_API_KEY", "GEMINI_API_KEY", "RUNNINGHUB_API_KEY"]
    is_valid = True
    for key in keys:
        if not os.getenv(key):
            log_status("ENV_CHECK", f"Missing environment variable: {key}", "ERROR")
            is_valid = False
            
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except Exception as e:
        log_status("ENV_CHECK", f"FFMPEG not found: {e}", "ERROR")
        is_valid = False

    if is_valid:
        log_status("ENV_CHECK", "Pet & Pretty environment validated.", "OK")
    return is_valid

def setup_workspace(folder_path: str) -> str:
    os.makedirs(folder_path, exist_ok=True)
    log_status("ENV", f"Workspace: {folder_path}", "OK")
    return folder_path

def safe_json_loads(text: str) -> dict:
    try:
        text = re.sub(r'```json\n|\n```|```', '', text).strip()
        return json.loads(text)
    except Exception as e:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try: return json.loads(match.group())
            except: pass
        log_status("JSON", "Failed to parse Gemini object.", "ERROR")
        return {}

def save_json_formatted(filepath: str, data: any):
    try:
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        log_status("FILE", f"Saved {os.path.basename(filepath)}", "OK")
    except Exception as e:
        log_status("FILE", f"Save failed {filepath}: {e}", "ERROR")

class LibraryManager:
    """Resp for loading fairy tale assets pool from CSV."""
    stories = ["A peaceful Cinderella adaptation"]
    styles = ["Calming, serene, atmospheric"]

    @classmethod
    def load_from_csv(cls, filepath: str):
        if not os.path.exists(filepath):
            log_status("LIBRARY", f"CSV not found at {filepath}. Using Fallbacks.", "WARN")
            return
        try:
            with open(filepath, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [field.strip().lower() for field in reader.fieldnames or []]
                s_list, st_list = [], []
                for row in reader:
                    # 我们只需要故事核心（童话大纲）和风格
                    if row.get('story') and row['story'].strip(): s_list.append(row['story'].strip())
                    if row.get('style') and row['style'].strip(): st_list.append(row['style'].strip())
                if s_list: cls.stories = s_list
                if st_list: cls.styles = st_list
            log_status("LIBRARY", f"Loaded {len(cls.stories)} fairy tales.", "OK")
        except Exception as e:
            log_status("LIBRARY", f"Parse failed: {e}", "ERROR")

# =====================================================================
# 5. API WRAPPERS
# =====================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
async def robust_gemini_call(prompt: str) -> str:
    res = await asyncio.to_thread(APIClients.get_gemini().models.generate_content, model=MODEL_CONFIG["G_MODEL"], contents=prompt)
    return res.text

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
async def robust_openai_call(prompt: str) -> list[str]:
    res = await APIClients.get_openai().beta.chat.completions.parse(
        model=MODEL_CONFIG["O_MODEL"], 
        messages=[{"role": "user", "content": prompt}],
        response_format=ExpandedScene
    )
    return res.choices[0].message.parsed.paragraphs

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
async def robust_deepseek_call(prompt: str) -> str:
    res = await APIClients.get_deepseek().chat.completions.create(model=MODEL_CONFIG["D_MODEL"], messages=[{"role": "user", "content": prompt}])
    return res.choices[0].message.content

# =====================================================================
# 6. PIPELINES (业务管线)
# =====================================================================

class StoryPipeline:
    def __init__(self, folder: str):
        self.folder = folder

    async def run_outline(self, story_source: str, style: str) -> tuple[list, dict]:
        # 【重要】角色固定为曦月和棉花糖，无需从CSV抽取
        log_status("STORY", "Generating Fairy Tale adaptation outline & glossary...", "INFO")
        prompt = PROMPT_CONFIG["GEMINI_OUTLINE"].format(story=story_source, style=style)
        try:
            res = await robust_gemini_call(prompt)
            data = safe_json_loads(res)
            outline = data.get("outline", [])
            glossary = data.get("glossary", {})
            
            if len(outline) == 8:
                save_json_formatted(os.path.join(self.folder, "1_outlines.json"), outline)
                # 曦月和棉花糖必须在词典里
                if "Aria" not in glossary: glossary["Aria"] = "曦月"
                if "Marshmallow" not in glossary: glossary["Marshmallow"] = "棉花糖"
                save_json_formatted(os.path.join(self.folder, "1_glossary.json"), glossary)
                log_status("STORY", f"Outline ready with {len(glossary)} glossary terms.", "OK")
                return outline, glossary
                
            log_status("STORY", "Outline format failed.", "ERROR")
            return [], {}
        except Exception as e:
            log_status("STORY", f"Outline crash: {repr(e)}", "ERROR")
            return [], {}

    async def _expand_single(self, outline: str, idx: int) -> list:
        async with ConcurrencyManager.LLM_SEM:
            try:
                chunks = await robust_openai_call(PROMPT_CONFIG["OPENAI_EXPAND"].format(outline=outline))
                log_status("OPENAI", f"Expanded Seg {idx+1}.", "OK")
                return chunks
            except Exception as e:
                log_status("OPENAI", f"Seg {idx+1} failed: {repr(e)}", "ERROR")
                return []

    async def run_expansion_en(self, outlines: list) -> list:
        log_status("STORY", "Expanding concurrently (P&P Mode)...", "INFO")
        tasks = [self._expand_single(ol, i) for i, ol in enumerate(outlines)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        en_scripts_flattened = []
        for r in results:
            if isinstance(r, list): en_scripts_flattened.extend(r)
        save_json_formatted(os.path.join(self.folder, "2_en_scripts.json"), en_scripts_flattened)
        return en_scripts_flattened

    async def _rewrite_single(self, en_text: str, idx: int, glossary_str: str) -> str:
        async with ConcurrencyManager.LLM_SEM:
            try:
                prompt = PROMPT_CONFIG["DEEPSEEK_REWRITE"].format(english_text=en_text, glossary=glossary_str)
                res = await robust_deepseek_call(prompt)
                log_status("DEEPSEEK", f"Rewrote Seg {idx+1}.", "OK")
                return res.strip()
            except Exception as e:
                log_status("DEEPSEEK", f"Seg {idx+1} fail: {repr(e)}", "ERROR")
                raise e

    async def run_localization_cn(self, en_scripts: list, glossary: dict) -> list:
        log_status("STORY", "Localizing (Glossary Injected)...", "INFO")
        glossary_str = "\n".join([f"- {k}: {v}" for k, v in glossary.items()]) if glossary else "曦月: 曦月, 棉花糖: 棉花糖。"
        tasks = [self._rewrite_single(st, i, glossary_str) if st else asyncio.sleep(0) for i, st in enumerate(en_scripts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cn_scripts = []
        for r in results:
            if isinstance(r, Exception): cn_scripts.append("")
            else: cn_scripts.append(r)
        save_json_formatted(os.path.join(self.folder, "3_cn_scripts.json"), cn_scripts)
        return cn_scripts

    async def _generate_cinematic_prompt_single(self, text: str, idx: int) -> str:
        if not text: return "A beautiful serene scene. [Studio Ghibli style, centerpiece]"
        async with ConcurrencyManager.LLM_SEM:
            try:
                res = await robust_gemini_call(PROMPT_CONFIG["SCENE_PROMPT_GEMINI"].format(text=text))
                log_status("SCENE", f"Framed Seg {idx+1}", "OK")
                return res.replace("\n", "").strip()
            except Exception as e:
                return "Serene fantasy Ghibli scene of a girl and cat. [masterpiece]"

    async def generate_cinematic_prompts(self, en_scripts: list) -> list:
        log_status("STORY", "Directing prompts concurrently...", "INFO")
        tasks = [self._generate_cinematic_prompt_single(text, i) for i, text in enumerate(en_scripts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        final_prompts = [r if not isinstance(r, Exception) else "Scene." for r in results]
        save_json_formatted(os.path.join(self.folder, "4_img_prompts.json"), final_prompts)
        return final_prompts

    async def build_full_story(self) -> tuple[list, list, list]:
        """P&P Orchestrator."""
        outlines, glossary = [], {}
        f_outline = os.path.join(self.folder, "1_outlines.json")
        f_glossary = os.path.join(self.folder, "1_glossary.json")
        if REUSE_GEMINI_OUTLINE and os.path.exists(f_outline) and os.path.exists(f_glossary):
            try:
                with open(f_outline, 'r', encoding='utf-8') as f: outlines = json.load(f)
                with open(f_glossary, 'r', encoding='utf-8') as f: glossary = json.load(f)
                log_status("CACHE", "Loaded Outline/Glossary cache.", "OK")
            except Exception: outlines = []
        
        if not outlines:
            LibraryManager.load_from_csv(LIBRARY_CSV_PATH)
            # 随机抽取一个童话原型
            fairytale_source = random.choice(LibraryManager.stories)
            style = random.choice(LibraryManager.styles)
            outlines, glossary = await self.run_outline(fairytale_source, style)

        if not outlines: return [], [], []

        en_scripts = []
        f_en = os.path.join(self.folder, "2_en_scripts.json")
        if REUSE_OPENAI_SCRIPT and os.path.exists(f_en):
            try:
                with open(f_en, 'r', encoding='utf-8') as f: en_scripts = json.load(f)
                log_status("CACHE", "Loaded EN cache.", "OK")
            except Exception: en_scripts = []
        if not en_scripts: en_scripts = await self.run_expansion_en(outlines)

        cn_scripts = []
        f_cn = os.path.join(self.folder, "3_cn_scripts.json")
        if REUSE_DEEPSEEK_SCRIPT and os.path.exists(f_cn):
            try:
                with open(f_cn, 'r', encoding='utf-8') as f: cn_scripts = json.load(f)
                log_status("CACHE", "Loaded CN cache.", "OK")
            except Exception: cn_scripts = []
        if not cn_scripts: cn_scripts = await self.run_localization_cn(en_scripts, glossary)

        img_prompts = []
        f_img = os.path.join(self.folder, "4_img_prompts.json")
        if REUSE_IMAGE_PROMPT and os.path.exists(f_img):
            try:
                with open(f_img, 'r', encoding='utf-8') as f: img_prompts = json.load(f)
                log_status("CACHE", "Loaded Image prompts.", "OK")
            except Exception: img_prompts = []
        if not img_prompts: img_prompts = await self.generate_cinematic_prompts(en_scripts)

        return en_scripts, cn_scripts, img_prompts

class MediaPipeline:
    def __init__(self, folder: str, segments: list[MediaSegment]):
        self.folder = folder
        self.segments = segments

    def _master_audio_sync(self, raw_wav: str, mastered_wav: str) -> float:
        try:
            with AudioFile(raw_wav) as f: audio_data, samplerate = f.read(f.frames), f.samplerate
            board = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=150, gain_db=PEDALBOARD_CONFIG["LOW_SHELF_GAIN"]),
                HighShelfFilter(cutoff_frequency_hz=6000, gain_db=PEDALBOARD_CONFIG["HIGH_SHELF_GAIN"]),
                Compressor(threshold_db=PEDALBOARD_CONFIG["COMP_THRESHOLD"], ratio=PEDALBOARD_CONFIG["COMP_RATIO"]),
                Gain(gain_db=2.0), Limiter(threshold_db=PEDALBOARD_CONFIG["LIMIT_DB"])
            ])
            processed_data = board(audio_data, samplerate)
            with AudioFile(mastered_wav, 'w', samplerate, processed_data.shape[0]) as f: f.write(processed_data)
            return len(AudioSegment.from_file(mastered_wav)) / 1000.0
        except Exception as e:
            return 0.0

    async def _generate_image(self, prompt: str, img_path: str) -> bool:
        if os.path.exists(img_path): return True
        client = APIClients.get_http()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RUNNINGHUB_CONFIG['KEY']}"}
        payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": prompt}]}
        base_url, task_id = "[https://www.runninghub.ai/openapi/v2](https://www.runninghub.ai/openapi/v2)", None
        for _ in range(15):
            try:
                resp = await client.post(f"{base_url}/run/workflow/{RUNNINGHUB_CONFIG['WF_T2I']}", headers=headers, json=payload)
                if (err := resp.json().get("errorCode")) == "421": await asyncio.sleep(5); continue
                task_id = resp.json().get("taskId")
                if task_id: break
            except: await asyncio.sleep(5)
        if not task_id: return False
        t0 = time.time()
        while time.time() - t0 < RUNNINGHUB_TIMEOUT_SEC:
            try:
                q_json = (await client.post(f"{base_url}/query", headers=headers, json={{"taskId": task_id}})).json()
                status = q_json.get("status", "").upper()
                if status == "SUCCESS":
                    img_url = ""
                    def find_url(d):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if k in ['fileUrl', 'url'] and v.startswith('http'): return v
                                if (res := find_url(v)): return res
                        return ""
                    if (img_url := find_url(q_json)):
                        with open(img_path, "wb") as f: f.write((await client.get(img_url)).content)
                        return True
                    break
                elif status == "FAILED": break
            except: pass
            await asyncio.sleep(API_POLL_INTERVAL_SEC)
        return False

    def _encode_video_sync(self, img_path: str, duration: float, clip_path: str, movement: str):
        if os.path.exists(clip_path): return True
        fps, frames = 25, int(duration * 25)
        base = "crop=1920:1080,scale=3840:2160,format=yuv420p"
        end = "scale=1920:1080"
        # 【Bugfix保持】d={frames}
        zp = f"{base},zoompan=z='min(1.15, 1.001+0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:fps={fps},{end}" \
             if movement == "zoom_in" else \
             f"{base},zoompan=z='max(1.001, 1.15-0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:fps={fps},{end}"
        cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path, 
               '-vf', zp, '-c:v', 'h264_nvenc', '-preset', 'p4', clip_path]
        try:
            subprocess.run(cmd, capture_output=True, check=True); return True
        except: return False

    async def _process_segment_en(self, seg: MediaSegment):
        if not seg.en_text: return
        try:
            raw_mp3 = os.path.join(self.folder, f"s{seg.index:03d}_en_raw.mp3")
            if not os.path.exists(seg.en_audio_path):
                async with ConcurrencyManager.TTS_SEM:
                    await edge_tts.Communicate(seg.en_text, MODEL_CONFIG["VOICE_EN"], rate="-15%").save(raw_mp3)
                seg.en_duration = await asyncio.to_thread(self._master_audio_sync, raw_mp3, seg.en_audio_path)
            else:
                seg.en_duration = len(AudioSegment.from_file(seg.en_audio_path)) / 1000.0
            if seg.en_duration <= 0: return
            async with ConcurrencyManager.IMG_SEM:
                if not await self._generate_image(seg.img_prompt, seg.img_path): return
            async with ConcurrencyManager.NVENC_SEM:
                if not await asyncio.to_thread(self._encode_video_sync, seg.img_path, seg.en_duration, seg.en_video_path, random.choice(["zoom_in", "zoom_out"])): return
            seg.is_valid_en = True
            log_status("MEDIA_EN", f"Seg {seg.index} (~{seg.en_duration:.1f}s).", "OK")
        except: pass

    async def _process_segment_cn(self, seg: MediaSegment):
        if not seg.is_valid_en or not seg.cn_text: return
        try:
            raw_mp3 = os.path.join(self.folder, f"s{seg.index:03d}_cn_raw.mp3")
            if not os.path.exists(seg.cn_audio_path):
                async with ConcurrencyManager.TTS_SEM:
                    await edge_tts.Communicate(seg.cn_text, MODEL_CONFIG["VOICE_CN"], rate="-15%").save(raw_mp3)
                seg.cn_duration = await asyncio.to_thread(self._master_audio_sync, raw_mp3, seg.cn_audio_path)
            else:
                seg.cn_duration = len(AudioSegment.from_file(seg.cn_audio_path)) / 1000.0
            if seg.cn_duration <= 0: return
            async with ConcurrencyManager.NVENC_SEM:
                if not await asyncio.to_thread(self._encode_video_sync, seg.img_path, seg.cn_duration, seg.cn_video_path, random.choice(["zoom_in", "zoom_out"])): return
            seg.is_valid_cn = True
            log_status("MEDIA_CN", f"Seg {seg.index} (~{seg.cn_duration:.1f}s).", "OK")
        except: pass

    def assemble(self, output_name: str, mode: str = "EN"):
        v_concat = os.path.join(self.folder, "v.txt"); a_concat = os.path.join(self.folder, "a.txt")
        segs = [s for s in self.segments if (s.is_valid_en if mode == "EN" else s.is_valid_cn)]
        if not segs: return
        with open(v_concat, "w") as fv, open(a_concat, "w") as fa:
            for s in segs:
                fv.write(f"file '{os.path.abspath(s.en_video_path if mode == 'EN' else s.cn_video_path)}'\n")
                fa.write(f"file '{os.path.abspath(s.en_audio_path if mode == 'EN' else s.cn_audio_path)}'\n")
        v_out, a_out = os.path.join(self.folder, "vo.mp4"), os.path.join(self.folder, "ao.wav")
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', v_out], capture_output=True)
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', a_out], capture_output=True)
        subprocess.run(['ffmpeg', '-y', '-i', v_out, '-i', a_out, '-c:v', 'copy', '-shortest', os.path.join(self.folder, output_name)], capture_output=True)
        log_status("STUDIO", f"Assembled: {output_name}", "SUCCESS")

# =====================================================================
# 7. MAIN ORCHESTRATOR
# =====================================================================

def construct_media_segments(folder: str, en_scripts: list, cn_scripts: list, img_prompts: list) -> list[MediaSegment]:
    segments = []
    for i in range(len(en_scripts)):
        segments.append(MediaSegment(
            index=i+1, en_text=en_scripts[i], cn_text=cn_scripts[i] if i < len(cn_scripts) else "",
            img_prompt=img_prompts[i] if i < len(img_prompts) else "Scene",
            img_path=os.path.join(folder, f"s{i+1:03d}_i.png"),
            en_audio_path=os.path.join(folder, f"s{i+1:03d}_e.wav"), cn_audio_path=os.path.join(folder, f"s{i+1:03d}_c.wav"),
            en_video_path=os.path.join(folder, f"s{i+1:03d}_e.mp4"), cn_video_path=os.path.join(folder, f"s{i+1:03d}_c.mp4")
        ))
    return segments

async def main():
    log_status("SYSTEM", "--- V99 Pet & Pretty Startup ---", "START")
    ConcurrencyManager.init_locks()
    if not validate_environment(): return
    try: 
        folder = setup_workspace(TARGET_WORKSPACE)
        story_pipe = StoryPipeline(folder)
        en_scripts, cn_scripts, img_prompts = await story_pipe.build_full_story()
        if ONLY_GENERATE_SCRIPT or not en_scripts: return
        media_pipe = MediaPipeline(folder, construct_media_segments(folder, en_scripts, cn_scripts, img_prompts))
        await media_pipe.run_english_track()
        media_pipe.assemble("STORY_EN.mp4", "EN")
        await media_pipe.run_chinese_track()
        media_pipe.assemble("STORY_CN.mp4", "CN")
    finally:
        await APIClients.close_all()
        log_status("SYSTEM", " रिसोर्स क्लीनअप।", "INFO")

if __name__ == "__main__":
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())