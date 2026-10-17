# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals
"""
AI Audio Masterclass Factory V29 - The Pure Architect Edition
Features: Planner-Executor, Strict Word Count Check, Auto-Retry, Independent Segments.
"""

import os
import sys
import asyncio
import re
import random
import json
import subprocess
from datetime import datetime

# 核心依赖库
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from openai import AsyncOpenAI
import edge_tts
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. 核心控制台 (Global Configuration)
# ==========================================
IS_AUTO_SEARCH = False
MANUAL_VIDEO_ID = "rDdoUbCFn24"

ONLY_GENERATE_SCRIPT = False      # 测试期：随时可以改为 False 启动渲染
IS_AUTO_UPLOAD = False

MODEL_CONFIG = {
    "G_MODEL": "gemini-2.5-pro",
    "O_MODEL": "gpt-4o-mini",      
    "VOICE": "en-AU-WilliamNeural"
}

SCRIPT_CONFIG = {
    "TARGET_WORDS": 600,         # 提示词要求字数
    "MIN_REQUIRED_WORDS": 450,   # 校验最低通过字数
    "MAX_RETRIES": 3,            # 单段最大重写次数
    "RETRY_DELAY": 2             # 重试间隔时间(秒)
}

CONFIG = {
    "BASE_PATH": "D:/AIGen/MasterFactory_V29",
    "TARGET_CHANNELS": ["UCGq-a57w-aPwyi3pW7XLiHw", "UC2D2CMWXMOVWx7giW1n3LIg"],
    "ASSETS_POOL": {
        "videos": ["D:/Assets/V/wind.mp4", "D:/Assets/V/bedroom.mp4", "D:/Assets/V/rain.mp4", "D:/Assets/V/tent.mp4"],
        "audios": ["D:/Assets/A/wind.mp3", "D:/Assets/A/bedroom.mp3", "D:/Assets/A/rain.mp3", "D:/Assets/A/tent.mp3"],
        "prompts": [
            "Studio Ghibli style, cozy bedroom at night, windy snow outside",
            "Studio Ghibli style, warm livingroom with fireplace, rainy night outside",
            "Studio Ghibli style, forest cabin with light strings, starry night sky",
            "Studio Ghibli style, corner desk with candle light, windy leaves outside"
        ]
    }
}

# ==========================================
# 2. 纯粹逻辑提示词库 (Pure Architect Prompts)
# ==========================================
PROMPT_CONFIG = {
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

# ==========================================
# 3. 基础工具层 (Utility Functions)
# ==========================================
def log_status(stage: str, msg: str, status: str = "INFO"):
    """统一日志输出格式"""
    time_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{time_str}] [{stage:<10}] [{status:<5}] {msg}")

def save_file(filepath: str, content: str) -> bool:
    """保存文本内容到文件"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        log_status("FILE", f"Saved successfully: {os.path.basename(filepath)}", "OK")
        return True
    except Exception as e:
        log_status("FILE", f"Failed to save {os.path.basename(filepath)}: {e}", "ERROR")
        return False

def split_chunks(text: str, chunk_size: int = 4000):
    """文本切片生成器"""
    words = text.split()
    for i in range(0, len(words), chunk_size):
        yield " ".join(words[i:i+chunk_size])

def text_wrap_for_image(text: str, font, max_width: int):
    """图片字体自动换行"""
    lines, words = [], text.split()
    while words:
        line = ''
        while words and font.getlength(line + words[0]) <= max_width:
            line += (words.pop(0) + ' ')
        lines.append(line.strip())
    return lines

def setup_environment() -> str:
    """初始化运行环境并返回会话目录"""
    try:
        os.makedirs(CONFIG["BASE_PATH"], exist_ok=True)
        session_id = datetime.now().strftime('%Y%m%d_%H%M')
        session_dir = os.path.join(CONFIG["BASE_PATH"], session_id)
        os.makedirs(session_dir, exist_ok=True)
        log_status("ENV", f"Session directory created: {session_dir}", "OK")
        return session_dir
    except Exception as e:
        log_status("ENV", f"Failed to setup environment: {e}", "ERROR")
        return ""

async def get_target_video_id() -> str:
    """获取目标视频ID"""
    if not IS_AUTO_SEARCH:
        log_status("SYSTEM", f"Using Manual ID: {MANUAL_VIDEO_ID}", "INFO")
        return MANUAL_VIDEO_ID
    log_status("SYSTEM", "Auto search logic not implemented, falling back to manual ID.", "WARN")
    return MANUAL_VIDEO_ID

# ==========================================
# 4. 数据获取与预处理层 (Data & Preprocessing)
# ==========================================
async def fetch_source_transcript(video_id: str) -> list:
    """提取原始字幕信息"""
    log_status("SOURCE", f"Fetching transcript for {video_id}...", "INFO")
    try:
        raw_ts = YouTubeTranscriptApi().fetch(video_id, languages=['en']).to_raw_data()
        if not isinstance(raw_ts, list) or not raw_ts:
            log_status("SOURCE", "Judgment failed: Transcript data is invalid or empty.", "ERROR")
            return []
            
        log_status("SOURCE", f"Transcript fetched. Entries: {len(raw_ts)}", "OK")
        return raw_ts
    except Exception as e:
        log_status("SOURCE", f"Fetch exception: {e}", "ERROR")
        return []

def clean_transcript_data(raw_ts: list) -> str:
    """清洗无意义填充词并返回纯文本"""
    log_status("CLEAN", "Cleaning transcript...", "INFO")
    try:
        text_list = [re.sub(r'\[.*?\]', '', entry['text']) for entry in raw_ts]
        full_text = " ".join(text_list)

        fillers = [r'\bum\b', r'\buh\b', r'\byou know\b']
        for f in fillers:
            full_text = re.sub(f, '', full_text, flags=re.IGNORECASE)

        full_text = re.sub(r'\s+', ' ', full_text).strip()
        words = full_text.split()
        
        if len(words) > 25000:
            log_status("CLEAN", "Judgment triggered: Truncating to 25000 words.", "WARN")
            words = words[:25000]

        final_text = " ".join(words)
        if not final_text:
            log_status("CLEAN", "Judgment failed: Cleaned text is empty.", "ERROR")
            return ""
            
        log_status("CLEAN", f"Cleaned length: {len(words)} words", "OK")
        return final_text
    except Exception as e:
        log_status("CLEAN", f"Cleaning failed: {e}", "ERROR")
        return ""

# ==========================================
# 5. 大语言模型业务层 (LLM Pipelines)
# ==========================================
async def extract_map_insights(clean_text: str, session_dir: str) -> str:
    """Map 阶段：并发提取洞察"""
    try:
        save_file(os.path.join(session_dir, "1_clean_transcript.txt"), clean_text)
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
        
        if not combined_insights.strip():
            log_status("MAP", "Judgment failed: No insights extracted.", "ERROR")
            return ""

        save_file(os.path.join(session_dir, "2_map_insights_pool.txt"), combined_insights)
        log_status("MAP", "Global map insights extracted.", "OK")
        return combined_insights
    except Exception as e:
        log_status("MAP", f"Map phase failed: {e}", "ERROR")
        return ""

async def reduce_to_unique_concepts(insights_pool: str, session_dir: str):
    """Reduce 阶段：提炼主题和概念列表"""
    log_status("REDUCE", "Deduplicating concepts and generating unique examples...", "INFO")
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        prompt = PROMPT_CONFIG["STEP2_REDUCE"].format(insights=insights_pool)
        res = await asyncio.to_thread(client.models.generate_content, model=MODEL_CONFIG["G_MODEL"], contents=prompt)
        
        json_match = re.search(r'\{.*\}', res.text, re.DOTALL)
        if not json_match: 
            log_status("REDUCE", "Judgment failed: No JSON found in response.", "ERROR")
            return "", []
            
        json_data = json.loads(json_match.group())
        topic = json_data.get("topic", "Unknown Topic")
        concepts = json_data.get("concepts", [])
        
        if not concepts:
            log_status("REDUCE", "Judgment failed: Concepts list is empty.", "ERROR")
            return "", []
            
        log_status("REDUCE", f"Topic discovered: {topic}", "OK")
        
        # 保存结构化提炼结果
        safe_folder_name = re.sub(r'[\\/*?:"<>|]', "", topic)[:30].strip()
        folder = os.path.join(session_dir, safe_folder_name)
        os.makedirs(folder, exist_ok=True)
        save_file(os.path.join(folder, "3_reduce_principles.json"), json.dumps({"Topic": topic, "Concepts": concepts}, indent=4))
        
        return topic, concepts
    except Exception as e:
        log_status("REDUCE", f"Reduce phase failed: {e}", "ERROR")
        return "", []

async def generate_hook_segment(o_client: AsyncOpenAI, topic: str, principles: list) -> str:
    """生成引言段落 (Hook)"""
    log_status("SCRIPT", "Generating Opening Hook with concept context...", "INFO")
    try:
        concepts_str = "\n".join([f"- {c.get('point', 'Concept')}" for c in principles])
        prompt = PROMPT_CONFIG["STEP3_HOOK"].format(topic=topic, concepts=concepts_str)
        res = await o_client.chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": prompt}])
        text = res.choices[0].message.content.replace("**", "").replace("#", "").replace("- ", "")
        log_status("SCRIPT", "Hook generated successfully.", "OK")
        return f"{text}\n\n"
    except Exception as e:
        log_status("SCRIPT", f"Hook generation failed: {e}", "ERROR")
        return ""

async def generate_single_concept(o_client: AsyncOpenAI, topic: str, concept: dict, index: int, total: int) -> str:
    """带有字数重写机制的独立正片段落生成"""
    point = concept.get('point', '')
    details = concept.get('details', '')
    example = concept.get('specific_example', 'A relatable scenario.')
    
    prompt = PROMPT_CONFIG["STEP3_SCRIPT_SINGLE"].format(
        topic=topic, point=point, details=details, example=example, target_words=SCRIPT_CONFIG["TARGET_WORDS"]
    )
    
    for attempt in range(1, SCRIPT_CONFIG["MAX_RETRIES"] + 1):
        log_status("SCRIPT", f"Seg {index}/{total} Attempt {attempt} starting...", "INFO")
        try:
            res = await o_client.chat.completions.create(
                model=MODEL_CONFIG["O_MODEL"], 
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.choices[0].message.content.replace("**", "").replace("#", "").replace("- ", "")
            word_count = len(text.split())
            
            if word_count >= SCRIPT_CONFIG["MIN_REQUIRED_WORDS"]:
                log_status("SCRIPT", f"Judgment passed: Seg {index} generated {word_count} words.", "OK")
                return f"{text}\n\n"
            
            log_status("SCRIPT", f"Judgment failed: Seg {index} short ({word_count} < {SCRIPT_CONFIG['MIN_REQUIRED_WORDS']}). Discarding.", "WARN")
            if attempt < SCRIPT_CONFIG["MAX_RETRIES"]:
                await asyncio.sleep(SCRIPT_CONFIG["RETRY_DELAY"])
                
        except Exception as e:
            log_status("SCRIPT", f"Exception on Seg {index} attempt {attempt}: {e}", "ERROR")
            if attempt < SCRIPT_CONFIG["MAX_RETRIES"]:
                await asyncio.sleep(SCRIPT_CONFIG["RETRY_DELAY"])
            
    log_status("SCRIPT", f"Generation failed: Seg {index} exhausted retries.", "ERROR")
    return ""

async def generate_outro_segment(o_client: AsyncOpenAI, topic: str) -> str:
    """生成结语段落 (Outro)"""
    log_status("SCRIPT", "Generating Outro and Call to Action...", "INFO")
    try:
        prompt = PROMPT_CONFIG["STEP3_OUTRO"].format(topic=topic)
        res = await o_client.chat.completions.create(model=MODEL_CONFIG["O_MODEL"], messages=[{"role": "user", "content": prompt}])
        text = res.choices[0].message.content.replace("**", "").replace("#", "").replace("- ", "")
        log_status("SCRIPT", "Outro generated successfully.", "OK")
        return f"{text}\n\n"
    except Exception as e:
        log_status("SCRIPT", f"Outro generation failed: {e}", "ERROR")
        return ""

async def assemble_master_script(topic: str, principles: list, session_dir: str) -> tuple:
    """组装最终剧本 (调度全量脚本生成链路)"""
    o_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    master_script_text = ""
    safe_folder_name = re.sub(r'[\\/*?:"<>|]', "", topic)[:30].strip()
    folder = os.path.join(session_dir, safe_folder_name)
    
    # 1. 钩子
    hook_text = await generate_hook_segment(o_client, topic, principles)
    if not hook_text: return "", ""
    master_script_text += hook_text
    
    # 2. 正片循环 (自带失败重写机制)
    total_concepts = len(principles)
    for i, concept in enumerate(principles):
        seg_text = await generate_single_concept(o_client, topic, concept, i+1, total_concepts)
        if not seg_text:
            log_status("SCRIPT", f"Critical Failure: Seg {i+1} failed to generate. Continuing anyway...", "ERROR")
        master_script_text += seg_text
        
    # 3. 结语
    outro_text = await generate_outro_segment(o_client, topic)
    master_script_text += outro_text
    
    # 4. 统计与保存
    total_words = len(master_script_text.split())
    log_status("PIPELINE", f"Master script assembled! Total Length: {total_words} words.", "OK")
    
    final_output = f"--- TITLE: {topic} ---\n--- TOTAL WORDS: {total_words} ---\n{master_script_text}"
    save_file(os.path.join(folder, "4_script_review.txt"), final_output)
    
    return master_script_text, folder

# ==========================================
# 6. 音视频生成层 (Media Rendering)
# ==========================================
async def generate_tts_audio(script: str, folder: str) -> str:
    """分段 TTS 与合并"""
    log_status("TTS", "Generating audio pieces...", "INFO")
    parts = [script[i:i+800] for i in range(0, len(script), 800)]
    flist = []
    
    for i, p in enumerate(parts):
        p_path = os.path.join(folder, f"p{i}.mp3")
        try:
            await edge_tts.Communicate(p, MODEL_CONFIG["VOICE"], rate="-15%", pitch="-5Hz").save(p_path)
            flist.append(p_path)
        except Exception as e:
            log_status("TTS", f"Function failed: Segment {i} generation error: {e}", "ERROR")
            return ""
            
    merged = os.path.join(folder, "voice_full.mp3")
    clist = os.path.join(folder, "clist.txt")
    
    try:
        with open(clist, "w", encoding="utf-8") as f:
            for p in flist: f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', clist, '-c', 'copy', merged], capture_output=True, check=True)
        log_status("TTS", "Audio rendering complete.", "OK")
        return merged
    except subprocess.CalledProcessError as e:
        log_status("TTS", f"Function failed: FFmpeg concat error: {e.stderr.decode() if e.stderr else str(e)}", "ERROR")
        return ""

async def generate_video_cover(topic: str, img_prompt: str, folder: str) -> str:
    """生成视频封面"""
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
            
        display_text = f"AUDIO MASTERCLASS:\n{topic.upper()}"
        lines = text_wrap_for_image(display_text, font, 1100)
        y_pos = 600 - (len(lines)*80)
        for line in lines:
            draw.text((80, y_pos), line, fill=(255,255,255), font=font, stroke_width=4, stroke_fill=(0,0,0))
            y_pos += 80
            
        thumb_path = os.path.join(folder, "thumb.jpg")
        img.convert('RGB').save(thumb_path)
        log_status("COVER", "Thumbnail successfully created.", "OK")
        return thumb_path
    except Exception as e:
        log_status("COVER", f"Function failed: Generation error: {e}", "ERROR")
        return ""

async def render_final_media(topic: str, master_script_text: str, folder: str):
    """最终音视频混流渲染"""
    selected_v = random.choice(CONFIG["ASSETS_POOL"]["videos"])
    selected_a = random.choice(CONFIG["ASSETS_POOL"]["audios"])
    selected_p = random.choice(CONFIG["ASSETS_POOL"]["prompts"])

    voice_path = await generate_tts_audio(master_script_text, folder)
    thumb_path = await generate_video_cover(topic, selected_p, folder)
    
    if not voice_path or not thumb_path: 
        log_status("PIPELINE", "Judgment failed: Media assets missing. Aborting render.", "ERROR")
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
        else:
            log_status("PIPELINE", f"Function failed: FFmpeg Error: {stderr.decode()}", "ERROR")
    except Exception as e:
        log_status("PIPELINE", f"Function failed: Render exception: {e}", "ERROR")

# ==========================================
# 7. 主控入口 (Main Execution)
# ==========================================
async def main():
    """
    极简主控函数：仅负责调度底层流程和中断判断，无任何复杂数据处理。
    """
    log_status("SYSTEM", "--- V29 PURE ARCHITECT FACTORY STARTING ---", "START")
    
    session_dir = setup_environment()
    if not session_dir:
        log_status("SYSTEM", "Execution stopped: Env setup failed.", "STOP")
        return
        
    v_id = await get_target_video_id()
    if not v_id: 
        log_status("SYSTEM", "Execution stopped: Target ID is missing.", "STOP")
        return
        
    raw_ts = await fetch_source_transcript(v_id)
    if not raw_ts: 
        log_status("SYSTEM", "Execution stopped: Transcript data missing.", "STOP")
        return
        
    clean_text = clean_transcript_data(raw_ts)
    if not clean_text: 
        log_status("SYSTEM", "Execution stopped: Cleaned text is empty.", "STOP")
        return
        
    global_insights = await extract_map_insights(clean_text, session_dir)
    if not global_insights: 
        log_status("SYSTEM", "Execution stopped: Map insights failed.", "STOP")
        return
        
    topic, principles = await reduce_to_unique_concepts(global_insights, session_dir)
    if not principles: 
        log_status("SYSTEM", "Execution stopped: Reduce principles failed.", "STOP")
        return
        
    master_script, folder = await assemble_master_script(topic, principles, session_dir)
    if not master_script: 
        log_status("SYSTEM", "Execution stopped: Script assembly failed.", "STOP")
        return
        
    if ONLY_GENERATE_SCRIPT:
        log_status("SYSTEM", "ONLY_GENERATE_SCRIPT is ON. Halting before render.", "STOP")
        log_status("SYSTEM", "--- V29 FACTORY SCRIPT MISSION COMPLETE ---", "DONE")
        return
        
    await render_final_media(topic, master_script, folder)
    log_status("SYSTEM", "--- V29 FACTORY FULL MISSION COMPLETE ---", "DONE")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())