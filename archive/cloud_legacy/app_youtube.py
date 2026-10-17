# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements
"""
YouTube Masterclass Channel - Specific Application Script
Features: YouTube API Transcript Fetch, Auto-Upload, Matrix Director, Concurrent Rendering, GBRP Overlay Fix.
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

# YouTube & Google OAuth Tools
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Audio Processing Tools
import edge_tts
from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
from pedalboard.io import AudioFile
from tenacity import retry, stop_after_attempt, wait_exponential

# 导入底层的复用模块
from core_engine import (
    validate_environment, setup_workspace, log_status, log_retry_attempt,
    ConcurrencyManager, APIClients, robust_gemini_call
)

# =====================================================================
# 1. BUSINESS CONFIGURATION (YouTube 专属配置)
# =====================================================================

IS_AUTO_SEARCH = False
MANUAL_VIDEO_ID = "rOYlOdDgYUU"

ONLY_GENERATE_SCRIPT = False
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
    "VOICE": "en-GB-SoniaNeural",
    "VOICE_RATE": "-20%",  
    "VOICE_PITCH": "-10Hz" 
}

# YouTube OAuth Settings
YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secret.json'

SCRIPT_CONFIG = {
    "TARGET_WORDS": 600,
    "EMOTION_CURVE": [
        "Painful Truth, Tension, and Discomfort",
        "Confusion, Overwhelm, and Lost Direction",
        "Curiosity, Seeking, and Shifting Perspective",
        "Profound Realization and Epiphany",
        "Release, Action, and Letting Go",
        "Deep Calm, Integration, but Lingering Thought"
    ]
}

RUNNINGHUB_CONFIG = {
    "KEY": os.getenv("RUNNINGHUB_API_KEY"),
    "WF_T2I": "2014487614874718210",
    "T2I_NODE": "111"
}

PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 5.0, "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -25.0, "COMP_RATIO": 3.0, "LIMIT_DB": -3.0
}

CONFIG = {
    "BASE_PATH": "D:/AIGen/MasterFactory_YouTube",
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
    "a contemplative older woman with elegant silver hair"
]

LOCATION_POOL = [
    "a quiet, rain-streaked empty train carriage",
    "a sun-drenched, dusty old kitchen corner",
    "a long, silent corporate hallway with leading lines",
    "an empty, dimly lit laundromat at 3 AM",
    "a peaceful balcony overlooking distant city lights"
]

CAMERA_POOL = [
    "Cinematic Wide Shot, capturing the scale of the environment",
    "Low-angle shot from the floor, looking up with a sense of weight",
    "Extreme Close-up, focusing on fine textures and micro-expressions",
    "Over-the-shoulder shot, creating a sense of intimacy",
    "Profile shot, capturing a thoughtful silhouette against the light"
]

METAPHOR_POOL = [
    "intricate shadows cast by a window lattice",
    "a single, heavy water droplet about to fall from a tap",
    "distorted reflections in a rain puddle on the ground",
    "a vintage mechanical clock's exposed, slow-moving gears",
    "dust motes dancing in a single, sharp beam of light"
]

# =====================================================================
# 3. PROMPT LIBRARY (结构化提示词)
# =====================================================================

PROMPT_CONFIG = {
    "STEP1_MAP": """
    TASK: Extract core knowledge from the provided segment.
    --- RULES ---
    1. Extract ONLY concrete, specific insights, frameworks, and hard knowledge.
    2. Each insight MUST be a distinct, non-overlapping idea.
    3. Ignore fluff, filler words, and redundant examples.
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
    - Write a gripping OPENING HOOK to draw the listener in. (~150 words)
    - Tone: Calm, slow, intimate, and deeply resonant.
    - PROHIBITIONS: NO 'you' or 'your'. NO ellipses (...). NO markdown formatting.
    """,
    
    "STEP3_SCRIPT_SINGLE": """
    PERSONA: You are recording ONE segment of a slow-paced audio masterclass.
    --- SEGMENT CONTEXT ---
    - Topic: {topic}
    - Core Concept: {point}
    - Logic/Details: {details}
    --- TASK & GUIDELINES ---
    - Write a deep, hypnotic spoken monologue exploring this specific concept.
    - TONE: Match the emotion exactly -> [{emotion_tone}].
    - PACING: Use periods and commas strategically to force breathing pauses.
    - Target Length: ~{target_words} words.
    - PROHIBITIONS: NO 'you' or 'your'. NO ellipses (...). NO markdown.
    """,
    
    "STEP3_OUTRO": """
    PERSONA: You are concluding a deeply hypnotic, slow-paced audio masterclass.
    --- CONTEXT ---
    - Topic: {topic}
    --- TASK & GUIDELINES ---
    - Write a grounding OUTRO and a gentle Call-To-Action (CTA). (~150 words)
    - PROHIBITIONS: NO 'you' or 'your'. NO ellipses (...). NO markdown.
    """,

    "STEP4_METADATA": """
    TASK: Generate YouTube metadata for a highly engaging, atmospheric audio masterclass.
    --- CONTEXT ---
    Topic of the Masterclass: {topic}
    --- OUTPUT REQUIREMENTS ---
    1. title: A captivating, high-CTR title (max 65 chars).
    2. description: A compelling 2-paragraph description.
    3. tags: An array of 10-15 highly relevant SEO tags.
    4. You MUST return the result strictly in valid JSON format.
    """,

    "VISUAL_ANCHOR_GEN": "Studio Ghibli animation style, beautiful vibrant colors, highly detailed, serene everyday life, cinematic anime still.",
    
    "SCENE_PROMPT_HUMAN": """
    PERSONA: Cinematic visual executor.
    --- FIXED VISUAL FRAMEWORK ---
    - SCENE TYPE: {forced_visual_type}
    - LOCATION: {location}
    - CAMERA: {camera}
    - CHARACTER: {subject}
    --- SCRIPT SEGMENT ---
    {text}
    --- EXECUTION RULES ---
    1. Focus entirely on the CHARACTER within the LOCATION. 
    2. Output ONLY the final English image prompt string. Append exactly [{anchor}]. DO NOT use markdown.
    """,

    "SCENE_PROMPT_ENVIRONMENT": """
    PERSONA: Cinematic visual executor.
    --- FIXED VISUAL FRAMEWORK ---
    - SCENE TYPE: {forced_visual_type}
    - LOCATION: {location}
    - CAMERA: {camera}
    --- SCRIPT SEGMENT ---
    {text}
    --- EXECUTION RULES ---
    1. ABSOLUTELY NO HUMANS ALLOWED. The subject is the LOCATION ITSELF.
    2. Output ONLY the final English image prompt string. Append exactly [{anchor}]. DO NOT use markdown.
    """,

    "SCENE_PROMPT_SYMBOLIC": """
    PERSONA: Cinematic visual executor.
    --- FIXED VISUAL FRAMEWORK ---
    - SCENE TYPE: {forced_visual_type}
    - FOCAL METAPHOR: {subject}
    - CAMERA: {camera}
    --- SCRIPT SEGMENT ---
    {text}
    --- EXECUTION RULES ---
    1. ABSOLUTELY NO HUMANS ALLOWED. Background must be beautifully blurred macro setting to isolate the metaphor.
    2. Output ONLY the final English image prompt string. Append exactly [{anchor}]. DO NOT use markdown.
    """
}

# =====================================================================
# 4. YOUTUBE API & LOCAL LLM WRAPPERS
# =====================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
async def local_openai_text_call(prompt: str) -> str:
    """A local wrapper for OpenAI that returns raw text (bypassing Structured Outputs)"""
    client = APIClients.get_openai()
    res = await client.chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": prompt}])
    return res.choices[0].message.content

async def fetch_source_transcript(video_id: str) -> str:
    try:
        log_status("YOUTUBE", f"Fetching transcript for {video_id}...", "INFO")
        ts = YouTubeTranscriptApi.get_transcript(video_id)
        text = " ".join([x['text'] for x in ts])
        log_status("YOUTUBE", "Transcript fetched successfully.", "OK")
        return re.sub(r'\[.*?\]', '', text)
    except Exception as e:
        log_status("YOUTUBE", f"Transcript fetch failed: {e}", "ERROR")
        return ""

def get_authenticated_service():
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
    log_status("UPLOAD", f"Starting upload for: {title[:20]}...", "INFO")
    try:
        youtube = get_authenticated_service()
        body = {
            'snippet': {'title': title, 'description': description, 'tags': tags, 'categoryId': '27'},
            'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False}
        }
        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status: log_status("UPLOAD", f"Progress: {int(status.progress() * 100)}%", "INFO")
        log_status("UPLOAD", f"Complete! Video ID: {response.get('id')}", "SUCCESS")
    except Exception as e:
        log_status("UPLOAD", f"Upload failed: {e}", "ERROR")

# =====================================================================
# 5. BUSINESS LOGIC (剧本生成与导演逻辑)
# =====================================================================

class MatrixDirector:
    def __init__(self):
        self.last_state = {"cast": None, "loc": None, "cam": None, "meta": None}

    def get_unique(self, pool: list, key: str) -> str:
        available = [x for x in pool if x != self.last_state[key]]
        if not available: available = pool 
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
    if idx == 0: return "ENVIRONMENT"
    if idx == total - 1: return "SYMBOLIC"
    if idx % 3 == 1: return "HUMAN"
    return random.choice(["ENVIRONMENT", "SYMBOLIC"])

async def analyze_and_plan(clean_text: str, session_dir: str) -> tuple:
    log_status("PLAN", "Mapping insights...", "INFO")
    chunks = [clean_text[i:i+6000] for i in range(0, len(clean_text), 6000)]
    map_results = []
    for c in chunks:
        try: map_results.append(await robust_gemini_call(PROMPT_CONFIG["STEP1_MAP"].format(chunk=c)))
        except: return "", [], "", ""
    
    log_status("PLAN", "Reducing to core principles...", "INFO")
    try:
        reduce_res = await robust_gemini_call(PROMPT_CONFIG["STEP2_REDUCE"].format(insights="\n".join(map_results)))
        json_match = re.search(r'\{.*\}', reduce_res, re.DOTALL)
        data = json.loads(json_match.group()) if json_match else json.loads(reduce_res)
        with open(os.path.join(session_dir, "3_reduce_principles.json"), "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
        
        visual_anchor = PROMPT_CONFIG["VISUAL_ANCHOR_GEN"]
        with open(os.path.join(session_dir, "0_visual_anchor.txt"), "w") as f: f.write(visual_anchor)
        log_status("PLAN", "Blueprint saved successfully.", "OK")
        return data.get('topic', 'Unknown'), data.get('concepts', []), visual_anchor, session_dir
    except Exception as e:
        log_status("PLAN", f"Blueprint save failed: {e}", "ERROR")
        return "", [], "", ""

async def generate_script_only(topic: str, principles: list, folder: str) -> str:
    log_status("SCRIPT", "Drafting Master Script...", "INFO")
    try:
        hook = await local_openai_text_call(PROMPT_CONFIG["STEP3_HOOK"].format(topic=topic, concepts=str(principles)))
        body_parts = []
        for idx, p in enumerate(principles):
            tone = SCRIPT_CONFIG["EMOTION_CURVE"][idx % len(SCRIPT_CONFIG["EMOTION_CURVE"])]
            part = await local_openai_text_call(PROMPT_CONFIG["STEP3_SCRIPT_SINGLE"].format(
                topic=topic, point=p.get('point',''), details=p.get('details',''), 
                emotion_tone=tone, target_words=SCRIPT_CONFIG["TARGET_WORDS"] // len(principles)
            ))
            body_parts.append(part)
        outro = await local_openai_text_call(PROMPT_CONFIG["STEP3_OUTRO"].format(topic=topic))
        
        full_script = f"{hook}\n\n" + "\n\n".join(body_parts) + f"\n\n{outro}"
        with open(os.path.join(folder, "master_script.txt"), "w", encoding="utf-8") as f: f.write(full_script)
        log_status("SCRIPT", "Master Script finalized.", "OK")
        return full_script
    except Exception as e:
        log_status("SCRIPT", f"Script generation failed: {e}", "ERROR")
        return ""

# =====================================================================
# 6. YOUTUBE MEDIA PIPELINE (专属的并行视频渲染管道)
# =====================================================================

class YouTubeMediaPipeline:
    def __init__(self, folder: str):
        self.folder = folder

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
        except: return 0.0

    async def _generate_image(self, prompt: str, img_path: str) -> bool:
        if os.path.exists(img_path): return True
        client = APIClients.get_http()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RUNNINGHUB_CONFIG['KEY']}"}
        payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": prompt}]}
        task_id = None
        for _ in range(30):
            try:
                resp = await client.post(f"https://www.runninghub.ai/openapi/v2/run/workflow/{RUNNINGHUB_CONFIG['WF_T2I']}", headers=headers, json=payload)
                if resp.json().get("errorCode") == "421": await asyncio.sleep(5); continue
                task_id = resp.json().get("taskId")
                if task_id: break
            except: await asyncio.sleep(5)
        if not task_id: return False

        t0 = time.time()
        while time.time() - t0 < RUNNINGHUB_TIMEOUT_SEC:
            try:
                q_json = (await client.post("https://www.runninghub.ai/openapi/v2/query", headers=headers, json={"taskId": task_id})).json()
                status = q_json.get("status", "").upper()
                if status == "SUCCESS":
                    img_url = ""
                    def find_url(d):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if k in ['fileUrl', 'url'] and isinstance(v, str) and v.startswith('http'): return v
                                if (res := find_url(v)): return res
                        elif isinstance(d, list):
                            for i in d:
                                if (res := find_url(i)): return res
                        return ""
                    if (img_url := find_url(q_json)):
                        with open(img_path, "wb") as f: f.write((await client.get(img_url)).content)
                        return True
                    break
                elif status == "FAILED": break
            except: pass
            await asyncio.sleep(API_POLL_INTERVAL_SEC)
        return False

    def _encode_video_with_overlay(self, img_path: str, duration: float, clip_path: str, movement: str):
        if os.path.exists(clip_path): return True
        overlays = CONFIG["ASSETS_POOL"].get("overlays", [])
        selected_overlay = random.choice(overlays) if overlays else None
        fps, frames = 25, int(duration * 25)
        
        base = "crop=1920:1080,scale=3840:2160"
        end = "scale=1920:1080"
        
        if movement == "zoom_in": 
            zp = f"{base},zoompan=z='1.001+0.15*(on/{frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=3840x2160:fps={fps},{end}"
        elif movement == "zoom_out": 
            zp = f"{base},zoompan=z='1.15-0.15*(on/{frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=3840x2160:fps={fps},{end}"
        elif movement == "pan_right": 
            zp = f"{base},zoompan=z='1.1+0.0001*on':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s=3840x2160:fps={fps},{end}"
        else: 
            zp = f"{base},zoompan=z='1.1+0.0001*on':x='(iw-iw/zoom)*(1 - on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s=3840x2160:fps={fps},{end}"

        if selected_overlay and os.path.exists(selected_overlay):
            cmd = [
                'ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path, 
                '-stream_loop', '-1', '-t', str(duration), '-i', selected_overlay,
                '-filter_complex', f"[0:v]format=yuv420p,{zp},format=gbrp[bg];[1:v]format=yuv420p,scale=1920x1080,format=gbrp[ovl];[bg][ovl]blend=all_mode='screen':all_opacity=0.6,format=yuv420p[v]",
                '-map', '[v]', '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p', clip_path
            ]
        else:
            cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path, 
                   '-vf', f"format=yuv420p,{zp}", '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p', clip_path]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return True
        except: return False

    async def process_segment_concurrent(self, config: dict):
        idx, para_text = config["idx"], config["para"]
        forced_type, v_config = config["forced_type"], config["v_config"]
        movement, visual_anchor = config["movement"], config["visual_anchor"]
        
        seg_dir = os.path.join(self.folder, "segments")
        os.makedirs(seg_dir, exist_ok=True)
        
        raw_wav = os.path.join(seg_dir, f"s{idx:02d}_raw.mp3")
        mastered_wav = os.path.join(seg_dir, f"s{idx:02d}_mastered.wav")
        img_path = os.path.join(seg_dir, f"s{idx:02d}_img.png")
        clip_path = os.path.join(seg_dir, f"s{idx:02d}_clip.mp4")

        # 1. TTS & Mastering
        if not (REUSE_TTS and os.path.exists(mastered_wav)):
            async with ConcurrencyManager.TTS_SEM:
                await edge_tts.Communicate(para_text, MODEL_CONFIG["VOICE"], rate=MODEL_CONFIG["VOICE_RATE"], pitch=MODEL_CONFIG["VOICE_PITCH"]).save(raw_wav)
            duration = await asyncio.to_thread(self._master_audio_sync, raw_wav, mastered_wav)
        else:
            duration = len(AudioSegment.from_file(mastered_wav)) / 1000.0
        
        if duration <= 0: return None

        # 2. Image Prompting & Gen
        async with ConcurrencyManager.IMG_SEM:
            if not os.path.exists(img_path):
                if forced_type == "HUMAN": tmpl = PROMPT_CONFIG["SCENE_PROMPT_HUMAN"]
                elif forced_type == "ENVIRONMENT": tmpl = PROMPT_CONFIG["SCENE_PROMPT_ENVIRONMENT"]
                else: tmpl = PROMPT_CONFIG["SCENE_PROMPT_SYMBOLIC"]
                
                full_prompt = tmpl.format(forced_visual_type=forced_type, location=v_config.get("location",""), camera=v_config["camera"], subject=v_config.get("subject",""), text=para_text, anchor=visual_anchor)
                img_prompt = await robust_gemini_call(full_prompt)
                
                if not await self._generate_image(img_prompt.replace("\n", "").strip(), img_path): return None

        # 3. NVENC Overlays
        async with ConcurrencyManager.NVENC_SEM:
            if not await asyncio.to_thread(self._encode_video_with_overlay, img_path, duration, clip_path, movement): return None

        log_status("PIPELINE", f"Block {idx:02d} Fully Rendered.", "OK")
        return {"v": clip_path, "a": mastered_wav}

# =====================================================================
# 7. MAIN ORCHESTRATOR
# =====================================================================

async def main():
    log_status("SYSTEM", "--- V90 YT APP (WITH CONCURRENT FIX & ENGINE IMPORT) STARTING ---", "START")
    ConcurrencyManager.init_locks()
    
    folder = setup_workspace(os.path.join(CONFIG["BASE_PATH"], datetime.now().strftime('%Y%m%d_%H%M')))
    
    raw_ts = await fetch_source_transcript(MANUAL_VIDEO_ID)
    if not raw_ts: return
    topic, principles, visual_anchor, _ = await analyze_and_plan(raw_ts, folder)
    if not principles: return
    
    master_script = await generate_script_only(topic, principles, folder)
    if not master_script or ONLY_GENERATE_SCRIPT: return
    
    paragraphs = [p.strip() for p in master_script.split('\n\n') if len(p.strip()) > 20]
    
    # 剧本前置预演算 (Pre-calculate Director Matrix to enable Concurrency)
    director = MatrixDirector()
    configs, prev_mv = [], None
    mv_pool = ["zoom_in", "zoom_out", "pan_right", "pan_left"]
    
    for idx, para in enumerate(paragraphs):
        f_type = get_visual_type(idx, len(paragraphs))
        movement = random.choice([m for m in mv_pool if m != prev_mv])
        prev_mv = movement
        configs.append({
            "idx": idx + 1, "para": para, "forced_type": f_type, 
            "v_config": director.get_visual_config(f_type),
            "movement": movement, "visual_anchor": visual_anchor
        })

    # 并发渲染所有片段 (Concurrent Rendering)
    log_status("PIPELINE", f"Dispatching {len(configs)} blocks to concurrent pool...", "INFO")
    media_pipe = YouTubeMediaPipeline(folder)
    tasks = [media_pipe.process_segment_concurrent(c) for c in configs]
    results = await asyncio.gather(*tasks)
    
    valid_clips = [r["v"] for r in results if r]
    valid_audios = [r["a"] for r in results if r]
    
    if not valid_clips: 
        log_status("SYSTEM", "No valid media rendered.", "ERROR")
        return

    # 最终合并与 BGM 混音
    v_concat, a_concat = os.path.join(folder, "concat_v.txt"), os.path.join(folder, "concat_a.txt")
    with open(v_concat, "w") as f: 
        for p in valid_clips: f.write(f"file '{os.path.abspath(p)}'\n")
    with open(a_concat, "w") as f: 
        for p in valid_audios: f.write(f"file '{os.path.abspath(p)}'\n")
        
    v_track, a_track = os.path.join(folder, "master_v.mp4"), os.path.join(folder, "master_a.wav")
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', v_track], capture_output=True)
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', a_track], capture_output=True)

    final_output = os.path.join(folder, "FINAL_MASTERPIECE.mp4")
    audios_list = CONFIG["ASSETS_POOL"].get("audios", [])
    bgm = random.choice(audios_list) if audios_list else None
    
    log_status("STUDIO", "Muxing final track with NVIDIA GPU...", "INFO")
    if bgm and os.path.exists(bgm):
        cmd_mux = ['ffmpeg', '-y', '-i', v_track, '-i', a_track, '-stream_loop', '-1', '-i', bgm, 
                   '-filter_complex', "[1:a]volume=1.0[va]; [2:a]volume=0.25[ba]; [va][ba]amix=inputs=2:duration=first[a]", 
                   '-map', '0:v', '-map', '[a]', '-c:v', 'h264_nvenc', '-preset', 'p4', '-c:a', 'aac', '-shortest', final_output]
    else:
        cmd_mux = ['ffmpeg', '-y', '-i', v_track, '-i', a_track, '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_output]
    subprocess.run(cmd_mux, capture_output=True)
    
    log_status("SYSTEM", f"=== COMPLETE! FILE: {final_output} ===", "SUCCESS")

    # YouTube SEO & Upload
    if IS_AUTO_UPLOAD:
        metadata = await local_openai_text_call(PROMPT_CONFIG["STEP4_METADATA"].format(topic=topic))
        m_json = safe_json_loads(metadata)
        if m_json:
            with open(os.path.join(folder, "youtube_metadata.json"), "w", encoding="utf-8") as f: json.dump(m_json, f, indent=4)
            upload_video_to_youtube(final_output, m_json.get("title", topic), m_json.get("description", ""), m_json.get("tags", []))

    await APIClients.close_all()

if __name__ == "__main__":
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())