# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches, too-many-instance-attributes, missing-docstring
"""
Content OS - Universal Channel Runner V143 (Dynamic High-Contrast Typography Edition)
Refactored: Split SKIP_QA_GUARDRAIL into language-specific flags (EN/CN).
Optimized: Enhanced `_generate_cinematic_prompt_single` to strictly partition character features for Close-up/Macro shots, preventing terrifying AI limb hallucination.
Optimized: Revamped `YOUTUBE_METADATA` prompts to enforce short, semantic 'Phrases' (around 3-5 words) rather than abstract count limits for better hook impact.
Optimized: Refactored `add_text_to_thumbnail` to dynamically calculate local background luminance and automatically choose high-contrast text colors.
Fixed: Enforced strict 1280x720 resizing in `add_text_to_thumbnail` to meet YouTube constraints natively.
Feature: Global prefix safety constraint for all image prompts and ONLY_GENERATE_IMAGE rapid testing mode.
Feature: Absolute Idempotency in Context Reuse - 0_context.json strictly overrides CSV logic to lock story, anchor, and randomized fonts during any reuse.
"""

import os
import sys
import subprocess
import asyncio
import json
import csv
import random
import re
import argparse
import importlib.util
import shutil
import textwrap
import _thread
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageStat

from core_engine import (
    validate_environment, setup_workspace, safe_json_loads, save_json_formatted,
    record_execution, log_retry_attempt, ConcurrencyManager, APIClients, 
    MediaSegment, robust_gemini_call, robust_openai_call, robust_deepseek_call,
    robust_oss_call, robust_kimi_call, generate_runninghub_image, upload_video_to_youtube, MODEL_CONFIG
)
from tenacity import retry, stop_after_attempt, wait_exponential

from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, LowShelfFilter, HighShelfFilter
from pedalboard.io import AudioFile
import edge_tts
from core_engine import robust_edge_tts_call, robust_image_call, apply_ssml_pauses, PEDALBOARD_CONFIG

# =====================================================================
# 本地强化日志管理器 (持久化落盘)
# =====================================================================
class LoggerManager:
    """【功能简介】：在后台静默收集终端打印日志，并在工作目录创建后，全量持久化写入 pipeline_master.log"""
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

def log_status(stage: str, msg: str, status: str = "INFO"):
    """【功能简介】：标准化日志格式刷，带颜色与对齐输出，并自动引流到 LoggerManager"""
    time_str = datetime.now().strftime('%H:%M:%S')
    date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    raw_log = f"[{date_str}] [{stage:<10}] [{status:<5}] {msg}"
    
    color_map = {
        "INFO": "\033[94m",     
        "OK": "\033[92m",       
        "SUCCESS": "\033[92m",  
        "WARN": "\033[93m",     
        "ERROR": "\033[91m",    
        "CRITICAL": "\033[91m", 
        "DEBUG": "\033[90m"     
    }
    c_code = color_map.get(status, "\033[0m")
    print(f"{c_code}[{time_str}] [{stage:<10}] [{status:<5}] {msg}\033[0m", flush=True)
    
    if LoggerManager.log_file_path:
        try:
            with open(LoggerManager.log_file_path, "a", encoding="utf-8") as f:
                f.write(raw_log + "\n")
        except Exception:
            pass
    else:
        LoggerManager._buffer.append(raw_log + "\n")

# =====================================================================
# 工业级优雅停机 & 子进程 PID 管理
# =====================================================================

ACTIVE_FFMPEG_PROCS = set()

def safe_subprocess_run(cmd):
    """【功能简介】：将 FFmpeg 进程注册到全局池，防止主程序被杀后沦为孤儿进程吃满显卡资源"""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ACTIVE_FFMPEG_PROCS.add(proc)
    try:
        out, err = proc.communicate()
        if proc.returncode != 0:
            log_status("FFMPEG", f"Process returned non-zero exit status {proc.returncode}", "ERROR")
            raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
        return out, err
    except Exception as e:
        log_status("FFMPEG", f"Process communication failed or interrupted: {e}", "ERROR")
        proc.terminate() 
        raise e
    finally:
        if proc in ACTIVE_FFMPEG_PROCS:
            ACTIVE_FFMPEG_PROCS.remove(proc)

async def stop_file_watcher():
    """【功能简介】：全局急停探针，监听目录下是否出现 stop.txt，用于优雅终止死循环"""
    while True:
        if os.path.exists("stop.txt"):
            log_status("SYSTEM", "🛑 检测到 stop.txt 外部停止信号! 正在触发全线优雅急停...", "CRITICAL")
            try: os.remove("stop.txt")
            except: pass
            _thread.interrupt_main() 
            break
        await asyncio.sleep(1)

# =====================================================================
# 0. THUMBNAIL TYPOGRAPHY ENGINE (封面排版引擎)
# =====================================================================

def wrap_chinese_text(text, max_len=8):
    """处理中文长标题换行"""
    lines = []
    current = ""
    for char in text:
        current += char
        if len(current) >= max_len or char in "，。！？：；":
            lines.append(current)
            current = ""
    if current: lines.append(current)
    return "\n".join(lines)

def get_best_font_size(draw, text, font_path, img_w, img_h, max_font_percentage=0.18, align="right"):
    """动态计算在图片上渲染文字的最佳字体大小"""
    start_size = int(img_h * max_font_percentage)
    min_size = int(img_h * 0.05)
    
    if start_size <= min_size: start_size = min_size + 2 
        
    for size in range(start_size, min_size, -2):
        try: font = ImageFont.truetype(font_path, size)
        except IOError: 
            log_status("FONT", f"IOError loading font size {size}, returning default.", "WARN")
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
            
    log_status("FONT", "Could not find optimal font size, falling back to minimum.", "WARN")
    try: return ImageFont.truetype(font_path, int(img_h * 0.05))
    except IOError: return ImageFont.load_default()

def add_text_to_thumbnail(image_path: str, output_path: str, full_title: str, align: str = "right", font_path: str = "msyhbd.ttc"):
    """【功能简介】：基于 PIL 动态探测文字下方背景亮度，自动实现高反差排版与专业阴影。结尾强制进行 YouTube 1280x720 缩放。"""
    try:
        short_title = full_title.split(":")[0].strip() if ":" in full_title else full_title
        short_title = short_title.split("：")[0].strip() 
        
        img = Image.open(image_path)
        if img.mode != 'RGB': img_rgb = img.convert('RGB')
        else: img_rgb = img
            
        draw = ImageDraw.Draw(img)
        img_w, img_h = img.size

        is_cn = any('\u4e00' <= c <= '\u9fff' for c in short_title)
        max_font_percentage = 0.18 
        
        if is_cn:
            wrapped_text = wrap_chinese_text(short_title)
        else:
            wrapped_text = textwrap.fill(short_title, width=15)
            num_lines = len(wrapped_text.split("\n"))
            base_max_percentage = 0.15 if align == "top" else 0.18
            
            if num_lines >= 4: max_font_percentage = 0.08 
            elif num_lines == 3: max_font_percentage = 0.12 
            elif num_lines <= 2: max_font_percentage = base_max_percentage 

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
        
        threshold = 128

        if luminance > threshold:
            text_color = "#857204" 
            is_light_bg = True
            log_status("TYPO", f"Light background detected (Lum: {int(luminance)}). Choosing dark text.", "DEBUG")
        else:
            text_color = "#FFE24A" 
            is_light_bg = False
            log_status("TYPO", f"Dark background detected (Lum: {int(luminance)}). Choosing light text.", "DEBUG")

        shadow_fill = (0, 0, 0, 255) if not is_light_bg else (255, 255, 255, 200)
        shadow_offset = 2 if font.size < 60 else 3 
        
        if not is_light_bg:
            draw.text((x + shadow_offset, y + shadow_offset), wrapped_text, font=font, fill=shadow_fill)
        else:
            for dx in range(-shadow_offset, shadow_offset + 1, 1):
                for dy in range(-shadow_offset, shadow_offset + 1, 1):
                    if dx == 0 and dy == 0: continue
                    draw.text((x + dx, y + dy), wrapped_text, font=font, fill=shadow_fill)

        draw.text((x, y), wrapped_text, font=font, fill=text_color)
        
        img = img.resize((1280, 720), Image.Resampling.LANCZOS)
        
        img.save(output_path)
        log_status("SEO_THUMB", f"High-contrast text generated perfectly: {output_path}", "OK")
        return True
    except Exception as e:
        log_status("SEO_THUMB", f"Failed to add high-contrast text to thumbnail: {e}", "ERROR")
        return False

# =====================================================================
# 1. DYNAMIC CONFIGURATION LOADER
# =====================================================================

def load_python_config(file_path: str):
    """【功能简介】：动态反射加载传入的不同 app_* Python 业务模板，实现频道隔离"""
    try:
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        cfg_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = cfg_module
        spec.loader.exec_module(cfg_module)
        log_status("CONFIG", f"Successfully loaded Python config: {file_path}", "OK")
        
        if hasattr(cfg_module, "model_settings"):
            if "voice_en" in cfg_module.model_settings: MODEL_CONFIG["VOICE_EN"] = cfg_module.model_settings["voice_en"]
            if "voice_cn" in cfg_module.model_settings: MODEL_CONFIG["VOICE_CN"] = cfg_module.model_settings["voice_cn"]
        return cfg_module
    except Exception as e:
        log_status("CONFIG", f"Failed to load Python config {file_path}: {e}", "CRITICAL")
        sys.exit(1)

# =====================================================================
# 2. BUSINESS WRAPPERS
# =====================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True, after=log_retry_attempt)
async def robust_openai_metadata_call(prompt: str, schema_model) -> dict:
    """【功能简介】：专门用于提取结构化 SEO YouTube 元数据的 OpenAI 独立调用"""
    try:
        res = await APIClients.get_openai().beta.chat.completions.parse(
            model=MODEL_CONFIG["OPENAI_MODEL"], messages=[{"role": "user", "content": prompt}], response_format=schema_model
        )
        log_status("SEO", "OpenAI metadata parsed successfully.", "OK")
        return res.choices[0].message.parsed.model_dump()
    except Exception as e:
        log_status("SEO", f"OpenAI metadata call failed: {e}", "ERROR")
        raise e

class LibraryManager:
    """【功能简介】：从 CSV 题库中读取并智能选取内容（支持顺序提取或随机提取）"""
    matrix = []
    @classmethod
    def load_from_csv(cls, filepath: str):
        if not os.path.exists(filepath): 
            log_status("LIBRARY", f"CSV not found at {filepath}.", "WARN")
            return
        try:
            with open(filepath, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [field.strip().lower() for field in reader.fieldnames or []]
                cls.matrix = [row for row in reader if any(row.values())]
                log_status("LIBRARY", f"Matrix Director loaded {len(cls.matrix)} rows.", "OK")
        except Exception as e:
            log_status("LIBRARY", f"Failed to parse CSV: {e}", "ERROR")

    @classmethod
    def get_target_index(cls, record_csv: str, mode: str) -> int:
        total = len(cls.matrix)
        if total == 0: 
            log_status("LIBRARY", "Matrix is empty, returning index 0.", "WARN")
            return 0
            
        if mode.upper() == "SEQUENCE":
            if not os.path.exists(record_csv): 
                log_status("LIBRARY", "Record CSV not found, starting sequence at 0.", "INFO")
                return 0
            try:
                with open(record_csv, mode='r', encoding='utf-8') as f:
                    rows = list(csv.reader(f))
                    if len(rows) <= 1: return 0 
                    last_story_title = ""
                    for row in reversed(rows):
                        if "SUCCESS" in row:
                            last_story_title = row[-1].strip()
                            break
                    if last_story_title:
                        for i, item in enumerate(cls.matrix):
                            if item.get('story', "").strip() == last_story_title:
                                log_status("LIBRARY", f"Found previous sequence story, targeting index {(i + 1) % total}.", "OK")
                                return (i + 1) % total
                return 0
            except Exception as e:
                log_status("SYSTEM", f"Failed to trace story from record.csv: {e}", "WARN")
                return 0
                
        rand_idx = random.randint(0, total - 1)
        log_status("LIBRARY", f"Random mode selected, targeting index {rand_idx}.", "INFO")
        return rand_idx

# =====================================================================
# 3. STORY PIPELINE (BATCH-DAG PIPELINE)
# =====================================================================

class StoryPipeline:
    def __init__(self, folder: str, cfg): 
        self.folder = folder
        self.cfg = cfg
        self.prompts = cfg.PROMPT_CONFIG
        self.context = {} 
        self.segment_metadata = {} 
        self.flattened_metadata = [] 

    async def run_outline(self) -> tuple[list, dict]:
        """【功能简介】：调用 Gemini 生成长故事的结构化大纲和世界观术语表"""
        selected_blueprint = random.choice(self.cfg.OUTLINE_BLUEPRINTS)
        blueprint_name = selected_blueprint.strip().split('\n')[0]
        log_status("STORY", f"Injecting Blueprint: {blueprint_name}", "INFO")
        
        try:
            prompt = self.prompts["GEMINI_OUTLINE"].format(blueprint=selected_blueprint, **self.context)
            res = await robust_gemini_call(prompt, max_tokens=4000)
            data = safe_json_loads(res)
            outline, glossary = data.get("outline", []), data.get("glossary", {})

            if glossary:
                char_body = glossary.get("char_body_and_apparel", "")
                char_face = glossary.get("char_facial_details", "")
                
                if not char_body and "character" in glossary:
                    char_body = glossary.get("character", "")
                
                self.context["char_body_and_apparel"] = char_body
                self.context["char_facial_details"] = char_face
                
                combined_char = ""
                if char_body: combined_char += char_body
                if char_face: combined_char += f", {char_face}"
                self.context["character"] = combined_char

                if combined_char:
                    log_status("STORY", f"Dynamic Character Loaded: {combined_char[:50]}...", "INFO")
            
            if len(outline) >= 8:
                save_json_formatted(os.path.join(self.folder, "1_outlines.json"), outline)
                save_json_formatted(os.path.join(self.folder, "1_glossary.json"), glossary)
                log_status("STORY", "Outline and glossary successfully generated and saved.", "OK")
                return outline, glossary
            else:
                log_status("STORY", f"Outline generation failed: Expected >= 8 paragraphs. Raw: {res}", "ERROR")
                return [], {}
        except Exception as e: 
            log_status("STORY", f"Outline generation failed with exception: {repr(e)}", "ERROR")
            return [], {}

    async def run_outline_kimi(self) -> tuple[list, dict]:
        """【功能简介】：调用 Kimi 作为备用通道生成长故事的结构化大纲和世界观术语表"""
        selected_blueprint = random.choice(self.cfg.OUTLINE_BLUEPRINTS)
        blueprint_name = selected_blueprint.strip().split('\n')[0]
        log_status("STORY", f"Injecting Blueprint (Kimi Fallback): {blueprint_name}", "INFO")
        
        try:
            prompt = self.prompts["KIMI_OUTLINE"].format(blueprint=selected_blueprint, **self.context)
            res = await robust_kimi_call(prompt, max_tokens=4000)
            data = safe_json_loads(res)
            outline, glossary = data.get("outline", []), data.get("glossary", {})

            if glossary:
                char_body = glossary.get("char_body_and_apparel", "")
                char_face = glossary.get("char_facial_details", "")
                
                if not char_body and "character" in glossary:
                    char_body = glossary.get("character", "")
                
                self.context["char_body_and_apparel"] = char_body
                self.context["char_facial_details"] = char_face
                
                combined_char = ""
                if char_body: combined_char += char_body
                if char_face: combined_char += f", {char_face}"
                self.context["character"] = combined_char

                if combined_char:
                    log_status("STORY", f"Dynamic Character Loaded (Kimi): {combined_char[:50]}...", "INFO")
            
            if len(outline) >= 8:
                save_json_formatted(os.path.join(self.folder, "1_outlines.json"), outline)
                save_json_formatted(os.path.join(self.folder, "1_glossary.json"), glossary)
                log_status("STORY", "Outline and glossary successfully generated and saved by Kimi.", "OK")
                return outline, glossary
            else:
                log_status("STORY", f"Kimi Outline generation failed: Expected >= 8 paragraphs. Raw: {res}", "ERROR")
                return [], {}
        except Exception as e: 
            log_status("STORY", f"Kimi Outline generation failed with exception: {repr(e)}", "ERROR")
            return [], {}

    async def _expand_single(self, outline: str, idx: int) -> list:
        """【功能简介】：利用 OpenAI 将简短的大纲节点扩写为长段落，并提取 metadata 供后续使用"""
        max_attempts = 2
        for attempt in range(max_attempts):
            async with ConcurrencyManager.OPENAI_SEM:
                try: 
                    prompt = self.prompts["OPENAI_EXPAND"].format(outline=outline, character=self.context.get('character', ''))
                    parsed_obj = await robust_openai_call(prompt, self.cfg.ExpandedScene)
                    raw_dict = parsed_obj.model_dump() if hasattr(parsed_obj, "model_dump") else vars(parsed_obj)
                    
                    chunks = []
                    meta_chunks = []
                    for key, val in raw_dict.items():
                        if isinstance(val, dict) and "narrative_text" in val:
                            text_val = val.get("narrative_text", "")
                            if len(text_val) > 20:
                                clean_val = re.sub(r'\s{2,}', ' ', re.sub(r'[\r\n]+', ' ', text_val)).strip()
                                chunks.append(clean_val)
                                meta_chunks.append(val)
                        elif isinstance(val, str) and len(val) > 20:
                            clean_val = re.sub(r'\s{2,}', ' ', re.sub(r'[\r\n]+', ' ', val)).strip()
                            chunks.append(clean_val)
                            meta_chunks.append({})
                    
                    full_text = " ".join(chunks)
                    word_count = len(full_text.split())
                    
                    if word_count < 350 and attempt < max_attempts - 1:
                        log_status("OPENAI", f"Outline {idx+1} word count ({word_count}) < 350. Retrying...", "WARN")
                        continue
                    
                    self.segment_metadata[idx] = meta_chunks
                    log_status("OPENAI", f"Expanded Outline {idx+1} safely. Segments generated: {len(chunks)}", "OK")
                    return chunks
                except Exception as e:
                    log_status("OPENAI", f"Outline {idx+1} expansion failed on attempt {attempt+1}: {repr(e)}", "ERROR")
                    if attempt == max_attempts - 1: return []
        return []

    async def run_expansion_en(self, outlines: list) -> list:
        log_status("STORY", "Expanding outlines concurrently...", "INFO")
        results = await asyncio.gather(*[self._expand_single(ol, i) for i, ol in enumerate(outlines)], return_exceptions=True)
        
        en_scripts_flattened = []
        for r in results:
            if isinstance(r, list): en_scripts_flattened.extend(r)
            
        flattened_meta = []
        for k in sorted(self.segment_metadata.keys()):
            flattened_meta.extend(self.segment_metadata[k])
            
        self.flattened_metadata = flattened_meta
        save_json_formatted(os.path.join(self.folder, "2_metadata.json"), flattened_meta)
        save_json_formatted(os.path.join(self.folder, "2_en_scripts.json"), en_scripts_flattened)
        return en_scripts_flattened

    async def _qa_guardrail(self, text_list: list, language: str) -> bool:
        """【功能简介】：LLM-as-a-Judge 语义级护栏。"""
        if not text_list: return False
        
        if getattr(self.cfg, f"SKIP_QA_GUARDRAIL_{language}", False):
            return True

        sample_rate = getattr(self.cfg, "QA_SAMPLE_RATE", 0.5)
        if random.random() > sample_rate:
            log_status("QA_JUDGE", f"[{language}] Guardrail skipped (Sampling pass).", "DEBUG")
            return True

        prompt_template = self.prompts.get(f"QUALITY_JUDGE_{language}")
        if not prompt_template:
            log_status("QA_JUDGE", f"Missing prompt template for QUALITY_JUDGE_{language}. Bypassing guardrail.", "WARN")
            return True

        combined_text = "\n\n".join(text_list)
        prompt = prompt_template.format(text=combined_text)

        try:
            res = await robust_oss_call(prompt, max_tokens=200, clean_output=True)
            data = json.loads(res.replace("```json", "").replace("```", "").strip())
            
            passed = data.get("pass", False)
            reason = data.get("reason", "No reason provided")
            
            if passed:
                log_status("QA_JUDGE", f"{language} text passed semantic guardrails.", "OK")
                return True
            else:
                log_status("QA_JUDGE", f"{language} text FAILED guardrails. Reason: {reason}", "WARN")
                log_status("QA_JUDGE", f"Origin {language} text: {combined_text}", "WARN")
                return False
                
        except Exception as e:
            log_status("QA_JUDGE", f"Guardrail evaluation failed/timed out: {e}. Defaulting to bypass.", "WARN")
            return True

    async def _localize_chunk_cn(self, batch_list: list, glossary_str: str, batch_idx: int) -> list:
        """【功能简介】：调用 DeepSeek 进行极高品质的中文散文翻译，内置防丢失段落及 QA Guardrail"""
        if not batch_list: return []
        combined_text = "\n\n---\n\n".join(batch_list)
        base_prompt = self.prompts["DEEPSEEK_REWRITE"].format(english_text=combined_text, glossary=glossary_str)
        batch_instruction = "\n\nCRITICAL RULE: The input contains multiple text blocks separated by '---'. You MUST return the EXACT same number of translated blocks, separated by '---'. Do not merge them! 返回的每段翻译必须用 '---' 严格隔开，绝对不能包含前言或结语废话！"
        final_prompt = base_prompt + batch_instruction
        
        max_retries = 3
        for attempt in range(max_retries):
            async with ConcurrencyManager.DEEPSEEK_SEM:
                try:
                    if attempt > 0: log_status("DEEPSEEK", f"Retrying Translation Batch {batch_idx+1}...", "WARN")
                    
                    res = await robust_deepseek_call(final_prompt, max_tokens=2500, clean_output=False)
                    raw_splits = re.split(r'-{3,}', res)
                    split_res = []
                    for p in raw_splits:
                        p_strip = p.strip()
                        if len(p_strip) > 15: 
                            clean_p = re.sub(r'[\r\n]+', '', p_strip)
                            split_res.append(clean_p)
                    
                    if len(split_res) == 1 and len(batch_list) > 1:
                        log_status("DEEPSEEK", f"Delimiter '---' missing in Batch {batch_idx+1}. Activating smart newline fallback...", "WARN")
                        fallback_splits = re.split(r'\n\s*\n', res.strip())
                        fallback_res = []
                        for p in fallback_splits:
                            p_strip = p.strip()
                            if len(p_strip) > 15:
                                clean_p = re.sub(r'[\r\n]+', '', p_strip)
                                fallback_res.append(clean_p)
                        if len(fallback_res) == len(batch_list):
                            split_res = fallback_res
                            log_status("DEEPSEEK", f"Smart fallback successful for Batch {batch_idx+1}.", "SUCCESS")
                    
                    if len(split_res) == len(batch_list):
                        qa_passed = await self._qa_guardrail(split_res, "CN")
                        if not qa_passed:
                            log_status("DEEPSEEK", f"Batch {batch_idx+1} rejected by QA Guardrail. Retrying translation.", "WARN")
                            if attempt == max_retries - 1:
                                raise ValueError("QA Guardrail continuously failed.")
                            continue 
                            
                        log_status("DEEPSEEK", f"Translation Batch {batch_idx+1} completed perfectly.", "SUCCESS")
                        return split_res
                    else:
                        log_status("DEEPSEEK", f"Batch {batch_idx+1} mismatch (got {len(split_res)}, expected {len(batch_list)}).", "WARN")
                        if attempt == max_retries - 1:
                            while len(split_res) < len(batch_list):
                                split_res.append(split_res[-1] if split_res else "Fallback Translation.")
                            return split_res[:len(batch_list)]
                except Exception as e:
                    error_str = str(e)
                    # 【核心拦截】：如果是 SiliconFlow/DeepSeek 余额不足（错误码 30001 或 403 包含 balance 关键字），直接物理掐断
                    if "30001" in error_str or "insufficient balance" in error_str.lower():
                        log_status("DEEPSEEK", "FATAL: DeepSeek account balance is insufficient! Stopping all operations immediately.", "CRITICAL")
                        sys.exit(1)
                        
                    log_status("DEEPSEEK", f"Translation Batch {batch_idx+1} failed: {e}", "ERROR")
                    if attempt == max_retries - 1: return [""] * len(batch_list)
        return [""] * len(batch_list)

    async def _rewrite_chunk(self, batch_list: list, language: str, batch_idx: int) -> list:
        """【功能简介】：OSS 润色与重写模块。内置极强的 Token 崩塌防结巴探针及 QA Guardrail"""
        if not batch_list: return batch_list
        prompt_template = self.prompts.get(f"REWRITE_PROMPT_{language}")
        if not prompt_template: 
            log_status("REWRITE", f"Missing prompt template for {language}.", "WARN")
            return batch_list
            
        combined_text = "\n\n---\n\n".join(batch_list)
        prompt = prompt_template.format(text=combined_text)
        
        max_retries = 3
        for attempt in range(max_retries):
            async with ConcurrencyManager.OSS_SEM:
                try:
                    if attempt > 0: log_status("REWRITE", f"Retrying Batch {batch_idx+1} ({language})...", "WARN")
                        
                    res = await robust_oss_call(prompt, max_tokens=2500, clean_output=False)
                    raw_splits = re.split(r'-{3,}', res)
                    split_res = []
                    for p in raw_splits:
                        p_strip = p.strip()
                        if len(p_strip) > 15: 
                            replace_char = " " if language == "EN" else ""
                            clean_p = re.sub(r'[\r\n]+', replace_char, p_strip).strip()
                            clean_p = re.sub(r'\s{2,}', ' ', clean_p)
                            
                            stripped_p = clean_p.replace(" ", "")
                            if re.search(r'(.+?)\1{8,}', stripped_p) or (len(stripped_p) > 100 and len(set(stripped_p)) < 25):
                                log_status("REWRITE", f"Token Collapse Detected (Stuttering/Gibberish) in Batch {batch_idx+1}. Rejecting.", "ERROR")
                                raise ValueError("LLM Repetition Collapse")
                                
                            split_res.append(clean_p)

                    if len(split_res) == 1 and len(batch_list) > 1:
                        log_status("REWRITE", f"Delimiter '---' missing in Batch {batch_idx+1} ({language}). Activating smart newline fallback...", "WARN")
                        fallback_splits = re.split(r'\n\s*\n', res.strip())
                        fallback_res = []
                        for p in fallback_splits:
                            p_strip = p.strip()
                            if len(p_strip) > 15:
                                replace_char = " " if language == "EN" else ""
                                clean_p = re.sub(r'[\r\n]+', replace_char, p_strip).strip()
                                clean_p = re.sub(r'\s{2,}', ' ', clean_p)
                                
                                stripped_p = clean_p.replace(" ", "")
                                if re.search(r'(.+?)\1{8,}', stripped_p) or (len(stripped_p) > 100 and len(set(stripped_p)) < 25):
                                    log_status("REWRITE", f"Token Collapse Detected in Fallback Batch {batch_idx+1}. Rejecting.", "ERROR")
                                    raise ValueError("LLM Repetition Collapse")

                                fallback_res.append(clean_p)
                        if len(fallback_res) == len(batch_list):
                            split_res = fallback_res
                            log_status("REWRITE", f"Smart fallback successful for Batch {batch_idx+1} ({language}).", "SUCCESS")
                    
                    if len(split_res) == len(batch_list):
                        qa_passed = await self._qa_guardrail(split_res, language)
                        if not qa_passed:
                            log_status("REWRITE", f"Batch {batch_idx+1} rejected by QA Guardrail. Retrying rewrite.", "WARN")
                            if attempt == max_retries - 1:
                                raise ValueError("QA Guardrail continuously failed.")
                            continue
                            
                        log_status("REWRITE", f"Batch {batch_idx+1} ({language}) rewritten perfectly.", "SUCCESS")
                        return split_res
                    else:
                        log_status("REWRITE", f"Batch {batch_idx+1} ({language}) mismatch (got {len(split_res)}).", "WARN")
                        if attempt == max_retries - 1: return [] 
                except Exception as e:
                    log_status("REWRITE", f"Failed rewrite Batch {batch_idx+1} ({language}): {e}", "ERROR")
                    if attempt == max_retries - 1: return []
        return []

    async def _generate_cinematic_prompt_single(self, text: str, idx: int) -> str:
        """【功能简介】：利用文本语义和元数据动态生成电影级生图提示词，支持降本免费生图模式 (USE_IMAGE_TEMPLATE)"""
        if not text:
            log_status("IMAGE_PROMPT", "Text is empty. Exiting program to avoid Fallback scene.", "CRITICAL")
            sys.exit(1)
        
        # 【全局最强护栏】：强制置于提示词开头，确保模型第一时间读取核心单人约束
        safety_constraint = "one single person, no duplication, no multiple bodies or heads, no interaction,no extra people, accurate human anatomy."
        if getattr(self.cfg, "USE_IMAGE_TEMPLATE", False):
            try:
                if not hasattr(self, "flattened_metadata") or not self.flattened_metadata:
                    self.flattened_metadata = []
                    for k in sorted(self.segment_metadata.keys()):
                        self.flattened_metadata.extend(self.segment_metadata[k])
                
                meta = {}
                if hasattr(self, "flattened_metadata") and idx < len(self.flattened_metadata):
                    meta = self.flattened_metadata[idx] or {}
                    
                scene = (meta.get("scene_desc") or "beautiful environment").strip(" .")
                action = (meta.get("action_desc") or "resting peacefully").strip(" .")
                if action: action = action[0].lower() + action[1:]

                # ==========================================
                # 1. 极近景/主观视角库 (严格限制：绝对不能出现下半身和全身动作)
                # 适用镜头: Point of View, Close-up
                # ==========================================
                action_close_up_pov = [
                    "gently touching the cheek with one hand",
                    "resting the chin lightly on one hand, elbow supported on a surface",
                    "gently holding a small object in one hand",
                    "looking softly ahead, completely still" # 补充一个最安全的无手动作
                ]

                # ==========================================
                # 2. 背影/过肩视角库 (严格限制：绝对不能出现放在大腿、胸前等被身体遮挡的动作)
                # 适用镜头: Over-the-shoulder Shot, Rear view
                # ==========================================
                action_rear_over_shoulder = [
                    "standing still, both arms resting naturally at the sides",
                    "standing slightly turned away, both hands placed in pockets",
                    "standing upright, both hands held loosely behind the back",
                    "looking out into the distance, motionless"
                ]

                # ==========================================
                # 3. 中全景/广角库 (自由区：可以展现全身舒展、坐卧行走的复杂姿态)
                # 适用镜头: Medium Full Shot, Cinematic Wide Shot
                # ==========================================
                action_wide_medium = [
                    "sitting upright, both hands folded neatly on the lap",
                    "sitting slightly leaning forward, both elbows resting on the knees, hands relaxed",
                    "sitting slightly leaning back, both hands resting on the thighs",
                    "sitting with legs together, both hands placed gently on the knees",
                    "sitting at a table, both hands resting flat on the table surface",
                    "standing with weight shifted to one leg, both arms relaxed at the sides",
                    "lying on one side, head supported by one hand, the other hand resting on the hip",
                    "walking slowly forward, both arms swinging naturally at the sides"
                ]

                # 光影库 (Lighting)
                lighting_pool = [
                    "volumetric lighting with god rays",
                    "soft moonlight casting long shadows",
                    "warm candlelight flickering",
                    "ethereal bioluminescent glow",
                    "cinematic chiaroscuro lighting"
                ]

                # 环境动态库 (Dynamics)
                dynamics_pool = [
                    "gentle breeze blowing the hair",
                    "glowing dust motes floating in the air",
                    "thick mystical fog rolling across the ground",
                    "soft rain falling outside the window",
                    "ethereal fireflies dancing in the background"
                ]

                # 镜头构图库 (Composition extras)
                composition_pool = [
                    "strong depth of field with blurred foreground elements",
                    "perfect symmetry",
                    "rule of thirds composition",
                    "wide cinematic framing"
                ]

                # ==========================================
                # 动态动作路由判断 (Action Routing)
                # ==========================================
                orig_camera = (meta.get("camera_shot") or "Medium Full Shot").strip(" .").lower()
                if "close-up" in orig_camera or "point of view" in orig_camera:
                    action = random.choice(action_close_up_pov)                    
                elif "over-the-shoulder" in orig_camera or "rear" in orig_camera:
                    action = random.choice(action_rear_over_shoulder)                    
                else:
                    # 包含了 Medium Full Shot 和 Cinematic Wide Shot
                    action = random.choice(action_wide_medium)
    
                emotion = (meta.get("emotion_desc") or "calm").strip(" .")
                anchor = self.context.get('anchor') or 'Cinematic photography, highly detailed, realistic texture'

                lighting = random.choice(lighting_pool)
                dynamic = random.choice(dynamics_pool)
                composition = random.choice(composition_pool)

                char_body = self.context.get("char_body_and_apparel", "").strip(" .") or "A person"
                char_face = self.context.get("char_facial_details", "").strip(" .") or ""
                
                if char_body == "A person" and self.context.get("character"):
                    char_body = self.context.get("character")
                    char_face = ""

                frame_num = idx + 1
                is_b_roll = (frame_num > 0 and frame_num % 5 == 0)

                if is_b_roll:
                    b_roll_strategies_pool = [
                        f"Cinematic Extreme Wide Establishing Shot. " \
                            f"Vast {scene} dominates the entire frame. {composition}" \
                            f"Atmosphere: {emotion}. Lighting: {lighting}. Dynamic: {dynamic}. "\
                            f"Character: A tiny, indistinct silhouette of {char_body} seen from far distance. No facial details. [{anchor}]",
                        f"Cinematic Medium Shot. Rear view perspective. "\
                            f"Viewed strictly from behind {char_body}, looking out at {scene}. {composition}" \
                            f"Back facing camera. Action: {action}. Atmosphere: {emotion}. Lighting: {lighting}. Dynamic: {dynamic}. "\
                            f"No face visible. [{anchor}]",
                        f"Aerial top-down shot from very high altitude, bird's-eye view. "\
                            f"Vast {scene} fills the frame. {composition}"\
                            f"A single tiny human figure, representing {char_body}, is barely visible, extremely small and indistinct, no facial or limb details. "\
                            f"Atmosphere: {emotion}. Lighting: {lighting}. Dynamic: {dynamic}. [{anchor}]"
                    ]
                    
                    b_roll_count = frame_num // 5
                    strategy_idx = (b_roll_count - 1) % len(b_roll_strategies_pool)
                    prompt = b_roll_strategies_pool[strategy_idx]
                    
                    log_status("IMAGE_PROMPT", f"Seg {idx+1} [Deterministic Safe B-Roll Type {strategy_idx+1}] Generated.", "OK")
                else:
                    lower_camera = orig_camera.lower()
                    
                    # 拦截并重构高风险的 over-the-shoulder
                    if "over-the-shoulder" in lower_camera or "over the shoulder" in lower_camera:
                        orig_camera = re.sub(r'(?i)over-the-shoulder\s*shot|over\s*the\s*shoulder\s*shot|over-the-shoulder', 'Cinematic Medium Shot. Rear view perspective', orig_camera)
                        lower_camera = orig_camera.lower()

                    is_safe_normal_shot = any(x in lower_camera for x in ["rear view", "from behind", "aerial", "birds-eye", "extreme wide"])
                    
                    if is_safe_normal_shot:
                        character_complex = f"Character: {char_body}"
                    else:
                        if char_face:
                            character_complex = f"Character: {char_body}. Complexion and Expression: {char_face}"
                        else:
                            character_complex = f"Character: {char_body}"

                    prompt = f"{orig_camera}. Environment: {scene}.{composition}. "\
                        f"Action: {action}. {dynamic}."\
                        f"Atmosphere: {emotion}. Lighting: {lighting}. "\
                        f"{character_complex}. [{anchor}]"
                    log_status("IMAGE_PROMPT", f"Seg {idx+1} [{orig_camera}] Generated.", "OK")
                
                # 强行将护栏置于提示词的最开始
                prompt = f"{safety_constraint}{prompt}"
                prompt = re.sub(r'\s+', ' ', prompt).strip()
                return prompt
                
            except Exception as e:
                log_status("IMAGE_PROMPT", f"Seg {idx+1} template gen failed: {e}", "ERROR")
                raise RuntimeError("CRITICAL_TEMPLATE_ERROR")

        prompt_context = self.context.copy()
        prompt_context["camera"] = "Cinematic Shot" 
        
        async with ConcurrencyManager.OSS_SEM:
            for attempt in range(3):
                try: 
                    prompt_template = self.prompts.get("SCENE_PROMPT_OSS") or self.prompts.get("SCENE_PROMPT_GEMINI")
                    prompt = prompt_template.format(text=text, **prompt_context)
                    raw_res = await robust_oss_call(prompt, max_tokens=300, clean_output=False)
                    match = re.search(r'<prompt>(.*?)</prompt>', raw_res, re.IGNORECASE | re.DOTALL)
                    if not match: continue
                    cleaned = match.group(1).replace("\n", " ").strip()
                    if len(cleaned) < 40: continue
                    log_status("IMAGE_PROMPT", f"Seg {idx+1} OSS Prompt Generated.", "OK")
                    return f"{safety_constraint}{cleaned} [{self.context.get('anchor', 'Masterpiece')}]"
                except Exception as e: 
                    log_status("STORY", f"Seg {idx+1} prompt gen exception: {e}", "WARN")
        return f"{safety_constraint}Cinematic Wide Shot of a beautiful serene scene. [{self.context.get('anchor', 'Masterpiece')}]"

    async def process_batch_pipeline(self, batch_idx: int, en_batch: list, glossary_str: str) -> tuple:
        en_final = en_batch
        if getattr(self.cfg, "SCRIPT_REWRITE_EN", False):
            res = await self._rewrite_chunk(en_batch, "EN", batch_idx)
            if res and len(res) == len(en_batch): en_final = res

        cn_raw = await self._localize_chunk_cn(en_final, glossary_str, batch_idx)
        if not cn_raw or len(cn_raw) != len(en_final):
            cn_raw = ["Fallback Translation."] * len(en_final)

        cn_final = cn_raw
        if getattr(self.cfg, "SCRIPT_REWRITE_CN", False):
            res = await self._rewrite_chunk(cn_raw, "CN", batch_idx)
            if res and len(res) == len(cn_raw): cn_final = res

        log_status("PIPELINE", f"Batch {batch_idx+1} Story Text Pipeline Completed.", "SUCCESS")
        return en_final, cn_raw, cn_final

    async def generate_youtube_assets(self, en_scripts: list, current_story_title: str, app_name: str) -> tuple[dict, dict, str]:
        """【功能简介】：为视频并行生成多语言的标题、描述、Tags 等 YouTube SEO 元数据，以及高度定制化的带文字覆盖的封面"""
        log_status("SEO", "Generating YouTube Metadata and Thumbnail prompt...", "INFO")
        script_summary = " ".join(en_scripts[:2]) if len(en_scripts) >= 2 else " ".join(en_scripts)
        metadata_en, metadata_cn, thumb_prompt = {}, {}, ""
        
        meta_en_path = os.path.join(self.folder, "youtube_metadata_en.json")
        meta_cn_path = os.path.join(self.folder, "youtube_metadata_cn.json")
        prompt_path = os.path.join(self.folder, "thumbnail_prompt.txt")

        # 1. 元数据复用检验
        if os.path.exists(meta_en_path) and os.path.exists(meta_cn_path):
            try:
                with open(meta_en_path, 'r', encoding='utf-8') as f: metadata_en = json.load(f)
                with open(meta_cn_path, 'r', encoding='utf-8') as f: metadata_cn = json.load(f)
                log_status("REUSE", "Loaded existing Youtube metadata (EN/CN).", "OK")
            except Exception: pass

        if not metadata_en:
            try:
                metadata_en = await robust_openai_metadata_call(
                    self.prompts["YOUTUBE_METADATA"].format(script_summary=script_summary), 
                    self.cfg.YouTubeMetadata
                )
                save_json_formatted(meta_en_path, metadata_en)
                
                prompt_cn = self.prompts["YOUTUBE_METADATA_CN"].format(english_metadata=json.dumps(metadata_en, ensure_ascii=False))
                metadata_cn = await robust_openai_metadata_call(prompt_cn, self.cfg.YouTubeMetadata)
                save_json_formatted(meta_cn_path, metadata_cn)
            except Exception as e: 
                log_status("SEO", f"Metadata generation error: {e}", "WARN")

        try:
            anchor = self.context.get('anchor', 'Masterpiece')
            character_desc = self.context.get("character", "")
            
            layout_options = [
                {
                    "align": "right", 
                    "rule": "Composition Rule of Thirds: Character is positioned strictly on the far left edge. The right side of the frame features a deep, softly blurred background (beautiful bokeh) filled with gentle environmental details, providing depth and atmospheric context while remaining unobtrusive enough for adding text overlay."
                },
                {
                    "align": "left", 
                    "rule": "Composition Rule of Thirds: Character is positioned strictly on the far right edge. The left side of the frame features a deep, softly blurred background (beautiful bokeh) filled with gentle environmental details, providing depth and atmospheric context while remaining unobtrusive enough for adding text overlay."
                }
            ]

            # 【复用逻辑】：从现有上下文读取排版设定，保证 Reuse 时封面结构一致
            saved_align = self.context.get("thumb_text_align")
            if saved_align:
                selected_layout = next((opt for opt in layout_options if opt["align"] == saved_align), layout_options[0])
            else:
                selected_layout = random.choice(layout_options)
                self.context["thumb_text_align"] = selected_layout["align"]
                save_json_formatted(os.path.join(self.folder, "0_context.json"), self.context)
                
            composition_rule = selected_layout["rule"]

            # 2. 封面 Prompt 复用检验
            if os.path.exists(prompt_path):
                try:
                    with open(prompt_path, 'r', encoding='utf-8') as f: thumb_prompt = f.read().strip()
                    log_status("REUSE", "Loaded existing thumbnail_prompt.txt.", "OK")
                except Exception: pass

            if not thumb_prompt:
                if getattr(self.cfg, "USE_IMAGE_TEMPLATE", False):
                    scene = "beautiful landscape"
                    if hasattr(self, "flattened_metadata") and self.flattened_metadata:
                        scene = self.flattened_metadata[0].get("scene_desc", "beautiful landscape")
                    thumb_prompt = f"Cinematic Wide Establishing Shot of {character_desc}. {composition_rule} The setting is {scene}. Breathtaking lighting, masterpiece. [{anchor}, 16:9 aspect ratio]"
                    log_status("SEO", "Thumbnail Template Generated (Cost: $0).", "OK")
                else:
                    async with ConcurrencyManager.OSS_SEM:
                        for attempt in range(3):
                            prompt_template = self.prompts.get("THUMBNAIL_PROMPT_OSS") or self.prompts.get("THUMBNAIL_PROMPT_GEMINI")
                            prompt = prompt_template.format(script_summary=script_summary, anchor=anchor, style=self.context.get('style', ''), character=character_desc)
                            raw_res = await robust_oss_call(prompt, max_tokens=300, clean_output=False)
                            match = re.search(r'<prompt>(.*?)</prompt>', raw_res, re.IGNORECASE | re.DOTALL)
                            if match:
                                cleaned = match.group(1).replace("\n", " ").strip()
                                if cleaned:
                                    thumb_prompt = f"{cleaned} {composition_rule} [{anchor}, 16:9 aspect ratio]"
                                    break
                
                if thumb_prompt:
                    with open(prompt_path, "w", encoding="utf-8") as f: 
                        f.write(thumb_prompt)
        except Exception as e: 
            log_status("SEO", f"Thumbnail Prompt Gen Failed: {e}", "WARN")
            thumb_prompt = ""
            
        return metadata_en, metadata_cn, thumb_prompt

    async def build_full_story(self) -> tuple[list, list, list]:
        """【核心业务总控】：调度选体裁 -> 扩写 -> 中英双语（带独立可插拔改写开关）的 DAG 执行流"""
        context_path = os.path.join(self.folder, "0_context.json")
        
        # 1. 优先尝试从已有目录恢复全量上下文（实现 100% 幂等复用）
        if os.path.exists(context_path):
            try:
                with open(context_path, 'r', encoding='utf-8') as f:
                    self.context = json.load(f)
                log_status("REUSE", "Loaded historical 0_context.json (Story/Anchor/Font strictly preserved).", "OK")
            except Exception as e:
                log_status("REUSE", f"Failed to load 0_context.json: {e}", "WARN")

        # 2. 如果没有成功加载（即新建任务），则从 CSV 初始化
        if not self.context:
            LibraryManager.load_from_csv(self.cfg.LIBRARY_CSV_PATH)
            if not LibraryManager.matrix: return [], [], []

            gen_mode = getattr(self.cfg, "STORY_GENERATE_MODE", "RANDOM")
            target_idx = LibraryManager.get_target_index(self.cfg.RECORD_CSV_PATH, gen_mode)
            
            row_data = LibraryManager.matrix[target_idx]
            self.context = {}
            for k, v in row_data.items():
                val = str(v).strip()
                if not val or (gen_mode == "RANDOM" and k != "story"):
                    valid_options = [str(r.get(k, "")).strip() for r in LibraryManager.matrix if str(r.get(k, "")).strip()]
                    if valid_options: val = random.choice(valid_options)
                self.context[k] = val
            
            log_status("STORY", f"Selected Row: {target_idx} | Topic: {self.context.get('story', 'N/A')[:40]}", "OK")
            save_json_formatted(context_path, self.context)

        outlines, glossary = [], {}
        if getattr(self.cfg, "REUSE_GEMINI_OUTLINE", False):
            try:
                with open(os.path.join(self.folder, "1_outlines.json"), 'r', encoding='utf-8') as f: outlines = json.load(f)
                with open(os.path.join(self.folder, "1_glossary.json"), 'r', encoding='utf-8') as f: glossary = json.load(f)
                
                if glossary:
                    char_body = glossary.get("char_body_and_apparel", "")
                    char_face = glossary.get("char_facial_details", "")
                    if not char_body and "character" in glossary:
                        char_body = glossary.get("character", "")
                    
                    self.context["char_body_and_apparel"] = char_body
                    self.context["char_facial_details"] = char_face
                    
                    combined_char = ""
                    if char_body: combined_char += char_body
                    if char_face: combined_char += f", {char_face}"
                    self.context["character"] = combined_char

                log_status("REUSE", "Loaded 1_outlines.json & 1_glossary.json", "OK")
            except Exception: pass
            
        if not outlines:
            outlines, glossary = await self.run_outline()
            if not outlines:
                log_status("STORY", "Gemini outline failed. Falling back to Kimi...", "WARN")
                sys.exit(1)

                outlines, glossary = await self.run_outline_kimi()
                if not outlines:
                    log_status("STORY", "Kimi outline ALSO failed. Aborting full pipeline.", "CRITICAL")
                    sys.exit(1)

        base_en_scripts = []
        rewritten_en_scripts = []
        cn_scripts_existing = []
        img_prompts_existing = []
        
        if getattr(self.cfg, "REUSE_OPENAI_SCRIPT", False):
            try:
                with open(os.path.join(self.folder, "2_en_scripts.json"), 'r', encoding='utf-8') as f: 
                    base_en_scripts = json.load(f)
                with open(os.path.join(self.folder, "2_metadata.json"), 'r', encoding='utf-8') as f: 
                    self.flattened_metadata = json.load(f)
                log_status("REUSE", "Loaded 2_en_scripts.json and metadata.", "OK")

                if getattr(self.cfg, "SCRIPT_REWRITE_EN", False):
                    rew_en_path = os.path.join(self.folder, "2_en_scripts_rewritten.json")
                    if os.path.exists(rew_en_path):
                        with open(rew_en_path, 'r', encoding='utf-8') as f:
                            temp_rew = json.load(f)
                            if len(temp_rew) == len(base_en_scripts):
                                rewritten_en_scripts = temp_rew
                                log_status("REUSE", "Loaded 2_en_scripts_rewritten.json. Bypassing EN rewrite.", "OK")
            except Exception: pass

        if getattr(self.cfg, "REUSE_DEEPSEEK_SCRIPT", False):
            try:
                if getattr(self.cfg, "SCRIPT_REWRITE_CN", False):
                    rew_cn_path = os.path.join(self.folder, "3_cn_scripts_rewritten.json")
                    if os.path.exists(rew_cn_path):
                        with open(rew_cn_path, 'r', encoding='utf-8') as f: cn_scripts_existing = json.load(f)
                        log_status("REUSE", "Loaded existing rewritten CN scripts.", "OK")
                
                if not cn_scripts_existing:
                    with open(os.path.join(self.folder, "3_cn_scripts.json"), 'r', encoding='utf-8') as f: cn_scripts_existing = json.load(f)
                    log_status("REUSE", "Loaded existing raw CN scripts.", "OK")
            except Exception: pass
                
        if getattr(self.cfg, "REUSE_IMAGE_PROMPT", False):
            try:
                with open(os.path.join(self.folder, "4_img_prompts.json"), 'r', encoding='utf-8') as f: 
                    img_prompts_existing = json.load(f)
                log_status("REUSE", "Loaded 4_img_prompts.json.", "OK")
            except Exception: pass

        if not base_en_scripts:
            base_en_scripts = await self.run_expansion_en(outlines)

        if not cn_scripts_existing:
            glossary_str = "\n".join([f"- {k}: {v}" for k, v in glossary.items()]) if glossary else "无。"
            
            log_status("STORY", "Igniting Batch-DAG Pipeline...", "INFO")
            
            chunk_size = 2
            skip_en_rewrite = bool(rewritten_en_scripts) and len(rewritten_en_scripts) == len(base_en_scripts)
            source_en_for_batches = rewritten_en_scripts if skip_en_rewrite else base_en_scripts
            batches = [source_en_for_batches[i:i+chunk_size] for i in range(0, len(source_en_for_batches), chunk_size)]
            
            async def run_batch_dag(batch, b_idx):
                en_f = batch
                if getattr(self.cfg, "SCRIPT_REWRITE_EN", False) and not skip_en_rewrite:
                    r = await self._rewrite_chunk(batch, "EN", b_idx)
                    if r and len(r) == len(batch): en_f = r

                c_r = await self._localize_chunk_cn(en_f, glossary_str, b_idx)
                if not c_r or len(c_r) != len(en_f): c_r = ["Fallback Translation."] * len(en_f)

                c_f = c_r
                if getattr(self.cfg, "SCRIPT_REWRITE_CN", False):
                    r = await self._rewrite_chunk(c_r, "CN", b_idx)
                    if r and len(r) == len(c_r): c_f = r

                return en_f, c_r, c_f

            tasks = [run_batch_dag(batch, i) for i, batch in enumerate(batches)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            final_en_scripts, raw_cn_scripts, final_cn_scripts = [], [], []
            for i, r in enumerate(results):
                if isinstance(r, BaseException):
                    log_status("PIPELINE", f"Fatal Error on Batch {i+1}: {r}", "ERROR")
                    raise r
                final_en_scripts.extend(r[0])
                raw_cn_scripts.extend(r[1])
                final_cn_scripts.extend(r[2])

            save_json_formatted(os.path.join(self.folder, "3_cn_scripts.json"), raw_cn_scripts)
            
            save_json_formatted(os.path.join(self.folder, "2_en_scripts_rewritten.json"), final_en_scripts)
            save_json_formatted(os.path.join(self.folder, "3_cn_scripts_rewritten.json"), final_cn_scripts)
                
            en_scripts_for_image = final_en_scripts
            cn_scripts_for_media = final_cn_scripts
        else:
            en_scripts_for_image = rewritten_en_scripts if rewritten_en_scripts else base_en_scripts 
            cn_scripts_for_media = cn_scripts_existing

        if not img_prompts_existing:
            log_status("STORY", "Generating cinematic image prompts concurrently...", "INFO")
            img_tasks = [self._generate_cinematic_prompt_single(text, i) for i, text in enumerate(en_scripts_for_image)]
            img_results = await asyncio.gather(*img_tasks, return_exceptions=True)
            img_prompts_existing = []
            for r in img_results:
                if isinstance(r, Exception):
                    log_status("IMAGE_PROMPT", f"Image prompt generation failed: {r}. Exiting program to avoid Fallback scene.", "CRITICAL")
                    sys.exit(1)
                img_prompts_existing.append(r)
            save_json_formatted(os.path.join(self.folder, "4_img_prompts.json"), img_prompts_existing)

        return en_scripts_for_image, cn_scripts_for_media, img_prompts_existing

# =====================================================================
# 4. MEDIA PIPELINE
# =====================================================================
class MediaPipeline:
    def __init__(self, folder: str, segments: list[MediaSegment], reuse_tts: bool = False, channel_name_en: str = "", channel_name_cn: str = "", overlays: list = None, force_pause: bool = False, pause_duration: str = "800ms", reuse_image: bool = False, reuse_video: bool = False, audios: list = None):
        self.folder = folder
        self.segments = segments
        self.reuse_tts = reuse_tts
        self.channel_name_en = channel_name_en
        self.channel_name_cn = channel_name_cn
        self.overlays = overlays or []
        self.force_pause = force_pause 
        self.pause_duration = pause_duration 
        self.reuse_image = reuse_image
        self.reuse_video = reuse_video
        self.audios = audios or []

    def _master_audio_sync(self, raw_wav: str, mastered_wav: str) -> float:
        """【功能简介】：调用专业音频插件串联器 (Compressor -> EQ -> Limiter) 对生成的 AI 语音进行混音干声母带处理"""
        try:
            with AudioFile(raw_wav) as f: audio_data, samplerate = f.read(f.frames), f.samplerate
            board = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=150, gain_db=PEDALBOARD_CONFIG["LOW_SHELF_GAIN"]),
                HighShelfFilter(cutoff_frequency_hz=6000, gain_db=PEDALBOARD_CONFIG["HIGH_SHELF_GAIN"]),
                Compressor(threshold_db=PEDALBOARD_CONFIG["COMP_THRESHOLD"], ratio=PEDALBOARD_CONFIG["COMP_RATIO"]),
                Gain(gain_db=2.0), Limiter(threshold_db=PEDALBOARD_CONFIG["LIMIT_DB"])
            ])
            processed_data = board(audio_data, samplerate)
            with AudioFile(mastered_wav, 'w', samplerate, processed_data.shape[0]) as f: f.write(processed_data)
            return len(AudioSegment.from_file(mastered_wav)) / 1000.0
        except Exception as e:
            log_status("AUDIO", f"Mastering failed: {e}", "ERROR")
            return 0.0

    def _encode_video_sync(self, img_path: str, duration: float, clip_path: str, movement: str):
        """【功能简介】：使用 FFmpeg + Nvenc 进行极速静态图片推拉摇移（Pan&Zoom）以及灰尘噪点等氛围素材覆层渲染"""
        fps = 25
        frames = int(duration * fps)
        f_frames = float(frames)
        ZOOM_MAX = 1.35
        ZOOM_DIFF = ZOOM_MAX - 1.001
        
        base_filter = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,scale=3840:2160"
        end_filter = "scale=1920:1080:flags=bicubic"
        
        if movement == "zoom_in": zp_expr = f"z='1.001+{ZOOM_DIFF}*(on/{f_frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif movement == "zoom_out": zp_expr = f"z='{ZOOM_MAX}-{ZOOM_DIFF}*(on/{f_frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif movement == "pan_right": zp_expr = f"z='{ZOOM_MAX}':x='(iw-iw/zoom)*(on/{f_frames})':y='ih/2-(ih/zoom/2)'"
        elif movement == "pan_left": zp_expr = f"z='{ZOOM_MAX}':x='(iw-iw/zoom)*(1 - on/{f_frames})':y='ih/2-(ih/zoom/2)'"
        elif movement == "pan_down": zp_expr = f"z='{ZOOM_MAX}':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(on/{f_frames})'"
        else: zp_expr = f"z='{ZOOM_MAX}':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1 - on/{f_frames})'"
            
        zp = f"{base_filter},zoompan={zp_expr}:d=1:s=3840x2160:fps={fps},{end_filter}"

        selected_overlay = random.choice(self.overlays) if self.overlays else None
        cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', str(fps), '-t', str(duration), '-i', img_path]
        
        if selected_overlay and os.path.exists(selected_overlay):
            cmd.extend(['-stream_loop', '-1', '-t', str(duration), '-i', selected_overlay])
            fc = f"[0:v]{zp},format=gbrp[bg];[1:v]format=yuv420p,scale=1920:1080,format=gbrp[ovl];[bg][ovl]blend=all_mode='screen':all_opacity=0.45,format=yuv420p[v]" 
            cmd.extend(['-filter_complex', fc, '-map', '[v]'])
        else:
            cmd.extend(['-vf', f"{zp},format=yuv420p"]) 
            
        cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', '5M', '-pix_fmt', 'yuv420p', clip_path])
        
        try: 
            safe_subprocess_run(cmd)
            log_status("FFMPEG", f"Video {os.path.basename(clip_path)} generated successfully with {movement}.", "SUCCESS")
            return True
        except subprocess.CalledProcessError as e: 
            log_status("FFMPEG", f"Encoding failed. Error: {e.stderr.decode()}", "ERROR")
            return False

    async def _process_segment_dual(self, seg: MediaSegment):
        """【功能简介】：双轨媒体生成引擎，通过计算中英双语的最长音频长度，仅渲染一次母视频后双轨复用裁切，可节省 50% 的显卡渲染时长"""
        if not seg.en_text or not seg.cn_text: 
            log_status("MEDIA", f"Seg {seg.index} aborted! Empty text.", "WARN")
            return
            
        en_raw_wav = os.path.join(self.folder, "audio", f"s{seg.index:03d}_en_raw.mp3")
        cn_raw_wav = os.path.join(self.folder, "audio", f"s{seg.index:03d}_cn_raw.mp3")
        base_vid_path = os.path.join(self.folder, "video", f"s{seg.index:03d}_base.mp4")
        en_vid_path = os.path.join(self.folder, "video", f"s{seg.index:03d}_en.mp4")
        cn_vid_path = os.path.join(self.folder, "video", f"s{seg.index:03d}_cn.mp4")
            
        try:
            all_audio_exist = os.path.exists(seg.en_audio_path) and os.path.exists(seg.cn_audio_path)
            has_base_video = os.path.exists(base_vid_path)
            has_split_video = os.path.exists(en_vid_path) and os.path.exists(cn_vid_path)
            
            if self.reuse_tts and self.reuse_video and all_audio_exist and has_split_video:
                log_status("MEDIA", f"Seg {seg.index} ALL media exists. Bypassing render.", "OK")
                seg.en_duration = len(AudioSegment.from_file(seg.en_audio_path)) / 1000.0
                seg.cn_duration = len(AudioSegment.from_file(seg.cn_audio_path)) / 1000.0
                seg.en_video_path = en_vid_path
                seg.cn_video_path = cn_vid_path
                seg.is_valid_en = True
                seg.is_valid_cn = True
                return

            log_status("MEDIA", f"Seg {seg.index} processing dual-track started.", "INFO")
                
            async def do_en_audio():
                if not (self.reuse_tts and os.path.exists(seg.en_audio_path)):
                    if not os.path.exists(en_raw_wav):
                        audio_text = apply_ssml_pauses(seg.en_text, self.pause_duration) if self.force_pause else seg.en_text
                        async with ConcurrencyManager.TTS_SEM:
                            await robust_edge_tts_call(audio_text, MODEL_CONFIG["VOICE_EN"], en_raw_wav)
                    return await asyncio.to_thread(self._master_audio_sync, en_raw_wav, seg.en_audio_path)
                return len(AudioSegment.from_file(seg.en_audio_path)) / 1000.0

            async def do_cn_audio():
                if not (self.reuse_tts and os.path.exists(seg.cn_audio_path)):
                    if not os.path.exists(cn_raw_wav):
                        audio_text = apply_ssml_pauses(seg.cn_text, self.pause_duration) if self.force_pause else seg.cn_text
                        async with ConcurrencyManager.TTS_SEM:
                            await robust_edge_tts_call(audio_text, MODEL_CONFIG["VOICE_CN"], cn_raw_wav)
                    return await asyncio.to_thread(self._master_audio_sync, cn_raw_wav, seg.cn_audio_path)
                return len(AudioSegment.from_file(seg.cn_audio_path)) / 1000.0

            async def do_image():
                if self.reuse_image and os.path.exists(seg.img_path):
                    log_status("MEDIA", f"Seg {seg.index} Image exists. Bypassing RunningHub.", "OK")
                    return True
                async with ConcurrencyManager.IMG_SEM:
                    await robust_image_call(seg.img_prompt, seg.img_path, f"IMG_{seg.index:02d}")
                return True

            en_dur, cn_dur, _ = await asyncio.gather(do_en_audio(), do_cn_audio(), do_image())
                
            seg.en_duration = en_dur
            seg.cn_duration = cn_dur
            max_dur = max(en_dur, cn_dur)
            
            if max_dur <= 0: 
                log_status("MEDIA", f"Seg {seg.index} aborted! max_dur <= 0.", "ERROR")
                return

            if not (self.reuse_video and has_split_video):
                if not (self.reuse_video and has_base_video):
                    async with ConcurrencyManager.NVENC_SEM:
                        log_status("MEDIA", f"Seg {seg.index} starting FFmpeg base video generation...", "INFO")
                        movement_pool = ["zoom_in", "pan_right", "pan_down", "zoom_out", "pan_left", "pan_up"]
                        movement = movement_pool[seg.index % 6]
                        encode_ok = await asyncio.to_thread(self._encode_video_sync, seg.img_path, max_dur, base_vid_path, movement)
                        if not encode_ok: 
                            log_status("MEDIA", f"Seg {seg.index} video encoding failed.", "ERROR")
                            return
                else:
                    log_status("MEDIA", f"Seg {seg.index} Base video exists. Bypassing NVENC.", "OK")

                await asyncio.to_thread(subprocess.run, ['ffmpeg', '-y', '-i', base_vid_path, '-t', str(en_dur), '-c', 'copy', en_vid_path], capture_output=True)
                await asyncio.to_thread(subprocess.run, ['ffmpeg', '-y', '-i', base_vid_path, '-t', str(cn_dur), '-c', 'copy', cn_vid_path], capture_output=True)
                    
            seg.en_video_path = en_vid_path
            seg.cn_video_path = cn_vid_path
            seg.is_valid_en = True
            seg.is_valid_cn = True
                
        except Exception as e:
            log_status("MEDIA", f"Seg {seg.index} failed critically: {repr(e)}", "ERROR")

    async def run_dual_tracks(self):
        log_status("PIPELINE", f"Starting Dual Track Pipeline ({len(self.segments)} segments)...", "INFO")
        results = await asyncio.gather(*[self._process_segment_dual(seg) for seg in self.segments], return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                log_status("PIPELINE", f"Dual Track Segment {i+1} returned FATAL exception: {repr(r)}", "ERROR")
                raise r

    def assemble(self, output_name: str, mode: str = "EN") -> str:
        """【功能简介】：全自动质检机制，通过 Concat 无损合并且一次性打上全屏硬字幕水波纹"""
        log_status("STUDIO", f"Validating all {len(self.segments)} segments before {mode} assembly...", "INFO")
        
        missing_segs = []
        for s in self.segments:
            is_valid = s.is_valid_en if mode == "EN" else s.is_valid_cn
            vid_path = s.en_video_path if mode == "EN" else s.cn_video_path
            audio_path = s.en_audio_path if mode == "EN" else s.cn_audio_path
            
            if not is_valid or not os.path.exists(vid_path) or not os.path.exists(audio_path):
                missing_segs.append(str(s.index))

        if missing_segs:
            fatal_msg = f"ASSEMBLY ABORTED! Missing/Invalid media files for segments: {', '.join(missing_segs)}"
            log_status("STUDIO", fatal_msg, "ERROR")
            raise FileNotFoundError(fatal_msg) 
        
        log_status("STUDIO", "All segments verified successfully. Proceeding with FFmpeg concat and watermarking...", "OK")
        
        prefix = output_name.split('.')[0]
        v_concat = os.path.join(self.folder, f"{prefix}_v.txt")
        a_concat = os.path.join(self.folder, f"{prefix}_a.txt")
        
        try:
            with open(v_concat, "w", encoding='utf-8') as fv, open(a_concat, "w", encoding='utf-8') as fa:
                for s in self.segments:
                    vid_path = s.en_video_path if mode == 'EN' else s.cn_video_path
                    aud_path = s.en_audio_path if mode == 'EN' else s.cn_audio_path
                    fv.write(f"file '{os.path.abspath(vid_path)}'\n")
                    fa.write(f"file '{os.path.abspath(aud_path)}'\n")

            v_out_temp = os.path.join(self.folder, f"{prefix}_temp_v.mp4")
            a_out = os.path.join(self.folder, f"{prefix}_master_a.wav")
            final_out = os.path.join(self.folder, output_name)
            
            safe_subprocess_run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', v_concat, '-c', 'copy', v_out_temp])
            safe_subprocess_run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', a_concat, '-c', 'copy', a_out])
            
            channel_watermark = self.channel_name_en if mode == "EN" else self.channel_name_cn
            text_filter = ""
            if channel_watermark:
                safe_name = channel_watermark.replace("'", "").replace(":", "")
                font_path = "C\\:/Windows/Fonts/msyhbd.ttc"
                text_filter = f"drawtext=fontfile='{font_path}':text='{safe_name}':fontcolor=white@0.7:fontsize=48:x=50:y=50:shadowcolor=black@0.7:shadowx=2:shadowy=2"
            

            # --- 混流与注入 (支持 BGM 与 水印) ---
            combine_cmd = ['ffmpeg', '-y', '-i', v_out_temp, '-i', a_out]
            bgm = random.choice(self.audios) if self.audios else None

            f_complex = []
            v_label = "0:v"
            a_label = "1:a"

            # 1. 处理 BGM 注入 (Input 2)
            if bgm and os.path.exists(bgm):
                combine_cmd.extend(['-stream_loop', '-1', '-i', bgm])
                log_status("STUDIO", f"Injecting BGM (45% volume): {os.path.basename(bgm)}", "INFO")
                # 混音流: 1:a (干声) + 2:a (BGM)
                f_complex.append("[1:a]volume=1.0[va]; [2:a]volume=0.45[ba]; [va][ba]amix=inputs=2:duration=first:dropout_transition=2[a_mix]")
                a_label = "[a_mix]"
            
            # 2. 处理水印 (drawtext)
            if text_filter:
                f_complex.append(f"[{v_label}]{text_filter}[v_out]")
                v_label = "[v_out]"
                combine_cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', '5M', '-pix_fmt', 'yuv420p'])
            else:
                combine_cmd.extend(['-c:v', 'copy'])

            # 3. 组合滤镜与映射
            if f_complex:
                combine_cmd.extend(['-filter_complex', "; ".join(f_complex)])
            
            combine_cmd.extend(['-map', v_label, '-map', a_label, '-c:a', 'aac', '-shortest', final_out])
            
            safe_subprocess_run(combine_cmd)
            log_status("STUDIO", f"Completed Assembly & Watermarking: {final_out}", "SUCCESS")
            return final_out
        except subprocess.CalledProcessError as e:
            log_status("STUDIO", f"Assemble FFmpeg failed: {e}", "ERROR")
            raise e
        except Exception as e: 
            log_status("STUDIO", f"Assemble failed: {e}", "ERROR")
            raise e

# =====================================================================
# 5. MAIN ORCHESTRATOR
# =====================================================================

def save_task_record(csv_path: str, task_id: str, app_name: str, start_time: datetime, end_time: datetime, result: str, output_path: str, story_title: str = "Unknown"):
    """【功能简介】：将任务结果安全地 upsert 存入记录追踪 CSV 中"""
    if not csv_path: return
    
    abs_csv_path = os.path.abspath(csv_path)
    os.makedirs(os.path.dirname(abs_csv_path), exist_ok=True)
    
    headers = ["task_id", "app_name", "start_time", "end_time", "result", "output_path", "story_title"]
    rows = []
    
    if os.path.isfile(abs_csv_path):
        try:
            with open(abs_csv_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                existing_headers = reader.fieldnames or []
                for h in existing_headers:
                    if h not in headers: headers.append(h)
                rows = list(reader)
        except Exception as e:
            log_status("RECORD", f"Failed to read existing CSV (it might be locked), proceeding to create new: {e}", "WARN")
            
    task_found = False
    for row in rows:
        if row.get("task_id") == task_id:
            row["end_time"] = end_time.strftime('%Y-%m-%d %H:%M:%S')
            row["result"] = result
            row["output_path"] = output_path
            row["story_title"] = story_title
            task_found = True
            break
            
    if not task_found:
        rows.append({
            "task_id": task_id, "app_name": app_name,
            "start_time": start_time.strftime('%Y-%m-%d %H:%M:%S'),
            "end_time": end_time.strftime('%Y-%m-%d %H:%M:%S'),
            "result": result, "output_path": output_path, "story_title": story_title
        })
        
    try:
        temp_csv = abs_csv_path + ".tmp"
        with open(temp_csv, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_csv, abs_csv_path)
        log_status("RECORD", f"Task [{task_id}] status '{result}' saved to {os.path.basename(abs_csv_path)}.", "OK")
    except Exception as e:
        log_status("RECORD", f"CRITICAL: Failed to write task record to {abs_csv_path}: {e}", "ERROR")

def construct_media_segments(folder: str, en_scripts: list, cn_scripts: list, img_prompts: list) -> list[MediaSegment]:
    segments = []
    for i in range(len(en_scripts)):
        segments.append(MediaSegment(
            index=i+1, en_text=en_scripts[i], cn_text=cn_scripts[i] if i < len(cn_scripts) else "",
            img_prompt=img_prompts[i] if i < len(img_prompts) else "Scene",
            img_path=os.path.join(folder, "image", f"s{i+1:03d}_img.png"),
            en_audio_path=os.path.join(folder, "audio", f"s{i+1:03d}_en.wav"), 
            cn_audio_path=os.path.join(folder, "audio", f"s{i+1:03d}_cn.wav"),
            en_video_path=os.path.join(folder, "video", f"s{i+1:03d}_en.mp4"), 
            cn_video_path=os.path.join(folder, "video", f"s{i+1:03d}_cn.mp4")
        ))
    return segments

def str2bool(v):
    """【功能简介】：工业级布尔值解析器，支撑强化的 CLI 参数转换"""
    if isinstance(v, bool): return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'): return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'): return False
    else: raise argparse.ArgumentTypeError('Boolean value expected.')

async def execute_channel(config_file: str, cli_args):
    start_time = datetime.now()
    app_name = os.path.basename(config_file)
    exec_result = "FAILED"
    folder = ""
    current_story_title = "Unknown"
    
    app_base_name = os.path.splitext(app_name)[0]
    task_prefix = app_base_name.split('_')[-1].upper()
    current_task_id = f"{task_prefix}_{start_time.strftime('%Y%m%d%H%M%S')}"

    cfg = load_python_config(config_file)
    
    is_cli_mode = len(sys.argv) > 1
    overrides_applied = []

    if is_cli_mode:
        cfg.REUSE_GEMINI_OUTLINE = cli_args.reuse_gemini_outline if cli_args.reuse_gemini_outline is not None else False
        cfg.REUSE_OPENAI_SCRIPT = cli_args.reuse_openai_script if cli_args.reuse_openai_script is not None else False
        cfg.REUSE_DEEPSEEK_SCRIPT = cli_args.reuse_deepseek_script if cli_args.reuse_deepseek_script is not None else False
        cfg.REUSE_IMAGE_PROMPT = cli_args.reuse_image_prompt if cli_args.reuse_image_prompt is not None else False
        cfg.REUSE_TTS = cli_args.reuse_tts if cli_args.reuse_tts is not None else False
        cfg.REUSE_IMAGE = cli_args.reuse_image if cli_args.reuse_image is not None else False
        cfg.REUSE_VIDEO = cli_args.reuse_video if cli_args.reuse_video is not None else False
        cfg.REUSE_TASK_ID = cli_args.reuse_task_id if cli_args.reuse_task_id is not None else ""
        
        if cli_args.only_generate_image is not None:
            cfg.ONLY_GENERATE_IMAGE = cli_args.only_generate_image
            
        overrides_applied.append("CLI Mode Active: File REUSE configs strictly ignored.")
    else:
        overrides_applied.append("IDE Mode Active: Trusting file REUSE configs.")

    log_status("SYSTEM", f"--- OS RUNNING CHANNEL: {app_name} [Task: {current_task_id}] ---", "START")
    
    if overrides_applied:
        log_status("SYSTEM", f"Applied Rule: {', '.join(overrides_applied)}", "INFO")
    
    ConcurrencyManager.init_locks()
    ConcurrencyManager.OPENAI_SEM = asyncio.Semaphore(5)   
    ConcurrencyManager.GEMINI_SEM = asyncio.Semaphore(3)   
    ConcurrencyManager.DEEPSEEK_SEM = asyncio.Semaphore(2) 
    ConcurrencyManager.OSS_SEM = asyncio.Semaphore(2)      
    
    if not validate_environment(): 
        save_task_record(cfg.RECORD_CSV_PATH, current_task_id, app_name, start_time, datetime.now(), exec_result, folder, current_story_title)
        return

    is_reusing = any([
        getattr(cfg, 'REUSE_GEMINI_OUTLINE', False), getattr(cfg, 'REUSE_OPENAI_SCRIPT', False), 
        getattr(cfg, 'REUSE_DEEPSEEK_SCRIPT', False), getattr(cfg, 'REUSE_IMAGE_PROMPT', False), 
        getattr(cfg, 'REUSE_TTS', False), getattr(cfg, 'REUSE_IMAGE', False),
        getattr(cfg, 'REUSE_VIDEO', False), bool(getattr(cfg, 'REUSE_TASK_ID', ""))
    ])
    
    if is_reusing:
        target = ""
        reuse_task_id_val = getattr(cfg, "REUSE_TASK_ID", "")
        
        if reuse_task_id_val:
            try:
                if os.path.exists(cfg.RECORD_CSV_PATH):
                    with open(cfg.RECORD_CSV_PATH, 'r', encoding='utf-8-sig') as f:
                        rows = list(csv.DictReader(f))
                        found_task = False
                        for row in rows:
                            if row.get("task_id") == reuse_task_id_val:
                                target = row.get("output_path", "")
                                current_task_id = reuse_task_id_val
                                log_status("SYSTEM", f"REUSE_TASK_ID matched. Targeting task: {current_task_id}", "OK")
                                found_task = True
                                break
                        
                        if not found_task:
                            log_status("SYSTEM", f"Task ID '{reuse_task_id_val}' not found in records. Falling back.", "WARN")
            except Exception as e:
                log_status("SYSTEM", f"Failed to search specific task ID in CSV: {e}", "WARN")
                
        if not target: 
            target = getattr(cfg, "REUSE_TARGET_FOLDER", "")

        if not target or not os.path.exists(target):
            log_status("SYSTEM", "Reuse flags ON, but target folder not found or Task ID invalid. Aborting.", "CRITICAL")
            save_task_record(cfg.RECORD_CSV_PATH, current_task_id, app_name, start_time, datetime.now(), exec_result, target, current_story_title)
            return
            
        folder = target
        log_status("ENV", f"Targeting existing workspace: {folder}", "OK")
    else:
        folder = setup_workspace(os.path.join(cfg.BASE_WORKSPACE, datetime.now().strftime('%Y%m%d_%H%M%S')))

    LoggerManager.set_log_file(os.path.join(folder, "pipeline_master.log"))

    os.makedirs(os.path.join(folder, "image"), exist_ok=True)
    os.makedirs(os.path.join(folder, "audio"), exist_ok=True)
    os.makedirs(os.path.join(folder, "video"), exist_ok=True)

    try: 
        stop_watcher_task = asyncio.create_task(stop_file_watcher())
        
        story_pipe = StoryPipeline(folder, cfg)
        en_scripts, cn_scripts, img_prompts = await story_pipe.build_full_story()
        current_story_title = story_pipe.context.get('story', 'Unknown')

        async def seo_thumbnail_task():
            if getattr(cfg, "GENERATE_YOUTUBE_ASSETS", False):
                log_status("SYSTEM", "Starting Parallel SEO Asset Generation...", "INFO")
                m_en, m_cn, t_prompt = await story_pipe.generate_youtube_assets(en_scripts, current_story_title, app_name)
                
                if t_prompt and not getattr(cfg, "ONLY_GENERATE_SCRIPT", False):
                    thumb_en_path = os.path.join(folder, "thumbnail_en.png")
                    thumb_cn_path = os.path.join(folder, "thumbnail_cn.png")
                    
                    if getattr(cfg, "REUSE_IMAGE", False) and os.path.exists(thumb_en_path) and os.path.exists(thumb_cn_path):
                        log_status("REUSE", "Thumbnail images already exist. Bypassing generation.", "OK")
                        return m_en

                    thumb_base_path = os.path.join(folder, "thumbnail_base.png")
                    async with ConcurrencyManager.IMG_SEM:
                        if await generate_runninghub_image(t_prompt, thumb_base_path, "SEO_THUMB"):
                            log_status("SEO", f"Thumbnail base image generated.", "SUCCESS")
                            text_align = story_pipe.context.get("thumb_text_align", "right")
                            
                            font_pool_en = getattr(cfg, "FONT_POOL", {}).get("EN", ["msyhbd.ttc"])
                            font_pool_cn = getattr(cfg, "FONT_POOL", {}).get("CN", font_pool_en)
                            
                            # 【复用逻辑】：强制读取并锁定第一次生成的字体，保证复用时封面排版完美一致
                            font_val_en = story_pipe.context.get("font")
                            font_val_cn = story_pipe.context.get("font_cn")
                            
                            context_updated = False
                            if not font_val_en:
                                font_val_en = random.choice(font_pool_en)
                                story_pipe.context["font"] = font_val_en
                                context_updated = True
                            if not font_val_cn:
                                font_val_cn = random.choice(font_pool_cn)
                                story_pipe.context["font_cn"] = font_val_cn
                                context_updated = True
                                
                            if context_updated:
                                save_json_formatted(os.path.join(folder, "0_context.json"), story_pipe.context)
                            
                            font_folder = getattr(cfg, "FONT_FOLDER", "")
                            if font_folder:
                                if not os.path.isabs(font_val_en): font_val_en = os.path.join(font_folder, font_val_en)
                                if not os.path.isabs(font_val_cn): font_val_cn = os.path.join(font_folder, font_val_cn)
                            
                            thumb_en_path = os.path.join(folder, "thumbnail_en.png")
                            thumb_cn_path = os.path.join(folder, "thumbnail_cn.png")
                            
                            add_text_to_thumbnail(thumb_base_path, thumb_en_path, m_en.get("thumbnail_text", current_story_title), align=text_align, font_path=font_val_en)
                            
                            title_cn = m_cn.get("thumbnail_text") if m_cn else m_en.get("thumbnail_text", current_story_title)
                            add_text_to_thumbnail(thumb_base_path, thumb_cn_path, title_cn, align=text_align, font_path=font_val_cn)
                            
                            if os.path.exists(thumb_base_path): os.remove(thumb_base_path)
                elif getattr(cfg, "ONLY_GENERATE_SCRIPT", False):
                    log_status("SEO", "Script Gen Only Mode: Bypassing Thumbnail Image Generation.", "INFO")
                    
                return m_en
            return None

        seo_task = asyncio.create_task(seo_thumbnail_task())

        if getattr(cfg, "ONLY_GENERATE_SCRIPT", False): 
            await seo_task 
            exec_result = "SUCCESS"
            log_status("SYSTEM", "Script Gen Only Mode active. Exiting.", "INFO")
            return

        if getattr(cfg, "ONLY_GENERATE_IMAGE", False):
            log_status("SYSTEM", "Image Gen Only Mode active. Bypassing TTS & Video generation.", "INFO")
            if not en_scripts:
                log_status("SYSTEM", "No valid scripts available. Exiting.", "ERROR")
                return

            segments = construct_media_segments(folder, en_scripts, cn_scripts, img_prompts)
            reuse_image = getattr(cfg, "REUSE_IMAGE", False)
            
            async def generate_all_images():
                async def gen_img(seg):
                    if reuse_image and os.path.exists(seg.img_path):
                        log_status("MEDIA", f"Seg {seg.index} Image exists. Bypassing RunningHub.", "OK")
                        return
                    async with ConcurrencyManager.IMG_SEM:
                        await robust_image_call(seg.img_prompt, seg.img_path, f"IMG_{seg.index:02d}")
                        log_status("MEDIA", f"Seg {seg.index} Image generated.", "SUCCESS")
                
                results = await asyncio.gather(*[gen_img(s) for s in segments], return_exceptions=True)
                for i, r in enumerate(results):
                    if isinstance(r, Exception):
                        log_status("MEDIA", f"Seg {i+1} Image Gen Failed: {r}", "ERROR")

            await asyncio.gather(generate_all_images(), seo_task)
            exec_result = "SUCCESS"
            log_status("SYSTEM", "Image Gen Only Mode complete. Exiting.", "SUCCESS")
            return

        if not en_scripts:
            log_status("SYSTEM", "No valid scripts available. Exiting.", "ERROR")
            return

        segments = construct_media_segments(folder, en_scripts, cn_scripts, img_prompts)
        
        channel_name = getattr(cfg, "CHANNEL_NAME", "")
        channel_name_cn = getattr(cfg, "CHANNEL_NAME_CN", channel_name)
        overlays = getattr(cfg, "ASSETS_POOL", {}).get("overlays", [])
        audios = getattr(cfg, "ASSETS_POOL", {}).get("audios", [])  # <--- 新增读取 audios
        force_pause = getattr(cfg, "FORCE_PAUSE", False)
        pause_duration = getattr(cfg, "PAUSE_DURATION", "800ms")
        reuse_image = getattr(cfg, "REUSE_IMAGE", False)
        reuse_video = getattr(cfg, "REUSE_VIDEO", False)
        
        media_pipe = MediaPipeline(
            folder, segments, getattr(cfg, "REUSE_TTS", False), channel_name, channel_name_cn, 
            overlays, force_pause, pause_duration, reuse_image, reuse_video, audios
        )
        
        parallel_results = await asyncio.gather(
            media_pipe.run_dual_tracks(),
            seo_task
        )
        metadata_en = parallel_results[1]
        
        final_en = media_pipe.assemble("FINAL_STORY_EN.mp4", "EN")
        final_cn = media_pipe.assemble("FINAL_STORY_CN.mp4", "CN")

        if getattr(cfg, "AUTO_UPLOAD_TO_YOUTUBE", False) and metadata_en and final_en and os.path.exists(final_en):
            upload_video_to_youtube(final_en, metadata_en.get("title", app_name), metadata_en.get("description", ""), metadata_en.get("tags", []))

        exec_result = "SUCCESS"

    except Exception as e: 
        log_status("SYSTEM", f"Critical Pipeline Failure: {repr(e)}", "CRITICAL")
    finally:
        if 'stop_watcher_task' in locals() and not stop_watcher_task.done():
            stop_watcher_task.cancel()
        await APIClients.close_all()
        
        if exec_result == "SUCCESS":
            log_status("CLEANUP", "Initializing smart clean of intermediate media assets...", "INFO")
            for f_name in os.listdir(folder):
                if f_name in ["FINAL_STORY_EN.mp4", "FINAL_STORY_CN.mp4"]: continue
                if f_name.startswith("FINAL_STORY_") and (f_name.endswith(".wav") or f_name.endswith(".aac") or f_name.endswith(".mp4")):
                    try: os.remove(os.path.join(folder, f_name))
                    except Exception: pass
            log_status("CLEANUP", "Smart cleanup complete. Valuable assets retained.", "OK")
        
        end_time = datetime.now()
        save_task_record(cfg.RECORD_CSV_PATH, current_task_id, app_name, start_time, end_time, exec_result, folder, current_story_title)
        log_status("SYSTEM", "Resources cleaned up gracefully.", "INFO")

if __name__ == "__main__":
    if sys.platform == 'win32': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    parser = argparse.ArgumentParser(description="Content OS Matrix - Universal Channel Runner")
    parser.add_argument("-c", "--config", type=str, default="app_tanktail.py", help="Path to the channel configuration Python file")
    
    parser.add_argument("--reuse-gemini-outline", type=str2bool, nargs='?', const=True, default=None, help="Force override REUSE_GEMINI_OUTLINE")
    parser.add_argument("--reuse-openai-script", type=str2bool, nargs='?', const=True, default=None, help="Force override REUSE_OPENAI_SCRIPT")
    parser.add_argument("--reuse-deepseek-script", type=str2bool, nargs='?', const=True, default=None, help="Force override REUSE_DEEPSEEK_SCRIPT")
    parser.add_argument("--reuse-image-prompt", type=str2bool, nargs='?', const=True, default=None, help="Force override REUSE_IMAGE_PROMPT")
    parser.add_argument("--reuse-tts", type=str2bool, nargs='?', const=True, default=None, help="Force override REUSE_TTS")
    parser.add_argument("--reuse-image", type=str2bool, nargs='?', const=True, default=None, help="Force override REUSE_IMAGE")
    parser.add_argument("--reuse-video", type=str2bool, nargs='?', const=True, default=None, help="Force override REUSE_VIDEO")
    parser.add_argument("--reuse-task-id", type=str, default=None, help="Specific Task ID to reuse")
    parser.add_argument("--only-generate-image", type=str2bool, nargs='?', const=True, default=None, help="Force override ONLY_GENERATE_IMAGE")
    
    args = parser.parse_args()
    
    config_file = args.config
    
    if not os.path.exists(config_file):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [SYSTEM    ] [ERROR] Config file '{config_file}' not found.")
        sys.exit(1)
        
    try:
        asyncio.run(execute_channel(config_file, args))
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [SYSTEM    ] [WARN ] KeyboardInterrupt received. Gracefully terminating mapped FFmpeg processes...")
        for p in ACTIVE_FFMPEG_PROCS:
            try: p.terminate()
            except Exception: pass
        os._exit(0)