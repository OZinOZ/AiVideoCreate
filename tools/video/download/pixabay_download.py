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
SOURCE = 'pixabay'  # 修改为你需要的源
SEARCH_QUERY = "sea drone" 
SAVE_DIR = r"H:\OliverAI\resources\seadrone" 
MAX_DOWNLOADS = 10
BATCH_SIZE = 5

TARGET_WIDTH, TARGET_HEIGHT = 1920, 1080
TARGET_RATIO = 16 / 9
RATIO_TOLERANCE = 0.05

# 滤镜参数
FILTER_SATURATION = 1.25
FILTER_CONTRAST = 1.10
ENABLE_VIGNETTE = True
WATERMARK_TEXT = "© Tank&Tail Talk"

# ================== 2. 核心洗白函数 (修正滤镜报错) ==================

def ffmpeg_process_nvenc(input_path, output_path):
    """
    深度洗白：修正 eq 滤镜参数兼容性，确保处理成功
    """
    h_flip = "hflip," if random.random() > 0.5 else ""
    speed = random.uniform(0.98, 1.02)
    
    # 修正点：将 eq 滤镜的参数严格化，去掉可能引起报错的 hue
    vf_chain = [
        f"scale=2016:1134", 
        f"crop=1920:1080", 
        f"{h_flip}fps=30",
        f"setpts={1/speed}*PTS",
        f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST}" # 移除了可能报错的 hue
    ]
    
    if ENABLE_VIGNETTE: 
        vf_chain.append("vignette=PI/4")
    
    # 修正点：drawtext 路径和转义优化
    drawtext = f"drawtext=text='{WATERMARK_TEXT}':fontcolor=white@0.6:fontsize=24:x=w-tw-20:y=h-th-20"
    vf_chain.append(drawtext)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-hwaccel", "cuda", "-i", input_path,
        "-vf", ",".join(vf_chain),
        "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "10M",
        "-pix_fmt", "yuv420p", 
        "-an",                 # 彻底移除音轨
        "-map_metadata", "-1", # 抹除所有元数据标签
        output_path
    ]
    
    try:
        # 执行命令并捕获详细错误输出
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg 报错详情: {e.stderr}")
        return False

# ================== 3. API 与 下载模块 ==================

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
            params = {'key': PIXABAY_API_KEY, 'q': query, 'per_page': per_page, 'page': page}
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                for item in res.json().get('hits', []):
                    videos = item.get('videos', {})
                    vid_url = videos.get('large', {}).get('url') or videos.get('medium', {}).get('url')
                    if vid_url: results.append({'id': str(item['id']), 'url': vid_url})
    except: pass
    return results

# ================== 4. 主流程控制 ==================

def main():
    if not os.path.exists(SAVE_DIR): os.makedirs(SAVE_DIR)
    total_downloaded = 0
    current_page = 1
    print(f"🌊 [任务开始] 目标素材: {MAX_DOWNLOADS} 个")

    while total_downloaded < MAX_DOWNLOADS:
        links = get_media_links(SOURCE, SEARCH_QUERY, current_page, BATCH_SIZE)
        if not links: 
            print("⚠️ 未能获取到更多链接，退出。")
            break
        
        for item in links:
            if total_downloaded >= MAX_DOWNLOADS: break
            
            raw_path = os.path.join(SAVE_DIR, f"temp_raw_{item['id']}.mp4")
            final_path = os.path.join(SAVE_DIR, f"{SOURCE}_{item['id']}.mp4")
            
            if os.path.exists(final_path):
                print(f"⏩ [跳过] 已存在: {item['id']}")
                continue

            try:
                # 1. 下载原始文件
                print(f"\n[下载中] ID: {item['id']}...")
                r = requests.get(item['url'], timeout=30)
                with open(raw_path, 'wb') as f: f.write(r.content)

                # 2. 物理检查
                if os.path.getsize(raw_path) < 2 * 1024 * 1024:
                    print(f"🗑️ [删除] ID:{item['id']} | 文件过小")
                    os.remove(raw_path); continue

                with VideoFileClip(raw_path) as clip:
                    dur = clip.duration
                    w, h = clip.size
                    ratio = w / h
                
                # 3. 筛选并执行洗白
                if (10.0 <= dur <= 60.0) and (abs(ratio - TARGET_RATIO) < RATIO_TOLERANCE):
                    print(f"✨ [精炼中] {w}x{h} | {dur:.1f}s")
                    if ffmpeg_process_nvenc(raw_path, final_path):
                        total_downloaded += 1
                        print(f"✅ [成功] 已保存洗白件: {os.path.basename(final_path)}")
                    else:
                        print(f"❌ [失败] FFmpeg 处理未成功")
                else:
                    print(f"🗑️ [跳过] 规格不符: {w}x{h}, {dur:.1f}s")
                
                # 4. 清理原始临时文件
                if os.path.exists(raw_path): os.remove(raw_path)

            except Exception as e:
                print(f"⚠️ [异常] ID:{item['id']} | {e}")
                if os.path.exists(raw_path): os.remove(raw_path)

        current_page += 1
        time.sleep(3)

    print("\n✨ [全流程完成] 你的“黄金素材库”已就绪！")

if __name__ == "__main__":
    main()