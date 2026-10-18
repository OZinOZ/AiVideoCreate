# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements
"""
AI Audio Masterclass Factory V90 - The Ultimate Clean Architecture & YouTube Upload
Features: Strict Modularization, Matrix Director, Full Script Gen, NVENC, GBRP Fix, Global TTS Rate, YouTube Auto-Upload.
"""

import os
import sys
import asyncio
import re
import random
import json
import time
import shutil
import subprocess
from datetime import datetime
import requests

# Google & OpenAI
from google import genai
from openai import AsyncOpenAI

# Youtube & Media Tools
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import edge_tts
from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
from pedalboard.io import AudioFile

# Engineering Tools
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, Field

# =====================================================================
# 1. GLOBAL CONFIGURATION (全局配置区)
# =====================================================================

IS_AUTO_SEARCH = False
MANUAL_VIDEO_ID = "rOYlOdDgYUU"

ONLY_GENERATE_SCRIPT = True
IS_AUTO_UPLOAD = False
AUTO_CLEANUP_TEMP = False

# Cache & Resume Settings
REUSE_GEMINI_IDEA = False
REUSE_OPENAI_SCRIPT = False
REUSE_TTS = False
REUSE_TARGET_FOLDER = r"D:\AIGen\MasterFactory_V49\20260320_1056\Mastering Internal Triggers fo"

# API & Model Settings
MODEL_CONFIG = {
    "G_MODEL": "gemini-2.5-pro",
    "O_MODEL": "gpt-4o-mini",
    "VOICE": "en-GB-SoniaNeural",  # "en-AU-WilliamNeural",
    "VOICE_RATE": "-20%",  # 【新增】：全局语速控制。负数表示减慢，如 "-25%" 表示比默认慢25% 
    "VOICE_PITCH": "-10Hz"         # 【新增】：强行把音高再压低一点，制造深夜慵懒感
}

# YouTube Settings
YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secret.json'

# Script Generation Settings
SCRIPT_CONFIG = {
    "TARGET_WORDS": 600,
    "MIN_REQUIRED_WORDS": 450,
    "EMOTION_CURVE": [
        "Painful Truth, Tension, and Discomfort",
        "Confusion, Overwhelm, and Lost Direction",
        "Curiosity, Seeking, and Shifting Perspective",
        "Profound Realization and Epiphany",
        "Release, Action, and Letting Go",
        "Deep Calm, Integration, but Lingering Thought"
    ]
}

# Audio Mastering Settings
PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 5.0,
    "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -18.0,
    "COMP_RATIO": 3.0,
    "LIMIT_DB": -3.0
}

# Image Generation Settings
RUNNINGHUB_CONFIG = {
    "KEY": os.getenv("RUNNINGHUB_API_KEY"),
    "WF_T2I": "2014487614874718210",
    "T2I_NODE": "111"
}

# Path & Asset Settings
CONFIG = {
    "BASE_PATH": "D:/AIGen/MasterFactory_V49",
    "ASSETS_POOL": {
        "audios": ["D:/Assets/A/rain.mp3", "D:/Assets/A/wind.mp3"],
        "overlays": ["D:/Assets/V/ghibli_dust.mp4", "D:/Assets/V/light_rays.mp4"]
    }
}

# =====================================================================
# 2. THE DIRECTOR'S MATRIX (导演武器库)
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
# 3. PROMPT LIBRARY (结构化提示词中心)
# =====================================================================

PROMPT_CONFIG = {
    
    # --------------------------------------------------
    # 阶段 1 & 2：信息提取与逻辑重构 (The Brain)
    # --------------------------------------------------
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
    
    # --------------------------------------------------
    # 阶段 3：沉浸式文案生成 (The Voice)
    # --------------------------------------------------
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

    # --------------------------------------------------
    # 阶段 4：自动生成 YouTube 标题/描述/标签 (The SEO)
    # --------------------------------------------------
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

    # --------------------------------------------------
    # 视觉锚点与导演执行引擎 (The Eye)
    # --------------------------------------------------
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

# =====================================================================
# 4. DATA MODELS & UTILS (数据模型与工具库)
# =====================================================================

class ConceptItem(BaseModel):
    point: str = Field(..., description="The core concept point")
    details: str = Field(..., description="Logic and explanation")
    specific_example: str = Field(..., description="Anonymous specific example")

class ReduceResult(BaseModel):
    topic: str = Field(..., description="Overarching topic")
    concepts: list[ConceptItem] = Field(..., min_length=3)

def log_status(stage: str, msg: str, status: str = "INFO"):
    time_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{time_str}] [{stage:<10}] [{status:<5}] {msg}")

def extract_image_url(data: dict) -> str:
    target_keys = ['fileUrl', 'url', 'image_url', 'file_url']
    if isinstance(data, dict):
        for k, v in data.items():
            if k in target_keys and isinstance(v, str) and v.startswith('http'):
                return v
            res = extract_image_url(v)
            if res: return res
    elif isinstance(data, list):
        for item in data:
            res = extract_image_url(item)
            if res: return res
    return ""

def get_text_paragraphs(master_script: str) -> list:
    return [p.strip() for p in master_script.split('\n\n') if len(p.strip()) > 20]

def setup_environment() -> str:
    try:
        os.makedirs(CONFIG["BASE_PATH"], exist_ok=True)
        session_id = datetime.now().strftime('%Y%m%d_%H%M')
        session_dir = os.path.join(CONFIG["BASE_PATH"], session_id)
        os.makedirs(session_dir, exist_ok=True)
        log_status("ENV", f"Workspace created at {session_dir}", "OK")
        return session_dir
    except Exception as e:
        log_status("ENV", f"Failed to create workspace: {e}", "ERROR")
        return ""

def cleanup_temp_files(folder: str):
    if not AUTO_CLEANUP_TEMP: return
    try:
        seg_dir = os.path.join(folder, "segments")
        if os.path.exists(seg_dir): shutil.rmtree(seg_dir, ignore_errors=True)
        for f in ["concat_v.txt", "concat_a.txt", "master_video.mp4", "master_audio.wav", "bg.png"]:
            fp = os.path.join(folder, f)
            if os.path.exists(fp): os.remove(fp)
    except Exception as e:
        log_status("CLEANUP", f"Cleanup failed: {e}", "WARN")

# =====================================================================
# 5. CORE LOGIC CLASSES (核心业务逻辑类)
# =====================================================================

class MatrixDirector:
    def __init__(self):
        self.last_state = {"cast": None, "loc": None, "cam": None, "meta": None}

    def get_unique(self, pool: list, key: str) -> str:
        available = [x for x in pool if x != self.last_state[key]]
        if not available:
            available = pool 
        choice = random.choice(available)
        self.last_state[key] = choice
        return choice

    def get_visual_config(self, forced_type: str) -> dict:
        config = {
            "type": forced_type,
            "camera": self.get_unique(CAMERA_POOL, "cam"),
        }
        
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

# =====================================================================
# 6. EXTERNAL API WRAPPERS (外部接口封装)
# =====================================================================

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def robust_gemini_call(prompt: str) -> str:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    res = await asyncio.to_thread(client.models.generate_content, model=MODEL_CONFIG["G_MODEL"], contents=prompt)
    return res.text

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def robust_openai_call(prompt: str) -> str:
    o_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    res = await o_client.chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": prompt}])
    return res.choices[0].message.content

async def fetch_source_transcript(video_id: str) -> str:
    try:
        log_status("YOUTUBE", f"Fetching transcript for {video_id}...", "INFO")
        ts = YouTubeTranscriptApi.get_transcript(video_id)
        text = " ".join([x['text'] for x in ts])
        log_status("YOUTUBE", "Transcript fetched successfully.", "OK")
        return text
    except Exception as e:
        log_status("YOUTUBE", f"Transcript fetch failed: {e}", "ERROR")
        return ""

def clean_transcript_data(text: str) -> str:
    text = re.sub(r'\[.*?\]', '', text)
    return " ".join(text.split())

# =====================================================================
# 7. SCRIPT GENERATION PIPELINE (文案生产流水线)
# =====================================================================

async def analyze_and_plan(clean_text: str, session_dir: str) -> tuple:
    log_status("PLAN", "Mapping insights...", "INFO")
    chunks = [clean_text[i:i+6000] for i in range(0, len(clean_text), 6000)]
    map_results = []
    
    for idx, c in enumerate(chunks):
        try:
            res = await robust_gemini_call(PROMPT_CONFIG["STEP1_MAP"].format(chunk=c))
            map_results.append(res)
        except Exception as e:
            log_status("PLAN", f"Mapping failed on chunk {idx}: {e}", "ERROR")
            return "", [], "", "", ""
    
    log_status("PLAN", "Reducing to core principles...", "INFO")
    try:
        reduce_res = await robust_gemini_call(PROMPT_CONFIG["STEP2_REDUCE"].format(insights="\n".join(map_results)))
        json_match = re.search(r'\{.*\}', reduce_res, re.DOTALL)
        data = json.loads(json_match.group()) if json_match else json.loads(reduce_res)
    except Exception as e:
        log_status("PLAN", f"Reduce parsing failed: {e}", "ERROR")
        return "", [], "", "", ""
        
    try:
        with open(os.path.join(session_dir, "3_reduce_principles.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        visual_anchor = PROMPT_CONFIG["VISUAL_ANCHOR_GEN"]
        with open(os.path.join(session_dir, "0_visual_anchor.txt"), "w", encoding="utf-8") as f:
            f.write(visual_anchor)
        log_status("PLAN", "Blueprint saved successfully.", "OK")
        return data.get('topic', 'Unknown'), data.get('concepts', []), "", visual_anchor, session_dir
    except Exception as e:
        log_status("PLAN", f"Blueprint save failed: {e}", "ERROR")
        return "", [], "", "", ""

async def generate_script_only(topic: str, principles: list, folder: str) -> str:
    log_status("SCRIPT", "Drafting Master Script...", "INFO")
    try:
        hook = await robust_openai_call(PROMPT_CONFIG["STEP3_HOOK"].format(topic=topic, concepts=str(principles)))
        
        body_parts = []
        for idx, p in enumerate(principles):
            tone = SCRIPT_CONFIG["EMOTION_CURVE"][idx % len(SCRIPT_CONFIG["EMOTION_CURVE"])]
            part = await robust_openai_call(PROMPT_CONFIG["STEP3_SCRIPT_SINGLE"].format(
                topic=topic, point=p.get('point',''), details=p.get('details',''), example=p.get('specific_example',''), 
                emotion_tone=tone, target_words=SCRIPT_CONFIG["TARGET_WORDS"] // len(principles)))
            body_parts.append(part)
            
        outro = await robust_openai_call(PROMPT_CONFIG["STEP3_OUTRO"].format(topic=topic))
        
        full_script = f"{hook}\n\n" + "\n\n".join(body_parts) + f"\n\n{outro}"
        with open(os.path.join(folder, "master_script.txt"), "w", encoding="utf-8") as f:
            f.write(full_script)
        log_status("SCRIPT", "Master Script finalized.", "OK")
        return full_script
    except Exception as e:
        log_status("SCRIPT", f"Script generation failed: {e}", "ERROR")
        return ""

async def load_cached_plan(folder_path: str) -> tuple:
    try:
        log_status("CACHE", f"Loading plan from: {folder_path}", "INFO")
        with open(os.path.join(folder_path, "3_reduce_principles.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        topic, principles = data.get("topic", "Unknown"), data.get("concepts", [])
        with open(os.path.join(folder_path, "0_visual_anchor.txt"), "r", encoding="utf-8") as f: 
            visual_anchor = f.read().strip()
        return topic, principles, "", visual_anchor, folder_path
    except Exception as e: 
        log_status("CACHE", f"Plan load failed: {e}", "ERROR")
        return "", [], "", "", ""

async def load_cached_script(folder_path: str) -> str:
    try:
        log_status("CACHE", "Loading Master Script...", "INFO")
        with open(os.path.join(folder_path, "master_script.txt"), "r", encoding="utf-8") as f: 
            return f.read().strip()
    except Exception as e: 
        log_status("CACHE", f"Script load failed: {e}", "ERROR")
        return ""

# =====================================================================
# 8. MEDIA GENERATION PIPELINE (流媒体生产线)
# =====================================================================

async def process_single_segment(idx: int, para_text: str, visual_anchor: str, folder: str, movement: str, forced_type: str, v_config: dict) -> tuple:
    log_status("SEGMENT", f"--- Building Block {idx:02d} | [{forced_type}] ---", "INFO")
    
    seg_dir = os.path.join(folder, "segments")
    os.makedirs(seg_dir, exist_ok=True)
    
    raw_wav = os.path.join(seg_dir, f"s{idx:02d}_raw.mp3")
    mastered_wav = os.path.join(seg_dir, f"s{idx:02d}_mastered.wav")
    img_path = os.path.join(seg_dir, f"s{idx:02d}_img.png")
    clip_path = os.path.join(seg_dir, f"s{idx:02d}_clip.mp4")

    # ---------------- 1. AUDIO (Edge-TTS & Mastering) ----------------
    duration = 0.0
    if REUSE_TTS and os.path.exists(mastered_wav):
        try:
            duration = len(AudioSegment.from_file(mastered_wav)) / 1000.0
            log_status("AUDIO", f"Block {idx:02d} Reusing cached audio.", "OK")
        except Exception as e:
            log_status("AUDIO", f"Block {idx:02d} Cache read failed: {e}", "ERROR")
    else:
        try:
            log_status("AUDIO", f"Block {idx:02d} Synthesizing TTS...", "INFO")
            await edge_tts.Communicate(para_text, MODEL_CONFIG["VOICE"], rate=MODEL_CONFIG["VOICE_RATE"], pitch=MODEL_CONFIG["VOICE_PITCH"]).save(raw_wav)
            with AudioFile(raw_wav) as f: 
                audio_data, samplerate = f.read(f.frames), f.samplerate
            
            board = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=150, gain_db=PEDALBOARD_CONFIG["LOW_SHELF_GAIN"]),
                HighShelfFilter(cutoff_frequency_hz=6000, gain_db=PEDALBOARD_CONFIG["HIGH_SHELF_GAIN"]),
                Compressor(threshold_db=PEDALBOARD_CONFIG["COMP_THRESHOLD"], ratio=PEDALBOARD_CONFIG["COMP_RATIO"]),
                Gain(gain_db=2.0), 
                Limiter(threshold_db=PEDALBOARD_CONFIG["LIMIT_DB"])
            ])
            
            processed_data = board(audio_data, samplerate)
            with AudioFile(mastered_wav, 'w', samplerate, processed_data.shape[0]) as f: 
                f.write(processed_data)
                
            duration = len(AudioSegment.from_file(mastered_wav)) / 1000.0
            log_status("AUDIO", f"Block {idx:02d} Audio mastering complete.", "OK")
        except Exception as e: 
            log_status("AUDIO", f"Block {idx:02d} Processing failed: {e}", "ERROR")
            return "", ""

    # ---------------- 2. IMAGE (Code-Driven Prompt Routing) ----------------
    if not os.path.exists(img_path):
        try:
            log_status("IMAGE", f"Block {idx:02d} Routing prompt via Matrix ({forced_type})...", "INFO")
            
            if forced_type == "HUMAN":
                template = PROMPT_CONFIG["SCENE_PROMPT_HUMAN"]
                full_prompt = template.format(
                    forced_visual_type=forced_type, location=v_config["location"], 
                    camera=v_config["camera"], subject=v_config["subject"], text=para_text, anchor=visual_anchor
                )
            elif forced_type == "ENVIRONMENT":
                template = PROMPT_CONFIG["SCENE_PROMPT_ENVIRONMENT"]
                full_prompt = template.format(
                    forced_visual_type=forced_type, location=v_config["location"], 
                    camera=v_config["camera"], text=para_text, anchor=visual_anchor
                )
            elif forced_type == "SYMBOLIC":
                template = PROMPT_CONFIG["SCENE_PROMPT_SYMBOLIC"]
                full_prompt = template.format(
                    forced_visual_type=forced_type, subject=v_config["subject"], 
                    camera=v_config["camera"], text=para_text, anchor=visual_anchor
                )
            
            img_prompt = await robust_gemini_call(full_prompt)
            img_prompt = img_prompt.replace("\n", "").strip()
            
            with open(os.path.join(folder, "visual_prompts_log.txt"), "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [Block {idx:02d} | Routing: {forced_type}]\n{img_prompt}\n\n")
        except Exception as e: 
            log_status("IMAGE", f"Block {idx:02d} Prompt generation failed: {e}", "ERROR")
            return "", mastered_wav

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RUNNINGHUB_CONFIG['KEY']}"}
        task_id = None
        
        log_status("IMAGE", f"Block {idx:02d} Requesting T2I...", "INFO")
        for _ in range(60): 
            try:
                payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": img_prompt}]}
                resp = requests.post(f"https://www.runninghub.ai/openapi/v2/run/workflow/{RUNNINGHUB_CONFIG['WF_T2I']}", headers=headers, json=payload, timeout=60)
                r_json = resp.json()
                if str(r_json.get("errorCode")) == "421": 
                    await asyncio.sleep(10)
                    continue
                task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
                if task_id: break
            except Exception as e: 
                log_status("IMAGE", f"Block {idx:02d} API request error: {e}", "WARN")
                await asyncio.sleep(5)
                
        img_url = ""
        if task_id:
            t0 = time.time()
            while time.time() - t0 < 600:
                try:
                    q_resp = requests.post("https://www.runninghub.ai/openapi/v2/query", headers=headers, json={"taskId": task_id}, timeout=60).json()
                    status = (q_resp.get("status") or q_resp.get("data", {}).get("status", "")).upper()
                    if status == "SUCCESS": 
                        img_url = extract_image_url(q_resp)
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
                    with open(img_path, "wb") as f: shutil.copyfileobj(r.raw, f)
                log_status("IMAGE", f"Block {idx:02d} Image downloaded.", "OK")
            except Exception as e: 
                log_status("IMAGE", f"Block {idx:02d} Download failed: {e}", "ERROR")
                return "", mastered_wav
        else:
            log_status("IMAGE", f"Block {idx:02d} Timeout waiting for URL.", "ERROR")

    # ---------------- 3. FFMPEG (NVENC + GBRP Fix) ----------------
    if not os.path.exists(img_path): 
        return "", mastered_wav
        
    log_status("FFMPEG", f"Block {idx:02d} Rendering video segment...", "INFO")
    overlays = CONFIG["ASSETS_POOL"].get("overlays", [])
    selected_overlay = random.choice(overlays) if overlays else None
    fps = 25
    frames = int(duration * fps)
    
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

    if selected_overlay and os.path.exists(selected_overlay):
        cmd = [
            'ffmpeg', '-y', 
            '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path, 
            '-stream_loop', '-1', '-t', str(duration), '-i', selected_overlay,
            '-filter_complex', f"[0:v]format=yuv420p,{zp},format=gbrp[bg];[1:v]format=yuv420p,scale=1920x1080,format=gbrp[ovl];[bg][ovl]blend=all_mode='screen':all_opacity=0.6,format=yuv420p[v]",
            '-map', '[v]', '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p', clip_path
        ]
    else:
        cmd = [
            'ffmpeg', '-y', 
            '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path, 
            '-vf', f"format=yuv420p,{zp}", 
            '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p', clip_path
        ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        log_status("FFMPEG", f"Block {idx:02d} Video segment encoded.", "OK")
    except Exception as e: 
        log_status("FFMPEG", f"Block {idx:02d} Encoding failed: {e}", "ERROR")
        
    await asyncio.sleep(1) 
    return clip_path, mastered_wav

# =====================================================================
# 9. ASSEMBLY (终端拼接)
# =====================================================================

def assemble_final_masterpiece(valid_clips: list, valid_audios: list, folder: str):
    log_status("STUDIO", f"Assembling {len(valid_clips)} blocks into final cut...", "INFO")
    
    v_concat = os.path.join(folder, "concat_v.txt")
    a_concat = os.path.join(folder, "concat_a.txt")
    
    try:
        with open(v_concat, "w") as f:
            for p in valid_clips: f.write(f"file '{os.path.abspath(p)}'\n")
        with open(a_concat, "w") as f:
            for p in valid_audios: f.write(f"file '{os.path.abspath(p)}'\n")
            
        video_track = os.path.join(folder, "master_video.mp4")
        audio_track = os.path.join(folder, "master_audio.wav")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', video_track], capture_output=True, check=True)
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', audio_track], capture_output=True, check=True)

        final_output = os.path.join(folder, "FINAL_MASTERPIECE.mp4")
        audios_list = CONFIG["ASSETS_POOL"].get("audios", [])
        bgm = random.choice(audios_list) if audios_list else None
        
        log_status("STUDIO", "Muxing final track with NVIDIA GPU...", "INFO")
        
        if bgm and os.path.exists(bgm):
            cmd_mux = [
                'ffmpeg', '-y', '-i', video_track, '-i', audio_track, '-stream_loop', '-1', '-i', bgm,      
                '-filter_complex', "[1:a]volume=1.0[va]; [2:a]volume=0.25[ba]; [va][ba]amix=inputs=2:duration=first[a]", 
                '-map', '0:v', '-map', '[a]', '-c:v', 'h264_nvenc', '-preset', 'p4', '-c:a', 'aac', '-shortest', final_output
            ]
        else:
            cmd_mux = [
                'ffmpeg', '-y', '-i', video_track, '-i', audio_track, 
                '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_output
            ]
            
        subprocess.run(cmd_mux, capture_output=True, check=True)
        log_status("SYSTEM", f"=== PIPELINE COMPLETE! FILE: {final_output} ===", "SUCCESS")
        
    except Exception as e:
        log_status("STUDIO", f"Final assembly failed: {e}", "ERROR")

# =====================================================================
# 10. YOUTUBE METADATA & UPLOAD MODULE (YouTube 自动编排与上传模块)
# =====================================================================

async def generate_youtube_metadata(topic: str, folder: str) -> dict:
    """使用大模型自动生成适用于 YouTube 的高转化率标题、描述和 SEO 标签"""
    log_status("SEO", "Generating YouTube Metadata...", "INFO")
    try:
        prompt = PROMPT_CONFIG["STEP4_METADATA"].format(topic=topic)
        res = await robust_openai_call(prompt)
        
        json_match = re.search(r'\{.*\}', res, re.DOTALL)
        data = json.loads(json_match.group()) if json_match else json.loads(res)
        
        meta_path = os.path.join(folder, "youtube_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            
        log_status("SEO", f"Metadata saved to: {meta_path}", "OK")
        return data
    except Exception as e:
        log_status("SEO", f"Metadata generation failed: {e}", "ERROR")
        return {}

def get_authenticated_service():
    """获取 YouTube API 的认证服务凭证"""
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

def upload_video_to_youtube(file_path: str, title: str, description: str, tags: list):
    """执行 YouTube 视频的自动上传操作"""
    log_status("UPLOAD", f"Starting upload for: {title}", "INFO")
    try:
        youtube = get_authenticated_service()
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': '27' # 27 = Education
            },
            'status': {
                'privacyStatus': 'private', # 为了安全，默认上传为私享，需人工确认发布
                'selfDeclaredMadeForKids': False
            }
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
# 11. PIPELINE ORCHESTRATOR (主函数)
# =====================================================================

async def execute_video_pipeline():
    log_status("SYSTEM", "--- V90 ULTIMATE EDITION (WITH UPLOAD) STARTING ---", "START")
    director = MatrixDirector()
    
    if REUSE_GEMINI_IDEA or REUSE_OPENAI_SCRIPT:
        if not os.path.exists(REUSE_TARGET_FOLDER):
            log_status("SYSTEM", "REUSE_TARGET_FOLDER does not exist!", "ERROR")
            return
        topic, principles, _, visual_anchor, folder = await load_cached_plan(REUSE_TARGET_FOLDER)
        if not principles: return
    else:
        folder = setup_environment()
        if not folder: return
        raw_ts = await fetch_source_transcript(MANUAL_VIDEO_ID)
        if not raw_ts: return
        clean_text = clean_transcript_data(raw_ts)
        topic, principles, _, visual_anchor, folder = await analyze_and_plan(clean_text, folder)
        if not principles: return
        
    if REUSE_OPENAI_SCRIPT:
        master_script = await load_cached_script(folder)
    else:
        master_script = await generate_script_only(topic, principles, folder)
        
    if not master_script or ONLY_GENERATE_SCRIPT: 
        log_status("SYSTEM", "Script generation complete. Exiting Early.", "INFO")
        return
        
    paragraphs = get_text_paragraphs(master_script)
    total_blocks = len(paragraphs)
    log_status("PIPELINE", f"Ready to process {total_blocks} execution blocks.", "INFO")
    
    valid_clips, valid_audios = [], []
    prev_mv = None
    mv_pool = ["zoom_in", "zoom_out", "pan_right", "pan_left"]
    
    for idx, para in enumerate(paragraphs):
        forced_type = get_visual_type(idx, total_blocks)
        v_config = director.get_visual_config(forced_type)
        
        movement = random.choice([m for m in mv_pool if m != prev_mv])
        prev_mv = movement
        
        v_path, a_path = await process_single_segment(
            idx + 1, para, visual_anchor, folder, movement, forced_type, v_config
        )
        
        if v_path and a_path:
            valid_clips.append(v_path)
            valid_audios.append(a_path)
            
    if valid_clips:
        assemble_final_masterpiece(valid_clips, valid_audios, folder)
        
        # ---------------- Step 4: YouTube SEO & Upload ----------------
        if IS_AUTO_UPLOAD:
            metadata = await generate_youtube_metadata(topic, folder)
            final_output = os.path.join(folder, "FINAL_MASTERPIECE.mp4")
            
            if metadata and os.path.exists(final_output):
                upload_video_to_youtube(
                    final_output, 
                    metadata.get("title", topic), 
                    metadata.get("description", ""), 
                    metadata.get("tags", [])
                )
                
        # cleanup_temp_files(folder) # 如果需要，可取消注释清理临时文件
    else:
        log_status("SYSTEM", "No valid media to assemble.", "ERROR")

async def main():
    try:
        await execute_video_pipeline()
    except Exception as e:
        log_status("SYSTEM", f"Critical Pipeline Failure: {e}", "CRITICAL")

if __name__ == "__main__":
    if sys.platform == 'win32': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())