import os
import time
import json
import random
import subprocess
import requests
from urllib.parse import urlparse
from moviepy.video.io.VideoFileClip import VideoFileClip

# ======================================================
# =============== 全局配置 ==============================
# ======================================================

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

SEARCH_QUERY = "great barrier reef underwater"
SAVE_DIR = "H:/resources/ocean"
PROCESSED_DIR = os.path.join(SAVE_DIR, "processed")

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_RATIO = 16 / 9
RATIO_TOLERANCE = 0.05

TARGET_TOTAL_SECONDS = 90 * 60  # 90 分钟

SUBTITLE_JSON = "subtitles_90min.json"
FINAL_OUTPUT = "final_90min_subtitled.mp4"

FONT_SIZE = 42
FONT_OPACITY = 0.85
Y_POS = "h*0.75"

# ======================================================
# =============== 工具函数 ===============================
# ======================================================

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def download_pixabay_videos(query, max_pages=5, per_page=10):
    ensure_dir(SAVE_DIR)
    page = 1

    while page <= max_pages:
        print(f"[API] Pixabay page {page}")
        url = "https://pixabay.com/api/videos/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": query,
            "per_page": per_page,
            "page": page,
            "orientation": "horizontal"
        }
        r = requests.get(url, params=params)
        if r.status_code != 200:
            break

        data = r.json()
        hits = data.get("hits", [])
        if not hits:
            break

        for item in hits:
            vid = item.get("videos", {}).get("large") or item.get("videos", {}).get("medium")
            if not vid:
                continue
            url = vid["url"]
            file_id = item["id"]
            ext = os.path.splitext(urlparse(url).path)[1] or ".mp4"
            out = os.path.join(SAVE_DIR, f"pixabay_{file_id}{ext}")
            if os.path.exists(out):
                continue

            print(f"[下载] {out}")
            with requests.get(url, stream=True, timeout=30) as resp:
                with open(out, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
        page += 1
        time.sleep(10)

def process_video(input_path, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda",
        "-i", input_path,
        "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}",
        "-an",                      # 🚨 永久去音频
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-b:v", "8M",
        output_path
    ]
    subprocess.run(cmd, check=True)

def preprocess_all_videos():
    ensure_dir(PROCESSED_DIR)
    for f in os.listdir(SAVE_DIR):
        if not f.endswith(".mp4"):
            continue
        in_path = os.path.join(SAVE_DIR, f)
        out_path = os.path.join(PROCESSED_DIR, f)
        if os.path.exists(out_path):
            continue

        try:
            clip = VideoFileClip(in_path)
            w, h = clip.size
            ratio = w / h
            clip.close()

            if abs(ratio - TARGET_RATIO) > RATIO_TOLERANCE:
                print(f"[跳过比例] {f}")
                continue

            print(f"[处理] {f}")
            process_video(in_path, out_path)
        except Exception as e:
            print(f"[异常] {f} {e}")

def build_concat_video():
    files = [os.path.join(PROCESSED_DIR, f) for f in os.listdir(PROCESSED_DIR) if f.endswith(".mp4")]
    random.shuffle(files)

    total = 0
    selected = []

    for f in files:
        clip = VideoFileClip(f)
        dur = clip.duration
        clip.close()

        selected.append(f)
        total += dur
        if total >= TARGET_TOTAL_SECONDS:
            break

    with open("concat.txt", "w", encoding="utf-8") as f:
        for v in selected:
            f.write(f"file '{v}'\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "concat.txt",
        "-c", "copy",
        "temp_90min.mp4"
    ], check=True)

def burn_subtitles():
    with open(SUBTITLE_JSON, "r", encoding="utf-8") as f:
        subs = json.load(f)

    filters = []
    for s in subs:
        start = s["time"]
        end = start + 4
        text = s["text"].replace("'", "\\'")
        filters.append(
            f"drawtext=text='{text}':"
            f"fontsize={FONT_SIZE}:"
            f"fontcolor=white@{FONT_OPACITY}:"
            f"x=(w-text_w)/2:y={Y_POS}:"
            f"enable='between(t,{start},{end})'"
        )

    vf = ",".join(filters)

    subprocess.run([
        "ffmpeg", "-y",
        "-i", "temp_90min.mp4",
        "-vf", vf,
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-b:v", "8M",
        "-an",
        FINAL_OUTPUT
    ], check=True)

# ======================================================
# =============== 主入口 ================================
# ======================================================

if __name__ == "__main__":
    print("🌊 Overnight Ocean Video Builder 启动")

    download_pixabay_videos(SEARCH_QUERY)
    preprocess_all_videos()
    build_concat_video()
    burn_subtitles()

    print("✅ 完成：带字幕的 90 分钟视频已生成")
