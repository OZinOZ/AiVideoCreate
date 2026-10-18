# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches, too-many-instance-attributes
"""
AI Audio Masterclass Factory V89 - The "Artery Reconnected" Edition
Features: Full Async Concurrency + Matrix Director + Cinematic Frame Prompts.
"""

import os
import sys
import asyncio
import re
import json
import time
import shutil
import subprocess
import csv
import random
from datetime import datetime
from dataclasses import dataclass

import httpx

# Google, OpenAI & DeepSeek
from google import genai
from openai import AsyncOpenAI

# Media Tools
import edge_tts
from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
from pedalboard.io import AudioFile

# Engineering Tools
from tenacity import retry, stop_after_attempt, wait_exponential

# =====================================================================
# 1. GLOBAL CONFIGURATION (全局配置区)
# =====================================================================

# Test & Cache Configs
ONLY_GENERATE_SCRIPT = False
IS_AUTO_UPLOAD = False
AUTO_CLEANUP_TEMP = False

REUSE_GEMINI_IDEA = True
REUSE_OPENAI_SCRIPT = True
REUSE_TTS = True
REUSE_TARGET_FOLDER = r"D:\AIGen\MasterFactory_V49\20260320_1056\Mastering Internal Triggers fo"

# System Limits & Timeouts
CONCURRENCY_LIMIT = 3
RUNNINGHUB_TIMEOUT_SEC = 600
API_POLL_INTERVAL_SEC = 10
HTTP_TIMEOUT_SEC = 60.0

# Model Names & Voices
MODEL_CONFIG = {
    "G_MODEL": "gemini-2.5-pro",
    "O_MODEL": "gpt-4o-mini",
    "D_MODEL": "deepseek-chat",
    "VOICE_EN": "en-AU-WilliamNeural",
    "VOICE_CN": "zh-CN-YunxiNeural"
}

# Path Settings
CONFIG = {
    "BASE_PATH": "D:/AIGen/MasterFactory_Dual",
    "CSV_PATH": "D:/AIGen/MasterFactory_Dual/config/story.csv",
    "ASSETS_POOL": {
        "audios": ["D:/Assets/A/rain.mp3", "D:/Assets/A/wind.mp3"],
        "overlays": ["D:/Assets/V/ghibli_dust.mp4", "D:/Assets/V/light_rays.mp4"]
    }
}

PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 5.0, "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -18.0, "COMP_RATIO": 3.0, "LIMIT_DB": -3.0
}

RUNNINGHUB_CONFIG = {
    "KEY": os.getenv("RUNNINGHUB_API_KEY"),
    "WF_T2I": "2014487614874718210",
    "T2I_NODE": "111"
}

# =====================================================================
# 2. DATA STRUCTURES & SINGLETONS (数据结构与单例)
# =====================================================================

@dataclass
class MediaSegment:
    """严格对齐的媒体段落数据结构"""
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

class APIClients:
    """统一管理 API 客户端，避免重复创建引起连接泄露"""
    _openai = None
    _deepseek = None
    _gemini = None

    @classmethod
    def get_openai(cls):
        if not cls._openai: 
            cls._openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return cls._openai

    @classmethod
    def get_deepseek(cls):
        if not cls._deepseek: 
            cls._deepseek = AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com/v1")
        return cls._deepseek

    @classmethod
    def get_gemini(cls):
        if not cls._gemini: 
            cls._gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return cls._gemini

# =====================================================================
# 3. DIRECTORS POOLS & PROMPTS (导演武器库 - 大动脉恢复！)
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

PROMPT_CONFIG = {
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

# =====================================================================
# 4. UTILITIES (工具函数)
# =====================================================================

def log_status(stage: str, msg: str, status: str = "INFO"):
    time_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{time_str}] [{stage:<10}] [{status:<5}] {msg}")

def safe_json_loads(text: str) -> list:
    """健壮的 JSON 解析器，防 Markdown 和非标准字符"""
    try:
        text = re.sub(r'```json\n|\n```|```', '', text).strip()
        return json.loads(text)
    except Exception:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try: return json.loads(match.group())
            except Exception: pass
        return []

def get_random_item(pool: list, name: str) -> str:
    item = random.choice(pool)
    log_status("CASTING", f"Selected {name}: {item[:50]}...", "OK")
    return item

def load_random_story_from_csv(csv_path: str) -> str:
    if not os.path.exists(csv_path): return "The Little Prince"
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            stories = [row[0] for row in csv.reader(f) if row]
        return random.choice(stories) if stories else "The Little Prince"
    except Exception: return "The Little Prince"

def setup_environment(force_folder: str = "") -> str:
    if force_folder and os.path.exists(force_folder):
        log_status("ENV", f"Reusing workspace at {force_folder}", "OK")
        return force_folder
    os.makedirs(CONFIG["BASE_PATH"], exist_ok=True)
    session_dir = os.path.join(CONFIG["BASE_PATH"], datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(session_dir, exist_ok=True)
    log_status("ENV", f"Workspace created at {session_dir}", "OK")
    return session_dir

def extract_image_url(data: dict) -> str:
    keys = ['fileUrl', 'url', 'image_url', 'file_url']
    if isinstance(data, dict):
        for k, v in data.items():
            if k in keys and isinstance(v, str) and v.startswith('http'): return v
            if res := extract_image_url(v): return res
    elif isinstance(data, list):
        for item in data:
            if res := extract_image_url(item): return res
    return ""

# =====================================================================
# 5. API WRAPPERS (带限制和重试的调用)
# =====================================================================

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def robust_gemini_call(prompt: str) -> str:
    res = await asyncio.to_thread(APIClients.get_gemini().models.generate_content, model=MODEL_CONFIG["G_MODEL"], contents=prompt)
    return res.text

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def robust_openai_call(prompt: str) -> str:
    res = await APIClients.get_openai().chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": prompt}])
    return res.choices[0].message.content

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def robust_deepseek_call(prompt: str) -> str:
    res = await APIClients.get_deepseek().chat.completions.create(model=MODEL_CONFIG["D_MODEL"], messages=[{"role": "user", "content": prompt}])
    return res.choices[0].message.content

# =====================================================================
# 6. PIPELINES (业务管线)
# =====================================================================

class StoryPipeline:
    """负责文本生成：大纲 -> 英文扩写 -> 中文转写 -> 并发生成电影级Prompt"""
    def __init__(self, folder: str):
        self.folder = folder
        self.sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def run_outline(self, story: str, char: str, style: str) -> list:
        log_status("STORY", "Generating 8-paragraph outline...", "INFO")
        prompt = PROMPT_CONFIG["GEMINI_OUTLINE"].format(story=story, character=char, style=style)
        res = await robust_gemini_call(prompt)
        data = safe_json_loads(res)
        if len(data) == 8:
            with open(os.path.join(self.folder, "1_outlines.json"), "w", encoding='utf-8') as f: json.dump(data, f)
            return data
        log_status("STORY", "Outline generation failed format check.", "ERROR")
        return []

    async def _expand_single(self, outline: str, idx: int) -> str:
        async with self.sem:
            prompt = PROMPT_CONFIG["OPENAI_EXPAND"].format(outline=outline)
            res = await robust_openai_call(prompt)
            log_status("OPENAI", f"Expanded block {idx+1}/8.", "OK")
            return res.strip()

    async def run_expansion_en(self, outlines: list) -> list:
        log_status("STORY", "Expanding outlines concurrently...", "INFO")
        tasks = [self._expand_single(ol, i) for i, ol in enumerate(outlines)]
        en_scripts = await asyncio.gather(*tasks, return_exceptions=True)
        en_scripts = [s if isinstance(s, str) else "" for s in en_scripts]
        with open(os.path.join(self.folder, "2_en_scripts.json"), "w", encoding='utf-8') as f: json.dump(en_scripts, f)
        return en_scripts

    async def _rewrite_single(self, en_text: str, idx: int) -> str:
        async with self.sem:
            prompt = PROMPT_CONFIG["DEEPSEEK_REWRITE"].format(english_text=en_text)
            res = await robust_deepseek_call(prompt)
            log_status("DEEPSEEK", f"Rewrote block {idx+1}/8.", "OK")
            return res.strip()

    async def run_localization_cn(self, en_scripts: list) -> list:
        log_status("STORY", "Localizing to Chinese concurrently...", "INFO")
        tasks = [self._rewrite_single(st, i) for i, st in enumerate(en_scripts)]
        cn_scripts = await asyncio.gather(*tasks, return_exceptions=True)
        cn_scripts = [s if isinstance(s, str) else "" for s in cn_scripts]
        with open(os.path.join(self.folder, "3_cn_scripts.json"), "w", encoding='utf-8') as f: json.dump(cn_scripts, f)
        return cn_scripts

    async def _generate_cinematic_prompt_single(self, text: str, anchor: str, idx: int) -> str:
        """核心大动脉：恢复独立的场景调度与镜头感"""
        async with self.sem:
            loc = random.choice(LOCATION_POOL)
            cam = random.choice(CAMERA_POOL)
            prompt = PROMPT_CONFIG["SCENE_PROMPT_GEMINI"].format(location=loc, camera=cam, text=text, anchor=anchor)
            try:
                res = await robust_gemini_call(prompt)
                log_status("SCENE", f"Framed Block {idx+1} [Cam: {cam.split(',')[0]}]", "OK")
                return res.replace("\n", "").strip()
            except Exception as e:
                log_status("SCENE", f"Failed Block {idx+1}: {e}", "ERROR")
                return f"Beautiful serene sleep story scene. [{anchor}]"

    async def generate_cinematic_prompts(self, en_scripts: list, anchor: str) -> list:
        """并发执行 8 次独立的电影级画面构图，完美结合并发优势与导演调度的质量"""
        log_status("STORY", "Directing cinematic image prompts concurrently...", "INFO")
        tasks = [self._generate_cinematic_prompt_single(text, anchor, i) for i, text in enumerate(en_scripts)]
        prompts = await asyncio.gather(*tasks)
        return prompts


class MediaPipeline:
    """负责多媒体合成：并发处理 TTS, 生图, 渲染"""
    def __init__(self, folder: str, segments: list[MediaSegment]):
        self.folder = folder
        self.segments = segments
        self.sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

    def _master_audio_sync(self, raw_wav: str, mastered_wav: str) -> float:
        """阻塞型音频处理函数，由 to_thread 调用"""
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

    async def _generate_image_httpx(self, prompt: str, img_path: str) -> bool:
        """异步生图逻辑"""
        if os.path.exists(img_path): return True
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RUNNINGHUB_CONFIG['KEY']}"}
        payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": prompt}]}
        
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
            task_id = None
            for _ in range(30):
                try:
                    resp = await client.post(f"[https://www.runninghub.ai/openapi/v2/run/workflow/](https://www.runninghub.ai/openapi/v2/run/workflow/){RUNNINGHUB_CONFIG['WF_T2I']}", headers=headers, json=payload)
                    r_json = resp.json()
                    if str(r_json.get("errorCode")) == "421":
                        await asyncio.sleep(5)
                        continue
                    task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
                    if task_id: break
                except Exception: await asyncio.sleep(5)
            
            if not task_id: return False

            t0 = time.time()
            img_url = ""
            while time.time() - t0 < RUNNINGHUB_TIMEOUT_SEC:
                try:
                    q_resp = await client.post("[https://www.runninghub.ai/openapi/v2/query](https://www.runninghub.ai/openapi/v2/query)", headers=headers, json={"taskId": task_id})
                    q_json = q_resp.json()
                    status = (q_json.get("status") or q_json.get("data", {}).get("status", "")).upper()
                    if status == "SUCCESS":
                        img_url = extract_image_url(q_json)
                        break
                    elif status == "FAILED": break
                except Exception: pass
                await asyncio.sleep(API_POLL_INTERVAL_SEC)

            if img_url:
                try:
                    img_resp = await client.get(img_url, timeout=HTTP_TIMEOUT_SEC)
                    with open(img_path, "wb") as f: f.write(img_resp.content)
                    return True
                except Exception: return False
        return False

    def _encode_video_sync(self, img_path: str, duration: float, clip_path: str, movement: str):
        """阻塞型 FFMPEG 渲染函数，由 to_thread 调用"""
        if os.path.exists(clip_path): return True
        fps, frames = 25, int(duration * 25)
        base = "crop=1920:1080,scale=3840:2160"
        end = "scale=1920:1080"
        if movement == "zoom_in": zp = f"{base},zoompan=z='min(1.15, 1.001+0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end}"
        else: zp = f"{base},zoompan=z='max(1.001, 1.15-0.15*(in/{frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=3840x2160:fps={fps},{end}"

        cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path, 
               '-vf', f"format=yuv420p,{zp}", '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p', clip_path]
        subprocess.run(cmd, capture_output=True, check=True)
        return True

    async def _process_segment_en(self, seg: MediaSegment):
        """处理单条英文数据流"""
        async with self.sem:
            try:
                raw_wav = os.path.join(self.folder, f"s{seg.index:02d}_en_raw.mp3")
                # TTS
                if not (REUSE_TTS and os.path.exists(seg.en_audio_path)):
                    await edge_tts.Communicate(seg.en_text, MODEL_CONFIG["VOICE_EN"], rate="-15%").save(raw_wav)
                    seg.en_duration = await asyncio.to_thread(self._master_audio_sync, raw_wav, seg.en_audio_path)
                else:
                    seg.en_duration = len(AudioSegment.from_file(seg.en_audio_path)) / 1000.0

                if seg.en_duration <= 0: return

                # Image
                if not await self._generate_image_httpx(seg.img_prompt, seg.img_path): return
                
                # Video
                movement = random.choice(["zoom_in", "zoom_out"])
                await asyncio.to_thread(self._encode_video_sync, seg.img_path, seg.en_duration, seg.en_video_path, movement)
                seg.is_valid_en = True
                log_status("MEDIA_EN", f"Segment {seg.index} ready.", "OK")
            except Exception as e:
                log_status("MEDIA_EN", f"Segment {seg.index} failed: {e}", "ERROR")

    async def _process_segment_cn(self, seg: MediaSegment):
        """处理单条中文数据流 (强制复用图片)"""
        if not seg.is_valid_en or not os.path.exists(seg.img_path): return
        async with self.sem:
            try:
                raw_wav = os.path.join(self.folder, f"s{seg.index:02d}_cn_raw.mp3")
                # TTS
                if not (REUSE_TTS and os.path.exists(seg.cn_audio_path)):
                    await edge_tts.Communicate(seg.cn_text, MODEL_CONFIG["VOICE_CN"], rate="-15%").save(raw_wav)
                    seg.cn_duration = await asyncio.to_thread(self._master_audio_sync, raw_wav, seg.cn_audio_path)
                else:
                    seg.cn_duration = len(AudioSegment.from_file(seg.cn_audio_path)) / 1000.0

                if seg.cn_duration <= 0: return

                # Video
                movement = random.choice(["zoom_in", "zoom_out"])
                await asyncio.to_thread(self._encode_video_sync, seg.img_path, seg.cn_duration, seg.cn_video_path, movement)
                seg.is_valid_cn = True
                log_status("MEDIA_CN", f"Segment {seg.index} ready.", "OK")
            except Exception as e:
                log_status("MEDIA_CN", f"Segment {seg.index} failed: {e}", "ERROR")

    async def run_english_track(self):
        log_status("PIPELINE", "Starting Async English Track...", "INFO")
        tasks = [self._process_segment_en(seg) for seg in self.segments]
        await asyncio.gather(*tasks)

    async def run_chinese_track(self):
        log_status("PIPELINE", "Starting Async Chinese Track...", "INFO")
        tasks = [self._process_segment_cn(seg) for seg in self.segments]
        await asyncio.gather(*tasks)

    def assemble(self, output_name: str, mode: str = "EN"):
        """最终拼接"""
        prefix = output_name.split('.')[0]
        v_concat, a_concat = os.path.join(self.folder, f"{prefix}_v.txt"), os.path.join(self.folder, f"{prefix}_a.txt")
        
        valid_segs = [s for s in self.segments if (s.is_valid_en if mode == "EN" else s.is_valid_cn)]
        if not valid_segs:
            log_status("STUDIO", f"No valid segments for {mode}.", "ERROR")
            return

        with open(v_concat, "w", encoding='utf-8') as fv, open(a_concat, "w", encoding='utf-8') as fa:
            for s in valid_segs:
                fv.write(f"file '{os.path.abspath(s.en_video_path if mode == 'EN' else s.cn_video_path)}'\n")
                fa.write(f"file '{os.path.abspath(s.en_audio_path if mode == 'EN' else s.cn_audio_path)}'\n")

        v_out, a_out = os.path.join(self.folder, f"{prefix}_master_v.mp4"), os.path.join(self.folder, f"{prefix}_master_a.wav")
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', v_out], capture_output=True, check=True)
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', a_out], capture_output=True, check=True)

        final_out = os.path.join(self.folder, output_name)
        cmd = ['ffmpeg', '-y', '-i', v_out, '-i', a_out, '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_out]
        subprocess.run(cmd, capture_output=True, check=True)
        log_status("STUDIO", f"Completed: {final_out}", "SUCCESS")

# =====================================================================
# 7. MAIN ORCHESTRATOR
# =====================================================================

async def execute_v89_pipeline():
    log_status("SYSTEM", "--- V89 ARTERY RECONNECTED PIPELINE START ---", "START")
    
    folder = setup_environment(REUSE_TARGET_FOLDER if REUSE_GEMINI_IDEA else "")
    story_pipe = StoryPipeline(folder)
    
    # 1. 尝试读取缓存 or 新建文案
    en_scripts, cn_scripts, img_prompts = [], [], []
    en_file, cn_file, p_file = os.path.join(folder, "2_en_scripts.json"), os.path.join(folder, "3_cn_scripts.json"), os.path.join(folder, "4_img_prompts.json")
    
    if REUSE_OPENAI_SCRIPT and os.path.exists(en_file) and os.path.exists(cn_file):
        log_status("CACHE", "Loading scripts from cache...", "INFO")
        with open(en_file, 'r', encoding='utf-8') as f: en_scripts = json.load(f)
        with open(cn_file, 'r', encoding='utf-8') as f: cn_scripts = json.load(f)
        if os.path.exists(p_file):
            with open(p_file, 'r', encoding='utf-8') as f: img_prompts = json.load(f)
    else:
        # Generate Flow
        anchor = get_random_item(ANCHOR_POOL, "Visual Anchor")
        outlines = await story_pipe.run_outline(load_random_story_from_csv(CONFIG["CSV_PATH"]), get_random_item(CHARACTER_POOL, "Char"), get_random_item(STYLE_POOL, "Style"))
        if len(outlines) != 8: return
        
        en_scripts = await story_pipe.run_expansion_en(outlines)
        cn_scripts = await story_pipe.run_localization_cn(en_scripts)
        
        # 恢复大动脉：并发执行带场景和镜头调度的生图 Prompt！
        img_prompts = await story_pipe.generate_cinematic_prompts(en_scripts, anchor)
        with open(p_file, 'w', encoding='utf-8') as f: json.dump(img_prompts, f)

    if ONLY_GENERATE_SCRIPT: return log_status("SYSTEM", "Script Gen Only. Exiting.", "INFO")

    # 2. 构建数据对齐结构
    segments = []
    for i in range(len(en_scripts)):
        if not en_scripts[i] or not cn_scripts[i]: continue
        seg = MediaSegment(
            index=i+1, en_text=en_scripts[i], cn_text=cn_scripts[i],
            img_prompt=img_prompts[i] if i < len(img_prompts) else "Beautiful scene",
            img_path=os.path.join(folder, f"s{i+1:02d}_img.png"),
            en_audio_path=os.path.join(folder, f"s{i+1:02d}_en.wav"), cn_audio_path=os.path.join(folder, f"s{i+1:02d}_cn.wav"),
            en_video_path=os.path.join(folder, f"s{i+1:02d}_en.mp4"), cn_video_path=os.path.join(folder, f"s{i+1:02d}_cn.mp4")
        )
        segments.append(seg)

    # 3. 媒体管线执行
    media_pipe = MediaPipeline(folder, segments)
    await media_pipe.run_english_track()
    media_pipe.assemble("FINAL_STORY_EN.mp4", "EN")
    
    await media_pipe.run_chinese_track()
    media_pipe.assemble("FINAL_STORY_CN.mp4", "CN")

async def main():
    try: await execute_v89_pipeline()
    except Exception as e: log_status("SYSTEM", f"Critical Failure: {e}", "CRITICAL")

if __name__ == "__main__":
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())