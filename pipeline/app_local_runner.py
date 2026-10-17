# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, broad-exception-caught, too-many-locals, too-many-statements, too-many-arguments, too-many-branches, too-many-instance-attributes, missing-docstring
"""
Content OS - Simple Runner
Purpose: local/debug-friendly runner without Gemini/OpenAI/DeepSeek outline/expand/rewrite/QA logic.
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
import signal
import threading
from contextlib import suppress
from datetime import datetime
from typing import Any, Optional, Dict, List, Tuple

from core_engine import (
    setup_workspace,     safe_json_loads,    save_json_formatted,    ConcurrencyManager,    APIClients,
    MediaSegment,    MODEL_CONFIG,  build_nvenc_zoompan_ffmpeg_cmd,    render_video_multi_segment_sync,    robust_tts_call,
    robust_image_call,    apply_ssml_pauses,    PEDALBOARD_CONFIG,    robust_gemma4_call,    robust_deepseek_call,    LoggerManager,
    log_status,    safe_subprocess_run,    ACTIVE_FFMPEG_PROCS,    FFMPEG_TIMEOUT_SECONDS,    stop_file_watcher,
    _terminate_process,    add_text_to_thumbnail,    save_task_record,    load_python_config,    LibraryManager,
    merge_dual_scripts,    construct_media_segments,    str2bool,    SystemController,
    inspect_tts_safety,    generate_blurred_title_video,  detect_nvenc,
    master_audio_sync, _format_windows_font_path, _escape_drawtext,
)

from core_engine import GitHubSyncManager, SystemController, encode_video_github_sync
from render_backends import (
    encode_video_colab_sync, get_render_config, get_render_parallelism, resolve_render_backend,
)
from app_podcast import SHOT_TYPES, LIGHTING_MOODS, MALE_OUTFITS, FEMALE_OUTFITS, RANDOM_ENVIRONMENTS, RANDOM_ACTIONS

from pydub import AudioSegment
from pedalboard import Pedalboard, Compressor, Limiter, Gain, PeakFilter, HighpassFilter   
from pedalboard.io import AudioFile


class StoryPipeline:
    def __init__(self, folder: str, cfg):
        self.folder = folder
        self.cfg = cfg
        self.context = {}
        self.flattened_metadata = []

    @staticmethod
    def _normalize_used_flag(value) -> bool:
        """Normalize a 'used' flag value to a boolean. Accepts 'yes', 'true', '1', or 'y'."""
        return str(value or "").strip().lower() in {"yes", "true", "1", "y"}

    def _load_script_resource_state(self, file_path: str) -> dict[str, Any]:
        """Load a script resource file (CSV or Excel) and return its state as a dict with headers and rows."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            last_error = None
            for encoding in ("utf-8-sig", "utf-8", "gbk"):
                try:
                    with open(file_path, "r", encoding=encoding, newline="") as file_obj:
                        reader = csv.DictReader(file_obj)
                        headers = list(reader.fieldnames or [])
                        rows = [{key: "" if value is None else str(value) for key, value in row.items()} for row in reader]
                    return {"type": "csv", "path": file_path, "headers": headers, "rows": rows, "encoding": encoding}
                except Exception as exc:
                    last_error = exc
            raise RuntimeError(f"Failed to read CSV script resource: {last_error}")

        if ext in {".xlsx", ".xlsm"}:
            try:
                from openpyxl import load_workbook
            except ImportError as exc:
                raise RuntimeError("Reading Excel script resources requires openpyxl.") from exc

            workbook = load_workbook(file_path)
            worksheet = workbook.active
            headers = ["" if cell.value is None else str(cell.value).strip() for cell in worksheet[1]]
            rows = []
            for row_idx in range(2, worksheet.max_row + 1):
                row_data = {}
                has_value = False
                for col_idx, header in enumerate(headers, start=1):
                    value = worksheet.cell(row=row_idx, column=col_idx).value
                    if value not in [None, ""]:
                        has_value = True
                    row_data[header] = "" if value is None else str(value)
                if has_value:
                    rows.append(row_data)
            return {
                "type": "excel",
                "path": file_path,
                "headers": headers,
                "rows": rows,
                "workbook": workbook,
                "worksheet": worksheet,
            }

        raise RuntimeError(f"Unsupported script resource format: {file_path}")

    def _mark_script_resource_used(self, state: dict[str, Any], row_index: int):
        """Mark a specific row in the script resource file (CSV or Excel) as used by setting its 'used' column to 'yes'."""
        if row_index < 0 or row_index >= len(state.get("rows", [])):
            return

        state["rows"][row_index]["used"] = "yes"
        if "used" not in state.get("headers", []):
            state["headers"].append("used")

        try:
            if state["type"] == "csv":
                with open(state["path"], "w", encoding=state.get("encoding", "utf-8-sig"), newline="") as file_obj:
                    writer = csv.DictWriter(file_obj, fieldnames=state["headers"])
                    writer.writeheader()
                    writer.writerows(state["rows"])
            else:
                worksheet = state["worksheet"]
                headers = state["headers"]
                used_col = headers.index("used") + 1
                worksheet.cell(row=1, column=used_col).value = "used"
                worksheet.cell(row=row_index + 2, column=used_col).value = "yes"
                state["workbook"].save(state["path"])
            log_status("PRESET", f"Marked script resource row {row_index + 2} as used.", "OK")
        except Exception as exc:
            log_status("PRESET", f"Failed to mark preset row as used: {exc}", "WARN")

    def _parse_script_cell(self, raw_value) -> list[str]:
        """Parse a raw script cell value into a list of script segments.
        Supports JSON arrays, delimiter-separated text, double-newline paragraphs,
        and single-newline lines merged into 150-300 character segments.
        """
        text = str(raw_value or "").strip()
        if not text:
            return []

        # --- DIAG: show raw content and detected line endings ---
        print(f"\n[DIAG][PARSE] raw text length: {len(text)}", flush=True)
        has_crlf = "\r\n" in text
        has_lf = "\n" in text and "\r\n" not in text
        has_double_lf = "\n\n" in text or "\r\n\r\n" in text
        print(f"[DIAG][PARSE] CRLF={has_crlf}, LF-only={has_lf}, double-newline={has_double_lf}", flush=True)
        # -------------------------------------------------------

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
            if isinstance(data, dict):
                for key in ("scripts", "data", "items", "outline"):
                    if isinstance(data.get(key), list):
                        return [str(item).strip() for item in data[key] if str(item).strip()]
        except (json.JSONDecodeError, TypeError, ValueError):
            log_status("PRESET", "Script cell is not JSON, falling back to plain text parsing.", "DEBUG")

        for pattern in (
            r"\r?\n\s*---+\s*\r?\n",
            r"\r?\n\s*\|\|\|\s*\r?\n",
            r"\r?\n\s*###\s*\r?\n",
            r"\r?\n\s*\d+\.\s+",
        ):
            parts = [part.strip() for part in re.split(pattern, text) if part.strip()]
            if len(parts) > 1:
                return parts

        paragraph_parts = [part.strip() for part in re.split(r"\r?\n\r?\n+", text) if part.strip()]
        print(f"[DIAG][PARSE] double-newline split => {len(paragraph_parts)} parts", flush=True)
        if len(paragraph_parts) > 1:
            return paragraph_parts

        # Last resort: text uses single \n only — split by line, then merge into 150-250 char segments.
        lines = [line.strip() for line in re.split(r"\r?\n", text) if line.strip()]
        print(f"[DIAG][PARSE] single-newline split => {len(lines)} lines, attempting merge into segments", flush=True)
        if len(lines) > 1:
            TARGET_MIN = 150
            TARGET_MAX = 300
            segments = []
            buf = ""
            for line in lines:
                if buf:
                    candidate = buf + line
                else:
                    candidate = line
                if len(candidate) >= TARGET_MIN:
                    segments.append(candidate.strip())
                    buf = ""
                else:
                    buf = candidate
            if buf:
                if segments:
                    segments[-1] = (segments[-1] + buf).strip()
                else:
                    segments.append(buf.strip())
            print(f"[DIAG][PARSE] merged into {len(segments)} segments", flush=True)
            for i, s in enumerate(segments):
                print(f"[DIAG][PARSE]   seg[{i}] len={len(s)} | {repr(s[:80])}", flush=True)
            return segments if segments else [text]

        return [text]

    @staticmethod
    def _extract_json_from_text(text: str):
        if not text:
            return None
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = text.replace("```", "").strip()

        def try_parse(candidate):
            try:
                return json.loads(candidate)
            except Exception:
                return None

        parsed = try_parse(text)
        if parsed is not None:
            return parsed

        for start_char, end_char in (("{", "}"), ("[", "]")):
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                candidate = text[start:end + 1]
                parsed = try_parse(candidate)
                if parsed is not None:
                    return parsed
        return None

    async def _ensure_preset_glossary_json(self, base_name: str, source_path: str = "") -> None:
        """Generate {base_name}_glossary.json via DeepSeek when missing."""
        glossary_path = f"{base_name}_glossary.json"
        if os.path.exists(glossary_path):
            return

        script_text = ""
        read_from = "" 
        cn_path = f"{base_name}_cn.txt"
        print(f"\n>>> Glossary 生成：检查 cn 路径是否存在: {cn_path} -> {os.path.exists(cn_path)}")
        if source_path:
            print(f">>> Glossary 生成：检查 source_path 是否存在: {source_path} -> {os.path.exists(source_path)}")
        if os.path.exists(cn_path):
            read_from = cn_path
            with open(cn_path, "r", encoding="utf-8") as f:
                script_text = f.read().strip()
        elif source_path and os.path.exists(source_path):
            read_from = source_path
            with open(source_path, "r", encoding="utf-8") as f:
                script_text = f.read().strip()

        print(f">>> Glossary 读取文件: {read_from or '(non e)'}")
        print(f">>> 文件长度: {len(script_text)} 字符")
        print(f">>> 文件内容:\n{script_text[:300]}")

        if not script_text:
            log_status("PRESET", f"No script text for glossary generation ({cn_path}).", "WARN")
            return

        yt_prompt_tpl = getattr(self.cfg, "PROMPT_CONFIG", {}).get("DEEPSEEK_YOUTUBE_PROMPT", "")
        if not yt_prompt_tpl:
            log_status("PRESET", "PROMPT_CONFIG['DEEPSEEK_YOUTUBE_PROMPT'] is empty, skip glossary generation.", "WARN")
            return

        print("\n>>> 调用 DeepSeek 进行【YouTube 参数 / Glossary 生成】...")
        yt_prompt = yt_prompt_tpl + f"\n\n{script_text}"
        yt_raw = await robust_deepseek_call(yt_prompt, max_tokens=1500, clean_output=False)

        yt_json = self._extract_json_from_text(yt_raw)
        if not yt_json or not isinstance(yt_json, dict):
            print(">>> Glossary JSON 解析失败。")
            print(f">>> 原始返回: {yt_raw}")
            log_status("PRESET", f"Glossary JSON parse failed. Raw: {(yt_raw or '')}", "WARN")
            return

        os.makedirs(os.path.dirname(glossary_path) or ".", exist_ok=True)
        with open(glossary_path, "w", encoding="utf-8") as f:
            json.dump(yt_json, f, ensure_ascii=False, indent=2)
        log_status("PRESET", f"Saved glossary: {glossary_path}", "SUCCESS")

    def _parse_glossary_cell(self, raw_value) -> dict[str, Any]:
        """Parse a raw glossary cell value into a dictionary.
        Supports JSON objects/arrays, key:value line pairs, and full-width colon separators.
        """
        text = str(raw_value or "").strip()
        if not text:
            return {}

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {"items": data}
        except (json.JSONDecodeError, TypeError, ValueError):
            log_status("PRESET", "Glossary cell is not JSON, falling back to line parsing.", "DEBUG")

        glossary_obj = safe_json_loads(text)
        if glossary_obj:
            return glossary_obj

        parsed = {}
        for line in re.split(r"\r?\n+", text):
            clean_line = line.strip()
            if not clean_line:
                continue
            if ":" in clean_line:
                key, value = clean_line.split(":", 1)
            elif "\uff1a" in clean_line:
                key, value = clean_line.split("\uff1a", 1)
            else:
                continue
            key = key.strip()
            value = value.strip()
            if key and value:
                parsed[key] = value
        return parsed if parsed else {"raw": text}

    def _load_context_from_library(self, context_path: str):
        """Load story context from an existing 0_context.json file, or build it from the library CSV.
        Saves the resulting context back to disk for subsequent pipeline stages.
        """
        if os.path.exists(context_path):
            try:
                with open(context_path, "r", encoding="utf-8") as file_obj:
                    self.context = json.load(file_obj)
                log_status("REUSE", "Loaded existing 0_context.json.", "OK")
                return
            except Exception as exc:
                log_status("REUSE", f"Failed to load 0_context.json: {exc}", "WARN")

        library_rows = []
        library_path = getattr(self.cfg, "LIBRARY_CSV_PATH", "")
        if library_path and os.path.exists(library_path):
            LibraryManager.load_from_csv(library_path)
            library_rows = [dict(row) for row in LibraryManager.matrix]

        self.context = {}
        if library_rows:
            gen_mode = getattr(self.cfg, "STORY_GENERATE_MODE", "RANDOM")
            target_idx = LibraryManager.get_target_index(self.cfg.RECORD_CSV_PATH, gen_mode)
            row_data = library_rows[target_idx]
            for key, value in row_data.items():
                val = str(value).strip()
                if not val or (gen_mode == "RANDOM" and key != "story"):
                    valid_options = [str(item.get(key, "")).strip() for item in library_rows if str(item.get(key, "")).strip()]
                    if valid_options:
                        val = random.choice(valid_options)
                self.context[key] = val
            log_status("STORY", f"Selected Row: {target_idx} | Topic: {self.context.get('story', 'N/A')[:40]}", "OK")
        else:
            log_status("STORY", "LIBRARY_CSV_PATH missing or empty. Context will rely on config/resource data.", "WARN")

        save_json_formatted(context_path, self.context)

    async def _load_preset_scripts(self) -> dict[str, Any]:
        """Load pre-written CN/EN scripts from the configured SCRIPT_RESOURCE_FILE.
        Selects the first unused row that passes all validation checks and returns
        the parsed scripts, glossary, and outlines. Raises RuntimeError if no valid row is found.
        """
        use_cn_preset = getattr(self.cfg, "USE_CN_PRESET_SCRIPT", False)
        use_en_preset = getattr(self.cfg, "USE_EN_PRESET_SCRIPT", False)
        if not use_cn_preset and not use_en_preset:
            return {}

        resource_file = getattr(self.cfg, "SCRIPT_RESOURCE_FILE", "")
        if not resource_file:
            raise RuntimeError("Preset script mode is enabled but SCRIPT_RESOURCE_FILE is empty.")
        if not os.path.exists(resource_file):
            raise FileNotFoundError(f"SCRIPT_RESOURCE_FILE not found: {resource_file}")

        state = self._load_script_resource_state(resource_file)
        selected_index = -1
        for idx, row in enumerate(state.get("rows", [])):
            print(row)
            if not self._normalize_used_flag(row.get("used", "")):
                # Skip rows that previously failed TTS safety check or other checks.
                if str(row.get("check", "")).strip().lower() == "fail":
                    print("Skipping row because check is fail")
                    continue
                
                # Skip rows that are not yet rewritten/populated if preset is required.
                if use_cn_preset and not str(row.get("rewrite_cn", "") or row.get("cn_rewrite", "") or "").strip():
                    print("Skipping row because cn_rewrite is empty")
                    continue
                if use_en_preset and not str(row.get("rewrite_en", "") or row.get("en_rewrite", "") or "").strip():
                    print("Skipping row because en_rewrite is empty")
                    continue
                selected_index = idx
                break
        if selected_index < 0:
            raise RuntimeError("No unused row (used=no) found in SCRIPT_RESOURCE_FILE.")

        row = state["rows"][selected_index]
        rewrite_cn_flag = str(row.get("rewrite_cn", "") or row.get("cn_rewrite", "") or "").strip().lower()
        if rewrite_cn_flag == "yes":
            source_path = str(row.get("path", "") or "").strip()
            base_name = os.path.splitext(source_path)[0].strip()
            print(source_path, base_name)
            if not base_name:
                raise RuntimeError("rewrite_cn=yes but path is empty in SCRIPT_RESOURCE_FILE.")
            await self._ensure_preset_glossary_json(base_name, source_path)
            glossary = {}
            if os.path.exists(f"{base_name}_glossary.json"):
                try:
                    with open(f"{base_name}_glossary.json", "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            glossary = loaded
                        elif isinstance(loaded, list):
                            for item in loaded:
                                if isinstance(item, dict):
                                    glossary.update(item)
                            if not glossary:
                                glossary = {"items": loaded}
                except Exception:
                    pass

            en_scripts = []
            if os.path.exists(f"{base_name}_en.txt"):
                with open(f"{base_name}_en.txt", "r", encoding="utf-8") as f:
                    en_scripts = self._parse_script_cell(f.read())

            cn_scripts = []
            if os.path.exists(f"{base_name}_cn.txt"):
                with open(f"{base_name}_cn.txt", "r", encoding="utf-8") as f:
                    cn_scripts = self._parse_script_cell(f.read())
        else:
            glossary = self._parse_glossary_cell(row.get("glossary", ""))
            en_scripts = self._parse_script_cell(row.get("rewrite_en", "") or row.get("en_rewrite", ""))
            cn_scripts = self._parse_script_cell(row.get("rewrite_cn", "") or row.get("cn_rewrite", ""))
        if use_en_preset and not en_scripts:
            raise RuntimeError(f"USE_EN_PRESET_SCRIPT=True but rewrite_en is empty (checked {base_name}_en.txt).")
        if use_cn_preset and not cn_scripts:
            if rewrite_cn_flag == "yes":
                raise RuntimeError(f"Excel record says 'yes', but generated script NOT FOUND or empty: {base_name}_cn.txt")
            raise RuntimeError("USE_CN_PRESET_SCRIPT=True but rewrite_cn is empty in Excel.")

        self._preset_state = state
        self._preset_selected_index = selected_index
        log_status("PRESET", f"Loaded preset row {selected_index + 2} from {os.path.basename(resource_file)}.", "SUCCESS")
        return {
            "row": row,
            "glossary": glossary,
            "en_scripts": en_scripts,
            "cn_scripts": cn_scripts,
            "outlines": en_scripts or cn_scripts,
        }

    def mark_preset_as_used(self):
        """Mark the currently selected preset script row as used in the resource file."""
        if hasattr(self, '_preset_state') and hasattr(self, '_preset_selected_index'):
            self._mark_script_resource_used(self._preset_state, self._preset_selected_index)

    def _build_scripts_from_context(self) -> tuple[list[str], list[str], dict[str, Any]]:
        """Extract EN scripts, CN scripts, and glossary directly from the loaded context dictionary."""
        candidate_en = self.context.get("rewrite_en") or self.context.get("en_script") or self.context.get("script_en") or self.context.get("story") or self.context.get("script") or ""
        candidate_cn = self.context.get("rewrite_cn") or self.context.get("cn_script") or self.context.get("script_cn") or self.context.get("story_cn") or ""
        glossary = self._parse_glossary_cell(self.context.get("glossary", ""))
        return self._parse_script_cell(candidate_en), self._parse_script_cell(candidate_cn), glossary

    def _build_local_youtube_metadata(self, en_scripts: list[str], current_story_title: str, app_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build YouTube metadata (title, description, tags, thumbnail text) for both EN and CN channels
        using the glossary file and context. Returns a tuple of (metadata_en, metadata_cn).
        """
        glossary_path = os.path.join(self.folder, "1_glossary.json")
        glossary_data = {}
        if os.path.exists(glossary_path):
            with open(glossary_path, "r", encoding="utf-8") as f:
                glossary_data = json.load(f)

        tags = []
        ds_tags = glossary_data.get("youtube_tags", [])
        if isinstance(ds_tags, list):
            for t in ds_tags:
                clean_candidate = str(t).strip()
                if clean_candidate and clean_candidate not in tags:
                    tags.append(clean_candidate)

        for candidate in (self.context.get("story", ""), self.context.get("anchor", ""), self.context.get("style", ""), app_name.replace(".py", "")):
            clean_candidate = str(candidate).strip()
            if clean_candidate and clean_candidate not in tags:
                tags.append(clean_candidate)

        title_fallback = (current_story_title or self.context.get("story") or app_name or "Story").strip()
        summary_fallback = " ".join(en_scripts[:2]) if en_scripts else title_fallback

        youtube_title = glossary_data.get("youtube_title", title_fallback)
        youtube_description = glossary_data.get("youtube_description", summary_fallback)
        thumbnail_overlay_text = glossary_data.get("thumbnail_overlay_text", youtube_title[:32])

        metadata_en = {
            "title": youtube_title,
            "thumbnail_text": thumbnail_overlay_text,
            "description": youtube_description,
            "tags": tags[:15]
        }
        
        # Dual outputs fallback (If Chinese title is used or available separately)
        title_cn = str(self.context.get("story_cn") or self.context.get("title_cn") or youtube_title).strip()
        intro_cn = glossary_data.get("intro_cn", "")
        intro_en = glossary_data.get("intro_en", "")
        metadata_cn = {
            "title": title_cn[:65] if title_cn else metadata_en["title"],
            "thumbnail_text": metadata_en["thumbnail_text"] if glossary_data.get("thumbnail_overlay_text") else (title_cn[:16] if title_cn else metadata_en["thumbnail_text"]),
            "description": metadata_en["description"] if glossary_data.get("youtube_description") else (title_cn or metadata_en["description"]),
            "tags": tags[:15],
            "intro_cn": intro_cn,
            "intro_en": intro_en,
        }

        if not intro_cn or len(intro_cn) < 4 or len(intro_cn) > 10:
            intro_cn = metadata_cn["thumbnail_text"]
        if not intro_en:
            intro_en = metadata_en["thumbnail_text"]

        return metadata_en, metadata_cn

    def _build_local_thumbnail_prompt(self) -> str:
        """Build a cinematic image generation prompt for the video thumbnail.
        Uses the glossary thumbnail_prompt if available, otherwise constructs one
        from context (anchor, character, style) with a randomised rule-of-thirds layout.
        """
        glossary_path = os.path.join(self.folder, "1_glossary.json")
        if os.path.exists(glossary_path):
            with open(glossary_path, "r", encoding="utf-8") as f:
                glossary_data = json.load(f)
            if "thumbnail_prompt" in glossary_data and glossary_data["thumbnail_prompt"]:
                return str(glossary_data["thumbnail_prompt"])

        anchor = self.context.get("anchor")
        if not anchor:
            raise RuntimeError("CRITICAL ERROR: 'anchor' is missing from context for thumbnail prompt generation.")
            
        character_desc = self.context.get("character", "") or self.context.get("char_body_and_apparel", "")
        if not character_desc:
             character_desc = "a single person"

        scene = str(self.context.get("style") or self.context.get("story") or "beautiful landscape")
        layout_options = [
            {"align": "right", "rule": "Composition Rule of Thirds: Character is positioned strictly on the far left edge. The right side remains open for text overlay."},
            {"align": "left", "rule": "Composition Rule of Thirds: Character is positioned strictly on the far right edge. The left side remains open for text overlay."},
        ]
        
        saved_align = self.context.get("thumb_text_align")
        selected_layout = next((item for item in layout_options if item["align"] == saved_align), None)
        if not selected_layout:
            selected_layout = random.choice(layout_options)
            self.context["thumb_text_align"] = selected_layout["align"]
            save_json_formatted(os.path.join(self.folder, "0_context.json"), self.context)

        return (
            f"Cinematic Wide Establishing Shot of {character_desc}. "
            f"{selected_layout['rule']} "
            f"The setting is {scene}. "
            f"Breathtaking lighting, masterpiece. [{anchor}, 16:9 aspect ratio]"
        )

    @staticmethod
    def sanitize_solo_action(action_text: str) -> str:
        """
        For single-subject scenes: sanitize_short_action has already replaced all
        opposite-gender pronouns with 'the other person' / 'the other person's'.
        This step finalises them as 'off-camera' / 'off-camera's'.
        current_gender is kept for API consistency but is not used here.
        """
        clean = action_text
        # (e.g. "Looking down at the curled figure below him.")
        # replace from that 'the' to the end of the string with 'off-camera'.
        clean = re.sub(r'\bthe\s+(?:\w+\s+)+figure\b.*', 'off-camera', clean, flags=re.IGNORECASE)
        # Must replace possessive first to avoid partial match
        clean = re.sub(r"the other person['']s", "off-camera's", clean, flags=re.IGNORECASE)
        clean = re.sub(r"the other person",      "off-camera",   clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean


    @staticmethod
    def sanitize_group_action(action_text: str) -> str:
        """Replace 'the other person' references with 'the group' for multi-subject scenes."""
        clean = action_text
        # Must replace possessive first to avoid partial match
        clean = re.sub(r"the other person['']s", "the group's", clean, flags=re.IGNORECASE)
        clean = re.sub(r"the other person",      "the group",   clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    @staticmethod
    def sanitize_short_action(action_text: str, current_gender: str) -> str:
        """Sanitize an action description for a single-gender subject by replacing opposite-gender
        pronouns and relational nouns (e.g. 'his mother', 'she') with 'the other person' references.
        """
        RELATIONAL_WORDS = r"(mother|father|sister|brother|mom|dad|wife|husband|girlfriend|boyfriend|son|daughter)"
        PREFIXES = r"(?:his|her)\s+"

        clean_action = action_text

        def replace_noun(match) -> str:
            if match.group(2):
                return "the other person's"
            return "the other person"

        # Replace prefixed compound nouns (e.g. "his mother's" -> "the other person's")
        pattern_with_prefix = rf"\b{PREFIXES}{RELATIONAL_WORDS}(['’]s)?\b"
        clean_action = re.sub(pattern_with_prefix, replace_noun, clean_action, flags=re.IGNORECASE)

        # Replace standalone relational nouns (e.g. "woman" -> "the other person")
        pattern_standalone = rf"\b{RELATIONAL_WORDS}(['’]s)?\b"
        clean_action = re.sub(pattern_standalone, replace_noun, clean_action, flags=re.IGNORECASE)

        # Step 2: Replace opposite-gender pronouns
        gender = current_gender.lower().strip()
        if gender == "male":
            clean_action = re.sub(r"\b(hers)\b", "the other person's", clean_action, flags=re.IGNORECASE)
            clean_action = re.sub(r"\b(her|she)\b", "the other person", clean_action, flags=re.IGNORECASE)
        else:
            clean_action = re.sub(r"\b(his)\b", "the other person's", clean_action, flags=re.IGNORECASE)
            clean_action = re.sub(r"\b(him|he)\b", "the other person", clean_action, flags=re.IGNORECASE)

        clean_action = re.sub(r"the other person['’]s\s*['’]s", "the other person's", clean_action, flags=re.IGNORECASE)
        clean_action = re.sub(r"the other person\s*['’]s", "the other person's", clean_action, flags=re.IGNORECASE)
        
        clean_action = re.sub(r'\s+', ' ', clean_action).strip()

        return clean_action

    _YOUTUBE_GLOSSARY_KEYS = frozenset({
        "youtube_title", "youtube_description", "youtube_tags",
        "thumbnail_prompt", "thumbnail_overlay_text",
        "intro_cn", "intro_en", "char_body_and_apparel", "char_facial_details",
    })

    @classmethod
    def _extract_target_chars(cls, glossary: dict) -> dict[str, str]:
        """Return name->traits map only when glossary actually defines characters."""
        if not isinstance(glossary, dict):
            return {}
        raw = glossary.get("characters")
        if isinstance(raw, dict) and raw:
            return {k: str(v) for k, v in raw.items()}
        if isinstance(raw, list):
            merged = {}
            for item in raw:
                if isinstance(item, dict):
                    merged.update({k: str(v) for k, v in item.items()})
            if merged:
                return merged
        if glossary and not cls._YOUTUBE_GLOSSARY_KEYS.intersection(glossary.keys()):
            if all(isinstance(v, str) for v in glossary.values()):
                return {k: str(v) for k, v in glossary.items()}
        return {}

    @staticmethod
    def _normalize_scene_environment(environment: str) -> str:
        environment = (environment or "").strip()
        if not environment:
            raise RuntimeError("assemble_human_prompt: missing 'environment' in Gemma JSON output.")
        bad = ("unspecified", "none", "not visible", "no specific", "unknown")
        if any(kw in environment.lower() for kw in bad):
            environment = random.choice(RANDOM_ENVIRONMENTS)
        return environment

    def assemble_human_prompt_simple(self, extracted_data: dict) -> tuple[str, int]:
        """Build image prompt from Gemma JSON when no glossary character list (DOAC-style)."""
        subject_count = int(extracted_data.get("subject_count", 0) or 0)
        characters = extracted_data.get("characters") or []
        environment = self._normalize_scene_environment(extracted_data.get("environment", ""))

        pronoun_label = {
            "him": "a male silhouette", "he": "a male silhouette",
            "her": "a female silhouette", "she": "a female silhouette",
        }

        if subject_count == 0 or not characters:
            log_status("STORY", "Scene-only prompt (no character list).", "INFO")
            return f"[Scene only] Environment: {environment}", 0

        char_segments = []
        for char in characters:
            if not isinstance(char, dict):
                continue
            name = (char.get("name") or "").strip().lower()
            action = (char.get("action") or "").strip().rstrip(".") or "still pose"
            clothing = (char.get("clothing") or "").strip()
            if any(kw in action.lower() for kw in ("not visible", "no visible", "none visible")):
                continue
            label = pronoun_label.get(name, "a solitary figure")
            segment = label
            if clothing and "empty" not in clothing.lower():
                segment += f", wearing {clothing}"
            segment += f", {action}"
            char_segments.append(segment)

        if not char_segments:
            log_status("STORY", "Gemma returned no usable characters; using scene-only prompt.", "WARN")
            return f"[Scene only] Environment: {environment}", 0

        subject_count = len(char_segments)
        if subject_count == 1:
            final_prompt = f"[Subject Count: 1 person only] {char_segments[0]}. Environment: {environment}"
        else:
            joined = ". ".join(char_segments)
            final_prompt = (
                f"[Subject Count: {subject_count} people only] {joined}. "
                f"Environment: {environment}"
            )
        log_status("STORY", "Simple human prompt assembled (no glossary).", "OK")
        return final_prompt, subject_count

    @staticmethod 
    def choose_random_clothing(gender: str, current_string: str) -> str:
        """Pick a random clothing item for the given gender that is not already present in current_string.
        Falls back to a random choice if all items have been used.
        """
        pool = FEMALE_OUTFITS if "female" in gender else MALE_OUTFITS
        shuffled = random.sample(pool, len(pool))  # randomised copy, original unchanged
        for item in shuffled:
            if item not in current_string:
                return item
        return random.choice(pool)  # fallback: all items used, just pick one

    def assemble_human_prompt(self, extracted_data: dict, target_chars: dict) -> (str, int):
        """Assemble a final English image generation prompt from Gemma4 JSON output and the glossary.
        Resolves character names, sanitizes actions for gender consistency, and applies
        solo/group action rules. Returns the assembled prompt string and the subject count.
        """

        subject_count = extracted_data.get("subject_count", 0)
        characters = extracted_data.get("characters", [])
        environment = self._normalize_scene_environment(extracted_data.get("environment", ""))
            
        if subject_count == 0 or not characters:
            log_status("STORY", "No visible characters found in scene, random pick one character for thumbnail.", "WARN")
            random_char_name = random.choice(list(target_chars.keys()))
            random_clothing = self.choose_random_clothing('female' if 'female' in target_chars[random_char_name] else 'male', "")
            final_prompt = (
                f"[Subject Count: {1} person only] "
                f"{target_chars[random_char_name]}, WEARING {random_clothing}, {random.choice(RANDOM_ACTIONS)}. "
                f"Environment: {environment}"
            )
            subject_count = 1
        else:
            char_segments = []
            
            for char in characters:
                name = char.get("name", "").strip()
                raw_action = char.get("action", "").strip().rstrip(".")
                extracted_clothing = char.get("clothing", "").strip().rstrip(".")

                if not name:
                    log_status("STORY", f"Character name is empty, skipping.", "WARN")
                    continue

                # Skip if Gemma explicitly says character is not visible
                _NOT_VISIBLE_KEYWORDS = ("not visible", "no visible", "none visible")
                if any(kw in raw_action.lower() for kw in _NOT_VISIBLE_KEYWORDS):
                    continue

                # Fallback: resolve pronouns to actual character name via glossary gender tag
                _PRONOUN_GENDER = {
                    "him": "male", "he": "male", "他": "male",
                    "her": "female", "she": "female", "她": "female",
                }
                if (gender_hint := _PRONOUN_GENDER.get(name.lower())):
                    name = next(
                        (k for k, v in target_chars.items() if gender_hint in v.lower()),
                        name  # keep original if no match found
                    )
                
                if name not in target_chars:
                    log_status("STORY", f"Character '{name}' not found in glossary, skipping.", "WARN")
                    continue

                traits = target_chars[name]
                action = raw_action or random.choice(RANDOM_ACTIONS)
                action = self.sanitize_short_action(action, 'female' if "female" in traits else 'male')
                random_clothing = self.choose_random_clothing('female' if "female" in traits else 'male', str(char_segments))
                extracted_clothing = extracted_clothing or random_clothing
                if not extracted_clothing or 'empty' in extracted_clothing.lower():
                    extracted_clothing = random_clothing

                char_segments.append(f"{traits}, WEARING {extracted_clothing}, {action}")
                
            if not char_segments:
                # Gemma returned characters but none matched glossary (e.g., empty names).
                # Fall back to random character pick, same as subject_count == 0 case.
                log_status("STORY", "No characters matched glossary after parsing, using random character fallback.", "WARN")
                random_char_name = random.choice(list(target_chars.keys()))
                random_clothing = self.choose_random_clothing('female' if 'female' in target_chars[random_char_name] else 'male', "")
                final_prompt = (
                    f"[Subject Count: 1 person only] "
                    f"{target_chars[random_char_name]}, WEARING {random_clothing}, {random.choice(RANDOM_ACTIONS)}. "
                    f"Environment: {environment}"
                )
            else:
                spatial_relation = "" # " Spatial Relation: standing apart, clearly separated. " if subject_count == 2 else " "
                subject_count = len(char_segments)
            
                if subject_count == 1:
                    char_segments[0] = self.sanitize_solo_action(char_segments[0])
                elif subject_count > 2:
                    char_segments = [self.sanitize_group_action(seg) for seg in char_segments]
                    
                final_prompt = (
                    f"[Subject Count: {subject_count} {'person' if subject_count == 1 else 'people'} only] "
                    f"{'. '.join(char_segments)}.{spatial_relation}"
                    f"Environment: {environment}"
                )

        
        log_status("STORY", "Human prompt assembled successfully.", "OK")
        return final_prompt, subject_count

        
    async def _generate_cinematic_prompt_single(self, text: str, idx: int, glossary: dict = None) -> str:
        """Generate a single cinematic image prompt for a given script segment.
        Uses a template if USE_IMAGE_TEMPLATE is enabled, otherwise calls Gemma4 to analyse
        the scene and assembles a structured prompt from the JSON output.
        """
        if glossary is None: glossary = {}
        if not text:
            raise RuntimeError("Empty text cannot generate image prompt.")

        safety_constraint = "accurate human anatomy, highly detailed, dramatic composition. "
        if getattr(self.cfg, "USE_IMAGE_TEMPLATE", True):
            log_status("USE_IMAGE_TEMPLATE", "Using image template.", "OK")

            scene = str(self.context.get("style") or self.context.get("story") or "serene environment").strip(" .")
            action = "resting peacefully"
            emotion = str(self.context.get("emotion") or "calm").strip(" .")
            anchor = self.context.get("anchor") or ""
            char_body = self.context.get("char_body_and_apparel", "").strip(" .") or self.context.get("character", "")
            lighting = random.choice(["volumetric lighting with god rays", "soft moonlight casting long shadows", "warm candlelight flickering", "cinematic chiaroscuro lighting"])
            composition = random.choice(["strong depth of field with blurred foreground elements", "perfect symmetry", "rule of thirds composition", "wide cinematic framing"])
            prompt = (
                f"Cinematic Medium Shot. Environment: {scene}. {composition}. "
                f"Action: {action}. Atmosphere: {emotion}. Lighting: {lighting}. "
                f"Character: {char_body}. [{anchor}]"
            )
            return re.sub(r"\s+", " ", f"{safety_constraint}{prompt}").strip()
        try:
            template = getattr(self.cfg, "PROMPT_CONFIG", {}).get("SCENE_PROMPT_GEMMA4", "")
            target_chars = self._extract_target_chars(glossary)
            has_character_list = bool(target_chars)

            if template:
                prompt = template.replace("{text}", text)
                if "{character_list}" in prompt:
                    if has_character_list:
                        prompt = prompt.replace(
                            "{character_list}", ", ".join(target_chars.keys())
                        )
                    else:
                        prompt = prompt.replace("{character_list}", "")
            elif has_character_list:
                prompt = f"Text: {text}\nCharacter List: {', '.join(target_chars.keys())}"
            else:
                prompt = text

            if has_character_list:
                img_system_prompt = (
                    "You are a cinematic storyboard analyzer. Match characters from the provided "
                    "character list when possible. Output ONLY valid raw JSON."
                )
                log_status("GEMMA4", f"Gemma prompt with character list ({len(target_chars)}).", "INFO")
            else:
                img_system_prompt = (
                    "You are an image-prompt assistant. Read the script snippet and output ONE still-frame "
                    "scene as strict raw JSON. No markdown."
                )
                log_status("GEMMA4", "Gemma prompt without character list (script only).", "INFO")

            gemma_prompt = await robust_gemma4_call(
                prompt=prompt,
                system_prompt=img_system_prompt,
                max_tokens=400,
                clean_output=False,
            )

            if not gemma_prompt:
                raise RuntimeError("Gemma4 returned None or empty response.")

            raw_output = gemma_prompt.strip()
            raw_output = re.sub(r'^```json\s*|^```\s*|\s*```$', '', raw_output, flags=re.MULTILINE).strip()

            if not raw_output:
                raise RuntimeError("Gemma4 produced an empty output.")

            repaired = re.sub(r'\}\s*\n(\s*)\{', r'},\n\1{', raw_output)
            repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

            try:
                extracted_data = json.loads(repaired)
            except json.JSONDecodeError as json_err:
                raise RuntimeError(
                    f"Gemma4 did not return valid JSON (after repair): {json_err}. "
                    f"Raw output: {raw_output[:300]}"
                )

            if has_character_list:
                human_prompt, subject_count = self.assemble_human_prompt(extracted_data, target_chars)
            else:
                human_prompt, subject_count = self.assemble_human_prompt_simple(extracted_data)
            # Strip any Chinese characters that may have leaked into the final assembled English prompt
            human_prompt = re.sub(r'[\u4e00-\u9fa5]', '', human_prompt).strip()
            if not human_prompt:
                raise RuntimeError("assemble_human_prompt returned empty string. Cannot build final prompt.")
            
            chosen_shot = random.choice(SHOT_TYPES)

            if subject_count > 1 and (chosen_shot == "Close-up" or chosen_shot == "Extreme-close-up"):
                chosen_shot = "Medium-shot"

            # 3. Mode Selection & Assembly
            if self.cfg.PIPELINE_FLAGS.get("use_runninghub_zimage", False):
                # Strict context validation for ZImage mode
                if "zimage_anchor_main" not in self.context or "zimage_anchor_specific" not in self.context or   "zimage_anchor_lighting" not in self.context:
                    raise RuntimeError("CRITICAL ERROR: ZImage mode is active but required feature keys are missing from context. Check build_full_story.")
                
                feature_main = self.context["zimage_anchor_main"]
                feature_specific = self.context["zimage_anchor_specific"]
                feature_lighting = self.context["zimage_anchor_lighting"]
                
            else:
                # Strict context validation for Standard mode
                if "anchor" not in self.context or "style" not in self.context:
                    raise RuntimeError("CRITICAL ERROR: Standard mode is active but 'anchor' or 'style' is missing from context. No fallback allowed.")

                urban_anchor = getattr(self.cfg, "IMAGE_PROMPT_ANCHORS", {}).get("MODERN_URBAN", "")
                feature_main = self.context["anchor"]
                feature_specific = self.context["style"] + urban_anchor       
                feature_lighting = random.choice(LIGHTING_MOODS)
         
            full_prompt = f"{feature_main}. {feature_specific}. {feature_lighting}. {chosen_shot}. {human_prompt}"
            return re.sub(r"\s+", " ", full_prompt).strip()

        except Exception as e:
            # Re-raise to terminate the process as per "Fail Fast" requirement
            log_status("GEMMA4", f"CRITICAL FAILURE: Gemma4 image prompt generation failed: {e}", "ERROR")
            raise e

        # Removed fallback return to ensure process terminates on failure

    async def build_full_story(self) -> tuple[list[str], list[str], list[str]]:
        """Build the complete story pipeline: load context, resolve scripts (preset or context-based),
        run TTS safety checks, and generate cinematic image prompts.
        Returns (en_scripts, cn_scripts, img_prompts).
        """
        context_path = os.path.join(self.folder, "0_context.json")
        self._load_context_from_library(context_path)

        # 1. Immediate Style Locking: Use ART_STYLE_DETAILS for consistency
        if self.cfg.PIPELINE_FLAGS.get("use_runninghub_zimage", False) and not self.context.get("zimage_anchor"):
            style_details = getattr(self.cfg, "ART_STYLE_DETAILS", {})
            if style_details:
                selected_anchor = random.choice(list(style_details.keys()))
                self.context["zimage_anchor"] = selected_anchor
                self.context["zimage_anchor_main"] = style_details[selected_anchor]["main_feature"].rstrip('.')
                
                # Also lock a specific artistic feature for visual consistency
                s_data = style_details.get(selected_anchor, {})
                features = s_data.get('specific_feature', {})
                if isinstance(features, dict) and features:
                    selected_feat_label = random.choice(list(features.keys()))
                    self.context["zimage_anchor_specific"] = features[selected_feat_label].rstrip('.')

                    lighting_pool = s_data.get("lighting")
                    if not lighting_pool:
                        raise RuntimeError(f"CRITICAL CONFIG ERROR: Style '{selected_anchor}' is missing 'lighting'. Cannot initialize ZImage pipeline.")
                    self.context["zimage_anchor_lighting"] = random.choice(lighting_pool)

                    log_status("STORY", f"Locked visual style: {selected_anchor} (Feature: {selected_feat_label}, Lighting: {self.context['zimage_anchor_lighting']})", "OK")
                else:
                    raise RuntimeError(f"CRITICAL CONFIG ERROR: Style '{selected_anchor}' is missing 'specific_feature'. Cannot initialize ZImage pipeline.")

                
                save_json_formatted(os.path.join(self.folder, "0_context.json"), self.context)
            else:
                raise RuntimeError("CRITICAL CONFIG ERROR: ART_STYLE_DETAILS is missing or empty in app configuration. Required for ZImage mode.")

        en_json = os.path.join(self.folder, "2_en_scripts.json")
        cn_json = os.path.join(self.folder, "3_cn_scripts.json")
        outline_json = os.path.join(self.folder, "1_outlines.json")
        glossary_json = os.path.join(self.folder, "1_glossary.json")

        # Reuse logic: if the script JSON files already exist and reuse flags are enabled, load them directly.
        reuse_en = getattr(self.cfg, "REUSE_OPENAI_SCRIPT", False)
        reuse_cn = getattr(self.cfg, "REUSE_DEEPSEEK_SCRIPT", False)
        reuse_outline = getattr(self.cfg, "REUSE_GEMINI_OUTLINE", False)

        scripts_loaded_from_json = False
        if reuse_en and os.path.exists(en_json) and reuse_cn and os.path.exists(cn_json):
            try:
                with open(en_json, "r", encoding="utf-8") as f: en_scripts = json.load(f)
                with open(cn_json, "r", encoding="utf-8") as f: cn_scripts = json.load(f)
                outlines = []
                if os.path.exists(outline_json):
                    with open(outline_json, "r", encoding="utf-8") as f: outlines = json.load(f)
                glossary = {}
                if os.path.exists(glossary_json):
                    with open(glossary_json, "r", encoding="utf-8") as f: glossary = json.load(f)
                
                log_status("REUSE", "Loaded existing scripts from JSON files.", "OK")
                
                # Sync outlines back into context.
                if outlines: self.context["outlines"] = outlines
                if cn_scripts: self.context["story_cn"] = cn_scripts[0][:80] if cn_scripts else ""
                scripts_loaded_from_json = True
            except Exception as exc:
                log_status("REUSE", f"Failed to load existing script JSONs: {exc}", "WARN")

        if not scripts_loaded_from_json:
            preset_data = await self._load_preset_scripts()
            if preset_data:
                self.context["script_resource_file"] = getattr(self.cfg, "SCRIPT_RESOURCE_FILE", "")
                self.context["script_resource_row"] = preset_data.get("row", {})
                outlines = list(preset_data.get("outlines", []))
                glossary = dict(preset_data.get("glossary", {}))
                en_scripts = list(preset_data.get("en_scripts", []))
                cn_scripts = list(preset_data.get("cn_scripts", []))


            else:
                en_scripts, cn_scripts, glossary = self._build_scripts_from_context()
                outlines = list(en_scripts or cn_scripts)
                log_status("STORY", "Simple runner is using local context scripts only.", "INFO")
            
            if not en_scripts and not cn_scripts:
                raise RuntimeError("No local scripts found for simple runner.")

            resource_row = self.context.get("script_resource_row", {})
            title_raw = resource_row.get("title", "")
            if title_raw:
                self.context["story"] = title_raw.split("_", 1)[-1].strip() if "_" in title_raw else title_raw.strip()
            elif outlines and not self.context.get("story"):
                self.context["story"] = outlines[0][:80]

            if glossary:
                char_body = glossary.get("char_body_and_apparel", "")
                char_face = glossary.get("char_facial_details", "")
                if not char_body and "character" in glossary:
                    char_body = glossary.get("character", "")
                self.context["char_body_and_apparel"] = char_body
                self.context["char_facial_details"] = char_face
                combined_char = ""
                if char_body:
                    combined_char += char_body
                if char_face:
                    combined_char += f", {char_face}"
                if combined_char:
                    self.context["character"] = combined_char
                elif "characters" in glossary:
                    chars = glossary.get("characters", [])
                    if isinstance(chars, list):
                        char_dict = {}
                        for item in chars:
                            if isinstance(item, dict):
                                char_dict.update(item)
                        self.context["character"] = char_dict
                    else:
                        self.context["character"] = chars

            save_json_formatted(context_path, self.context)
            save_json_formatted(outline_json, outlines)
            save_json_formatted(glossary_json, glossary)
            self.flattened_metadata = []
            save_json_formatted(os.path.join(self.folder, "2_metadata.json"), self.flattened_metadata)

            en_scripts, cn_scripts = merge_dual_scripts(en_scripts, cn_scripts)

            save_json_formatted(en_json, en_scripts)
            save_json_formatted(cn_json, cn_scripts)
            # Save an extra copy of the rewritten scripts for inspection.
            save_json_formatted(os.path.join(self.folder, "2_en_scripts_rewritten.json"), en_scripts)
            save_json_formatted(os.path.join(self.folder, "3_cn_scripts_rewritten.json"), cn_scripts)

        # ==========================================
        # CN scripts TTS safety inspection (hard gate).
        # ==========================================
        if cn_scripts and not MODEL_CONFIG.get("USE_AZURE_TTS", False):
            os.makedirs(os.path.join(self.folder, "error_scripts"), exist_ok=True)
            failed_scripts = []
            
            for idx, cn_text in enumerate(cn_scripts):
                is_safe, error_msg = inspect_tts_safety(f"{os.path.basename(self.folder)}_seg{idx:02d}", cn_text)
                if not is_safe:
                    failed_scripts.append((idx, cn_text, error_msg))
                    log_status("TTS_SAFETY", f"Seg {idx}: TTS safety check failed - {error_msg}", "WARN")
            
            # If any scripts fail inspection, write a review file and stop the pipeline.
            if failed_scripts:
                review_path = os.path.join(self.folder, "error_scripts", "tts_safety_review.txt")
                with open(review_path, "w", encoding="utf-8") as f:
                    f.write(f"Workspace: {os.path.basename(self.folder)}\n")
                    f.write(f"Checked at: {datetime.now().isoformat()}\n")
                    f.write(f"Failed count: {len(failed_scripts)}/{len(cn_scripts)}\n")
                    f.write("\n" + "="*80 + "\n\n")
                    
                    for idx, text, error_msg in failed_scripts:
                        f.write(f"Segment {idx}\n")
                        f.write(f"Reason: {error_msg}\n")
                        f.write(f"Script text:\n{text}\n")
                        f.write("\n" + "-"*80 + "\n\n")
                
                # Update the Excel file directly if this was loaded from a preset
                try:
                    if hasattr(self, "_preset_selected_index"):
                        resource_file = getattr(self.cfg, "SCRIPT_RESOURCE_FILE", "")
                        if resource_file and os.path.exists(resource_file):
                            import pandas as pd
                            df = pd.read_excel(resource_file)
                            # the DataFrame index maps directly to self._preset_selected_index
                            df.at[self._preset_selected_index, 'check'] = 'fail'
                            df.to_excel(resource_file, index=False)
                            log_status("TTS_SAFETY", f"Marked check=fail for row {self._preset_selected_index + 2} in {os.path.basename(resource_file)}.", "ERROR")
                except Exception as e:
                    log_status("TTS_SAFETY", f"Failed to mark check=fail in Excel: {e}", "WARN")

                log_status("TTS_SAFETY", f"TTS safety check failed for {len(failed_scripts)}/{len(cn_scripts)} scripts. See {review_path}", "ERROR")
                raise RuntimeError(f"TTS safety inspection failed for {len(failed_scripts)}/{len(cn_scripts)} CN scripts. Check {review_path} for details.")

        img_prompt_path = os.path.join(self.folder, "4_img_prompts.json")
        img_prompts = []
        if getattr(self.cfg, "REUSE_IMAGE_PROMPT", False) and os.path.exists(img_prompt_path):
            try:
                with open(img_prompt_path, "r", encoding="utf-8") as file_obj:
                    img_prompts = json.load(file_obj)
                log_status("REUSE", "Loaded 4_img_prompts.json.", "OK")
            except (OSError, json.JSONDecodeError) as exc:
                log_status("REUSE", f"Failed to load 4_img_prompts.json: {exc}", "WARN")
                img_prompts = []

        if not img_prompts:
            if getattr(self.cfg, "USE_CN_PRESET_SCRIPT", False) and cn_scripts:
                source_scripts = cn_scripts
            else:
                source_scripts = en_scripts
                
            log_status("STORY", f"Generating cinematic image prompts using {'Chinese' if source_scripts == cn_scripts else 'English'} scripts...", "INFO")
            
            prompt_tasks = [self._generate_cinematic_prompt_single(text, idx, glossary) for idx, text in enumerate(source_scripts)]
            results = await asyncio.gather(*prompt_tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result
                img_prompts.append(result)
            save_json_formatted(img_prompt_path, img_prompts)

        return en_scripts, cn_scripts, img_prompts

    async def generate_youtube_assets(self, en_scripts: list[str], current_story_title: str, app_name: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        """Generate YouTube metadata (EN + CN) and a thumbnail image prompt.
        Loads from disk if already generated, otherwise builds and saves them.
        Returns (metadata_en, metadata_cn, thumbnail_prompt_with_anchor).
        """
        log_status("SEO", "Generating YouTube metadata and thumbnail prompt locally...", "INFO")
        meta_en_path = os.path.join(self.folder, "youtube_metadata_en.json")
        meta_cn_path = os.path.join(self.folder, "youtube_metadata_cn.json")
        prompt_path = os.path.join(self.folder, "thumbnail_prompt.txt")
        metadata_en, metadata_cn, thumb_prompt = {}, {}, ""

        if os.path.exists(meta_en_path) and os.path.exists(meta_cn_path):
            try:
                with open(meta_en_path, "r", encoding="utf-8") as file_obj:
                    metadata_en = json.load(file_obj)
                with open(meta_cn_path, "r", encoding="utf-8") as file_obj:
                    metadata_cn = json.load(file_obj)
                log_status("REUSE", "Loaded existing YouTube metadata.", "OK")
            except (OSError, json.JSONDecodeError) as exc:
                log_status("REUSE", f"Failed to load existing YouTube metadata: {exc}", "WARN")
                metadata_en, metadata_cn = {}, {}

        if not metadata_en:
            metadata_en, metadata_cn = self._build_local_youtube_metadata(en_scripts, current_story_title, app_name)
            save_json_formatted(meta_en_path, metadata_en)
            save_json_formatted(meta_cn_path, metadata_cn)

        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as file_obj:
                    thumb_prompt = file_obj.read().strip()
                log_status("REUSE", "Loaded thumbnail_prompt.txt.", "OK")
            except OSError as exc:
                log_status("REUSE", f"Failed to load thumbnail_prompt.txt: {exc}", "WARN")
                thumb_prompt = ""

        if not thumb_prompt:
            thumb_prompt = self._build_local_thumbnail_prompt()
            with open(prompt_path, "w", encoding="utf-8") as file_obj:
                file_obj.write(thumb_prompt)
            log_status("SEO", "Thumbnail prompt generated locally.", "OK")

        # Determine the style anchor for the thumbnail
        zimage_enabled = self.cfg.PIPELINE_FLAGS.get("use_runninghub_zimage", False)
        style_details = getattr(self.cfg, "ART_STYLE_DETAILS", {})
        
        # Double-check locking here in case build_full_story was skipped or loaded from old context
        if zimage_enabled and not self.context.get("zimage_anchor") and style_details:
            selected_style = random.choice(list(style_details.keys()))
            self.context["zimage_anchor"] = selected_style
            self.context["zimage_anchor_main"] = style_details[selected_style]["main_feature"]
            
            # Ensure feature is also locked
            s_data = style_details.get(selected_style, {})
            features = s_data.get('specific_feature', {})
            if isinstance(features, dict) and features:
                selected_feat_label = random.choice(list(features.keys()))
                self.context["zimage_anchor_specific"] = features[selected_feat_label]
            else:
                raise RuntimeError(f"CRITICAL CONFIG ERROR: Style '{selected_style}' is missing 'specific_feature' for thumbnail generation.")
            
            lighting_pool = s_data.get("lighting")
            if not lighting_pool:
                raise RuntimeError(f"CRITICAL CONFIG ERROR: Style '{selected_style}' is missing 'lighting'. Cannot initialize ZImage pipeline.")
            self.context["zimage_anchor_lighting"] = random.choice(lighting_pool)

            log_status("SEO", f"Initialized visual style for thumbnail: {selected_style} (Feature: {selected_feat_label}, Lighting: {self.context['zimage_anchor_lighting']})", "INFO")
            save_json_formatted(os.path.join(self.folder, "0_context.json"), self.context)

        locked_style_key = self.context.get("zimage_anchor")
        if zimage_enabled:
            if not locked_style_key:
                raise RuntimeError("CRITICAL ERROR: ZImage mode is enabled but 'zimage_anchor' is missing from context.")
                            
            try:
                feature_main = self.context["zimage_anchor_main"]
                feature_specific = self.context["zimage_anchor_specific"]
                feature_lighting = self.context["zimage_anchor_lighting"]
            except KeyError as e:
                raise RuntimeError(f"CRITICAL ERROR: ZImage mode is active but required feature key {e} is missing from context.")
            
            anchor = f"{feature_main}, {feature_specific}, {feature_lighting}"
        else:
            if "anchor" not in self.context:
                raise RuntimeError("CRITICAL ERROR: Standard mode is active but 'anchor' is missing from context.")
            anchor = self.context["anchor"]

        return metadata_en, metadata_cn, f"[{anchor}] {thumb_prompt}"


def aggressive_markdown_cleaner(raw_text: str) -> str:
    """Aggressively strip markdown bold tags and hash headers to prevent TTS from reading them."""
    # 1. Core logic: delete all content surrounded by double asterisks (including asterisks)
    clean_text = re.sub(r'\*\*.*?\*\*', '', raw_text)
    
    # 2. Clean up any remaining markdown header hash symbols
    clean_text = clean_text.replace("#", "")
    
    # 3. Handle excessive newlines generated by removing headers
    clean_text = re.sub(r'\n\s*\n', '\n', clean_text)
    
    return clean_text.strip()


class MediaPipeline:
    def __init__(self, folder: str, segments: list[MediaSegment], reuse_tts: bool = False, channel_name_en: str = "", channel_name_cn: str = "", overlays: str = "", reuse_image: bool = False, reuse_video: bool = False, ambience: str = "", bgm: str = "", use_gemma4_optimize_tts: bool = False, prompt_config: Optional[dict[str, Any]] = None, render_backend: str = "local", render_config: Optional[dict[str, Any]] = None):
        """Initialize the MediaPipeline with workspace folder, media segments, and all asset/reuse settings."""
        self.folder = folder
        self.segments = segments
        self.reuse_tts = reuse_tts
        self.channel_name_en = channel_name_en
        self.channel_name_cn = channel_name_cn
        self.overlays = overlays or ""
        self.reuse_image = reuse_image
        self.reuse_video = reuse_video
        self.ambience = ambience or ""
        self.bgm = bgm or ""
        self.use_gemma4_optimize_tts = use_gemma4_optimize_tts
        self.prompt_config = prompt_config or {}
        self.render_backend = render_backend
        self.render_config = render_config or {}
        self.ASSEMBLY_CONFIG: Dict[str, Any] = {
            # Video processing and rendering presets
            "video_codec_gpu": "h264_nvenc",
            "video_codec_cpu": "libx264",
            "preset_gpu": "p4",
            "preset_cpu": "fast",
            "bitrate": "5M",
            "crf": "23",
            "pixel_format": "yuv420p",
            "resolution": "1920:1080",
            "fps": 30,
            
            # Watermark and font
            "font_path": "C:/Windows/Fonts/msyhbd.ttc",
            
            # Final audio mixdown parameters (last line of defense against sidechain crashes)
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "sample_rate": "48000"
        }

    def _encode_video_sync(self, img_path: str, duration: float, clip_path: str, movement: str):
        """Encode a single image into a video clip with optional overlay and camera movement.
        Picks a random overlay file from the overlays directory if configured.
        Returns True on success, False on failure.
        """
        overlay_path = None
        if self.overlays:
            files_in_dir = [os.path.join(self.overlays, f) for f in os.listdir(self.overlays) if os.path.isfile(os.path.join(self.overlays, f))]
            if files_in_dir:
                overlay_path = random.choice(files_in_dir)

        success = render_video_multi_segment_sync(
            img_path=img_path,
            duration=duration,
            clip_path=clip_path,
            start_movement=movement,
            overlay_path=overlay_path,
        )
        if success:
            return True
        else:
            log_status("FFMPEG", f"Multi-segment encoding failed for {os.path.basename(clip_path)}", "ERROR")
            return False

    def _encode_video_github_sync(self, img_path: str, duration: float, clip_path: str, movement: str):
        """Render one clip through GitHub Actions, with retries."""
        retry_attempts = max(1, int(self.render_config.get("RETRY_ATTEMPTS", 2) or 2))
        task_id = os.path.splitext(os.path.basename(clip_path))[0]
        for attempt in range(1, retry_attempts + 1):
            SystemController.check_stop_signal()
            ok = encode_video_github_sync(
                img_path=img_path,
                duration=duration,
                clip_path=clip_path,
                movement=movement,
                github_config=self.render_config,
                watermark=self.channel_name_cn if not NVENC_AVAILABLE else "",
            )
            if ok:
                if attempt > 1:
                    log_status("GITHUB", f"[{task_id}] Render recovered on retry attempt {attempt}/{retry_attempts}.", "SUCCESS")
                return True
            if attempt < retry_attempts:
                log_status("GITHUB", f"[{task_id}] Render failed or timed out; retrying ({attempt + 1}/{retry_attempts})...", "WARN")
                if os.path.exists("stop.txt"):
                    log_status("GITHUB", f"[{task_id}] Stop signal detected, aborting retries.", "WARN")
                    return False
        log_status("GITHUB", f"[{task_id}] Render failed after {retry_attempts} attempt(s).", "ERROR")
        return False

    def _encode_video_colab_sync(self, img_path: str, duration: float, clip_path: str, movement: str):
        """Render one clip on the Colab worker via the shared Google Drive folder."""
        SystemController.check_stop_signal()
        return encode_video_colab_sync(img_path, duration, clip_path, movement, self.render_config)

    def _encode_video(self, img_path: str, duration: float, clip_path: str, movement: str):
        """Dispatch a clip render to the configured backend (local | github | colab)."""
        if self.render_backend == "github":
            return self._encode_video_github_sync(img_path, duration, clip_path, movement)
        if self.render_backend == "colab":
            return self._encode_video_colab_sync(img_path, duration, clip_path, movement)
        return self._encode_video_sync(img_path, duration, clip_path, movement)

    async def _process_segment_dual(self, seg: MediaSegment):
        """Process a single media segment: generate TTS audio for both EN and CN tracks,
        render the base video clip from the image, then split it into per-language clips
        trimmed to each audio duration.
        """
        if not seg.en_text and not seg.cn_text:
            log_status("MEDIA", f"Seg {seg.index} aborted: both texts are empty.", "WARN")
            return

        en_raw_wav = os.path.join(self.folder, "audio", f"s{seg.index:03d}_en_raw.mp3")
        cn_raw_wav = os.path.join(self.folder, "audio", f"s{seg.index:03d}_cn_raw.mp3")
        base_vid_path = os.path.join(self.folder, "video", f"s{seg.index:03d}_base.mp4")
        en_vid_path = os.path.join(self.folder, "video", f"s{seg.index:03d}_en.mp4")
        cn_vid_path = os.path.join(self.folder, "video", f"s{seg.index:03d}_cn.mp4")

        all_audio_exist = os.path.exists(seg.en_audio_path) and os.path.exists(seg.cn_audio_path)
        has_base_video = os.path.exists(base_vid_path)
        has_split_video = os.path.exists(en_vid_path) and os.path.exists(cn_vid_path)
        if self.reuse_tts and self.reuse_video and all_audio_exist and has_split_video:
            seg.en_duration = len(AudioSegment.from_file(seg.en_audio_path)) / 1000.0
            seg.cn_duration = len(AudioSegment.from_file(seg.cn_audio_path)) / 1000.0
            seg.en_video_path = en_vid_path
            seg.cn_video_path = cn_vid_path
            seg.is_valid_en = True
            seg.is_valid_cn = True
            return

        async def do_en_audio():
            if not seg.en_text.strip():
                return 0.0
            if not (self.reuse_tts and os.path.exists(seg.en_audio_path)):
                if not os.path.exists(en_raw_wav):
                    audio_text = apply_ssml_pauses(seg.en_text)
                    async with ConcurrencyManager.TTS_SEM:
                        await robust_tts_call(audio_text, MODEL_CONFIG["VOICE_EN"], en_raw_wav)
                return await asyncio.to_thread(master_audio_sync, en_raw_wav, seg.en_audio_path)
            return len(AudioSegment.from_file(seg.en_audio_path)) / 1000.0

        async def do_cn_audio():
            if not seg.cn_text.strip():
                return 0.0
            if not (self.reuse_tts and os.path.exists(seg.cn_audio_path)):
                if not os.path.exists(cn_raw_wav):
                    cn_text_for_tts = seg.cn_text
                    # Optimize TTS text using Gemma4 if enabled
                    if self.use_gemma4_optimize_tts:
                        tts_optimize_prompt = self.prompt_config.get("TTS_OPTIMIZE_GEMMA4", "")
                        if tts_optimize_prompt:
                            try:
                                format_kwargs = {"text": seg.cn_text}
                                optimize_prompt = tts_optimize_prompt.format(**format_kwargs) if "{" in tts_optimize_prompt else tts_optimize_prompt + f"\n\nText: {seg.cn_text}"
                                log_status("TTS_OPTIMIZE", f"Seg {seg.index}: Requesting Gemma4 to polish text for TTS...", "INFO")
                                
                                tts_system_prompt = "你是一位精通中文口语表达与 TTS 语音合成优化的语言专家，擅长通过调整标点和微调语感，使文本在朗读时听起来极其自然、流畅且富有情感。"
                                optimized_text = await robust_gemma4_call(
                                    prompt=optimize_prompt,
                                    system_prompt=tts_system_prompt,
                                    max_tokens=500,
                                    clean_output=False
                                )
                                cn_text_for_tts = optimized_text.strip() if optimized_text and optimized_text.strip() else seg.cn_text
                                cn_text_for_tts = aggressive_markdown_cleaner(cn_text_for_tts)
                                log_status("TTS_OPTIMIZE", f"Seg {seg.index} CN text optimized by Gemma4.", "OK")
                            except Exception as exc:
                                log_status("TTS_OPTIMIZE", f"Gemma4 optimization failed for seg {seg.index}: {exc}", "WARN")
                                cn_text_for_tts = seg.cn_text
                    # Apply SSML pauses after optimization
                    audio_text = apply_ssml_pauses(cn_text_for_tts)
                    async with ConcurrencyManager.TTS_SEM:
                        await robust_tts_call(audio_text, MODEL_CONFIG["VOICE_CN"], cn_raw_wav)
                return await asyncio.to_thread(master_audio_sync, cn_raw_wav, seg.cn_audio_path)
            return len(AudioSegment.from_file(seg.cn_audio_path)) / 1000.0

        async def do_image():
            if self.reuse_image and os.path.exists(seg.img_path):
                return True
            async with ConcurrencyManager.IMG_SEM:
                await robust_image_call(seg.img_prompt, seg.img_path, f"IMG_{seg.index:02d}")
            return True

        en_dur, cn_dur, _ = await asyncio.gather(do_en_audio(), do_cn_audio(), do_image())
        seg.en_duration = en_dur
        seg.cn_duration = cn_dur
        max_dur = max(en_dur, cn_dur)
        if max_dur <= 0:
            return

        if not (self.reuse_video and has_split_video):
            if not (self.reuse_video and has_base_video):
                async with ConcurrencyManager.NVENC_SEM:
                    movement_pool = ["zoom_in", "pan_right", "pan_down", "zoom_out", "pan_left", "pan_up"]
                    movement = movement_pool[seg.index % 6]
                    encode_ok = await asyncio.to_thread(self._encode_video, seg.img_path, max_dur, base_vid_path, movement)
                    if not encode_ok:
                        return

            if en_dur > 0:
                try:
                    await asyncio.to_thread(
                        safe_subprocess_run,
                        ["ffmpeg", "-y", "-i", base_vid_path, "-t", str(en_dur), "-c", "copy", en_vid_path],
                        FFMPEG_TIMEOUT_SECONDS,
                        "FFMPEG_SPLIT",
                    )
                except Exception as exc:
                    log_status("FFMPEG_SPLIT", f"EN segment split failed (s{seg.index:03d}): {exc}", "ERROR")
                    en_dur = 0.0
            if cn_dur > 0:
                try:
                    await asyncio.to_thread(
                        safe_subprocess_run,
                        ["ffmpeg", "-y", "-i", base_vid_path, "-t", str(cn_dur), "-c", "copy", cn_vid_path],
                        FFMPEG_TIMEOUT_SECONDS,
                        "FFMPEG_SPLIT",
                    )
                except Exception as exc:
                    log_status("FFMPEG_SPLIT", f"CN segment split failed (s{seg.index:03d}): {exc}", "ERROR")
                    cn_dur = 0.0

        seg.en_video_path = en_vid_path if en_dur > 0 else ""
        seg.cn_video_path = cn_vid_path if cn_dur > 0 else ""
        seg.is_valid_en = en_dur > 0
        seg.is_valid_cn = cn_dur > 0

    async def run_dual_tracks(self):
        """Run all segment processing tasks concurrently and raise on any failure."""
        results = await asyncio.gather(*[self._process_segment_dual(seg) for seg in self.segments], return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, BaseException):
                raise RuntimeError(f"Segment {idx + 1} failed: {result}") from result

    def _get_video_duration_ms(self, video_path: str) -> int:
        """Uses ffprobe to extract exact video duration in milliseconds."""
        log_status("PROBE", f"Extracting duration for: {os.path.basename(video_path)}", "INFO")
        if not os.path.exists(video_path):
            log_status("PROBE", f"Target missing: {video_path}", "ERROR")
            return 0
        
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            dur_ms = int(float(res.stdout.strip()) * 1000)
            log_status("PROBE", f"Duration extracted: {dur_ms}ms", "OK")
            return dur_ms
        except Exception as exc:
            log_status("PROBE", f"Probe failed: {exc}", "ERROR")
            return 0

    # ==============================================================================
    # DISCRETE PIPELINE STEPS (STEM MIXING)
    # ==============================================================================
    def _step1_concat_story_segments(self, valid_entries: List[Tuple[str, str]], v_concat_txt: str, output_v: str) -> bool:
        """
        STRICTLY concats only the generated segments. Intro is explicitly excluded 
        here to prevent the concat demuxer from silently dropping the stream.
        """
        log_status("STEP_1", "Concatenating 40-min base story segments...", "INFO")
        with open(v_concat_txt, "w", encoding="utf-8") as f:
            for vid_path, _ in valid_entries:
                f.write(f"file '{os.path.abspath(vid_path)}'\n")
                
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", v_concat_txt, "-c", "copy", output_v]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        
        if res.returncode != 0:
            log_status("STEP_1", f"Base concat failed: {res.stderr}", "ERROR")
            return False
        log_status("STEP_1", "Base story video successfully concatenated.", "OK")
        return True

    def _step2_merge_intro_and_watermark(self, intro_vid: str, base_vid: str, output_v: str, channel_name: str, has_nvenc: bool) -> bool:
        """
        Uses filter_complex to merge Intro and Base Video. Filtergraph operates on raw frames, 
        making it 100% immune to timebase/framerate mismatches that crash standard concat.
        """
        log_status("STEP_2", "Merging Intro and applying GPU Watermark...", "INFO")
        cmd = ["ffmpeg", "-y"]
        
        if intro_vid:
            cmd.extend(["-i", intro_vid])
        cmd.extend(["-i", base_vid])

        filter_complex = []
        current_v = ""

        # 1. Build lossless concat filter
        res = self.ASSEMBLY_CONFIG["resolution"]
        fps = self.ASSEMBLY_CONFIG["fps"]
        scale_filter = f"scale={res}:force_original_aspect_ratio=decrease,pad={res}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        
        if intro_vid:
            filter_complex.append(f"[0:v]{scale_filter}[v0]")
            filter_complex.append(f"[1:v]{scale_filter}[v1]")
            filter_complex.append("[v0][v1]concat=n=2:v=1[v_cat]")
            current_v = "[v_cat]"
        else:
            current_v = "0:v"

        # 2. Build watermark filter
        final_v_map = ""
        if channel_name:
            # 1. Write channel name to a temp text file to avoid Windows CLI encoding issues (Ultimate Fix)
            txt_path = os.path.join(self.folder, "watermark_text.txt")
            with open(txt_path, "w", encoding="utf-8") as tf:
                # Apply basic drawtext escaping before writing
                tf.write(_escape_drawtext(channel_name))
            
            # 2. Use core_engine native helpers to format paths
            f_path = _format_windows_font_path(self.ASSEMBLY_CONFIG["font_path"])
            t_file_path = _format_windows_font_path(txt_path)
            
            text_filter = f"drawtext=fontfile='{f_path}':textfile='{t_file_path}':fontcolor=white@0.7:fontsize=48:x=50:y=50:shadowcolor=black@0.7:shadowx=2:shadowy=2"
            
            if current_v == "0:v":
                filter_complex.append(f"[0:v]{text_filter}[v_out]")
            else:
                filter_complex.append(f"{current_v}{text_filter}[v_out]")
            final_v_map = "[v_out]"
        else:
            final_v_map = current_v

        # 3. Assemble the final command
        if filter_complex:
            cmd.extend(["-filter_complex", ";".join(filter_complex)])
            cmd.extend(["-map", final_v_map])
            
            if has_nvenc:
                cmd.extend(["-c:v", self.ASSEMBLY_CONFIG["video_codec_gpu"], "-preset", self.ASSEMBLY_CONFIG["preset_gpu"], 
                            "-b:v", self.ASSEMBLY_CONFIG["bitrate"], "-pix_fmt", self.ASSEMBLY_CONFIG["pixel_format"]])
            else:
                log_status("STEP_2", "NVENC unavailable. Falling back to CPU render.", "WARN")
                cmd.extend(["-c:v", self.ASSEMBLY_CONFIG["video_codec_cpu"], "-preset", self.ASSEMBLY_CONFIG["preset_cpu"], 
                            "-crf", self.ASSEMBLY_CONFIG["crf"], "-pix_fmt", self.ASSEMBLY_CONFIG["pixel_format"]])
        else:
            cmd.extend(["-c:v", "copy"])

        cmd.extend(["-an", output_v])  # Strictly no audio processing at this stage
        
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode != 0:
            log_status("STEP_2", f"Render failed: {res.stderr}", "ERROR")
            return False
        log_status("STEP_2", "Video merging and watermarking complete.", "OK")
        return True

    def _step3_build_master_vocal(self, valid_entries: List[Tuple[str, str]], intro_aud: str, intro_duration_ms: int, output_a: str) -> bool:
        """Uses Pydub to seamlessly merge the Intro SFX with the 40-min story dictation."""
        log_status("STEP_3", f"Building master primary audio track (Pydub). Target intro: {intro_duration_ms}ms", "INFO")
        try:
            from pydub import AudioSegment
            combined = AudioSegment.empty()
            
            if intro_aud and os.path.exists(intro_aud):
                full_intro = AudioSegment.from_file(intro_aud)
                # Critical fix: force audio start to match video length to prevent voice lag
                if intro_duration_ms > 0:
                    combined += full_intro[:intro_duration_ms]
                else:
                    combined += full_intro
                
            for _, aud_path in valid_entries:
                combined += AudioSegment.from_file(aud_path)
                
            combined.export(output_a, format="wav")
            log_status("STEP_3", "Master primary audio successfully exported.", "OK")
            return True
        except Exception as exc:
            log_status("STEP_3", f"Pydub audio builder failed: {exc}", "ERROR")
            return False

    def _step4_audio_mixdown(self, primary_a: str, bgm: str, amb: str, delay_ms: int, output_a: str) -> bool:
        """Dedicated FFmpeg node for Sidechain compression and timing delay. 100% crash-proof format injection."""
        log_status("STEP_4", "Initializing Audio Mixdown Engine...", "INFO")
        
        cmd = ["ffmpeg", "-y", "-i", primary_a]
        filter_complex = []
        
        idx = 1
        bgm_idx = None
        amb_idx = None

        if bgm and os.path.exists(bgm):
            cmd.extend(["-stream_loop", "-1", "-i", bgm])
            bgm_idx = idx
            idx += 1

        if amb and os.path.exists(amb):
            cmd.extend(["-stream_loop", "-1", "-i", amb])
            amb_idx = idx
            idx += 1

        if bgm_idx is None and amb_idx is None:
            log_status("STEP_4", "No BGM or Ambience found. Bypassing mixdown.", "INFO")
            import shutil
            shutil.copy(primary_a, output_a)
            return True

        safe_fmt = f"aresample={self.ASSEMBLY_CONFIG['sample_rate']},aformat=sample_fmts=fltp:sample_rates={self.ASSEMBLY_CONFIG['sample_rate']}:channel_layouts=stereo"
        filter_complex.append(f"[0:a]{safe_fmt},asplit=2[v_sc][v_mix]")
        
        v_sc = "[v_sc]"
        v_mix = "[v_mix]"
        bgm_input = f"[{bgm_idx}:a]" if bgm_idx else ""
        amb_input = f"[{amb_idx}:a]" if amb_idx else ""

        if delay_ms > 0:
            if bgm_idx:
                filter_complex.append(f"{bgm_input}{safe_fmt},adelay={delay_ms}|{delay_ms}[bgm_del]")
                bgm_input = "[bgm_del]"
            if amb_idx:
                filter_complex.append(f"{amb_input}{safe_fmt},adelay={delay_ms}|{delay_ms}[amb_del]")
                amb_input = "[amb_del]"
        else:
            if bgm_idx:
                filter_complex.append(f"{bgm_input}{safe_fmt}[bgm_fmt]")
                bgm_input = "[bgm_fmt]"
            if amb_idx:
                filter_complex.append(f"{amb_input}{safe_fmt}[amb_fmt]")
                amb_input = "[amb_fmt]"

        if bgm_idx is not None and amb_idx is not None:
            filter_complex.append(
                f"{bgm_input}{v_sc}sidechaincompress=threshold=0.15:ratio=5:attack=5:release=700[bgm_ducked];"
                f"[bgm_ducked]volume=0.4[bgm_final];"
                f"{amb_input}volume=0.15[amb_final];"
                f"{v_mix}[bgm_final][amb_final]amix=inputs=3:duration=first:dropout_transition=2[a_mix]"
            )
        elif bgm_idx is not None:
            filter_complex.append(
                f"{bgm_input}{v_sc}sidechaincompress=threshold=0.15:ratio=5:attack=5:release=700[bgm_ducked];"
                f"[bgm_ducked]volume=0.4[bgm_final];"
                f"{v_mix}[bgm_final]amix=inputs=2:duration=first:dropout_transition=2[a_mix]"
            )
        elif amb_idx is not None:
            filter_complex.append(
                f"{amb_input}volume=0.15[amb_final];"
                f"{v_mix}[amb_final]amix=inputs=2:duration=first:dropout_transition=2[a_mix]"
            )

        cmd.extend([
            "-filter_complex", ";".join(filter_complex),
            "-map", "[a_mix]",
            "-c:a", self.ASSEMBLY_CONFIG["audio_codec"],
            "-b:a", self.ASSEMBLY_CONFIG["audio_bitrate"],
            output_a
        ])

        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode != 0:
            log_status("STEP_4", f"Mixdown failed: {res.stderr}", "ERROR")
            return False
        log_status("STEP_4", "Final audio stems perfectly mixed.", "OK")
        return True

    def _step5_mux_master_file(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """Instant 0.1-second muxing of the fully processed video and audio tracks."""
        log_status("STEP_5", "Muxing final Master A/V tracks (Stream Copy)...", "INFO")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "copy",
            "-shortest",
            output_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode != 0:
            log_status("STEP_5", f"Final mux failed: {res.stderr}", "ERROR")
            return False
        log_status("STEP_5", "Final Master File securely generated.", "OK")
        return True

    # ==============================================================================
    # CLASS ORCHESTRATOR
    # ==============================================================================
    def assemble(self, output_name: str, mode: str = "EN") -> str:
        """
        Orchestrates the 5-Stage Stem Mixing Pipeline.
        """
        prefix = output_name.split(".")[0]
        v_concat_txt = os.path.join(self.folder, f"{prefix}_v.txt")
        required_segments = []
        valid_entries = []

        # 1. Strictly filter segments (Intro is never added to this queue)
        for seg in self.segments:
            target_text = (seg.en_text if mode == "EN" else seg.cn_text) or ""
            if not target_text.strip():
                continue
            required_segments.append(seg)
            is_valid = getattr(seg, "is_valid_en", False) if mode == "EN" else getattr(seg, "is_valid_cn", False)
            vid_path = seg.en_video_path if mode == "EN" else seg.cn_video_path
            aud_path = seg.en_audio_path if mode == "EN" else seg.cn_audio_path
            
            if is_valid and vid_path and aud_path and os.path.exists(vid_path) and os.path.exists(aud_path):
                valid_entries.append((vid_path, aud_path))

        if len(valid_entries) != len(required_segments):
            log_status("STUDIO", f"Skip {mode} assembly: Missing required segments.", "ERROR")
            return ""

        if not valid_entries:
            log_status("STUDIO", f"No valid segments to assemble for {mode} mode.", "WARN")
            return ""

        # 2. Measure Intro duration
        intro_duration_ms = 0
        intro_vid = getattr(self, "intro_video_path", None)
        intro_aud = getattr(self, "intro_audio_path", None)
        
        if intro_vid and os.path.exists(intro_vid):
            intro_duration_ms = self._get_video_duration_ms(intro_vid)
            log_status("STUDIO", f"Intro detected. BGM track delay set to {intro_duration_ms}ms.", "INFO")
        else:
            log_status("STUDIO", "No Intro video found. Proceeding with standard base.", "INFO")
            intro_vid = ""
            intro_aud = ""

        # 3. Define physical paths for all intermediate pipeline nodes
        temp_base_v = os.path.join(self.folder, f"{prefix}_STEP1_base_v.mp4")
        temp_watermarked_v = os.path.join(self.folder, f"{prefix}_STEP2_watermarked_v.mp4")
        temp_primary_a = os.path.join(self.folder, f"{prefix}_STEP3_primary_a.wav")
        temp_mixed_a = os.path.join(self.folder, f"{prefix}_STEP4_mixed_a.m4a")
        final_out = os.path.join(self.folder, output_name)

        # 4. Extract runtime environment variables
        channel_name = self.channel_name_en if mode == "EN" else self.channel_name_cn
        has_nvenc = NVENC_AVAILABLE
        
        bgm_path = None
        if getattr(self, "bgm", None) and os.path.isdir(self.bgm):
            bgms = [os.path.join(self.bgm, f) for f in os.listdir(self.bgm) if os.path.isfile(os.path.join(self.bgm, f))]
            if bgms: bgm_path = random.choice(bgms)
            
        amb_path = None
        if getattr(self, "ambience", None) and os.path.isdir(self.ambience):
            ambs = [os.path.join(self.ambience, f) for f in os.listdir(self.ambience) if os.path.isfile(os.path.join(self.ambience, f))]
            if ambs: amb_path = random.choice(ambs)

        # 5. Fire the five-stage pipeline
        if not self._step1_concat_story_segments(valid_entries, v_concat_txt, temp_base_v): return ""
        if not self._step2_merge_intro_and_watermark(intro_vid, temp_base_v, temp_watermarked_v, channel_name, has_nvenc): return ""
        if not self._step3_build_master_vocal(valid_entries, intro_aud, intro_duration_ms, temp_primary_a): return ""
        if not self._step4_audio_mixdown(temp_primary_a, bgm_path, amb_path, intro_duration_ms, temp_mixed_a): return ""
        if not self._step5_mux_master_file(temp_watermarked_v, temp_mixed_a, final_out): return ""

        # 6. Clean up all intermediate temp files
        for tmp_file in [v_concat_txt, temp_base_v, temp_watermarked_v, temp_primary_a, temp_mixed_a]:
            if os.path.exists(tmp_file): os.remove(tmp_file)

        log_status("STUDIO", f"Industrial assembly complete: {final_out}", "SUCCESS")
        return final_out


# Global NVENC availability flag. It is detected during startup by validate_simple_runner_environment().
NVENC_AVAILABLE: bool = False


def validate_simple_runner_environment(cfg) -> bool:
    """Validate that all required environment variables, files, and tools (ffmpeg, NVENC) are available.
    Also detects and caches NVENC availability in the global NVENC_AVAILABLE flag.
    Returns True if the environment is valid, False otherwise.
    """
    global NVENC_AVAILABLE

    is_valid = True
    if getattr(cfg, "USE_CN_PRESET_SCRIPT", False) or getattr(cfg, "USE_EN_PRESET_SCRIPT", False):
        resource_file = getattr(cfg, "SCRIPT_RESOURCE_FILE", "")
        if not resource_file or not os.path.exists(resource_file):
            log_status("ENV_CHECK", f"SCRIPT_RESOURCE_FILE not found: {resource_file}", "ERROR")
            is_valid = False

    if not getattr(cfg, "ONLY_GENERATE_SCRIPT", False) and not getattr(cfg, "REUSE_IMAGE", False):
        if not os.getenv("RUNNINGHUB_API_KEY"):
            log_status("ENV_CHECK", "Missing environment variable: RUNNINGHUB_API_KEY", "ERROR")
            is_valid = False

    if not getattr(cfg, "ONLY_GENERATE_SCRIPT", False):
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except Exception as exc:
            log_status("ENV_CHECK", f"FFMPEG not found: {exc}", "ERROR")
            is_valid = False

    # Detect NVENC and store the result in the global flag for assemble() to use later.
    NVENC_AVAILABLE = detect_nvenc()

    if is_valid:
        log_status("ENV_CHECK", "Simple runner environment validated.", "OK")
    return is_valid


async def execute_channel(config_file: str, cli_args):
    """Main async entry point for a single channel run.
    Loads config, resolves the workspace folder (new or reused), runs the story and media pipelines,
    assembles the final EN and CN video files, and records the task result to CSV.
    """
    start_time = datetime.now()
    app_name = os.path.basename(config_file)
    exec_result = "FAILED"
    folder = ""
    current_story_title = "Unknown"

    app_base_name = os.path.splitext(app_name)[0]
    task_prefix = app_base_name.split("_")[-1].upper()
    current_task_id = f"{task_prefix}_{start_time.strftime('%Y%m%d%H%M%S')}"
    cfg = load_python_config(config_file)
    render_backend = resolve_render_backend(cfg, getattr(cli_args, "render_backend", None))
    cfg.RENDER_BACKEND = render_backend
    render_config = get_render_config(cfg, render_backend)
    log_status("CONFIG", f"Render backend: {render_backend}", "INFO")

    if len(sys.argv) > 1:
        # Global override for a totally fresh run
        if getattr(cli_args, "fresh", False):
            log_status("CONFIG", "FORCE FRESH RUN: Overriding all reuse flags to False.", "WARN")
            cfg.REUSE_TASK_ID = ""
            cfg.REUSE_GEMINI_OUTLINE = False
            cfg.REUSE_OPENAI_SCRIPT = False
            cfg.REUSE_DEEPSEEK_SCRIPT = False
            cfg.REUSE_IMAGE_PROMPT = False
            cfg.REUSE_TTS = False
            cfg.REUSE_IMAGE = False
            cfg.REUSE_VIDEO = False
        else:
            if cli_args.reuse_image_prompt is not None: cfg.REUSE_IMAGE_PROMPT = cli_args.reuse_image_prompt
            if cli_args.reuse_tts is not None: cfg.REUSE_TTS = cli_args.reuse_tts
            if cli_args.reuse_image is not None: cfg.REUSE_IMAGE = cli_args.reuse_image
            if cli_args.reuse_video is not None: cfg.REUSE_VIDEO = cli_args.reuse_video
            if cli_args.reuse_task_id is not None: cfg.REUSE_TASK_ID = cli_args.reuse_task_id
            if cli_args.only_generate_image is not None: cfg.ONLY_GENERATE_IMAGE = cli_args.only_generate_image

    # Clean up any lingering stop signals from previous runs.
    if os.path.exists("stop.txt"):
        with suppress(Exception):
            os.remove("stop.txt")
            log_status("SYSTEM", "Found and removed existing stop.txt to prevent accidental shutdown.", "OK")

    log_status("SYSTEM", f"--- RUNNING SIMPLE CHANNEL: {app_name} [Task: {current_task_id}] ---", "START")
    log_status("CONFIG", f"Pipeline Flags: REUSE_IMAGE={cfg.REUSE_IMAGE}, REUSE_TTS={cfg.REUSE_TTS}, REUSE_VIDEO={cfg.REUSE_VIDEO}, REUSE_IMAGE_PROMPT={cfg.REUSE_IMAGE_PROMPT}", "INFO")
    log_status("CONFIG", f"Pipeline Flags: REUSE_OPENAI_SCRIPT={getattr(cfg, 'REUSE_OPENAI_SCRIPT', False)}, REUSE_DEEPSEEK_SCRIPT={getattr(cfg, 'REUSE_DEEPSEEK_SCRIPT', False)}, REUSE_GEMINI_OUTLINE={getattr(cfg, 'REUSE_GEMINI_OUTLINE', False)}", "INFO")
    log_status("CONFIG", f"Pipeline Flags: USE_GEMMA4_OPTIMIZE_TTS={getattr(cfg, 'USE_GEMMA4_OPTIMIZE_TTS', False)}", "INFO")

    ConcurrencyManager.init_locks()
    ConcurrencyManager.TTS_SEM = asyncio.Semaphore(4)
    ConcurrencyManager.IMG_SEM = asyncio.Semaphore(1)
    nvenc_parallel = get_render_parallelism(render_backend, cfg)
    log_status("SYSTEM", f"Render concurrency [{render_backend}] (NVENC_SEM): {nvenc_parallel}", "OK")
    ConcurrencyManager.NVENC_SEM = asyncio.Semaphore(nvenc_parallel)

    if not validate_simple_runner_environment(cfg):
        save_task_record(cfg.RECORD_CSV_PATH, current_task_id, app_name, start_time, datetime.now(), exec_result, folder, current_story_title)
        return

    is_reusing = any([getattr(cfg, "REUSE_IMAGE_PROMPT", False), getattr(cfg, "REUSE_TTS", False), getattr(cfg, "REUSE_IMAGE", False), getattr(cfg, "REUSE_VIDEO", False), bool(getattr(cfg, "REUSE_TASK_ID", ""))])
    if is_reusing:
        target = ""
        reuse_task_id_val = getattr(cfg, "REUSE_TASK_ID", "")
        if reuse_task_id_val and os.path.exists(cfg.RECORD_CSV_PATH):
            try:
                with open(cfg.RECORD_CSV_PATH, "r", encoding="utf-8-sig") as file_obj:
                    rows = list(csv.DictReader(file_obj))
                for row in rows:
                    if row.get("task_id") == reuse_task_id_val:
                        target = row.get("output_path", "")
                        current_task_id = reuse_task_id_val
                        break
            except Exception as exc:
                log_status("SYSTEM", f"Failed to search task ID in CSV: {exc}", "WARN")

        if not target:
            target = getattr(cfg, "REUSE_TARGET_FOLDER", "")
        if not target or not os.path.exists(target):
            log_status("SYSTEM", "Reuse flags ON, but target folder not found. Aborting.", "CRITICAL")
            save_task_record(cfg.RECORD_CSV_PATH, current_task_id, app_name, start_time, datetime.now(), exec_result, target, current_story_title)
            return
        folder = target
        log_status("ENV", f"Targeting existing workspace: {folder}", "OK")
    else:
        folder = setup_workspace(os.path.join(cfg.BASE_WORKSPACE, datetime.now().strftime("%Y%m%d_%H%M%S")))

    if render_backend == "github":
        GitHubSyncManager.configure_for_workspace(cfg, folder)
    LoggerManager.set_log_file(os.path.join(folder, "pipeline_master.log"))
    os.makedirs(os.path.join(folder, "image"), exist_ok=True)
    os.makedirs(os.path.join(folder, "audio"), exist_ok=True)
    os.makedirs(os.path.join(folder, "video"), exist_ok=True)

    try:
        stop_watcher_task = asyncio.create_task(stop_file_watcher())
        story_pipe = StoryPipeline(folder, cfg)
        en_scripts, cn_scripts, img_prompts = await story_pipe.build_full_story()
        current_story_title = story_pipe.context.get("story", "Unknown")
        intro_cn_path = ""
        intro_en_path = ""

        async def seo_thumbnail_task():
            nonlocal intro_cn_path, intro_en_path
            if not getattr(cfg, "GENERATE_YOUTUBE_ASSETS", False):
                return None

            metadata_en, metadata_cn, thumb_prompt = await story_pipe.generate_youtube_assets(en_scripts, current_story_title, app_name)
            if thumb_prompt and not getattr(cfg, "ONLY_GENERATE_SCRIPT", False):
                thumb_en_path = os.path.join(folder, "thumbnail_en.png")
                thumb_cn_path = os.path.join(folder, "thumbnail_cn.png")
                # Reuse logic: verify not only thumbnails, but also any required intro videos.
                # If intro files were deleted manually, allow regeneration even when REUSE_IMAGE=True.
                potential_cn = os.path.join(folder, "video", "intro_cn.mp4")
                potential_en = os.path.join(folder, "video", "intro_en.mp4")
                need_cn = bool(metadata_cn.get("intro_cn")) if metadata_cn else False
                need_en = bool(metadata_cn.get("intro_en")) if metadata_cn else False

                if getattr(cfg, "REUSE_IMAGE", False):
                    thumbs_ok = os.path.exists(thumb_en_path) and os.path.exists(thumb_cn_path)
                    
                    # Skip generation only when thumbnails and all required intros already exist.
                    if thumbs_ok and (not need_cn or os.path.exists(potential_cn)) and (not need_en or os.path.exists(potential_en)):
                        if need_cn: intro_cn_path = potential_cn
                        if need_en: intro_en_path = potential_en
                        log_status("REUSE", "Thumbnails and intros already exist. Skipping SEO generation.", "OK")
                        return metadata_en

                thumb_base_path = os.path.join(folder, "thumbnail_base.png")
                async with ConcurrencyManager.IMG_SEM:
                    if await robust_image_call(thumb_prompt, thumb_base_path, "SEO_THUMB"):
                        font_dir_en = getattr(cfg, "ASSETS_POOL", {}).get("font_en", "")
                        font_dir_cn = getattr(cfg, "ASSETS_POOL", {}).get("font_cn", "") or font_dir_en
                        font_val_en = story_pipe.context.get("font") or ""
                        font_val_cn = story_pipe.context.get("font_cn") or ""
                        if not font_val_en and font_dir_en and os.path.isdir(font_dir_en):
                            fonts = [os.path.join(font_dir_en, f) for f in os.listdir(font_dir_en) if os.path.isfile(os.path.join(font_dir_en, f))]
                            if fonts:
                                font_val_en = random.choice(fonts)
                        if not font_val_cn and font_dir_cn and os.path.isdir(font_dir_cn):
                            fonts = [os.path.join(font_dir_cn, f) for f in os.listdir(font_dir_cn) if os.path.isfile(os.path.join(font_dir_cn, f))]
                            if fonts:
                                font_val_cn = random.choice(fonts)
                        if not font_val_cn:
                            font_val_cn = font_val_en
                        story_pipe.context["font"] = font_val_en
                        story_pipe.context["font_cn"] = font_val_cn
                        save_json_formatted(os.path.join(folder, "0_context.json"), story_pipe.context)

                        text_align = story_pipe.context.get("thumb_text_align", "right")
                        add_text_to_thumbnail(thumb_base_path, thumb_en_path, metadata_en.get("thumbnail_text", current_story_title), align=text_align, font_path=font_val_en)
                        title_cn = metadata_cn.get("thumbnail_text") if metadata_cn else metadata_en.get("thumbnail_text", current_story_title)
                        add_text_to_thumbnail(thumb_base_path, thumb_cn_path, title_cn, align=text_align, font_path=font_val_cn)

                        # Generate opening title clips (3-second intro) for both languages.
                        for lang, key, chan, font in [
                            ("cn", "intro_cn", getattr(cfg, "CHANNEL_NAME_CN", getattr(cfg, "CHANNEL_NAME", "")), font_val_cn),
                            ("en", "intro_en", getattr(cfg, "CHANNEL_NAME", ""), font_val_en)
                        ]:
                            text = metadata_cn.get(key, "") if metadata_cn else ""
                            log_status("SEO", f"start_{lang} value: '{text}'", "INFO")
                            if text:
                                path_val = os.path.join(folder, "video", f"intro_{lang}.mp4")
                                if generate_blurred_title_video(thumb_base_path, path_val, text, chan, font_path=font):
                                    log_status("SEO", f"intro_{lang}.mp4 generated successfully: {path_val}", "SUCCESS")
                                    # Record the successful intro path into context for subsequent assembly.
                                    story_pipe.context[f"intro_{lang}_path"] = path_val
                                    if lang == "cn": intro_cn_path = path_val
                                    else: intro_en_path = path_val
                                else:
                                    log_status("SEO", f"Failed to generate intro_{lang}.mp4", "ERROR")

                        # Consolidate and sync context updates.
                        save_json_formatted(os.path.join(folder, "0_context.json"), story_pipe.context)


                        if os.path.exists(thumb_base_path):
                            os.remove(thumb_base_path)
            return metadata_en

        seo_task = asyncio.create_task(seo_thumbnail_task())

        if getattr(cfg, "ONLY_GENERATE_SCRIPT", False):
            await seo_task
            exec_result = "SUCCESS"
            story_pipe.mark_preset_as_used()
            return

        if getattr(cfg, "ONLY_GENERATE_IMAGE", False):
            segments = construct_media_segments(folder, en_scripts, cn_scripts, img_prompts)

            async def generate_all_images():
                async def gen_img(seg):
                    if getattr(cfg, "REUSE_IMAGE", False) and os.path.exists(seg.img_path):
                        return
                    async with ConcurrencyManager.IMG_SEM:
                        await robust_image_call(seg.img_prompt, seg.img_path, f"IMG_{seg.index:02d}")

                results = await asyncio.gather(*[gen_img(seg) for seg in segments], return_exceptions=True)
                for result in results:
                    if isinstance(result, BaseException):
                        raise result

            await asyncio.gather(generate_all_images(), seo_task)
            exec_result = "SUCCESS"
            story_pipe.mark_preset_as_used()
            return

        segments = construct_media_segments(folder, en_scripts, cn_scripts, img_prompts)
        media_pipe = MediaPipeline(
            folder=folder,
            segments=segments,
            reuse_tts=getattr(cfg, "REUSE_TTS", False),
            channel_name_en=getattr(cfg, "CHANNEL_NAME", ""),
            channel_name_cn=getattr(cfg, "CHANNEL_NAME_CN", getattr(cfg, "CHANNEL_NAME", "")),
            overlays=getattr(cfg, "ASSETS_POOL", {}).get("overlays", ""),
            reuse_image=getattr(cfg, "REUSE_IMAGE", False),
            reuse_video=getattr(cfg, "REUSE_VIDEO", False),
            ambience=getattr(cfg, "ASSETS_POOL", {}).get("ambience", ""),
            bgm=getattr(cfg, "ASSETS_POOL", {}).get("bgm", ""),
            use_gemma4_optimize_tts=getattr(cfg, "USE_GEMMA4_OPTIMIZE_TTS", False),
            prompt_config=getattr(cfg, "PROMPT_CONFIG", {}),
            render_backend=render_backend,
            render_config=render_config,
        )

        parallel_results = await asyncio.gather(media_pipe.run_dual_tracks(), seo_task)
        metadata_en = parallel_results[1]
        
        # Inject the correct intro paths (if any) based on current mode for the assemble function.
        media_pipe.intro_video_path = intro_en_path
        media_pipe.intro_audio_path = getattr(cfg, "ASSETS_POOL", {}).get("intro", "")
        final_en = media_pipe.assemble("FINAL_STORY_EN.mp4", "EN")
        
        media_pipe.intro_video_path = intro_cn_path
        media_pipe.intro_audio_path = getattr(cfg, "ASSETS_POOL", {}).get("intro", "")
        final_cn = media_pipe.assemble("FINAL_STORY_CN.mp4", "CN")

        exec_result = "SUCCESS"
        story_pipe.mark_preset_as_used()
    except Exception as exc:
        log_status("SYSTEM", f"Critical Pipeline Failure: {repr(exc)}", "CRITICAL")
    finally:
        if "stop_watcher_task" in locals() and not stop_watcher_task.done():
            stop_watcher_task.cancel()
            with suppress(asyncio.CancelledError):
                await stop_watcher_task

        await APIClients.close_all()
        
        if exec_result == "SUCCESS" and current_story_title and current_story_title != "Unknown":
            safe_title = re.sub(r'[\\/*?:"<>|]', "", current_story_title).strip()
            safe_title = safe_title[:50]
            if safe_title and safe_title not in os.path.basename(folder):
                new_folder = f"{folder}_{safe_title}"
                try:
                    os.rename(folder, new_folder)
                    folder = new_folder
                    LoggerManager.set_log_file(os.path.join(folder, "pipeline_master.log"))
                    log_status("SYSTEM", f"Renamed workspace to: {new_folder}", "OK")
                except Exception as e:
                    log_status("SYSTEM", f"Failed to rename workspace: {e}", "WARN")

        if render_backend == "github":
            log_status("SYSTEM", "Cleaning up remote GitHub workspace...", "INFO")
            GitHubSyncManager.cleanup_workspace()
            log_status("SYSTEM", "Cleaning up GitHub workflow runs...", "INFO")
            GitHubSyncManager.cleanup_workflow_runs()

        save_task_record(cfg.RECORD_CSV_PATH, current_task_id, app_name, start_time, datetime.now(), exec_result, folder, current_story_title)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    parser = argparse.ArgumentParser(description="Content OS - Simple Runner")
    parser.add_argument("-c", "--config", type=str, default="app_doac.py", help="Path to the channel configuration Python file")
    parser.add_argument("--reuse-image-prompt", type=str2bool, nargs="?", const=True, default=None, help="Force override REUSE_IMAGE_PROMPT")
    parser.add_argument("--reuse-tts", type=str2bool, nargs="?", const=True, default=None, help="Force override REUSE_TTS")
    parser.add_argument("--reuse-image", type=str2bool, nargs="?", const=True, default=None, help="Force override REUSE_IMAGE")
    parser.add_argument("--reuse-video", type=str2bool, nargs="?", const=True, default=None, help="Force override REUSE_VIDEO")
    parser.add_argument("--reuse-task-id", type=str, default=None, help="Specific Task ID to reuse")
    parser.add_argument("--fresh", action="store_true", help="Force disable all reuse flags for a clean run")
    parser.add_argument("--only-generate-image", type=str2bool, nargs="?", const=True, default=None, help="Force override ONLY_GENERATE_IMAGE")
    parser.add_argument("--render-backend", choices=["local", "github", "colab"], default=None, help="Where to render clips (overrides RENDER_BACKEND / USE_GIT_HUB_INTERFACE)")
    args = parser.parse_args()

    def handle_sigint(sig, frame):
        """Handle Ctrl+C by creating stop.txt file for graceful shutdown."""
        log_status("SYSTEM", "Ctrl+C detected. Creating stop.txt for graceful shutdown...", "WARN")
        try:
            with open("stop.txt", "w") as f:
                f.write("Graceful shutdown requested via Ctrl+C\n")
        except Exception as e:
            log_status("SYSTEM", f"Failed to create stop.txt: {e}", "ERROR")
        # Give it a moment for the signal to be detected
        import time
        time.sleep(0.5)
    
    # Register signal handler for Ctrl+C
    original_sigint = signal.signal(signal.SIGINT, handle_sigint)
    
    try:
        asyncio.run(execute_channel(args.config, args))
    except KeyboardInterrupt:
        log_status("SYSTEM", "KeyboardInterrupt received. Terminating mapped FFmpeg processes...", "WARN")
        for proc in list(ACTIVE_FFMPEG_PROCS):
            _terminate_process(proc, stage="SYSTEM")
        sys.exit(1)
    finally:
        signal.signal(signal.SIGINT, original_sigint)
