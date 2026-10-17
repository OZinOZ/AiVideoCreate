"""
本地测试控制端脚本 (适配 Windows Google Drive 客户端)。
包含 API 存活探测，并强行忽略 SSL 证书校验以穿透企业级防火墙 (Fortinet等)。
在同步目录中准备任务环境，检测/轮询API地址，下发生成任务，成功后自动停止。
"""

import os
import sys
import time
import uuid
import shutil
import requests
import urllib3

# 禁用 requests 在 verify=False 时产生的大量 InsecureRequestWarning 警告打印
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 配置区域 (Configuration)
# ==========================================

# 【Windows 专属配置】Google Drive 桌面客户端的真实本地映射路径
DRIVE_BASE_DIR = r"G:\My Drive\AiGenerations"
API_PATH_FILE = os.path.join(DRIVE_BASE_DIR, "API_PATH.txt")

# 测试用的初始图片路径
SOURCE_IMAGE_PATH = r"C:\Users\zhang\Downloads\test_input.jpg"

# 轮询配置
POLL_INTERVAL_SECONDS = 3
MAX_POLL_ATTEMPTS = 100

# 视频生成命令模板
FFMPEG_CMD = (
    "ffmpeg -i '{INPUT_IMAGE}' "
    "-vf \"scale=4000:-1,zoompan=z='min(zoom+0.00033,1.5)':d=1500:fps=25:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080,scale=trunc(iw/2)*2:trunc(ih/2)*2\" "
    "-c:v libx264 -t 60 -pix_fmt yuv420p '{OUTPUT_VIDEO}'"
)
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

def get_or_wait_api_url():
    """读取现有 API 地址，若不存在则轮询等待 Colab 写入"""
    print("[网络读取] 尝试读取同步盘中的 API 地址...")
    
    try:
        if os.path.exists(API_PATH_FILE):
            with open(API_PATH_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content.startswith("http"):
                    print(f"[网络读取] [成功] 读取到记录的 API 地址: {content}")
                    return content
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[网络读取] [警告] 读取历史文件异常，将进入轮询: {exc}")

    print("[网络轮询] 未找到有效地址，开始等待 Colab 服务端上线并写入...")
    attempts = 0
    while attempts < MAX_POLL_ATTEMPTS:
        try:
            if os.path.exists(API_PATH_FILE):
                with open(API_PATH_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content.startswith("http"):
                        print(f"[网络轮询] [成功] 捕获到全新服务地址: {content}")
                        return content
        except Exception as exc: # pylint: disable=broad-exception-caught
            print(f"[网络轮询] [警告] 文件读取冲突，将重试: {exc}")
            
        time.sleep(POLL_INTERVAL_SECONDS)
        attempts += 1
        print(f"[网络轮询] 等待云盘同步中... (重试 {attempts}/{MAX_POLL_ATTEMPTS})")
        
    print(f"[网络轮询] [错误] 达到最大等待次数 ({MAX_POLL_ATTEMPTS})，未获取到地址。")
    return None

def ping_api_server(api_url):
    """发送探针，验证读取到的 API 地址是否仍然存活"""
    endpoint = f"{api_url}/docs"
    print(f"[健康探测] 正在验证云端服务是否存活: {endpoint}")
    try:
        # 添加 verify=False 忽略 Fortinet 等防火墙的 SSL 劫持
        response = requests.get(endpoint, timeout=5, verify=False)
        if response.status_code == 200:
            print("[健康探测] [成功] Colab 服务端在线，握手成功！")
            return True
        print(f"[健康探测] [错误] 接口响应异常，HTTP 状态码: {response.status_code}")
        return False
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[健康探测] [异常] 无法连接到服务器。可能 Colab 已断开或 ngrok 已失效: {exc}")
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
    """创建本次任务的专属目录并将测试图片塞入其中供云盘同步"""
    task_dir = os.path.join(DRIVE_BASE_DIR, task_id)
    try:
        os.makedirs(task_dir)
        print(f"[任务环境] [成功] 创建专属任务目录: {task_dir}")
        
        if not os.path.exists(SOURCE_IMAGE_PATH):
            print(f"[任务环境] [错误] 找不到指定的测试源图片: {SOURCE_IMAGE_PATH}")
            return False
            
        ext = os.path.splitext(SOURCE_IMAGE_PATH)[1]
        target_image_path = os.path.join(task_dir, f"{task_id}{ext}")
        shutil.copy2(SOURCE_IMAGE_PATH, target_image_path)
        print(f"[任务环境] [成功] 测试图片已塞入，等待客户端自动上云: {target_image_path}")
        return True
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[任务环境] [异常] 环境构造时发生崩溃: {exc}")
        return False

def trigger_generation_task(api_url, task_id):
    """向获取到的服务端地址正式下发视频生成指令"""
    endpoint = f"{api_url}/start"
    payload = {
        "task_id": task_id,
        "ffmpeg_command": FFMPEG_CMD
    }
    try:
        print(f"[任务下发] 正在呼叫云端接口: {endpoint}")
        # 添加 verify=False 忽略 SSL 校验
        response = requests.post(endpoint, json=payload, timeout=10, verify=False)
        if response.status_code == 200:
            print("[任务下发] [成功] 服务器已受理生成请求。")
            return True
        print(f"[任务下发] [错误] 接口调用失败，HTTP 状态码: {response.status_code}")
        return False
    except Exception as exc: # pylint: disable=broad-exception-caught
        print(f"[任务下发] [异常] 网络请求崩溃: {exc}")
        return False

def poll_task_status(api_url, task_id):
    """轮询查岗，直到服务端反馈成功或失败"""
    endpoint = f"{api_url}/query?task_id={task_id}"
    print("[状态跟踪] 开始高频查岗，监控云端生成进度...")
    while True:
        try:
            # 添加 verify=False 忽略 SSL 校验
            response = requests.get(endpoint, timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                print(f"[状态跟踪] 当前服务器反馈状态: {status}")
                
                if status == "success":
                    print("[状态跟踪] [成功] 远端确认任务已顺利完成！")
                    return True
                if status == "fail":
                    error_msg = data.get('error', '未提供详细错误')
                    print(f"[状态跟踪] [错误] 远端任务处理失败，服务端上报信息: {error_msg}")
                    return False
            else:
                print(f"[状态跟踪] [错误] 查询异常，HTTP 状态码: {response.status_code}")
        except Exception as exc: # pylint: disable=broad-exception-caught
            print(f"[状态跟踪] [异常] 查岗网络请求崩溃: {exc}")
            
        time.sleep(POLL_INTERVAL_SECONDS)

# ==========================================
# 主函数 (Main)
# ==========================================

def main():
    """主控流程，严格遵循平铺调用与失败即退出的设计"""
    print(">>> 启动自动化测试工作流 (防劫持版) <<<")
    
    if not init_drive_directory():
        print("[主流程] [严重错误] 初始化同步目录失败，阻断退出。")
        sys.exit(1)
        
    api_url = get_or_wait_api_url()
    if not api_url:
        print("[主流程] [严重错误] 无法获取 API 地址，阻断退出。")
        sys.exit(1)
        
    if not ping_api_server(api_url):
        print("[主流程] [严重错误] 服务端探测失败！请确认 Colab 正在运行。如果已停止，请重新运行 Colab。")
        sys.exit(1)
        
    task_id = generate_task_id()
    if not task_id:
        print("[主流程] [严重错误] 任务流水号生成失败，阻断退出。")
        sys.exit(1)
        
    if not setup_task_environment(task_id):
        print(f"[主流程] [严重错误] 任务环境 ({task_id}) 构建失败，阻断退出。")
        sys.exit(1)
        
    start_time = time.time() 
    if not trigger_generation_task(api_url, task_id):
        print("[主流程] [严重错误] 任务下发失败，阻断退出。")
        sys.exit(1)
        
    is_success = poll_task_status(api_url, task_id)
    if not is_success:
        print("[主流程] [严重错误] 任务执行最终被判定为失败，阻断退出。")
        sys.exit(1)

    elapsed = time.time() - start_time        
    print(f"\n>>> [耗时统计] 从触发下发到生成成功总共用时: {elapsed:.2f} 秒 <<<")    

    print(">>> [主流程] 执行成功！任务完成，Google Drive 客户端会自动将视频下载到本地目录。 <<<")
    sys.exit(0)

if __name__ == "__main__":
    main()