import os
import time
import requests
import random
import subprocess  # 用于调用 FFmpeg 命令
from urllib.parse import urlparse
# from moviepy.editor import VideoFileClip # 仅用于读取信息，不用于处理
from moviepy.video.io.VideoFileClip import VideoFileClip

# ==========================================
# --- 全局配置区域 ---
# ==========================================

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
SOURCE = 'pixabay'
SEARCH_QUERY = "running river"
SAVE_DIR = "H:\\resources\\streams"
MAX_DOWNLOADS = 200
BATCH_SIZE = 5

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_RATIO = 16 / 9
RATIO_TOLERANCE = 0.05

# ==========================================
# --- 硬件加速处理函数 (核心修改) ---
# ==========================================

def ffmpeg_convert_nvenc(input_path, output_path):
    """
    使用 NVIDIA GPU (nvenc) 进行硬件加速转码和缩放。
    """
    # 构建 FFmpeg 命令
    # -hwaccel cuda: 尝试使用 CUDA 硬件解码 (如果支持)
    # -i: 输入文件
    # -vf scale=1920:1080: 视频滤镜，强制缩放到 1080p
    # -c:v h264_nvenc: 使用 NVIDIA 硬件编码器
    # -preset p4: 性能预设 (p1最快~p7画质最好，p4是平衡)
    # -b:v 5M: 强制比特率 5Mbps (保证画质，可根据需求改)
    # -c:a copy: 音频直接复制，不重新编码 (速度极快)
    # -y: 覆盖输出文件不询问
    
    cmd = [
        "ffmpeg",
        "-y",
        "-hwaccel", "cuda", 
        "-i", input_path,
        "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}",
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-b:v", "6M", 
        "-c:a", "copy",
        output_path
    ]
    
    try:
        # 隐藏命令行输出，只在出错时显示
        # 如果你想看进度，把 stdout 和 stderr 去掉
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FFmpeg 错误] {e}")
        return False

# ==========================================
# --- 其他辅助函数 (保持不变) ---
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

def process_videos_in_directory(directory):
    print(f"\n>>> 开始 GPU 极速清洗 (目标: 1920x1080, NVENC 加速) <<<")
    files = [f for f in os.listdir(directory) if f.endswith(".mp4")]
    
    if not files:
        print("目录为空。")
        return

    for filename in files:
        filepath = os.path.join(directory, filename)
        temp_filepath = os.path.join(directory, f"temp_{filename}")
        
        try:
            # 依然用 MoviePy 快速读取信息（这步很快，只读元数据）
            clip = VideoFileClip(filepath)
            w, h = clip.size
            ratio = w / h
            clip.close() # 读完马上关掉，释放资源
            
            # 1. 检查宽高比
            if not (TARGET_RATIO - RATIO_TOLERANCE <= ratio <= TARGET_RATIO + RATIO_TOLERANCE):
                print(f"[删除] {filename} | 比例不符 ({w}x{h})")
                os.remove(filepath)
                continue

            # 2. 检查分辨率
            if w == TARGET_WIDTH and h == TARGET_HEIGHT:
                print(f"[完美] {filename} | 无需处理")
                continue
            
            # 3. GPU 极速重编码
            print(f"[GPU转码] {filename} | {w}x{h} -> 1080p ...")
            
            # 调用 FFmpeg 硬件加速
            success = ffmpeg_convert_nvenc(filepath, temp_filepath)
            
            if success:
                os.remove(filepath)
                os.rename(temp_filepath, filepath)
                print(f"[成功] {filename} 处理完毕")
            else:
                print(f"[失败] {filename} 转码失败，保留原文件")
                if os.path.exists(temp_filepath): os.remove(temp_filepath)

        except Exception as e:
            print(f"[处理异常] {filename}: {e}")

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
        time.sleep(2)

    print(f"\n=== 下载结束，开始处理 ===")
    if total_downloaded > 0 or len(os.listdir(SAVE_DIR)) > 0:
        process_videos_in_directory(SAVE_DIR)
    print("\n=== 完成 ===")

if __name__ == "__main__":
    main()