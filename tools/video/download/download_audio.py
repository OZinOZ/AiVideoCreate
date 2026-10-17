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
SEARCH_QUERY = "flowers" # 建议：搜索带 sound 关键词的测试一下，比如 "forest sound"
SAVE_DIR = "H:\\resources\\flowers" # 主目录
MAX_DOWNLOADS = 1000 
BATCH_SIZE = 5

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# --- 音频标准设置 ---
AUDIO_TARGET_LUFS = -16
AUDIO_TRUE_PEAK = -1.5
AUDIO_LRA = 11

# --- 滤镜与水印 ---
FILTER_SATURATION = 1.2   
FILTER_CONTRAST = 1.08    
ENABLE_VIGNETTE = True    

WATERMARK_TEXT = "© Scenery Hub" 
WATERMARK_FONT_SIZE = 28
WATERMARK_OPACITY = 0.7   
FONT_FILE_PATH = None 

# ==========================================
# --- 核心工具函数 ---
# ==========================================

def get_audio_info(filepath):
    """
    使用 ffprobe 权威检测是否有音频流
    返回: (has_audio: bool, stream_index: str)
    """
    cmd = [
        "ffprobe", 
        "-v", "quiet", 
        "-print_format", "json", 
        "-show_streams", 
        "-select_streams", "a", 
        filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        if data.get("streams"):
            return True
        else:
            return False
    except Exception as e:
        print(f"   [检测出错] 无法读取音频信息: {e}")
        return False

def ffmpeg_process_nvenc(input_path, output_path, has_audio):
    """
    硬件转码 + 滤镜 + 水印 + 音频处理 (修复版)
    """
    # 1. 构建视频滤镜链
    vf_chain = []
    vf_chain.append(f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}")
    vf_chain.append(f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST}")
    if ENABLE_VIGNETTE:
        vf_chain.append("vignette=PI/5")

    # 水印
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

    # 2. 构建 FFmpeg 命令
    cmd = [
        "ffmpeg", "-y", 
        "-hwaccel", "cuda", 
        "-i", input_path,
        "-vf", full_vf_string,
        "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "8M",
    ]

    # 3. 音频处理逻辑 (关键修复点)
    if has_audio:
        # 强制映射第一个音频流，防止丢失
        # -map 0:v:0 选择第一个视频流
        # -map 0:a:0 选择第一个音频流
        cmd.extend(["-map", "0:v:0", "-map", "0:a:0"]) 
        
        cmd.extend([
            "-af", f"loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TRUE_PEAK}:LRA={AUDIO_LRA}",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100"
        ])
    else:
        # 如果确实没声音，就不映射音频流，只映射视频
        cmd.extend(["-map", "0:v:0"])
        # 并且不加 -c:a 参数
    
    cmd.append(output_path)
    
    try:
        # 打印命令以便调试 (如果还不行，把下面这行注释取消，看看具体跑了什么)
        # print(" ".join(cmd)) 
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore')
        print(f"[FFmpeg 错误] {err_msg}")
        return False

# ==========================================
# --- 下载与辅助函数 ---
# ==========================================

def ensure_dir(directory):
    if not os.path.exists(directory): os.makedirs(directory)

def download_file(url, folder, prefix, file_id):
    # 这里增加逻辑：先下载到临时文件，不直接命名为 mp4，防止中断
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1]
        if not ext or len(ext) > 5: ext = '.mp4'
        filename = f"{prefix}_{file_id}{ext}"
        filepath = os.path.join(folder, filename)
        
        # 检查是否已存在 (包括在 mute 里的)
        if os.path.exists(filepath):
            print(f"[跳过] 文件已存在: {filename}")
            return False
        if os.path.exists(os.path.join(folder, "mute", filename)):
            print(f"[跳过] 文件已存在(mute): {filename}")
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
# --- 流程控制 ---
# ==========================================

def process_videos_in_directory(directory):
    mute_dir = os.path.join(directory, "mute")
    ensure_dir(mute_dir)
    
    print(f"\n>>> 开始全流程处理 (ffprobe 强力检测版) <<<")
    
    files = [f for f in os.listdir(directory) if f.endswith(".mp4")]
    if not files:
        print("主目录无可处理文件。")
        return

    for filename in files:
        filepath = os.path.join(directory, filename)
        temp_filepath = os.path.join(directory, f"temp_{filename}")
        
        try:
            # 1. 使用 ffprobe 检测音频 (更准)
            has_audio = get_audio_info(filepath)
            
            # 2. 打印诊断信息
            audio_status = "✅ 有音轨" if has_audio else "❌ 无音轨(纯画面)"
            print(f"[分析] {filename} | {audio_status}")

            # 3. 处理
            success = ffmpeg_process_nvenc(filepath, temp_filepath, has_audio)
            
            if success:
                os.remove(filepath)
                if has_audio:
                    os.rename(temp_filepath, filepath)
                    print(f"[完成] 保留在主目录 (有声)")
                else:
                    dest_path = os.path.join(mute_dir, filename)
                    if os.path.exists(dest_path): os.remove(dest_path)
                    os.rename(temp_filepath, dest_path)
                    print(f"[完成] 移入 mute 目录 (无声)")
            else:
                print(f"[失败] 跳过文件")
                if os.path.exists(temp_filepath): os.remove(temp_filepath)

        except Exception as e:
            print(f"[异常] {filename}: {e}")

def main():
    ensure_dir(SAVE_DIR)
    total_downloaded = 0
    current_page = 1
    
    print(f"=== 任务开始: 目标 {MAX_DOWNLOADS} 个视频 ===")
    
    # 为了测试音频，我们可以先把关键词改成容易有声音的，比如 "ocean waves"
    # 如果你搜 "drone"，大概率全是无声的。
    
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

    print(f"\n=== 下载结束，开始处理 ===")
    if total_downloaded > 0 or len([f for f in os.listdir(SAVE_DIR) if f.endswith(".mp4")]) > 0:
        process_videos_in_directory(SAVE_DIR)
    print("\n=== 全部完成 ===")

if __name__ == "__main__":
    main()