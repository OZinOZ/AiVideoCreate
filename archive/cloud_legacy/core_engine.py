# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches, too-many-instance-attributes, missing-docstring
"""
Core Engine V119 - Shared Module (Ken Burns Cinematic Amplitude Edition)
Features: 1.35x High-Amplitude Zoompan, 6-Way Motion, Overlay Optimization.
Added: Strict Segment Validation & Image Generation Retry/Circuit Breaker.
Integrated: Universal LLM Output Cleaning Pipeline.
Fixed: Added max_tokens and programmatic circuit breakers to prevent LLM runaway.
Added: gpt-oss-20b compatible robust API call and SSML dynamic pause tagger.
"""

import os
import sys
import asyncio
import re
import json
import time
import csv
import random
import subprocess
import atexit
import urllib.request
from datetime import datetime
from dataclasses import dataclass

import httpx
from google import genai
from openai import AsyncOpenAI
from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
from pedalboard.io import AudioFile
import edge_tts
from tenacity import retry, stop_after_attempt, wait_exponential

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# =====================================================================
# CORE CONFIGURATIONS
# =====================================================================

RUNNINGHUB_TIMEOUT_SEC = 600
API_POLL_INTERVAL_SEC = 10
HTTP_TIMEOUT_SEC = 60.0

MODEL_CONFIG = {
    "GEMINI_MODEL": "gemini-2.5-pro",
    "KIMI_MODEL": "moonshotai/kimi-k2.5",
    "OPENAI_MODEL": "gpt-4o-mini",
    "DEEPSEEK_MODEL": "deepseek-ai/DeepSeek-V3",
    "OSS_MODEL": "openai/gpt-oss-120b", 
    "VOICE_EN": "en-GB-SoniaNeural",
    "VOICE_CN": "zh-CN-XiaoxiaoNeural", 
}

RUNNINGHUB_CONFIG = {
    "KEY": os.getenv("RUNNINGHUB_API_KEY"),
    "WF_T2I": "2014487614874718210",
    "T2I_NODE": "111"
}

PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 5.0, "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -25.0, "COMP_RATIO": 3.0, "LIMIT_DB": -3.0
}

YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secret.json'

# LLM 文本清洗正则配置
# 模式 1：匹配无意义的纯符号分割线 (例如 "----------" 或 "========")
PATTERN_PURE_SYMBOLS = r"^[\s\-\*#=~_]{3,}\s*$"
# 模式 2：匹配带有常见 AI 前缀/后缀的标题行，容错各种符号包裹
# 例如: "--- 中文文案 ---", "### 最终输出：", "【翻译结果】"
PATTERN_AI_PREFIXES = r"^[\s\-\*#=【\[]*(中文|英文|最终)?(文案|输出|正文|翻译|生成|故事|内容|结果)[】\]\s\-\*#=]*[:：]?\s*$"

# =====================================================================
# DATA STRUCTURES & UTILITIES
# =====================================================================

# 【新增核心】：工业级全局急停开关
class SystemController:
    """
    外部控制探针：只要在运行目录下新建一个 stop.txt，
    系统探测到后会立即引发精准的 KeyboardInterrupt 从而触发全链路优雅退出。
    """
    STOP_FILE = "stop.txt"

    @classmethod
    def check_stop_signal(cls):
        if os.path.exists(cls.STOP_FILE):
            log_status("SYSTEM", "🛑 检测到 stop.txt 外部停止信号! 正在启动全线优雅急停...", "CRITICAL")
            try:
                os.remove(cls.STOP_FILE) # 消费掉这个文件，防止下次启动直接暴毙
            except Exception:
                pass
            raise KeyboardInterrupt("Graceful shutdown triggered by external stop.txt")

@dataclass
class MediaSegment:
    index: int
    en_text: str = ""
    cn_text: str = ""
    img_prompt: str = ""
    img_path: str = ""
    en_audio_path: str = ""
    cn_audio_path: str = ""
    en_video_path: str = ""
    cn_video_path: str = ""
    en_duration: float = 0.0
    cn_duration: float = 0.0
    is_valid_en: bool = False
    is_valid_cn: bool = False

class LoggerManager:
    log_file_path = None
    _buffer = []

    @classmethod
    def set_log_file(cls, path: str):
        cls.log_file_path = path
        if cls._buffer:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.writelines(cls._buffer)
                cls._buffer.clear()
            except Exception:
                pass

# 【功能简介】：标准化日志格式刷，带颜色与对齐输出，并在后台自动持久化存入 pipeline_master.log
def log_status(stage: str, msg: str, status: str = "INFO"):
    time_str = datetime.now().strftime('%H:%M:%S')
    date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 纯净文本（写入硬盘文件）
    raw_log = f"[{date_str}] [{stage:<10}] [{status:<5}] {msg}"
    
    # 彩色文本（输出终端显示）
    color_map = {
        "INFO": "\033[94m",     # 蓝色
        "OK": "\033[92m",       # 绿色
        "SUCCESS": "\033[92m",  # 绿色
        "WARN": "\033[93m",     # 黄色
        "ERROR": "\033[91m",    # 红色
        "CRITICAL": "\033[91m", # 红色
        "DEBUG": "\033[90m"     # 灰色
    }
    c_code = color_map.get(status, "\033[0m")
    print(f"{c_code}[{time_str}] [{stage:<10}] [{status:<5}] {msg}\033[0m", flush=True)
    
    # 支持将日志安全引流到业务文件夹中
    if LoggerManager.log_file_path:
        try:
            with open(LoggerManager.log_file_path, "a", encoding="utf-8") as f:
                f.write(raw_log + "\n")
        except Exception:
            pass
    else:
        LoggerManager._buffer.append(raw_log + "\n")

# 【功能简介】：拦截并记录 Tenacity 的自动重试异常事件
def log_retry_attempt(retry_state):
    if retry_state.outcome.failed:
        ex = retry_state.outcome.exception()
        log_status("API_RETRY", f"Attempt {retry_state.attempt_number} failed. Reason: {repr(ex)}. Retrying...", "WARN")

# 【功能简介】：检查核心密钥和依赖路径是否配置健全
def validate_environment() -> bool:
    keys = ["OPENAI_API_KEY", "SILICONFLOW_API_KEY", "GEMINI_API_KEY", "RUNNINGHUB_API_KEY"]
    is_valid = True
    for key in keys:
        if not os.getenv(key):
            log_status("ENV_CHECK", f"Missing environment variable: {key}", "ERROR")
            is_valid = False
            
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except Exception as e:
        log_status("ENV_CHECK", f"FFMPEG not found: {e}", "ERROR")
        is_valid = False

    if is_valid: log_status("ENV_CHECK", "Core environment validated.", "OK")
    return is_valid

# 【功能简介】：创建按时间戳隔离的本次任务专属工作目录
def setup_workspace(folder_path: str) -> str:
    os.makedirs(folder_path, exist_ok=True)
    log_status("ENV", f"Workspace: {folder_path}", "OK")
    return folder_path

# 【功能简介】：剥离大模型回复中的 Markdown 代码块并安全转为字典
def safe_json_loads(text: str) -> dict:
    try:
        text = re.sub(r'```json\n|\n```|```', '', text).strip()
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try: return json.loads(match.group())
            except Exception: pass
        log_status("JSON", "Failed to parse Gemini object.", "ERROR")
        return {}

# 【功能简介】：将中间结果以易读的宽字符版 JSON 形式固化到硬盘
def save_json_formatted(filepath: str, data: any):
    try:
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        log_status("FILE", f"Saved {os.path.basename(filepath)}", "OK")
    except Exception as e:
        log_status("FILE", f"Save failed {filepath}: {e}", "ERROR")

# 【功能简介】：向统计用的 CSV 追加记录本次运行的文案与配置
def record_execution(csv_path: str, app_name: str, start_time: datetime, end_time: datetime, result: str, output_path: str, story_title: str = "Unknown"):
    file_exists = os.path.isfile(csv_path)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    try:
        with open(csv_path, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["app_name", "start_time", "end_time", "result", "output_path", "story_title"])
            writer.writerow([
                app_name,
                start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_time.strftime('%Y-%m-%d %H:%M:%S'),
                result,
                output_path,
                story_title
            ])
        log_status("RECORD", f"Execution logged to {os.path.basename(csv_path)}", "OK")
    except Exception as e:
        log_status("RECORD", f"Failed to write record: {e}", "ERROR")

# =====================================================================
# LLM TEXT CLEANING PIPELINE & SSML INJECTION
# =====================================================================

# 【功能简介】：正则表达式剔除输出里多余的分割线废字符
def remove_pure_symbols(text: str) -> str:
    """
    清理大模型生成的纯符号分割线。
    """
    if not text:
        log_status("CLEAN", "remove_pure_symbols: Empty text received.", "WARN")
        return text
    
    try:
        cleaned_text = re.sub(PATTERN_PURE_SYMBOLS, "", text, flags=re.MULTILINE)
        return cleaned_text
    except Exception as e:
        log_status("CLEAN", f"remove_pure_symbols Exception: {e}", "ERROR")
        return text

# 【功能简介】：清除诸如「这是为您生成的文本」等大模型车轱辘语
def remove_ai_hallucinations(text: str) -> str:
    """
    清理大模型生成的带有语义前缀的标题行 (如 '--- 中文文案 ---')。
    """
    if not text:
        log_status("CLEAN", "remove_ai_hallucinations: Empty text received.", "WARN")
        return text
    
    try:
        cleaned_text = re.sub(PATTERN_AI_PREFIXES, "", text, flags=re.MULTILINE)
        return cleaned_text
    except Exception as e:
        log_status("CLEAN", f"remove_ai_hallucinations Exception: {e}", "ERROR")
        return text

# 【功能简介】：统一整理段落间距防连续排版留白、错乱
def clean_formatting(text: str) -> str:
    """
    清理文本首尾的空白字符以及因删除行而产生的多余空行。
    """
    if not text:
        log_status("CLEAN", "clean_formatting: Empty text received.", "WARN")
        return text
    
    try:
        cleaned_text = re.sub(r'\n{3,}', '\n\n', text)
        cleaned_text = cleaned_text.strip()
        return cleaned_text
    except Exception as e:
        log_status("CLEAN", f"clean_formatting Exception: {e}", "ERROR")
        return text

# 【功能简介】：执行串联的系统级文本净化清洗强力管线
def run_clean_pipeline(raw_text: str) -> str:
    """
    底层核心中枢：按顺序执行清洗流水线。
    """
    if not raw_text:
        log_status("PIPELINE", "run_clean_pipeline: Received empty string, aborting.", "WARN")
        return ""
    
    text = remove_pure_symbols(raw_text)
    text = remove_ai_hallucinations(text)
    final_text = clean_formatting(text)
    return final_text 

# 【新增核心】：TTS 发音停顿时间动态注入格式化器 (SSML)
def apply_ssml_pauses(text: str, duration: str = None) -> str:
    """
    【升级版】：ASMR 物理停顿注射器 (Edge-TTS Bypass)
    核心优化：不仅拉长句末停顿，同时针对句中（逗号、分号）强制切分，营造“慵懒呢喃”的呼吸感。
    """
    log_status("TTS_PAUSE", "Applying ASMR natural punctuation pauses...", "INFO")
    if not text or not text.strip():
        log_status("TTS_PAUSE", "Text is empty, skipping pause injection.", "WARN")
        return text
        
    try:
        # 第一步：处理句中短停顿 (逗号、分号)
        # 替换为：原标点 + 换行 + 单个省略号 + 换行
        # 这会诱导 SoniaNeural 产生大约 0.5~0.8 秒的轻微停顿和换气
        pattern_comma = r'([,;，；])'
        replacement_comma = r'\1 \n \n'
        text_with_breaks = re.sub(pattern_comma, replacement_comma, text)
        
        # 第二步：处理句末长停顿 (句号、问号、感叹号)
        # 替换为：原标点 + 连续双换行 + 独立段落的省略号 + 连续双换行
        # 这是物理割裂 Neural 模型上下文的最强手段，能逼出 1.5~2 秒的极长留白
        pattern_period = r'([.!?。！？])'
        replacement_period = r'\1 \n\n ... \n\n ... \n\n'
        text_with_breaks = re.sub(pattern_period, replacement_period, text_with_breaks)
        
        # 第三步：清理可能产生的极端多余空白符，防止 TTS 引擎报错
        text_with_breaks = re.sub(r' {2,}', ' ', text_with_breaks)
        
        log_status("TTS_PAUSE", "ASMR punctuation pauses injected successfully.", "OK")
        return text_with_breaks.strip()
        
    except Exception as e:
        log_status("TTS_PAUSE", f"Pause injection failed with Exception: {e}", "ERROR")
        return text


# =====================================================================
# MANAGERS & CLIENTS
# =====================================================================

class RunningHubManager:
    """
    【新增功能】：安全生命周期管理器，监控所有在 RunningHub 上发起但未完成的任务。
    采用纯同步 urllib 请求，彻底免疫 Asyncio/HTTPX 在系统退出或中断时的报错崩溃。
    """
    _active_tasks = set()

    @classmethod
    def add_task(cls, task_id: str):
        if task_id:
            cls._active_tasks.add(task_id)

    @classmethod
    def remove_task(cls, task_id: str):
        if task_id in cls._active_tasks:
            cls._active_tasks.remove(task_id)

    @classmethod
    def has_task(cls, task_id: str) -> bool:
        return task_id in cls._active_tasks

    @classmethod
    def cancel_task(cls, task_id: str):
        """同步取消，防止被异步生命周期销毁干扰"""
        if not task_id: return
        cls.remove_task(task_id)
        api_key = RUNNINGHUB_CONFIG.get("KEY")
        if not api_key: return

        url = "https://www.runninghub.ai/task/openapi/cancel"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = json.dumps({"apiKey": api_key, "taskId": task_id}).encode('utf-8')

        try:
            log_status("RH_CANCEL", f"Attempting to kill stuck task {task_id}...", "WARN")
            req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=5.0) as response:
                resp_data = json.loads(response.read().decode('utf-8'))
                if resp_data.get("code") in [0, 200] or resp_data.get("success") is True:
                    log_status("RH_CANCEL", f"Successfully killed task {task_id}.", "SUCCESS")
                else:
                    log_status("RH_CANCEL", f"Failed to kill task {task_id}: {resp_data}", "ERROR")
        except Exception as e:
            log_status("RH_CANCEL", f"Network error while cancelling task {task_id}: {e}", "ERROR")

    @classmethod
    def cancel_all(cls):
        tasks = list(cls._active_tasks)
        if tasks:
            log_status("RH_CLEANUP", f"Cleaning up {len(tasks)} active RunningHub tasks...", "WARN")
            for tid in tasks:
                cls.cancel_task(tid)

# 【新增功能】：同步的紧急退场保险。用于捕获极端的系统崩溃或 os._exit() 退出。
def _emergency_sync_cleanup():
    tasks = list(RunningHubManager._active_tasks)
    if not tasks: return
    api_key = RUNNINGHUB_CONFIG.get("KEY")
    if not api_key: return
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [SYSTEM    ] [WARN ] Emergency Exit: Terminating {len(tasks)} RunningHub tasks...", flush=True)
    url = "https://www.runninghub.ai/task/openapi/cancel"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    
    for tid in tasks:
        try:
            payload = json.dumps({"apiKey": api_key, "taskId": tid}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
            urllib.request.urlopen(req, timeout=5.0)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [RH_CANCEL ] [SUCCESS] Task {tid} killed.")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [RH_CANCEL ] [ERROR] Failed to kill {tid}: {e}")

# 注册至 Python 底层生命周期退出钩子
atexit.register(_emergency_sync_cleanup)


class ConcurrencyManager:
    LLM_SEM = None
    TTS_SEM = None
    IMG_SEM = None
    NVENC_SEM = None

    @classmethod
    # 【功能简介】：在事件循环启动期初始挂载并绑定一切全链路并发量信号锁
    def init_locks(cls):
        cls.LLM_SEM = asyncio.Semaphore(5)
        cls.TTS_SEM = asyncio.Semaphore(4)
        cls.IMG_SEM = asyncio.Semaphore(1)
        cls.NVENC_SEM = asyncio.Semaphore(2)
        log_status("SYSTEM", "Concurrency locks explicitly bound to Event Loop.", "OK")

class APIClients:
    _openai = None
    _deepseek = None
    _gemini = None
    _http = None

    @classmethod
    # 【功能简介】：基于懒加载策略实例化并且缓存全局唯一的 OpenAI 客户端网络资源
    def get_openai(cls):
        if not cls._openai: cls._openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return cls._openai

    @classmethod
    # 【功能简介】：基于单例池懒加载实例化唯一的 DeepSeek 官方客户端
    def get_deepseek(cls):
        if not cls._deepseek: 
            cls._deepseek = AsyncOpenAI(api_key=os.getenv("SILICONFLOW_API_KEY"), base_url="https://api.siliconflow.com/v1")
        return cls._deepseek

    @classmethod
    # 【功能简介】：单例模式加载获取 Google GenAI 官方调用客户端
    def get_gemini(cls):
        if not cls._gemini: cls._gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return cls._gemini

    @classmethod
    # 【功能简介】：复用同一个 httpx 的 AsyncClient 异步连接池实例以加快密集吞吐
    def get_http(cls):
        if not cls._http: cls._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC)
        return cls._http
        
    @classmethod
    # 【功能简介】：安全兜底：在任何意外退出/终结前优雅卸载并销毁网络堆内存通道
    async def close_all(cls):
        RunningHubManager.cancel_all() # 退出前清理未完成任务
        if cls._http: 
            await cls._http.aclose()
            cls._http = None

class APIRateLimiter:
    _locks = {}
    _last_calls = {}

    @classmethod
    # 【功能简介】：令牌桶流控防爆壁垒：控制任何并发瞬间对 API 端造成 DDoS 冲锋拦截
    async def throttle(cls, api_name: str, delay_sec=5.0):
        # 【全图急停探针】：API 发起前如果探到 stop.txt，立刻断链！
        SystemController.check_stop_signal()
        
        if api_name not in cls._locks:
            cls._locks[api_name] = asyncio.Lock()
            cls._last_calls[api_name] = 0.0
        
        async with cls._locks[api_name]:
            now = time.time()
            elapsed = now - cls._last_calls[api_name]
            if elapsed < delay_sec:
                await asyncio.sleep(delay_sec - elapsed)
            cls._last_calls[api_name] = time.time()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# 【功能简介】：统一工业级重试封装：Edge-TTS 接口调用，防偶尔的连接断开或握手失败
async def robust_edge_tts_call(text: str, voice: str, raw_wav: str):
    await edge_tts.Communicate(text, voice, rate="-30%").save(raw_wav)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# 【功能简介】：统一工业级重试封装：RunningHub 出图接口，防获取不到 taskId 或轮询超时
async def robust_image_call(prompt: str, img_path: str, log_tag: str):
    success = await generate_runninghub_image(prompt, img_path, log_tag)
    if not success:
        raise RuntimeError("RunningHub API completely failed to return a successful image.")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# 【功能简介】：工业级 Gemini 请求：附带并发容错、字符截断验证与无限重试
async def robust_gemini_call(prompt: str, max_tokens: int = 2000) -> str:
    """
    双重保险防暴走：
    1. config 设置 max_output_tokens 物理截断。
    2. 字符长度校验熔断拦截。
    """
    await APIRateLimiter.throttle("gemini", 2.0)
    res = await asyncio.to_thread(
        APIClients.get_gemini().models.generate_content, 
        model=MODEL_CONFIG["GEMINI_MODEL"], 
        contents=prompt,
        config=genai.types.GenerateContentConfig(max_output_tokens=max_tokens)
    )
    
    text = res.text
    if text and len(text) > max_tokens * 4: # 粗略按照每个 token 4 个字符校验
        raise RuntimeError(f"Circuit Breaker Tripped: Gemini output wildly exceeded limits ({len(text)} chars).")
        
    return run_clean_pipeline(text)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# 【功能简介】：工业级 OpenAI 请求：采用 parse 强结构化对象强类型解析
async def robust_openai_call(prompt: str, response_format, max_tokens: int = 1500) -> any:
    """
    双重保险防暴走：
    1. API 调用层设置 max_tokens=1500。
    2. 判断预解析后的对象转换成字符串后的词数，异常过长直接抛错重试。
    """
    await APIRateLimiter.throttle("openai", 0.5)
    # 注意：使用 response_format 时返回的是预解析对象，无需清洗
    res = await APIClients.get_openai().beta.chat.completions.parse(
        model=MODEL_CONFIG["OPENAI_MODEL"], 
        messages=[{"role": "user", "content": prompt}], 
        response_format=response_format,
        max_tokens=max_tokens
    )
    
    parsed_data = res.choices[0].message.parsed
    
    # 熔断机制：防大模型进入格式冲突导致的乱码死循环
    if len(str(parsed_data).split()) > 1500:
        raise RuntimeError("Circuit Breaker Tripped: OpenAI structured output word count wildly exceeded safety limits.")
        
    return parsed_data

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# 【功能简介】：工业级 DeepSeek 请求：带中文极限量截断安全退出
async def robust_deepseek_call(prompt: str, max_tokens: int = 1000, clean_output: bool = True) -> str:
    """
    双重保险防暴走：
    1. API 调用层设置 max_tokens=1000 截断。
    2. 判断返回中文字符长度，超出安全边界熔断。
    """
    await APIRateLimiter.throttle("deepseek", 4)
    res = await APIClients.get_deepseek().chat.completions.create(
        model=MODEL_CONFIG["DEEPSEEK_MODEL"], 
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    
    text = res.choices[0].message.content
    
    if text and len(text) > max_tokens * 4:
        raise RuntimeError("Circuit Breaker Tripped: DeepSeek output text length wildly exceeded safety limits.")
        
    return run_clean_pipeline(text) if clean_output else text

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# 【新增功能】：Kimi 备用模型请求接口
async def robust_kimi_call(prompt: str, max_tokens: int = 4000, clean_output: bool = True) -> str:
    """
    Kimi 专用接口，复用 DeepSeek 的客户端因为其遵循 OpenAI 兼容格式。
    """
    await APIRateLimiter.throttle("kimi", 4)
    res = await APIClients.get_deepseek().chat.completions.create(
        model=MODEL_CONFIG.get("KIMI_MODEL", "moonshotai/kimi-k2.5"), 
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    
    text = res.choices[0].message.content
    
    if text and len(text) > max_tokens * 4:
        raise RuntimeError("Circuit Breaker Tripped: Kimi output text length wildly exceeded safety limits.")
        
    return run_clean_pipeline(text) if clean_output else text

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# 【新增功能】：工业级 OSS 小模型专属通道：调用廉价且高速的网络节点进行批量格式化处理
async def robust_oss_call(prompt: str, max_tokens: int = 2000, clean_output: bool = True) -> str:
    """
    调用兼容 DeepSeek API 格式的高性价比模型 (如 gpt-oss-20b)。
    """
    await APIRateLimiter.throttle("oss", 4)
    log_status("OSS_API", f"Calling OSS model {MODEL_CONFIG.get('OSS_MODEL')} for rewrite...", "INFO")
    try:
        # 复用硅基等兼容平台的通讯通道，动态指定 Model 参数
        res = await APIClients.get_deepseek().chat.completions.create(
            model=MODEL_CONFIG.get("OSS_MODEL", "openai/gpt-oss-120b"), 
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens
        )
        
        text = res.choices[0].message.content
        if text and len(text) > max_tokens * 4:
            log_status("OSS_API", f"Output wildly exceeded limits ({len(text)} chars). Tripping Circuit Breaker.", "ERROR")
            raise RuntimeError("Circuit Breaker Tripped: OSS output length wildly exceeded safety limits.")
            
        log_status("OSS_API", "OSS model response successful.", "SUCCESS")
        return run_clean_pipeline(text) if clean_output else text
    except Exception as e:
        log_status("OSS_API", f"OSS model call failed: {repr(e)}", "ERROR")
        raise e

# =====================================================================
# GLOBAL IMAGE GENERATOR & YOUTUBE UPLOAD
# =====================================================================

# 【功能简介】：向云端工作流引擎异步推送提示词并轮询抓取高清生图 URL
async def generate_runninghub_image(prompt: str, img_path: str, log_tag: str = "IMAGE") -> bool:
    if os.path.exists(img_path): return True
    client = APIClients.get_http()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RUNNINGHUB_CONFIG['KEY']}"}
    payload = {"nodeInfoList": [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": prompt}]}
    base_url = "https://www.runninghub.ai/openapi/v2"
    task_id = None
    
    for attempt in range(15):
        try:
            await APIRateLimiter.throttle("runninghub", 5.0)
            resp = await client.post(f"{base_url}/run/workflow/{RUNNINGHUB_CONFIG['WF_T2I']}", headers=headers, json=payload)
            r_json = resp.json()
            if str(r_json.get("errorCode")) == "421": 
                await asyncio.sleep(5)
                continue
            task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
            if task_id: 
                log_status(log_tag, f"Task Created: {task_id}", "OK")
                RunningHubManager.add_task(task_id) # 记录至管理器
                break
        except Exception as e:
            await asyncio.sleep(5)
            
    if not task_id: 
        log_status(log_tag, "Failed to obtain Task ID.", "ERROR")
        return False
    
    # 启用防弹衣：无论由于 Ctrl+C 取消还是报错，都保证清理
    try:
        t0 = time.time()
        while time.time() - t0 < RUNNINGHUB_TIMEOUT_SEC:
            # 【轮询急停探针】：轮询等待生图时，随时检查是否有 stop.txt
            SystemController.check_stop_signal()
            
            try:
                q_resp = await client.post(f"{base_url}/query", headers=headers, json={"taskId": task_id})
                q_json = q_resp.json()
                status = q_json.get("status", "").upper()
                
                if status == "SUCCESS":
                    # 【功能简介】：无脑提取工具：支持正则强制从混杂干扰描述文本中单独摘出 CDN 高清图像网络直链
                    def find_url(d):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if k in ['fileUrl', 'url'] and isinstance(v, str) and v.startswith('http'): return v
                                if (res := find_url(v)): return res
                        elif isinstance(d, list):
                            for i in d:
                                if (res := find_url(i)): return res
                        return ""
                    
                    img_url = find_url(q_json)
                    if img_url:
                        log_status(log_tag, "Downloading Image...", "INFO")
                        img_data = await client.get(img_url)
                        with open(img_path, "wb") as f: f.write(img_data.content)
                        log_status(log_tag, "Image Download Complete.", "SUCCESS")
                        RunningHubManager.remove_task(task_id) # 成功后注销
                        return True
                    else:
                        RunningHubManager.remove_task(task_id) # 失败亦注销
                        return False
                elif status == "FAILED": 
                    log_status(log_tag, f"Task Failed, response: {q_json}", "ERROR")
                    RunningHubManager.remove_task(task_id) # 失败亦注销
                    return False
            except Exception as e: 
                log_status(log_tag, f"Exception during polling: {repr(e)}", "DEBUG")
            await asyncio.sleep(API_POLL_INTERVAL_SEC)
            
        log_status(log_tag, f"Timed out after {RUNNINGHUB_TIMEOUT_SEC}s.", "ERROR")
        RunningHubManager.remove_task(task_id) # 失败亦注销
        return False
    finally:
        # 当协程被外力强行中断（如 Ctrl+C 导致 CancelledError/KeyboardInterrupt）或发生未捕获异常时
        if RunningHubManager.has_task(task_id):
            RunningHubManager.cancel_task(task_id)

# 【功能简介】：获取和缓存经过 OAuth 校验的 YouTube API 谷歌凭证授权
def get_authenticated_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', YOUTUBE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

# 【功能简介】：推送打包好的带标签和封面媒体文件上架部署至 YouTube
def upload_video_to_youtube(file_path: str, title: str, description: str, tags: list):
    log_status("UPLOAD", f"Starting upload for: {title[:20]}...", "INFO")
    try:
        youtube = get_authenticated_service()
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': '27'
            },
            'status': {
                'privacyStatus': 'private',
                'selfDeclaredMadeForKids': False
            }
        }
        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status: log_status("UPLOAD", f"Upload progress: {int(status.progress() * 100)}%", "INFO")
                
        log_status("UPLOAD", f"Upload Complete! Video ID: {response.get('id')}", "SUCCESS")
    except Exception as e:
        log_status("UPLOAD", f"Upload failed: {e}", "ERROR")
