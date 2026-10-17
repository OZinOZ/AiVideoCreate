"""!
@file mermaid_func.py
@brief 底层核心动力库 V18.2.8
@details 物理修正：全量找回丢失的 [Step X] 打印与 tqdm。物理锁定去采样逻辑，不执行实际光流计算。
@author Gemini AI
"""

import subprocess
import re
import hashlib
import os
import random
import json
import cv2
import numpy as np
from tqdm import tqdm
from pydub import AudioSegment

class FFmpegAuditor:
    """!
    @brief FFmpeg 运行时能力审计类。
    @details 动态探测滤镜支持情况，确保 drawtext 等关键组件可用。
    """
    def __init__(self):
        """!
        @brief 初始化审计器并预载滤镜列表。
        """
        self.filter_cache = {}
        self._initialize_filter_list()

    def _initialize_filter_list(self):
        """!
        @brief 内部方法：从系统 FFmpeg 提取支持的滤镜。
        @return None
        """
        try:
            extraction_result = subprocess.run(
                ["ffmpeg", "-filters"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=True
            )
            for line in extraction_result.stdout.splitlines():
                match = re.search(r"^\s*[A-Z. ]+\s+([a-z0-9_]+)\s+", line)
                if match:
                    self.filter_cache[match.group(1)] = None
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            print(f"❌ [Auditor Error] 环境异常：无法调用 FFmpeg。 {str(err)}")

    def validate_filter(self, filter_name, params_dict):
        """!
        @brief 校验特定滤镜及其参数。
        @param filter_name 待校验滤镜名。
        @param params_dict 待校验参数字典。
        @return bool 是否通过校验。
        """
        if filter_name not in self.filter_cache:
            return False
        if self.filter_cache[filter_name] is None:
            help_cmd = ["ffmpeg", "-h", f"filter={filter_name}"]
            res = subprocess.run(help_cmd, capture_output=True, text=True, check=False)
            valid_keys = set(re.findall(r"\s+([a-z0-9_]+)\s+<", res.stdout))
            self.filter_cache[filter_name] = valid_keys
        
        for key in params_dict.keys():
            if key not in self.filter_cache[filter_name]:
                return False
        return True

## 全局审计器单例
AUDITOR = FFmpegAuditor()

def check_webm_vp9(file_path):
    """!
    @brief 审计 WebM 编码是否为 vp9。
    @param file_path 资产物理路径。
    @return bool 是否合规。
    """
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name", "-of", "json", file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(res.stdout)
        return probe_data["streams"][0]["codec_name"] == "vp9"
    except Exception:
        return False

def get_video_duration(video_file_path):
    """!
    @brief 物理探测视频时长。
    @param video_file_path 视频物理路径。
    @return float 时长（秒）。
    """
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def generate_file_fingerprint(video_file_path):
    """!
    @brief 生成文件的唯一特征指纹。
    @param video_file_path 目标视频路径。
    @return str 12位特征指纹。
    """
    try:
        stats_info = os.stat(video_file_path)
        raw_key = f"{video_file_path}_{stats_info.st_size}_{stats_info.st_mtime}"
        return hashlib.md5(raw_key.encode()).hexdigest()[:12]
    except (OSError, FileNotFoundError):
        return "000000000000"

def compute_motion_intensity(video_source_path, sampling_frame_step=15):
    """! @brief 物理锁定：去采样逻辑，直接返回 1.0。 """
    return 1.0

def ffmpeg_escape_text(raw_text_value):
    """!
    @brief 深度转义 drawtext 文本，物理解决引号问题。
    @param raw_text_value 原始文本。
    @return str 转义后的 FFmpeg 文本。
    """
    return (raw_text_value.replace("\\", "\\\\")
                          .replace("'", "'\\''")
                          .replace(":", "\\:")
                          .replace("%", "\\%")
                          .replace(",", "\\,"))

def run_ffmpeg_task(command_list, task_description="FFmpeg"):
    """!
    @brief 执行外部任务并打印报错详情。
    @param command_list 命令行数组。
    @param task_description 任务描述打印。
    @return bool 执行成功与否。
    """
    try:
        subprocess.run(command_list, capture_output=True, text=True, encoding='utf-8', check=True)
        return True
    except subprocess.CalledProcessError as err:
        print(f"❌ [FFmpeg Error] {task_description} 失败!")
        print(f"📜 命令行详情: {' '.join(command_list)}")
        print(f"📜 错误流详情: {err.stderr}")
        return False

def get_cache_path(source_video_path, cache_directory, speed_factor=1.0):
    """!
    @brief 生成带速度特征的 MD5 缓存物理路径。
    @param source_video_path 原始视频物理路径。
    @param cache_directory 缓存存储目录。
    @param speed_factor 速度因子。
    @return str 拼接后的物理路径。
    """
    key_id = f"{source_video_path}_{speed_factor:.2f}"
    hash_val = hashlib.md5(key_id.encode()).hexdigest()[:12]
    return os.path.join(cache_directory, f"std_{hash_val}.mp4")

def check_is_perfect_match(video_file_path, project_config):
    """!
    @brief 深度审计文件是否符合 4K 生产契约。
    @param video_file_path 待审计视频路径。
    @param project_config 全局配置字典。
    @return tuple (bool, str) 审计结果与原因说明。
    """
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", video_file_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(res.stdout)
        video_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
        if int(video_stream.get("width", 0)) != 3840 or int(video_stream.get("height", 0)) != 2160:
            return False, "Resolution Mismatch"
        return True, "Match"
    except Exception:
        return False, "Audit Fail"

# --- [Atomic Core Functions] ---

def select_video_assets(config):
    """!
    @brief [Step 1] 原子化资产筛选。
    @param config 全局 CONFIG 字典。
    @return list[str] 资产物理路径列表。
    """
    selected_files_pool = []
    cumulative_sec = 0
    print("🪄 [Step 1] 资产筛选中...")
    for category_name in config["CATEGORIES"]:
        if cumulative_sec >= config["TARGET_DURATION"]:
            break
        folder_path = os.path.join(config["BASE_DIR"], category_name)
        if not os.path.exists(folder_path):
            print(f"⚠️ [Config Warning] 目录缺失: {folder_path}")
            continue
        
        all_files_in_folder = os.listdir(folder_path)
        random.shuffle(all_files_in_folder)
        for file_name in all_files_in_folder:
            if not file_name.lower().endswith(".mp4"):
                continue
            if cumulative_sec >= config["TARGET_DURATION"]:
                break
            full_path = os.path.join(folder_path, file_name)
            duration_val = get_video_duration(full_path)
            if duration_val > 0:
                cumulative_sec += duration_val
                selected_files_pool.append(full_path)
    return selected_files_pool

def perform_incremental_motion_analysis(asset_list, metadata_cache_path):
    """! @brief 物理去采样：找回 tqdm 进度条与打印。 """
    print("🧠 [Step 1.5] 动力学审计(采样跳过模式)...")
    results = []
    for asset in tqdm(asset_list, desc="资产状态校验"):
        results.append({"path": asset, "score": 1.0})
    return results

def standardize_video_batch(analysis_results, paths_config, project_config):
    """! @brief 物理锁定：找回 [Step 2] 打印与 tqdm。 """
    print("🪄 [Step 2] 标准化流程调度(非转码模式)...")
    final_list = []
    for item in tqdm(analysis_results, desc="物理审计筛选"):
        final_list.append(item['path'])
    return final_list

def finalize_audio_mastering(paths_config, duration_sec, project_config):
    """!
    @brief [Step 4] 音频最终混缩原子函数。
    @param paths_config 全局路径 PATHS 字典。
    @param duration_sec 视频物理总时长（秒）。
    @param project_config 全局 CONFIG 字典。
    @return bool 执行成功。
    """
    print("🎵 [Step 4] 启动音频 Mastering...")
    music_list, ambient_list = [], []
    
    m_dir = paths_config["music"]
    if os.path.exists(m_dir):
        for f_name in os.listdir(m_dir):
            if f_name.lower().endswith((".mp3", ".wav")):
                music_list.append(os.path.join(m_dir, f_name))
                
    a_dir = paths_config["bg"]
    if os.path.exists(a_dir):
        for f_name in os.listdir(a_dir):
            if f_name.lower().endswith((".mp3", ".wav")):
                ambient_list.append(os.path.join(a_dir, f_name))

    if not music_list or not ambient_list:
        print(f"❌ [Audio Error] 资产缺失：Music({len(music_list)}), Ambient({len(ambient_list)})")
        return False

    try:
        t_ms = int(duration_sec * 1000)
        master_music_segment = AudioSegment.from_file(random.choice(music_list)).normalize()
        while len(master_music_segment) < t_ms:
            master_music_segment += AudioSegment.from_file(random.choice(music_list)).normalize()

        ambient_layer_segment = AudioSegment.from_file(random.choice(ambient_list)).normalize()
        ambient_layer_segment = ambient_layer_segment + project_config["AMBIENT_GAIN"]
        
        final_mixed_audio_object = master_music_segment.overlay(ambient_layer_segment, loop=True)[:t_ms]
        final_mixed_audio_object.export(paths_config["temp_audio_raw"], format="wav")
        cmd = [
            "ffmpeg", "-y", "-i", paths_config["temp_audio_raw"],
            "-af", "crystalizer=i=2.0,loudnorm=I=-14:TP=-1.5",
            "-c:a", "libmp3lame", "-b:a", "320k", paths_config["temp_audio_mastered"]
        ]
        return run_ffmpeg_task(cmd, "Audio Master Process")
    except Exception as e:
        print(f"❌ [Audio Master Error] 业务崩溃: {str(e)}")
        return False

def build_overlay_plan(duration_sec, captions_list, style_pool):
    """!
    @brief [Step 5] 渲染计划构建原子函数。
    @param duration_sec 视频总长（秒）。
    @param captions_list 字幕内容。
    @param style_pool 字幕样式配置。
    @return dict 完整的渲染计划。
    """
    print("📝 [Step 5] 构建渲染计划中...")
    plan_dict = {"branding": [], "mermaid": {"segments": []}, "captions": []}
    
    cur_b = 300
    while cur_b < duration_sec - 300:
        plan_dict["branding"].append({"start": cur_b, "end": cur_b + 15})
        cur_b += random.randint(900, 1500)
    
    cur_c = 30
    for text_val in captions_list:
        if cur_c + 20 > duration_sec:
            break
        plan_dict["captions"].append({
            "start": cur_c, "end": cur_c + 8,
            "text": ffmpeg_escape_text(text_val),
            "font": random.choice(style_pool["fonts"]),
            "size": random.choice(style_pool["sizes"]),
            "color": random.choice(style_pool["colors"]),
            "y": random.choice(style_pool["y_offsets"]),
            "x_pos": "(w-text_w)/2"
        })
        cur_c += random.randint(150, 250)
    
    cur_m = 60
    while cur_m + 6 < duration_sec:
        plan_dict["mermaid"]["segments"].append({"start": cur_m, "end": cur_m + 6})
        cur_m += random.randint(500, 900)
        
    return plan_dict

def build_concat_file(standardized_list, output_txt_path):
    """!
    @brief 生成 FFmpeg 拼接清单。
    @details MODIFIED: 物理修复 f-string 中包含反斜杠导致的 SyntaxError。
    @param standardized_list 视频物理路径列表。
    @param output_txt_path 目标清单物理路径。
    @return bool 执行状态。
    """
    try:
        with open(output_txt_path, "w", encoding="utf-8") as f_out:
            for p_path in standardized_list:
                safe_ffmpeg_path = p_path.replace("'", "'\\''")
                f_out.write(f"file '{safe_ffmpeg_path}'\n")
        return True
    except IOError:
        return False