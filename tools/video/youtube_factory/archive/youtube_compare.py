# -*- coding: utf-8 -*-
"""
AI Audio Masterclass Factory V18 - The High-Density Deduplicated Edition
Features: Concept Deduplication, Anti-Fluff Constraints, High Information Density, Pylint Compliant.
"""

import os
import sys
import asyncio
import re
import random
import json
import subprocess
import pickle
from datetime import datetime

# 核心依赖库
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from google import genai
from openai import AsyncOpenAI
import edge_tts
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. 核心控制台 (Global Configuration)
# ==========================================
IS_AUTO_SEARCH = False
MANUAL_VIDEO_ID = "rDdoUbCFn24"

ONLY_GENERATE_SCRIPT = True      # 测试期：只生成文案审查信息密度
IS_AUTO_UPLOAD = False

MODEL_CONFIG = {
    "G_MODEL": "gemini-2.0-pro-exp-02-05",
    "O_MODEL": "gpt-4o-mini",
    "VOICE": "en-AU-WilliamNeural"
}

# ==========================================
# 2. 极致去重高密提示词库 (High-Density Prompts)
# ==========================================
PROMPT_CONFIG = {
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
        {text}"""
}

CONFIG = {
    "BASE_PATH": "D:/AIGen/MasterFactory_V18",
    "TARGET_CHANNELS": ["UCGq-a57w-aPwyi3pW7XLiHw", "UC2D2CMWXMOVWx7giW1n3LIg"],
    "ASSETS_POOL": {
        "videos": ["D:/Assets/V/Sleep.mp4", "D:/Assets/V/Zen.mp4", "D:/Assets/V/Library.mp4", "D:/Assets/V/Mountain.mp4"],
        "audios": ["D:/Assets/A/Rain.mp3", "D:/Assets/A/Zen.mp3", "D:/Assets/A/Ambient.mp3", "D:/Assets/A/Wind.mp3"],
        "prompts": [
            "Studio Ghibli style, dark cozy bedroom at night, heavy rain outside",
            "Studio Ghibli style, peaceful abandoned temple, glowing moon",
            "Studio Ghibli style, ancient library, single candle burning",
            "Studio Ghibli style, high mountain peak, starry night sky"
        ]
    },
    "CLIENT_SECRETS_FILE": "client_secrets.json",
    "SCOPES": ["https://www.googleapis.com/auth/youtube.upload"]
}


# ==========================================
# 3. 基础工具层 (Utility Functions)
# ==========================================

def log_status(stage, msg, status="INFO"):
    """统一日志输出"""
    time_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{time_str}] [{stage:<12}] [{status:<5}] {msg}")

def safe_fetch_transcript(video_id):
    """安全获取字幕列表"""
    log_status("SOURCE", f"Fetching transcript for {video_id}...")
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en'])
        raw_ts = transcript.fetch()
        
        if not isinstance(raw_ts, list):
            log_status("SOURCE", f"Expected list, got {type(raw_ts)}", "ERROR")
            return None
            
        log_status("SOURCE", f"Transcript fetched successfully. Entries: {len(raw_ts)}", "OK")
        return raw_ts
    except Exception as e:
        log_status("SOURCE", f"Fetch failed: {e}", "ERROR")
        return None

def clean_transcript(raw_ts):
    """清洗与强截断字幕"""
    log_status("CLEAN", "Cleaning transcript...")
    try:
        text_list = [re.sub(r'\[.*?\]', '', entry['text']) for entry in raw_ts]
        full_text = " ".join(text_list)

        fillers = [r'\bum\b', r'\buh\b', r'\byou know\b']
        for f in fillers:
            full_text = re.sub(f, '', full_text, flags=re.IGNORECASE)

        full_text = re.sub(r'\s+', ' ', full_text).strip()
        words = full_text.split()
        
        if len(words) > 25000:
            log_status("CLEAN", "Truncating to 25000 words.", "WARN")
            words = words[:25000]

        final_text = " ".join(words)
        log_status("CLEAN", f"Final length: {len(words)} words", "OK")
        return final_text
    except Exception as e:
        log_status("CLEAN", f"Cleaning failed: {e}", "ERROR")
        return ""

def split_chunks(text, chunk_size=4000):
    """文本定长切片生成器"""
    words = text.split()
    for i in range(0, len(words), chunk_size):
        yield " ".join(words[i:i+chunk_size])

def text_wrap_for_image(text, font, max_width):
    """处理封面文字换行"""
    lines, words = [], text.split()
    while words:
        line = ''
        while words and font.getlength(line + words[0]) <= max_width:
            line += (words.pop(0) + ' ')
        lines.append(line.strip())
    return lines


# ==========================================
# 4. API 认知层 (Map-Reduce)
# ==========================================

async def extract_map_insights(video_id, session_dir):
    """执行 Map 阶段：切片并并发提取不重叠的洞察"""
    raw_ts = safe_fetch_transcript(video_id)
    if not raw_ts: 
        log_status("MAP", "No raw transcript to process.", "ERROR")
        return None
        
    try:
        clean_text = clean_transcript(raw_ts)
        if not clean_text: 
            log_status("MAP", "Cleaned text is empty.", "ERROR")
            return None
            
        with open(os.path.join(session_dir, "1_clean_transcript.txt"), "w", encoding="utf-8") as f:
            f.write(clean_text)
            
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        chunks = list(split_chunks(clean_text, chunk_size=4000))
        log_status("MAP", f"Processing {len(chunks)} chunks concurrently...", "INFO")

        async def map_chunk(chunk_text):
            prompt = PROMPT_CONFIG["STEP1_MAP"].format(chunk=chunk_text)
            try:
                res = await asyncio.to_thread(client.models.generate_content, model=MODEL_CONFIG["G_MODEL"], contents=prompt)
                return res.text
            except Exception as e: 
                log_status("MAP", f"Chunk generation error: {e}", "ERROR")
                return ""

        map_results = await asyncio.gather(*[map_chunk(c) for c in chunks])
        combined_insights = "\n---\n".join([text for text in map_results if text])
        
        with open(os.path.join(session_dir, "2_map_insights_pool.txt"), "w", encoding="utf-8") as f:
            f.write(combined_insights)

        log_status("MAP", "Global map insights extracted.", "OK")
        return combined_insights
    except Exception as e:
        log_status("MAP", f"Map phase failed: {e}", "ERROR")
        return None

async def reduce_to_unique_concepts(insights_pool):
    """执行 Reduce 阶段：去重合并，提取唯一的核心概念"""
    log_status("REDUCE", "Deduplicating and discovering core topic...", "INFO")
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        prompt = PROMPT_CONFIG["STEP2_REDUCE"].format(insights=insights_pool)
        res = await asyncio.to_thread(client.models.generate_content, model=MODEL_CONFIG["G_MODEL"], contents=prompt)
        
        json_match = re.search(r'\{.*\}', res.text, re.DOTALL)
        if not json_match: 
            log_status("REDUCE", "No JSON found in response.", "ERROR")
            return None, []
            
        json_data = json.loads(json_match.group())
        log_status("REDUCE", f"Topic discovered: {json_data.get('topic', 'Unknown')}", "OK")
        return json_data.get("topic", "Unknown Topic"), json_data.get("concepts", [])
    except Exception as e:
        log_status("REDUCE", f"Reduce phase failed: {e}", "ERROR")
        return None, []


# ==========================================
# 5. 音视频生成层 (Media Rendering)
# ==========================================

async def generate_tts_audio(script, folder):
    """防抖动的分段 TTS 音频合成"""
    log_status("TTS", "Generating audio pieces...", "INFO")
    parts = [script[i:i+800] for i in range(0, len(script), 800)]
    flist = []
    
    for i, p in enumerate(parts):
        p_path = os.path.join(folder, f"p{i}.mp3")
        try:
            await edge_tts.Communicate(p, MODEL_CONFIG["VOICE"], rate="-15%", pitch="-5Hz").save(p_path)
            flist.append(p_path)
        except Exception as e:
            log_status("TTS", f"Segment {i} failed: {e}", "ERROR")
            return None
    
    merged = os.path.join(folder, "voice_full.mp3")
    clist = os.path.join(folder, "clist.txt")
    with open(clist, "w", encoding="utf-8") as f:
        for p in flist: f.write(f"file '{os.path.abspath(p)}'\n")
    
    try:
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', clist, '-c', 'copy', merged], capture_output=True, check=True)
        log_status("TTS", "Audio rendering complete.", "OK")
        return merged
    except subprocess.CalledProcessError as e:
        log_status("TTS", f"FFmpeg concat failed: {e.stderr.decode() if e.stderr else str(e)}", "ERROR")
        return None

async def generate_video_cover(topic, img_prompt, folder):
    """生成视频缩略图封面"""
    log_status("COVER", f"Generating cover for: {topic[:20]}...", "INFO")
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = await asyncio.to_thread(client.models.generate_image, model="gemini-3-flash-image", prompt=img_prompt)
        bg_p = os.path.join(folder, "bg.png")
        response.save(bg_p)
        
        img = Image.open(bg_p).resize((1280, 720))
        draw = ImageDraw.Draw(img)
        try: font = ImageFont.truetype("arial.ttf", 60)
        except: font = ImageFont.load_default()
        
        display_text = f"AUDIO MASTERCLASS:\n{topic.upper()}"
        lines = text_wrap_for_image(display_text, font, 1100)
        y = 600 - (len(lines)*80)
        for line in lines:
            draw.text((80, y), line, fill=(255,255,255), font=font, stroke_width=4, stroke_fill=(0,0,0))
            y += 80
            
        thumb_path = os.path.join(folder, "thumb.jpg")
        img.convert('RGB').save(thumb_path)
        log_status("COVER", "Thumbnail successfully created.", "OK")
        return thumb_path
    except Exception as e:
        log_status("COVER", f"Generation failed: {e}", "ERROR")
        return None


# ==========================================
# 6. 生产流水线层 (Core Pipeline)
# ==========================================

async def run_masterclass_pipeline(global_insights, session_dir):
    """总控制流水线：提取概念、高密度生成、渲染封装"""
    log_status("PIPELINE", "Initiating high-density production cycle...", "START")
    
    topic, principles = await reduce_to_unique_concepts(global_insights)
    if not principles:
        log_status("PIPELINE", "No valid concepts extracted. Halting.", "ERROR")
        return

    safe_folder_name = re.sub(r'[\\/*?:"<>|]', "", topic)[:30].strip()
    folder = os.path.join(session_dir, safe_folder_name)
    os.makedirs(folder, exist_ok=True)

    with open(os.path.join(folder, "3_reduce_principles.txt"), "w", encoding="utf-8") as f:
        json.dump({"Topic": topic, "Concepts": principles}, f, indent=4, ensure_ascii=False)

    o_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    master_script_text = ""
    
    log_status("SCRIPT", f"Expanding {len(principles)} deduplicated concepts...", "INFO")
    
    for i, concept in enumerate(principles):
        point = concept.get('point', '')
        details = concept.get('details', '')
        log_status("SCRIPT", f"Processing Seg {i+1}/{len(principles)}: {point[:30]}...", "INFO")
        
        script_prompt = PROMPT_CONFIG["STEP3_SCRIPT_SINGLE"].format(topic=topic, point=point, details=details)
        
        try:
            res = await o_client.chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": script_prompt}])
            chunk_text = res.choices[0].message.content
            
            # 清理 Markdown 确保零标记语言
            chunk_text = chunk_text.replace("**", "").replace("#", "").replace("- ", "")
            word_count = len(chunk_text.split())
            log_status("SCRIPT", f"Seg {i+1} initial words: {word_count}", "OK")
            
            # 防偷懒循环：ChatGPT 建议阈值下调至 500，避免无意义水文
            if word_count < 500:
                log_status("SCRIPT", f"Seg {i+1} is under 500 words. Expanding...", "WARN")
                continue_prompt = PROMPT_CONFIG["STEP3_SCRIPT_CONTINUE"].format(text=chunk_text[-500:]) 
                more_res = await o_client.chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": continue_prompt}])
                more_text = more_res.choices[0].message.content.replace("**", "").replace("#", "")
                
                chunk_text += f" ... {more_text}"
                log_status("SCRIPT", f"Seg {i+1} successfully expanded to {len(chunk_text.split())} words.", "OK")
            
            master_script_text += f"\n\n{chunk_text}\n\n"
            
        except Exception as e:
            log_status("SCRIPT", f"Failed generating Seg {i+1}: {e}", "ERROR")

    # 生成 SEO
    try:
        meta_prompt = f"Generate JSON SEO metadata (title, description, tags) for a highly intelligent audio masterclass about {topic}. No cliches."
        meta_res = await o_client.chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": meta_prompt}], response_format={"type": "json_object"})
        meta = json.loads(meta_res.choices[0].message.content)
    except Exception as e:
        log_status("PIPELINE", f"Meta generation failed: {e}", "WARN")
        meta = {"title": topic, "description": "Audio masterclass.", "tags": "education"}

    total_words = len(master_script_text.split())
    log_status("PIPELINE", f"Master script assembled! Total Length: {total_words} words.", "OK")

    with open(os.path.join(folder, "4_script_review.txt"), "w", encoding="utf-8") as f:
        f.write(f"--- TITLE: {meta.get('title', 'Unknown')} ---\n--- TOTAL WORDS: {total_words} ---\n{master_script_text}")

    if ONLY_GENERATE_SCRIPT:
        log_status("PIPELINE", "ONLY_GENERATE_SCRIPT is ON. Halting.", "STOP")
        return

    # 随机素材组合与渲染
    selected_v = random.choice(CONFIG["ASSETS_POOL"]["videos"])
    selected_a = random.choice(CONFIG["ASSETS_POOL"]["audios"])
    selected_p = random.choice(CONFIG["ASSETS_POOL"]["prompts"])

    voice_path = await generate_tts_audio(master_script_text, folder)
    thumb_path = await generate_video_cover(topic, selected_p, folder)
    
    if not voice_path or not thumb_path: 
        log_status("PIPELINE", "Media assets missing. Aborting render.", "ERROR")
        return

    final_v = os.path.join(folder, "final.mp4")
    cmd = ['ffmpeg', '-y', '-stream_loop', '-1', '-i', selected_v, '-i', voice_path, '-stream_loop', '-1', '-i', selected_a,
           '-filter_complex', "[1:a]showwaves=s=1280x100:mode=line:colors=white@0.2[w]; [0:v][w]overlay=0:H-100[v]; [1:a]volume=1.2[va]; [2:a]volume=0.25[ba]; [va][ba]amix=inputs=2:duration=first[a]",
           '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'ultrafast', '-shortest', final_v]
    
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    
    if process.returncode == 0: 
        log_status("PIPELINE", f"FFmpeg Render Success: {final_v}", "SUCCESS")
    else:
        log_status("PIPELINE", f"FFmpeg Error: {stderr.decode()}", "ERROR")


# ==========================================
# 7. 主控入口 (Main Execution)
# ==========================================

async def get_target_video_id():
    """获取处理目标，预留自动增长率算法接口"""
    if not IS_AUTO_SEARCH:
        log_status("SYSTEM", f"Using Manual Video ID: {MANUAL_VIDEO_ID}", "INFO")
        return MANUAL_VIDEO_ID
    return MANUAL_VIDEO_ID

async def main():
    """主调度函数"""
    os.makedirs(CONFIG["BASE_PATH"], exist_ok=True)
    log_status("SYSTEM", "--- V18 HIGH-DENSITY FACTORY STARTING ---", "START")
    
    session_id = datetime.now().strftime('%Y%m%d_%H%M')
    session_dir = os.path.join(CONFIG["BASE_PATH"], session_id)
    os.makedirs(session_dir, exist_ok=True)
    log_status("SYSTEM", f"Session initialized at: {session_dir}", "OK")
    
    v_id = await get_target_video_id()
    if not v_id: 
        log_status("SYSTEM", "Video ID invalid. Shutting down.", "ERROR")
        return
        
    global_insights = await extract_map_insights(v_id, session_dir)
    if not global_insights: 
        log_status("SYSTEM", "Global insights extraction failed. Shutting down.", "ERROR")
        return
        
    await run_masterclass_pipeline(global_insights, session_dir)
    log_status("SYSTEM", "--- V18 FACTORY MISSION COMPLETE ---", "DONE")


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())