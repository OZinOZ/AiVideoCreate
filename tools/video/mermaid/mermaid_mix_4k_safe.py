"""
Mermaid Video Generator V16.1 - ULTIMATE UNATTENDED PRODUCTION BUILD
-------------------------------------------------------------------
System Architecture: 
1. Checkpoint State Machine (Resumable)
2. Asymmetric "Dirty Data" Color Jitter (Anti-Fingerprint)
3. Hardened FFmpeg Text Escaping (Zero-Crash)
4. Hybrid LLM/Local Fallback Captions
"""

import os
import random
import json
import subprocess
import re
import sys
import time
import warnings

# --- 环境兼容性与依赖检查 ---
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")

try:
    from moviepy import VideoFileClip, concatenate_videoclips
    from pydub import AudioSegment
    from openai import OpenAI
except ImportError as err:
    print(f"❌ 运行环境缺失，请执行: pip install moviepy pydub openai")
    sys.exit(1)

# ================== 1. 核心配置 ==================
VERSION = "16.1"
CONFIG = {
    "BASE_DIR": r"H:\OliverAI\resources\mermaid-0202",
    "CATEGORIES": ["1_fish", "2_turtle", "3_coral"],
    "TARGET_DURATION": 90 * 60,
    "FPS": 60,
    "VIDEO_BITRATE": "55M",
    "AUDIO_BITRATE": "320k",
    "TARGET_LUFS": -14.0,
    "LLM_MODEL": "gpt-4o-mini",
    "FONT_FILE": "C\\:/Windows/Fonts/arial.ttf",
    "JITTER_RANGE": (180, 360), # 字幕间隔扰动
    "LOCAL_CAPTIONS": [
        "Glittering bioluminescence in the abyss", 
        "Echoes of the ancient tides",
        "The siren's midnight sanctuary", 
        "Azure dreams under the surface",
        "Celestial currents meeting the deep", 
        "Emerald veils of the coral queen"
    ]
}

class PathManager:
    def __init__(self, base):
        self.base = base
        self.music = os.path.join(base, "music")
        self.bg = os.path.join(base, "background")
        self.mermaid = os.path.join(base, "mermaid_assets")
        self.branding = os.path.join(base, "branding")
        self.temp_std = os.path.join(base, "temp_standardized")
        self.temp_video = os.path.join(base, "temp_video.mp4")
        self.temp_audio_raw = os.path.join(base, "temp_audio_raw.wav")
        self.temp_audio_mastered = os.path.join(base, "temp_audio_mastered.mp3")
        self.overlay_json = os.path.join(base, "overlay_plan.json")
        self.output = os.path.join(base, f"FINAL_MASTER_V{VERSION}.mp4")
        self.checkpoints = os.path.join(base, "task_state.json")

PATHS = PathManager(CONFIG["BASE_DIR"])

# 确保基础目录存在
for p in [PATHS.temp_std, PATHS.branding]:
    os.makedirs(p, exist_ok=True)

# ================== 2. 工程级底层工具 ==================

def ffmpeg_safe_text(s):
    """极致转义：处理所有可能导致 FFmpeg 崩溃的非法字符"""
    if not s: return ""
    return (s.replace("\\", "\\\\")
             .replace("'", "\\'")
             .replace(":", "\\:")
             .replace("%", "\\%")
             .replace(",", "\\,")
             .replace("\n", " ")
             .replace("[", "\\[")
             .replace("]", "\\]"))

def run_cmd(cmd):
    """带实时错误流捕获的执行器"""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ FFmpeg Error: {res.stderr}")
        return False
    return True

def get_video_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=False)
    try:
        return float(res.stdout.strip())
    except:
        return 0.0

# ================== 3. 核心业务模块 ==================

def master_audio_engine(input_wav, output_mp3):
    print(f"🎧 [Step 4] 执行高级音效增强与动态压缩...")
    af_chain = [
        "rubberband=pitch=1.005:atempo=1.005",
        "crystalizer=i=2.0",
        "compand=0.3|0.3:60/-900/-900/-70/-70/0/-31/21/0:0.01:1:0",
        "stereowiden=level_in=1:level_out=1:crossfeed=0.3:drymix=0.8",
        f"loudnorm=I={CONFIG['TARGET_LUFS']}:TP=-1.5:LRA=11",
        "aformat=sample_fmts=s16:sample_rates=44100"
    ]
    cmd = ["ffmpeg", "-y", "-i", input_wav, "-af", ",".join(af_chain), "-c:a", "libmp3lame", "-b:a", CONFIG["AUDIO_BITRATE"], output_mp3]
    run_cmd(cmd)

def generate_overlay_plan(total_duration):
    print("📝 [Step 5] 生成非线性反指纹特效计划...")
    captions = []
    if os.environ.get("OPENAI_API_KEY"):
        try:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            resp = client.chat.completions.create(
                model=CONFIG["LLM_MODEL"],
                messages=[{"role": "user", "content": "Generate 60 unique short poetic ocean captions. JSON array of strings only."}]
            )
            raw_json = re.sub(r"```(json)?|```", "", resp.choices[0].message.content).strip()
            captions = json.loads(raw_json)
        except Exception as e:
            print(f"⚠️ LLM 掉线 ({e})，启用本地备用池。")
    
    # 物理去重与补齐
    captions = list(dict.fromkeys(captions))
    if len(captions) < 40:
        captions.extend(random.sample(CONFIG["LOCAL_CAPTIONS"] * 10, 60 - len(captions)))

    plan = {"mermaid": {"segments": []}, "captions": [], "subscribe": []}
    
    # 1. 订阅提醒：非线性抖动，反平台算法识别
    cursor = 600
    while cursor < total_duration - 400:
        plan["subscribe"].append({"start": cursor, "end": cursor + 12})
        cursor += random.randint(800, 1400)

    # 2. 美人鱼 WebM 随机计划
    m_cursor = 120
    while m_cursor + 15 < total_duration:
        plan["mermaid"]["segments"].append({"start": m_cursor, "end": m_cursor + 8})
        m_cursor += random.randint(500, 1000)

    # 3. 动态字幕：加入 Jitter 间隔与位置随机化
    c_cursor = 45
    for text in captions:
        if c_cursor + 20 > total_duration: break
        plan["captions"].append({
            "start": c_cursor, "end": c_cursor + 9, 
            "text": ffmpeg_safe_text(text),
            "size": random.randint(95, 115),
            "y": random.uniform(0.82, 0.86)
        })
        c_cursor += random.randint(CONFIG["JITTER_RANGE"][0], CONFIG["JITTER_RANGE"][1])

    with open(PATHS.overlay_json, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

def final_fusion_engine():
    print(f"🔥 [Step 6] 启动终极融合渲染 (人类脏数据扰动模式)...")
    with open(PATHS.overlay_json, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    inputs = ["-i", PATHS.temp_video, "-i", PATHS.temp_audio_mastered]
    
    # --- 非对称色温扰动 (反指纹核心) ---
    def get_dirty_adj():
        return random.choice([random.uniform(0.97, 0.99), random.uniform(1.01, 1.03)])
    
    rs, gs, bs = get_dirty_adj(), get_dirty_adj(), get_dirty_adj()
    filters = [f"[0:v]colorbalance=rs={rs}:gs={gs}:bs={bs}[base]"]
    last_v = "[base]"

    # 美人鱼资源动态加载
    m_assets = [os.path.join(PATHS.mermaid, f) for f in os.listdir(PATHS.mermaid) if f.endswith(".webm")]
    if m_assets:
        inputs += ["-stream_loop", "-1", "-i", random.choice(m_assets)]
        m_en = "+".join([f"between(t,{s['start']},{s['end']})" for s in cfg["mermaid"]["segments"]])
        filters.append(f"[{len(inputs)-1}:v]scale=iw*0.2:-1[m_v]")
        filters.append(f"{last_v}[m_v]overlay=x=150:y=h-h*0.28:enable='{m_en}'[v_m]")
        last_v = "[v_m]"

    # 订阅按钮 (非对称抖动)
    sub_img = os.path.join(PATHS.branding, "subscribe.png")
    if os.path.exists(sub_img):
        inputs += ["-i", sub_img]
        sub_en = "+".join([f"between(t,{s['start']},{s['end']})" for s in cfg["subscribe"]])
        x_off = random.randint(460, 510)
        filters.append(f"[{len(inputs)-1}:v]scale=400:-1[sub_v]")
        filters.append(f"{last_v}[sub_v]overlay=x=w-{x_off}:y=120:enable='{sub_en}'[v_s]")
        last_v = "[v_s]"

    # 链式字幕渲染
    for i, cap in enumerate(cfg["captions"]):
        opacity = random.uniform(0.78, 0.88)
        draw = (f"drawtext=text='{cap['text']}':fontfile='{CONFIG['FONT_FILE']}':fontsize={cap['size']}:"
                f"fontcolor=white@{opacity}:shadowcolor=black@0.6:shadowx=3:shadowy=3:"
                f"x=(w-text_w)/2:y=h*{cap['y']}:enable='between(t,{cap['start']},{cap['end']})'")
        next_v = f"[v_txt{i}]"
        filters.append(f"{last_v}{draw}{next_v}")
        last_v = next_v

    # GPU 硬件加速命令
    cmd = [
        "ffmpeg", "-y", "-hwaccel", "cuda", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", last_v, "-map", "1:a:0",
        "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr_hq", 
        "-b:v", CONFIG["VIDEO_BITRATE"], "-maxrate", "80M", "-bufsize", "120M",
        "-c:a", "copy", "-shortest", PATHS.output
    ]
    run_cmd(cmd)

# ================== 4. 断点续传主流程控制 ==================

def main():
    state = {"step": 0, "selected_files": [], "std_list": []}
    if os.path.exists(PATHS.checkpoints):
        with open(PATHS.checkpoints, "r") as f: state = json.load(f)

    # Step 1: 素材筛选
    if state["step"] < 1:
        print("🪄 [Step 1] 筛选 90 分钟优质素材...")
        selected, total_dur = [], 0
        for cat in CONFIG["CATEGORIES"]:
            cat_p = os.path.join(CONFIG["BASE_DIR"], cat)
            if not os.path.exists(cat_p): continue
            files = [os.path.join(cat_p, f) for f in os.listdir(cat_p) if f.endswith(".mp4")]
            random.shuffle(files)
            for vid in files:
                if total_dur >= CONFIG["TARGET_DURATION"]: break
                d = get_video_duration(vid)
                if d > 0:
                    total_dur += d
                    selected.append(vid)
        state["selected_files"] = selected
        state["step"] = 1
        with open(PATHS.checkpoints, "w") as f: json.dump(state, f)

    # Step 2: GPU 标准化
    if state["step"] < 2:
        print(f"⚙️ [Step 2] 正在标准化至 4K 60FPS...")
        std_list = []
        for i, path in enumerate(state["selected_files"]):
            out = os.path.join(PATHS.temp_std, f"std_{i}.mp4")
            if "UHD_60FPS" in path: 
                std_list.append(path)
                continue
            if not os.path.exists(out):
                vf = f"scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2,fps={CONFIG['FPS']}"
                run_cmd(["ffmpeg", "-y", "-hwaccel", "cuda", "-i", path, "-vf", vf, "-c:v", "h264_nvenc", "-an", out])
            std_list.append(out)
        state["std_list"] = std_list
        state["step"] = 2
        with open(PATHS.checkpoints, "w") as f: json.dump(state, f)

    # Step 3: 拼接
    if state["step"] < 3:
        print("🔗 [Step 3] 拼接 4K 主轴...")
        clips = [VideoFileClip(p) for p in state["std_list"]]
        final_v = concatenate_videoclips(clips, method="chain").subclipped(0, CONFIG["TARGET_DURATION"])
        final_v.write_videofile(PATHS.temp_video, fps=CONFIG["FPS"], audio=False, logger=None, 
                                ffmpeg_params=["-c:v", "h264_nvenc", "-b:v", CONFIG["VIDEO_BITRATE"]])
        for c in clips: c.close()
        state["step"] = 3
        with open(PATHS.checkpoints, "w") as f: json.dump(state, f)

    # Step 4: 音频混缩
    if state["step"] < 4:
        print("🎵 [Step 4] 音频流生产与 Master 处理...")
        m_files = [os.path.join(PATHS.music, f) for f in os.listdir(PATHS.music) if f.endswith((".mp3", ".wav"))]
        b_files = [os.path.join(PATHS.bg, f) for f in os.listdir(PATHS.bg) if f.endswith((".mp3", ".wav"))]
        
        music = AudioSegment.from_file(random.choice(m_files))
        while len(music) < CONFIG["TARGET_DURATION"] * 1000:
            music += AudioSegment.from_file(random.choice(m_files))
        
        ambient = AudioSegment.from_file(random.choice(b_files))
        mixed = music.overlay(ambient, loop=True)[:CONFIG["TARGET_DURATION"] * 1000]
        mixed.export(PATHS.temp_audio_raw, format="wav")
        master_audio_engine(PATHS.temp_audio_raw, PATHS.temp_audio_mastered)
        state["step"] = 4
        with open(PATHS.checkpoints, "w") as f: json.dump(state, f)

    # Step 5: 最终融合
    if state["step"] < 5:
        generate_overlay_plan(CONFIG["TARGET_DURATION"])
        final_fusion_engine()
        state["step"] = 5
        with open(PATHS.checkpoints, "w") as f: json.dump(state, f)

    print(f"\n✅ [任务大成功] 4K 成品已生成: {PATHS.output}")
    if os.path.exists(PATHS.checkpoints): os.remove(PATHS.checkpoints)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[用户中断] 进度已保存。")
    except Exception as e:
        print(f"\n[崩溃日志]: {e}")