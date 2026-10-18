#!/usr/bin/env python
"""
Mermaid 长视频生成器 (合并自 mermaid*.py 共 14 个脚本)

把分类素材 (1_fish / 2_turtle / ...) 随机拼成长视频, 混音 (主音乐 + 环境音), 再叠加
美人鱼透明 WebM 动画、订阅按钮、随机样式字幕, 一次渲染输出成品。

目录约定 (-d BASE_DIR):
    <分类目录>/*.mp4        素材 (默认自动识别所有子目录, 也可用 --categories 指定顺序)
    intro/<分类>.mp4        可选片头 (也兼容 intro/intro_1.mp4 这种按序号命名)
    music/ *.mp3|wav        主音乐
    background/ *.mp3|wav   环境音
    mermaid_assets/ *.webm  美人鱼 (VP9 透明)
    branding/subscribe.png  订阅按钮 (可选)
    _work/                  中间文件与断点状态 (task_state.json)

流程 (支持断点续传, --fresh 重新开始):
    1 select      选素材            4 audio     混音 / 母带 / 指纹扰动
    2 standardize 标准化到目标规格   5 plan      生成字幕/动画/订阅计划
    3 concat      拼接               6 fusion    叠加渲染输出

示例:
    python mermaid_video.py -d H:/res/mermaid-0202 --minutes 90
    python mermaid_video.py -d I:/MyVideo/seadrone_4K --res 4k --fps 60 --minutes 120 --master --ambient-db -24
    python mermaid_video.py -d H:/res/barrier/0202 --no-audio --no-overlay --concat copy   # 仅随机拼接
    python mermaid_video.py -d H:/res/x --minutes 3 --captions 5 --fingerprint --color-jitter

环境变量: OPENAI_API_KEY (可选, 用于生成字幕; 没有则使用内置字幕池)
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time

VIDEO_EXTS = (".mp4", ".mov", ".mkv")
AUDIO_EXTS = (".mp3", ".wav")
RESERVED_DIRS = {"intro", "music", "background", "mermaid_assets", "branding", "_work",
                 "temp_standardized", "mermaid_assets", "processed"}

BACKUP_CAPTIONS = [
    "The ocean remembers what the wind forgets", "Echoes of a sunken heart",
    "Blue is the loneliest color beneath the tide", "Tracing shadows in the cold abyss",
    "A silent requiem for the waves", "Drowning in the beauty of silence",
    "Cold currents, colder memories", "Where the light dies, the dream begins",
    "Every wave is a new beginning", "Chasing the dawn across the endless blue",
    "The sun shall rise from the liquid horizon", "Infinite power in a single drop",
    "Golden paths written on the water", "The soul breathes with the surging sea",
    "Strength born from the depths", "The horizon is not the end, but a promise",
    "Sparkling ripples of pure joy", "Crystal laughter in the sea spray",
    "Turquoise dreams and sun-kissed foam", "Dancing on the edge of the world",
    "Emerald whispers of a gentle sea", "A symphony of bubbles and light",
    "Serenity found in every grain of sand", "Let the ocean wash away the noise",
    "Ocean's lullaby for a restless world", "Sailing through liquid starlight",
    "The reef's secret garden", "Nature's masterpiece in every ripple",
    "Lost in the velvet embrace of the deep", "Where peace flows deeper than the abyss",
]

STYLE_POOL = {
    "fonts": ["arial.ttf", "calibri.ttf", "georgia.ttf", "segoeui.ttf"],
    "sizes": [42, 48, 54],           # 以 1080p 为基准, 其他分辨率按高度等比放大
    "colors": ["white", "0xFFE4B5", "0x00FFFF", "0xFFD700"],
    "y_offsets": [0.82, 0.85, 0.88],
    "x_aligns": ["(w-text_w)/2", "(w-text_w)/3", "(w-text_w)*2/3"],
}

RES = {"1080": (1920, 1080), "4k": (3840, 2160)}


# ==========================================
# --- 通用工具 ---
# ==========================================

def run(cmd, what="FFmpeg", quiet=True):
    """运行命令。失败时打印 stderr 末尾并抛 RuntimeError。"""
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL if quiet else None,
                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        print(f"❌ [{what}] 失败:\n{(r.stderr or '')[-1500:]}")
        raise RuntimeError(f"{what} failed")


def probe(path):
    """返回 dict(w,h,fps,dur,bitrate) ; 文件损坏返回 None"""
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]
    try:
        data = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
        v = next(s for s in data["streams"] if s["codec_type"] == "video")
        n, d = (v.get("r_frame_rate") or "0/1").split("/")
        fps = float(n) / float(d) if float(d) else 0.0
        dur = float(data["format"].get("duration") or v.get("duration") or 0)
        if fps <= 0 or dur <= 0:
            return None
        return {"w": int(v["width"]), "h": int(v["height"]), "fps": fps, "dur": dur,
                "bitrate": int(data["format"].get("bit_rate") or 0)}
    except Exception:
        return None


def duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def list_files(folder, exts):
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts))


def concat_line(path):
    return "file '" + os.path.abspath(path).replace("\\", "/").replace("'", "'\\''") + "'\n"


def write_concat(list_path, files):
    with open(list_path, "w", encoding="utf-8") as f:
        f.writelines(concat_line(p) for p in files)


def scale_rate(rate, k):
    """'55M' * 1.4 -> '77M'"""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([MKmk])", rate)
    return f"{int(float(m.group(1)) * k)}{m.group(2).upper()}" if m else rate


def escape_drawtext(text):
    return (text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:")
                .replace("%", "\\%").replace(",", "\\,").replace("\n", " ")
                .replace("[", "\\[").replace("]", "\\]"))


def font_path(font_dir, name):
    p = os.path.join(font_dir, name).replace("\\", "/")
    return p.replace(":", "\\:")


class Ctx:
    """所有路径与参数的集合"""

    def __init__(self, args):
        self.a = args
        b = args.dir
        self.base = b
        self.music, self.bg = os.path.join(b, "music"), os.path.join(b, "background")
        self.mermaid, self.branding = os.path.join(b, "mermaid_assets"), os.path.join(b, "branding")
        self.intro = os.path.join(b, "intro")
        self.work = os.path.join(b, "_work")
        self.std = os.path.join(self.work, "std")
        os.makedirs(self.std, exist_ok=True)
        self.state_file = os.path.join(self.work, "task_state.json")
        self.concat_list = os.path.join(self.work, "concat_list.txt")
        self.temp_video = os.path.join(self.work, "temp_video.mp4")
        self.temp_audio = os.path.join(self.work, "temp_audio.m4a")
        self.plan_json = os.path.join(self.work, "overlay_plan.json")
        self.filter_script = os.path.join(self.work, "fusion_filters.txt")
        self.output = args.output or os.path.join(b, f"FINAL_{args.res}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
        self.w, self.h = RES[args.res]
        self.target = args.minutes * 60
        hw = [] if args.cpu else ["-hwaccel", "cuda"]
        self.hw = hw
        if args.cpu:
            self.venc = ["-c:v", "libx264", "-preset", "medium", "-b:v", args.bitrate]
        else:
            self.venc = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr_hq", "-b:v", args.bitrate,
                         "-maxrate", scale_rate(args.bitrate, 1.4), "-bufsize", scale_rate(args.bitrate, 2.0)]


# ==========================================
# --- Step 1: 选素材 ---
# ==========================================

def find_categories(c):
    if c.a.categories:
        return c.a.categories
    return sorted(d for d in os.listdir(c.base)
                  if os.path.isdir(os.path.join(c.base, d)) and d not in RESERVED_DIRS and not d.startswith("."))


def step_select(c):
    cats = find_categories(c)
    if not cats:
        sys.exit("❌ 没有找到素材分类目录")
    print(f"🪄 [Step 1] 选择素材 | 分类: {cats} | 目标 {c.target / 60:.0f} 分钟")
    limit = c.target + c.a.margin
    per_cat = limit / len(cats) if c.a.balance else None
    selected, total = [], 0.0
    for i, cat in enumerate(cats, 1):
        if not c.a.balance and total >= limit:
            break
        cat_total = 0.0
        for cand in (os.path.join(c.intro, f"{cat}.mp4"), os.path.join(c.intro, f"intro_{i}.mp4")):
            if os.path.exists(cand):
                d = duration(cand)
                selected.append(cand); total += d; cat_total += d
                break
        vids = list_files(os.path.join(c.base, cat), (".mp4",))
        if not vids:
            print(f"⚠️ 目录缺失或为空: {cat}")
        random.shuffle(vids)
        for v in vids:
            if total >= limit or (per_cat and cat_total >= per_cat):
                break
            d = duration(v)
            if d > 0:
                selected.append(v); total += d; cat_total += d
    if not selected:
        sys.exit("❌ 没有可用素材")
    print(f"✅ 选中 {len(selected)} 个片段, 约 {total / 60:.1f} 分钟")
    return selected


# ==========================================
# --- Step 2: 标准化 ---
# ==========================================

def is_match(c, info):
    ok = info["w"] == c.w and info["h"] == c.h and abs(info["fps"] - c.a.fps) < 0.1
    if ok and c.a.res == "4k" and info["bitrate"]:
        br = float(re.sub(r"[Mm]$", "", c.a.bitrate)) * 1e6
        ok = br * 0.9 < info["bitrate"] < br * 1.2
    return ok


def step_standardize(c, selected):
    print(f"🪄 [Step 2] 标准化到 {c.w}x{c.h} @{c.a.fps}fps ...")
    out_list = []
    for i, p in enumerate(selected, 1):
        info = probe(p)
        if not info:
            print(f"⚠️ 跳过损坏文件: {os.path.basename(p)}")
            continue
        if is_match(c, info):
            out_list.append(p)
            continue
        key = hashlib.md5(f"{p}_{c.w}x{c.h}_{c.a.fps}_{c.a.bitrate}".encode()).hexdigest()[:12]
        out = os.path.join(c.std, f"std_{key}.mp4")
        if not os.path.exists(out):
            print(f"   [{i}/{len(selected)}] {os.path.basename(p)} ({info['w']}x{info['h']})")
            vf = (f"scale={c.w}:{c.h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                  f"pad={c.w}:{c.h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={c.a.fps}")
            tmp = out + ".part.mp4"
            run(["ffmpeg", "-y", "-loglevel", "error", *c.hw, "-i", p, "-vf", vf, *c.venc,
                 "-pix_fmt", "yuv420p", "-an", tmp], "标准化")
            os.replace(tmp, out)
        out_list.append(out)
    if not out_list:
        sys.exit("❌ 所有素材都无效")
    return out_list


# ==========================================
# --- Step 3: 拼接 ---
# ==========================================

def step_concat(c, std_list):
    print(f"🔗 [Step 3] 拼接 ({c.a.concat})...")
    write_concat(c.concat_list, std_list)
    base = ["ffmpeg", "-y", "-loglevel", "error"]
    if c.a.concat == "copy":
        run([*base, "-f", "concat", "-safe", "0", "-fflags", "+genpts", "-i", c.concat_list,
             "-c", "copy", "-an", c.temp_video], "拼接(copy)")
    else:
        # 重编码 + 重置 PTS, 彻底抹平时间轴间隙 (解决长视频后半段漂移)
        run([*base, *c.hw, "-f", "concat", "-safe", "0", "-i", c.concat_list,
             "-vf", "setpts=N/FRAME_RATE/TB", "-r", str(c.a.fps), *c.venc, "-pix_fmt", "yuv420p",
             "-an", c.temp_video], "拼接(重编码)")
    real = duration(c.temp_video)
    if real <= 0:
        raise RuntimeError("拼接结果为空")
    print(f"✅ 物理时长: {real:.1f}s (目标 {c.target}s)")
    return real


# ==========================================
# --- Step 4: 音频 ---
# ==========================================

def pick_until(files, sec):
    durs = {f: duration(f) for f in files}
    picked, total = [], 0.0
    pool = files[:]
    while total < sec:
        random.shuffle(pool)
        for f in pool:
            picked.append(f); total += durs[f]
            if total >= sec:
                break
    return picked


def step_audio(c, real_dur):
    print("🎵 [Step 4] 混音...")
    music, ambient = list_files(c.music, AUDIO_EXTS), list_files(c.bg, AUDIO_EXTS)
    if not music:
        print("⚠️ music/ 里没有音频, 将输出无声视频")
        return False
    a = c.a
    need = real_dur * (1.03 if a.fingerprint else 1.0)
    mlist = os.path.join(c.work, "music_list.txt")
    write_concat(mlist, pick_until(music, need))

    inputs = ["-f", "concat", "-safe", "0", "-i", mlist]
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    if ambient:
        inputs += ["-stream_loop", "-1", "-i", random.choice(ambient)]
        fc = (f"[0:a]{fmt},volume={a.music_db}dB[m];[1:a]{fmt},volume={a.ambient_db}dB[b];"
              f"[m][b]amix=inputs=2:duration=first:dropout_transition=0:weights=1 1[mix]")
    else:
        fc = f"[0:a]{fmt},volume={a.music_db}dB[mix]"

    def chain(use_rubberband):
        parts = []
        if a.fingerprint:
            p, s = random.uniform(1.005, 1.015), random.uniform(1.005, 1.015)
            parts.append(f"rubberband=pitch={p:.4f},atempo={s:.4f}" if use_rubberband else f"atempo={s:.4f}")
        if a.master:
            parts += ["crystalizer=i=2.0", "stereowiden=delay=20:feedback=0.25:crossfeed=0.3:drymix=0.8"]
        parts += [f"loudnorm=I={a.lufs}:TP=-1.5:LRA=11", "aformat=sample_rates=44100"]
        return ",".join(parts)

    def build(use_rb):
        return ["ffmpeg", "-y", "-loglevel", "error", *inputs,
                "-filter_complex", f"{fc};[mix]{chain(use_rb)}[out]", "-map", "[out]",
                "-t", f"{need:.2f}", "-c:a", "aac", "-b:a", a.audio_bitrate, c.temp_audio]
    try:
        run(build(True), "混音")
    except RuntimeError:
        if not a.fingerprint:
            raise
        print("⚠️ rubberband 不可用, 退化为仅 atempo")
        run(build(False), "混音(降级)")
    return True


# ==========================================
# --- Step 5: 计划 ---
# ==========================================

def get_captions(c):
    a = c.a
    caps = []
    if not a.no_llm and os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            for intent in ("melancholy and deep poetic", "hopeful and majestic", "healing and whimsical"):
                prompt = (f"Generate 20 short, calm, {intent} {a.caption_theme} captions.\n"
                          "Rules: 6 to 12 words; no punctuation at the end; calm, emotional, cinematic; no emojis.\n"
                          "Return ONLY a raw JSON array of strings.")
                r = client.chat.completions.create(model=a.llm_model, timeout=20,
                                                   messages=[{"role": "user", "content": prompt}])
                txt = re.sub(r"```(json)?|```", "", r.choices[0].message.content).strip()
                caps += [str(x) for x in json.loads(txt)]
            print(f"✅ LLM 生成 {len(caps)} 条字幕")
        except Exception as e:
            print(f"⚠️ LLM 失败 ({e}), 使用内置字幕池")
    caps = list(dict.fromkeys(caps))
    if len(caps) < 20:
        pool = BACKUP_CAPTIONS[:]
        random.shuffle(pool)
        caps += [x for x in pool if x not in caps]
    random.shuffle(caps)
    return caps


def step_plan(c, real_dur):
    print("📝 [Step 5] 生成叠加计划...")
    a = c.a
    plan = {"mermaid": [], "subscribe": [], "captions": []}

    t = a.subscribe_first + random.randint(-5, 5)
    while t + a.subscribe_len < real_dur:
        plan["subscribe"].append({"start": t, "end": t + a.subscribe_len})
        t += a.subscribe_gap + random.randint(-5, 5)

    t = a.mermaid_first
    while t + a.mermaid_len < real_dur:
        plan["mermaid"].append({"start": t, "end": t + a.mermaid_len})
        t += random.randint(*a.mermaid_gap)

    fonts = [f for f in STYLE_POOL["fonts"] if os.path.exists(os.path.join(a.font_dir, f))] or [None]
    k = c.h / 1080
    t, n = a.caption_first, 0
    for text in get_captions(c):
        if t + a.caption_len + 2 > real_dur or (a.captions and n >= a.captions):
            break
        plan["captions"].append({
            "start": t, "end": t + a.caption_len, "text": text,
            "font": random.choice(fonts), "size": int(random.choice(STYLE_POOL["sizes"]) * k),
            "color": random.choice(STYLE_POOL["colors"]), "y": random.choice(STYLE_POOL["y_offsets"]),
            "x": random.choice(STYLE_POOL["x_aligns"]),
        })
        t += random.randint(*a.caption_gap)
        n += 1
    with open(c.plan_json, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"✅ 字幕 {len(plan['captions'])} | 动画 {len(plan['mermaid'])} | 订阅 {len(plan['subscribe'])}")
    return plan


# ==========================================
# --- Step 6: 融合渲染 ---
# ==========================================

def enable_expr(segs):
    return "+".join(f"between(t,{s['start']},{s['end']})" for s in segs)


def step_fusion(c, plan, has_audio):
    print("🔥 [Step 6] 融合渲染...")
    a = c.a
    inputs = ["-i", c.temp_video]
    if has_audio:
        inputs += ["-i", c.temp_audio]
    n_in = len(inputs) // 2
    filters, last = [], "[base]"

    if a.color_jitter:   # 非对称色温扰动 (每次输出略有不同)
        adj = lambda: random.choice([random.uniform(-0.03, -0.01), random.uniform(0.01, 0.03)])
        filters.append(f"[0:v]setpts=PTS-STARTPTS,colorbalance=rs={adj():.3f}:gs={adj():.3f}:bs={adj():.3f}[base]")
    else:
        filters.append("[0:v]setpts=PTS-STARTPTS[base]")

    webms = list_files(c.mermaid, (".webm",))
    if webms and plan["mermaid"]:
        inputs += ["-stream_loop", "-1", "-c:v", "libvpx-vp9", "-i", random.choice(webms)]
        idx = n_in; n_in += 1
        filters.append(f"[{idx}:v]format=yuva420p,scale=iw*{a.mermaid_scale}:-1,setpts=PTS-STARTPTS[m_v]")
        filters.append(f"{last}[m_v]overlay=x={int(120 * c.h / 1080)}:y=H-h-{int(120 * c.h / 1080)}"
                       f":enable='{enable_expr(plan['mermaid'])}'[v_m]")
        last = "[v_m]"

    sub_img = os.path.join(c.branding, "subscribe.png")
    if os.path.exists(sub_img) and plan["subscribe"]:
        inputs += ["-i", sub_img]
        idx = n_in; n_in += 1
        ck = "chromakey=0xCBCBCB:0.15:0.1," if a.sub_chromakey else ""
        filters.append(f"[{idx}:v]{ck}scale={int(220 * c.h / 1080)}:-1[sub_v]")
        m = int(100 * c.h / 1080)
        filters.append(f"{last}[sub_v]overlay=x=W-w-{m}:y={m}:enable='{enable_expr(plan['subscribe'])}'[v_s]")
        last = "[v_s]"

    shadow = max(2, int(3 * c.h / 1080))
    for i, cap in enumerate(plan["captions"]):
        ff = f":fontfile='{font_path(a.font_dir, cap['font'])}'" if cap["font"] else ""
        alpha = (f":alpha='if(lt(t,{cap['start']}+0.5),(t-{cap['start']})/0.5,"
                 f"if(gt(t,{cap['end']}-0.5),({cap['end']}-t)/0.5,1))'") if a.fade else ""
        filters.append(
            f"{last}drawtext=text='{escape_drawtext(cap['text'])}'{ff}:fontsize={cap['size']}"
            f":fontcolor={cap['color']}@0.85:shadowcolor=black@0.6:shadowx={shadow}:shadowy={shadow}"
            f":x={cap['x']}:y=h*{cap['y']}{alpha}:enable='between(t,{cap['start']},{cap['end']})'[v_t{i}]")
        last = f"[v_t{i}]"

    # 滤镜很长 (数百条字幕) , 用脚本文件避免 Windows 命令行长度限制
    with open(c.filter_script, "w", encoding="utf-8") as f:
        f.write(";\n".join(filters))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *c.hw, *inputs, "-filter_complex_script", c.filter_script,
           "-map", last]
    if has_audio:
        cmd += ["-map", "1:a:0", "-c:a", "copy", "-shortest"]
    cmd += [*c.venc, "-pix_fmt", "yuv420p", "-max_muxing_queue_size", "1024", c.output]
    run(cmd, "融合渲染", quiet=False)


# ==========================================
# --- 主流程 ---
# ==========================================

def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")   # GBK 控制台遇到 emoji 不再崩溃
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Mermaid 长视频生成器", epilog=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-d", "--dir", required=True, help="BASE_DIR")
    p.add_argument("-o", "--output", help="输出文件 (默认 BASE_DIR/FINAL_<res>_<时间>.mp4)")
    p.add_argument("--categories", nargs="+", help="素材分类目录 (按顺序), 默认自动识别")
    p.add_argument("--balance", action="store_true", help="每个分类平均分配时长 (默认按顺序填满)")
    p.add_argument("--minutes", type=float, default=90)
    p.add_argument("--margin", type=float, default=60, help="素材时长冗余(秒)")

    g = p.add_argument_group("视频")
    g.add_argument("--res", choices=list(RES), default="1080")
    g.add_argument("--fps", type=int, default=30)
    g.add_argument("--bitrate", default=None, help="默认 1080p=12M, 4k=55M")
    g.add_argument("--cpu", action="store_true")
    g.add_argument("--concat", choices=["reencode", "copy"], default="reencode",
                   help="reencode: 重编码并重置 PTS (稳); copy: 流复制 (快, 需素材规格一致)")

    g = p.add_argument_group("音频")
    g.add_argument("--no-audio", action="store_true", help="输出无声视频")
    g.add_argument("--music-db", type=float, default=2)
    g.add_argument("--ambient-db", type=float, default=-24, help="环境音相对音量 dB")
    g.add_argument("--master", action="store_true", help="母带增强 (crystalizer + stereowiden)")
    g.add_argument("--fingerprint", action="store_true", help="音频指纹扰动 (rubberband + atempo, 随机微调)")
    g.add_argument("--lufs", type=float, default=-14)
    g.add_argument("--audio-bitrate", default="320k")

    g = p.add_argument_group("叠加")
    g.add_argument("--no-overlay", action="store_true", help="不叠加字幕/动画/订阅, 只输出拼接+音频")
    g.add_argument("--captions", type=int, default=0, help="字幕数量上限 (0=铺满全片)")
    g.add_argument("--caption-len", type=int, default=8)
    g.add_argument("--caption-first", type=int, default=30)
    g.add_argument("--caption-gap", type=int, nargs=2, default=[150, 250], metavar=("MIN", "MAX"))
    g.add_argument("--caption-theme", default="deep ocean relaxation video")
    g.add_argument("--no-llm", action="store_true")
    g.add_argument("--llm-model", default="gpt-4o-mini")
    g.add_argument("--fade", action="store_true", help="字幕淡入淡出")
    g.add_argument("--font-dir", default="C:/Windows/Fonts")
    g.add_argument("--mermaid-scale", type=float, default=0.2)
    g.add_argument("--mermaid-first", type=int, default=60)
    g.add_argument("--mermaid-len", type=int, default=6)
    g.add_argument("--mermaid-gap", type=int, nargs=2, default=[500, 900], metavar=("MIN", "MAX"))
    g.add_argument("--subscribe-first", type=int, default=300)
    g.add_argument("--subscribe-len", type=int, default=10)
    g.add_argument("--subscribe-gap", type=int, default=900)
    g.add_argument("--sub-chromakey", action="store_true", help="订阅按钮 PNG 带棋盘格假透明时去底色")
    g.add_argument("--color-jitter", action="store_true", help="非对称色温扰动")

    g = p.add_argument_group("流程")
    g.add_argument("--fresh", action="store_true", help="忽略断点, 从头开始")
    g.add_argument("--clean", action="store_true", help="完成后删除 _work 中间文件")
    a = p.parse_args()
    if a.bitrate is None:
        a.bitrate = "55M" if a.res == "4k" else "12M"

    c = Ctx(a)
    state = {"step": 0}
    if os.path.exists(c.state_file) and not a.fresh:
        state = json.load(open(c.state_file, encoding="utf-8"))
        print(f"↩️ 从断点继续 (已完成 step {state['step']})")

    def save(step):
        state["step"] = step
        with open(c.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)

    try:
        if state["step"] < 1:
            state["selected"] = step_select(c); save(1)
        if state["step"] < 2:
            state["std_list"] = step_standardize(c, state["selected"]); save(2)
        if state["step"] < 3 or not os.path.exists(c.temp_video):
            state["real_dur"] = step_concat(c, state["std_list"]); save(3)
        real = state["real_dur"]
        has_audio = False
        if not a.no_audio:
            if state["step"] < 4 or not os.path.exists(c.temp_audio):
                step_audio(c, real); save(4)
            has_audio = os.path.exists(c.temp_audio)
        if a.no_overlay:
            plan = {"mermaid": [], "subscribe": [], "captions": []}
        else:
            if state["step"] < 5 or not os.path.exists(c.plan_json):
                plan = step_plan(c, real); save(5)
            else:
                plan = json.load(open(c.plan_json, encoding="utf-8"))
        step_fusion(c, plan, has_audio)
    except KeyboardInterrupt:
        print("\n[用户中断] 进度已保存, 重新运行同一命令即可续传。")
        return
    except Exception as e:
        print(f"\n❌ 失败: {e}\n(进度已保存, 修复后重新运行同一命令即可续传)")
        sys.exit(1)

    if os.path.exists(c.state_file):
        os.remove(c.state_file)
    if a.clean:
        shutil.rmtree(c.work, ignore_errors=True)
    print(f"\n✨ 完成: {c.output}")


if __name__ == "__main__":
    main()
