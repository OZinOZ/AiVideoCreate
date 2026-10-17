import subprocess
from pathlib import Path

# ================== 配置区 ==================
INPUT_DIR = Path("I:\\MyVideo\\0207")   # ← 改成你的目录
USE_FFMPEG_ROTATE = False                  # ← 关键开关！！
ROTATE_DURATION = 15
FPS = 30
VIDEO_EXTS = {".mp4", ".mov", ".mkv"}
# ===========================================


def run(cmd):
    subprocess.run(cmd, check=True)


def rename_videos(folder: Path):
    folder_name = folder.name
    videos = sorted([f for f in folder.iterdir() if f.suffix.lower() in VIDEO_EXTS])

    renamed = []
    for idx, video in enumerate(videos, start=1):
        new_name = f"{folder_name}_{idx:03d}{video.suffix}"
        new_path = folder / new_name
        if video.name != new_name:
            video.rename(new_path)
        renamed.append(new_path)

    return renamed


def extract_last_frame(video_path: Path, output_dir: Path):
    last_frame = output_dir / f"{video_path.stem}_last.png"

    run([
        "ffmpeg", "-y",
        "-sseof", "-0.1",
        "-i", str(video_path),
        "-vframes", "1",
        str(last_frame)
    ])

    return last_frame


def generate_rotate_video(png_path: Path, output_dir: Path):
    rotate_video = output_dir / f"{png_path.stem}_rotate.mp4"

    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(png_path),
        "-vf",
        (
            "scale=iw*1.05:ih*1.05,"
            "rotate=0.005*t:c=none,"
            "crop=iw/1.05:ih/1.05"
        ),
        "-t", str(ROTATE_DURATION),
        "-r", str(FPS),
        "-pix_fmt", "yuv420p",
        str(rotate_video)
    ])

    return rotate_video


def concat_video(original: Path, rotate: Path, output_dir: Path):
    final_video = output_dir / f"{original.stem}_final.mp4"
    concat_file = output_dir / f"{original.stem}_concat.txt"

    with open(concat_file, "w") as f:
        f.write(f"file '{original.resolve()}'\n")
        f.write(f"file '{rotate.resolve()}'\n")

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(final_video)
    ])

    concat_file.unlink(missing_ok=True)
    rotate.unlink(missing_ok=True)


def main():
    output_dir = INPUT_DIR / "output"
    output_dir.mkdir(exist_ok=True)

    print("🔁 重命名视频...")
    videos = rename_videos(INPUT_DIR)

    for video in videos:
        print("🎞 处理:", video.name)

        last_png = extract_last_frame(video, output_dir)
        print("🖼 抽取关键帧:", last_png.name)

        if USE_FFMPEG_ROTATE:
            rotate_mp4 = generate_rotate_video(last_png, output_dir)
            concat_video(video, rotate_mp4, output_dir)
            last_png.unlink(missing_ok=True)
            print("🎬 已生成最终视频")
        else:
            print("➡️ 保留 PNG，等待 Veo 使用")

    print("✅ 全部完成")


if __name__ == "__main__":
    main()