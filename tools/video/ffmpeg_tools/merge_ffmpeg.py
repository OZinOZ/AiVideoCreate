import os
import random
import subprocess

# ==================== 用户参数区 ====================
MEDIA_DIR = "D:\\AImerge\\0105"           # 放置视频(mp4)和音频(mp3)的目录
OUTPUT_FILE = "final_video.mp4"  # 输出文件名
TARGET_MINUTES = 20          # 目标视频时长（分钟）
RESOLUTION = "1920x1080"      # 输出分辨率，例如 "1920x1080" 或 "1080x1920"
# ====================================================

# 自动创建 temp 目录
TEMP_DIR = os.path.join(MEDIA_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

def get_duration(file_path):
    """获取文件时长（秒）"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return float(result.stdout)

def random_loop_videos(video_files, target_duration):
    clips = []
    total_duration = 0
    durations = [get_duration(f) for f in video_files]

    while total_duration < target_duration:
        idx = random.randint(0, len(video_files)-1)
        clips.append(video_files[idx])
        total_duration += durations[idx]

    list_file = os.path.join(TEMP_DIR, "videos.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for clip in clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")
    return list_file

def random_loop_audios(audio_files, target_duration):
    durations = [get_duration(f) for f in audio_files]
    combined = []
    total_duration = 0
    i = 0
    while total_duration < target_duration:
        combined.append(audio_files[i % len(audio_files)])
        total_duration += durations[i % len(audio_files)]
        i += 1

    list_file = os.path.join(TEMP_DIR, "audios.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for a in combined:
            f.write(f"file '{os.path.abspath(a)}'\n")

    temp_audio = os.path.join(TEMP_DIR, "temp_audio.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-t", str(target_duration), "-c", "copy", temp_audio
    ])
    return temp_audio

def merge_video_audio():
    target_duration = TARGET_MINUTES * 60  # 分钟转秒

    # 自动搜索视频和音频
    all_files = [os.path.join(MEDIA_DIR, f) for f in os.listdir(MEDIA_DIR)]
    video_files = [f for f in all_files if f.endswith(".mp4")]
    audio_files = [f for f in all_files if f.endswith(".mp3")]

    if not video_files:
        raise ValueError("没有找到 mp4 视频文件")
    if not audio_files:
        raise ValueError("没有找到 mp3 音频文件")

    print("生成视频列表...")
    video_list_file = random_loop_videos(video_files, target_duration)

    temp_video = os.path.join(TEMP_DIR, "temp_video.mp4")
    print("合并视频中...")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", video_list_file,
        "-vf", f"scale={RESOLUTION}", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an", temp_video
    ])

    print("生成音频...")
    temp_audio = random_loop_audios(audio_files, target_duration)

    print("合成音频和视频...")
    subprocess.run([
        "ffmpeg", "-y", "-i", temp_video, "-i", temp_audio,
        "-c:v", "copy", "-c:a", "aac", "-shortest", OUTPUT_FILE
    ])

    print("完成！输出文件:", OUTPUT_FILE)

if __name__ == "__main__":
    merge_video_audio()
