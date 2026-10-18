#!/usr/bin/env python
"""
FFmpeg 工具集 (合并自 ffmpeg.py / merge_ffmpeg.py / multi_ffmpeg.py / burn_subtitle.py /
video_color.py / video_4k_process.py / video_convert.py / music_process.py)

子命令:
    merge      随机拼接目录里的 mp4 + mp3, 生成 N 个指定时长的视频
    subtitle   把 JSON 字幕 (drawtext) 烧录进视频
    color      批量调色 (水下/珊瑚风格 curves + eq + 锐化)
    uhd        批量转 4K/60fps + 水印 + 去音轨 (目录 -> 目录)
    lastframe  重命名视频并抽取最后一帧, 可选生成旋转片段拼接在结尾
    music      两组音频 (主音乐 + 背景音) 随机拼接、交叉淡化、叠加成长音频

示例:
    python ffmpeg_tools.py merge -d D:/AImerge/0105 --minutes 25 --count 6
    python ffmpeg_tools.py merge -d D:/AImerge/0105 --minutes 20 --reencode --res 1920x1080
    python ffmpeg_tools.py subtitle -i in.mp4 -s subs.json -o out.mp4
    python ffmpeg_tools.py color -d H:/res/coral
    python ffmpeg_tools.py uhd -i Z:/sunset -o I:/out --watermark "© Tank&Tail Talk"
    python ffmpeg_tools.py lastframe -d I:/MyVideo/0207 --rotate
    python ffmpeg_tools.py music --music-dir H:/harp --bg-dir H:/water -o final.mp3 --minutes 90
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

VIDEO_EXTS = (".mp4", ".mov", ".mkv")
AUDIO_EXTS = (".mp3", ".wav")
DEFAULT_FONT = "C\\:/Windows/Fonts/arial.ttf" if os.name == "nt" else None


# ==========================================
# --- 通用工具 ---
# ==========================================

def run(cmd, quiet=False):
    """运行命令, 失败抛异常。quiet 时只在出错时输出 stderr。"""
    if not quiet:
        subprocess.run(cmd, check=True)
        return
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        sys.stderr.write((e.stderr or b"").decode("utf-8", errors="ignore")[-1500:] + "\n")
        raise


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def video_size(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def list_files(folder, exts):
    return sorted(str(Path(folder) / f) for f in os.listdir(folder) if f.lower().endswith(exts))


def encoder(args):
    """返回 (hwaccel参数, 视频编码参数)"""
    if getattr(args, "cpu", False):
        return [], ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    return ["-hwaccel", "cuda"], ["-c:v", "h264_nvenc", "-preset", "p4", "-b:v", getattr(args, "bitrate", "8M")]


def pick_until(files, target_sec, min_unique=2):
    """随机挑选文件直到累计时长 >= target_sec, 且避免只有同一个文件。"""
    durs = {f: duration(f) for f in files}
    picked, total = [], 0.0
    while total < target_sec:
        f = random.choice(files)
        picked.append(f)
        total += durs[f]
    if len(set(picked)) < min_unique and len(set(files)) >= min_unique:
        picked.append(random.choice([f for f in files if f != picked[0]]))
    return picked


def write_concat_list(path, files):
    with open(path, "w", encoding="utf-8") as f:
        for p in files:
            safe = os.path.abspath(p).replace("\\", "/").replace("'", r"'\''")
            f.write(f"file '{safe}'\n")


# ==========================================
# --- merge ---
# ==========================================

def cmd_merge(args):
    videos = list_files(args.dir, (".mp4",))
    audios = list_files(args.dir, (".mp3",))
    if not videos or not audios:
        sys.exit("目录下需要至少 1 个 mp4 和 1 个 mp3")
    temp = os.path.join(args.dir, "temp")
    os.makedirs(temp, exist_ok=True)
    target = args.minutes * 60
    start = time.time()

    for i in range(1, args.count + 1):
        print(f"\n▶ 生成第 {i}/{args.count} 个视频")
        vlist, alist = os.path.join(temp, f"v_{i}.txt"), os.path.join(temp, f"a_{i}.txt")
        write_concat_list(vlist, pick_until(videos, target))
        write_concat_list(alist, pick_until(audios, target))

        temp_v, temp_a = os.path.join(temp, f"video_{i}.mp4"), os.path.join(temp, f"audio_{i}.aac")
        print("  - 拼接视频" + (" (重编码)" if args.reencode else " (copy)"))
        if args.reencode:
            hw, enc = encoder(args)
            w, h = args.res.split("x")
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", vlist,
                 "-vf", f"scale={w}:{h}:flags=lanczos,setsar=1", *enc, "-an", temp_v])
        else:
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", vlist, "-c", "copy", "-an", temp_v])

        print("  - 拼接音频 (AAC)")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", alist, "-t", str(target),
             "-c:a", "aac", "-b:a", args.audio_bitrate, temp_a])

        print("  - 合成")
        out = os.path.join(args.dir, f"{args.prefix}_{i}.mp4" if args.count > 1 else f"{args.prefix}.mp4")
        run(["ffmpeg", "-y", "-i", temp_v, "-i", temp_a, "-map", "0:v:0", "-map", "1:a:0",
             "-c", "copy", "-shortest", out])
        print(f"  ✔ {out}")

    if args.clean:
        shutil.rmtree(temp, ignore_errors=True)
    used = int(time.time() - start)
    print(f"\n✅ 全部完成, 用时 {used // 60} 分 {used % 60} 秒")


# ==========================================
# --- subtitle ---
# ==========================================

def escape_drawtext(text):
    for a, b in (("\\", "\\\\"), ("'", "\\'"), (":", "\\:"), ("%", "\\%")):
        text = text.replace(a, b)
    return text


def cmd_subtitle(args):
    with open(args.subs, encoding="utf-8") as f:
        subs = json.load(f)
    font = f":fontfile='{args.font}'" if args.font else ""
    filters = []
    for item in subs:
        start = item["time"]
        end = start + item.get("duration", args.seconds)
        filters.append(
            f"drawtext=text='{escape_drawtext(item['text'])}'{font}:fontsize={args.size}"
            f":fontcolor={args.color}@{args.opacity}:x=(w-text_w)/2:y=h*{args.y}"
            f":enable='between(t,{start},{end})'")
    hw, enc = encoder(args)
    run(["ffmpeg", "-y", *hw, "-i", args.input, "-vf", ",".join(filters), *enc, "-c:a", "copy", args.output])
    print("✅ 字幕已成功烧录完成")


# ==========================================
# --- color ---
# ==========================================

COLOR_PRESETS = {
    # 水下: 补红、压蓝、提对比/饱和、轻锐化
    "underwater": ["curves=r='0/0 0.5/0.6 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.45 1/1'",
                   "eq=contrast=1.15:saturation=1.3:brightness=-0.02",
                   "unsharp=5:5:1.0:5:5:0.0"],
    "vivid": ["eq=contrast=1.1:saturation=1.25", "unsharp=3:3:0.5:3:3:0.0"],
}


def cmd_color(args):
    out_dir = args.output or os.path.join(args.dir, "processed_color")
    os.makedirs(out_dir, exist_ok=True)
    files = list_files(args.dir, VIDEO_EXTS)
    hw, enc = encoder(args)
    vf = ",".join(COLOR_PRESETS[args.preset])
    print(f"找到 {len(files)} 个视频, 预设: {args.preset}")
    for i, f in enumerate(files, 1):
        name = os.path.basename(f)
        print(f"[{i}/{len(files)}] {name}")
        try:
            run(["ffmpeg", "-y", *hw, "-i", f, "-vf", vf, *enc, "-c:a", "copy",
                 os.path.join(out_dir, name)], quiet=True)
        except subprocess.CalledProcessError:
            print(f"--- 失败: {name}")
    print(f"\n完成: {out_dir}")


# ==========================================
# --- uhd ---
# ==========================================

def cmd_uhd(args):
    os.makedirs(args.output, exist_ok=True)
    files = list_files(args.input, VIDEO_EXTS)
    W, H = 3840, 2160
    hw = [] if args.cpu else ["-hwaccel", "cuda"]
    if args.cpu:
        enc = ["-c:v", "libx264", "-preset", "medium", "-b:v", args.bitrate]
    else:
        enc = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr_hq", "-b:v", args.bitrate,
               "-maxrate", args.maxrate, "-bufsize", args.bufsize, "-profile:v", "high", "-level", "5.2"]
    font = f":fontfile='{args.font}'" if args.font else ""
    print(f"🎬 发现 {len(files)} 个视频")
    for i, f in enumerate(files, 1):
        name = os.path.basename(f)
        out = os.path.join(args.output, f"UHD{args.fps}_{os.path.splitext(name)[0]}.mp4")
        if os.path.exists(out):
            print(f"⏩ 跳过: {name}"); continue
        try:
            w, _ = video_size(f)
            chain = []
            if not args.watermark_only:
                chain += [f"scale={W}:{H}:force_original_aspect_ratio=decrease", f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"]
                if w < W:
                    chain.append("unsharp=3:3:0.4")
                chain += [f"fps={args.fps}", f"eq=saturation={args.saturation}:contrast={args.contrast}"]
                if args.vignette:
                    chain.append("vignette=PI/4")
            if args.watermark:
                chain.append(f"drawtext=text='{args.watermark}'{font}:fontsize=48:fontcolor=white@0.5:x=w-tw-40:y=h-th-40")
            print(f"⚙️ [{i}/{len(files)}] {name}")
            cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *hw, "-i", f]
            if chain:
                cmd += ["-vf", ",".join(chain)]
            run([*cmd, *enc, "-pix_fmt", "yuv420p", "-an", "-map_metadata", "-1", out])
            print("✅ 完成")
        except Exception as e:
            print(f"❌ 失败: {name} | {e}")


# ==========================================
# --- lastframe ---
# ==========================================

def cmd_lastframe(args):
    folder = Path(args.dir)
    out_dir = folder / "output"
    out_dir.mkdir(exist_ok=True)
    videos = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTS)

    renamed = []
    if args.rename:
        print("🔁 重命名视频...")
        for idx, v in enumerate(videos, 1):
            new = folder / f"{folder.name}_{idx:03d}{v.suffix}"
            if v != new:
                v.rename(new)
            renamed.append(new)
    else:
        renamed = videos

    for v in renamed:
        print("🎞 处理:", v.name)
        png = out_dir / f"{v.stem}_last.png"
        run(["ffmpeg", "-y", "-sseof", "-0.1", "-i", str(v), "-vframes", "1", str(png)], quiet=True)
        print("🖼 抽取关键帧:", png.name)
        if args.rotate:
            rot = out_dir / f"{v.stem}_rotate.mp4"
            run(["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-vf",
                 "scale=iw*1.05:ih*1.05,rotate=0.005*t:c=none,crop=iw/1.05:ih/1.05",
                 "-t", str(args.rotate_seconds), "-r", str(args.fps), "-pix_fmt", "yuv420p", str(rot)], quiet=True)
            lst = out_dir / f"{v.stem}_concat.txt"
            write_concat_list(lst, [str(v), str(rot)])
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                 str(out_dir / f"{v.stem}_final.mp4")], quiet=True)
            lst.unlink(missing_ok=True)
            rot.unlink(missing_ok=True)
            png.unlink(missing_ok=True)
            print("🎬 已生成最终视频")
    print("✅ 全部完成")


# ==========================================
# --- music ---
# ==========================================

def cmd_music(args):
    try:
        from pydub import AudioSegment
        from pydub.effects import normalize
    except ImportError:
        sys.exit("需要安装 pydub: pip install pydub")
    target_ms = args.minutes * 60 * 1000

    def build(folder, crossfade, shuffle_each_loop):
        files = list_files(folder, AUDIO_EXTS)
        if not files:
            sys.exit(f"{folder} 里没有音频文件")
        random.shuffle(files)
        combined = AudioSegment.empty()
        while len(combined) < target_ms:
            if shuffle_each_loop:
                random.shuffle(files)
            for f in files:
                if len(combined) >= target_ms:
                    break
                s = normalize(AudioSegment.from_file(f))
                combined = s if len(combined) == 0 else combined.append(s, crossfade=crossfade)
        return combined[:target_ms]

    print("正在处理主音乐...")
    music = build(args.music_dir, args.music_crossfade, False)
    if args.bg_dir:
        print("正在处理背景音...")
        bg = build(args.bg_dir, args.bg_crossfade, True) - args.bg_db
        music = music.overlay(bg)
    print(f"正在导出到: {args.output}")
    music.export(args.output, format="mp3", bitrate="192k")
    print("✅ 全部完成")


# ==========================================
# --- 入口 ---
# ==========================================

def build_parser():
    p = argparse.ArgumentParser(description="FFmpeg 工具集", epilog=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_enc(sp, bitrate="8M"):
        sp.add_argument("--cpu", action="store_true", help="使用 libx264 而非 NVENC")
        sp.add_argument("--bitrate", default=bitrate)

    s = sub.add_parser("merge", help="随机拼接 mp4 + mp3")
    s.add_argument("-d", "--dir", required=True, help="包含 mp4/mp3 的目录")
    s.add_argument("--minutes", type=float, default=20, help="每个视频时长(分钟)")
    s.add_argument("--count", type=int, default=1, help="输出数量")
    s.add_argument("--prefix", default="final")
    s.add_argument("--reencode", action="store_true", help="重编码并统一分辨率 (默认流复制, 更快)")
    s.add_argument("--res", default="1920x1080")
    s.add_argument("--audio-bitrate", default="192k")
    s.add_argument("--clean", action="store_true", help="完成后删除 temp 目录")
    add_enc(s)
    s.set_defaults(fn=cmd_merge)

    s = sub.add_parser("subtitle", help="烧录 JSON 字幕")
    s.add_argument("-i", "--input", required=True)
    s.add_argument("-s", "--subs", required=True, help='JSON: [{"time": 秒, "text": "...", "duration": 可选}]')
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--seconds", type=float, default=4, help="每条字幕默认显示秒数")
    s.add_argument("--size", type=int, default=42)
    s.add_argument("--color", default="white")
    s.add_argument("--opacity", type=float, default=0.85)
    s.add_argument("--y", type=float, default=0.75, help="垂直位置 (占高度比例)")
    s.add_argument("--font", default=DEFAULT_FONT)
    add_enc(s)
    s.set_defaults(fn=cmd_subtitle)

    s = sub.add_parser("color", help="批量调色")
    s.add_argument("-d", "--dir", required=True)
    s.add_argument("-o", "--output", help="默认 <dir>/processed_color")
    s.add_argument("--preset", choices=list(COLOR_PRESETS), default="underwater")
    add_enc(s)
    s.set_defaults(fn=cmd_color)

    s = sub.add_parser("uhd", help="批量转 4K 60fps")
    s.add_argument("-i", "--input", required=True)
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--fps", type=int, default=60)
    s.add_argument("--maxrate", default="75M")
    s.add_argument("--bufsize", default="110M")
    s.add_argument("--saturation", type=float, default=1.18)
    s.add_argument("--contrast", type=float, default=1.08)
    s.add_argument("--vignette", action="store_true")
    s.add_argument("--watermark", default="© Tank&Tail Talk", help='空字符串 "" 表示不加水印')
    s.add_argument("--watermark-only", action="store_true", help="只加水印, 不缩放/调色")
    s.add_argument("--font", default=DEFAULT_FONT)
    add_enc(s, "55M")
    s.set_defaults(fn=cmd_uhd)

    s = sub.add_parser("lastframe", help="抽取最后一帧 (可选旋转片段)")
    s.add_argument("-d", "--dir", required=True)
    s.add_argument("--rename", action="store_true", help="按 目录名_001 重命名视频")
    s.add_argument("--rotate", action="store_true", help="生成旋转片段并拼到结尾 (否则只保留 PNG)")
    s.add_argument("--rotate-seconds", type=int, default=15)
    s.add_argument("--fps", type=int, default=30)
    s.set_defaults(fn=cmd_lastframe)

    s = sub.add_parser("music", help="拼接并混合长音频")
    s.add_argument("--music-dir", required=True)
    s.add_argument("--bg-dir", help="背景音目录 (可选)")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--minutes", type=float, default=90)
    s.add_argument("--music-crossfade", type=int, default=3000, help="毫秒")
    s.add_argument("--bg-crossfade", type=int, default=5000, help="毫秒")
    s.add_argument("--bg-db", type=float, default=20, help="背景音降低多少 dB")
    s.set_defaults(fn=cmd_music)
    return p


def main():
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中断。")
