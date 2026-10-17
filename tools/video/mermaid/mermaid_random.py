import json
import subprocess
import random
import os

# --- 配置区 ---
VIDEO_INPUT = "calibrated_final.mp4" # 建议使用你刚才修复好时间轴的文件
VIDEO_OUTPUT = "final_with_mermaid_and_sub.mp4"
SUBTITLE_JSON = "subtitles_90min.json"
MERMAID_DIR = "./mermaid_assets/" 

FONT_PATH = "C\:/Windows/Fonts/msyh.ttc"
FONT_SIZE = 42
FONT_COLOR = "white"
Y_POS = "h*0.8"

def load_subtitles(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_random_mermaid():
    files = [f for f in os.listdir(MERMAID_DIR) if f.endswith('.webm')]
    return os.path.join(MERMAID_DIR, random.choice(files)) if files else None

def main():
    subtitles = load_subtitles(SUBTITLE_JSON)
    
    # 基础输入：第 0 号输入是背景视频
    cmd = ["ffmpeg", "-y", "-i", VIDEO_INPUT]
    
    filter_parts = []
    input_index = 1 # 1 开始是美人鱼素材
    current_v = "0:v"

    # 1. 处理美人鱼叠加逻辑
    for item in subtitles:
        if item.get("type") == "mermaid":
            m_path = get_random_mermaid()
            if m_path:
                # 关键：这里强制指定解码器 libvpx-vp9 以确保透明度识别
                cmd.extend(["-c:v", "libvpx-vp9", "-itsoffset", str(item["time"]), "-i", m_path])
                
                start = item["time"]
                end = start + 8 # 假设显示8秒
                
                m_label = f"m{input_index}"
                out_label = f"v{input_index}"
                
                # 平移你成功的命令逻辑：缩放 + 偏移
                filter_parts.append(
                    f"[{input_index}:v]scale=100:-1,setpts=PTS-STARTPTS[{m_label}];"
                    f"[{current_v}][{m_label}]overlay=x=20:y=20:enable='between(t,{start},{end})'[{out_label}]"
                )
                current_v = out_label
                input_index += 1
    
    # 2. 处理字幕逻辑（保持原有淡入淡出）
    for i, item in enumerate(subtitles):
        offset = random.uniform(-3, 3)
        start = max(0, item["time"] + offset)
        end = start + 5
        text = item["text"].replace("'", "\\'").replace(":", "\\:")
        
        fade_effect = f"alpha='if(lt(t,{start}+0.5),(t-{start})/0.5,if(gt(t,{end}-0.5),({end}-t)/0.5,1))'"
        
        next_v = f"sub{i}"
        filter_parts.append(
            f"[{current_v}]drawtext=text='{text}':fontfile='{FONT_PATH}':"
            f"fontsize={FONT_SIZE}:fontcolor={FONT_COLOR}:"
            f"shadowcolor=black@0.4:shadowx=2:shadowy=2:"
            f"x=(w-text_w)/2:y={Y_POS}:"
            f"{fade_effect}:enable='between(t,{start},{end})'[{next_v}]"
        )
        current_v = next_v

    # 组合最终命令
    cmd.extend([
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{current_v}]",
        "-map", "0:a?", # 尝试保留原始音频（如果你洗白时删了也没关系）
        "-c:v", "h264_nvenc",
        "-b:v", "12M",
        "-c:a", "aac", # 既然要出成片，重新编码一次音频最保险
        "-shortest", # 确保视频在主背景结束时停止
        VIDEO_OUTPUT
    ])

    print(f"🚀 正在合成！当前共有 {input_index-1} 个美人鱼彩蛋点...")
    subprocess.run(cmd, check=True)
    print("✅ 大功告成！")

if __name__ == "__main__":
    main()