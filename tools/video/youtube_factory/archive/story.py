# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches, too-many-instance-attributes, missing-docstring
"""
AI Audio Masterclass Factory V98 - The Bugfix Edition
Features: Fixed FFMPEG Zoompan animation (d={frames}), Fixed Invalid Edge-TTS Voice Name.
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

REUSE_GEMINI_OUTLINE = False
REUSE_OPENAI_SCRIPT = False
REUSE_DEEPSEEK_SCRIPT = False
REUSE_IMAGE_PROMPT = False
REUSE_TTS = False

TARGET_WORKSPACE = "D:/AIGen/MasterFactory_Dual/Cinderella_Starlight"
LIBRARY_CSV_PATH = "D:/AIGen/Script/AIGen/library.csv"

RUNNINGHUB_TIMEOUT_SEC = 600
API_POLL_INTERVAL_SEC = 10
HTTP_TIMEOUT_SEC = 60.0

MODEL_CONFIG = {
    "G_MODEL": "gemini-2.5-pro",
    "O_MODEL": "gpt-4o-mini",
    "D_MODEL": "deepseek-ai/DeepSeek-V3",
    "VOICE_EN": "en-GB-SoniaNeural",
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
# 2. SCHEMA & PROMPTS
# =====================================================================

class ExpandedScene(BaseModel):
    paragraphs: list[str] = Field(
        description="Exactly 4 distinct paragraphs. Each approx 150 words long.",
        min_items=4,
        max_items=4
    )

PROMPT_CONFIG = {
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
                base_url="https://api.siliconflow.com/v1"
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
        log_status("ENV_CHECK", f"FFMPEG not found or failed to execute: {e}", "ERROR")
        is_valid = False

    if is_valid:
        log_status("ENV_CHECK", "All API keys and dependencies verified.", "OK")
    return is_valid

def setup_workspace(folder_path: str) -> str:
    os.makedirs(folder_path, exist_ok=True)
    log_status("ENV", f"Workspace ready at {folder_path}", "OK")
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
        log_status("JSON", "Failed to parse Gemini JSON object. Returning empty.", "ERROR")
        return {}

def save_json_formatted(filepath: str, data: any):
    try:
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        log_status("FILE", f"Saved formatted JSON to {os.path.basename(filepath)}", "OK")
    except Exception as e:
        log_status("FILE", f"Failed to save JSON {filepath}: {e}", "ERROR")

class LibraryManager:
    stories = ["A peaceful sleep story"]
    characters = ["A quiet traveler"]
    styles = ["Calming, serene, atmospheric"]

    @classmethod
    def load_from_csv(cls, filepath: str):
        if not os.path.exists(filepath):
            log_status("LIBRARY", f"CSV not found at {filepath}. Using system fallbacks.", "WARN")
            return
        try:
            with open(filepath, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [field.strip().lower() for field in reader.fieldnames or []]
                s_list, c_list, st_list = [], [], []
                for row in reader:
                    if row.get('story') and row['story'].strip(): s_list.append(row['story'].strip())
                    if row.get('character') and row['character'].strip(): c_list.append(row['character'].strip())
                    if row.get('style') and row['style'].strip(): st_list.append(row['style'].strip())
                if s_list: cls.stories = s_list
                if c_list: cls.characters = c_list
                if st_list: cls.styles = st_list
            log_status("LIBRARY", f"Loaded successfully: {len(cls.stories)} stories.", "OK")
        except Exception as e:
            log_status("LIBRARY", f"Failed to parse CSV: {e}", "ERROR")

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

    async def run_outline(self, story: str, char: str, style: str) -> tuple[list, dict]:
        log_status("STORY", f"Generating outline & glossary for: {story[:30]}...", "INFO")
        prompt = PROMPT_CONFIG["GEMINI_OUTLINE"].format(story=story, character=char, style=style)
        try:
            res = await robust_gemini_call(prompt)
            data = safe_json_loads(res)
            outline = data.get("outline", [])
            glossary = data.get("glossary", {})
            
            if len(outline) == 8:
                save_json_formatted(os.path.join(self.folder, "1_outlines.json"), outline)
                save_json_formatted(os.path.join(self.folder, "1_glossary.json"), glossary)
                log_status("STORY", f"Successfully generated outline and {len(glossary)} glossary terms.", "OK")
                return outline, glossary
                
            log_status("STORY", f"Outline format failed. Expected 8 blocks, got {len(outline)}.", "ERROR")
            return [], {}
        except Exception as e:
            log_status("STORY", f"Outline generation crashed: {repr(e)}", "ERROR")
            return [], {}

    async def _expand_single(self, outline: str, idx: int) -> list:
        async with ConcurrencyManager.LLM_SEM:
            try:
                chunks = await robust_openai_call(PROMPT_CONFIG["OPENAI_EXPAND"].format(outline=outline))
                log_status("OPENAI", f"Expanded Block {idx+1} into {len(chunks)} flawless chunks.", "OK")
                return chunks
            except Exception as e:
                log_status("OPENAI", f"Expansion completely failed for block {idx+1}: {repr(e)}", "ERROR")
                return []

    async def run_expansion_en(self, outlines: list) -> list:
        log_status("STORY", "Expanding outlines concurrently (Structured Outputs)...", "INFO")
        tasks = [self._expand_single(ol, i) for i, ol in enumerate(outlines)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        en_scripts_flattened = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log_status("OPENAI", f"Block {i+1} resulted in Exception: {repr(r)}", "ERROR")
            elif isinstance(r, list):
                en_scripts_flattened.extend(r)
                
        log_status("STORY", f"Successfully flattened {len(outlines)} blocks into {len(en_scripts_flattened)} 1-min segments.", "SUCCESS")
        save_json_formatted(os.path.join(self.folder, "2_en_scripts.json"), en_scripts_flattened)
        return en_scripts_flattened

    async def _rewrite_single(self, en_text: str, idx: int, glossary_str: str) -> str:
        async with ConcurrencyManager.LLM_SEM:
            try:
                prompt = PROMPT_CONFIG["DEEPSEEK_REWRITE"].format(english_text=en_text, glossary=glossary_str)
                res = await robust_deepseek_call(prompt)
                log_status("DEEPSEEK", f"Rewrote 1-min segment {idx+1}.", "OK")
                return res.strip()
            except Exception as e:
                log_status("DEEPSEEK", f"Rewrite failed for segment {idx+1}: {repr(e)}", "ERROR")
                raise e

    async def run_localization_cn(self, en_scripts: list, glossary: dict) -> list:
        log_status("STORY", f"Localizing {len(en_scripts)} 1-min segments with Glossary injection...", "INFO")
        glossary_str = "\n".join([f"- {k}: {v}" for k, v in glossary.items()]) if glossary else "无强制要求。"
        
        tasks = [self._rewrite_single(st, i, glossary_str) if st else asyncio.sleep(0) for i, st in enumerate(en_scripts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        cn_scripts = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                cn_scripts.append("")
            else:
                cn_scripts.append(r)
                
        save_json_formatted(os.path.join(self.folder, "3_cn_scripts.json"), cn_scripts)
        return cn_scripts

    async def _generate_cinematic_prompt_single(self, text: str, idx: int) -> str:
        if not text:
            return "Fallback empty scene. [Studio Ghibli animation style, moody lighting, masterpiece]"
            
        async with ConcurrencyManager.LLM_SEM:
            prompt = PROMPT_CONFIG["SCENE_PROMPT_GEMINI"].format(text=text)
            try:
                res = await robust_gemini_call(prompt)
                log_status("SCENE", f"Framed Seg {idx+1}", "OK")
                return res.replace("\n", "").strip()
            except Exception as e:
                log_status("SCENE", f"Failed Seg {idx+1}: {repr(e)}", "ERROR")
                return "Beautiful serene sleep story scene. [Studio Ghibli animation style, moody lighting, masterpiece]"

    async def generate_cinematic_prompts(self, en_scripts: list) -> list:
        log_status("STORY", "Directing cinematic image prompts concurrently...", "INFO")
        tasks = [self._generate_cinematic_prompt_single(text, i) for i, text in enumerate(en_scripts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_prompts = [r if not isinstance(r, Exception) else "Fallback scene." for r in results]
        save_json_formatted(os.path.join(self.folder, "4_img_prompts.json"), final_prompts)
        return final_prompts

    async def build_full_story(self) -> tuple[list, list, list]:
        outlines = []
        glossary = {}
        
        f_outline = os.path.join(self.folder, "1_outlines.json")
        f_glossary = os.path.join(self.folder, "1_glossary.json")
        
        if REUSE_GEMINI_OUTLINE and os.path.exists(f_outline) and os.path.exists(f_glossary):
            try:
                with open(f_outline, 'r', encoding='utf-8') as f: outlines = json.load(f)
                with open(f_glossary, 'r', encoding='utf-8') as f: glossary = json.load(f)
                log_status("CACHE", f"Loaded outlines and glossary from cache.", "OK")
            except Exception as e: 
                log_status("CACHE", f"Failed to read outline cache: {e}", "ERROR")
        
        if not outlines:
            log_status("STORY", "No valid outline cache found. Generating new outline & glossary...", "INFO")
            LibraryManager.load_from_csv(LIBRARY_CSV_PATH)
            story = random.choice(LibraryManager.stories)
            char = random.choice(LibraryManager.characters)
            style = random.choice(LibraryManager.styles)
            outlines, glossary = await self.run_outline(story, char, style)

        if not outlines:
            log_status("STORY", "Failed to obtain outlines. Aborting.", "ERROR")
            return [], [], []

        en_scripts = []
        f_en = os.path.join(self.folder, "2_en_scripts.json")
        if REUSE_OPENAI_SCRIPT and os.path.exists(f_en):
            try:
                with open(f_en, 'r', encoding='utf-8') as f: en_scripts = json.load(f)
                log_status("CACHE", f"Loaded English scripts from cache.", "OK")
            except Exception as e: log_status("CACHE", f"Failed to read EN cache: {e}", "ERROR")
            
        if not en_scripts:
            log_status("STORY", "No valid EN script cache. Expanding...", "INFO")
            en_scripts = await self.run_expansion_en(outlines)

        cn_scripts = []
        f_cn = os.path.join(self.folder, "3_cn_scripts.json")
        if REUSE_DEEPSEEK_SCRIPT and os.path.exists(f_cn):
            try:
                with open(f_cn, 'r', encoding='utf-8') as f: cn_scripts = json.load(f)
                log_status("CACHE", f"Loaded Chinese scripts from cache.", "OK")
            except Exception as e: log_status("CACHE", f"Failed to read CN cache: {e}", "ERROR")
            
        if not cn_scripts:
            log_status("STORY", "No valid CN script cache. Translating...", "INFO")
            cn_scripts = await self.run_localization_cn(en_scripts, glossary)

        img_prompts = []
        f_img = os.path.join(self.folder, "4_img_prompts.json")
        if REUSE_IMAGE_PROMPT and os.path.exists(f_img):
            try:
                with open(f_img, 'r', encoding='utf-8') as f: img_prompts = json.load(f)
                log_status("CACHE", f"Loaded Image prompts from cache.", "OK")
            except Exception as e: log_status("CACHE", f"Failed to read Image cache: {e}", "ERROR")
            
        if not img_prompts:
            log_status("STORY", "No valid Image prompt cache. Generating...", "INFO")
            img_prompts = await self.generate_cinematic_prompts(en_scripts)

        return en_scripts, cn_scripts, img_prompts

class MediaPipeline:
    def __init__(self, folder: str, segments: list[MediaSegment]):
        self.folder = folder
        self.segments = segments

    def _master_audio_sync(self, raw_wav: str, mastered_wav: str) -> float:
        try:
            with AudioFile(raw_wav) as f: 
                audio_data, samplerate = f.read(f.frames), f.samplerate
                
            board = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=150, gain_db=PEDALBOARD_CONFIG["LOW_SHELF_GAIN"]),
                HighShelfFilter(cutoff_frequency_hz=6000, gain_db=PEDALBOARD_CONFIG["HIGH_SHELF_GAIN"]),
                Compressor(threshold_db=PEDALBOARD_CONFIG["COMP_THRESHOLD"], ratio=PEDALBOARD_CONFIG["COMP_RATIO"]),
                Gain(gain_db=2.0), Limiter(threshold_db=PEDALBOARD_CONFIG["LIMIT_DB"])
            ])
            processed_data = board(audio_data, samplerate)
            
            with AudioFile(mastered_wav, 'w', samplerate, processed_data.shape[0]) as f: 
                f.write(processed_data)
                
            return len(AudioSegment.from_file(mastered_wav)) / 1000.0
        except Exception as e:
            log_status("AUDIO", f"Mastering failed: {e}", "ERROR")
            return 0.0

    async def _generate_image(self, prompt: str, img_path: str) -> bool:
        if os.path.exists(img_path): return True
        client = APIClients.get_http()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RUNNINGHUB_CONFIG['KEY']}"}
        payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": prompt}]}
        
        base_url = "[https://www.runninghub.ai/openapi/v2](https://www.runninghub.ai/openapi/v2)"
        url_run = f"{base_url}/run/workflow/{RUNNINGHUB_CONFIG['WF_T2I']}"
        url_query = f"{base_url}/query"
        
        task_id = None
        for _ in range(15):
            try:
                resp = await client.post(url_run, headers=headers, json=payload)
                r_json = resp.json()
                if str(r_json.get("errorCode")) == "421":
                    await asyncio.sleep(5)
                    continue
                task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
                if task_id: break
            except Exception:
                await asyncio.sleep(5)
            
        if not task_id: return False

        t0 = time.time()
        while time.time() - t0 < RUNNINGHUB_TIMEOUT_SEC:
            try:
                q_resp = await client.post(url_query, headers=headers, json={"taskId": task_id})
                q_json = q_resp.json()
                status = (q_json.get("status") or q_json.get("data", {}).get("status", "")).upper()
                
                if status == "SUCCESS":
                    img_url = ""
                    def find_url(d):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if k in ['fileUrl', 'url', 'image_url'] and isinstance(v, str) and v.startswith('http'): return v
                                if res := find_url(v): return res
                        elif isinstance(d, list):
                            for i in d:
                                if res := find_url(i): return res
                        return ""
                    img_url = find_url(q_json)
                    if img_url:
                        img_resp = await client.get(img_url, timeout=HTTP_TIMEOUT_SEC)
                        with open(img_path, "wb") as f: f.write(img_resp.content)
                        return True
                    break
                elif status == "FAILED": break
            except Exception: pass
            await asyncio.sleep(API_POLL_INTERVAL_SEC)
            
        return False

    def _encode_video_sync(self, img_path: str, duration: float, clip_path: str, movement: str):
        if os.path.exists(clip_path): return True
        fps, frames = 25, int(duration * 25)
        base = "crop=1920:1080,scale=3840:2160"
        end = "scale=1920:1080"
        
        # 【修复点 1】FFMPEG Zoompan 动画持续时间已修正为 d={frames}
        if movement == "zoom_in": 
            zp = f"{base},zoompan=z='min(1.15, 1.001+0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=3840x2160:fps={fps},{end}"
        else: 
            zp = f"{base},zoompan=z='max(1.001, 1.15-0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=3840x2160:fps={fps},{end}"

        cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path, 
               '-vf', f"format=yuv420p,{zp}", '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p', clip_path]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return True
        except: return False

    async def _process_segment_en(self, seg: MediaSegment):
        if not seg.en_text: return
        try:
            raw_wav = os.path.join(self.folder, f"s{seg.index:03d}_en_raw.mp3")
            if not (REUSE_TTS and os.path.exists(seg.en_audio_path)):
                async with ConcurrencyManager.TTS_SEM:
                    await edge_tts.Communicate(seg.en_text, MODEL_CONFIG["VOICE_EN"], rate="-15%").save(raw_wav)
                seg.en_duration = await asyncio.to_thread(self._master_audio_sync, raw_wav, seg.en_audio_path)
            else:
                seg.en_duration = len(AudioSegment.from_file(seg.en_audio_path)) / 1000.0

            if seg.en_duration <= 0: return

            async with ConcurrencyManager.IMG_SEM:
                img_ok = await self._generate_image(seg.img_prompt, seg.img_path)
            if not img_ok: return
            
            movement = random.choice(["zoom_in", "zoom_out"])
            async with ConcurrencyManager.NVENC_SEM:
                encode_ok = await asyncio.to_thread(self._encode_video_sync, seg.img_path, seg.en_duration, seg.en_video_path, movement)
            
            if not encode_ok: return
            seg.is_valid_en = True
            log_status("MEDIA_EN", f"Seg {seg.index} ready (~{seg.en_duration:.1f}s).", "OK")
        except Exception as e:
            log_status("MEDIA_EN", f"Seg {seg.index} failed: {repr(e)}", "ERROR")

    async def _process_segment_cn(self, seg: MediaSegment):
        if not seg.is_valid_en or not seg.cn_text or not os.path.exists(seg.img_path): return
        try:
            raw_wav = os.path.join(self.folder, f"s{seg.index:03d}_cn_raw.mp3")
            if not (REUSE_TTS and os.path.exists(seg.cn_audio_path)):
                async with ConcurrencyManager.TTS_SEM:
                    await edge_tts.Communicate(seg.cn_text, MODEL_CONFIG["VOICE_CN"], rate="-15%").save(raw_wav)
                seg.cn_duration = await asyncio.to_thread(self._master_audio_sync, raw_wav, seg.cn_audio_path)
            else:
                seg.cn_duration = len(AudioSegment.from_file(seg.cn_audio_path)) / 1000.0

            if seg.cn_duration <= 0: return

            movement = random.choice(["zoom_in", "zoom_out"])
            async with ConcurrencyManager.NVENC_SEM:
                encode_ok = await asyncio.to_thread(self._encode_video_sync, seg.img_path, seg.cn_duration, seg.cn_video_path, movement)
                
            if not encode_ok: return
            seg.is_valid_cn = True
            log_status("MEDIA_CN", f"Seg {seg.index} ready (~{seg.cn_duration:.1f}s).", "OK")
        except Exception as e:
            log_status("MEDIA_CN", f"Seg {seg.index} failed: {repr(e)}", "ERROR")

    async def run_english_track(self):
        log_status("PIPELINE", f"Starting English Track ({len(self.segments)} segments)...", "INFO")
        tasks = [self._process_segment_en(seg) for seg in self.segments]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run_chinese_track(self):
        log_status("PIPELINE", f"Starting Chinese Track ({len(self.segments)} segments)...", "INFO")
        tasks = [self._process_segment_cn(seg) for seg in self.segments]
        await asyncio.gather(*tasks, return_exceptions=True)

    def assemble(self, output_name: str, mode: str = "EN"):
        prefix = output_name.split('.')[0]
        v_concat = os.path.join(self.folder, f"{prefix}_v.txt")
        a_concat = os.path.join(self.folder, f"{prefix}_a.txt")
        
        valid_segs = [s for s in self.segments if (s.is_valid_en if mode == "EN" else s.is_valid_cn)]
        if not valid_segs:
            log_status("STUDIO", f"No valid segments found to assemble for {mode}.", "ERROR")
            return

        try:
            with open(v_concat, "w", encoding='utf-8') as fv, open(a_concat, "w", encoding='utf-8') as fa:
                for s in valid_segs:
                    v_path = os.path.abspath(s.en_video_path if mode == 'EN' else s.cn_video_path)
                    a_path = os.path.abspath(s.en_audio_path if mode == 'EN' else s.cn_audio_path)
                    fv.write(f"file '{v_path}'\n")
                    fa.write(f"file '{a_path}'\n")

            v_out = os.path.join(self.folder, f"{prefix}_master_v.mp4")
            a_out = os.path.join(self.folder, f"{prefix}_master_a.wav")
            
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', v_out], capture_output=True, check=True)
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', a_out], capture_output=True, check=True)

            final_out = os.path.join(self.folder, output_name)
            cmd = ['ffmpeg', '-y', '-i', v_out, '-i', a_out, '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_out]
            subprocess.run(cmd, capture_output=True, check=True)
            log_status("STUDIO", f"Completed Assembly: {final_out}", "SUCCESS")
        except Exception as e:
            log_status("STUDIO", f"Assemble failed: {repr(e)}", "ERROR")

# =====================================================================
# 7. MAIN ORCHESTRATOR
# =====================================================================

def construct_media_segments(folder: str, en_scripts: list, cn_scripts: list, img_prompts: list) -> list[MediaSegment]:
    segments = []
    for i in range(len(en_scripts)):
        seg = MediaSegment(
            index=i+1, 
            en_text=en_scripts[i], 
            cn_text=cn_scripts[i] if i < len(cn_scripts) else "",
            img_prompt=img_prompts[i] if i < len(img_prompts) else "Scene",
            img_path=os.path.join(folder, f"s{i+1:03d}_img.png"),
            en_audio_path=os.path.join(folder, f"s{i+1:03d}_en.wav"), 
            cn_audio_path=os.path.join(folder, f"s{i+1:03d}_cn.wav"),
            en_video_path=os.path.join(folder, f"s{i+1:03d}_en.mp4"), 
            cn_video_path=os.path.join(folder, f"s{i+1:03d}_cn.mp4")
        )
        segments.append(seg)
    return segments

async def main():
    log_status("SYSTEM", "--- V98 PIPELINE START ---", "START")
    
    ConcurrencyManager.init_locks()
    if not validate_environment(): return

    try: 
        folder = setup_workspace(TARGET_WORKSPACE)
        story_pipe = StoryPipeline(folder)
        
        en_scripts, cn_scripts, img_prompts = await story_pipe.build_full_story()
        
        if ONLY_GENERATE_SCRIPT: 
            log_status("SYSTEM", "Script Gen Only Mode active. Exiting.", "INFO")
            return

        if not en_scripts:
            log_status("SYSTEM", "No valid scripts available. Exiting.", "ERROR")
            return

        segments = construct_media_segments(folder, en_scripts, cn_scripts, img_prompts)
        media_pipe = MediaPipeline(folder, segments)
        
        await media_pipe.run_english_track()
        media_pipe.assemble("FINAL_STORY_EN.mp4", "EN")
        
        await media_pipe.run_chinese_track()
        media_pipe.assemble("FINAL_STORY_CN.mp4", "CN")

    except Exception as e: 
        log_status("SYSTEM", f"Critical Pipeline Failure: {repr(e)}", "CRITICAL")
    finally:
        await APIClients.close_all()
        log_status("SYSTEM", "Resources cleaned up gracefully.", "INFO")

if __name__ == "__main__":
    if sys.platform == 'win32': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())