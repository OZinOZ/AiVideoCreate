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
import _thread
import asyncio
import re
import json
import time
import csv
import random
import textwrap
import html
import subprocess
import atexit
import base64 
import io
import posixpath
import shutil
import threading
import urllib.request
import zipfile
import tempfile
import argparse
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Optional, Dict, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageStat

try:
    RESAMPLING_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLING_LANCZOS = getattr(Image, "LANCZOS", Image.ANTIALIAS)

import httpx
from google import genai
from openai import AsyncOpenAI
from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter, HighpassFilter, PeakFilter
from pedalboard.io import AudioFile

try:
    from google.oauth2.credentials import Credentials as _OAuthCredentials
    from google.auth.transport.requests import Request as _GoogleRequest
    from googleapiclient.discovery import build as _gdrive_build
    from googleapiclient.http import MediaIoBaseDownload as _MediaIoBaseDownload
    _GDRIVE_AVAILABLE = True
except ImportError:
    _GDRIVE_AVAILABLE = False
import edge_tts
from tenacity import retry, stop_after_attempt, wait_exponential

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from runtime_config import (
    get_loaded_env_config_file,
    load_channel_runtime_config,
    load_env_config_file as _load_env_config_file_impl,
    parse_dotenv_file as _parse_dotenv_file_impl,
)

# =====================================================================

# =====================================================================
# Automatically load variables from .env file specified by ENV_CONFIG_FILE if os.getenv fails.
# ENV_CONFIG_FILE can be specified by env vars or declared in channel config within app_xxx.py,
# and manually activated via load_env_config_file(path) after load_python_config().

# =====================================================================
# ENV FILE LOADER
# =====================================================================

def load_env_config_file(env_path: str):
    """
    Proactively load the specified .env file into the global cache.
    Variables not found by os.getenv will automatically fallback to this file.
    """
    if not env_path:
        return
    normalized_path = os.path.abspath(env_path)
    if get_loaded_env_config_file() == normalized_path:
        return
    _load_env_config_file_impl(normalized_path)
    print(f"[ENV_LOADER] Activated .env context from: {normalized_path}", flush=True)

# Auto load on startup: prioritize the file pointed to by system env ENV_CONFIG_FILE
if _auto_env_path := os.getenv("ENV_CONFIG_FILE"):
    load_env_config_file(_auto_env_path)

# =====================================================================
# CORE CONFIGURATIONS
# =====================================================================

RUNNINGHUB_TIMEOUT_SEC = 600
API_POLL_INTERVAL_SEC = 10
HTTP_TIMEOUT_SEC = 60.0

MODEL_CONFIG = {
    "GEMINI_MODEL": "gemini-2.5-pro",
    "GEMMA4_MODEL": os.getenv("GEMMA4_MODEL", "gemma-4-e4b-it"),
    "KIMI_MODEL": "moonshotai/kimi-k2.5",
    "OPENAI_MODEL": "gpt-4o-mini",
    "DEEPSEEK_MODEL": "deepseek-ai/DeepSeek-V4-Flash", #"deepseek-ai/DeepSeek-V3.2"
    "OSS_MODEL": "openai/gpt-oss-120b", 
    "AGNES_MODEL": "Agnes-2.0-Flash",
    "VOICE_EN": "en-GB-SoniaNeural",
    "VOICE_CN": "zh-CN-XiaoxiaoNeural", 
    "TTS_VOICERATE": "-30%",
    "USE_AZURE_TTS": True,
    "AZURE_TTS_ENDPOINT": os.getenv("AZURE_TTS_ENDPOINT", "https://australiaeast.api.cognitive.microsoft.com/"),
    "AZURE_TTS_REGION": os.getenv("AZURE_TTS_REGION", "australiaeast"),
    "AZURE_TTS_OUTPUT_FORMAT": os.getenv("AZURE_TTS_OUTPUT_FORMAT", "audio-16khz-32kbitrate-mono-mp3"),
    "AZURE_TTS_VOICE": os.getenv("AZURE_TTS_VOICE", "zh-CN-YunjianNeural"),
    "AZURE_TTS_STYLE": os.getenv("AZURE_TTS_STYLE", "narration-relaxed"),
    "AZURE_TTS_BREAK_MID_MS": os.getenv("AZURE_TTS_BREAK_MID_MS", "300"),
    "AZURE_TTS_BREAK_END_MS": os.getenv("AZURE_TTS_BREAK_END_MS", "1000"),
}


VIDEO_RENDER_CONFIG = {
    "SPLIT_VIDEO_SEGMENT": True,
}

RUNNINGHUB_CONFIG = {
    "KEY": os.getenv("RUNNINGHUB_API_KEY"),
    "WF_T2I": "2014487614874718210",
    "T2I_NODE": "111",
    "WF_ZIMAGE": "2046708015562235905",
    "USE_ZIMAGE": False  
}

# =====================================================================
# WF_ZIMAGE core runtime parameters and workflow node configuration
# =====================================================================
WF_ZIMAGE_NODES = {
    # 1. Core runtime parameters (required to keep the workflow running)
    # These define the physical foundation for every frame generation:
    "PROMPT": "11",         # Core prompt. Qwen's CLIP (Node 5) accepts detailed Chinese descriptions directly — the biggest advantage over Flux.
    "SEED": "6",            # Random seed. Each image must use a different seed in automated scripts, otherwise the video sequence will be completely static.
    "SIZE": "10",           # "width" & "height": 1080x1920 (portrait) for Shorts/TikTok. Change to 1920x1080 for landscape projects.

    # 2. Diversity drivers (must be dynamically adjusted to solve the "same face" problem)
    # To fix the "they all look the same" issue, dynamically tweak the following parameters:
    "LORA_STRENGTH": "7",   # "strength_model" (LoRA strength): recommended random range (0.8 to 1.2). Loads zit_fdpo_v1; tweaking the weight breaks the AI average face.
    "NEGATIVE_PROMPT": "3", # "text" (Negative Prompt): recommended addition: "(average face, generic features, standard look:1.2), (3d render, plastic skin:1.2)".

    # 3. Quality vs. efficiency balance (special settings for Turbo models)
    "STEPS": "8",           # "steps": fixed at 8-12. Sweet spot for Turbo/Flow models; too many steps cause oversaturation or artifacts.
    "CFG": "8",             # "cfg" (classifier-free guidance scale): fixed between 1.0 and 1.5. DPO and Turbo models perform best at CFG=1.
}


PEDALBOARD_CONFIG = {
    "LOW_SHELF_GAIN": 3.0, "HIGH_SHELF_GAIN": 2.0,
    "COMP_THRESHOLD": -20.0, "COMP_RATIO": 2.0, "LIMIT_DB": -3.0
}

YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secret.json'

# LLM text cleaning regex configurations
# Pattern 1: match meaningless symbol dividers (e.g., "----" or "====")
PATTERN_PURE_SYMBOLS = r"^[\s\-\*#=~_]{3,}\s*$"
# Pattern 2: match title lines with common AI prefixes/suffixes, tolerating various wrapper symbols
# e.g., "--- Chinese Script ---", "### Final Output:", "[Translation Result]"
PATTERN_AI_PREFIXES = r"^[\s\-\*#=【\[]*(Chinese|English|Final)?(Script|Output|Text|Translation|Generation|Story|Content|Result)[】\]\s\-\*#=]*[:：]?\s*$"

# =====================================================================
# DATA STRUCTURES & UTILITIES
# =====================================================================

# [Core Feature]: Industrial-grade global emergency stop switch
class SystemController:
    """
    External control probe: creating a stop.txt in the runtime directory
    triggers a precise KeyboardInterrupt, initiating an elegant full-pipeline shutdown.
    """
    STOP_FILE = "stop.txt"

    @classmethod
    def check_stop_signal(cls):
        if os.path.exists(cls.STOP_FILE):
            log_status("SYSTEM", "🛑 External stop signal (stop.txt) detected! Initiating graceful shutdown...", "CRITICAL")
            try:
                os.remove(cls.STOP_FILE) # Consume the file to prevent immediate abort on the next startup
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


LOG_LOCK = threading.Lock()
PROC_LOCK = threading.Lock()
ACTIVE_FFMPEG_PROCS: set[subprocess.Popen] = set()
FFMPEG_TIMEOUT_SECONDS = 300


class LoggerManager:
    log_file_path = None
    _buffer = []

    @classmethod
    def set_log_file(cls, path: str):
        with LOG_LOCK:
            cls.log_file_path = path
            if cls._buffer:
                try:
                    with open(path, "a", encoding="utf-8") as file_obj:
                        file_obj.writelines(cls._buffer)
                    cls._buffer.clear()
                except OSError as exc:
                    print(f"[LOGGER] Failed to flush buffered logs to {path}: {exc}", file=sys.stderr, flush=True)


# [Function]: Standardized logging formatter with color/alignment, persisting to pipeline_master.log
def log_status(stage: str, msg: str, status: str = "INFO"):
    time_str = datetime.now().strftime("%H:%M:%S")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_log = f"[{date_str}] [{stage:<10}] [{status:<5}] {msg}"

    color_map = {
        "INFO": "\033[94m",
        "OK": "\033[92m",
        "SUCCESS": "\033[92m",
        "WARN": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[91m",
        "DEBUG": "\033[90m",
        "START": "\033[96m",
    }
    color_code = color_map.get(status, "\033[0m")
    print(f"{color_code}[{time_str}] [{stage:<10}] [{status:<5}] {msg}\033[0m", flush=True)

    with LOG_LOCK:
        if LoggerManager.log_file_path:
            try:
                with open(LoggerManager.log_file_path, "a", encoding="utf-8") as file_obj:
                    file_obj.write(raw_log + "\n")
            except OSError as exc:
                LoggerManager._buffer.append(raw_log + "\n")
                print(f"[LOGGER] Failed to write log file {LoggerManager.log_file_path}: {exc}", file=sys.stderr, flush=True)
                if "[Errno 2]" in str(exc):
                    print("[SYSTEM] Fatal filesystem error (drive missing?). Terminating...", file=sys.stderr, flush=True)
                    _thread.interrupt_main()
        else:
            LoggerManager._buffer.append(raw_log + "\n")


def _register_active_process(proc: subprocess.Popen):
    with PROC_LOCK:
        ACTIVE_FFMPEG_PROCS.add(proc)


def _unregister_active_process(proc: subprocess.Popen):
    with PROC_LOCK:
        ACTIVE_FFMPEG_PROCS.discard(proc)


def _terminate_process(proc: subprocess.Popen, stage: str = "FFMPEG"):
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        log_status(stage, f"Terminated stuck subprocess PID={proc.pid}.", "WARN")
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=5)
            log_status(stage, f"Killed stuck subprocess PID={proc.pid} after terminate timeout.", "WARN")
        except Exception as exc:
            log_status(stage, f"Failed to kill subprocess PID={proc.pid}: {exc}", "ERROR")
    except Exception as exc:
        log_status(stage, f"Failed to terminate subprocess PID={proc.pid}: {exc}", "ERROR")


def safe_subprocess_run(cmd, timeout: int = FFMPEG_TIMEOUT_SECONDS, stage: str = "FFMPEG"):
    """Run a subprocess with timeout and automatic process tracking.
    Registers the process in ACTIVE_FFMPEG_PROCS so it can be force-killed on shutdown.
    Raises CalledProcessError on non-zero exit, or TimeoutExpired if the timeout is exceeded.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _register_active_process(proc)
    try:
        out, err = proc.communicate(timeout=timeout)
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
        return out, err
    except subprocess.TimeoutExpired as exc:
        log_status(stage, f"Subprocess timed out after {timeout}s: {' '.join(cmd)}", "ERROR")
        _terminate_process(proc, stage=stage)
        raise exc
    except Exception as exc:
        if not isinstance(exc, subprocess.CalledProcessError):
            log_status(stage, f"Subprocess execution failed: {exc}", "ERROR")
            _terminate_process(proc, stage=stage)
        raise
    finally:
        _unregister_active_process(proc)





def inspect_tts_safety(task_id: str, text: str) -> Tuple[bool, str]:
    """
    TTS safety inspection helper.
    Strictly blocks text that may cause Azure TTS to sound broken, clipped, or unnatural.
    Returns: (passed, detailed_reason)
    """
    del task_id  # Retained for compatibility with existing call sites.
    if not text or not text.strip():
        return False, "Text is empty"

    error_reasons = []

    if re.search(r"[a-z]", text):
        error_reasons.append("Contains lowercase English letters")

    if re.search(r"([\uFF0C\u3002\uFF1F\uFF01\uFF1B\uFF1A])\1{1,}", text):
        error_reasons.append("Contains repeated punctuation")

    if re.search(r"[@#$%^&*<>{}\[\]\\]", text):
        error_reasons.append("Contains special math/network symbols")

    if re.search(r"[0-9]", text):
        error_reasons.append("Contains Arabic numerals (consider rewriting them in Chinese words for smoother TTS)")

    if error_reasons:
        return False, " | ".join(error_reasons)

    return True, "PASS"


def master_audio_sync(raw_wav: str, mastered_wav: str) -> float:
    """Apply a professional audio mastering chain (EQ, compression, limiting, LUFS normalization)
    to a raw TTS WAV file and write the result to mastered_wav.
    Returns the duration of the mastered file in seconds, or 0.0 on failure.
    """
    try:
        # 1. Determine parameters based on TTS provider        
        is_azure = MODEL_CONFIG.get("USE_AZURE_TTS", False)
        peak_150_gain = 2.5 if is_azure else -2.0
        peak_250_gain = -1.5 if is_azure else -3.0
        peak_2800_gain = 1.2 if is_azure else 2.0
        peak_4500_gain = 1.5 if is_azure else 1.5
        compressor_ratio = 4.0 if is_azure else 3.0
        lufs_val = "loudnorm=I=-14:LRA=7:TP=-1.0" if is_azure else "loudnorm=I=-19:LRA=7:TP=-2.0"

        # 2. Read audio samples.
        with AudioFile(raw_wav) as file_obj:
            audio_data = file_obj.read(file_obj.frames)
            samplerate = file_obj.samplerate

        board = Pedalboard([
            # --- Basic cleanup ---
            HighpassFilter(cutoff_frequency_hz=80),

            # --- Low-frequency body: fuller without becoming muddy ---
            PeakFilter(cutoff_frequency_hz=150, gain_db=peak_150_gain, q=1.0),
            PeakFilter(cutoff_frequency_hz=250, gain_db=peak_250_gain, q=1.2),            

            # --- Remove boxiness ---
            PeakFilter(cutoff_frequency_hz=400, gain_db=-2.0, q=1.5),

            # --- Presence: critical for intimate narration ---
            PeakFilter(cutoff_frequency_hz=2800, gain_db=peak_2800_gain, q=1.0),
            # --- Clarity ---
            PeakFilter(cutoff_frequency_hz=4500, gain_db=peak_4500_gain, q=1.0),
            
            # --- Simple de-esser to control harsh sibilance ---
            PeakFilter(cutoff_frequency_hz=7000, gain_db=-2.0, q=2.0),

            # --- Controlled compression: the core glue stage ---
            Compressor(
                threshold_db=-20.0,
                ratio=compressor_ratio,
                attack_ms=3.0,
                release_ms=120.0
            ),

            # --- Makeup gain ---
            Gain(gain_db=1.2),

            # --- Final limiter ---
            Limiter(threshold_db=-1.0),
        ])

        processed_data = board(audio_data, samplerate)

        # 4. Write a temporary file for LUFS normalization.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            temp_wav = tmp_file.name

        with AudioFile(temp_wav, "w", samplerate, processed_data.shape[0]) as f:
            f.write(processed_data)

        # 5. LUFS normalization to keep overall loudness consistent.
        lufs = lufs_val

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", temp_wav,
            "-af", lufs,
            mastered_wav
        ]
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Clean up the temporary WAV file.
        os.remove(temp_wav)

        return len(AudioSegment.from_file(mastered_wav)) / 1000.0

    except Exception as exc:
        log_status("AUDIO", f"Mastering failed: {exc}", "ERROR")
        return 0.0


def _check_file_exists(file_path: str, file_type: str) -> bool:
    """Check if a file exists and log the result."""
    if not os.path.exists(file_path):
        print(f"[ERROR] {file_type} not found: {file_path}")
        return False
    return True


def _format_windows_font_path(path: str) -> str:
    """Format Windows font paths to prevent FFmpeg syntax escaping errors."""
    if not path:
        print("[ERROR] Font path is empty.")
        return ""
    return path.replace("\\", "/").replace(":", r"\:")


def _escape_drawtext(text: str) -> str:
    """Escape text content to prevent FFmpeg syntax errors."""
    if not text:
        print("[WARNING] Text content is empty.")
        return ""
    safe_text = text.replace("\n", "").replace("\r", "").replace("\t", " ")
    return safe_text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")

INTRO_CONFIG: Dict[str, Any] = {
    "duration": 3.0,
    "fps": 30,
    "zoom_max": 1.10,
    "blur_sigma": 15,
    "resolution": "1920:1080",
    "video_codec": "libx264",
    "preset": "fast",
    "crf": "18",
    "pixel_format": "yuv420p",
    "default_font_path": "C:/Windows/Fonts/msyhbd.ttc"
}

def _build_blurred_title_filtergraph(font_path: str, main_text: str, sub_text: str) -> str:
    """
    Constructs the FFmpeg filtergraph string with 4K supersampling, 
    dynamic blur fade-in, and precise text alpha keyframing.
    """
    log_status("BUILDER", "Constructing 4K supersampled visual filtergraph...", "INFO")
    
    duration = INTRO_CONFIG["duration"]
    fps = INTRO_CONFIG["fps"]
    total_frames = int(duration * fps)
    w_out, h_out = INTRO_CONFIG["resolution"].split(':')
    
    w_int, h_int = 3840, 2160
    
    z_expr = f"1.0+({INTRO_CONFIG['zoom_max']}-1.0)*(time/{duration})"
    base_chain = (
        f"scale={w_int}:{h_int}:force_original_aspect_ratio=increase,crop={w_int}:{h_int},"
        f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:s={w_int}x{h_int}:fps={fps},"
        f"scale={w_out}:{h_out}:flags=lanczos[zoomed]"
    )

    blur_sigma = INTRO_CONFIG["blur_sigma"]
    blur_chain = (
        "[zoomed]split=2[sharp][to_blur];"
        f"[to_blur]gblur=sigma={blur_sigma},format=yuva420p,"
        "fade=t=in:st=2.0:d=1.0:alpha=1[blur_layer];"
        "[sharp][blur_layer]overlay=x=0:y=0[bg_blurred]"
    )

    alpha_expr = r"if(lt(t\,0.5)\,0\,if(lt(t\,1.0)\,(t-0.5)/0.5\,if(lt(t\,2.0)\,1\,max(0\,1-(t-2.0)/0.5))))"
    
    spaced_main = " ".join(list(main_text))
    spaced_sub = " ".join(list(sub_text))

    text_main = (
        f"[bg_blurred]drawtext=fontfile='{font_path}':text='{spaced_main}':"
        "fontcolor=white:fontsize=90:"
        "x=(w-text_w)/2:y=(h-text_h)/2-60:"
        "shadowcolor=black@0.6:shadowx=3:shadowy=3:"
        f"alpha='{alpha_expr}'[t1]"
    )

    text_sub = (
        f"[t1]drawtext=fontfile='{font_path}':text='{spaced_sub}':"
        "fontcolor=gray:fontsize=45:"
        "x=(w-text_w)/2:y=(h-text_h)/2+60:"
        "shadowcolor=black@0.6:shadowx=2:shadowy=2:"
        f"alpha='{alpha_expr}'"
    )

    return f"{base_chain};{blur_chain};{text_main};{text_sub}"

def _execute_ffmpeg_render(source_img: str, output_video: str, vf_string: str) -> bool:
    """Executes FFmpeg to render a pure, silent video stream (-an flag)."""
    log_status("RENDER", "Assembling FFmpeg video-only payload...", "INFO")
    
    ffmpeg_cmd: List[str] = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", source_img,
        "-filter_complex", vf_string,
        "-map", "0:v",
        "-c:v", INTRO_CONFIG["video_codec"],
        "-preset", INTRO_CONFIG["preset"],
        "-crf", INTRO_CONFIG["crf"],
        "-pix_fmt", INTRO_CONFIG["pixel_format"],
        "-t", str(INTRO_CONFIG["duration"]),
        "-an",  # Absolute silence: forcibly strip/discard any audio stream that may be generated
        output_video
    ]

    try:
        log_status("RENDER", "Executing FFmpeg engine...", "INFO")
        result = subprocess.run(
            ffmpeg_cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.PIPE, 
            text=True, 
            encoding='utf-8', 
            errors='replace',
            check=False
        )
        
        if result.returncode != 0:
            log_status("RENDER", f"FFmpeg Render Failed (Code {result.returncode})", "ERROR")
            log_status("RENDER", f"Trace: {result.stderr}", "ERROR")
            return False
            
        log_status("RENDER", f"Silent Intro successfully rendered: {output_video}", "OK")
        return True
    except Exception as exc:
        log_status("RENDER", f"Subprocess exception during render: {exc}", "ERROR")
        return False

def generate_blurred_title_video(
    source_img: str,
    output_video: str,
    main_text: str,
    sub_text: str,
    font_path: str = INTRO_CONFIG["default_font_path"],
) -> bool:
    """Render a cinematic 3-second blurred title silent video."""
    log_status("PIPELINE", "Initiating silent intro generation sequence...", "INFO")
    
    if not _check_file_exists(source_img, "Source Image"):
        return False

    safe_font_path = _format_windows_font_path(font_path)
    if not safe_font_path:
        log_status("PIPELINE", "Font path formatting failed.", "ERROR")
        return False

    safe_main_text = _escape_drawtext(main_text)
    safe_sub_text = _escape_drawtext(sub_text)

    vf_string = _build_blurred_title_filtergraph(safe_font_path, safe_main_text, safe_sub_text)
    if not vf_string:
        log_status("PIPELINE", "Filtergraph construction failed.", "ERROR")
        return False

    success = _execute_ffmpeg_render(source_img, output_video, vf_string)
    if success:
        log_status("PIPELINE", "Intro generation COMPLETED SUCCESSFULLY.", "OK")
    else:
        log_status("PIPELINE", "Intro generation FAILED at render stage.", "ERROR")
    return success


def detect_nvenc() -> bool:
    """
    Detect NVENC by asking ffmpeg to actually encode a one-frame black video with h264_nvenc.
    This is more reliable than only checking the encoder list because it catches driver/runtime failures.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1",
                "-vframes", "1",
                "-c:v", "h264_nvenc",
                "-f", "null", "-",
            ],
            capture_output=True,
            timeout=15,
        )
        available = result.returncode == 0
        if available:
            log_status("ENV_CHECK", "NVENC detected: GPU encoding available.", "OK")
        else:
            log_status("ENV_CHECK", "NVENC not available: will skip watermark and use CPU copy.", "WARN")
        return available
    except Exception as exc:
        log_status("ENV_CHECK", f"NVENC detection failed ({exc}): assuming no GPU.", "WARN")
        return False


async def stop_file_watcher():
    """Async background task that polls for a stop.txt file every second.
    When detected, removes the file and raises KeyboardInterrupt on the main thread
    to trigger a graceful pipeline shutdown.
    """
    while True:
        if os.path.exists("stop.txt"):
            log_status("SYSTEM", "Detected stop.txt. Triggering graceful shutdown...", "CRITICAL")
            try:
                os.remove("stop.txt")
            except OSError as exc:
                log_status("SYSTEM", f"Failed to remove stop.txt: {exc}", "WARN")
            _thread.interrupt_main()
            break
        await asyncio.sleep(1)


def wrap_chinese_text(text: str, max_len: int = 12) -> str:
    """Wrap Chinese text into lines of at most max_len characters, breaking at sentence punctuation."""
    lines = []
    current = ""
    sentence_breaks = {",", ".", "!", "?", ";", "\uff0c", "\u3002", "\uff01", "\uff1f", "\uff1b"}
    for char in text:
        current += char
        if len(current) >= max_len or char in sentence_breaks:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return "\n".join(lines)


def get_best_font_size(draw, text, font_path, img_w, img_h, max_font_percentage=0.18, align="right"):
    """Find the largest font size that fits the text within safe width/height bounds for the given alignment."""
    start_size = int(img_h * max_font_percentage)
    min_size = int(img_h * 0.05)
    if start_size <= min_size:
        start_size = min_size + 2

    for size in range(start_size, min_size, -2):
        try:
            font = ImageFont.truetype(font_path, size)
        except IOError:
            return ImageFont.load_default()

        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        else:
            text_w, text_h = draw.textsize(text, font=font)

        max_width_ratio = 0.5 if align in ["left", "right"] else 0.8
        if text_w < img_w * max_width_ratio and text_h < img_h * 0.7:
            return font

    try:
        return ImageFont.truetype(font_path, int(img_h * 0.05))
    except IOError:
        return ImageFont.load_default()


def add_text_to_thumbnail(image_path: str, output_path: str, full_title: str, align: str = "right", font_path: str = "msyhbd.ttc"):
    """Overlay a title text onto a thumbnail image with adaptive font sizing, shadow, and contrast-aware color.
    Resizes the output to 1280x720 and saves it to output_path. Returns True on success.
    """
    try:
        title_text = str(full_title or "").strip()
        short_title = re.split(r"[:\uff1a]", title_text, maxsplit=1)[0].strip() or title_text
        img = Image.open(image_path)
        img_rgb = img.convert("RGB") if img.mode != "RGB" else img
        draw = ImageDraw.Draw(img_rgb)
        img_w, img_h = img_rgb.size

        is_cn = any("\u4e00" <= c <= "\u9fff" for c in short_title)
        max_font_percentage = 0.18
        if is_cn:
            wrapped_text = wrap_chinese_text(short_title)
        else:
            wrapped_text = textwrap.fill(short_title, width=15)
            num_lines = len(wrapped_text.split("\n"))
            base_max_percentage = 0.15 if align == "top" else 0.18
            if num_lines >= 4:
                max_font_percentage = 0.08
            elif num_lines == 3:
                max_font_percentage = 0.12
            else:
                max_font_percentage = base_max_percentage

        font = get_best_font_size(draw, wrapped_text, font_path, img_w, img_h, max_font_percentage=max_font_percentage, align=align)
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), wrapped_text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        else:
            text_w, text_h = draw.textsize(wrapped_text, font=font)

        margin_x = int(img_w * 0.08)
        margin_y = int(img_h * 0.10)
        if align == "left":
            x = margin_x
            y = int((img_h - text_h) / 2)
        elif align == "top":
            x = int((img_w - text_w) / 2)
            y = margin_y
        else:
            x = img_w - text_w - margin_x
            y = int((img_h - text_h) / 2)

        text_region_box = (max(0, x - 10), max(0, y - 10), min(img_w, x + text_w + 10), min(img_h, y + text_h + 10))
        cropped_region = img_rgb.crop(text_region_box)
        stat = ImageStat.Stat(cropped_region)
        avg_r, avg_g, avg_b = stat.mean
        luminance = 0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b

        if luminance > 128:
            text_color = "#857204"
            shadow_fill = (255, 255, 255, 200)
        else:
            text_color = "#FFE24A"
            shadow_fill = (0, 0, 0, 255)

        shadow_offset = 2 if getattr(font, "size", 32) < 60 else 3
        for dx in range(-shadow_offset, shadow_offset + 1):
            for dy in range(-shadow_offset, shadow_offset + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), wrapped_text, font=font, fill=shadow_fill)

        draw.text((x, y), wrapped_text, font=font, fill=text_color)
        img_rgb = img_rgb.resize((1280, 720), RESAMPLING_LANCZOS)
        img_rgb.save(output_path)
        log_status("SEO_THUMB", f"Thumbnail saved: {output_path}", "OK")
        return True
    except Exception as exc:
        log_status("SEO_THUMB", f"Failed to add text to thumbnail: {exc}", "ERROR")
        return False


# [Function]: Intercept and log Tenacity auto-retry exception events
def log_retry_attempt(retry_state):
    """Log a warning when a Tenacity retry attempt fails, showing the attempt number and exception."""
    if retry_state.outcome.failed:
        ex = retry_state.outcome.exception()
        log_status("API_RETRY", f"Attempt {retry_state.attempt_number} failed. Reason: {repr(ex)}. Retrying...", "WARN")

# [Function]: Create a timestamp-isolated dedicated workspace directory for this task
def setup_workspace(folder_path: str) -> str:
    """Create the workspace directory at folder_path if it does not exist and return the path."""
    os.makedirs(folder_path, exist_ok=True)
    log_status("ENV", f"Workspace: {folder_path}", "OK")
    return folder_path


def _join_github_path(*parts: str) -> str:
    """Join repository paths using POSIX separators."""
    normalized_parts = []
    for part in parts:
        if not part:
            continue
        normalized = str(part).replace("\\", "/").strip("/")
        if normalized:
            normalized_parts.append(normalized)
    return posixpath.join(*normalized_parts) if normalized_parts else ""


class GitHubSyncManager:
    """Manage GitHub workspace creation and JSON file synchronization."""

    _lock = threading.Lock()
    _enabled = False
    _workspace_root = ""
    _remote_project_dir = ""
    _config: dict[str, Any] = {}

    @classmethod
    def disable(cls):
        """Disable synchronization for the current process."""
        with cls._lock:
            cls._enabled = False
            cls._workspace_root = ""
            cls._remote_project_dir = ""
            cls._config = {}

    @classmethod
    def configure_for_workspace(cls, cfg: Any, folder_path: str):
        """Bind a local workspace folder to a remote GitHub directory."""
        if not getattr(cfg, "USE_GIT_HUB_INTERFACE", False):
            cls.disable()
            return

        github_cfg = dict(getattr(cfg, "GITHUB_INTERFACE_CONFIG", {}) or {})
        token = github_cfg.get("TOKEN") or os.getenv("GITHUB_TOKEN", "")
        repo_owner = github_cfg.get("REPO_OWNER", "")
        repo_name = github_cfg.get("REPO_NAME", "")

        if not token or not repo_owner or not repo_name:
            log_status("GITHUB", "GitHub sync disabled: missing TOKEN, REPO_OWNER or REPO_NAME.", "WARN")
            cls.disable()
            return

        workspace_root = os.path.abspath(folder_path)
        project_root = github_cfg.get("PROJECTS_ROOT", "")
        remote_project_dir = _join_github_path(project_root, os.path.basename(workspace_root))
        github_cfg["TOKEN"] = token

        with cls._lock:
            cls._enabled = True
            cls._workspace_root = workspace_root
            cls._remote_project_dir = remote_project_dir
            cls._config = github_cfg

        if cls._ensure_remote_workspace():
            log_status("GITHUB", f"Remote workspace ready: {remote_project_dir}", "OK")

    @classmethod
    def _headers(cls) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {cls._config['TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @classmethod
    def _contents_url(cls, remote_path: str) -> str:
        repo_owner = cls._config["REPO_OWNER"]
        repo_name = cls._config["REPO_NAME"]
        return f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{remote_path}"

    @classmethod
    def _request(
        cls,
        method: str,
        url: str,
        expected_statuses: Optional[set[int]] = None,
        **kwargs,
    ) -> Optional[httpx.Response]:
        timeout = kwargs.pop("timeout", HTTP_TIMEOUT_SEC)
        for attempt in range(3):
            try:
                response = httpx.request(method, url, timeout=timeout, **kwargs)
                if expected_statuses and response.status_code in expected_statuses:
                    return response
                if not expected_statuses and response.status_code < 500:
                    return response
                log_status(
                    "GITHUB",
                    f"GitHub API returned {response.status_code} on attempt {attempt + 1}: {response.text[:200]}",
                    "WARN",
                )
            except httpx.HTTPError as exc:
                log_status("GITHUB", f"GitHub API request failed on attempt {attempt + 1}: {exc}", "WARN")
            time.sleep(2)
        return None

    @classmethod
    def _get_file_sha(cls, remote_path: str) -> Optional[str]:
        response = cls._request(
            "GET",
            cls._contents_url(remote_path),
            expected_statuses={200, 404},
            headers=cls._headers(),
            params={"ref": cls._config.get("BRANCH", "main")},
        )
        if response is None or response.status_code == 404:
            return None
        try:
            return response.json().get("sha")
        except ValueError:
            return None

    @classmethod
    def _commit_text_file(cls, remote_path: str, content: str, message: str) -> bool:
        with cls._lock:
            if not cls._enabled:
                return False
            cfg = dict(cls._config)

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {cfg['TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        repo_owner = cfg["REPO_OWNER"]
        repo_name = cfg["REPO_NAME"]
        branch = cfg.get("BRANCH", "main")
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{remote_path}"

        sha_response = cls._request(
            "GET",
            url,
            expected_statuses={200, 404},
            headers=headers,
            params={"ref": branch},
        )
        sha = None
        if sha_response is not None and sha_response.status_code == 200:
            try:
                sha = sha_response.json().get("sha")
            except ValueError:
                sha = None

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        response = cls._request(
            "PUT",
            url,
            expected_statuses={200, 201},
            headers=headers,
            json=payload,
        )
        return response is not None and response.status_code in {200, 201}

    @classmethod
    def _ensure_remote_workspace(cls) -> bool:
        if not cls._enabled or not cls._remote_project_dir:
            return False
        marker_path = _join_github_path(cls._remote_project_dir, ".gitkeep")
        commit_message = f"Create workspace {os.path.basename(cls._workspace_root)}"
        return cls._commit_text_file(marker_path, "", commit_message)

    @classmethod
    def sync_json_file(cls, filepath: str):
        """Commit a JSON file into the bound GitHub workspace directory."""
        if not cls._enabled:
            return

        abs_path = os.path.abspath(filepath)
        if not abs_path.lower().endswith(".json") or not os.path.isfile(abs_path):
            return

        try:
            common_root = os.path.commonpath([abs_path, cls._workspace_root])
        except ValueError:
            return
        if common_root != cls._workspace_root:
            return

        rel_path = os.path.relpath(abs_path, cls._workspace_root).replace("\\", "/")
        remote_path = _join_github_path(cls._remote_project_dir, rel_path)

        try:
            with open(abs_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read()
        except OSError as exc:
            log_status("GITHUB", f"Failed to read JSON before sync: {exc}", "WARN")
            return

        if cls._commit_text_file(remote_path, content, f"Sync JSON {rel_path}"):
            log_status("GITHUB", f"Committed JSON to GitHub: {rel_path}", "OK")
        else:
            log_status("GITHUB", f"Failed to commit JSON to GitHub: {rel_path}", "WARN")

    @classmethod
    def cleanup_workspace(cls) -> bool:
        """Delete all files in the remote workspace directory on GitHub."""
        if not cls._enabled or not cls._remote_project_dir:
            return False

        with cls._lock:
            if not cls._enabled:
                return False
            cfg = dict(cls._config)

        headers = cls._headers()
        repo_owner = cfg["REPO_OWNER"]
        repo_name = cfg["REPO_NAME"]
        branch = cfg.get("BRANCH", "main")
        
        try:
            # Retrieve all files in the remote directory
            url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{cls._remote_project_dir}"
            response = cls._request(
                "GET",
                url,
                expected_statuses={200, 404},
                headers=headers,
                params={"ref": branch},
            )
            
            if response is None or response.status_code == 404:
                log_status("GITHUB", f"Remote workspace not found or already empty: {cls._remote_project_dir}", "INFO")
                return True
            
            if response.status_code != 200:
                log_status("GITHUB", f"Failed to list remote workspace contents: {response.status_code}", "WARN")
                return False
            
            try:
                contents = response.json()
                if not isinstance(contents, list):
                    contents = [contents]
            except (ValueError, KeyError):
                log_status("GITHUB", "Failed to parse remote workspace contents.", "WARN")
                return False
            
            # Delete each file
            deleted_count = 0
            for item in contents:
                if item.get("type") == "file":
                    file_path = item.get("path", "")
                    file_sha = item.get("sha", "")
                    if file_path and file_sha:
                        delete_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
                        delete_payload = {
                            "message": f"Clean up workspace {os.path.basename(cls._workspace_root)}",
                            "sha": file_sha,
                            "branch": branch,
                        }
                        
                        delete_response = cls._request(
                            "DELETE",
                            delete_url,
                            expected_statuses={200, 404},
                            headers=headers,
                            json=delete_payload,
                        )
                        
                        if delete_response and delete_response.status_code in {200, 204}:
                            deleted_count += 1
                        else:
                            log_status("GITHUB", f"Failed to delete remote file: {file_path}", "WARN")
            
            log_status("GITHUB", f"Cleaned up remote workspace: deleted {deleted_count} file(s).", "OK")
            return True
        except Exception as exc:
            log_status("GITHUB", f"Workspace cleanup failed: {exc}", "WARN")
            return False

    @classmethod
    def cleanup_workflow_runs(cls) -> bool:
        """Delete all GitHub workflow runs in the repository."""
        if not cls._enabled:
            return False

        with cls._lock:
            if not cls._enabled:
                return False
            cfg = dict(cls._config)

        headers = cls._headers()
        repo_owner = cfg["REPO_OWNER"]
        repo_name = cfg["REPO_NAME"]

        try:
            # List all workflow runs
            runs_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs"
            page = 1
            per_page = 100
            all_runs = []

            while True:
                response = cls._request(
                    "GET",
                    runs_url,
                    expected_statuses={200},
                    headers=headers,
                    params={"per_page": per_page, "page": page},
                )
                if response is None or response.status_code != 200:
                    log_status("GITHUB", f"Failed to list workflow runs on page {page}.", "WARN")
                    break

                payload = response.json()
                runs = payload.get("workflow_runs", [])
                if not runs:
                    break

                all_runs.extend(runs)

                if len(runs) < per_page:
                    break
                page += 1

            total = len(all_runs)
            if total == 0:
                log_status("GITHUB", "No workflow runs found to clean up.", "INFO")
                return True

            log_status("GITHUB", f"Found {total} workflow run(s) to clean up.", "INFO")

            # Delete each run
            deleted = 0
            failed = 0
            for run in all_runs:
                run_id = run.get("id")
                if not run_id:
                    continue

                delete_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
                delete_response = cls._request(
                    "DELETE",
                    delete_url,
                    expected_statuses={204},
                    headers=headers,
                )

                if delete_response and delete_response.status_code == 204:
                    deleted += 1
                    log_status("GITHUB", f"Deleted workflow run {run_id}.", "OK")
                else:
                    failed += 1
                    log_status("GITHUB", f"Failed to delete workflow run {run_id}.", "WARN")

                time.sleep(0.3)  # Rate limiting

            log_status(
                "GITHUB",
                f"Workflow runs cleanup complete. success={deleted}, failed={failed}, total={total}.",
                "OK" if failed == 0 else "WARN",
            )
            return failed == 0
        except Exception as exc:
            log_status("GITHUB", f"Workflow runs cleanup failed: {exc}", "WARN")
            return False

# [Function]: Strip Markdown code blocks from LLM output and safely convert to dictionary
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

# [Function]: Persist intermediate results to disk as readable JSON
def save_json_formatted(filepath: str, data: any):
    try:
        with open(filepath, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        log_status("FILE", f"Saved {os.path.basename(filepath)}", "OK")
        GitHubSyncManager.sync_json_file(filepath)
    except Exception as e:
        log_status("FILE", f"Save failed {filepath}: {e}", "ERROR")




def _github_upload_image_dynamic(file_path: str, task_id: str, imgbb_api_key: str) -> Optional[str]:
    """Upload an image so a GitHub workflow can fetch it remotely."""
    if not os.path.exists(file_path):
        log_status("GITHUB", f"[{task_id}] Source image missing: {file_path}", "CRITICAL")
        _thread.interrupt_main()
        return None

    if imgbb_api_key:
        try:
            with open(file_path, "rb") as file_obj:
                response = GitHubSyncManager._request(
                    "POST",
                    "https://api.imgbb.com/1/upload",
                    data={"key": imgbb_api_key},
                    files={"image": file_obj},
                    expected_statuses={200},
                )
            if response is not None and response.status_code == 200:
                image_url = response.json().get("data", {}).get("url")
                if image_url:
                    log_status("GITHUB", f"[{task_id}] Uploaded image via ImgBB.", "OK")
                    return image_url
        except OSError as exc:
            log_status("GITHUB", f"[{task_id}] ImgBB upload failed to read file: {exc}", "WARN")

    try:
        with open(file_path, "rb") as file_obj:
            response = GitHubSyncManager._request(
                "POST",
                "https://tmpfiles.org/api/v1/upload",
                files={"file": file_obj},
                expected_statuses={200},
            )
        if response is not None and response.status_code == 200:
            image_url = response.json().get("data", {}).get("url", "")
            if image_url:
                image_url = image_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                log_status("GITHUB", f"[{task_id}] Uploaded image via TmpFiles.", "OK")
                return image_url
    except OSError as exc:
        log_status("GITHUB", f"[{task_id}] TmpFiles upload failed to read file: {exc}", "WARN")

    log_status("GITHUB", f"[{task_id}] Failed to upload source image for GitHub rendering.", "CRITICAL")
    _thread.interrupt_main()
    return None


def _github_extract_rendered_video(zip_bytes: bytes, clip_path: str, task_id: str) -> bool:
    """Extract the first rendered video file from a downloaded artifact ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_ref:
            members = [info for info in zip_ref.infolist() if not info.is_dir()]
            video_members = [
                info for info in members
                if os.path.splitext(info.filename)[1].lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}
            ]
            target_info = video_members[0] if video_members else (members[0] if len(members) == 1 else None)
            if target_info is None:
                log_status("GITHUB", f"[{task_id}] Artifact ZIP does not contain a unique video file.", "ERROR")
                return False

            os.makedirs(os.path.dirname(clip_path), exist_ok=True)
            with zip_ref.open(target_info) as source_obj, open(clip_path, "wb") as target_obj:
                shutil.copyfileobj(source_obj, target_obj)
        log_status("GITHUB", f"[{task_id}] Downloaded rendered video to {clip_path}", "SUCCESS")
        return True
    except (zipfile.BadZipFile, OSError) as exc:
        log_status("GITHUB", f"[{task_id}] Failed to extract artifact ZIP: {exc}", "ERROR")
        return False


def _gdrive_authenticate(client_id: str, client_secret: str, refresh_token: str):
    """Authenticate with Google Drive API using an OAuth Refresh Token.

    Args:
        client_id:     OAuth 2.0 Client ID  (GCP_CLIENT_ID)
        client_secret: OAuth 2.0 Client Secret (GCP_CLIENT_SECRET)
        refresh_token: Long-lived refresh token (GCP_REFRESH_TOKEN)
    Returns:
        A Drive API service object, or None on failure.
    """
    if not _GDRIVE_AVAILABLE:
        log_status("GDRIVE", "google-api-python-client / google-auth not installed.", "ERROR")
        return None
    if not refresh_token:
        log_status("GDRIVE", "GCP_REFRESH_TOKEN is empty — cannot authenticate.", "ERROR")
        return None
    try:
        creds = _OAuthCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        # Force-refresh once to validate the token and obtain an access token
        creds.refresh(_GoogleRequest())
        service = _gdrive_build("drive", "v3", credentials=creds)
        log_status("GDRIVE", "Google Drive OAuth authentication successful.", "OK")
        return service
    except Exception as exc:
        log_status("GDRIVE", f"Google Drive authentication failed: {exc}", "ERROR")
        return None


def _gdrive_poll_and_download(
    service,
    root_folder_id: str,
    task_id: str,
    file_name: str,
    clip_path: str,
    poll_interval: int,
    max_wait: int,
) -> bool:
    """Poll a GDrive subfolder for the rendered video and download it.

    The workflow uploads to: <root_folder_id>/<task_id>/<file_name>.
    This function first waits for the subfolder to appear, then waits for
    the video file, downloads it to clip_path, and returns True on success.
    """
    start_time = time.time()
    subfolder_id = None

    # Phase 1 – wait for task subfolder to be created by the workflow
    while time.time() - start_time <= max_wait:
        if os.path.exists("stop.txt"):
            log_status("GDRIVE", f"[{task_id}] Stop signal detected, aborting GDrive poll.", "WARN")
            return False
        SystemController.check_stop_signal()
        try:
            query = (
                f"'{root_folder_id}' in parents and name='{task_id}' "
                f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
            )
            results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            items = results.get("files", [])
            if items:
                subfolder_id = items[0]["id"]
                log_status("GDRIVE", f"[{task_id}] Found GDrive subfolder. ID: {subfolder_id}", "INFO")
                break
        except Exception as exc:
            log_status("GDRIVE", f"[{task_id}] Error querying GDrive subfolder: {exc}", "WARN")
        log_status("GDRIVE", f"[{task_id}] Waiting for GDrive subfolder to appear...", "INFO")
        if os.path.exists("stop.txt"):
            log_status("GDRIVE", f"[{task_id}] Stop signal detected, aborting GDrive poll.", "WARN")
            return False
        SystemController.check_stop_signal()
        time.sleep(poll_interval)

    if not subfolder_id:
        log_status("GDRIVE", f"[{task_id}] Timed out waiting for GDrive subfolder.", "ERROR")
        return False

    # Phase 2 – wait for the target video file inside the subfolder
    while time.time() - start_time <= max_wait:
        if os.path.exists("stop.txt"):
            log_status("GDRIVE", f"[{task_id}] Stop signal detected, aborting GDrive poll.", "WARN")
            return False
        SystemController.check_stop_signal()
        try:
            query = f"'{subfolder_id}' in parents and name='{file_name}' and trashed=false"
            results = service.files().list(
                q=query, spaces="drive", fields="files(id, name, size)"
            ).execute()
            items = results.get("files", [])
            if items:
                file_id = items[0]["id"]
                log_status("GDRIVE", f"[{task_id}] Found '{file_name}' on GDrive. Downloading...", "INFO")
                os.makedirs(os.path.dirname(clip_path), exist_ok=True)
                request = service.files().get_media(fileId=file_id)
                with open(clip_path, "wb") as fh:
                    downloader = _MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                log_status("GDRIVE", f"[{task_id}] Downloaded rendered video to {clip_path}", "SUCCESS")
                return True
        except Exception as exc:
            log_status("GDRIVE", f"[{task_id}] Error querying/downloading from GDrive: {exc}", "WARN")
        log_status("GDRIVE", f"[{task_id}] Waiting for rendered video on GDrive...", "INFO")
        if os.path.exists("stop.txt"):
            log_status("GDRIVE", f"[{task_id}] Stop signal detected, aborting GDrive poll.", "WARN")
            return False
        SystemController.check_stop_signal()
        time.sleep(poll_interval)

    log_status("GDRIVE", f"[{task_id}] Timed out waiting for video on GDrive.", "ERROR")
    return False


def encode_video_github_sync(
    img_path: str,
    duration: float,
    clip_path: str,
    movement: str,
    github_config: dict[str, Any],
    watermark: str = "",
) -> bool:
    """Render a single clip through GitHub Actions and download the artifact."""
    token = github_config.get("TOKEN") or os.getenv("GITHUB_TOKEN", "")
    repo_owner = github_config.get("REPO_OWNER", "")
    repo_name = github_config.get("REPO_NAME", "")
    workflow_filename = github_config.get("WORKFLOW_FILENAME", "")
    branch = github_config.get("BRANCH", "main")
    imgbb_api_key = github_config.get("IMGBB_API_KEY", "")
    poll_interval = int(github_config.get("POLL_INTERVAL_SECONDS", 20))
    max_wait = int(github_config.get("MAX_WAIT_SECONDS", 600))

    task_id = os.path.splitext(os.path.basename(clip_path))[0]
    if not token or not repo_owner or not repo_name or not workflow_filename:
        log_status("GITHUB", f"[{task_id}] GitHub renderer config is incomplete.", "ERROR")
        return False

    image_url = _github_upload_image_dynamic(img_path, task_id, imgbb_api_key)
    if not image_url:
        return False

    trace_id = f"{task_id}-{int(time.time())}"
    dispatch_url = (
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/"
        f"{workflow_filename}/dispatches"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    dispatch_inputs: dict[str, Any] = {
        "task_id": task_id,
        "trace_id": trace_id,
        "image_url": image_url,
        "duration": str(duration),
        "movement": movement,
    }
    if watermark:
        dispatch_inputs["watermark"] = watermark
    payload = {
        "ref": branch,
        "inputs": dispatch_inputs,
    }

    dispatch_response = GitHubSyncManager._request(
        "POST",
        dispatch_url,
        headers=headers,
        json=payload,
        expected_statuses={204},
    )
    if dispatch_response is None or dispatch_response.status_code != 204:
        log_status("GITHUB", f"[{task_id}] Failed to trigger GitHub workflow.", "ERROR")
        return False

    log_status("GITHUB", f"[{task_id}] GitHub workflow dispatched. Polling Google Drive for rendered video...", "INFO")
    runs_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs"

    # ---- Step 1: Resolve GDrive OAuth credentials from github_config or environment ----
    gdrive_folder_id  = github_config.get("GDRIVE_FOLDER_ID",  "") or os.getenv("GDRIVE_FOLDER_ID",  "")
    gcp_client_id     = github_config.get("GCP_CLIENT_ID",     "") or os.getenv("GCP_CLIENT_ID",     "")
    gcp_client_secret = github_config.get("GCP_CLIENT_SECRET", "") or os.getenv("GCP_CLIENT_SECRET", "")
    gcp_refresh_token = github_config.get("GCP_REFRESH_TOKEN", "") or os.getenv("GCP_REFRESH_TOKEN", "")

    if not gdrive_folder_id:
        log_status("GDRIVE", f"[{task_id}] GDRIVE_FOLDER_ID is not configured.", "ERROR")
        return False
    if not gcp_refresh_token:
        log_status("GDRIVE", f"[{task_id}] GCP_REFRESH_TOKEN is not configured.", "ERROR")
        return False

    # ---- Step 2: Authenticate via OAuth and poll GDrive for the rendered video ----
    gdrive_service = _gdrive_authenticate(gcp_client_id, gcp_client_secret, gcp_refresh_token)
    if not gdrive_service:
        return False

    # The workflow uploads: output_{trace_id}.mp4 → GDrive:<root_folder>/<task_id>/
    expected_filename = f"output_{trace_id}.mp4"
    success = _gdrive_poll_and_download(
        service=gdrive_service,
        root_folder_id=gdrive_folder_id,
        task_id=task_id,
        file_name=expected_filename,
        clip_path=clip_path,
        poll_interval=poll_interval,
        max_wait=max_wait,
    )

    return success


def build_nvenc_zoompan_ffmpeg_cmd(
    img_path: str,
    duration: float,
    clip_path: str,
    movement: str,
    overlay_path: Optional[str] = None,
    fps: int = 25,
    nvenc_preset: str = "p6",
    watermark: str = "",
) -> list[str]:
    """
    Build ffmpeg argv for a single Ken Burns segment → H.264 NVENC clip.
    Updated to match high-quality parameters from video_render.yml.
    """
    f_frames = max(float(duration * fps), 1.0)
    zoom_max = 1.25
    zoom_diff = 0.25

    # Logic from video_render.yml: Scale to increase, crop, then scale to intermediate high-res
    base_filter = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,scale=2560:1440"
    end_filter = "scale=1920:1080:flags=bicubic"

    if movement == "zoom_in":
        zp_expr = f"z='1.001+{zoom_diff}*(on/{f_frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif movement == "zoom_out":
        zp_expr = f"z='{zoom_max}-{zoom_diff}*(on/{f_frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif movement == "pan_right":
        zp_expr = f"z='{zoom_max}':x='(iw-iw/zoom)*(on/{f_frames})':y='ih/2-(ih/zoom/2)'"
    elif movement == "pan_left":
        zp_expr = f"z='{zoom_max}':x='(iw-iw/zoom)*(1-on/{f_frames})':y='ih/2-(ih/zoom/2)'"
    elif movement == "pan_down":
        zp_expr = f"z='{zoom_max}':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(on/{f_frames})'"
    elif movement == "pan_up":
        zp_expr = f"z='{zoom_max}':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{f_frames})'"
    else:
        # Default to center zoom in
        zp_expr = f"z='1.001+{zoom_diff}*(on/{f_frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    zoompan = f"{base_filter},zoompan={zp_expr}:d=1:s=2560x1440:fps={fps},{end_filter}"
    
    cmd: list[str] = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-t", f"{duration:.2f}", "-i", img_path]

    filters = [zoompan]

    # Watermark support (if provided)
    if watermark:
        # Simple drawtext filter for watermark
        font_path = "C:/Windows/Fonts/msyhbd.ttc" # Default Windows font
        # Escape single quotes and colons for ffmpeg drawtext
        safe_watermark = watermark.replace("'", "").replace(":", "")
        text_filter = (
            f"drawtext=fontfile='{font_path}':text='{safe_watermark}':"
            f"fontcolor=white@0.6:fontsize=40:x=60:y=60:"
            f"shadowcolor=black@0.6:shadowx=2:shadowy=2"
        )
        filters.append(text_filter)

    use_overlay = bool(overlay_path and os.path.isfile(overlay_path))
    if use_overlay:
        cmd.extend(["-stream_loop", "-1", "-t", f"{duration:.2f}", "-i", overlay_path])
        filter_complex = (
            f"[0:v]{','.join(filters)},format=gbrp[bg];[1:v]format=yuv420p,scale=1920:1080,format=gbrp[ovl];"
            f"[bg][ovl]blend=all_mode='screen':all_opacity=0.4,format=yuv420p[v]"
        )
        cmd.extend(["-filter_complex", filter_complex, "-map", "[v]"])
    else:
        cmd.extend(["-vf", f"{','.join(filters)},format=yuv420p"])

    # High-quality NVENC settings from YAML: -preset p6 -tune hq -rc vbr -cq 23
    cmd.extend([
        "-c:v", "h264_nvenc",
        "-preset", nvenc_preset,
        "-tune", "hq",
        "-rc", "vbr",
        "-cq", "23",
        "-pix_fmt", "yuv420p",
        clip_path
    ])
    return cmd


def render_video_multi_segment_sync(
    img_path: str,
    duration: float,
    clip_path: str,
    start_movement: str = "zoom_in",
    watermark: str = "",
    overlay_path: Optional[str] = None,
    segment_length: float = 15.0,
    fade_duration: float = 0.6,
    fps: int = 25,
) -> bool:
    """
    Render a video by splitting it into 15s segments and merging with xfade.
    Adopts the logic from video_render.yml into the local pipeline.
    """
    if duration <= 0:
        return False

    # Single-pass render: channel disabled splitting, or clip shorter than one segment.
    split_video = VIDEO_RENDER_CONFIG.get("SPLIT_VIDEO_SEGMENT", True)
    if not split_video or duration <= segment_length + fade_duration:
        if duration > segment_length + fade_duration and not split_video:
            log_status(
                "FFMPEG",
                f"SPLIT_VIDEO_SEGMENT=False: direct single render for {duration:.1f}s clip.",
                "INFO",
            )
        cmd = build_nvenc_zoompan_ffmpeg_cmd(
            img_path=img_path,
            duration=duration,
            clip_path=clip_path,
            movement=start_movement,
            overlay_path=overlay_path,
            fps=fps,
            watermark=watermark
        )
        try:
            safe_subprocess_run(cmd, stage="FFMPEG_SINGLE")
            return True
        except Exception as exc:
            log_status("FFMPEG", f"Single segment render failed: {exc}", "ERROR")
            return False

    temp_dir = os.path.join(os.path.dirname(clip_path), "temp_clips")
    os.makedirs(temp_dir, exist_ok=True)
    
    movements = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_down", "pan_up"]
    try:
        start_idx = movements.index(start_movement)
    except ValueError:
        start_idx = 0

    num_segments = int(duration // segment_length)
    remainder = duration % segment_length
    if remainder > 1.0: # Only add remainder segment if it's meaningful
        num_segments += 1
    
    segment_data = [] # List of (path, duration)
    current_time = 0.0
    
    log_status("FFMPEG", f"Splitting {duration}s into {num_segments} segments for xfade...", "INFO")

    try:
        for i in range(num_segments):
            is_last = (i == num_segments - 1)
            base_duration = segment_length if not is_last else (duration - current_time)
            
            if base_duration <= 0.1:
                break
                
            render_duration = base_duration + fade_duration if not is_last else base_duration
            current_movement = movements[(start_idx + i) % len(movements)]
            
            seg_filename = f"seg_{i:03d}_{current_movement}.mp4"
            seg_path = os.path.join(temp_dir, seg_filename)
            
            # Use build_nvenc_zoompan_ffmpeg_cmd for each segment
            cmd = build_nvenc_zoompan_ffmpeg_cmd(
                img_path=img_path,
                duration=render_duration,
                clip_path=seg_path,
                movement=current_movement,
                overlay_path=overlay_path,
                fps=fps,
                watermark=watermark
            )
            
            safe_subprocess_run(cmd, stage=f"SEG_{i+1}")
            
            segment_data.append((seg_path, render_duration))
            current_time += base_duration

        # Merge segments with xfade
        if not segment_data:
            return False
            
        if len(segment_data) == 1:
            shutil.move(segment_data[0][0], clip_path)
            return True

        log_status("FFMPEG", "Merging segments with complex xfade transitions...", "INFO")
        merge_cmd = ["ffmpeg", "-y"]
        for s_path, _ in segment_data:
            merge_cmd.extend(["-i", s_path])
            
        filters = []
        last_out = "0:v"
        current_offset = 0.0
        
        for i in range(1, len(segment_data)):
            prev_render_duration = segment_data[i-1][1]
            current_offset += (prev_render_duration - fade_duration)
            
            out_tag = f"v{i}"
            # Select random transition? YAML uses 'fade'.
            transitions = ["fade", "wipeleft", "wiperight", "slideleft", "slideright"]
            trans = transitions[0] # Stick to fade for now as per user request
            f_str = f"[{last_out}][{i}:v]xfade=transition={trans}:duration={fade_duration}:offset={current_offset:.2f}[{out_tag}]"
            filters.append(f_str)
            last_out = out_tag
            
        merge_cmd.extend([
            "-filter_complex", ";".join(filters),
            "-map", f"[{last_out}]",
            "-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "23",
            "-pix_fmt", "yuv420p",
            clip_path
        ])
        
        safe_subprocess_run(merge_cmd, stage="FFMPEG_MERGE")
        log_status("FFMPEG", f"Multi-segment video completed: {os.path.basename(clip_path)}", "SUCCESS")
        return True

    finally:
        # Cleanup temp segments
        try:
            for s_path, _ in segment_data:
                if os.path.exists(s_path):
                    os.remove(s_path)
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
        except Exception as e:
            log_status("FFMPEG", f"Temp cleanup failed: {e}", "WARN")





def save_task_record(csv_path: str, task_id: str, app_name: str, start_time: datetime, end_time: datetime, result: str, output_path: str, story_title: str = "Unknown"):
    """Upsert one row keyed by task_id into a UTF-8-sig CSV (atomic replace)."""
    if not csv_path:
        return
    abs_csv_path = os.path.abspath(csv_path)
    parent = os.path.dirname(abs_csv_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    headers = ["task_id", "app_name", "start_time", "end_time", "result", "output_path", "story_title"]
    rows = []
    if os.path.isfile(abs_csv_path):
        try:
            with open(abs_csv_path, mode="r", encoding="utf-8-sig") as file_obj:
                reader = csv.DictReader(file_obj)
                existing_headers = reader.fieldnames or []
                for header in existing_headers:
                    if header not in headers:
                        headers.append(header)
                rows = list(reader)
        except Exception as exc:
            log_status("RECORD", f"Failed to read existing CSV, proceeding fresh: {exc}", "WARN")

    task_found = False
    for row in rows:
        if row.get("task_id") == task_id:
            row["end_time"] = end_time.strftime("%Y-%m-%d %H:%M:%S")
            row["result"] = result
            row["output_path"] = output_path
            row["story_title"] = story_title
            task_found = True
            break

    if not task_found:
        rows.append(
            {
                "task_id": task_id,
                "app_name": app_name,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "result": result,
                "output_path": output_path,
                "story_title": story_title,
            }
        )

    try:
        temp_csv = abs_csv_path + ".tmp"
        with open(temp_csv, mode="w", newline="", encoding="utf-8-sig") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_csv, abs_csv_path)
        log_status("RECORD", f"Task [{task_id}] saved to {os.path.basename(abs_csv_path)}.", "OK")
    except Exception as exc:
        log_status("RECORD", f"Failed to write task record: {exc}", "ERROR")


# =====================================================================
# SHARED RUNNER UTILITIES
# =====================================================================

def str2bool(value):
    """Convert CLI string arguments to boolean for argparse."""
    if isinstance(value, bool):
        return value
    if value.lower() in ("yes", "true", "t", "y", "1"):
        return True
    if value.lower() in ("no", "false", "f", "n", "0"):
        return False
    raise argparse.ArgumentTypeError("Boolean value expected.")


def _sync_runtime_config_to_model_globals(cfg_module: Any):
    """Apply the finalized layered config to global runtime dictionaries."""
    if hasattr(cfg_module, "model_settings"):
        if "voice_en" in cfg_module.model_settings:
            MODEL_CONFIG["VOICE_EN"] = cfg_module.model_settings["voice_en"]
        if "voice_cn" in cfg_module.model_settings:
            MODEL_CONFIG["VOICE_CN"] = cfg_module.model_settings["voice_cn"]
            if not hasattr(cfg_module, "AZURE_TTS_VOICE"):
                MODEL_CONFIG["AZURE_TTS_VOICE"] = cfg_module.model_settings["voice_cn"]
        if "gemma4_model" in cfg_module.model_settings:
            MODEL_CONFIG["GEMMA4_MODEL"] = cfg_module.model_settings["gemma4_model"]
        if "azure_tts_style" in cfg_module.model_settings:
            MODEL_CONFIG["AZURE_TTS_STYLE"] = cfg_module.model_settings["azure_tts_style"]
        if "tts_voicerate" in cfg_module.model_settings:
            MODEL_CONFIG["TTS_VOICERATE"] = cfg_module.model_settings["tts_voicerate"]

    gemma4_cfg = dict(getattr(cfg_module, "GEMMA4_INTERFACE_CONFIG", {}) or {})
    if gemma4_cfg:
        MODEL_CONFIG["GEMMA4_INTERFACE_CONFIG"] = gemma4_cfg
    MODEL_CONFIG["GEMMA4_MODEL"] = str(
        gemma4_cfg.get("MODEL")
        or getattr(cfg_module, "GEMMA4_MODEL", "")
        or os.getenv("GEMMA4_MODEL", MODEL_CONFIG.get("GEMMA4_MODEL", "gemma-4-e4b-it"))
    )

    MODEL_CONFIG["USE_AZURE_TTS"] = bool(getattr(cfg_module, "USE_AZURE_TTS", MODEL_CONFIG.get("USE_AZURE_TTS", False)))
    MODEL_CONFIG["AZURE_TTS_ENDPOINT"] = str(getattr(cfg_module, "AZURE_TTS_ENDPOINT", os.getenv("AZURE_TTS_ENDPOINT", MODEL_CONFIG.get("AZURE_TTS_ENDPOINT", ""))))
    MODEL_CONFIG["AZURE_TTS_REGION"] = str(getattr(cfg_module, "AZURE_TTS_REGION", os.getenv("AZURE_TTS_REGION", MODEL_CONFIG.get("AZURE_TTS_REGION", ""))))
    MODEL_CONFIG["AZURE_TTS_OUTPUT_FORMAT"] = str(getattr(cfg_module, "AZURE_TTS_OUTPUT_FORMAT", os.getenv("AZURE_TTS_OUTPUT_FORMAT", MODEL_CONFIG.get("AZURE_TTS_OUTPUT_FORMAT", ""))))
    MODEL_CONFIG["AZURE_TTS_VOICE"] = str(getattr(cfg_module, "AZURE_TTS_VOICE", os.getenv("AZURE_TTS_VOICE", MODEL_CONFIG.get("AZURE_TTS_VOICE", ""))))
    MODEL_CONFIG["AZURE_TTS_STYLE"] = str(getattr(cfg_module, "AZURE_TTS_STYLE", os.getenv("AZURE_TTS_STYLE", MODEL_CONFIG.get("AZURE_TTS_STYLE", ""))))
    MODEL_CONFIG["AZURE_TTS_BREAK_MID_MS"] = str(getattr(cfg_module, "AZURE_TTS_BREAK_MID_MS", os.getenv("AZURE_TTS_BREAK_MID_MS", MODEL_CONFIG.get("AZURE_TTS_BREAK_MID_MS", "300"))))
    MODEL_CONFIG["AZURE_TTS_BREAK_END_MS"] = str(getattr(cfg_module, "AZURE_TTS_BREAK_END_MS", os.getenv("AZURE_TTS_BREAK_END_MS", MODEL_CONFIG.get("AZURE_TTS_BREAK_END_MS", "1000"))))
    if hasattr(cfg_module, "TTS_VOICERATE"):
        MODEL_CONFIG["TTS_VOICERATE"] = str(getattr(cfg_module, "TTS_VOICERATE"))

    RUNNINGHUB_CONFIG["KEY"] = os.getenv("RUNNINGHUB_API_KEY") or RUNNINGHUB_CONFIG.get("KEY")
    RUNNINGHUB_CONFIG["USE_ZIMAGE"] = bool(getattr(cfg_module, "USE_RUNNINGHUB_ZIMAGE", RUNNINGHUB_CONFIG.get("USE_ZIMAGE", False)))
    VIDEO_RENDER_CONFIG["SPLIT_VIDEO_SEGMENT"] = bool(
        getattr(cfg_module, "SPLIT_VIDEO_SEGMENT", VIDEO_RENDER_CONFIG.get("SPLIT_VIDEO_SEGMENT", True))
    )


def load_python_config(file_path: str, cli_args: Optional[Any] = None):
    """Load layered config with deterministic precedence and sync runtime globals."""
    try:
        cfg_module = load_channel_runtime_config(file_path, cli_args=cli_args)
        log_status("CONFIG", f"Successfully loaded Python config: {file_path}", "OK")
        env_config_file = getattr(cfg_module, "ENV_CONFIG_FILE", "")
        if env_config_file:
            loaded_env_vars = getattr(cfg_module, "LOADED_ENV_VARS", {}) or {}
            log_status("CONFIG", f"Loaded {len(loaded_env_vars)} env var(s) from: {env_config_file}", "INFO")
        _sync_runtime_config_to_model_globals(cfg_module)
        return cfg_module
    except Exception as exc:
        log_status("CONFIG", f"Failed to load Python config {file_path}: {exc}", "CRITICAL")
        sys.exit(1)


class LibraryManager:
    """Load asset matrix from CSV, supporting SEQUENCE or RANDOM row fetching strategies."""
    matrix = []

    @classmethod
    def load_from_csv(cls, filepath: str):
        cls.matrix = []
        if not filepath or not os.path.exists(filepath):
            log_status("LIBRARY", f"CSV not found at {filepath}.", "WARN")
            return
        try:
            with open(filepath, mode="r", encoding="utf-8-sig") as file_obj:
                reader = csv.DictReader(file_obj)
                original_headers = list(reader.fieldnames or [])
                normalized_headers = [(field or "").strip().lower() for field in original_headers]
                rows = []
                for raw_row in reader:
                    normalized_row = {}
                    for original, normalized in zip(original_headers, normalized_headers):
                        if not normalized:
                            continue
                        normalized_row[normalized] = raw_row.get(original)
                    if any(str(val or "").strip() for val in normalized_row.values()):
                        rows.append(normalized_row)
                cls.matrix = rows
                log_status("LIBRARY", f"Loaded {len(cls.matrix)} rows from library.", "OK")
        except Exception as exc:
            log_status("LIBRARY", f"Failed to parse CSV: {exc}", "ERROR")

    @classmethod
    def get_target_index(cls, record_csv: str, mode: str) -> int:
        total = len(cls.matrix)
        if total == 0:
            return 0

        if mode.upper() == "SEQUENCE":
            if not os.path.exists(record_csv):
                return 0
            try:
                with open(record_csv, mode="r", encoding="utf-8") as file_obj:
                    rows = list(csv.reader(file_obj))
                if len(rows) <= 1:
                    return 0
                last_story_title = ""
                for row in reversed(rows):
                    if "SUCCESS" in row:
                        last_story_title = row[-1].strip()
                        break
                if last_story_title:
                    for idx, item in enumerate(cls.matrix):
                        if item.get("story", "").strip() == last_story_title:
                            return (idx + 1) % total
            except Exception as exc:
                log_status("LIBRARY", f"Failed to trace story from record.csv: {exc}", "WARN")
            return 0

        return random.randint(0, total - 1)


def merge_dual_scripts(en_list: list, cn_list: list, min_length: int = 40) -> tuple:
    """
    Merge bilingual EN/CN script lists by character length bounding to prevent overly fragmented audio.
    Returns (merged_en, merged_cn) as two lists.
    """
    merged_en, merged_cn = [], []
    buf_en, buf_cn = "", ""
    max_len = max(len(en_list), len(cn_list))
    for i in range(max_len):
        en = en_list[i] if i < len(en_list) else ""
        cn = cn_list[i] if i < len(cn_list) else ""
        en_clean, cn_clean = en.strip(), cn.strip()
        if not en_clean and not cn_clean:
            continue
        buf_en = (buf_en + " " + en_clean).strip()
        buf_cn = (buf_cn + " " + cn_clean).strip()
        if len(buf_cn) >= min_length or len(buf_en) >= min_length * 2:
            merged_en.append(buf_en)
            merged_cn.append(buf_cn)
            buf_en, buf_cn = "", ""
    if buf_en or buf_cn:
        if merged_en or merged_cn:
            if merged_en:
                merged_en[-1] = (merged_en[-1] + " " + buf_en).strip()
            if merged_cn:
                merged_cn[-1] = (merged_cn[-1] + " " + buf_cn).strip()
        else:
            merged_en.append(buf_en)
            merged_cn.append(buf_cn)
    return merged_en, merged_cn


def construct_media_segments(folder: str, en_scripts: list, cn_scripts: list, img_prompts: list) -> list:
    """
    Construct a list of MediaSegment objects from the EN/CN scripts and image prompt lists.
    Factory function complementing the MediaSegment dataclass.
    """
    segments = []
    max_len = max(len(en_scripts), len(cn_scripts))
    for idx in range(max_len):
        en_text = en_scripts[idx] if idx < len(en_scripts) else ""
        cn_text = cn_scripts[idx] if idx < len(cn_scripts) else ""
        img_prompt = img_prompts[idx] if idx < len(img_prompts) else "Scene"
        segments.append(MediaSegment(
            index=idx + 1,
            en_text=en_text,
            cn_text=cn_text,
            img_prompt=img_prompt,
            img_path=os.path.join(folder, "image", f"s{idx + 1:03d}_img.png"),
            en_audio_path=os.path.join(folder, "audio", f"s{idx + 1:03d}_en.wav"),
            cn_audio_path=os.path.join(folder, "audio", f"s{idx + 1:03d}_cn.wav"),
            en_video_path=os.path.join(folder, "video", f"s{idx + 1:03d}_en.mp4"),
            cn_video_path=os.path.join(folder, "video", f"s{idx + 1:03d}_cn.mp4"),
        ))
    return segments


# =====================================================================
# LLM TEXT CLEANING PIPELINE & SSML INJECTION
# =====================================================================

# [Function]: Regex stripper for excessive divider noise characters in outputs
def remove_pure_symbols(text: str) -> str:
    """
    Clean up pure symbol divider lines generated by LLMs.
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

# [Function]: Remove LLM conversational filler/boilerplate
def remove_ai_hallucinations(text: str) -> str:
    """
    Remove LLM-generated title lines with semantic prefixes (e.g. "--- Chinese Script ---").
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

# [Function]: Unify paragraph spacing to prevent consecutive layout gaps
def clean_formatting(text: str) -> str:
    """
    Clean leading/trailing whitespace and excessive blank lines from row deletions.
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

# [Function]: Execute chained system-level text purification pipeline
def run_clean_pipeline(raw_text: str) -> str:
    """
    Core text processor: execute the cleanup pipeline sequentially.
    """
    if not raw_text:
        log_status("PIPELINE", "run_clean_pipeline: Received empty string, aborting.", "WARN")
        return ""
    
    text = remove_pure_symbols(raw_text)
    text = remove_ai_hallucinations(text)
    final_text = clean_formatting(text)
    return final_text 

# [Feature]: Dynamic TTs pause injection formatter (SSML)
def apply_ssml_pauses(text: str) -> str:
    """
    [Enhancement]: ASMR physical pause injector
    - Azure TTS: inject explicit SSML <break> tags (300ms intra-sentence, end delays adjustable).
    - Edge TTS: retain original newline/punctuation behavior for inherent semantic pausing.
    """
    log_status("TTS_PAUSE", "Applying ASMR natural punctuation pauses...", "INFO")
    if not text or not text.strip():
        log_status("TTS_PAUSE", "Text is empty, skipping pause injection.", "WARN")
        return text

    try:
        if MODEL_CONFIG.get("USE_AZURE_TTS", False):
            mid_pause = MODEL_CONFIG.get("AZURE_TTS_BREAK_MID_MS", "300")
            end_pause = MODEL_CONFIG.get("AZURE_TTS_BREAK_END_MS", "800")
            
            # Optimization 1: add "+" to fix repeated injection bug caused by consecutive punctuation (e.g. "!!!", "...")
            # Optimization 2: add \s* to absorb trailing spaces after punctuation and avoid noise
            
            #pattern_comma = r'([,;，；]+)\s*'
            #replacement_comma = r'\1[[BR_' + str(mid_pause) + r']] ' 
            
            pattern_period = r'([.!?。！？]+)\s*'
            replacement_period = r'\1[[BR_' + str(end_pause) + r']] ' 
            
            #text_with_breaks = re.sub(pattern_comma, replacement_comma, text)
            text_with_breaks = re.sub(pattern_period, replacement_period, text)

            # Clean up excessive spacing
            text_with_breaks = re.sub(r' {2,}', ' ', text_with_breaks)
            
            # log_status("TTS_PAUSE", "Azure SSML pauses injected successfully.", "OK")
            return text_with_breaks.strip()

        # Edge-TTS fallback: trigger original newline-split strategy
        pattern_comma = r'([,;，；])'
        replacement_comma = r'\1 \n'
        text_with_breaks = re.sub(pattern_comma, replacement_comma, text)

        pattern_period = r'([.!?。！？])'
        replacement_period = r'\1 \n\n ... \n\n ... \n\n'
        text_with_breaks = re.sub(pattern_period, replacement_period, text_with_breaks)

        text_with_breaks = re.sub(r' {2,}', ' ', text_with_breaks)
        log_status("TTS_PAUSE", "Edge pause markers injected successfully.", "OK")
        return text_with_breaks.strip()

    except Exception as e:
        log_status("TTS_PAUSE", f"Pause injection failed with Exception: {e}", "ERROR")
        return text


# =====================================================================
# MANAGERS & CLIENTS
# =====================================================================

class RunningHubManager:
    """
    [Feature]: Safe lifecycle manager tracking all pending RunningHub operations.
    Uses synchronous urllib requests to prevent Asyncio/HTTPX teardown crash loops on interrupt.
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
        """Synchronous cancellation blocking asynchronous lifecycle teardown interference."""
        if not task_id: return
        cls.remove_task(task_id)
        # Dynamically read API key to support post-import .env file loads
        api_key = os.getenv("RUNNINGHUB_API_KEY") or RUNNINGHUB_CONFIG.get("KEY")
        if not api_key: return

        url = "https://www.runninghub.ai/task/openapi/cancel"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = json.dumps({"apiKey": api_key, "taskId": task_id}).encode('utf-8')

        log_status("RH_CONNECT", f"Cancel RunningHub with key {api_key[:20]}..." if len(api_key) > 20 else "***", "WARN")

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

# [Feature]: Synchronous emergency exit hook capturing extreme faults or os._exit() aborts.
def _emergency_sync_cleanup():
    """Emergency atexit hook: synchronously cancel all active RunningHub tasks on process exit."""
    tasks = list(RunningHubManager._active_tasks)
    if not tasks: return
    # Dynamically read API key to support post-import .env file loads
    api_key = os.getenv("RUNNINGHUB_API_KEY") or RUNNINGHUB_CONFIG.get("KEY")
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

# Register into low-level Python lifecycle exit hooks
atexit.register(_emergency_sync_cleanup)


class ConcurrencyManager:
    LLM_SEM = None
    TTS_SEM = None
    IMG_SEM = None
    NVENC_SEM = None
    GEMMA4_SEM = None

    @classmethod
    # [Function]: Initial mount binding all core pipeline concurrency semaphores
    def init_locks(cls):
        """Initialize all async semaphores for LLM, TTS, image, NVENC, and Gemma4 concurrency control."""
        cls.LLM_SEM = asyncio.Semaphore(5)
        cls.TTS_SEM = asyncio.Semaphore(4)
        cls.IMG_SEM = asyncio.Semaphore(1)
        cls.NVENC_SEM = asyncio.Semaphore(2)
        cls.GEMMA4_SEM = asyncio.Semaphore(2)
        log_status("SYSTEM", "Concurrency locks explicitly bound to Event Loop.", "OK")

class APIClients:
    _openai = None
    _deepseek = None
    _gemini = None
    _http = None

    @classmethod
    # [Function]: Lazily instantiate and cache global singleton OpenAI client pools
    def get_openai(cls):
        """Return the cached AsyncOpenAI client, creating it on first call."""
        if not cls._openai: cls._openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return cls._openai

    @classmethod
    # [Function]: Lazily instantiate unique DeepSeek official client from singleton pool
    def get_deepseek(cls):
        """Return the cached DeepSeek/SiliconFlow AsyncOpenAI client, creating it on first call."""
        if not cls._deepseek: 
            cls._deepseek = AsyncOpenAI(api_key=os.getenv("SILICONFLOW_API_KEY"), base_url="https://api.siliconflow.com/v1")
        return cls._deepseek

    @classmethod
    # [Function]: Singleton loader retrieving Google GenAI official client
    def get_gemini(cls):
        """Return the cached Google GenAI client, creating it on first call."""
        if not cls._gemini: cls._gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return cls._gemini

    @classmethod
    # [Function]: Reuse local httpx AsyncClient for intensive high-throughput tasks
    def get_http(cls):
        """Return the cached httpx AsyncClient, creating it on first call."""
        if not cls._http: cls._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC)
        return cls._http
        
    @classmethod
    # [Function]: Safety net: gracefully teardown deep memory sockets upon application halt
    async def close_all(cls):
        """Cancel all active RunningHub tasks and close the shared httpx client."""
        RunningHubManager.cancel_all() # Cleanup incomplete operations before exiting
        if cls._http: 
            await cls._http.aclose()
            cls._http = None

class APIRateLimiter:
    _locks = {}
    _last_calls = {}

    @classmethod
    # [Function]: Token bucket flow guard minimizing API bombardment floods during high concurrency
    async def throttle(cls, api_name: str, delay_sec=5.0):
        """Enforce a minimum delay between consecutive calls to the same API endpoint.
        Also checks for the stop signal before each API call.
        """
        # [Global Kill Switch]: Immediate circuit break if stop.txt is detected before API calls!
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

async def _azure_tts_url() -> str:
    """Resolve the Azure TTS REST endpoint URL from config, normalizing the hostname to the TTS subdomain."""
    endpoint = MODEL_CONFIG.get("AZURE_TTS_ENDPOINT", "").rstrip("/")
    if not endpoint:
        region = MODEL_CONFIG.get("AZURE_TTS_REGION", "")
        if not region:
            raise RuntimeError("Azure TTS endpoint or region is not configured.")
        endpoint = f"https://{region}.api.cognitive.microsoft.com"
    if "api.cognitive.microsoft.com" in endpoint:
        endpoint = endpoint.replace("api.cognitive.microsoft.com", "tts.speech.microsoft.com")
    return endpoint.rstrip("/") + "/cognitiveservices/v1"

def _build_azure_tts_ssml(text: str) -> str:
    """Build an SSML document for Azure TTS, injecting break tags and optional express-as style."""
    voice = MODEL_CONFIG.get("AZURE_TTS_VOICE", "zh-CN-YunjianNeural")
    style = MODEL_CONFIG.get("AZURE_TTS_STYLE", "")
    safe_text = html.escape(text)
    safe_text = re.sub(r'\[\[BR_(\d+)\]\]', lambda m: f"<break time='{m.group(1)}ms'/>", safe_text)

    # Core Fix: Standard xmlns required to prevent <break> tag invalidations in recent APIs
    base_xmlns = "http://www.w3.org/2001/10/synthesis"
    mstts_xmlns = "http://www.w3.org/2001/mstts"
    
    if style:
        ssml = f"""<speak version='1.0' xml:lang='zh-CN' xmlns='{base_xmlns}' xmlns:mstts='{mstts_xmlns}'>
  <voice name='{voice}'>
    <mstts:express-as style='{style}'>
      {safe_text}
    </mstts:express-as>
  </voice>
</speak>"""
    else:
        ssml = f"""<speak version='1.0' xml:lang='zh-CN' xmlns='{base_xmlns}'>
  <voice name='{voice}'>
    {safe_text}
  </voice>
</speak>"""

    return ssml

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Function]: Industrial retry wrapper for Azure Speech TTS resolving connection hiccups
async def robust_azure_tts_call(text: str, raw_wav: str):
    api_key = os.getenv("AZURE_API_KEY", "")
    if not api_key:
        raise RuntimeError("Azure TTS key is not configured in AZURE_API_KEY.")
    tts_url = await _azure_tts_url()
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": MODEL_CONFIG.get("AZURE_TTS_OUTPUT_FORMAT", "audio-16khz-32kbitrate-mono-mp3"),
        "User-Agent": "ContentOS-AzureTTS/1.0",
        "Accept": "application/octet-stream",
    }
    ssml = _build_azure_tts_ssml(text)
    http = APIClients.get_http()
    resp = await http.post(tts_url, headers=headers, content=ssml.encode("utf-8"), timeout=HTTP_TIMEOUT_SEC)

    # Hard exit on 429 Quota Exceeded — retrying is pointless and wastes quota.
    if resp.status_code == 429:
        log_status("TTS", f"Azure TTS quota exceeded (429). Terminating pipeline immediately.", "ERROR")
        sys.exit(1)

    resp.raise_for_status()
    with open(raw_wav, "wb") as f:
        f.write(resp.content)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Function]: Industrial retry wrapper for Edge-TTS guarding against early connection drops
async def robust_edge_tts_call(text: str, voice: str, raw_wav: str):
    await edge_tts.Communicate(text, voice, rate=MODEL_CONFIG.get("TTS_VOICERATE", "-30%"), pitch="+4Hz") .save(raw_wav)

# [Function]: Unified TTS gateway: prioritize Azure, no fallback to Edge
async def robust_tts_call(text: str, voice: str, raw_wav: str):
    if MODEL_CONFIG.get("USE_AZURE_TTS", False):
        try:
            await robust_azure_tts_call(text, raw_wav)
            return
        except SystemExit:
            raise
        except Exception as exc:
            log_status("TTS", f"Azure TTS failed. Terminating pipeline immediately. Reason: {exc}", "ERROR")
            sys.exit(1)
    
    # If not using Azure TTS, use Edge TTS (e.g. for cost optimization)
    await robust_edge_tts_call(text, voice, raw_wav)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Function]: Industrial retry wrapper for RunningHub API capturing taskId or fetch timeouts
async def robust_image_call(prompt: str, img_path: str, log_tag: str):
    if RUNNINGHUB_CONFIG.get("USE_ZIMAGE", True):
        success = await generate_runninghub_image_with_zimage(prompt, img_path, log_tag)
    else:
        success = await generate_runninghub_image(prompt, img_path, log_tag)
        
    if not success:
        raise RuntimeError("RunningHub API completely failed to return a successful image.")
    return True

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Function]: Enterprise Gemini router featuring fault tolerance, length truncation, and auto-retry
async def robust_gemini_call(prompt: str, max_tokens: int = 2000) -> str:
    """
    Dual insurance guardrails:
    1. Physical output truncation via max_output_tokens.
    2. Failsafe circuit breaking via returned token lengths.
    """
    await APIRateLimiter.throttle("gemini", 2.0)
    res = await asyncio.to_thread(
        APIClients.get_gemini().models.generate_content, 
        model=MODEL_CONFIG["GEMINI_MODEL"], 
        contents=prompt,
        config=genai.types.GenerateContentConfig(max_output_tokens=max_tokens)
    )
    
    text = res.text
    if text and len(text) > max_tokens * 4: # Rough heuristic checking max limit by allocating 4 chars per token
        raise RuntimeError(f"Circuit Breaker Tripped: Gemini output wildly exceeded limits ({len(text)} chars).")
        
    return run_clean_pipeline(text)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Function]: Enterprise OpenAI router leveraging structural strong-type response parser
async def robust_openai_call(prompt: str, response_format, max_tokens: int = 1500) -> any:
    """
    Dual insurance guardrails:
    1. API level max_tokens constraint.
    2. Abort/retry upon string conversion measuring anomalous extreme output volumes.
    """
    await APIRateLimiter.throttle("openai", 0.5)
    # Note: response_format directly yields object instances bypassing need for regex cleaning
    res = await APIClients.get_openai().beta.chat.completions.parse(
        model=MODEL_CONFIG["OPENAI_MODEL"], 
        messages=[{"role": "user", "content": prompt}], 
        response_format=response_format,
        max_tokens=max_tokens
    )
    
    parsed_data = res.choices[0].message.parsed
    
    # Failsafe mechanism preventing infinite loop hallucination structures
    if len(str(parsed_data).split()) > 1500:
        raise RuntimeError("Circuit Breaker Tripped: OpenAI structured output word count wildly exceeded safety limits.")
        
    return parsed_data

def _extract_deepseek_choice_text(res) -> str:
    """Extract assistant text from a DeepSeek chat completion (content or reasoning fallback)."""
    choices = getattr(res, "choices", None) or []
    if not choices:
        log_status("DEEPSEEK", "API returned no choices.", "WARN")
        return ""
    choice = choices[0]
    msg = getattr(choice, "message", None)
    if msg is None:
        return ""
    text = _extract_message_text(getattr(msg, "content", None))
    if not text.strip():
        text = _extract_message_text(getattr(msg, "reasoning_content", None))
    if not text.strip():
        finish = getattr(choice, "finish_reason", "unknown")
        log_status("DEEPSEEK", f"Empty model output (finish_reason={finish})", "WARN")
    return text


async def _deepseek_chat_create(messages: list, max_tokens: int, temperature: float, disable_thinking: bool):
    kwargs = {
        "model": MODEL_CONFIG["DEEPSEEK_MODEL"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.95,
    }
    if disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return await APIClients.get_deepseek().chat.completions.create(**kwargs)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Function]: Enterprise DeepSeek router with hard output-length cap logic
async def robust_deepseek_call(
    prompt: str,
    max_tokens: int = 1000,
    clean_output: bool = True,
    temperature: float = 1.0,
    disable_thinking: bool = True,
) -> str:
    """
    Dual insurance guardrails:
    1. API layer parameter max_tokens limits.
    2. Runtime inspection of generated characters yielding protective abort circuits.
    
    Parameters:
    - temperature: variance (0.0-2.0). Higher yields creative variations. Default 0.9-1.2 for expanding narratives
    """
    await APIRateLimiter.throttle("deepseek", 4)
    res = await _deepseek_chat_create(
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        disable_thinking=disable_thinking,
    )

    text = _extract_deepseek_choice_text(res)

    if text and len(text) > max_tokens * 4:
        raise RuntimeError("Circuit Breaker Tripped: DeepSeek output text length wildly exceeded safety limits.")

    return run_clean_pipeline(text) if clean_output else text

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
async def robust_deepseek_call_system(
    prompt: str,
    system_prompt: str,
    max_tokens: int = 1000,
    clean_output: bool = True,
    temperature: float = 1.0,
    disable_thinking: bool = True,
) -> str:
    """Same as robust_deepseek_call but accepts a system prompt."""
    await APIRateLimiter.throttle("deepseek", 4)
    res = await _deepseek_chat_create(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        disable_thinking=disable_thinking,
    )

    text = _extract_deepseek_choice_text(res)

    if text and len(text) > max_tokens * 4:
        raise RuntimeError("Circuit Breaker Tripped: DeepSeek output text length wildly exceeded safety limits.")

    return run_clean_pipeline(text) if clean_output else text

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Function]: MiniMax API router via NVIDIA NIM endpoint using httpx async streaming
async def robust_minimax_call(prompt: str, max_tokens: int = 1024, clean_output: bool = True, temperature: float = 0.5) -> str:
    """
    MiniMax API router using NVIDIA NIM endpoint with Bearer token auth via httpx async streaming.
    
    Parameters:
    - temperature: variance (0.0-2.0). Higher yields creative variations. Default 0.5 for balanced output.
    - max_tokens: Hard output limit enforced both at API level and circuit breaker validation.
    """
    await APIRateLimiter.throttle("minimax", 4)
    
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        log_status("MINIMAX", "NVIDIA_NIM_API_KEY environment variable not set", "ERROR")
        raise RuntimeError("NVIDIA_NIM_API_KEY environment variable not set")
    
    invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json" # 强制返回JSON，而不是text/event-stream
    }
    
    payload = {
        "model": "minimaxai/minimax-m2.7",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": 1,
        "max_tokens": max_tokens,
        "stream": False
    }
    
    log_status("MINIMAX", f"Calling MiniMax API with max_tokens={max_tokens}, temp={temperature}...", "INFO")
    
    http_client = APIClients.get_http()
    text = ""
    chunk_count = 0
    line_count = 0
    
    try:
        async with http_client.stream("POST", invoke_url, headers=headers, json=payload, timeout=120.0) as response:
            log_status("MINIMAX", f"Response status: {response.status_code}", "INFO")
            log_status("MINIMAX", f"Response headers: {dict(response.headers)}", "DEBUG")
            
            # 读取原始字节以诊断格式
            raw_bytes = await response.aread()
            raw_text = raw_bytes.decode('utf-8', errors='replace')
            
            # 记录原始响应长度和前500字符
            log_status("MINIMAX", f"Raw response length: {len(raw_bytes)} bytes", "INFO")
            log_status("MINIMAX", f"Raw response preview: {repr(raw_text[:500])}", "DEBUG")

            if response.status_code == 202:
                request_id = None
                try:
                    pending_data = json.loads(raw_text) if raw_text.strip() else {}
                except json.JSONDecodeError:
                    pending_data = {}
                request_id = (
                    response.headers.get("NVCF-REQID")
                    or response.headers.get("X-Request-Id")
                    or pending_data.get("requestId")
                    or pending_data.get("id")
                )
                if not request_id:
                    raise RuntimeError(f"MiniMax returned 202 without requestId: {raw_text[:300]}")
                log_status("MINIMAX", f"MiniMax request pending; polling requestId={request_id}", "WARN")
                text = await _poll_nvidia_nim_result(http_client, headers, request_id)
                chunk_count = 1 if text else 0
                line_count = len(raw_text.splitlines()) if raw_text else 0
                raw_text = text
            else:
                response.raise_for_status()
            
                is_sse = any(line.startswith("data: ") for line in raw_text.splitlines())

                if is_sse:
                    # 按照可能的行分隔符分割（\n, \r\n, \n\r）
                    lines = raw_text.split('\n')
                    log_status("MINIMAX", f"Total lines after split: {len(lines)}", "INFO")
                    
                    for line in lines:
                        line = line.rstrip('\r')
                        line_count += 1
                        
                        # Debug: 记录前10行（无论是否为空）
                        if line_count <= 10:
                            log_status("MINIMAX", f"[Raw Line {line_count}] {repr(line[:100])}", "DEBUG")
                        
                        if not line or line.isspace():
                            continue
                        
                        # 处理 data: 开头的行
                        if line.startswith("data: "):
                            data = line[6:].strip()
                            if data == "[DONE]":
                                log_status("MINIMAX", f"Stream completed at line {line_count}", "INFO")
                                break
                            
                            try:
                                chunk = json.loads(data)
                                token_text = _extract_text_from_openai_like_payload(chunk)
                                if token_text:
                                    text += token_text
                                    chunk_count += 1
                            except json.JSONDecodeError:
                                log_status("MINIMAX", f"Failed to parse JSON at line {line_count}: {data[:50]}", "WARN")
                                continue
                        else:
                            # 记录非 data: 开头的行（可能有重要信息）
                            if line and not line.startswith(":"):
                                log_status("MINIMAX", f"[Non-data line {line_count}] {repr(line[:100])}", "DEBUG")
                else:
                    log_status("MINIMAX", "Response was not SSE; attempting direct JSON/text extraction.", "WARN")
                    try:
                        data = json.loads(raw_text)
                        text = _extract_text_from_openai_like_payload(data)
                        if not text:
                            nested_candidates = (
                                data.get("result"),
                                data.get("response"),
                                data.get("data"),
                            ) if isinstance(data, dict) else ()
                            for candidate in nested_candidates:
                                text = _extract_text_from_openai_like_payload(candidate)
                                if text:
                                    break
                        if text:
                            chunk_count = 1
                        else:
                            log_status("MINIMAX", f"Direct JSON payload keys: {list(data.keys())[:10] if isinstance(data, dict) else []}", "DEBUG")
                    except json.JSONDecodeError:
                        text = raw_text.strip()
                        if text:
                            chunk_count = 1
        
        # Validate output
        log_status("MINIMAX", f"Stream finished: {line_count} total lines, {chunk_count} chunks, {len(text)} chars", "INFO")
        
        if not text or not text.strip():
            log_status("MINIMAX", "Warning: MiniMax returned empty response (no content in any delta)", "WARN")
            return ""
        
        if len(text) > max_tokens * 4:
            log_status("MINIMAX", f"Circuit Breaker: Output {len(text)} chars exceeds limit {max_tokens * 4}", "ERROR")
            raise RuntimeError("Circuit Breaker Tripped: MiniMax output text length wildly exceeded safety limits.")
        
        log_status("MINIMAX", f"MiniMax response received ({len(text)} chars, {chunk_count} chunks)", "SUCCESS")
        return run_clean_pipeline(text) if clean_output else text
        
    except httpx.RequestError as e:
        log_status("MINIMAX", f"Network error calling MiniMax: {e}", "ERROR")
        raise
    except httpx.HTTPStatusError as e:
        log_status("MINIMAX", f"MiniMax API error {e.response.status_code}: {e}", "ERROR")
        raise

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
# [Feature]: Alternate model router (Kimi/Moonshot)
async def robust_kimi_call(prompt: str, max_tokens: int = 4000, clean_output: bool = True) -> str:
    """
    Dedicated Kimi endpoint natively multiplexing DeepSeek OS client interfaces via OpenAI compat.
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
# [Feature]: Light OSS router tunneling low-cost high-throughput formatting operations
async def robust_oss_call(prompt: str, max_tokens: int = 2000, clean_output: bool = True) -> str:
    """
    Calls highly efficient localized or OSS models conforming to DeepSeek REST specs (e.g., gpt-oss-20b).
    """
    await APIRateLimiter.throttle("oss", 4)
    log_status("OSS_API", f"Calling OSS model {MODEL_CONFIG.get('OSS_MODEL')} for rewrite...", "INFO")
    try:
        # Mutliplex generic OpenAI communication channel specifying dynamic model variants
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
        raise


def _extract_message_text(content) -> str:
    """Normalize OpenAI-compatible message content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                text_val = item.get("text")
                if text_val:
                    chunks.append(str(text_val))
            elif hasattr(item, "text") and getattr(item, "text"):
                chunks.append(str(item.text))
            else:
                chunks.append(str(item))
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    if content is None:
        return ""
    return str(content)


def _extract_text_from_openai_like_payload(data) -> str:
    """Extract assistant text from OpenAI-compatible JSON payload variants."""
    if not isinstance(data, dict):
        return ""

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice0 = choices[0] or {}

        delta = choice0.get("delta")
        if isinstance(delta, dict):
            delta_text = _extract_message_text(
                delta.get("content") or delta.get("formatted_content")
            )
            if delta_text:
                return delta_text

        message = choice0.get("message")
        if isinstance(message, dict):
            message_text = _extract_message_text(message.get("content"))
            if message_text:
                return message_text

        text = choice0.get("text")
        if text:
            return str(text)

    output = data.get("output")
    if isinstance(output, list) and output:
        output0 = output[0] or {}
        output_text = _extract_message_text(output0.get("content"))
        if output_text:
            return output_text

    content = data.get("content")
    if content:
        return _extract_message_text(content)

    return ""


async def _poll_nvidia_nim_result(
    http_client: httpx.AsyncClient,
    headers: dict,
    request_id: str,
    timeout_seconds: float = 120.0,
    poll_interval: float = 2.0,
) -> str:
    """Poll NVIDIA NIM pending requests until a fulfilled payload returns."""
    status_url = f"https://integrate.api.nvidia.com/v1/status/{request_id}"
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    attempt = 0

    while True:
        attempt += 1
        response = await http_client.get(status_url, headers=headers, timeout=timeout_seconds)
        log_status("MINIMAX", f"Status poll #{attempt} for {request_id}: {response.status_code}", "INFO")

        if response.status_code == 202:
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(f"MiniMax status polling timed out for requestId={request_id}")
            await asyncio.sleep(poll_interval)
            continue

        response.raise_for_status()

        try:
            data = response.json()
        except Exception:
            raw_text = response.text
            log_status("MINIMAX", f"Status poll raw preview: {repr(raw_text[:500])}", "DEBUG")
            return raw_text

        log_status("MINIMAX", f"Status poll payload keys: {list(data.keys())[:10]}", "DEBUG")
        extracted = _extract_text_from_openai_like_payload(data)
        if extracted:
            return extracted

        # Some fulfilled payloads can wrap the actual result deeper.
        nested_candidates = (
            data.get("result"),
            data.get("response"),
            data.get("data"),
        )
        for candidate in nested_candidates:
            extracted = _extract_text_from_openai_like_payload(candidate)
            if extracted:
                return extracted

        return json.dumps(data, ensure_ascii=False)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
async def robust_gemma4_call(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 1200,
    clean_output: bool = True,
) -> str:
    """Call a local OpenAI-compatible Gemma 4 endpoint."""
    await APIRateLimiter.throttle("gemma4", 0.2)

    config = dict(MODEL_CONFIG.get("GEMMA4_INTERFACE_CONFIG", {}))
    base_url = config.get("BASE_URL") or os.getenv("GEMMA4_BASE_URL", "")
    api_key = config.get("API_KEY") or os.getenv("GEMMA4_API_KEY", "")
    model_name = config.get("MODEL") or MODEL_CONFIG.get("GEMMA4_MODEL", "gemma-2-4b-it")

    if not base_url:
        raise ValueError("GEMMA4 base URL is not configured.")

    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("chat") and not endpoint.endswith("completions") and not endpoint.endswith("generate"):
        endpoint = f"{endpoint}/api/v1/chat"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # As per LM Studio curl requirement mapping logic
    payload = {
        "model": model_name,
        "input": prompt
    }
    if system_prompt.strip():
        payload["system_prompt"] = system_prompt
    else:
        payload["system_prompt"] = "You are a helpful assistant."

    # If calling the standard OpenAI compatibility endpoint, reformat as messages array
    if endpoint.endswith("/chat/completions"):
        payload["messages"] = [{"role": "system", "content": payload.pop("system_prompt")}, {"role": "user", "content": payload.pop("input")}]
        payload["temperature"] = 0.7
        payload["max_tokens"] = max_tokens

    # print(f"\n[GEMMA4_DEBUG] Input Payload:\n{json.dumps(payload, indent=2, ensure_ascii=False)}", flush=True)

    client = APIClients.get_http()

    async with ConcurrencyManager.GEMMA4_SEM:
        response = await client.post(endpoint, headers=headers, json=payload, timeout=120.0)
    response.raise_for_status()
    data = response.json()
    # print(f"\n[GEMMA4_DEBUG] Output Data:\n{json.dumps(data, indent=2, ensure_ascii=False)}", flush=True)

    # Safely extract the text depending on LM Studio's return variant format (output vs choices)
    text = ""
    if "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
        text = _extract_message_text(data["choices"][0].get("message", {}).get("content"))
    elif "output" in data and isinstance(data["output"], list) and len(data["output"]) > 0:
        text = str(data["output"][0].get("content", ""))
    elif "content" in data:
        text = str(data["content"])

    if not text:
        raise RuntimeError(f"GEMMA4 returned no valid text choices: {data}")

    log_status("GEMMA4", "Local Gemma4 response successful.", "SUCCESS")
    return run_clean_pipeline(text) if clean_output else text

# =====================================================================
# GLOBAL IMAGE GENERATOR & YOUTUBE UPLOAD
# =====================================================================

# [Function]: Base logic to run a RunningHub workflow and poll for results
async def _run_runninghub_workflow(workflow_id: str, node_info_list: list, img_path: str, log_tag: str) -> bool:
    """Submit a RunningHub workflow job, poll until completion, and download the result image.
    Returns True on success, False on any failure or timeout.
    """
    if os.path.exists(img_path): return True
    
    # Dynamically refresh API key to support .env files loaded after module import
    api_key = os.getenv("RUNNINGHUB_API_KEY") or RUNNINGHUB_CONFIG.get("KEY")
    if not api_key:
        log_status(log_tag, "RUNNINGHUB_API_KEY not found in environment or config", "ERROR")
        return False
    RUNNINGHUB_CONFIG["KEY"] = api_key
    
    client = APIClients.get_http()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"nodeInfoList": node_info_list}
    base_url = "https://www.runninghub.ai/openapi/v2"
    task_id = None
    
    for attempt in range(15):
        SystemController.check_stop_signal()
        try:
            await APIRateLimiter.throttle("runninghub", 5.0)
            resp = await client.post(f"{base_url}/run/workflow/{workflow_id}", headers=headers, json=payload)
            r_json = resp.json()
            if str(r_json.get("errorCode")) == "421": 
                log_status(log_tag, "Error code 421: Retrying after 5s...", "WARN")
                await asyncio.sleep(5)
                continue

            # Robust Task ID extraction: check both root level and nested 'data' field
            task_id = r_json.get("taskId")
            if not task_id and isinstance(r_json.get("data"), dict):
                task_id = r_json.get("data").get("taskId")
            
            if task_id: 
                log_status(log_tag, f"Task Created: {task_id}", "OK")
                RunningHubManager.add_task(task_id) # Record job reference to lifecycle manager
                break
            else:
                # [DEBUG]: Print full response if task creation failed to identify parameter mismatches
                log_status(log_tag, f"API Response Error: {r_json}", "ERROR")
        except Exception as e:
            log_status(log_tag, f"Exception on attempt {attempt + 1}: {repr(e)}", "ERROR")
            await asyncio.sleep(5)
            
    if not task_id: 
        log_status(log_tag, "Failed to obtain Task ID.", "ERROR")
        return False
    
    # Bulletproof defer: ensures removal irrespective of async crashes or KeyboardInterrupts
    try:
        t0 = time.time()
        while time.time() - t0 < RUNNINGHUB_TIMEOUT_SEC:
            # [Polling Kill Switch]: Continually verify stop.txt absence within sleep intervals
            SystemController.check_stop_signal()
            
            try:
                q_resp = await client.post(f"{base_url}/query", headers=headers, json={"taskId": task_id})
                q_json = q_resp.json()
                status = q_json.get("status", "").upper()
                
                if status == "SUCCESS":
                    # [Function]: Fail-safe extractor: Regex enforcing raw CDN picture URL isolation across garbled payloads
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
                        RunningHubManager.remove_task(task_id) # Deregister upon completion success
                        return True
                    else:
                        RunningHubManager.remove_task(task_id) # Deregister via soft-fails
                        return False
                elif status == "FAILED": 
                    log_status(log_tag, f"Task Failed, response: {q_json}", "ERROR")
                    RunningHubManager.remove_task(task_id) # Deregister via soft-fails
                    return False
            except Exception as e: 
                log_status(log_tag, f"Exception during polling: {repr(e)}", "DEBUG")
            await asyncio.sleep(API_POLL_INTERVAL_SEC)
            
        log_status(log_tag, f"Timed out after {RUNNINGHUB_TIMEOUT_SEC}s.", "ERROR")
        RunningHubManager.remove_task(task_id) # Deregister via soft-fails
        return False
    finally:
        # Triggered when coroutine forcefully terminated (CancelledError/KeyboardInterrupt) resolving hung states
        if RunningHubManager.has_task(task_id):
            RunningHubManager.cancel_task(task_id)

# [Function]: Asynchronously ping cloud generator engine for standard T2I
async def generate_runninghub_image(prompt: str, img_path: str, log_tag: str = "IMAGE") -> bool:
    """Generate an image via the standard RunningHub T2I workflow and save it to img_path."""
    node_info_list = [{"nodeId": RUNNINGHUB_CONFIG["T2I_NODE"], "fieldName": "value", "fieldValue": prompt}]
    return await _run_runninghub_workflow(RUNNINGHUB_CONFIG['WF_T2I'], node_info_list, img_path, log_tag)

# [Function]: Enhanced image generation using ZImage workflow with randomized parameters
async def generate_runninghub_image_with_zimage(prompt: str, img_path: str, log_tag: str = "IMAGE_Z") -> bool:
    """
    [Diversity Optimization]: Dynamically randomizes Seed, LoRA Strength, Steps, and CFG 
    within safe boundaries defined in WF_ZIMAGE_NODES to ensure unique visual outputs.
    """
    # 1. Core randomization strategy (see WF_ZIMAGE_NODES comments)
    seed = random.randint(1, 10**16)
    steps = random.randint(8, 12)
    cfg = round(random.uniform(1.0, 1.5), 1)
    lora_strength = round(random.uniform(0.8, 1.2), 2)
    
    # 2. Preset parameters and negative prompt
    negative_prompt = "(average face, generic features, standard look:1.2), (3d render, plastic skin:1.2)"
    width, height = 1920, 1080  # Default landscape resolution
    
    # 3. Build workflow node payload
    node_info_list = [
        {"nodeId": WF_ZIMAGE_NODES["PROMPT"], "fieldName": "prompt", "fieldValue": prompt},
        {"nodeId": WF_ZIMAGE_NODES["SEED"], "fieldName": "seed", "fieldValue": seed},
        {"nodeId": WF_ZIMAGE_NODES["SIZE"], "fieldName": "width", "fieldValue": width},
        {"nodeId": WF_ZIMAGE_NODES["SIZE"], "fieldName": "height", "fieldValue": height},
        {"nodeId": WF_ZIMAGE_NODES["LORA_STRENGTH"], "fieldName": "strength_model", "fieldValue": lora_strength},
        {"nodeId": WF_ZIMAGE_NODES["STEPS"], "fieldName": "steps", "fieldValue": steps},
        {"nodeId": WF_ZIMAGE_NODES["CFG"], "fieldName": "cfg", "fieldValue": cfg},
    ]
    
    return await _run_runninghub_workflow(RUNNINGHUB_CONFIG['WF_ZIMAGE'], node_info_list, img_path, log_tag)

# [Function]: Procure and locally cache OAuth2 authenticated YouTube API credentials
def get_authenticated_service():
    """Load or refresh YouTube OAuth2 credentials and return an authenticated YouTube API service object."""
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

# [Function]: Pack and dispatch completely rendered assets orchestrating direct YouTube deployments
def upload_video_to_youtube(file_path: str, title: str, description: str, tags: list):
    """Upload a video file to YouTube as a private video using resumable upload."""
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
