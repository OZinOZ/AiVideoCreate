import json
import subprocess

VIDEO_INPUT = "input_90min.mp4"
VIDEO_OUTPUT = "output_90min_subtitled.mp4"
SUBTITLE_JSON = "subtitles_90min.json"

FONT_SIZE = 42
FONT_COLOR = "white"
FONT_OPACITY = 0.85
X_POS = "(w-text_w)/2"
Y_POS = "h*0.75"

def load_subtitles(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_drawtext_filters(subs):
    filters = []
    for item in subs:
        start = item["time"]
        end = start + 4  # 每条字幕显示 4 秒（可调）
        text = item["text"].replace("'", "\\'")
        filters.append(
            f"drawtext=text='{text}':"
            f"fontsize={FONT_SIZE}:"
            f"fontcolor={FONT_COLOR}@{FONT_OPACITY}:"
            f"x={X_POS}:y={Y_POS}:"
            f"enable='between(t,{start},{end})'"
        )
    return ",".join(filters)

def main():
    subtitles = load_subtitles(SUBTITLE_JSON)
    drawtext_filter = build_drawtext_filters(subtitles)

    cmd = [
        "ffmpeg", "-y",
        "-i", VIDEO_INPUT,
        "-vf", drawtext_filter,
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-b:v", "8M",
        "-c:a", "copy",
        VIDEO_OUTPUT
    ]

    subprocess.run(cmd, check=True)
    print("✅ 字幕已成功烧录完成")

if __name__ == "__main__":
    main()
