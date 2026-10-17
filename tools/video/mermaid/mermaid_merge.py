import os
import random
import subprocess

# --- 配置区 ---
BASE_DIR = r"H:\OliverAI\resources\barrier\0202"
CATEGORIES = ["1_fish", "2_turtle", "3_coral"]
INTRO_DIR = os.path.join(BASE_DIR, "intro")
OUTPUT_FILE = os.path.join(BASE_DIR, "final_shuffled_video.mp4")

def main():
    final_video_list = []

    for i, cat in enumerate(CATEGORIES):
        print(f"正在读取目录: {cat}")
        cat_path = os.path.join(BASE_DIR, cat)
        
        # 1. 获取该章节所有 MP4 文件
        if not os.path.exists(cat_path):
            print(f"警告：找不到目录 {cat_path}")
            continue
            
        files = [os.path.join(cat_path, f) for f in os.listdir(cat_path) if f.endswith(".mp4")]
        
        # 2. 随机打乱当前章节的文件顺序
        random.shuffle(files)
        
        # 3. 添加 Intro (如果有的话)
        intro_file = os.path.join(INTRO_DIR, f"intro_{i+1}.mp4")
        if os.path.exists(intro_file):
            final_video_list.append(intro_file)
        
        # 4. 将打乱后的文件加入总列表
        final_video_list.extend(files)

    # 5. 生成 FFmpeg 拼接列表
    concat_list_path = os.path.join(BASE_DIR, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for vid in final_video_list:
            # 统一处理 Windows 路径斜杠
            clean_path = vid.replace('\\', '/')
            f.write(f"file '{clean_path}'\n")

    # 6. 执行 FFmpeg 拼接
    # 使用 -c copy 最快，如果所有视频格式一致，几秒钟就出结果
    print(f"🚀 正在按随机顺序拼接所有视频...")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        OUTPUT_FILE
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ 处理完成！全长视频已保存至: {OUTPUT_FILE}")
    except subprocess.CalledProcessError as e:
        print(f"❌ 拼接失败，可能是视频分辨率不统一。错误码: {e.returncode}")

if __name__ == "__main__":
    main()