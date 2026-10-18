#!/usr/bin/env python
"""
统一素材下载 + 后期处理工具 (合并自 download*.py / pixabay_*.py)

目录结构 (SAVE_DIR):
    raw/    下载的原始文件 (处理成功后删除)
    ./      处理后的成品 (有声)
    mute/   处理后的成品 (无声, 仅 --split-mute 时)

处理模式 (--process):
    none     只下载, 不处理
    scale    仅缩放到目标分辨率, 音频直接复制          (原 download_parse)
    enhance  缩放 + 调色 + 暗角 + 水印 + 响度标准化     (原 download_mark / mute / audio)
    intro    enhance + 拼接季节片头 (含音频采样率修复)   (原 download_title / audio_fix)
    wash     去音轨/去元数据/随机翻转/微调速度/可选4K    (原 pixabay_download / _4k / _4k_chatgpt)

运行阶段 (--mode):
    download 只下载到 raw/
    process  只处理 raw/ 里已有的文件
    all      下载 + 处理 (默认)

示例:
    python media_downloader.py -q "forest drone" -d H:/resources/drone --process enhance --split-mute
    python media_downloader.py -q "sea beach drone 4k" -d H:/res/sea --process wash --res 4k --fps 60 --no-audio
    python media_downloader.py -q "snow forest" -d ./winter --process intro --season Winter
    python media_downloader.py -d H:/res/sea --mode process --process wash
    python media_downloader.py -q "cinematic ambient" --type image --source pexels --process none

API Key 通过环境变量 PEXELS_API_KEY / PIXABAY_API_KEY 提供。
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from urllib.parse import urlparse

import requests

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

RESOLUTIONS = {"1080": (1920, 1080), "4k": (3840, 2160)}
SEASON_COLORS = {
    "Winter": "0x00FFFF",
    "Autumn": "0xFFAA00",
    "Summer": "0xFFDD00",
    "Spring": "0x55FF55",
}
DEFAULT_FONT = "C\\:/Windows/Fonts/arial.ttf" if os.name == "nt" else None
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")


# ==========================================
# --- 通用小工具 ---
# ==========================================

def ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def probe(path):
    """用 ffprobe 读取视频信息: width/height/duration/has_audio。失败返回 None。"""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", path]
    try:
        data = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
        v = next(s for s in data["streams"] if s["codec_type"] == "video")
        has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
        dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
        return {"w": int(v["width"]), "h": int(v["height"]), "dur": dur, "has_audio": has_audio}
    except Exception as e:
        print(f"   [检测失败] {path}: {e}")
        return None


def run_ffmpeg(cmd, verbose=False):
    try:
        subprocess.run(cmd, check=True, stdout=None if verbose else subprocess.DEVNULL,
                       stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else "未知错误"
        print(f"[FFmpeg 错误] {msg[-1500:]}")
        print("【提示】如果是字体错误, 请检查 --font 参数。")
        return False


def video_encoder_args(args):
    """返回 (hwaccel参数, 编码参数)。--cpu 时使用 libx264。"""
    if args.cpu:
        return [], ["-c:v", "libx264", "-preset", "medium", "-b:v", args.bitrate, "-pix_fmt", "yuv420p"]
    enc = ["-c:v", "h264_nvenc", "-preset", "p4", "-b:v", args.bitrate, "-pix_fmt", "yuv420p"]
    return ["-hwaccel", "cuda"], enc


def drawtext(args, size, opacity, margin):
    font = f":fontfile='{args.font}'" if args.font else ""
    return (f"drawtext=text='{args.watermark}'{font}:fontcolor=white@{opacity}"
            f":fontsize={size}:x=w-tw-{margin}:y=h-th-{margin}")


# ==========================================
# --- API 与下载 ---
# ==========================================

def get_links(args, page):
    """返回 [{'id':..., 'url':...}]"""
    results = []
    try:
        if args.source == "pexels":
            if not PEXELS_API_KEY:
                print("[错误] 未设置 PEXELS_API_KEY"); return []
            headers = {"Authorization": PEXELS_API_KEY}
            params = {"query": args.query, "per_page": args.batch, "page": page}
            if args.type == "image":
                res = requests.get("https://api.pexels.com/v1/search",
                                   headers=headers, params=params, timeout=15)
                if res.status_code == 200:
                    for it in res.json().get("photos", []):
                        results.append({"id": str(it["id"]), "url": it["src"]["original"]})
            else:
                params["orientation"] = "landscape"
                res = requests.get("https://api.pexels.com/videos/search",
                                   headers=headers, params=params, timeout=15)
                if res.status_code == 200:
                    for it in res.json().get("videos", []):
                        files = sorted(it.get("video_files", []),
                                       key=lambda x: (x.get("width") or 0) * (x.get("height") or 0),
                                       reverse=True)
                        if files:
                            results.append({"id": str(it["id"]), "url": files[0]["link"]})
            if res.status_code != 200:
                print(f"[API错误] Pexels {res.status_code}: {res.text[:200]}")
        else:
            if not PIXABAY_API_KEY:
                print("[错误] 未设置 PIXABAY_API_KEY"); return []
            params = {"key": PIXABAY_API_KEY, "q": args.query, "per_page": args.batch, "page": page}
            if args.type == "image":
                res = requests.get("https://pixabay.com/api/", params=params, timeout=15)
                if res.status_code == 200:
                    for it in res.json().get("hits", []):
                        url = it.get("largeImageURL") or it.get("webformatURL")
                        if url:
                            results.append({"id": str(it["id"]), "url": url})
            else:
                params["orientation"] = "horizontal"
                if args.video_type:
                    params["video_type"] = args.video_type
                res = requests.get("https://pixabay.com/api/videos/", params=params, timeout=15)
                if res.status_code == 200:
                    order = ("large", "medium") if args.quality == "large" else ("medium", "large")
                    for it in res.json().get("hits", []):
                        vids = it.get("videos", {})
                        url = (vids.get(order[0], {}).get("url") or vids.get(order[1], {}).get("url")
                               or vids.get("small", {}).get("url"))
                        if url:
                            results.append({"id": str(it["id"]), "url": url})
            if res.status_code != 200:
                print(f"[API错误] Pixabay {res.status_code}: {res.text[:200]}")
    except Exception as e:
        print(f"[API异常] {e}")
    return results


def download_file(url, dest, show_progress=True):
    """先写入 .part 再重命名, 避免中断后留下损坏文件。"""
    tmp = dest + ".part"
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if show_progress and total:
                    bar = int(40 * done / total)
                    sys.stdout.write(f"\r   [{'=' * bar}{' ' * (40 - bar)}] {done / 1048576:.1f} MB")
                    sys.stdout.flush()
        if show_progress:
            print()
        os.replace(tmp, dest)
        return True
    except Exception as e:
        print(f"[下载错误] {url}: {e}")
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def guess_ext(url, media_type):
    ext = os.path.splitext(urlparse(url).path)[1]
    if not ext or len(ext) > 5:
        ext = ".jpg" if media_type == "image" else ".mp4"
    return ext


def already_have(args, name):
    base, _ = os.path.splitext(name)
    for folder in (args.save_dir, os.path.join(args.save_dir, "raw"), os.path.join(args.save_dir, "mute")):
        if os.path.exists(os.path.join(folder, name)):
            return True
        if folder == args.save_dir and os.path.exists(os.path.join(folder, f"{base}.mp4")):
            return True
    return False


def download_all(args, raw_dir):
    ensure_dir(raw_dir)
    total, page, empty = 0, 1, 0
    print(f"=== 下载: {args.source} | {args.type} | '{args.query}' | 目标 {args.max} 个 ===")
    while total < args.max:
        print(f"\n--- API 第 {page} 页 ---")
        links = get_links(args, page)
        if not links:
            empty += 1
            if empty >= 1:
                print("[-] 没有更多结果 (或 API 出错/额度耗尽)")
                break
        for item in links:
            if total >= args.max:
                break
            name = f"{args.source}_{item['id']}{guess_ext(item['url'], args.type)}"
            if already_have(args, name):
                print(f"[跳过] 已存在: {name}")
                continue
            dest_dir = args.save_dir if (args.type == "image" or args.process == "none") else raw_dir
            print(f"[下载中] {name}")
            if download_file(item["url"], os.path.join(dest_dir, name)):
                total += 1
        page += 1
        time.sleep(args.delay)
    print(f"\n[下载完成] 新增 {total} 个")
    return total


# ==========================================
# --- FFmpeg 处理: 各模式的命令构造 ---
# ==========================================

def enhance_vf(args, w, h):
    """缩放 -> 调色 -> 暗角 -> 水印"""
    chain = [f"scale={w}:{h}", f"eq=saturation={args.saturation}:contrast={args.contrast}"]
    if not args.no_vignette:
        chain.append("vignette=PI/5")
    chain.append(drawtext(args, args.wm_size, args.wm_opacity, 20))
    return ",".join(chain)


def audio_args(args, has_audio):
    if has_audio:
        return ["-af", f"loudnorm=I={args.lufs}:TP={args.true_peak}:LRA={args.lra}",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
    return []


def process_scale(args, src, dst, info):
    w, h = RESOLUTIONS[args.res]
    hw, enc = video_encoder_args(args)
    cmd = ["ffmpeg", "-y", *hw, "-i", src, "-vf", f"scale={w}:{h}", *enc, "-c:a", "copy", dst]
    return run_ffmpeg(cmd)


def process_enhance(args, src, dst, info):
    w, h = RESOLUTIONS[args.res]
    hw, enc = video_encoder_args(args)
    cmd = ["ffmpeg", "-y", *hw, "-i", src, "-vf", enhance_vf(args, w, h), *enc]
    if info["has_audio"]:
        cmd += ["-map", "0:v:0", "-map", "0:a:0", *audio_args(args, True)]
    else:
        cmd += ["-map", "0:v:0"]
    return run_ffmpeg(cmd + [dst])


def generate_intro(args, path):
    """生成 3 秒黑底文字片头 (带 44.1k 静音音轨, 方便拼接)"""
    if os.path.exists(path):
        return True
    w, h = RESOLUTIONS[args.res]
    color = SEASON_COLORS.get(args.season, "white")
    font = f":fontfile='{args.font}'" if args.font else ""
    print(f"[片头] 正在生成 {args.season} Intro ...")
    graph = (
        f"color=c=black:s={w}x{h}:d=3:r={args.fps},"
        f"drawtext=text='Scenery Hub'{font}:fontcolor=white:fontsize={h // 13}:x=(w-text_w)/2:y=(h-text_h)/2-40,"
        f"drawtext=text='{args.season} Collection'{font}:fontcolor={color}:fontsize={h // 27}"
        f":x=(w-text_w)/2:y=(h-text_h)/2+60:alpha='if(lt(t,0.5),0,if(lt(t,2.5),1,0))',"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st=2.5:d=0.5,setsar=1"
    )
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-filter_complex", f"{graph}[v]", "-map", "[v]", "-map", "0:a", "-t", "3",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-ar", "44100", path]
    return run_ffmpeg(cmd)


def process_intro(args, src, dst, info, intro_path=None):
    w, h = RESOLUTIONS[args.res]
    hw, enc = video_encoder_args(args)
    main_vf = enhance_vf(args, w, h) + f",fps={args.fps},setsar=1"
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    inputs = ["-i", intro_path, "-i", src]
    if info["has_audio"]:
        main_a = f"[1:a]{fmt}[ma];"
    else:
        # 无音轨: 生成与主视频等长的静音, 避免复用同一个音频 pad
        inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        main_a = f"[2:a]atrim=duration={info['dur']:.3f},{fmt}[ma];"
    fc = (f"[1:v]{main_vf}[mv];{main_a}"
          f"[0:v][0:a][mv][ma]concat=n=2:v=1:a=1[ov][ja];"
          f"[ja]loudnorm=I={args.lufs}:TP={args.true_peak}:LRA={args.lra}[oa]")
    cmd = ["ffmpeg", "-y", *hw, *inputs, "-filter_complex", fc, "-map", "[ov]", "-map", "[oa]",
           *enc, "-c:a", "aac", "-b:a", "192k", "-ar", "44100", dst]
    return run_ffmpeg(cmd)


def process_wash(args, src, dst, info):
    """去音轨/元数据, 随机翻转, 微调速度, 小于目标分辨率时锐化放大"""
    w, h = RESOLUTIONS[args.res]
    hw, enc = video_encoder_args(args)
    flip = "hflip," if random.random() > 0.5 else ""
    speed = random.uniform(0.995, 1.005)
    chain = [f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos",
             f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"]
    if info["w"] < w:
        chain.append("unsharp=3:3:0.5:3:3:0.0")
    chain += [f"{flip}fps={args.fps}", f"setpts={1 / speed:.5f}*PTS",
              f"eq=saturation={args.saturation}:contrast={args.contrast}"]
    if not args.no_vignette:
        chain.append("vignette=PI/4")
    chain.append(drawtext(args, args.wm_size, 0.5, 40 if args.res == "4k" else 20))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *hw, "-i", src,
           "-vf", ",".join(chain), *enc, "-map_metadata", "-1"]
    if not args.keep_audio:
        cmd.append("-an")
    return run_ffmpeg(cmd + [dst])


# ==========================================
# --- 处理流程控制 ---
# ==========================================

def process_all(args, raw_dir):
    if not os.path.isdir(raw_dir):
        print("[提示] raw/ 目录不存在, 无需处理")
        return
    files = sorted(f for f in os.listdir(raw_dir) if f.lower().endswith(VIDEO_EXTS))
    if not files:
        print("[提示] raw/ 里没有待处理的视频")
        return

    mute_dir = os.path.join(args.save_dir, "mute")
    intro_path = None
    if args.process == "intro":
        intro_path = os.path.join(args.save_dir, f"Intro_{args.season}_{args.res}.mp4")
        if not generate_intro(args, intro_path):
            print("[错误] 片头生成失败, 终止处理")
            return

    ratio_target = 16 / 9
    print(f"\n>>> 开始处理 {len(files)} 个文件 (模式: {args.process}, 分辨率: {args.res}) <<<")
    for name in files:
        src = os.path.join(raw_dir, name)
        base = os.path.splitext(name)[0]
        out_name = f"{base}.mp4"
        tmp = os.path.join(raw_dir, f"tmp_{out_name}")
        try:
            if os.path.getsize(src) < args.min_size_mb * 1024 * 1024:
                print(f"[删除] {name} | 文件过小")
                os.remove(src); continue
            info = probe(src)
            if not info:
                print(f"[跳过] {name} | 无法解析 (保留原文件)")
                continue
            ratio = info["w"] / info["h"]
            if abs(ratio - ratio_target) > args.ratio_tol:
                print(f"[删除] {name} | 宽高比不符 ({info['w']}x{info['h']})")
                os.remove(src); continue
            if not (args.min_dur <= info["dur"] <= args.max_dur):
                print(f"[删除] {name} | 时长不符 ({info['dur']:.1f}s)")
                os.remove(src); continue
            if args.process == "scale" and (info["w"], info["h"]) == RESOLUTIONS[args.res]:
                print(f"[完美] {name} | 无需转码")
                os.replace(src, os.path.join(args.save_dir, name)); continue

            print(f"[处理] {name} | {info['w']}x{info['h']} {info['dur']:.1f}s | 音轨: {'有' if info['has_audio'] else '无'}")
            if args.process == "scale":
                ok = process_scale(args, src, tmp, info)
            elif args.process == "enhance":
                ok = process_enhance(args, src, tmp, info)
            elif args.process == "intro":
                ok = process_intro(args, src, tmp, info, intro_path)
            else:
                ok = process_wash(args, src, tmp, info)

            if not ok:
                print(f"[失败] {name} (保留原文件)")
                if os.path.exists(tmp): os.remove(tmp)
                continue

            to_mute = args.split_mute and not info["has_audio"] and args.process != "wash"
            dest_dir = mute_dir if to_mute else args.save_dir
            ensure_dir(dest_dir)
            dest = os.path.join(dest_dir, out_name)
            os.replace(tmp, dest)
            os.remove(src)
            print(f"[完成] -> {'mute/' if to_mute else ''}{out_name}")
        except Exception as e:
            print(f"[异常] {name}: {e}")
            if os.path.exists(tmp): os.remove(tmp)


# ==========================================
# --- 入口 ---
# ==========================================

def build_parser():
    p = argparse.ArgumentParser(description="Pexels/Pixabay 素材下载 + FFmpeg 处理",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    g = p.add_argument_group("下载")
    g.add_argument("-q", "--query", default="", help="搜索关键词 (英文效果最好)")
    g.add_argument("-d", "--save-dir", default="./downloads", help="输出目录")
    g.add_argument("--source", choices=["pexels", "pixabay"], default="pixabay")
    g.add_argument("--type", choices=["video", "image"], default="video")
    g.add_argument("--max", type=int, default=10, help="最大下载数量")
    g.add_argument("--batch", type=int, default=5, help="每页数量")
    g.add_argument("--delay", type=float, default=2, help="翻页间隔秒数 (避免触发限流)")
    g.add_argument("--quality", choices=["medium", "large"], default="medium", help="Pixabay 视频质量偏好")
    g.add_argument("--video-type", choices=["film", "animation"], default=None, help="Pixabay video_type")
    g.add_argument("--mode", choices=["download", "process", "all"], default="all")

    g = p.add_argument_group("处理")
    g.add_argument("--process", choices=["none", "scale", "enhance", "intro", "wash"], default="enhance")
    g.add_argument("--res", choices=list(RESOLUTIONS), default="1080")
    g.add_argument("--fps", type=int, default=30)
    g.add_argument("--bitrate", default=None, help="视频码率, 默认 1080p=8M, 4k=30M")
    g.add_argument("--cpu", action="store_true", help="使用 libx264 而非 NVENC")
    g.add_argument("--split-mute", action="store_true", help="无音轨的成品移入 mute/")
    g.add_argument("--keep-audio", action="store_true", help="wash 模式保留音轨")
    g.add_argument("--season", default="Winter", choices=list(SEASON_COLORS), help="intro 模式的季节")
    g.add_argument("--min-dur", type=float, default=0)
    g.add_argument("--max-dur", type=float, default=10 ** 6)
    g.add_argument("--min-size-mb", type=float, default=0, help="小于该大小的文件视为损坏并删除")
    g.add_argument("--ratio-tol", type=float, default=0.05, help="16:9 宽高比容差")

    g = p.add_argument_group("滤镜 / 水印 / 音频")
    g.add_argument("--saturation", type=float, default=1.2)
    g.add_argument("--contrast", type=float, default=1.08)
    g.add_argument("--no-vignette", action="store_true")
    g.add_argument("--watermark", default="© Scenery Hub")
    g.add_argument("--wm-size", type=int, default=None, help="水印字号, 默认 1080p=28, 4k=48")
    g.add_argument("--wm-opacity", type=float, default=0.7)
    g.add_argument("--font", default=DEFAULT_FONT, help="字体文件路径 (Windows 需要, 注意冒号转义 C\\:/...)")
    g.add_argument("--lufs", type=float, default=-16)
    g.add_argument("--true-peak", type=float, default=-1.5)
    g.add_argument("--lra", type=float, default=11)
    return p


def main():
    args = build_parser().parse_args()
    if args.bitrate is None:
        args.bitrate = "30M" if args.res == "4k" else "8M"
    if args.wm_size is None:
        args.wm_size = 48 if args.res == "4k" else 28
    if args.mode != "process" and not args.query:
        sys.exit("[错误] 下载需要 -q/--query 关键词")

    ensure_dir(args.save_dir)
    raw_dir = os.path.join(args.save_dir, "raw")

    if args.mode in ("download", "all"):
        download_all(args, raw_dir)
    if args.mode in ("process", "all") and args.process != "none" and args.type == "video":
        process_all(args, raw_dir)
    print("\n=== 全部完成 ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序已停止。")
