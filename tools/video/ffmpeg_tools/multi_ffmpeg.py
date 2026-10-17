import os
import random
import subprocess
import time
import shutil

# ===================== 参数区（只改这里） =====================
MEDIA_DIR = "D:\\AImerge\\01052"          # mp4 + mp3 所在目录
TARGET_MINUTES = 25          # 每个视频长度（分钟）
NUM_OUTPUTS = 6              # 输出视频数量
OUTPUT_PREFIX = "final"      # 输出文件前缀
AUDIO_BITRATE = "192k"       # AAC 音频码率
FINAL_WIDTH = 1920
FINAL_HEIGHT = 1080
CRF = 18                     # 画质，16~20 都很好
ENCODER = "h264_nvenc"       # 编码速度 "libx264" for software "h264_nvenc" for hardware
PRESET = "p4"                # 编码速度, "veryfast" for software "p4" for hardware
CLEAN_TEMP = False           # 是否删除 temp 目录
# =============================================================

TEMP_DIR = os.path.join(MEDIA_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

def run(cmd):
    subprocess.run(cmd, check=True)

def duration(file):
    r = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", file],
        stdout=subprocess.PIPE
    )
    return float(r.stdout)

def build_concat_list(files, target_sec, name):
    if len(set(files)) < 2:
        raise RuntimeError("concat 至少需要 2 个不同文件")

    total = 0
    picked = []
    durs = {f: duration(f) for f in files}

    while total < target_sec:
        f = random.choice(files)
        picked.append(f)
        total += durs[f]

    if len(set(picked)) == 1:
        picked.append(random.choice([f for f in files if f != picked[0]]))

    path = os.path.join(TEMP_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        for p in picked:
            f.write(f"file '{os.path.abspath(p)}'\n")

    return path

def main():
    start = time.time()
    target_sec = TARGET_MINUTES * 60

    videos = [os.path.join(MEDIA_DIR, f)
              for f in os.listdir(MEDIA_DIR) if f.lower().endswith(".mp4")]

              
    audios = [os.path.join(MEDIA_DIR, f)
              for f in os.listdir(MEDIA_DIR) if f.lower().endswith(".mp3")]

    if len(videos) < 2 or len(audios) < 2:
        raise RuntimeError("mp4 / mp3 都必须 ≥ 2 个")

    for i in range(1, NUM_OUTPUTS + 1):
        print(f"\n▶ 生成第 {i} 个视频")

        vlist = build_concat_list(videos, target_sec, f"v_{i}.txt")
        alist = build_concat_list(audios, target_sec, f"a_{i}.txt")

        temp_video = os.path.join(TEMP_DIR, f"video_raw_{i}.mp4")
        temp_audio = os.path.join(TEMP_DIR, f"audio_{i}.aac")
        temp_final = os.path.join(TEMP_DIR, f"final_std_{i}.mp4")

        # 1️⃣ 极速拼接视频（不重编码）
        print("  - 拼接视频（copy）")
        run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", vlist,
            "-c", "copy",
            temp_video
        ])

        # 2️⃣ 拼接音频（统一 AAC）
        print("  - 拼接音频（AAC）")
        run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", alist,
            "-t", str(target_sec),
            "-c:a", "aac",
            "-b:a", AUDIO_BITRATE,
            temp_audio
        ])


        # 3️⃣ 最终标准化（唯一一次重编码）
        '''print("  - 最终标准化 1920x1080（一次性解决比例问题）")
        run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", temp_audio,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", f"scale={FINAL_WIDTH}:{FINAL_HEIGHT},setsar=1,setdar=16/9",
            "-c:v", ENCODER, 
            "-preset", PRESET,
            "-crf", str(CRF),
            "-c:a", "aac",
            "-shortest",
            temp_final
        ])'''

        print("  - 最终合并（流复制模式，不重新编码）")
        run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", temp_audio,
            "-c", "copy",        # 关键修改：直接复制流
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            temp_final
        ])

        out = os.path.join(
            MEDIA_DIR,
            f"{OUTPUT_PREFIX}_{i}.mp4" if NUM_OUTPUTS > 1 else f"{OUTPUT_PREFIX}.mp4"
        )

        os.replace(temp_final, out)
        print(f"  ✔ 输出完成：{out}")

    if CLEAN_TEMP:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    used = time.time() - start
    print(f"\n✅ 全部完成，用时 {int(used//60)} 分 {int(used%60)} 秒")

if __name__ == "__main__":
    main()
