"""
本地测试控制端脚本 (基于 Google Drive 文件状态机通信)。
完全摒弃网络 API，通过 task_file.txt 跨平台下发指令并轮询执行结果。
"""

import os
import sys
import time
import uuid
import shutil
import json

# ==========================================
# 配置区域 (Configuration)
# ==========================================

# 【Windows 专属配置】Google Drive 桌面客户端的真实本地映射路径
DRIVE_BASE_DIR = r"G:\My Drive\AiGenerations"
TASK_FILE_PATH = os.path.join(DRIVE_BASE_DIR, "task_file.txt")

# 测试用的初始图片路径
SOURCE_IMAGE_PATH = r"C:\Users\zhang\Downloads\test_input.jpg"

# 轮询配置
POLL_INTERVAL_SECONDS = 3
MAX_POLL_ATTEMPTS = 200

# 视频生成命令模板 (留出占位符供 Colab 端替换绝对路径)
FFMPEG_CMD = "ffmpeg -loop 1 -i '{INPUT_IMAGE}' -vf \"scale=trunc(iw/2)*2:trunc(ih/2)*2\" -c:v libx264 -t 3 -pix_fmt yuv420p '{OUTPUT_VIDEO}'"

# ==========================================
# 底层函数区域 (Underlying Functions)
# ==========================================

def init_drive_directory():
    """初始化同步目录，确保根目录存在"""
    try:
        if not os.path.exists(DRIVE_BASE_DIR):
            os.makedirs(DRIVE_BASE_DIR)
            print(f"[基础目录] [成功] 创建同步根目录: {DRIVE_BASE_DIR}")
        else:
            print(f"[基础目录] [成功] 同步根目录已就绪: {DRIVE_BASE_DIR}")
        return True
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[基础目录] [异常] 目录初始化失败: {exc}")
        return False

def generate_task_id():
    """生成唯一的任务标识符"""
    try:
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        print(f"[任务ID] [成功] 生成唯一流水号: {task_id}")
        return task_id
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[任务ID] [异常] 生成ID失败: {exc}")
        return None

def setup_task_environment(task_id):
    """创建本次任务的专属目录并将测试图片塞入其中"""
    task_dir = os.path.join(DRIVE_BASE_DIR, task_id)
    try:
        os.makedirs(task_dir)
        print(f"[任务环境] [成功] 创建专属任务目录: {task_dir}")
        
        if not os.path.exists(SOURCE_IMAGE_PATH):
            print(f"[任务环境] [错误] 找不到指定的测试源图片: {SOURCE_IMAGE_PATH}")
            return None, None
            
        ext = os.path.splitext(SOURCE_IMAGE_PATH)[1]
        image_name = f"{task_id}{ext}"
        target_image_path = os.path.join(task_dir, image_name)
        shutil.copy2(SOURCE_IMAGE_PATH, target_image_path)
        print(f"[任务环境] [成功] 测试图片已塞入，等待云盘同步: {target_image_path}")
        
        # 返回相对路径，解决 Windows/Linux 路径差异问题
        relative_image_path = f"{task_id}/{image_name}"
        return task_dir, relative_image_path
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[任务环境] [异常] 环境构造时发生崩溃: {exc}")
        return None, None

def write_start_task_file(relative_image_path, command):
    """将任务信息和 start 状态写入 task_file.txt (格式化为JSON提高稳健性)"""
    print(f"[指令下发] 准备写入指令至: {TASK_FILE_PATH}")
    task_data = {
        "image": relative_image_path,
        "command": command,
        "status": "start"
    }
    try:
        with open(TASK_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=4)
        print("[指令下发] [成功] 任务写入成功，状态为: start")
        return True
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[指令下发] [异常] 写入文件崩溃: {exc}")
        return False

def poll_task_status():
    """轮询 task_file.txt，直到状态变为 success 或 fail"""
    print("[状态跟踪] 开始高频轮询 task_file.txt 监控云端执行进度...")
    attempts = 0
    while attempts < MAX_POLL_ATTEMPTS:
        try:
            if os.path.exists(TASK_FILE_PATH):
                with open(TASK_FILE_PATH, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        status = data.get("status", "unknown")
                        
                        if status == "running":
                            print("[状态跟踪] 云端正在处理任务 (running)...")
                        elif status == "success":
                            video_path = data.get("video", "未知路径")
                            print(f"[状态跟踪] [成功] 远端确认任务已完成！输出视频相对路径: {video_path}")
                            return True
                        elif status == "fail":
                            print("[状态跟踪] [错误] 远端任务处理失败。")
                            return False
        except json.JSONDecodeError:
            print("[状态跟踪] [警告] 读取到不完整的文件内容，等待下一次同步补全...")
        except Exception as exc: # pylint: disable=broad-exception-caught
            print(f"[状态跟踪] [警告] 文件读取冲突或异常: {exc}")
            
        time.sleep(POLL_INTERVAL_SECONDS)
        attempts += 1
        
    print(f"[状态跟踪] [错误] 达到最大等待次数 ({MAX_POLL_ATTEMPTS})，轮询超时退出。")
    return False

def clear_task_file():
    """测试结束后清空/删除 task_file.txt"""
    print("[环境清理] 正在清空指令文件...")
    try:
        if os.path.exists(TASK_FILE_PATH):
            os.remove(TASK_FILE_PATH)
            print("[环境清理] [成功] task_file.txt 已被成功移除。")
        else:
            print("[环境清理] [跳过] task_file.txt 不存在。")
        return True
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[环境清理] [异常] 删除指令文件发生崩溃: {exc}")
        return False

# ==========================================
# 主函数 (Main)
# ==========================================

def main():
    """主控流程，严格按顺序调度底层文件操作"""
    print(">>> 启动基于文件的本地自动化控制端 <<<")
    
    if not init_drive_directory():
        sys.exit(1)
        
    task_id = generate_task_id()
    if not task_id:
        sys.exit(1)
        
    task_dir, relative_image_path = setup_task_environment(task_id)
    if not task_dir or not relative_image_path:
        sys.exit(1)
        
    if not write_start_task_file(relative_image_path, FFMPEG_CMD):
        sys.exit(1)
        
    is_success = poll_task_status()
    if not is_success:
        print("[主流程] [严重错误] 轮询判定云端任务失败。")
        clear_task_file() # 失败也尝试清理
        sys.exit(1)
        
    if not clear_task_file():
        print("[主流程] [警告] 虽然任务成功，但清理指令文件失败。")
        sys.exit(1)
        
    print(">>> [主流程] 执行大圆满！任务文件已清理，程序正常退出。 <<<")
    sys.exit(0)

if __name__ == "__main__":
    main()