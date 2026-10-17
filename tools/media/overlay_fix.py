"""
Batch Video Converter.
Converts all video files in a specified directory to 1920x1080, 5Mbps bitrate, and 25 fps.
Strictly adheres to pylint standards, layered logic, and mandatory logging requirements.
"""

import os
import subprocess
from typing import List

# ==========================================
# CONFIGURATION
# ==========================================
CONFIG = {
    "input_directory": "Y:/assets/Overlays",
    "output_directory": "Y:/assets/Overlays/output_videos",
    "target_resolution": "1920:1080",
    "target_fps": "25",
    "target_bitrate": "5M",
    # 强制控制码率波动的最高阈值，确保最终文件体积可控
    "max_bitrate": "5M",
    "buf_size": "10M",
    "video_extensions": (".mp4", ".mov", ".mkv", ".avi", ".flv", ".wmv")
}

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def setup_directories(input_dir: str, output_dir: str) -> bool:
    """Check if the input directory exists and create the output directory."""
    print(f"[INFO] Checking directories. Input: {input_dir} | Output: {output_dir}")
    
    if not os.path.exists(input_dir):
        print(f"[ERROR] Input directory does not exist: {input_dir}")
        return False
    
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"[INFO] Created output directory: {output_dir}")
        except OSError as error:
            print(f"[ERROR] Failed to create output directory {output_dir}: {error}")
            return False
            
    return True

def get_video_files(input_dir: str, extensions: tuple) -> List[str]:
    """Scan the input directory and return a list of video files matching the extensions."""
    print(f"[INFO] Scanning for video files in: {input_dir}")
    video_files = []
    try:
        for filename in os.listdir(input_dir):
            if filename.lower().endswith(extensions):
                video_files.append(filename)
        print(f"[INFO] Found {len(video_files)} video file(s) matching extensions {extensions}.")
        return video_files
    except OSError as error:
        print(f"[ERROR] Failed to read input directory {input_dir}: {error}")
        return []

def build_ffmpeg_command(input_path: str, output_path: str) -> List[str]:
    """Build the FFmpeg command list for the video conversion."""
    print(f"[INFO] Building FFmpeg command for: {input_path}")
    
    # 采用 scale=1920:1080 强制拉伸。
    # 如需保持原比例并添加黑边，可替换为: scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vf", f"scale={CONFIG['target_resolution']}",
        "-r", CONFIG["target_fps"],
        "-b:v", CONFIG["target_bitrate"],
        "-maxrate", CONFIG["max_bitrate"],
        "-bufsize", CONFIG["buf_size"],
        "-c:a", "aac",
        "-b:a", "192k",
        output_path
    ]
    return cmd

def process_single_video(input_path: str, output_path: str) -> bool:
    """Execute FFmpeg to process a single video file."""
    print(f"[INFO] Starting conversion: {input_path} -> {output_path}")
    cmd = build_ffmpeg_command(input_path, output_path)
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[INFO] Successfully converted: {output_path}")
        return True
    except subprocess.CalledProcessError as error:
        print(f"[ERROR] FFmpeg conversion failed for {input_path}. Return code: {error.returncode}")
        print(f"[ERROR] FFmpeg STDERR: {error.stderr}")
        return False
    except FileNotFoundError as error:
        print(f"[ERROR] FFmpeg executable not found. Please install FFmpeg and add it to PATH. Error: {error}")
        return False
    except Exception as error:
        print(f"[ERROR] Unexpected error during conversion of {input_path}: {error}")
        return False

def process_all_videos() -> None:
    """Orchestrate the processing of all video files in the configured directory."""
    print("[INFO] --- STARTING BATCH VIDEO CONVERSION ---")
    
    in_dir = CONFIG["input_directory"]
    out_dir = CONFIG["output_directory"]
    
    if not setup_directories(in_dir, out_dir):
        print("[ERROR] Directory setup failed. Halting process.")
        return
        
    video_files = get_video_files(in_dir, CONFIG["video_extensions"])
    
    if not video_files:
        print("[ERROR] No video files found to process. Exiting.")
        return
        
    success_count = 0
    failure_count = 0
    
    for filename in video_files:
        input_path = os.path.join(in_dir, filename)
        # 强制将输出后缀改为 .mp4 保证兼容性
        output_filename = os.path.splitext(filename)[0] + "_1080p.mp4"
        output_path = os.path.join(out_dir, output_filename)
        
        is_success = process_single_video(input_path, output_path)
        if is_success:
            success_count += 1
        else:
            failure_count += 1
            print(f"[ERROR] Failed to process file: {filename}")
            
    print("[INFO] --- BATCH CONVERSION COMPLETED ---")
    print(f"[INFO] Total Success: {success_count}")
    print(f"[INFO] Total Failures: {failure_count}")

# ==========================================
# MAIN ORCHESTRATOR
# ==========================================
def main() -> None:
    """Main entry point. Strictly limited to calling underlying orchestration."""
    process_all_videos()

if __name__ == "__main__":
    main()