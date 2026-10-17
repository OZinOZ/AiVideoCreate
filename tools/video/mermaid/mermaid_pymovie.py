"""
Mermaid Video Generator V11.5 - AUDIO FINGERPRINT REMASTER
-----------------------------
针对 YouTube Content ID 优化的音频/视频双重去重生产脚本。
"""

import os
import random
import json
import subprocess
import re
import warnings
import sys

# --- 环境检查 ---
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")

try:
    from moviepy import VideoFileClip, concatenate_videoclips
    from pydub import AudioSegment
    from pydub.effects import normalize
    from openai import OpenAI
except ImportError as err:
    print(f"❌ 缺少必要库: {err}")
    sys.exit(1)

# ================== 1. 全局常量配置 ==================
USE_OPENAI = True
OPENAI_MODEL = "gpt-3.5-turbo"
BASE_DIR = r"H:\OliverAI\resources\mermaid-0202"
CATEGORIES = ["1_fish", "2_turtle", "3_coral"]
TARGET_DURATION = 90 * 60  # 90分钟生产模式
FPS = 30
VIDEO_BITRATE = "12M"

PATHS = {
    "music": os.path.join(BASE_DIR, "music"),
    "bg": os.path.join(BASE_DIR, "background"),
    "mermaid": os.path.join(BASE_DIR, "mermaid_assets"),
    "temp_std": os.path.join(BASE_DIR, "temp_standardized"),
    "temp_video": os.path.join(BASE_DIR, "temp_video.mp4"),
    "temp_audio_raw": os.path.join(BASE_DIR, "temp_audio_raw.mp3"),
    "temp_audio_clean": os.path.join(BASE_DIR, "temp_audio_clean.mp3"),
    "overlay_json": os.path.join(BASE_DIR, "overlay_plan.json"),
    "output": os.path.join(BASE_DIR, "FINAL_MERMAID_V11_5.mp4")
}

STYLE_POOL = {
    "fonts": ["arial.ttf", "calibri.ttf", "georgia.ttf", "segoeui.ttf"],
    "sizes": [50, 60, 70],
    "colors": ["white", "0xFFE4B5", "0x00FFFF", "0xFFD700"],
    "y_offsets": [0.82, 0.85, 0.88],
    "x_aligns": ["(w-text_w)/2", "(w-text_w)/3", "(w-text_w)*2/3"]
}

os.makedirs(PATHS["temp_std"], exist_ok=True)

# ================== 2. 音频“物理洗白”函数 ==================

def clean_audio_fingerprint(input_path, output_path):
    """
    通过微调音高和速度，彻底改变音频指纹。
    atempo: 改变速度 (1.01 = 加快1%)
    rubberband: 改变音高 (pitch=1.01 = 提高微量半音)
    """
    print("🧬 [Audio] 正在重塑音频频谱指纹...")
    # 随机化微调，确保每个视频的音频指纹都不一样
    p = random.uniform(1.005, 1.015)
    s = random.uniform(1.005, 1.015)
    
    # 使用 FFmpeg 滤镜进行重采样和频谱位移
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", f"rubberband=pitch={p},atempo={s}", 
        "-ar", "44100", "-ac", "2", "-b:a", "192k",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

# ================== 3. 核心逻辑模块 ==================

def get_video_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=False)
    return float(res.stdout.strip()) if res.stdout else 0.0

def generate_overlay_plan(total_duration):
    print("📝 [Step 4] 生成多样式特效计划...")
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = "Generate 60 poetic ocean captions. JSON array of strings only."
    try:
        resp = client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": prompt}])
        captions = json.loads(re.sub(r"```(json)?|```", "", resp.choices[0].message.content).strip())
    except:
        captions = ["Ocean whispers"] * 60

    plan = {"mermaid": {"enable": True, "segments": []}, "captions": []}
    cursor = 30
    for text in captions:
        if cursor + 20 > total_duration: break
        plan["captions"].append({
            "start": cursor, "end": cursor + 8, "text": text,
            "font": random.choice(STYLE_POOL["fonts"]),
            "size": random.choice(STYLE_POOL["sizes"]),
            "color": random.choice(STYLE_POOL["colors"]),
            "y": random.choice(STYLE_POOL["y_offsets"]),
            "x_pos": random.choice(STYLE_POOL["x_aligns"])
        })
        cursor += random.randint(80, 120)

    m_cursor = 60
    while m_cursor + 5 < total_duration:
        plan["mermaid"]["segments"].append({"start": m_cursor, "end": m_cursor + 5})
        m_cursor += random.randint(300, 600)

    with open(PATHS["overlay_json"], "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

def final_fusion():
    print("🔥 [Step 5] 启动最终合成 (音视频双去重)...")
    with open(PATHS["overlay_json"], "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 注意：这里使用的是洗白后的音频 temp_audio_clean
    inputs = ["-i", PATHS["temp_video"], "-i", PATHS["temp_audio_clean"]]
    filters = ["[0:v]setpts=PTS-STARTPTS[base]"]
    last_v = "[base]"

    if cfg["mermaid"]["enable"]:
        m_assets = [os.path.join(PATHS["mermaid"], f) for f in os.listdir(PATHS["mermaid"]) if f.endswith(".webm")]
        if m_assets:
            inputs += ["-stream_loop", "-1", "-i", random.choice(m_assets)]
            m_en = "+".join([f"between(t,{s['start']},{s['end']})" for s in cfg["mermaid"]["segments"]])
            filters.append(f"[2:v]scale=iw*0.18:-1,setpts=PTS-STARTPTS[m_v]")
            filters.append(f"{last_v}[m_v]overlay=x=20:y=20:enable='{m_en}'[v1]")
            last_v = "[v1]"

    for i, cap in enumerate(cfg["captions"]):
        txt = cap["text"].replace("'", "'\\\\\\''").replace(":", "\\:")
        f_path = f"C\\:/Windows/Fonts/{cap['font']}"
        draw = (f"drawtext=text='{txt}':fontfile='{f_path}':fontsize={cap['size']}:"
                f"fontcolor={cap['color']}:shadowcolor=black@0.6:shadowx=3:shadowy=3:"
                f"x={cap['x_pos']}:y=h*{cap['y']}:enable='between(t,{cap['start']},{cap['end']})'")
        next_v = f"[v_txt{i}]"
        filters.append(f"{last_v}{draw}{next_v}")
        last_v = next_v

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", last_v, "-map", "1:a:0", "-c:v", "h264_nvenc", "-preset", "p4",
           "-b:v", VIDEO_BITRATE, "-c:a", "aac", "-b:a", "192k", "-shortest", PATHS["output"]]
    subprocess.run(cmd, check=True)

# ================== 4. 主流程 ==================

def main():
    # 1. 素材筛选
    selected, duration = [], 0
    for cat in CATEGORIES:
        intro = os.path.join(BASE_DIR, "intro", f"{cat}.mp4")
        if os.path.exists(intro):
            duration += get_video_duration(intro); selected.append(intro)
        cat_p = os.path.join(BASE_DIR, cat)
        files = [os.path.join(cat_p, f) for f in os.listdir(cat_p) if f.endswith(".mp4")]
        random.shuffle(files)
        for vid in files:
            if duration >= TARGET_DURATION: break
            duration += get_video_duration(vid); selected.append(vid)

    # 2. 视频处理 (NVENC)
    std_vids = []
    for i, path in enumerate(selected):
        out = os.path.join(PATHS["temp_std"], f"std_{i}.mp4")
        vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", vf, "-c:v", "h264_nvenc", "-an", out], check=True)
        std_vids.append(out)

    # 3. 视频拼接
    clips = [VideoFileClip(p) for p in std_vids]
    final_v = concatenate_videoclips(clips, method="chain").subclipped(0, TARGET_DURATION)
    final_v.write_videofile(PATHS["temp_video"], fps=FPS, audio=False, logger=None, 
                            ffmpeg_params=["-c:v", "h264_nvenc", "-b:v", VIDEO_BITRATE])
    for c in clips: c.close()

    # 4. 音频洗白流程 (核心变动点)
    print("🎵 [Step 4] 执行音频频谱指纹重塑...")
    m_files = [os.path.join(PATHS["music"], f) for f in os.listdir(PATHS["music"]) if f.endswith(".mp3")]
    b_files = [os.path.join(PATHS["bg"], f) for f in os.listdir(PATHS["bg"]) if f.endswith(".mp3")]
    
    # 混缩原始音频
    music = normalize(AudioSegment.from_file(random.choice(m_files)))
    ambient = normalize(AudioSegment.from_file(random.choice(b_files))) - 15
    mixed = music.overlay(ambient, loop=True)[:TARGET_DURATION * 1000]
    mixed.export(PATHS["temp_audio_raw"], format="mp3")
    
    # 调用 FFmpeg 物理重塑指纹
    clean_audio_fingerprint(PATHS["temp_audio_raw"], PATHS["temp_audio_clean"])
    
    generate_overlay_plan(TARGET_DURATION)
    final_fusion()
    print(f"✨ 任务完成！洗白视频已生成至: {PATHS['output']}")

if __name__ == "__main__":
    main()