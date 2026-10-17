import os
import random
import subprocess
from pathlib import Path

# ========== 用户配置 ==========
DIR = "D:\\AImerge\\0103"   # 输入目录名
TEMP_DIR = os.path.join(DIR, "temp_ffmpeg")
OUTPUT_VIDEO = "final_output.mp4"
TARGET_DURATION = 600  # 2.5 * 3600  # 2.5 小时，单位秒
UPSCALE_WIDTH = 1920           # 输出分辨率宽度
UPSCALE_HEIGHT = 1080          # 输出分辨率高度，横屏或竖屏可自行设置
VIDEO_FILTER_SCALE = f"scale={UPSCALE_WIDTH}:{UPSCALE_HEIGHT}:flags=lanczos"
# =============================

def list_files(folder, ext):
    return [str(p) for p in Path(folder).glob(f"*.{ext}")]

def get_media_duration(file_path):
    """获取视频或音频时长"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def generate_random_sequence(files, target_duration):
    """根据时长生成随机序列"""
    durations = [get_media_duration(f) for f in files]
    sequence = []
    total = 0.0
    while total < target_duration:
        idx = random.randint(0, len(files)-1)
        sequence.append(files[idx])
        total += durations[idx]
    return sequence

def concat_videos(sequence):
    """生成随机拼接的视频文件列表"""
    concat_list_path = os.path.join(TEMP_DIR, "video_list.txt")
    with open(concat_list_path, "w") as f:
        for video in sequence:
            # 统一分辨率
            temp_scaled = os.path.join(TEMP_DIR, os.path.basename(video))
            subprocess.run([
                "ffmpeg", "-y", "-i", video,
                "-vf", VIDEO_FILTER_SCALE,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                temp_scaled
            ])
            f.write(f"file '{temp_scaled}'\n")
    # 合并视频
    output_path = os.path.join(TEMP_DIR, "video_concat.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", output_path
    ])
    return output_path

def concat_audios(sequence):
    """生成随机拼接的音频文件"""
    concat_list_path = os.path.join(TEMP_DIR, "audio_list.txt")
    with open(concat_list_path, "w") as f:
        for audio in sequence:
            f.write(f"file '{audio}'\n")
    output_path = os.path.join(TEMP_DIR, "audio_concat.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-c:a", "aac", "-b:a", "192k", output_path
    ])
    return output_path

def merge_video_audio(video_file, audio_file, output_file):
    """合成最终视频和音频"""
    subprocess.run([
        "ffmpeg", "-y", "-i", video_file, "-i", audio_file,
        "-c:v", "copy", "-c:a", "aac", "-shortest", output_file
    ])

def main():

    os.makedirs(TEMP_DIR, exist_ok=True)
    video_files = list_files(DIR, "mp4")
    audio_files = list_files(DIR, "mp3")

    if not video_files:
        print("目录下没有 mp4 视频")
        return
    if not audio_files:
        print("目录下没有 mp3 音频")
        return

    print("生成随机视频序列...")
    video_sequence = generate_random_sequence(video_files, TARGET_DURATION)
    print("生成随机音频序列...")
    audio_sequence = generate_random_sequence(audio_files, TARGET_DURATION)

    print("合并视频...")
    final_video = concat_videos(video_sequence)
    print("合并音频...")
    final_audio = concat_audios(audio_sequence)

    print("合成最终视频...")
    merge_video_audio(final_video, final_audio, OUTPUT_VIDEO)

    print(f"完成！输出文件：{OUTPUT_VIDEO}")

if __name__ == "__main__":
    main()
