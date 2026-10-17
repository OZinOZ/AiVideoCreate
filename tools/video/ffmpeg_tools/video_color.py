import os
import subprocess

# --- 配置区 ---
INPUT_DIR = "H:\\OliverAI\\resources\\barrier_pex\\coral"  # 你存放已加水印视频的目录
OUTPUT_DIR = os.path.join(INPUT_DIR, "processed_color")

# --- 调色参数设置 ---
# 1. 红色通道补偿：水下最缺红，我们要把红色的中音区拉高
# 2. 蓝色通道微调：减弱那种发灰的蓝色
# 3. 对比度与饱和度：进一步提升通透感
CURVES_STR = "curves=r='0/0 0.5/0.6 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.45 1/1'"
SHARP_STR = "unsharp=5:5:1.0:5:5:0.0" # 轻微锐化，破除水下雾感
EQ_STR = "eq=contrast=1.15:saturation=1.3:brightness=-0.02"

#如果觉得红色补得太多，把 0.65 改小一点（比如 0.6）；如果觉得还不够鲜艳，把 0.65 改成 0.7

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def process_color_correction(input_path, output_path):
    # 组合滤镜链
    # 因为你已经加过水印和缩放了，这里只做调色和锐化
    vf_chain = [CURVES_STR, EQ_STR, SHARP_STR]
    vf_string = ",".join(vf_chain)

    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda", 
        "-i", input_path,
        "-vf", vf_string,
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-b:v", "8M",
        "-c:a", "copy", # 保留你之前的音频（如果是静音也是copy）
        output_path
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing {input_path}: {e.stderr.decode()}")
        return False

def main():
    ensure_dir(OUTPUT_DIR)
    files = [f for f in os.listdir(INPUT_DIR) if f.endswith((".mp4", ".mov"))]
    
    print(f"找到 {len(files)} 个视频，开始 BBC 风格色彩修复...")
    
    for i, filename in enumerate(files):
        in_p = os.path.join(INPUT_DIR, filename)
        out_p = os.path.join(OUTPUT_DIR, filename)
        
        print(f"[{i+1}/{len(files)}] 正在调色: {filename}")
        if process_color_correction(in_p, out_p):
            print(f"--- 成功: {filename}")
        else:
            print(f"--- 失败: {filename}")

    print(f"\n全部处理完成！请去该目录下查看结果: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()