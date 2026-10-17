import pandas as pd
import time
import urllib.parse
import re
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ================= 配置区 =================
INPUT_CSV = r"E:\upwork\routes\SYD_dist.csv"
OUTPUT_CSV = r"E:\upwork\routes\SYD_dist_result.csv"
# ==========================================

def setup_driver():
    chrome_options = Options()
    # 过滤掉无用的终端报错日志
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_argument("--lang=zh-CN")
    # 如果要看过程，请保持 headless 为 False
    # chrome_options.add_argument("--headless") 
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def get_distance(driver, src, dst, is_retry=False):
    try:
        src_encoded = urllib.parse.quote(src)
        dst_encoded = urllib.parse.quote(dst)
        # 使用 Google Maps 预览链接
        url = f"https://www.google.com/maps/dir/{src_encoded}/{dst_encoded}/"
        driver.get(url)

        # 1. 增加一个基础等待，确保页面路线面板加载（这是最重要的）
        wait = WebDriverWait(driver, 15)
        try:
            # 等待侧边栏路线容器出现
            wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='section-directions-trip-0'] | //div[contains(@aria-label, '公里')] | //div[contains(@aria-label, 'km')]")))
        except:
            if not is_retry:
                print(f"      📍 路径未直接显示，尝试等待并重试...")
                time.sleep(3) # 额外多等几秒给地图渲染

        # 2. 全量扫描页面中所有可能的距离元素
        # Google Maps 的里程通常在这些 ID 或 Class 里，但也可能随版本变化
        possible_xpaths = [
            "//div[contains(@class, 'iv01mc')]", # 新版常用
            "//div[@id='section-directions-trip-0']//div[contains(text(), 'km')]", 
            "//span[contains(text(), 'km') or contains(text(), '公里')]",
            "//div[contains(@aria-label, '公里') or contains(@aria-label, 'km')]"
        ]
        
        found_text = ""
        for xpath in possible_xpaths:
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                t = el.text.strip()
                # 正则查找：数字 + (空格) + km
                if t and re.search(r"\d+[\d,.]*\s*(km|公里)", t, re.IGNORECASE):
                    found_text = t
                    break
            if found_text: break

        # 3. 如果通过元素没找到，尝试从整个 Body 文本里捞（兜底方案）
        if not found_text:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            # 匹配类似 "15.4 km" 或 "7 公里"
            match_all = re.findall(r"(\d+[\d,.]*)\s*(?:km|公里)", body_text, re.IGNORECASE)
            if match_all:
                # 路线距离通常是第一个出现的较大数字（排除步行时间等）
                found_text = match_all[0] + " km"

        if found_text:
            print(f"      🔍 成功捕获文本: {repr(found_text)}")
            clean_text = found_text.replace(',', '')
            match = re.search(r"(\d+\.?\d*)", clean_text)
            if match:
                return float(match.group(1))

        # 4. 如果还是没找到，打印当前页面看到的关键信息辅助调试
        print(f"      ⚠️ 页面已显示但未匹配到距离。标题: {driver.title}")
        return None

    except Exception as e:
        print(f"      ❌ 脚本内部异常: {str(e)[:100]}")
        return None

def main():
    try:
        df = pd.read_csv(INPUT_CSV)
    except Exception as e:
        print(f"❌ 读取CSV失败: {e}")
        return

    driver = setup_driver()
    distances = []

    print(f"🚀 任务启动，总计 {len(df)} 条数据")

    for index, row in df.iterrows():
        src = row['src']
        dst = row['dst']
        print(f"[{index+1}/{len(df)}] 正在计算: {dst}")
        
        dist = get_distance(driver, src, dst)
        distances.append(dist)
        
        if dist:
            print(f"      ✅ 最终距离: {dist} km")
        else:
            print(f"      ❌ 最终距离: 无法获取")
        
        # 适当增加间隔，防止被 Google 标记为机器人
        time.sleep(random.uniform(2, 4))

    df['distance_km'] = distances
    df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    
    driver.quit()
    print(f"\n🎉 运行结束，结果已保存。")

if __name__ == "__main__":
    main()