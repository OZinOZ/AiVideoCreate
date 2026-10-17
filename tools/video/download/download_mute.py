import os
import time
import requests
import random
import subprocess
import shutil
from urllib.parse import urlparse
from moviepy.video.io.VideoFileClip import VideoFileClip

# ==========================================
# --- 全局配置区域 ---
# ==========================================

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
SOURCE = 'pixabay'
SEARCH_QUERY = "forest drone" 
SAVE_DIR = "H:\\resources\\drone" # 主目录
MAX_DOWNLOADS = 200
BATCH_SIZE = 5

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_RATIO = 16 / 9
RATIO_TOLERANCE = 0.05

# --- 音频标准设置 ---
AUDIO_TARGET_LUFS = -16
AUDIO_TRUE_PEAK = -1.5
AUDIO_LRA = 11

# --- 滤镜与水印设置 ---
FILTER_SATURATION = 1.2   
FILTER_CONTRAST = 1.08    
ENABLE_VIGNETTE = True    

WATERMARK_TEXT = "© Scenery Hub" 
WATERMARK_FONT_SIZE = 24
WATERMARK_OPACITY = 0.7   

# Windows 字体路径 (如果报错请取消注释并修改路径)
# FONT_FILE_PATH = "C:/Windows/Fonts/arial.ttf" 
FONT_FILE_PATH = None 

# ==========================================
# --- 核心处理函数 (FFmpeg) ---
# ==========================================

def ffmpeg_process_nvenc(input_path, output_path, has_audio):
    """
    硬件转码 + 滤镜 + 水印 + 音频处理
    """
    vf_chain = []
    vf_chain.append(f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}")
    vf_chain.append(f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST}")
    if ENABLE_VIGNETTE:
        vf_chain.append("vignette=PI/5")

    font_config = ""
    if FONT_FILE_PATH:
        font_config = f":fontfile='{FONT_FILE_PATH}'"
        
    drawtext_cmd = (
        f"drawtext=text='{WATERMARK_TEXT}'"
        f"{font_config}"
        f":fontcolor=white@{WATERMARK_OPACITY}"
        f":fontsize={WATERMARK_FONT_SIZE}"
        f":x=w-tw-20:y=h-th-20"
    )
    vf_chain.append(drawtext_cmd)
    full_vf_string = ",".join(vf_chain)

    cmd = [
        "ffmpeg", "-y", "-hwaccel", "cuda", "-i", input_path,
        "-vf", full_vf_string,
        "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "8M",
    ]

    if has_audio:
        cmd.extend([
            "-af", f"loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TRUE_PEAK}:LRA={AUDIO_LRA}",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100"
        ])
    else:
        # 无音频时，不处理音频流
        pass

    cmd.append(output_path)
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FFmpeg 错误] {e.stderr.decode('utf-8', errors='ignore') if e.stderr else '未知'}")
        return False

# ==========================================
# --- 下载与辅助函数 ---
# ==========================================

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def download_file(url, folder, prefix, file_id):
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1]
        if not ext or len(ext) > 5: ext = '.mp4'
        filename = f"{prefix}_{file_id}{ext}"
        filepath = os.path.join(folder, filename)
        if os.path.exists(filepath):
            print(f"[跳过] 文件已存在: {filename}")
            return False
        
        # 检查是否已经在 mute 目录里了（避免重复下载）
        mute_filepath = os.path.join(folder, "mute", filename)
        if os.path.exists(mute_filepath):
             print(f"[跳过] 文件已存在于 mute 目录: {filename}")
             return False

        print(f"[下载中] {filename} ...")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[成功] 已保存: {filename}")
        return True
    except Exception as e:
        print(f"[下载错误] {url}: {e}")
        return False

def get_media_links(source, query, page, per_page):
    results = []
    try:
        if source == 'pexels':
            headers = {'Authorization': PEXELS_API_KEY}
            url = f"https://api.pexels.com/videos/search?query={query}&orientation=landscape&per_page={per_page}&page={page}"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                for item in data.get('videos', []):
                    files = sorted(item.get('video_files', []), key=lambda x: x['width']*x['height'], reverse=True)
                    if files: results.append({'id': str(item['id']), 'url': files[0]['link']})
        elif source == 'pixabay':
            url = "https://pixabay.com/api/videos/"
            params = {'key': PIXABAY_API_KEY, 'q': query, 'per_page': per_page, 'page': page, 'orientation': 'horizontal'}
            res = requests.get(url, params=params)
            if res.status_code == 200:
                data = res.json()
                for item in data.get('hits', []):
                    videos = item.get('videos', {})
                    vid_url = videos.get('medium', {}).get('url') or videos.get('large', {}).get('url')
                    if vid_url: results.append({'id': str(item['id']), 'url': vid_url})
    except Exception as e:
        print(f"[API 异常] {e}")
    return results

# ==========================================
# --- 流程控制 (含分类逻辑) ---
# ==========================================

def process_videos_in_directory(directory):
    # 1. 确保 mute 子目录存在
    mute_dir = os.path.join(directory, "mute")
    ensure_dir(mute_dir)
    
    print(f"\n>>> 开始全流程处理 (含静音分类) <<<")
    
    # 只扫描当前目录下的 mp4，不扫描 mute 子目录里的
    files = [f for f in os.listdir(directory) if f.endswith(".mp4")]
    
    if not files:
        print("主目录无可处理文件。")
        return

    for filename in files:
        filepath = os.path.join(directory, filename)
        temp_filepath = os.path.join(directory, f"temp_{filename}")
        
        try:
            # 读取信息
            clip = VideoFileClip(filepath)
            w, h = clip.size
            ratio = w / h
            has_audio = clip.audio is not None # 关键判断
            clip.close() 
            
            # 筛选 16:9
            if not (TARGET_RATIO - RATIO_TOLERANCE <= ratio <= TARGET_RATIO + RATIO_TOLERANCE):
                print(f"[删除] {filename} | 宽高比不符")
                os.remove(filepath)
                continue

            print(f"[处理中] {filename} | 音频: {'有' if has_audio else '无'} ...")
            
            # 执行 FFmpeg 处理 (都会加滤镜和水印)
            success = ffmpeg_process_nvenc(filepath, temp_filepath, has_audio)
            
            if success:
                # 删除原始未处理文件
                os.remove(filepath)
                
                if has_audio:
                    # 有声音 -> 留在主目录
                    os.rename(temp_filepath, filepath)
                    print(f"[完成] 保留在主目录")
                else:
                    # 无声音 -> 移动到 mute 目录
                    dest_path = os.path.join(mute_dir, filename)
                    # 如果 mute 里已有同名文件，先删除旧的
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    os.rename(temp_filepath, dest_path)
                    print(f"[完成] 移入 mute 目录")
            else:
                print(f"[失败] 跳过文件")
                if os.path.exists(temp_filepath): os.remove(temp_filepath)

        except Exception as e:
            print(f"[异常] {filename}: {e}")

# ==========================================
# --- 主程序 ---
# ==========================================

def main():
    ensure_dir(SAVE_DIR)
    total_downloaded = 0
    current_page = 1
    print(f"=== 任务开始: 目标 {MAX_DOWNLOADS} 个视频 ===")
    
    while total_downloaded < MAX_DOWNLOADS:
        print(f"\n--- API 第 {current_page} 页 ---")
        links = get_media_links(SOURCE, SEARCH_QUERY, current_page, BATCH_SIZE)
        if not links: break
        for item in links:
            if total_downloaded >= MAX_DOWNLOADS: break
            if download_file(item['url'], SAVE_DIR, SOURCE, item['id']):
                total_downloaded += 1
        current_page += 1
        time.sleep(20)

    print(f"\n=== 下载结束，开始处理与分类 ===")
    if total_downloaded > 0 or len([f for f in os.listdir(SAVE_DIR) if f.endswith(".mp4")]) > 0:
        process_videos_in_directory(SAVE_DIR)
    print("\n=== 全部完成 ===")

if __name__ == "__main__":
    main()