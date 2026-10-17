"""
Mermaid Video Generator V16.25 - ANTI-DETECTION SEMANTIC ENGINE
---------------------------------------------------------------
- Fix: [CRITICAL] Re-encoding concat with setpts to ensure 100% timeline continuity.
- Fix: [CRITICAL] Deep suppression of ambient audio (-24dB) to prevent music overlap.
- Fix: [CRITICAL] Fixed "Invalid file index" by locking Subscribe to index [3:v].
- Fix: [CRITICAL] Replaced MoviePy concat with FFmpeg Demuxer for 100% stability.
- Protocol: 100% Logic preservation, NO other changes.
"""

import os
import random
import json
import subprocess
import re
import warnings
import sys
import hashlib
import traceback

# --- 抑制环境杂音 ---
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")

try:
    from moviepy import VideoFileClip, concatenate_videoclips
    from pydub import AudioSegment
    from openai import OpenAI
    from tqdm import tqdm
except ImportError as err:
    print(f"❌ 运行环境缺失，请执行: pip install moviepy pydub openai tqdm")
    sys.exit(1)

# ================== 1. 核心配置 ==================
VERSION = "16.25"
CONFIG = {
    "BASE_DIR": r"I:\MyVideo\seadrone_4K",
    "CATEGORIES": ["1_rock", "2_sand", "3_wave"],
    "TARGET_DURATION": 120 * 60,
    "FPS": 60,
    "VIDEO_BITRATE": "55M",
    "AUDIO_BITRATE": "320k",
    "TARGET_LUFS": -14.0,
    "AMBIENT_VOLUME_DB": -24  # 环境音量压制分贝数 (建议 -18 到 -30)
}

# 静态语义加扰池
BACKUP_CAPTIONS = [
    "The ocean remembers what the wind forgets.", "Echoes of a sunken heart.", "Blue is the loneliest color beneath the tide.",
    "Tracing shadows in the cold abyss.", "A silent requiem for the waves.", "Drowning in the beauty of silence.",
    "The salt remains after the joy is gone.", "Cold currents, colder memories.", "Solitude has the taste of brine.",
    "Where the light dies, the dream begins.",
    "Every wave is a new beginning.", "Chasing the dawn across the endless blue.", "The sun shall rise from the liquid horizon.",
    "Infinite power in a single drop.", "Behold the majesty of the rising tide.", "Golden paths written on the water.",
    "The soul breathes with the surging sea.", "Unbound, unchained, everlasting ocean.", "Strength born from the depths.",
    "The horizon is not the end, but a promise.",
    "Sparkling ripples of pure joy.", "Crystal laughter in the sea spray.", "Turquoise dreams and sun-kissed foam.",
    "The tide brings gifts of shells and light.", "Dancing on the edge of the world.", "Emerald whispers of a gentle sea.",
    "A symphony of bubbles and light.", "Serenity found in every grain of sand.", "Soft as the mist, bright as the spray.",
    "Let the ocean wash away the noise.",
    "Ocean's lullaby for a restless world.", "Gravity's love song to the shore.", "Sailing through liquid starlight.",
    "The reef's secret garden.", "Nature's masterpiece in every ripple.", "Salty skin, golden soul.",
    "Lost in the velvet embrace of the deep.", "The pulse of the planet in every wave.", "Azure poetry in motion.",
    "Where peace flows deeper than the abyss."
] * 2

STYLE_POOL = {
    "fonts": ["arial.ttf", "calibri.ttf", "georgia.ttf", "segoeui.ttf"],
    "sizes": [90, 100, 110], 
    "colors": ["white", "0xFFE4B5", "0x00FFFF", "0xFFD700"],
    "y_offsets": [0.82, 0.85, 0.88],
    "x_aligns": ["(w-text_w)/2", "(w-text_w)/3", "(w-text_w)*2/3"]
}

PATHS = {k: os.path.join(CONFIG["BASE_DIR"], v) for k, v in {
    "music": "music", "bg": "background", "mermaid": "mermaid_assets",
    "branding": "branding", "temp_std": "temp_standardized",
    "temp_video": "temp_video.mp4", "temp_audio_raw": "temp_audio_raw.wav",
    "temp_audio_mastered": "temp_audio_mastered.mp3", "overlay_json": "overlay_plan.json",
    "concat_list": "concat_list.txt"
}.items()}
PATHS["output"] = os.path.join(CONFIG["BASE_DIR"], f"FINAL_MASTER_V{VERSION}.mp4")

for p in [PATHS["temp_std"], PATHS["branding"]]:
    os.makedirs(p, exist_ok=True)

# ================== 2. 审计与工具 ==================

def get_video_duration(path):
    """
    获取视频文件的时长（秒）。
    
    Args:
        path (str): 视频文件的路径。
        
    Returns:
        float: 视频时长（秒），如果获取失败则返回 0.0。
    """
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=False)
        return float(res.stdout.strip()) if res.stdout else 0.0
    except: return 0.0

def check_is_perfect_match(path):
    """
    检查视频是否完美符合目标规格（4K, 60FPS, 码率），以决定是否跳过重编码。
    
    Args:
        path (str): 视频文件的路径。
        
    Returns:
        bool: 如果完全匹配返回 True，否则返回 False。
    """
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        v_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
        num_s, den_s = v_stream.get("r_frame_rate", "0/1").split("/")
        fps = float(num_s) / float(den_s) if float(den_s) != 0 else 0
        bit_rate = int(data["format"].get("bit_rate", 0))
        return all([
            v_stream.get("width") == 3840, v_stream.get("height") == 2160,
            abs(fps - 60.0) < 0.1, (55 * 1000 * 1000 * 0.9) < bit_rate < (55 * 1000 * 1000 * 1.2)
        ])
    except: return False

def master_audio_engine(input_wav, output_mp3):
    """
    使用 FFmpeg 滤镜链对音频进行母带级处理（甚至响度标准化、立体声增强等）。
    
    Args:
        input_wav (str): 输入 WAV 音频文件路径。
        output_mp3 (str): 输出 MP3 音频文件路径。
    """
    print(f"🎧 [Audio Master] 执行大师级音效增强...")
    af_chain = [
        "crystalizer=i=2.0",
        "stereowiden=delay=20:feedback=0.25:crossfeed=0.3:drymix=0.8",
        f"loudnorm=I={CONFIG['TARGET_LUFS']}:TP=-1.5:LRA=11",
        "aformat=sample_fmts=s16:sample_rates=44100"
    ]
    cmd = ["ffmpeg", "-y", "-i", input_wav, "-af", ",".join(af_chain), 
            "-c:a", "libmp3lame", "-b:a", CONFIG["AUDIO_BITRATE"], output_mp3]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def validate_video_integrity(path):
    """
    自检：验证视频文件完整性 (Stream, Duration, FPS)。
    防止 Windows/USB 坏文件导致 FFmpeg 级联报错。
    """
    try:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,duration", "-of", "json", path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        
        if not data.get("streams"): return False
        stream = data["streams"][0]
        
        # Check FPS != 0/0
        if stream.get("r_frame_rate") == "0/0": return False
        
        # Check Duration > 0
        dur = float(stream.get("duration", 0))
        if dur <= 0: return False
        
        return True
    except:
        return False

# ================== 4. 业务逻辑 (反检测语义混合) ==================
def generate_overlay_plan(total_duration):
    """
    生成包含字幕、美人鱼特效和订阅水印的叠加计划，支持 GPT 生成的多样化意境字幕。
    
    Args:
        total_duration (float): 视频总时长（秒）。
    """
    print("📝 [Step 5] 执行多意境语义生成 (Model: gpt-4o-mini)...")
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    mixed_captions = []
    intent_prompts = [
        "melancholy and deep poetic ocean captions",
        "hopeful and majestic ocean captions",
        "healing and whimsical ocean captions"
    ]
    
    try:
        for intent in intent_prompts:
            prompt = f"""
Generate 20 short, calm, {intent} for deep ocean relaxation videos.
Rules:
- Length: 6 to 12 words
- NO punctuation at the end
- Style: Calm, emotional, cinematic
- NO emojis
- Output format: Return ONLY a raw JSON array of strings
"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" if False else "text" }, 
                timeout=15
            )
            content = re.sub(r"```(json)?|```", "", resp.choices[0].message.content).strip()
            mixed_captions.extend(json.loads(content))
        
        random.shuffle(mixed_captions)
        print(f"✅ 成功物理对齐 {len(mixed_captions)} 条多意境字幕。")
    except Exception as e:
        print(f"⚠️ OpenAI 调用或解析失败: {str(e)}")
        mixed_captions = BACKUP_CAPTIONS
        random.shuffle(mixed_captions)
    
    plan = {"mermaid": {"segments": []}, "captions": [], "subscribe": []}
    sub_cursor = 300 + random.randint(-5, 5)
    while sub_cursor < total_duration:
        plan["subscribe"].append({"start": sub_cursor, "end": sub_cursor + 10})
        sub_cursor += 900 + random.randint(-5, 5)

    m_cursor = 60
    while m_cursor + 6 < total_duration:
        plan["mermaid"]["segments"].append({"start": m_cursor, "end": m_cursor + 6})
        m_cursor += random.randint(500, 900)

    cursor = 30
    for text in mixed_captions:
        if cursor + 20 > total_duration: break
        plan["captions"].append({
            "start": cursor, "end": cursor + 8, "text": text,
            "font": random.choice(STYLE_POOL["fonts"]),
            "size": random.choice(STYLE_POOL["sizes"]),
            "color": random.choice(STYLE_POOL["colors"]),
            "y": random.choice(STYLE_POOL["y_offsets"]),
            "x_pos": random.choice(STYLE_POOL["x_aligns"])
        })
        cursor += random.randint(150, 250)
    with open(PATHS["overlay_json"], "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

def final_fusion():
    """
    执行最终的视频渲染，将处理好的视频流、音频流和 overlay 计划合并导出。
    
    Reads:
        PATHS["overlay_json"]: 读取覆盖层计划。
        PATHS["temp_video"]: 读取临时视频文件。
        PATHS["temp_audio_mastered"]: 读取母带处理后的音频。
        
    Writes:
        PATHS["output"]: 输出最终合成的视频文件。
    """
    print(f"🔥 [Step 6] 启动最终融合渲染 (物理索引锁定版)...")
    with open(PATHS["overlay_json"], "r", encoding="utf-8") as f: cfg = json.load(f)
    m_assets = [os.path.join(PATHS["mermaid"], f) for f in os.listdir(PATHS["mermaid"]) if f.endswith(".webm")]
    sub_img = os.path.join(PATHS["branding"], "subscribe.png")
    
    inputs = ["-i", PATHS["temp_video"], "-i", PATHS["temp_audio_mastered"]]
    filters = ["[0:v]setpts=PTS-STARTPTS[base]"]
    last_v = "[base]"

    if m_assets:
        inputs += ["-stream_loop", "-1", "-c:v", "libvpx-vp9", "-i", random.choice(m_assets)] 
        m_en = "+".join([f"between(t,{s['start']},{s['end']})" for s in cfg["mermaid"]["segments"]])
        filters.append(f"[2:v]scale=iw*0.2:-1[m_v]")
        filters.append(f"{last_v}[m_v]overlay=x=120:y=h-h*0.25:enable='{m_en}'[v1]"); last_v = "[v1]"

    if os.path.exists(sub_img) and cfg.get("subscribe"):
        inputs += ["-i", sub_img]
        sub_en = "+".join([f"between(t,{s['start']},{s['end']})" for s in cfg["subscribe"]])
        filters.append("[3:v]scale=220:-1[sub_v]")
        filters.append(f"{last_v}[sub_v]overlay=x=W-w-100:y=100:enable='{sub_en}'[v2]")
        last_v = "[v2]"

    for i, cap in enumerate(cfg["captions"]):
        txt = cap["text"].replace("'", "'\\\\\\''").replace(":", "\\:").replace(",", "\\,")
        font_p = f"C\\:/Windows/Fonts/{cap['font']}"
        draw = (f"drawtext=text='{txt}':fontfile='{font_p}':fontsize={cap['size']}:"
                f"fontcolor={cap['color']}@0.8:shadowcolor=black@0.6:shadowx=4:shadowy=4:x={cap['x_pos']}:y=h*{cap['y']}:"
                f"enable='between(t,{cap['start']},{cap['end']})'")
        next_v = f"[v_txt{i}]"; filters.append(f"{last_v}{draw}{next_v}"); last_v = next_v

    cmd = ["ffmpeg", "-y", "-hwaccel", "cuda", *inputs, "-filter_complex", ";".join(filters), 
            "-map", last_v, "-map", "1:a:0", "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr_hq", 
            "-b:v", CONFIG["VIDEO_BITRATE"], "-maxrate", "75M", "-bufsize", "110M", "-c:a", "copy", "-shortest", PATHS["output"]]
    subprocess.run(cmd, check=True)

# ================== 5. 主流程 ==================

def step1_select_materials():
    """
    步骤 1: 根据配置类别选择视频素材，直到达到目标时长。
    
    Returns:
        list: 选中的视频文件路径列表。
    """
    selected, current_dur = [], 0
    for cat in CONFIG["CATEGORIES"]:
        if current_dur >= CONFIG["TARGET_DURATION"]: break
        intro_p = os.path.join(CONFIG["BASE_DIR"], "intro", f"{cat}.mp4")
        if os.path.exists(intro_p):
            selected.append(intro_p); current_dur += get_video_duration(intro_p)
        cat_p = os.path.join(CONFIG["BASE_DIR"], cat)
        if not os.path.exists(cat_p): continue
        vids = [os.path.join(cat_p, f) for f in os.listdir(cat_p) if f.endswith(".mp4")]
        random.shuffle(vids)
        for vid in vids:
            if current_dur >= CONFIG["TARGET_DURATION"]: break
            current_dur += get_video_duration(vid); selected.append(vid)
    return selected

def step2_standardize_videos(selected):
    """
    步骤 2: 将选中的视频标准化为 4K 60FPS。
    如果视频已符合规格则跳过，否则进行转码。
    
    Args:
        selected (list): 选中的源视频路径列表。
        
    Returns:
        list: 标准化后的视频文件路径列表。
    """
    std_vids = []
    print(f"🪄 [Step 2] 正在标准化至 4K 60FPS (MD5 缓存保护)...")
    for path in tqdm(selected, desc="处理片段"):
        if check_is_perfect_match(path):
            std_vids.append(path); continue
        file_hash = hashlib.md5(path.encode()).hexdigest()[:12]
        out = os.path.join(PATHS["temp_std"], f"std_{file_hash}.mp4")
        if not os.path.exists(out):
            vf = f"scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2,fps={CONFIG['FPS']}"
            subprocess.run(["ffmpeg", "-y", "-hwaccel", "cuda", "-loglevel", "error", "-i", path, 
                            "-vf", vf, "-c:v", "h264_nvenc", "-b:v", CONFIG["VIDEO_BITRATE"], "-an", out], check=True)
        std_vids.append(out)
    return std_vids

def step3_physical_concat(std_vids):
    """
    步骤 3: 使用 FFmpeg concat 协议物理拼接视频。
    强制重编码并重置 PTS 以解决时间轴漂移问题。
    [新增] 拼接前执行视频完整性自检。
    
    Args:
        std_vids (list): 标准化后的视频路径列表。
    """
    # --- [Step 3] 物理拼接 (ChatGPT 建议：重编码强制 PTS 对齐) ---
    print("🔥 [Step 3] 执行 FFmpeg Concat (物理重编码 + PTS 对齐)...")
    
    # [新增] 完整性自检
    valid_vids = []
    print("🔍 [Self-Check] 正在执行视频完整性验证...")
    for v in std_vids:
        if validate_video_integrity(v):
            valid_vids.append(v)
        else:
            print(f"⚠️ [Skip] 发现损坏或无效视频: {os.path.basename(v)}")
    
    if not valid_vids:
        raise Exception("所有视频素材均未通过完整性自检，无法继续拼接！")
        
    if len(valid_vids) < len(std_vids):
        print(f"⚠️ [Warning] 已剔除 {len(std_vids) - len(valid_vids)} 个无效片段，剩余 {len(valid_vids)} 个。")

    with open(PATHS["concat_list"], "w", encoding="utf-8") as f:
        for p in valid_vids:
            # 物理分离路径转义逻辑，避免 f-string backslash 语法限制
            safe_p = p.replace("'", "'\\''")
            f.write(f"file '{safe_p}'\n")
    
    # MODIFIED: concat 阶段强制重编码 + setpts，解决 1h27m 漂移 Bug
    concat_cmd = [
        "ffmpeg", "-y", "-hwaccel", "cuda",
        "-f", "concat", "-safe", "0",
        "-i", PATHS["concat_list"],
        "-vf", "setpts=N/FRAME_RATE/TB",  # 关键：物理抹平时间轴间隙
        "-r", str(CONFIG["FPS"]),
        "-c:v", "h264_nvenc",
        "-b:v", CONFIG["VIDEO_BITRATE"],
        "-an", PATHS["temp_video"]
    ]
    subprocess.run(concat_cmd, check=True)

def step4_audio_mixing():
    """
    步骤 4: 混合背景音乐和环境音效。
    背景音乐自动循环，环境音效降低音量（-24dB）。
    [新增] 使用 temp_video 的真实物理时长进行音频裁剪，而非理论时长。
    最终输出到临时音频文件并进行母带处理。
    """
    print("🎵 [Step 4] 大师混音 (-24dB 背景音深度压制)...")
    
    # [新增] 获取物理拼接后的真实时长
    real_duration = get_video_duration(PATHS["temp_video"])
    if real_duration <= 0:
        print(f"⚠️ 无法获取拼接视频时长，回退至目标时长: {CONFIG['TARGET_DURATION']}s")
        target_dur = CONFIG["TARGET_DURATION"]
    else:
        print(f"⏱️ [Physical Sync] 视频物理时长: {real_duration:.2f}s (理论: {CONFIG['TARGET_DURATION']}s)")
        target_dur = real_duration

    m_f = [os.path.join(PATHS["music"], f) for f in os.listdir(PATHS["music"]) if f.endswith((".mp3", ".wav"))]
    b_f = [os.path.join(PATHS["bg"], f) for f in os.listdir(PATHS["bg"]) if f.endswith((".mp3", ".wav"))]
    
    music = AudioSegment.from_file(random.choice(m_f)).normalize() + 2
    while len(music) < target_dur * 1000: 
        music += AudioSegment.from_file(random.choice(m_f)).normalize() + 2
    
    # 使用配置的音量压制参数
    ambient_vol = CONFIG.get("AMBIENT_VOLUME_DB", -24)
    if ambient_vol > 0: ambient_vol = -ambient_vol # 确保是减去分贝
    
    ambient = AudioSegment.from_file(random.choice(b_f)) + ambient_vol
    
    mixed = music.overlay(ambient, loop=True)[:int(target_dur * 1000)]
    mixed.export(PATHS["temp_audio_raw"], format="wav")
    master_audio_engine(PATHS["temp_audio_raw"], PATHS["temp_audio_mastered"])

def main():
    """
    主程序入口：协调所有步骤执行视频生成任务。
    包含错误检查，如果任何步骤失败则立即退出。
    """
    print(f"Mermaid Video Generator V{VERSION} - ANTI-DETECTION MASTER")
    print("-" * 59)
    
    # Step 1: Select Materials
    print("\n--- Step 1: Selecting Materials ---")
    selected = step1_select_materials()
    if not selected:
        print("❌ Step 1 Failed: No valid video materials found.")
        sys.exit(1)
    print(f"✅ Step 1 Success: Identified {len(selected)} source videos.")
    
    # Step 2: Standardize
    print("\n--- Step 2: Standardizing Videos ---")
    std_vids = step2_standardize_videos(selected)
    if not std_vids:
         print("❌ Step 2 Failed: Video standardization produced no output.")
         sys.exit(1)
    print(f"✅ Step 2 Success: Prepared {len(std_vids)} standardized clips.")
    
    # Step 3: Concat
    print("\n--- Step 3: Physical Concatenation ---")
    try:
        step3_physical_concat(std_vids)
        if not os.path.exists(PATHS["temp_video"]) or os.path.getsize(PATHS["temp_video"]) == 0:
            raise Exception("Concatenated video file is missing or empty.")
        print("✅ Step 3 Success: Video concatenation completed.")
    except Exception as e:
        print(f"❌ Step 3 Failed: {str(e)}")
        sys.exit(1)
    
    # Step 4: Audio Mixing
    print("\n--- Step 4: Audio Mixing ---")
    try:
        step4_audio_mixing()
        if not os.path.exists(PATHS["temp_audio_mastered"]) or os.path.getsize(PATHS["temp_audio_mastered"]) == 0:
            raise Exception("Mastered audio file is missing or empty.")
        print("✅ Step 4 Success: Audio mixing and mastering completed.")
    except Exception as e:
        print(f"❌ Step 4 Failed: {str(e)}")
        sys.exit(1)
    
    # Step 5: Overlay Plan
    print("\n--- Step 5: Generating Overlay Plan ---")
    try:
        generate_overlay_plan(CONFIG["TARGET_DURATION"])
        if not os.path.exists(PATHS["overlay_json"]):
             raise Exception("Overlay plan JSON not generated.")
        print("✅ Step 5 Success: Overlay plan generated.")
    except Exception as e:
         print(f"❌ Step 5 Failed: {str(e)}")
         sys.exit(1)
    
    # Step 6: Final Fusion
    print("\n--- Step 6: Final Fusion Rendering ---")
    try:
        final_fusion()
        if not os.path.exists(PATHS["output"]) or os.path.getsize(PATHS["output"]) == 0:
             raise Exception("Final output video missing or empty.")
        print(f"✅ Step 6 Success: Final render completed.")
    except Exception as e:
         print(f"❌ Step 6 Failed: {str(e)}")
         sys.exit(1)
    
    print(f"\n✨ ALL STEPS COMPLETED SUCCESSFULLY! Finished Video: {PATHS['output']}")

if __name__ == "__main__":
    main()