import os
import time
import requests
import random
from urllib.parse import urlparse

# ==========================================
# --- 全局配置区域 (User Configuration) ---
# ==========================================

# 1. 设置 API 密钥 (必须填写，否则无法下载)
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

# 2. 下载源选择: 'pexels' 或 'pixabay'
SOURCE = 'pixabay' 

# 3. 下载类型: 'video' (视频), 'image' (图片), 'audio' (仅 Pixabay 支持)
MEDIA_TYPE = 'audio'

# 4. 搜索关键词 (英文效果最好)
SEARCH_QUERY = "cinematic ambient"

# 5. 存放目录
SAVE_DIR = "H:\\resources\\cinema_music"

# 6. 每次循环尝试下载的数量
BATCH_SIZE = 5


# 7. 最大下载数量
MAX_DOWNLOADS = 50

# ==========================================
# --- 脚本逻辑区域 (Script Logic) ---
# ==========================================

def ensure_dir(directory):
    """确保目录存在"""
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"[*] 创建目录: {directory}")

def download_file(url, folder, prefix, file_id):
    """下载文件并自动去重"""
    try:
        # 解析文件后缀
        parsed_url = urlparse(url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1]
        if not ext or len(ext) > 5:
            # 如果没抓到后缀，根据类型给默认值
            if MEDIA_TYPE == 'video': ext = '.mp4'
            elif MEDIA_TYPE == 'image': ext = '.jpg'
            elif MEDIA_TYPE == 'audio': ext = '.mp3'
        
        # 构建唯一文件名: 来源_ID.后缀
        filename = f"{prefix}_{file_id}{ext}"
        filepath = os.path.join(folder, filename)

        # 检查是否存在
        if os.path.exists(filepath):
            print(f"[跳过] 文件已存在: {filename}")
            return

        # 开始下载
        print(f"[下载中] {filename} ...")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[成功] 已保存: {filename}")

    except Exception as e:
        print(f"[错误] 下载失败 {url}: {e}")

def get_pexels_media():
    """从 Pexels 获取资源列表"""
    if not PEXELS_API_KEY or "你的" in PEXELS_API_KEY:
        print("[错误] 请先配置 Pexels API Key")
        return []

    headers = {'Authorization': PEXELS_API_KEY}
    # Pexels 不支持 Audio API，只有 Video 和 Photo
    if MEDIA_TYPE == 'audio':
        print("[提示] Pexels API 不支持音频下载，请切换到 Pixabay。")
        return []

    # 随机页码以获取不同内容
    random_page = random.randint(1, 20)
    
    base_url = "https://api.pexels.com"
    if MEDIA_TYPE == 'image':
        url = f"{base_url}/v1/search?query={SEARCH_QUERY}&per_page={BATCH_SIZE}&page={random_page}"
    else: # video
        url = f"{base_url}/videos/search?query={SEARCH_QUERY}&per_page={BATCH_SIZE}&page={random_page}"

    try:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print(f"[API错误] Pexels 响应: {res.text}")
            return []
        
        data = res.json()
        results = []
        
        items = data.get('photos', []) if MEDIA_TYPE == 'image' else data.get('videos', [])
        
        for item in items:
            item_id = str(item['id'])
            download_url = ""
            
            if MEDIA_TYPE == 'image':
                download_url = item['src']['original']
            else:
                # 寻找最高质量的视频链接
                video_files = item.get('video_files', [])
                # 简单排序取最大的
                if video_files:
                    sorted_files = sorted(video_files, key=lambda x: x['width'] * x['height'], reverse=True)
                    download_url = sorted_files[0]['link']
            
            if download_url:
                results.append({'id': item_id, 'url': download_url})
                
        return results
    except Exception as e:
        print(f"[异常] Pexels 请求失败: {e}")
        return []

def get_pixabay_media():
    """从 Pixabay 获取资源列表"""
    if not PIXABAY_API_KEY or "你的" in PIXABAY_API_KEY:
        print("[错误] 请先配置 Pixabay API Key")
        return []

    # 随机页码
    random_page = random.randint(1, MAX_DOWNLOADS)
    
    # 基础参数
    params = {
        'key': PIXABAY_API_KEY,
        'q': SEARCH_QUERY,
        'per_page': BATCH_SIZE,
        'page': random_page
    }

    base_url = "https://pixabay.com/api/"
    
    if MEDIA_TYPE == 'video':
        base_url = "https://pixabay.com/api/videos/"
    # 注意：Pixabay 音频 API 并没有完全公开在标准文档中，但如果支持 images/videos，我们主要处理这两个。
    # 这里为了稳健性，主要处理 Video 和 Image。如果是 Audio，Pixabay 比较特殊，这里暂按不支持处理或你可以自行扩展。
    
    try:
        res = requests.get(base_url, params=params)
        if res.status_code != 200:
            print(f"[API错误] Pixabay 响应: {res.text}")
            return []
            
        data = res.json()
        hits = data.get('hits', [])
        results = []

        for item in hits:
            item_id = str(item['id'])
            download_url = ""

            if MEDIA_TYPE == 'image':
                download_url = item.get('largeImageURL') or item.get('webformatURL')
            elif MEDIA_TYPE == 'video':
                # 获取最大的视频文件
                videos = item.get('videos', {})
                if videos.get('large'):
                    download_url = videos['large']['url']
                elif videos.get('medium'):
                    download_url = videos['medium']['url']
                elif videos.get('tiny'): # fallback
                     download_url = videos['tiny']['url']

            if download_url:
                results.append({'id': item_id, 'url': download_url})
        
        return results

    except Exception as e:
        print(f"[异常] Pixabay 请求失败: {e}")
        return []

def main_job():
    print(f"\n--- 开始新一轮抓取: {time.strftime('%H:%M:%S')} ---")
    print(f"源: {SOURCE} | 类型: {MEDIA_TYPE} | 关键词: {SEARCH_QUERY}")
    
    ensure_dir(SAVE_DIR)
    
    media_list = []
    if SOURCE.lower() == 'pexels':
        media_list = get_pexels_media()
    elif SOURCE.lower() == 'pixabay':
        media_list = get_pixabay_media()
    else:
        print("未知的 SOURCE 设置，请检查配置。")
        return

    if not media_list:
        print("[-] 未找到任何媒体资源 (或 API 额度耗尽/出错)")
        return

    print(f"[*] 获取到 {len(media_list)} 个资源链接，准备处理...")
    
    for media in media_list:
        download_file(media['url'], SAVE_DIR, SOURCE, media['id'])

if __name__ == "__main__":
    print(">>> 自动化素材下载器已启动 <<<")
    print(">>> 按 Ctrl+C 停止脚本 <<<")
    
    downloaded_count = 0
    # 立即执行一次
    main_job()
    
    # 之后每 60 秒执行一次
    while True:
        try:
            time.sleep(100)
            main_job()
            downloaded_count += 1
            if downloaded_count >= MAX_DOWNLOADS:
                print("\n程序已停止。")
                break   
        except KeyboardInterrupt:
            print("\n程序已停止。")
            break
        except Exception as e:
            print(f"主循环发生错误: {e}")
            time.sleep(10) # 出错后等待一会再试