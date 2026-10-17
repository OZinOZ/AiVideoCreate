import os
import random
from pydub import AudioSegment
from pydub.effects import normalize

# --- 输入配置 ---
MUSIC_DIR = "H:\\OliverAI\\resources\\harp"      # 竖琴配乐目录
BG_DIR = "H:\\OliverAI\\resources\\water"       # 水声背景目录
OUTPUT_PATH = "H:\\OliverAI\\resources\\final_90min_audio.mp3"
TARGET_DURATION_MIN = 90               # 目标时长（分钟）

def process_audio():
    target_ms = TARGET_DURATION_MIN * 60 * 1000
    
    # 1. 加载并归一化竖琴音乐
    print("正在处理竖琴音乐...")
    music_files = [os.path.join(MUSIC_DIR, f) for f in os.listdir(MUSIC_DIR) if f.endswith(('.mp3', '.wav'))]
    random.shuffle(music_files)
    
    combined_music = AudioSegment.empty()
    while len(combined_music) < target_ms:
        for file in music_files:
            if len(combined_music) >= target_ms:
                break
            sound = AudioSegment.from_file(file)
            sound = normalize(sound) # 统一响度
            
            if len(combined_music) == 0:
                combined_music = sound
            else:
                # 3000ms (3秒) 的交叉淡化，让衔接无感
                combined_music = combined_music.append(sound, crossfade=3000)
    
    combined_music = combined_music[:target_ms] # 裁切到精确时长
    print(f"竖琴音乐拼接完成，当前长度: {len(combined_music)/60000:.2f} 分钟")

    # 2. 加载并处理背景水声
    print("正在处理背景水声...")
    bg_files = [os.path.join(BG_DIR, f) for f in os.listdir(BG_DIR) if f.endswith(('.mp3', '.wav'))]
    
    combined_bg = AudioSegment.empty()
    while len(combined_bg) < target_ms:
        random.shuffle(bg_files) # 每次循环随机排序，增加随机性
        for file in bg_files:
            if len(combined_bg) >= target_ms:
                break
            bg_sound = AudioSegment.from_file(file)
            bg_sound = normalize(bg_sound)
            if len(combined_bg) == 0:
                combined_bg = bg_sound
            else:
                combined_bg = combined_bg.append(bg_sound, crossfade=5000) # 水声淡入淡出更长，更平滑

    # 3. 调整背景音量并叠加
    print("正在进行最终混合...")
    combined_bg = combined_bg[:target_ms] - 20 # 背景音量减低 15 分贝，变成纯背景
    
    # 将竖琴和水声叠加
    final_audio = combined_music.overlay(combined_bg)
    
    # 4. 导出最终成品
    print(f"正在导出到: {OUTPUT_PATH}")
    final_audio.export(OUTPUT_PATH, format="mp3", bitrate="192k")
    print("✅ 全部完成！")

if __name__ == "__main__":
    process_audio()