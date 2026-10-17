"""
Mermaid Video Generator V12.0 - 4K UHD & AUDIO FINGERPRINT REMASTER
-----------------------------
针对 YouTube 4K 算法优化的全流程生产脚本。
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

# ================== 1. 全局 4K 常量配置 ==================
USE_OPENAI = True
OPENAI_MODEL = "gpt-3.5-turbo"
BASE_DIR = r"H:\OliverAI\resources\mermaid-0202"
CATEGORIES = ["1_fish", "2_turtle", "3_coral"]
TARGET_DURATION = 90 * 60  # 90分钟
FPS = 30

# 4K 核心参数
UHD_WIDTH = 3840
UHD_HEIGHT = 2160
VIDEO_BITRATE = "50M" # 4K 建议 40M-60M 保证质感

PATHS = {
    "music": os.path.join(BASE_DIR, "music"),
    "bg": os.path.join(BASE_DIR, "background"),
    "mermaid": os.path.join(BASE_DIR, "mermaid_assets"),
    "temp_std": os.path.join(BASE_DIR, "temp_standardized"),
    "temp_video": os.path.join(BASE_DIR, "temp_video.mp4"),
    "temp_audio_raw": os.path.join(BASE_DIR, "temp_audio_raw.mp3"),
    "temp_audio_clean": os.path.join(BASE_DIR, "temp_audio_clean.mp3"),
    "overlay_json": os.path.join(BASE_DIR, "overlay_plan.json"),
    "output": os.path.join(BASE_DIR, "FINAL_MERMAID_4K_V12.mp4")
}

# 字体大小针对 4K 进行了翻倍处理
STYLE_POOL = {
    "fonts": ["arial.ttf", "calibri.ttf", "georgia.ttf", "segoeui.ttf"],
    "sizes": [100, 120, 140], # 4K 下字体需加大
    "colors": ["white", "0xFFE4B5", "0x00FFFF", "0xFFD700"],
    "y_offsets": [0.82, 0.85, 0.88],
    "x_aligns": ["(w-text_w)/2", "(w-text_w)/3", "(w-text_w)*2/3"]
}

os.makedirs(PATHS["temp_std"], exist_ok=True)

# ================== 2. 音频指纹洗白 (保持原逻辑) ==================

def clean_audio_fingerprint(input_path, output_path):
    print("🧬 [Audio] 正在重塑 4K 视频配套音频指纹...")
    p = random.uniform(1.005, 1.015)
    s = random.uniform(1.005, 1.015)
    
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", f"rubberband=pitch={p},atempo={s}", 
        "-ar", "44100", "-ac", "2", "-b:a", "192k",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

# ================== 3. 核心合成逻辑 (4K 适配) ==================

def get_video_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=False)
    return float(res.stdout.strip()) if res.stdout else 0.0

def generate_overlay_plan(total_duration):
    print("📝 [Step 4] 生成 4K 特效字幕计划...")
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = "Generate 60 poetic ocean captions. JSON array of strings only."
    try:
        resp = client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": prompt}])
        captions = json.loads(re.sub(r"```(json)?|```", "", resp.choices[0].message.content).strip())
    except:
        captions = ["The rhythm of the ocean"] * 60 
    
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
    print("🔥 [Step 5] 启动最终 4K 渲染合成...")
    with open(PATHS["overlay_json"], "r", encoding="utf-8") as f:
        cfg = json.load(f)

    inputs = ["-i", PATHS["temp_video"], "-i", PATHS["temp_audio_clean"]]
    filters = ["[0:v]setpts=PTS-STARTPTS[base]"]
    last_v = "[base]"

    if cfg["mermaid"]["enable"]:
        m_assets = [os.path.join(PATHS["mermaid"], f) for f in os.listdir(PATHS["mermaid"]) if f.endswith(".webm")]
        if m_assets:
            inputs += ["-stream_loop", "-1", "-i", random.choice(m_assets)]
            m_en = "+".join([f"between(t,{s['start']},{s['end']})" for s in cfg["mermaid"]["segments"]])
            # 4K 下缩放比例调整
            filters.append(f"[2:v]scale=iw*0.25:-1,setpts=PTS-STARTPTS[m_v]") 
            filters.append(f"{last_v}[m_v]overlay=x=50:y=50:enable='{m_en}'[v1]")
            last_v = "[v1]"

    for i, cap in enumerate(cfg["captions"]):
        txt = cap["text"].replace("'", "'\\\\\\''").replace(":", "\\:")
        f_path = f"C\\:/Windows/Fonts/{cap['font']}"
        # 4K 下影子和偏移量同步增大
        draw = (f"drawtext=text='{txt}':fontfile='{f_path}':fontsize={cap['size']}:"
                f"fontcolor={cap['color']}:shadowcolor=black@0.7:shadowx=5:shadowy=5:"
                f"x={cap['x_pos']}:y=h*{cap['y']}:enable='between(t,{cap['start']},{cap['end']})'")
        next_v = f"[v_txt{i}]"
        filters.append(f"{last_v}{draw}{next_v}")
        last_v = next_v

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", last_v, "-map", "1:a:0", "-c:v", "h264_nvenc", "-preset", "p4",
           "-b:v", VIDEO_BITRATE, "-maxrate", "80M", "-bufsize", "100M",
           "-c:a", "aac", "-b:a", "192k", "-shortest", PATHS["output"]]
    subprocess.run(cmd, check=True)

# ================== 4. 主流程 ==================

def main():
    # 1. 筛选逻辑
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

    # 2. 视频标准化 (核心：升级到 4K)
    std_vids = []
    print("🪄 [Step 2] 正在将原始素材标准化为 4K...")
    for i, path in enumerate(selected):
        out = os.path.join(PATHS["temp_std"], f"std_{i}.mp4")
        # 升级点：scale 和 pad 设置为 3840x2160
        vf = f"scale={UHD_WIDTH}:{UHD_HEIGHT}:force_original_aspect_ratio=decrease,pad={UHD_WIDTH}:{UHD_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps=30"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", vf, "-c:v", "h264_nvenc", "-b:v", "40M", "-an", out], check=True)
        std_vids.append(out)

    # 3. 拼接 (保持 NVENC 导出)
    clips = [VideoFileClip(p) for p in std_vids]
    final_v = concatenate_videoclips(clips, method="chain").subclipped(0, TARGET_DURATION)
    # 导出 temp_video 也要用 4K 码率
    final_v.write_videofile(PATHS["temp_video"], fps=FPS, audio=False, logger=None, 
                            ffmpeg_params=["-c:v", "h264_nvenc", "-b:v", VIDEO_BITRATE])
    for c in clips: c.close()

    # 4. 音频处理与合成
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
    print(f"✨ 4K 任务完成！输出路径: {PATHS['output']}")

if __name__ == "__main__":
    main()