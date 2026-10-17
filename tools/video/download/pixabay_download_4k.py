import os
import time
import requests
import random
import subprocess
from urllib.parse import urlparse
from moviepy.video.io.VideoFileClip import VideoFileClip

# ================== 1. 全局配置区域 ==================
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
SOURCE = 'pixabay' 
SEARCH_QUERY = "sea drone 4k" 
SAVE_DIR = r"H:\OliverAI\resources\seadrone" 
MAX_DOWNLOADS = 10
BATCH_SIZE = 5

# 目标 4K 参数
UHD_W, UHD_H = 3840, 2160
TARGET_RATIO = 16 / 9
RATIO_TOLERANCE = 0.05

# 滤镜参数
FILTER_SATURATION = 1.25
FILTER_CONTRAST = 1.10
ENABLE_VIGNETTE = True
WATERMARK_TEXT = "© Tank&Tail Talk"

# ================== 2. 增强版 FFmpeg 处理函数 ==================

def ffmpeg_process_uhd(input_path, output_path, original_w, original_h):
    """
    智能 Upscale 与洗白：
    如果原图 < 4K，执行 Lanczos 放大 + 锐化。
    如果原图 >= 4K，仅执行滤镜处理。
    """
    h_flip = "hflip," if random.random() > 0.5 else ""
    speed = random.uniform(0.99, 1.01) # 稍微缩减范围确保稳定
    
    vf_chain = []
    
    # --- 逻辑 A: 判断是否需要 Upscale ---
    if original_w < UHD_W:
        print(f"🚀 [Upscaling] {original_w}p -> 4K (Lanczos)")
        # 放大到 4K 并添加轻微锐化 (unsharp) 补偿拉伸导致的模糊
        vf_chain.append(f"scale={UHD_W}:{UHD_H}:flags=lanczos")
        vf_chain.append("unsharp=3:3:0.5:3:3:0.0")
    else:
        print(f"💎 [Native 4K] Maintaining original resolution")
        # 即使是 4K，也可以做微小的裁剪或缩放来改变 MD5 数据特征
        vf_chain.append(f"scale={UHD_W}:{UHD_H}")

    # --- 逻辑 B: 基础洗白滤镜 ---
    vf_chain.append(f"{h_flip}fps=30")
    vf_chain.append(f"setpts={1/speed}*PTS")
    vf_chain.append(f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST}")
    
    if ENABLE_VIGNETTE: 
        vf_chain.append("vignette=PI/4")
    
    # 水印 (根据 4K 分辨率调大了字体)
    drawtext = f"drawtext=text='{WATERMARK_TEXT}':fontcolor=white@0.5:fontsize=48:x=w-tw-40:y=h-th-40"
    vf_chain.append(drawtext)

    # 编码参数：4K 需要更高的码率 (-b:v 30M)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-hwaccel", "cuda", "-i", input_path,
        "-vf", ",".join(vf_chain),
        "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "30M", 
        "-pix_fmt", "yuv420p", 
        "-an",                  # 移除音轨
        "-map_metadata", "-1",  # 抹除元数据
        output_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg 报错详情: {e.stderr}")
        return False

# ================== 3. API 与 下载模块 (保持不变) ==================
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
                    vid_url = videos.get('large', {}).get('url') or videos.get('medium', {}).get('url')
                    if vid_url: results.append({'id': str(item['id']), 'url': vid_url})
    except: pass
    return results

# ================== 4. 主流程控制 (已更新) ==================

def main():
    if not os.path.exists(SAVE_DIR): os.makedirs(SAVE_DIR)
    total_downloaded = 0
    current_page = 1
    
    # API 获取逻辑已在上方定义

    while total_downloaded < MAX_DOWNLOADS:
        links = get_media_links(SOURCE, SEARCH_QUERY, current_page, BATCH_SIZE)
        if not links: break
        
        for item in links:
            if total_downloaded >= MAX_DOWNLOADS: break
            
            raw_path = os.path.join(SAVE_DIR, f"temp_raw_{item['id']}.mp4")
            final_path = os.path.join(SAVE_DIR, f"{SOURCE}_UHD_{item['id']}.mp4")
            
            if os.path.exists(final_path):
                print(f"⏩ [跳过] 已存在: {item['id']}")
                continue

            try:
                # 下载
                r = requests.get(item['url'], timeout=30)
                with open(raw_path, 'wb') as f: f.write(r.content)

                if os.path.getsize(raw_path) < 2 * 1024 * 1024:
                    os.remove(raw_path); continue

                # 读取视频属性
                with VideoFileClip(raw_path) as clip:
                    dur = clip.duration
                    w, h = clip.size
                    ratio = w / h
                
                # 规格筛选
                if (10.0 <= dur <= 120.0) and (abs(ratio - TARGET_RATIO) < RATIO_TOLERANCE):
                    # 传入 w, h 供处理函数判断是否需要 Upscale
                    if ffmpeg_process_uhd(raw_path, final_path, w, h):
                        total_downloaded += 1
                        print(f"✅ [完成] 4K洗白件保存: {os.path.basename(final_path)}")
                    else:
                        print(f"❌ [失败] FFmpeg 处理出错")
                else:
                    print(f"🗑️ [跳过] 比例或时长不符")
                
                if os.path.exists(raw_path): os.remove(raw_path)

            except Exception as e:
                print(f"⚠️ [异常] {e}")
                if os.path.exists(raw_path): os.remove(raw_path)

        current_page += 1
        time.sleep(2)

if __name__ == "__main__":
    main()