"""
Mermaid Video Generator V10.9
-----------------------------
Professional automated video production with dynamic captions.
Features: 
- Material standardization with NVENC acceleration.
- Lossless concatenation with MoviePy 2.x.
- Dynamic caption generation via OpenAI.
- Looping animated overlays (Mermaid) at fixed intervals.
- Enhanced dynamic captions with random font size, opacity, and floating effect.
"""

import os
import random
import json
import subprocess
import re
import warnings
import sys

# --- Environment & Library Checks ---
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")

try:
    from moviepy import VideoFileClip, concatenate_videoclips
    from pydub import AudioSegment
    from pydub.effects import normalize
    from openai import OpenAI
except ImportError as err:
    print(f"❌ Missing required library: {err}")
    sys.exit(1)

# ================== 1. GLOBAL CONSTANTS ==================
USE_OPENAI = True
OPENAI_MODEL = "gpt-3.5-turbo"
BASE_DIR = r"H:\OliverAI\resources\mermaid-0202"
CATEGORIES = ["1_fish", "2_turtle", "3_coral"]
TARGET_DURATION = 3 * 60  # Seconds
FPS = 30
VIDEO_BITRATE = "12M"
FONT_PATH = r"C:\Windows\Fonts\arial.ttf"

PATHS = {
    "music": os.path.join(BASE_DIR, "music"),
    "bg": os.path.join(BASE_DIR, "background"),
    "mermaid": os.path.join(BASE_DIR, "mermaid_assets"),
    "temp_std": os.path.join(BASE_DIR, "temp_standardized"),
    "temp_video": os.path.join(BASE_DIR, "temp_video.mp4"),
    "temp_audio": os.path.join(BASE_DIR, "temp_audio.mp3"),
    "overlay_json": os.path.join(BASE_DIR, "overlay_plan.json"),
    "output": os.path.join(BASE_DIR, "FINAL_STABLE_V10_PRO.mp4")
}

# Ensure workspaces exist
os.makedirs(PATHS["temp_std"], exist_ok=True)


# ================== 2. LOGIC MODULES ==================

def get_video_duration(path):
    """Retrieves video duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=False)
    return float(result.stdout.strip()) if result.stdout else 0.0


def fetch_openai_captions():
    """Fetches poetic captions from OpenAI API."""
    if not USE_OPENAI:
        return ["Ocean breathes in silence"] * 10

    print("🤖 [Step 0] Requesting captions from OpenAI...")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY not found in environment!")
        return ["Deep sea peace", "Silent blue world"]

    client = OpenAI(api_key=api_key)
    prompt = (
        "Generate 50 short, calm, poetic English captions for deep ocean relaxation. "
        "Return ONLY a JSON array of strings. 6-12 words per phrase."
    )
    try:
        resp = client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": prompt}])
        content = resp.choices[0].message.content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()
        return json.loads(content)
    except (json.JSONDecodeError, KeyError, Exception) as err:
        print(f"⚠️ OpenAI fetching failed: {err}")
        return ["Serene waters embrace the soul", "A quiet rhythm beneath the waves"]


def standardize_material(input_path, output_path):
    """Standardizes video to 1080p 30fps with NVENC."""
    v_filter = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps={FPS},setpts=PTS-STARTPTS"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", input_path,
        "-vf", v_filter, "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", VIDEO_BITRATE,
        "-pix_fmt", "yuv420p", "-an", output_path
    ]
    subprocess.run(cmd, check=True)


def generate_overlay_plan(total_duration):
    """Generates JSON plan for captions and 5s mermaid loops."""
    print("📝 [Step 4] Generating randomized overlay plan...")
    raw_captions = fetch_openai_captions()
    random.shuffle(raw_captions)

    plan = {
        "mermaid": {"enable": True, "scale": 0.18, "x": 20, "y": 20, "segments": []},
        "captions": []
    }

    # Assign captions
    cursor = 20
    for text in raw_captions:
        if cursor + 15 > total_duration:
            break
        plan["captions"].append({"start": cursor, "end": cursor + 8, "text": text})
        cursor += random.randint(55, 95)

    # Assign Mermaid (Fixed 5s duration)
    m_cursor = 45
    while m_cursor + 5 < total_duration:
        plan["mermaid"]["segments"].append({"start": m_cursor, "end": m_cursor + 5})
        m_cursor += random.randint(180, 400)

    with open(PATHS["overlay_json"], "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)


def final_fusion():
    """Final burn-in: captions + looping mermaid animation with dynamic subtitles."""
    print("🔥 [Step 5] Starting Final Fusion (FFmpeg Filter Complex)...")
    with open(PATHS["overlay_json"], "r", encoding="utf-8") as f:
        cfg = json.load(f)

    inputs = ["-i", PATHS["temp_video"], "-i", PATHS["temp_audio"]]
    filters = ["[0:v]setpts=PTS-STARTPTS[base]"]
    last_v = "[base]"

    # Mermaid overlay (unchanged)
    if cfg["mermaid"]["enable"]:
        m_assets = [os.path.join(PATHS["mermaid"], f) for f in os.listdir(PATHS["mermaid"]) if f.endswith(".webm")]
        if m_assets:
            inputs += ["-stream_loop", "-1", "-c:v", "libvpx-vp9", "-i", random.choice(m_assets)]
            m_en = " or ".join([f"between(t,{s['start']},{s['end']})" for s in cfg["mermaid"]["segments"]])
            filters.append(f"[2:v]scale=iw*{cfg['mermaid']['scale']}:-1,setpts=PTS-STARTPTS[m_v]")
            filters.append(f"{last_v}[m_v]overlay=x={cfg['mermaid']['x']}:y={cfg['mermaid']['y']}:enable='{m_en}'[v1]")
            last_v = "[v1]"

    # Dynamic drawtext for captions
    f_path_safe = FONT_PATH.replace("\\", "/").replace(":", "\\:")
    for i, cap in enumerate(cfg["captions"]):
        clean_txt = cap["text"].replace("'", "'\\\\\\''").replace(":", "\\:")

        # Random font size 42-56, y jitter for floating effect, random opacity
        fontsize = random.randint(42, 56)
        y_pos = f"h*0.8 + mod(t*5\,20)"
        opacity = round(random.uniform(0.7, 0.9), 2)
        shadow_opacity = round(random.uniform(0.4, 0.6), 2)

        draw = (
            f"drawtext=text='{clean_txt}':fontfile='{f_path_safe}':fontsize={fontsize}:fontcolor=white@{opacity}:"
            f"shadowcolor=black@{shadow_opacity}:shadowx=2:shadowy=2:x=(w-text_w)/2:y={y_pos}:"
            f"enable='between(t,{cap['start']},{cap['end']})'"
        )
        next_v = f"[v_txt{i}]"
        filters.append(f"{last_v}{draw}{next_v}")
        last_v = next_v

    cmd = [
        "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", last_v, "-map", "1:a:0", "-c:v", "h264_nvenc", "-preset", "p4",
        "-b:v", VIDEO_BITRATE, "-c:a", "aac", "-b:a", "192k", "-shortest", PATHS["output"]
    ]
    subprocess.run(cmd, check=True)


# ================== 3. MAIN WORKFLOW ==================

def main():
    """Main entry point for video production."""
    print("🎬 [Step 1] Selecting assets and inserting intros...")
    selected, current_duration = [], 0
    for cat in CATEGORIES:
        intro_path = os.path.join(BASE_DIR, "intro", f"{cat}.mp4")
        if os.path.exists(intro_path):
            current_duration += get_video_duration(intro_path)
            selected.append(intro_path)

        cat_dir = os.path.join(BASE_DIR, cat)
        files = [os.path.join(cat_dir, f) for f in os.listdir(cat_dir) if f.endswith(".mp4")]
        random.shuffle(files)
        for vid in files:
            if current_duration >= TARGET_DURATION + 5:
                break
            current_duration += get_video_duration(vid)
            selected.append(vid)

    print(f"⚡ [Step 2] Standardizing {len(selected)} clips...")
    std_paths = []
    for i, p in enumerate(selected):
        out = os.path.join(PATHS["temp_std"], f"std_{i}.mp4")
        standardize_material(p, out)
        std_paths.append(out)
        if i % 10 == 0:
            print(f"   Progress: {i}/{len(selected)}")

    print("🔗 [Step 3] Concatenating video stream (MoviePy 2.x)...")
    clips = [VideoFileClip(p) for p in std_paths]
    final_v = concatenate_videoclips(clips, method="chain").subclipped(0, TARGET_DURATION)
    final_v.write_videofile(
        PATHS["temp_video"], fps=FPS, audio=False, logger=None,
        ffmpeg_params=["-c:v", "h264_nvenc", "-b:v", VIDEO_BITRATE]
    )
    for c in clips:
        c.close()

    print("🎵 [Step 4] Mixing audio tracks and generating plan...")
    ms = TARGET_DURATION * 1000
    m_files = [os.path.join(PATHS["music"], f) for f in os.listdir(PATHS["music"]) if f.endswith(".mp3")]
    b_files = [os.path.join(PATHS["bg"], f) for f in os.listdir(PATHS["bg"]) if f.endswith(".mp3")]

    aud = normalize(AudioSegment.from_file(random.choice(m_files)))
    bgs = normalize(AudioSegment.from_file(random.choice(b_files))) - 18
    (aud.overlay(bgs))[:ms].export(PATHS["temp_audio"], format="mp3")

    generate_overlay_plan(TARGET_DURATION)

    final_fusion()

    print("🧹 [Step 6] Cleaning up workspace...")
    for f in os.listdir(PATHS["temp_std"]):
        os.remove(os.path.join(PATHS["temp_std"], f))
    os.remove(PATHS["temp_video"])
    os.remove(PATHS["temp_audio"])
    print(f"✨ Success! Final video at: {PATHS['output']}")


if __name__ == "__main__":
    main()
