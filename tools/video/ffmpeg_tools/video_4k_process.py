import os
import subprocess
import random
from moviepy.video.io.VideoFileClip import VideoFileClip
FONT_PATH = "C:/Windows/Fonts/arial.ttf"  # 避免 Fontconfig 错误

# ================== 基础配置 ==================

INPUT_DIR  = r"Z:\sunset"      # 你放原始素材的目录
OUTPUT_DIR = r"I:\MyVideo\seadrone_4K\04_sunset"   # 输出目录

UHD_W, UHD_H = 3840, 2160
TARGET_FPS = 60

BITRATE  = "55M"
MAXRATE  = "75M"
BUFSIZE  = "110M"

# 画面统一风格（与你现有素材接近）
SATURATION = 1.18
CONTRAST   = 1.08
ENABLE_VIGNETTE = False   # 建议关，后期统一加更可控

# ================== 水印配置 ==================

WATERMARK_ONLY = False   # True = 只加水印；False = 全流程 + 水印
WATERMARK_TEXT = "© Tank&Tail Talk"
FONT_PATH = "C:/Windows/Fonts/arial.ttf"  # 避免 Fontconfig 错误


# ================== FFmpeg 处理函数 ==================

def process_video(input_path, output_path):
    with VideoFileClip(input_path) as clip:
        w, h = clip.size

    vf_chain = []

    if not WATERMARK_ONLY:
        # --- 分辨率：强制 4K，不拉伸 ---
        vf_chain.append(
            f"scale={UHD_W}:{UHD_H}:force_original_aspect_ratio=decrease"
        )
        vf_chain.append(
            f"pad={UHD_W}:{UHD_H}:(ow-iw)/2:(oh-ih)/2"
        )

        # 原始非 4K 才轻度锐化
        if w < UHD_W:
            vf_chain.append("unsharp=3:3:0.4")

        # --- 帧率 ---
        vf_chain.append(f"fps={TARGET_FPS}")

        # --- 色彩 ---
        vf_chain.append(
            f"eq=saturation={SATURATION}:contrast={CONTRAST}"
        )

        if ENABLE_VIGNETTE:
            vf_chain.append("vignette=PI/4")

    # ================== 水印（始终执行） ==================
    drawtext = f"drawtext=text='{WATERMARK_TEXT}':fontfile='{FONT_PATH}':fontsize=48:fontcolor=white@0.5:x=w-tw-40:y=h-th-40"
    vf_chain.append(drawtext)

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-hwaccel", "cuda",
        "-i", input_path,
        "-vf", ",".join(vf_chain),
        "-c:v", "h264_nvenc",
        "-preset", "p5",
        "-rc", "vbr_hq",
        "-b:v", BITRATE,
        "-maxrate", MAXRATE,
        "-bufsize", BUFSIZE,
        "-profile:v", "high",
        "-level", "5.2",
        "-pix_fmt", "yuv420p",
        "-an",
        "-map_metadata", "-1",
        output_path
    ]

    subprocess.run(cmd, check=True)

# ================== 主流程 ==================

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = [
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith((".mp4", ".mov", ".mkv"))
    ]

    print(f"🎬 发现 {len(files)} 个视频，开始统一规格处理…")

    for idx, filename in enumerate(files, 1):
        in_path  = os.path.join(INPUT_DIR, filename)
        out_path = os.path.join(
            OUTPUT_DIR,
            f"UHD60_{os.path.splitext(filename)[0]}.mp4"
        )

        if os.path.exists(out_path):
            print(f"⏩ 跳过已存在: {filename}")
            continue

        try:
            print(f"⚙️ [{idx}/{len(files)}] 处理: {filename}")
            process_video(in_path, out_path)
            print("✅ 完成")
        except Exception as e:
            print(f"❌ 失败: {filename} | {e}")

if __name__ == "__main__":
    main()
