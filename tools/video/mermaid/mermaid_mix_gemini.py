import os
import random
import subprocess
import json
import re
import math

# ================== 基础配置 ==================
BASE_DIR = "H:\\OliverAI\\resources\\mermaid-0202"
CATEGORIES = ["1_fish", "2_turtle", "3_coral"]
TARGET_DURATION = 3 * 60
OUTPUT_FILE = os.path.join(BASE_DIR, "FINAL_STABLE_VERSION.mp4")
FONT_PATH = "C:/Windows/Fonts/arial.ttf"
USE_OPENAI_CAPTIONS = True   # 不想用就 False
OPENAI_MODEL = "gpt-4.1-mini"

CAPTION_COUNT = 5
MERMAID_COUNT = 2

# ================== 工具函数 ==================
def get_video_duration(file_path):
    """获取单个视频的时长（秒）"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        return float(result.stdout)
    except:
        return 0

# ================== OpenAI 文案生成 ==================
def generate_captions():
    if not USE_OPENAI_CAPTIONS:
        return ["Ocean breathes in silence"] * CAPTION_COUNT
        
    from openai import OpenAI
    # 请确保已设置环境变量 os.environ["OPENAI_API_KEY"]
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    prompt = """
Generate 50 short, calm, poetic English captions for deep ocean relaxation videos.
Rules:
- 6 to 12 words
- No punctuation at the end
- Calm, emotional, cinematic
- No emojis
- Return ONLY a JSON array of strings
"""
    print("🤖 Calling OpenAI to generate poetic captions...")
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()    
    
    print(text)

    return json.loads(text)

def get_files(path, ext):
    if not os.path.exists(path): return []
    return [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith(ext)]

def main():
    captions = generate_captions()

	# 1. 建立临时处理目录
    temp_dir = os.path.join(BASE_DIR, "temp_standardized")
    os.makedirs(temp_dir, exist_ok=True)

    # 2. 整理并选取必要的素材 (动态累加，及时止损)
    print("🎯 Selecting necessary clips to reach target duration...")
    raw_source_list = []
    accumulated_duration = 0
    # 冗余量，确保最后拼接后长度足够
    required_limit = TARGET_DURATION + 60

    for cat in CATEGORIES:
        if accumulated_duration >= required_limit: break
        
        # 处理 Intro
        intro = os.path.join(BASE_DIR, "intro", f"{cat}.mp4")
        if os.path.exists(intro):
            dur = get_video_duration(intro)
            raw_source_list.append(intro)
            accumulated_duration += dur
        
        # 处理该类别的素材
        vids = get_files(os.path.join(BASE_DIR, cat), ".mp4")
        random.shuffle(vids)
        
        for v in vids:
            if accumulated_duration >= required_limit: break
            dur = get_video_duration(v)
            if dur > 0:
                raw_source_list.append(v)
                accumulated_duration += dur

    print(f"✅ Selected {len(raw_source_list)} clips. Total selected duration: {accumulated_duration:.2f}s")

    # 随机选出加美人鱼的片段索引
    mermaid_indices = random.sample(range(len(raw_source_list)), min(MERMAID_COUNT, len(raw_source_list)))
    mermaid_assets = get_files(os.path.join(BASE_DIR, "mermaid_assets"), ".webm")

    # 2. 【核心】精准洗白 (只标准化选中的片段)
    print("🔄 Step 1: Standardizing selected clips & Injecting Mermaids...")
    standardized_vids = []
    for i, vid_path in enumerate(raw_source_list):
        temp_out = os.path.join(temp_dir, f"clip_{i}.mp4")
        
        # 如果这个片段需要加美人鱼
        if i in mermaid_indices and mermaid_assets:
            # 【路径 A】加美人鱼 + 标准化
            print(f"  [🧜] Processing mermaid clip {i}...")
            m_asset = random.choice(mermaid_assets)
            cmd = [
                "ffmpeg", "-y", "-i", vid_path,
                "-c:v", "libvpx-vp9", "-i", m_asset,
                "-filter_complex", 
                "[1:v]scale=100:-1[m];[0:v]scale=1920:1080,fps=30,setsar=1[bg];[bg][m]overlay=x=20:y=20",
                "-c:v", "h264_nvenc", "-b:v", "10M", "-an", temp_out
            ]
        else:
            # 【路径 B】仅标准化
            cmd = [
                "ffmpeg", "-y", "-i", vid_path,
                "-vf", "scale=1920:1080,fps=30,setsar=1",
                "-c:v", "h264_nvenc", "-b:v", "10M", "-an", temp_out
            ]
        
        subprocess.run(cmd, check=True)
        standardized_vids.append(temp_out)

    # 3. 生成 Concat 列表
    concat_txt = os.path.join(BASE_DIR, "concat_safe.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for v in standardized_vids:
            clean_v = v.replace('\\', '/')
            f.write(f"file '{clean_v}'\n")

    # 4. 最终合成
    print("🎬 Step 2: Final assembly with OpenAI captions & Audio...")
    music = random.choice(get_files(os.path.join(BASE_DIR, "music"), ".mp3"))
    ambient = random.choice(get_files(os.path.join(BASE_DIR, "background"), ".mp3"))

    # 构建字幕滤镜链
    sub_filters = []
    # 均匀分布字幕时间点
    safe_time_points = sorted(random.sample(range(20, TARGET_DURATION - 60), CAPTION_COUNT))
    for t, txt in zip(safe_time_points, captions):
        clean_txt = txt.replace("'", "\\'").replace(":", "\\:")
        sub_filters.append(
            f"drawtext=text='{clean_txt}':fontfile='{FONT_PATH}':fontsize=42:fontcolor=white@0.8:"
            f"shadowcolor=black@0.5:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h*0.85:"
            f"enable='between(t,{t},{t+6})'"
        )

    # 拼接所有的滤镜
    vf_chain = ",".join(sub_filters)

# ---------------------------------------------------------
    # 第一步：仅生成无声长视频（解决拼接导致的断音）
    # ---------------------------------------------------------
    SILENT_VIDEO = os.path.join(BASE_DIR, "silent_temp.mp4")
    
    # 字幕滤镜脚本
    fc_video = f"[0:v]{','.join(sub_filters)}[v_out]"
    with open(os.path.join(BASE_DIR, "vf_video.txt"), "w", encoding="utf-8") as f:
        f.write(fc_video)

    cmd_video = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-filter_complex_script", os.path.join(BASE_DIR, "vf_video.txt"),
        "-map", "[v_out]",
        "-an", # 彻底去掉所有片段的原始声音索引
        "-t", str(TARGET_DURATION),
        "-c:v", "h264_nvenc", "-b:v", "12M",
        SILENT_VIDEO
    ]
    
    print("🎬 Step 2.1: Generating silent video (No audio glitches possible)...")
    subprocess.run(cmd_video, check=True)

    # ---------------------------------------------------------
    # 第二步：将背景音乐直接贴在长视频上
    # ---------------------------------------------------------
    audio_mix_filter = (
        "[1:a]loudnorm,volume=0.8[a1]; "
        "[2:a]volume=0.15[a2]; "
        "[a1][a2]amix=inputs=2:duration=first:dropout_transition=0[outa]"
    )
    
    cmd_audio = [
        "ffmpeg", "-y",
        "-i", SILENT_VIDEO, # 输入 0: 已经合好的长视频
        "-stream_loop", "-1", "-i", music,   # 输入 1
        "-stream_loop", "-1", "-i", ambient, # 输入 2
        "-filter_complex", audio_mix_filter,
        "-map", "0:v",      # 直接取视频
        "-map", "[outa]",   # 取混合后的音频
        "-c:v", "copy",     # ！！！关键：视频流直接拷贝，不需要重新编码，速度极快
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest",        # 确保音频不超出视频长度
        OUTPUT_FILE
    ]

    print("🎵 Step 2.2: Layering background music...")
    subprocess.run(cmd_audio, check=True)

    print(f"✨ ALL DONE! Check your masterpiece: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()