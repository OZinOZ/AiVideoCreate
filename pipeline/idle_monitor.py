import argparse
import ctypes
import time
import subprocess
from datetime import datetime

# ===============================
# Windows Idle Time 获取
# ===============================
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0


# ===============================
# 配置
# ===============================
parser = argparse.ArgumentParser(description="Idle monitor to trigger pipeline")
parser.add_argument("-c", "--config", type=str, default="app_podcast.py", help="Config file to run")
args = parser.parse_args()

IDLE_THRESHOLD = 10 * 60   # 10分钟
CHECK_INTERVAL = 30        # 每30秒检查一次
CONFIG_FILE = args.config

# 防止重复触发
last_run_time = 0
COOLDOWN = 10 * 60   # 跑完后至少15分钟不再触发


# ===============================
# 主循环
# ===============================
print("Idle watcher started...")

while True:
    idle = get_idle_seconds()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Idle: {int(idle)} sec")

    now = time.time()

    if idle > IDLE_THRESHOLD and (now - last_run_time) > COOLDOWN:
        print(">>> User away. Starting video generation...")

        try:
            subprocess.run(
                ["python", "app_local_runner.py", "-c", CONFIG_FILE, "--fresh"],
                check=True
            )
        except Exception as e:
            print(f"Error running pipeline: {e}")

        last_run_time = time.time()
        print(">>> Task finished. Cooling down...")

    time.sleep(CHECK_INTERVAL)