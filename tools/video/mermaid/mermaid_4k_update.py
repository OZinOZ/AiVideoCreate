# ruff: noqa: F821  # This file is a code fragment (patch snippet), not a standalone runnable script.
# ... (前面的导入和配置保持不变) ...

def final_fusion():
    print("🔥 [Step 5] 启动最终 4K 渲染合成 (长视频优化版)...")
    with open(PATHS["overlay_json"], "r", encoding="utf-8") as f:
        cfg = json.load(f)

    inputs = ["-i", PATHS["temp_video"], "-i", PATHS["temp_audio_clean"]]
    filters = ["[0:v]setpts=PTS-STARTPTS[base]"]
    last_v = "[base]"

    # 1. 美人鱼动画叠加
    if cfg["mermaid"]["enable"]:
        m_assets = [os.path.join(PATHS["mermaid"], f) for f in os.listdir(PATHS["mermaid"]) if f.endswith(".webm")]
        if m_assets:
            inputs += ["-stream_loop", "-1", "-i", random.choice(m_assets)]
            m_en = "+".join([f"between(t,{s['start']},{s['end']})" for s in cfg["mermaid"]["segments"]])
            filters.append(f"[2:v]scale=iw*0.25:-1,setpts=PTS-STARTPTS[m_v]") 
            filters.append(f"{last_v}[m_v]overlay=x=100:y=100:enable='{m_en}'[v1]") # 坐标稍微内移
            last_v = "[v1]"

    # 2. 动态字幕叠加 (优化长路径处理)
    for i, cap in enumerate(cfg["captions"]):
        txt = cap["text"].replace("'", "'\\\\\\''").replace(":", "\\:")
        f_path = f"C\\:/Windows/Fonts/{cap['font']}"
        draw = (f"drawtext=text='{txt}':fontfile='{f_path}':fontsize={cap['size']}:"
                f"fontcolor={cap['color']}@0.8:shadowcolor=black@0.6:shadowx=5:shadowy=5:" # 透明度稍微调低更高级
                f"x={cap['x_pos']}:y=h*{cap['y']}:enable='between(t,{cap['start']},{cap['end']})'")
        next_v = f"[v_txt{i}]"
        filters.append(f"{last_v}{draw}{next_v}")
        last_v = next_v

    # 3. 最终执行命令 (加入长视频稳定性参数)
    cmd = [
        "ffmpeg", "-y", *inputs, 
        "-filter_complex", ";".join(filters),
        "-map", last_v, "-map", "1:a:0", 
        "-c:v", "h264_nvenc", "-preset", "p4", 
        "-b:v", VIDEO_BITRATE, "-maxrate", "80M", "-bufsize", "100M",
        "-max_muxing_queue_size", "1024", # 防止长视频缓冲区溢出
        "-c:a", "aac", "-b:a", "192k", "-shortest", 
        PATHS["output"]
    ]
    subprocess.run(cmd, check=True)

# ... (main 函数中的标准化逻辑建议增加码率以匹配 4K 质感) ...
# vf 保持不变，但 -b:v 建议设为 40M 以上