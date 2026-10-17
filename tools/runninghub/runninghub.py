import subprocess
import time
import webbrowser
import psutil
import os

# 👉 你的 Chrome 路径（一般不用改）
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

TARGET_URL = "https://www.runninghub.ai/"

def is_chrome_running():
    """检查 Chrome 是否在运行"""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'chrome' in proc.info['name'].lower():
            return True
    return False

def open_chrome():
    """启动 Chrome"""
    try:
        subprocess.Popen([CHROME_PATH])
        print("✅ Chrome 已启动")
        time.sleep(3)  # 等待启动
    except Exception as e:
        print(f"❌ 启动 Chrome 失败: {e}")

def open_new_tab(url):
    """打开新 tab"""
    try:
        webbrowser.get('chrome').open_new_tab(url)
        print(f"🌐 已打开新标签页: {url}")
    except:
        # fallback（如果 webbrowser 找不到 chrome）
        subprocess.Popen([CHROME_PATH, url])
        print(f"🌐 使用 fallback 打开: {url}")

def main():
    if not is_chrome_running():
        print("⚠️ Chrome 未运行，准备启动...")
        open_chrome()
    else:
        print("✅ Chrome 已在运行")

    open_new_tab(TARGET_URL)

if __name__ == "__main__":
    main()