"""
Google Maps Scraper - Debug Mode (Visible Window)
Logic: Visible browser to observe loading behavior.
Author: Gemini
Date: 2026-03-11
"""

import time
import re
import urllib.parse
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ================= 配置部分 =================
INPUT_CSV = r"E:\upwork\routes\MEL_dist.csv"
OUTPUT_CSV = r"E:\upwork\routes\MEL_dist_result_debug.csv"

# 【关键修改】关闭无头模式，让你能看到浏览器运行
HEADLESS_MODE = False 
PAGE_LOAD_TIMEOUT = 30 
# ===========================================

def init_driver():
    """初始化并启动可见的浏览器"""
    print("正在启动 Chrome 浏览器...")
    try:
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument("--headless=new")
        
        # 基础配置
        chrome_options.add_argument("--window-size=1280,800")
        chrome_options.add_argument("--lang=en-US") # 统一用英文，方便 aria-label 匹配 'km'
        
        # 屏蔽冗余的系统报错日志
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("✅ 浏览器已启动（你应该能看到窗口了）")
        return driver
    except Exception as e:
        print(f"❌ 驱动初始化失败: {e}")
        return None

def extract_distance(driver):
    """尝试从页面提取距离数据"""
    print("正在分析页面内容...")
    try:
        # 方案 1: 寻找带 km 的文本 (最通用)
        # Google Maps 的距离通常在包含 'km' 或 'miles' 的 div/span 中
        patterns = ["//div[contains(text(), 'km')]", "//span[contains(text(), 'km')]"]
        
        for p in patterns:
            elements = driver.find_elements(By.XPATH, p)
            for e in elements:
                text = e.text
                if text:
                    match = re.search(r"(\d+(\.\d+)?)\s*km", text)
                    if match:
                        print(f"🎯  方案 1 成功提取: {match.group(1)} km")
                        return float(match.group(1))
        
        # 方案 2: 寻找 aria-label (你提到的稳定方案)
        aria_elements = driver.find_elements(By.XPATH, "//*[contains(@aria-label, 'km')]")
        for e in aria_elements:
            label = e.get_attribute("aria-label")
            match = re.search(r"(\d+(\.\d+)?)\s*km", label)
            if match:
                print(f"🎯  方案 2 成功提取: {match.group(1)} km")
                return float(match.group(1))
                
        return None
    except Exception as e:
        print(f"⚠️ 提取出错: {e}")
        return None

def process_route(driver, src, dst):
    """导航并获取结果"""
    # 构造更稳定的 Google Maps 搜索 URL
    query = f"{src} to {dst}"
    url = f"https://www.google.com/maps/dir/{urllib.parse.quote(src)}/{urllib.parse.quote(dst)}/"
    
    print(f"\n查询路线: {src} -> {dst}")
    try:
        driver.get(url)
        
        # 等待页面加载（寻找左侧详情面板的特征）
        # 如果出现“同意/接受 Cookie”的弹窗，这里可能需要手动点一下，或者脚本跳过
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # 给地图渲染留出时间，观察浏览器窗口是否卡住
        time.sleep(5) 
        
        return extract_distance(driver)
    except Exception as e:
        print(f"❌ 任务超时或加载失败: {type(e).__name__}")
        return None

def main():
    df = pd.read_csv(INPUT_CSV)
    driver = init_driver()
    if not driver: return

    results = []
    try:
        for i, row in df.iterrows():
            print(f"--- 任务 [{i+1}/{len(df)}] ---")
            dist = process_route(driver, str(row['src']), str(row['dst']))
            
            if dist:
                print(f"🎯 成功提取: {dist} km")
                results.append(dist)
            else:
                print("🛑 提取失败（请检查浏览器窗口是否停留在搜索建议页）")
                results.append("ERROR")
            
            time.sleep(2)
            
    finally:
        df["distance_km"] = results
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        driver.quit()
        print(f"\n📁 处理完成，结果保存至: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()