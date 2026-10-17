import os
import time
import requests
import random
import subprocess
import shutil
import json
from urllib.parse import urlparse

# ==========================================
# --- 全局配置区域 ---
# ==========================================

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
SOURCE = 'pixabay'

# --- 季节与分类 ---
CURRENT_SEASON = "Winter" 
SEARCH_QUERY = "snow forest" 

SAVE_DIR = f"./downloads/{CURRENT_SEASON}_Collection"
MAX_DOWNLOADS = 5
BATCH_SIZE = 5

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# --- 配色 ---
SEASON_COLORS = {
    "Winter": "0x00FFFF",  
    "Autumn": "0xFFAA00",  
    "Summer": "0xFFDD00",  
    "Spring": "0x55FF55",
    "Default": "white"
}

# --- 音频与滤镜 ---
AUDIO_TARGET_LUFS = -16
AUDIO_TRUE_PEAK = -1.5
AUDIO_LRA = 11

FILTER_SATURATION = 1.2
FILTER_CONTRAST = 1.08
ENABLE_VIGNETTE = True

WATERMARK_TEXT = "Scenery Hub Originals"
WATERMARK_FONT_SIZE = 28
WATERMARK_OPACITY = 0.7
# Windows 必须指定字体路径
FONT_FILE_PATH = "C:/Windows/Fonts/arial.ttf" 

# ==========================================
# --- 核心工具函数 ---
# ==========================================

def get_audio_info(filepath):
    """检测是否有音频流"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "a", filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        if data.get("streams"):
            return True
        return False
    except:
        return False

def generate_intro_video(output_path, season):
    """
    生成 3 秒 Intro，音频强制设定为 44100Hz Stereo
    """
    if os.path.exists(output_path): return True
    
    print(f"[片头生成] 正在制作 {season} Intro...")
    color = SEASON_COLORS.get(season, "white")
    font_cmd = f":fontfile='{FONT_FILE_PATH}'" if FONT_FILE_PATH else ""
    
    vf_graph = (
        f"color=c=black:s={TARGET_WIDTH}x{TARGET_HEIGHT}:d=3,"
        f"drawtext=text='Scenery Hub'{font_cmd}:fontcolor=white:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2-40,"
        f"drawtext=text='{season} Collection'{font_cmd}:fontcolor={color}:fontsize=40:x=(w-text_w)/2:y=(h-text_h)/2+60:alpha='if(lt(t,0.5),0,if(lt(t,2.5),1,0))',"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st=2.5:d=0.5"
    )

    # 关键点：ar=44100 强制 Intro 也是 44.1k
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", 
        "-filter_complex", f"{vf_graph}[v]", 
        "-map", "[v]", "-map", "0:a",
        "-t", "3",
        "-c:v", "libx264", "-preset", "ultrafast", 
        "-c:a", "aac", "-ar", "44100", # 显式指定 Intro 音频采样率
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[片头生成失败] {e.stderr.decode('utf-8', errors='ignore')}")
        return False

def ffmpeg_process_concat(intro_path, main_video_path, output_path, has_audio):
    """
    拼接 Intro + 主视频 (修复音频采样率不匹配导致的丢声问题)
    """
    
    font_config = f":fontfile='{FONT_FILE_PATH}'" if FONT_FILE_PATH else ""
    
    # 1. 主视频画面处理 (缩放 -> 调色 -> 水印)
    main_vf = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT},"
        f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST},"
        f"{'vignette=PI/5,' if ENABLE_VIGNETTE else ''}"
        f"drawtext=text='{WATERMARK_TEXT}'{font_config}:fontcolor=white@{WATERMARK_OPACITY}:fontsize={WATERMARK_FONT_SIZE}:x=w-tw-20:y=h-th-20"
    )
    
    # 2. 核心修复逻辑：构建 filter_complex
    # 我们必须确保主视频的音频在 concat 之前，格式与 Intro 完全一致 (44100Hz, Stereo)
    
    if has_audio:
        # 逻辑：
        # [1:v] -> 滤镜 -> [main_v]
        # [1:a] -> 强制重采样(44100/stereo) -> [main_a_resampled]
        # [0:v][0:a] (Intro) + [main_v][main_a_resampled] -> 拼接 -> [out_v][joined_a]
        # [joined_a] -> 响度标准化 -> [out_a]
        
        filter_complex = (
            f"[1:v]{main_vf}[main_v];"
            f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo[main_a_resampled];" 
            f"[0:v][0:a][main_v][main_a_resampled]concat=n=2:v=1:a=1[out_v][joined_a];"
            f"[joined_a]loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TRUE_PEAK}:LRA={AUDIO_LRA}[out_a]"
        )
    else:
        # 无音频逻辑 (保持不变，因为不需要拼接音频流)
        filter_complex = (
            f"[1:v]{main_vf}[main_v];"
            f"[0:v][0:a][main_v][0:a]concat=n=2:v=1:a=1[out_v][out_a]"
        )

    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda", 
        "-i", intro_path,       # [0]
        "-i", main_video_path,  # [1]
        "-filter_complex", filter_complex,
        "-map", "[out_v]", "-map", "[out_a]",
        "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "8M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", # 输出也强制 44100
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        # 打印详细错误，方便调试
        print(f"[拼接失败] {e.stderr.decode('utf-8', errors='ignore')}")
        return False

# ==========================================
# --- 流程控制 ---
# ==========================================

def download_file(url, folder, prefix, file_id):
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1]
        if not ext or len(ext) > 5: ext = '.mp4'
        filename = f"{prefix}_{file_id}{ext}"
        filepath = os.path.join(folder, filename)
        if os.path.exists(filepath): return False
        if os.path.exists(os.path.join(folder, "mute", filename)): return False
        
        print(f"[下载中] {filename} ...")
        response = requests.get(url, stream=True, timeout=30)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        print(f"[成功] 已保存: {filename}")
        return True
    except: return False

def get_media_links(source, query, page, per_page):
    results = []
    try:
        if source == 'pixabay':
            url = "https://pixabay.com/api/videos/"
            params = {'key': PIXABAY_API_KEY, 'q': query, 'per_page': per_page, 'page': page, 'orientation': 'horizontal'}
            res = requests.get(url, params=params)
            if res.status_code == 200:
                for item in res.json().get('hits', []):
                    videos = item.get('videos', {})
                    vid_url = videos.get('medium', {}).get('url') or videos.get('large', {}).get('url')
                    if vid_url: results.append({'id': str(item['id']), 'url': vid_url})
    except: pass
    return results

def ensure_dir(d): 
    if not os.path.exists(d): os.makedirs(d)

def process_videos_in_directory(directory):
    mute_dir = os.path.join(directory, "mute")
    ensure_dir(mute_dir)
    
    intro_filename = f"Intro_{CURRENT_SEASON}.mp4"
    intro_path = os.path.join(directory, intro_filename)
    
    if not generate_intro_video(intro_path, CURRENT_SEASON):
        print("片头生成失败，请检查字体路径。")
        return

    print(f"\n>>> 开始全流程 (音频修复版) <<<")
    
    files = [f for f in os.listdir(directory) if f.endswith(".mp4") and not f.startswith("Intro_")]
    
    for filename in files:
        filepath = os.path.join(directory, filename)
        temp_filepath = os.path.join(directory, f"temp_{filename}")
        
        try:
            has_audio = get_audio_info(filepath)
            print(f"[处理] {filename} | 音轨检测: {'✅' if has_audio else '❌'} | 正在拼接...")

            success = ffmpeg_process_concat(intro_path, filepath, temp_filepath, has_audio)
            
            if success:
                os.remove(filepath)
                if has_audio:
                    os.rename(temp_filepath, filepath)
                    print(f"[完成] 主目录 (有声)")
                else:
                    dest_path = os.path.join(mute_dir, filename)
                    if os.path.exists(dest_path): os.remove(dest_path)
                    os.rename(temp_filepath, dest_path)
                    print(f"[完成] Mute目录 (无声)")
            else:
                print(f"[失败] 跳过，可能是文件损坏")
                if os.path.exists(temp_filepath): os.remove(temp_filepath)

        except Exception as e:
            print(f"[异常] {filename}: {e}")

def main():
    ensure_dir(SAVE_DIR)
    
    total_downloaded = 0
    current_page = 1
    print(f"=== 季节: {CURRENT_SEASON} | 目标: {MAX_DOWNLOADS} 个 ===")
    
    while total_downloaded < MAX_DOWNLOADS:
        print(f"--- Page {current_page} ---")
        links = get_media_links(SOURCE, SEARCH_QUERY, current_page, BATCH_SIZE)
        if not links: break
        for item in links:
            if total_downloaded >= MAX_DOWNLOADS: break
            if download_file(item['url'], SAVE_DIR, SOURCE, item['id']):
                total_downloaded += 1
        current_page += 1
        time.sleep(2)

    if total_downloaded > 0 or len([f for f in os.listdir(SAVE_DIR) if f.endswith(".mp4") and not f.startswith("Intro_")]) > 0:
        process_videos_in_directory(SAVE_DIR)
    
    print("\n=== 全部完成 ===")

if __name__ == "__main__":
    main()