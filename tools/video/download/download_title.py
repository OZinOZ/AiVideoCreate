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

# --- 季节与分类设置 (每次运行前修改这里) ---
CURRENT_SEASON = "Winter"  # 可选: "Winter", "Autumn", "Summer", "Spring"
SEARCH_QUERY = "snow forest winter" # 对应季节的搜索词

SAVE_DIR = f"./downloads/{CURRENT_SEASON}_Collection" # 自动按季节分目录
MAX_DOWNLOADS = 5
BATCH_SIZE = 5

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# --- 季节配色配置 (文字颜色) ---
SEASON_COLORS = {
    "Winter": "0x00FFFF",  # 青色/冰蓝
    "Autumn": "0xFFAA00",  # 橙色/琥珀
    "Summer": "0xFFDD00",  # 金色
    "Spring": "0x55FF55",  # 嫩绿
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
# Windows 字体路径 (必填，否则片头无法生成文字)
# 建议去 C:/Windows/Fonts/ 找一个喜欢的 .ttf 文件复制路径到这里
# 如果是 Linux/Mac，通常设为 None FFmpeg 能自动找，但 Windows 必须指定
FONT_FILE_PATH = "C:/Windows/Fonts/arial.ttf" 
# FONT_FILE_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" # Linux示例

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
        return bool(data.get("streams"))
    except:
        return False

def generate_intro_video(output_path, season):
    """
    使用 FFmpeg 纯代码生成一个 3 秒的黑底文字片头
    """
    if os.path.exists(output_path):
        return True
    
    print(f"[片头生成] 正在制作 {season} 风格的 Intro...")
    
    color = SEASON_COLORS.get(season, "white")
    font_cmd = f":fontfile='{FONT_FILE_PATH}'" if FONT_FILE_PATH else ""
    
    # 复杂的 FFmpeg 滤镜链：
    # 1. color=c=black: 生成黑底
    # 2. drawtext 1: 居中写 Scenery Hub
    # 3. drawtext 2: 下方写 Season Collection (带淡入效果)
    # 4. fade: 视频首尾淡入淡出
    
    vf_graph = (
        f"color=c=black:s={TARGET_WIDTH}x{TARGET_HEIGHT}:d=3,"
        f"drawtext=text='Scenery Hub'{font_cmd}:fontcolor=white:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2-40,"
        f"drawtext=text='{season} Collection'{font_cmd}:fontcolor={color}:fontsize=40:x=(w-text_w)/2:y=(h-text_h)/2+60:alpha='if(lt(t,0.5),0,if(lt(t,2.5),1,0))',"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st=2.5:d=0.5"
    )

    # 生成一个带静音音轨的片头 (方便后续拼接)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", # 虚拟静音源
        "-filter_complex", f"{vf_graph}[v]", # 视频流生成
        "-map", "[v]", "-map", "0:a", # 映射视频和静音音频
        "-t", "3", # 强制时长3秒
        "-c:v", "libx264", "-preset", "ultrafast", # 片头用CPU快速生成即可，不用NVENC，兼容性更好
        "-c:a", "aac",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"[片头生成] 成功: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[片头生成失败] {e.stderr.decode('utf-8', errors='ignore')}")
        return False

def ffmpeg_process_concat(intro_path, main_video_path, output_path, has_audio):
    """
    拼接 Intro + 主视频，并进行滤镜/水印/NVENC处理
    这是最高难度的 FFmpeg 命令：Complex Filtergraph
    """
    
    # --- 1. 构建主视频的处理链 (Scale + Filter + Watermark) ---
    # 注意：我们不能直接在这里转码，我们要先把主视频处理成流，再和 Intro 拼接
    
    # 构建滤镜字符串
    font_config = f":fontfile='{FONT_FILE_PATH}'" if FONT_FILE_PATH else ""
    
    # 主视频滤镜: 缩放 -> 调色 -> 暗角 -> 水印
    # 注意：水印只加在主视频上，不加在片头上！
    main_vf = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT},"
        f"eq=saturation={FILTER_SATURATION}:contrast={FILTER_CONTRAST},"
        f"{'vignette=PI/5,' if ENABLE_VIGNETTE else ''}"
        f"drawtext=text='{WATERMARK_TEXT}'{font_config}:fontcolor=white@{WATERMARK_OPACITY}:fontsize={WATERMARK_FONT_SIZE}:x=w-tw-20:y=h-th-20"
    )
    
    # --- 2. 拼接逻辑 (Concat) ---
    # 输入0: Intro (已生成好)
    # 输入1: Main Video (原始素材)
    # 逻辑: 
    #   [1:v] 经过 main_vf 处理 -> [main_v_processed]
    #   [0:v] (Intro) + [main_v_processed] -> Concat -> [out_v]
    #   音频: 如果主视频有音频，就用 Intro音频(静音) + 主视频音频。如果没有，全用静音。
    
    filter_complex = f"[1:v]{main_vf}[main_v]; [0:v][0:a][main_v]{'[1:a]' if has_audio else '[0:a]'}concat=n=2:v=1:a=1[out_v][out_a]"
    
    # 解释上面那行鬼画符：
    # [1:v]{main_vf}[main_v] : 把第2个输入(主视频)进行滤镜处理，命名为 [main_v]
    # [0:v][0:a] : 取第1个输入(Intro)的视频和音频
    # [main_v] : 取处理好的主视频
    # {'[1:a]' if has_audio else '[0:a]'} : 如果主视频有声音，取它的声音[1:a]；如果没有，重复使用Intro的静音[0:a]来占位
    # concat=n=2:v=1:a=1 : 拼接2个片段，输出1个视频流，1个音频流
    
    # --- 3. 音频响度处理 (Loudnorm) ---
    # 拼接完后的音频 [out_a] 需要再过一次 loudnorm
    # 注意：loudnorm 只能处理有声的情况，如果全是静音可能不需要，但为了保险还是加上
    
    final_audio_filter = f"[out_a]loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TRUE_PEAK}:LRA={AUDIO_LRA}[final_a]" if has_audio else "[out_a]anullsink;[0:a]aformat=channel_layouts=stereo[final_a]" 
    # 修正：如果无声，直接用静音流输出，不跑loudnorm
    
    if not has_audio:
        # 如果主视频没声音，concat 已经拼了两个静音流，直接输出即可
        filter_complex = f"[1:v]{main_vf}[main_v]; [0:v][0:a][main_v][0:a]concat=n=2:v=1:a=1[out_v][final_a]"
    else:
        # 如果有声音，拼接后还要过响度
         filter_complex = f"[1:v]{main_vf}[main_v]; [0:v][0:a][main_v][1:a]concat=n=2:v=1:a=1[out_v][raw_a]; [raw_a]loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TRUE_PEAK}:LRA={AUDIO_LRA}[final_a]"

    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda", # 尝试解码加速
        "-i", intro_path,       # Input 0
        "-i", main_video_path,  # Input 1
        "-filter_complex", filter_complex,
        "-map", "[out_v]", "-map", "[final_a]",
        "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "8M",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[拼接失败] {e.stderr.decode('utf-8', errors='ignore')}")
        return False

# ==========================================
# --- 流程控制 ---
# ==========================================

def download_file(url, folder, prefix, file_id):
    # (同之前的代码，略，保持不变)
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
    # (同之前的代码，略，保持不变，记得把 API KEY 填进去)
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
    
    # 1. 准备片头
    intro_filename = f"Intro_{CURRENT_SEASON}.mp4"
    intro_path = os.path.join(directory, intro_filename)
    
    # 如果当前目录下没有这个片头，就生成一个
    if not generate_intro_video(intro_path, CURRENT_SEASON):
        print("无法生成片头，终止处理。请检查字体路径。")
        return

    print(f"\n>>> 开始全流程: 拼接Intro({CURRENT_SEASON}) + 滤镜 + 水印 <<<")
    
    files = [f for f in os.listdir(directory) if f.endswith(".mp4") and not f.startswith("Intro_")]
    
    for filename in files:
        filepath = os.path.join(directory, filename)
        temp_filepath = os.path.join(directory, f"temp_{filename}")
        
        try:
            has_audio = get_audio_info(filepath)
            print(f"[处理] {filename} | 音频: {has_audio} | 正在拼接...")

            # 调用拼接函数
            success = ffmpeg_process_concat(intro_path, filepath, temp_filepath, has_audio)
            
            if success:
                os.remove(filepath)
                if has_audio:
                    os.rename(temp_filepath, filepath)
                    print(f"[完成] 主目录")
                else:
                    dest_path = os.path.join(mute_dir, filename)
                    if os.path.exists(dest_path): os.remove(dest_path)
                    os.rename(temp_filepath, dest_path)
                    print(f"[完成] Mute目录")
            else:
                print(f"[失败] 跳过")
                if os.path.exists(temp_filepath): os.remove(temp_filepath)

        except Exception as e:
            print(f"[异常] {filename}: {e}")

def main():
    ensure_dir(SAVE_DIR)
    
    # 下载逻辑
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

    # 处理逻辑
    if total_downloaded > 0 or len([f for f in os.listdir(SAVE_DIR) if f.endswith(".mp4") and not f.startswith("Intro_")]) > 0:
        process_videos_in_directory(SAVE_DIR)
    
    print("\n=== 全部完成 ===")

if __name__ == "__main__":
    main()