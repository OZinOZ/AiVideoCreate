# -*- coding: utf-8 -*-
"""
Content OS - Cross-Platform YouTube Uploader
Features: Anti-bot random sleep, Bilingual channel support, CSV tracking.
"""

import os
import sys
import time
import random
import csv
import json
import argparse
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# =====================================================================
# 配置区 (CONFIGURATION)
# =====================================================================

# 默认基础路径 (可根据你的实际环境修改，支持跨平台格式)
DEFAULT_BASE_PATH = r"I:\AiVideos"

# YouTube API 权限范围 (仅限上传视频，最安全的最小权限)
SCOPES = ['https://www.googleapis.com/auth/youtube']
# SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def log_print(level: str, message: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level.ljust(8)}] {message}")

# =====================================================================
# YOUTUBE AUTH & UPLOAD
# =====================================================================

def get_authenticated_service(lang: str, target_dir: str):
    """根据语言标识从目标频道目录加载对应的 YouTube API Token 和 Client Secret"""
    client_secret_file = os.path.join(target_dir, f"client_secret_{lang}.json")
    token_file = os.path.join(target_dir, f"token_{lang}.json")
    
    if not os.path.exists(client_secret_file) and not os.path.exists(token_file):
        log_print("ERROR", f"Missing credentials! Please ensure {client_secret_file} exists in the script directory.")
        sys.exit(1)

    credentials = None
    if os.path.exists(token_file):
        log_print("AUTH", f"Loading existing token from {token_file}")
        credentials = Credentials.from_authorized_user_file(token_file, SCOPES)
        
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            log_print("AUTH", "Refreshing expired token...")
            credentials.refresh(Request())
        else:
            log_print("AUTH", f"Initiating new OAuth flow using {client_secret_file}...")
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            # 在没有桌面的 Linux 服务器上可能需要 run_console()，本地用 run_local_server
            credentials = flow.run_local_server(port=0)
            
        with open(token_file, 'w') as token:
            token.write(credentials.to_json())
            log_print("AUTH", f"Token saved to {token_file}")

    return build('youtube', 'v3', credentials=credentials)

def upload_video(youtube, video_path: str, metadata: dict):
    """执行视频上传并返回 Video ID"""
    body = {
        'snippet': {
            'title': metadata.get('title', 'Untitled ASMR Story'),
            'description': metadata.get('description', ''),
            'tags': metadata.get('tags', []),
            'categoryId': metadata.get('categoryId', '24') # 24 = Entertainment
        },
        'status': {
            'privacyStatus': 'private', # 建议默认 private，检查无误后再在后台公开
            'selfDeclaredMadeForKids': False
        }
    }

    # 使用断点续传块 (chunk_size=-1 代表自动适配)
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    log_print("UPLOAD", f"Uploading {os.path.basename(video_path)}... (This may take a while)")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [UPLOAD  ] Progress: {int(status.progress() * 100)}%", end='\r')
    print() # 换行
    
    video_id = response.get('id')
    log_print("SUCCESS", f"Video uploaded successfully! Video ID: {video_id}")
    return video_id

def upload_thumbnail(youtube, video_id: str, thumb_path: str):
    """附加上传自定义精美封面图"""
    log_print("UPLOAD", f"Uploading custom thumbnail: {os.path.basename(thumb_path)}...")
    try:
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumb_path, mimetype='image/png')
            # media_body=MediaFileUpload(thumb_path)
        )
        request.execute()
        log_print("SUCCESS", "Thumbnail attached to video successfully!")
    except Exception as e:
        log_print("WARN", f"Failed to upload thumbnail: {e}")

# =====================================================================
# MAIN LOGIC
# =====================================================================
# python youtube_uploader.py TankTailTalk en
def main():
    parser = argparse.ArgumentParser(description="Content OS - YouTube Anti-Bot Uploader")
    parser.add_argument("directory", type=str, help="Target directory name inside base path")
    parser.add_argument("lang", choices=['en', 'cn'], help="Target language channel ('en' or 'cn')")
    args = parser.parse_args()

    # 1. 反审查随机休眠机制 (100 - 300 秒)
    sleep_time = random.randint(100, 300)
    log_print("ANTI-BOT", f"Sleeping for {sleep_time} seconds to simulate human behavior...")
    time.sleep(sleep_time)
    log_print("ANTI-BOT", "Awake. Starting execution.")

    target_dir = os.path.join(DEFAULT_BASE_PATH, args.directory)
    csv_path = os.path.join(target_dir, "record.csv")

    if not os.path.exists(csv_path):
        log_print("ERROR", f"Record CSV not found at {csv_path}")
        sys.exit(1)

    # 2. 读取并处理 CSV
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # 动态检查并添加 upload_en / upload_cn 列
    upload_col = f"upload_{args.lang}"
    if upload_col not in fieldnames:
        fieldnames.append(upload_col)

    target_row_idx = -1
    
    # 3. 倒序搜索最后一个 SUCCESS 且 尚未上传 的记录
    for i in range(len(rows)-1, -1, -1):
        row = rows[i]
        
        # 初始化空值为 NO
        if not row.get(upload_col) or row[upload_col].strip() == '':
            row[upload_col] = 'NO'
            
        if row.get('result') == 'SUCCESS' and row.get(upload_col, 'NO').upper() == 'NO':
            target_row_idx = i
            break

    if target_row_idx == -1:
        log_print("INFO", f"No successful, unuploaded ({args.lang}) records found in {args.directory}. Exiting.")
        sys.exit(0)

    target_row = rows[target_row_idx]
    workspace_folder = target_row.get('output_path', '')
    
    if not workspace_folder or not os.path.exists(workspace_folder):
        log_print("ERROR", f"Output path not found: {workspace_folder}")
        sys.exit(1)

    # 4. 组装视频、Metadata 与封面路径
    video_filename = f"FINAL_STORY_{args.lang.upper()}.mp4"
    video_path = os.path.join(workspace_folder, video_filename)
    metadata_path = os.path.join(workspace_folder, f"youtube_metadata_{args.lang}.json")
    
    # 优先匹配带后缀的专属高级封面（如 thumbnail_cn.png），其次降级匹配旧版或无字封面（thumbnail.png）
    thumb_path = os.path.join(workspace_folder, f"thumbnail_{args.lang}.png")
    if not os.path.exists(thumb_path):
        thumb_path = os.path.join(workspace_folder, "thumbnail.png")

    if not os.path.exists(video_path):
        log_print("ERROR", f"Target video missing: {video_path}")
        sys.exit(1)

    metadata = {}
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            log_print("INFO", f"Loaded metadata for [{metadata.get('title', 'Unknown')}]")
        except Exception as e:
            log_print("WARN", f"Failed to parse metadata JSON: {e}")
    else:
        log_print("WARN", f"Metadata file missing at {metadata_path}. Uploading with default blank details.")

    # 5. 鉴权与上传
    youtube_service = get_authenticated_service(args.lang, target_dir)
    try:
        video_id = upload_video(youtube_service, video_path, metadata)
        
        # 6. 上传封面（如果生成了封面）
        if os.path.exists(thumb_path):
            upload_thumbnail(youtube_service, video_id, thumb_path)
        
        # 7. 上传成功，将 CSV 对应状态改为 YES
        rows[target_row_idx][upload_col] = 'YES'
        
        # 写回 CSV
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
        log_print("SYSTEM", f"CSV record updated. '{upload_col}' set to YES.")
        
    except Exception as e:
        log_print("ERROR", f"Upload failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()