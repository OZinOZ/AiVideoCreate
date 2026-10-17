import os
import time
import requests
import random
import subprocess
import sys
import glob
from moviepy.video.io.VideoFileClip import VideoFileClip

# ================== 1. 全局配置区域 ==================
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

# --- 新增模式开关 ---
# 1: 只下载不处理 | 2: 不下载只处理 (扫描本地raw文件) | 3: 下载+处理同步
PROCESS_MODE = 3

SOURCE = 'pixabay'
SEARCH_QUERY = "sea beach drone 4k"
SAVE_DIR = r"H:\OliverAI\resources\seadrone"

MAX_DOWNLOADS = 400   
BATCH_SIZE = 5          

# 目标规格 (4K 60FPS 旗舰配置)
UHD_W, UHD_H = 3840, 2160   
TARGET_RATIO = 16 / 9       
RATIO_TOLERANCE = 0.05      

# 画面风格参数
FILTER_SATURATION = 1.18    
FILTER_CONTRAST = 1.08      
ENABLE_VIGNETTE = True      
WATERMARK_TEXT = "© Tank&Tail Talk"
FONT_PATH = "C\\:/Windows/Fonts/arial.ttf" 

TARGET_FPS = 60             
TARGET_BITRATE = "55M"      
MAX_RATE = "75M"            
BUF_SIZE = "110M"           

MIN_DURATION = 7            
MAX_DURATION = 60           

# ================== 2. FFmpeg 处理函数 ==================

def ffmpeg_process_uhd(input_path, output_path, original_w, original_h):
    h_flip = "hflip," if random.random() > 0.5 else ""
    speed = random.uniform(0.995, 1.005)
    vf_chain = []
    vf_chain.append(f"scale={UHD_W}:{UHD_H}:force_original_aspect_ratio=decrease")
    vf_chain.append(f"pad={UHD_W}:{UHD_H}:(ow-iw)/2:(oh-ih)/2")
    
    if original_w < UHD_W:
        vf_chain.append("unsharp=3:3:0.5:3:3:0.0")

    vf_chain.append(f"{h_flip}fps={TARGET_FPS}")
    vf_chain.append(f"setpts={1/speed}*PTS")
    vf_chain.append(f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST}")
    if ENABLE_VIGNETTE:
        vf_chain.append("vignette=PI/4")
    vf_chain.append(
        f"drawtext=text='{WATERMARK_TEXT}':fontfile='{FONT_PATH}':fontcolor=white@0.4:"
        f"fontsize=48:x=w-tw-40:y=h-th-40"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-hwaccel", "cuda", "-i", input_path,
        "-vf", ",".join(vf_chain),
        "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr_hq", 
        "-b:v", TARGET_BITRATE, "-maxrate", MAX_RATE, "-bufsize", BUF_SIZE,
        "-profile:v", "high", "-level", "5.2", "-pix_fmt", "yuv420p", "-an", "-map_metadata", "-1",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except:
        print("❌ FFmpeg 压制失败")
        return False

# ================== 3. API 下载 ==================

def get_media_links(source, query, page, per_page):
    results = []
    try:
        if source == 'pexels':
            headers = {'Authorization': PEXELS_API_KEY}
            url = f"https://api.pexels.com/videos/search?query={query}&orientation=landscape&per_page={per_page}&page={page}"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                for item in res.json().get('videos', []):
                    files = sorted(item.get('video_files', []), key=lambda x: x['width']*x['height'], reverse=True)
                    if files: results.append({'id': str(item['id']), 'url': files[0]['link']})
        elif source == 'pixabay':
            url = "https://pixabay.com/api/videos/"
            params = {'key': PIXABAY_API_KEY, 'q': query, 'per_page': per_page, 'page': page, 'video_type': 'film', 'orientation': 'horizontal'}
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                for item in res.json().get('hits', []):
                    videos = item.get('videos', {})
                    vid_url = videos.get('large', {}).get('url')
                    if vid_url: results.append({'id': str(item['id']), 'url': vid_url})
    except: pass
    return results

# ================== 4. 主流程 ==================

def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    
    # --- 模式 2：只处理本地 raw 文件 ---
    if PROCESS_MODE == 2:
        print("🛠️ [Mode 2] 模式：不下载，只处理本地 raw_*.mp4 文件")
        raw_files = glob.glob(os.path.join(SAVE_DIR, "raw_*.mp4"))
        for raw_path in raw_files:
            file_id = os.path.basename(raw_path).replace("raw_", "").replace(".mp4", "")
            final_path = os.path.join(SAVE_DIR, f"{SOURCE}_UHD_60FPS_{file_id}.mp4")
            
            if os.path.exists(final_path):
                print(f"⏭️ 跳过已存在: {final_path}"); continue
                
            print(f"\n🎬 正在处理本地素材: {file_id}")
            try:
                with VideoFileClip(raw_path) as clip:
                    w, h = clip.size
                if ffmpeg_process_uhd(raw_path, final_path, w, h):
                    print(f"✅ 处理成功: {final_path}")
                    os.remove(raw_path) # 处理完删除原始文件
            except Exception as e:
                print(f"❌ 处理失败 {file_id}: {e}")
        return

    # --- 模式 1 & 3：涉及下载逻辑 ---
    total_downloaded = 0
    page = 1
    processed_ids = set()
    print(f"🌊 [Mission] 模式: {PROCESS_MODE} | 目标: {MAX_DOWNLOADS} 个素材")

    while total_downloaded < MAX_DOWNLOADS:
        links = get_media_links(SOURCE, SEARCH_QUERY, page, BATCH_SIZE)
        if not links: break

        for item in links:
            if total_downloaded >= MAX_DOWNLOADS: break
            raw = os.path.join(SAVE_DIR, f"raw_{item['id']}.mp4")
            final = os.path.join(SAVE_DIR, f"{SOURCE}_UHD_60FPS_{item['id']}.mp4")

            if os.path.exists(final) or (PROCESS_MODE == 1 and os.path.exists(raw)):
                print(f"⏭️ 跳过已存在: {item['id']}"); total_downloaded += 1; continue

            try:
                print(f"\n📥 正在下载 ID: {item['id']}")
                r = requests.get(item['url'], stream=True, timeout=30)
                if r.status_code == 200:
                    with open(raw, 'wb') as f:
                        total_length = r.headers.get('content-length')
                        if total_length:
                            total_length = int(total_length)
                            dl = 0
                            for chunk in r.iter_content(chunk_size=1024*1024):
                                if chunk:
                                    dl += len(chunk)
                                    f.write(chunk)
                                    done = int(50 * dl / total_length)
                                    sys.stdout.write(f"\r[{'=' * done}{' ' * (50-done)}] {dl/1024/1024:.2f} MB")
                                    sys.stdout.flush()
                        else:
                            for chunk in r.iter_content(chunk_size=1024*1024):
                                if chunk: f.write(chunk)
                
                # --- 下载后的逻辑分流 ---
                if PROCESS_MODE == 1:
                    print(f"\n✅ 下载完成，跳过处理模式。")
                    total_downloaded += 1
                    continue

                # --- 模式 3：同步处理 ---
                with VideoFileClip(raw) as clip:
                    w, h, dur = clip.size[0], clip.size[1], clip.duration
                
                ratio_val = w / h
                if not (MIN_DURATION <= dur <= MAX_DURATION) or abs(ratio_val - TARGET_RATIO) >= RATIO_TOLERANCE:
                    print(f"\n❌ 规格不符，已丢弃原始文件")
                    os.remove(raw)
                else:
                    if ffmpeg_process_uhd(raw, final, w, h):
                        total_downloaded += 1
                        print(f"\n✅ 处理成功 [{total_downloaded}/{MAX_DOWNLOADS}]")
                        os.remove(raw)
            except Exception as e:
                print(f"\n❌ 出错: {e}")
                if os.path.exists(raw): os.remove(raw)

        page += 1
        time.sleep(1)

if __name__ == "__main__":
    main()