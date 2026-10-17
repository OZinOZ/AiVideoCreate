import os
import time
import requests
import random
import subprocess
from urllib.parse import urlparse
from moviepy.video.io.VideoFileClip import VideoFileClip

# ==========================================
# --- 全局配置区域 ---
# ==========================================

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
SOURCE = 'pixabay'
SEARCH_QUERY = "sunrise, sunset, bluesky"
SAVE_DIR = "H:\\resources\\sky" # 主目录
MAX_DOWNLOADS = 600 # 测试时先设置小一点
BATCH_SIZE = 5

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_RATIO = 16 / 9
RATIO_TOLERANCE = 0.05

# --- 音频标准设置 ---
AUDIO_TARGET_LUFS = -16
AUDIO_TRUE_PEAK = -1.5
AUDIO_LRA = 11

# --- 新增：滤镜与水印设置 ---
# 1. 自然滤镜强度
FILTER_SATURATION = 1.2   # 饱和度 (1.0是原图, 1.2增加20%)
FILTER_CONTRAST = 1.08    # 对比度 (1.0是原图, 1.08增加8%)
ENABLE_VIGNETTE = True    # 是否开启电影感暗角

# 2. 水印文字设置
# 注意：不要使用中文，除非你非常懂如何在FFmpeg里配置中文字体路径
WATERMARK_TEXT = "© Scenery Hub" 
WATERMARK_FONT_SIZE = 24
WATERMARK_OPACITY = 0.7   # 透明度 (0.1透明 ~ 1.0不透明)

# 【Windows用户特别注意】
# 如果报错 "Fontconfig error: Cannot load default config file"，
# 请取消下面这行的注释，并确认路径正确，强制指定一个字体文件：
# FONT_FILE_PATH = "C:/Windows/Fonts/arial.ttf" 
FONT_FILE_PATH = None # 默认尝试自动查找

# ==========================================
# --- 核心处理函数 (FFmpeg 复杂滤镜链) ---
# ==========================================

def ffmpeg_process_nvenc(input_path, output_path, has_audio):
    """
    集大成处理：硬件转码 + 缩放 + 自然滤镜 + 水印 + 音频标准化
    """
    
    # --- 构建视频滤镜链 (Video Filter Chain) ---
    # FFmpeg 的滤镜是像糖葫芦一样串起来的，用逗号分隔
    vf_chain = []

    # 1. 基础缩放 (Scale)
    vf_chain.append(f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}")

    # 2. 自然增强滤镜 (EQ & Vignette)
    # eq=saturation=1.2:contrast=1.08
    vf_chain.append(f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST}")
    if ENABLE_VIGNETTE:
        # PI/5 是一个比较自然的暗角角度
        vf_chain.append("vignette=PI/5")

    # 3. 文字水印 (Drawtext)
    # x=w-tw-20:y=h-th-20 表示放在右下角，距离边缘20像素
    # fontcolor=white@0.7 设置白色且0.7透明度
    font_config = ""
    if FONT_FILE_PATH:
        # 如果指定了字体路径 (Windows常用)
        font_config = f":fontfile='{FONT_FILE_PATH}'"
        
    drawtext_cmd = (
        f"drawtext=text='{WATERMARK_TEXT}'"
        f"{font_config}"
        f":fontcolor=white@{WATERMARK_OPACITY}"
        f":fontsize={WATERMARK_FONT_SIZE}"
        f":x=w-tw-20:y=h-th-20"
    )
    vf_chain.append(drawtext_cmd)

    # 将所有视频滤镜合并成一个字符串
    full_vf_string = ",".join(vf_chain)
    print(f"   [滤镜链调试] {full_vf_string}")


    # --- 构建完整的 FFmpeg 命令 ---
    cmd = [
        "ffmpeg",
        "-y",
        "-hwaccel", "cuda",             # 硬件解码
        "-i", input_path,
        # 核心：应用上面构建的复杂滤镜链
        "-vf", full_vf_string,
        "-c:v", "h264_nvenc",           # N卡硬件编码
        "-preset", "p4",                # 编码质量平衡
        "-b:v", "8M",                   # 稍微提高一点比特率以应对滤镜细节
    ]

    # --- 音频处理逻辑 (保持不变) ---
    if has_audio:
        print(f"   [音频处理] 正在标准化响度至 {AUDIO_TARGET_LUFS} LUFS...")
        cmd.extend([
            "-af", f"loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TRUE_PEAK}:LRA={AUDIO_LRA}",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100"
        ])
    else:
        print("   [音频处理] 原视频无音轨，保持静音")

    cmd.append(output_path)
    
    try:
        # 运行命令
        # 如果想看FFmpeg详细报错，把 stderr=subprocess.PIPE 改成 stderr=None
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        # 捕捉到错误时，尝试打印出 stderr 以便调试（比如字体找不到的问题）
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "未知错误"
        print(f"[FFmpeg 错误] {error_msg}")
        print("【提示】如果是字体错误，请检查脚本开头的 FONT_FILE_PATH 设置。")
        return False

# ==========================================
# --- 辅助函数 & 下载逻辑 (保持不变) ---
# ==========================================
# (为了篇幅，这部分省略，与上一版本完全相同，请直接复制使用)
def ensure_dir(directory):
    if not os.path.exists(directory): os.makedirs(directory)

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

# ==========================================
# --- 处理流程逻辑 ---
# ==========================================

def process_videos_in_directory(directory):
    print(f"\n>>> 开始全流程处理 (滤镜+水印+1080p+NVENC+音频规范) <<<")
    files = [f for f in os.listdir(directory) if f.endswith(".mp4")]
    if not files:
        print("目录为空。")
        return

    for filename in files:
        filepath = os.path.join(directory, filename)
        temp_filepath = os.path.join(directory, f"temp_{filename}")
        
        try:
            # 读取信息
            clip = VideoFileClip(filepath)
            w, h = clip.size
            ratio = w / h
            has_audio = clip.audio is not None
            clip.close() 
            
            # 1. 筛选 16:9
            if not (TARGET_RATIO - RATIO_TOLERANCE <= ratio <= TARGET_RATIO + RATIO_TOLERANCE):
                print(f"[删除] {filename} | 宽高比不符 ({w}x{h})")
                os.remove(filepath)
                continue

            # 2. 强制所有视频过一遍处理流程
            print(f"[开始处理] {filename} | 添加滤镜与水印...")
            
            # 调用新的处理函数
            success = ffmpeg_process_nvenc(filepath, temp_filepath, has_audio)
            
            if success:
                os.remove(filepath)
                os.rename(temp_filepath, filepath)
                print(f"[成功] {filename} 处理完毕")
            else:
                print(f"[失败] {filename} 处理出错，跳过")
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
        time.sleep(20)

    print(f"\n=== 下载结束，开始后期处理 ===")
    if total_downloaded > 0 or len(os.listdir(SAVE_DIR)) > 0:
        process_videos_in_directory(SAVE_DIR)
    print("\n=== 全部完成 ===")

if __name__ == "__main__":
    main()