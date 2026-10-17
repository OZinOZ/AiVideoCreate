#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "pipeline")))
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
regen_characters.py
-------------------
Batch regenerate the 'characters' field in all existing _glossary.json files
using the updated image prompt template (图片提示词.txt).

Only the 'characters' key is overwritten; all other fields (YouTube metadata,
intro_cn, etc.) are preserved as-is.
"""

import os
import re
import sys
import json
import asyncio
import traceback
import pandas as pd
from typing import Dict, List

# ── path config ────────────────────────────────────────────────────────────────
SCRIPT_DIR           = os.path.dirname(os.path.abspath(__file__))
STORIES_DIR          = r"I:\AiVideos\podcast\extracted_stories"
ENV_CONFIG_FILE      = r"I:\AiVideos\podcast\podcast.env"
CHARACTER_PROMPT_FILE = os.path.join(SCRIPT_DIR, "标题提示词.txt")
SCRIPT_RESOURCE_FILE = r"I:\AiVideos\podcast\script_resource.xlsx"

MAX_PROCESS_NUMBER = 0 # 0 means process all. Otherwise, stop after N documents.

# ── bootstrap env & engine ────────────────────────────────────────────────────
sys.path.insert(0, SCRIPT_DIR)
import random
from core_engine import robust_deepseek_call, load_env_config_file, log_status
from trait_pool import TRAIT_POOL

if ENV_CONFIG_FILE:
    load_env_config_file(ENV_CONFIG_FILE)

# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_json_from_text(text):
    """Best-effort JSON extraction from a model response."""
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()

    def try_parse(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    parsed = try_parse(text)
    if parsed is not None:
        return parsed

    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        end   = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            parsed = try_parse(text[start:end + 1])
            if parsed is not None:
                return parsed
    return None


def _select_trait(trait_category: str, gender: str) -> str:
    """Randomly selects a trait from the pool based on category and gender."""
    pool = TRAIT_POOL.get(trait_category)
    if not pool:
        return ""
    
    # 优先取特定性别的特征，如果没有则取通用(ANY)特征
    options = pool.get(gender, pool.get("ANY", []))
    if not options:
        return ""
        
    return random.choice(options)


def _build_character_prompt(name: str, gender: str, age: int) -> str:
    """Assembles the final visual prompt string."""
    log_status("BUILDER", f"Assembling procedural traits for [{name}]...", "INFO")
    
    heritage = _select_trait("heritage", gender)
    gender_text = "male" if gender == "M" else "female"
    frame = _select_trait("frame", gender)
    face = _select_trait("face", gender)
    eyes = _select_trait("eyes", gender)
    hair = _select_trait("hair", gender)

    prompt_parts = [
        heritage,
        f"{gender_text}, {age} years old",
        frame,
        face,
        eyes,
        hair,
    ]

    final_prompt = ", ".join(part for part in prompt_parts if part)
    return final_prompt

def collect_targets(stories_dir: str) -> list[dict]:
    """Return list of {cn_txt, glossary_json} pairs that are ready for regen.
    Filtered by Excel: cn_rewrite == 'yes' and used != 'yes'
    """
    valid_paths = set()
    try:
        if os.path.exists(SCRIPT_RESOURCE_FILE):
            df = pd.read_excel(SCRIPT_RESOURCE_FILE)
            for _, row in df.iterrows():
                val_cn = row.get('cn_rewrite')
                val_used = row.get('used')
                
                cn_rewrite = "" if pd.isna(val_cn) else str(val_cn).strip().lower()
                used = "" if pd.isna(val_used) else str(val_used).strip().lower()
                
                if cn_rewrite == 'yes' and used != 'yes':
                    path = row.get('path')
                    if not pd.isna(path):
                        # Extract base path without extension to match properly
                        base_path = os.path.splitext(str(path).strip())[0]
                        valid_paths.add(os.path.normpath(base_path).lower())
        else:
            print(f"Warning: Excel file not found: {SCRIPT_RESOURCE_FILE}")
    except Exception as e:
        print(f"Error reading Excel file: {e}")

    targets = []
    for fname in os.listdir(stories_dir):
        if not fname.endswith("_cn.txt"):
            continue
        base = os.path.join(stories_dir, fname[:-len("_cn.txt")])
        base_norm = os.path.normpath(base).lower()
        cn_txt = f"{base}_cn.txt"
        
        # Apply Excel filter using base path
        if base_norm not in valid_paths:
            continue
            
        glossary_path = f"{base}_glossary.json"
        
        targets.append({
            "cn_txt":       cn_txt,
            "glossary_json": glossary_path,
            "base":         base,
        })
    targets.sort(key=lambda x: x["base"])
    return targets


async def regen_one(target: dict, prompt_template: str) -> str:
    """Regenerate characters for a single story if needed. Returns status string."""
    cn_txt_path   = target["cn_txt"]
    glossary_path = target["glossary_json"]
    label         = os.path.basename(target["base"])

    print(f"        Forcing regen based on Excel filter.")

    # Read story text
    try:
        with open(cn_txt_path, "r", encoding="utf-8") as f:
            story_text = f.read().strip()
    except Exception as exc:
        return f"[SKIP] {label}: cannot read _cn.txt — {exc}"

    if not story_text:
        return f"[SKIP] {label}: _cn.txt is empty"


    # Read existing glossary
    existing = {}
    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        pass  # will create fresh if unreadable

    # Call DeepSeek
    full_prompt = f"{prompt_template}\n\n{story_text}"
    try:
        raw_response = await robust_deepseek_call(full_prompt, max_tokens=1500, clean_output=False)
    except Exception as exc:
        return f"[ERROR] {label}: DeepSeek call failed — {exc}"

    print(raw_response)
    
    parsed = _extract_json_from_text(raw_response)
    if not isinstance(parsed, dict) or "characters" not in parsed:
        return f"[WARN] {label}: unexpected response format, skipping write"

    # Procedural generation for each character and store as {name: description}
    char_list = parsed.get("characters", [])
    processed_chars = {}
    if isinstance(char_list, list):
        for char in char_list:
            name = char.get("name", "Unknown")
            gender = char.get("gender", "M")
            age = char.get("age", 25)
            # Generate the procedural prompt
            enhanced_desc = _build_character_prompt(name, gender, age)
            # Save as name: description
            processed_chars[name] = enhanced_desc
            log_status("CHAR_SYNC", f"Processed character: {name} (Gender: {gender}, Age: {age})", "OK")

    # Merge logic:
    if not existing:
        # If the file didn't exist, we treat this as a fresh generation.
        # Use everything returned by the model (metadata, title, etc.) if present.
        existing = parsed if isinstance(parsed, dict) else {}
        existing["characters"] = processed_chars
        log_status("CHAR_SYNC", f"Glossary created fresh for {label}", "INFO")
    else:
        # If the file already existed, we strictly PROTECT other fields (YouTube metadata, etc.)
        # and only overwrite the 'characters' key.
        existing["characters"] = processed_chars

    try:
        with open(glossary_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"[ERROR] {label}: failed to write glossary — {exc}"

    char_count = len(parsed["characters"]) if isinstance(parsed["characters"], list) else "?"
    return f"[OK]    {label}: updated {char_count} character(s)"


async def main():
    # Load the new prompt template
    if not os.path.exists(CHARACTER_PROMPT_FILE):
        print(f"ERROR: prompt file not found: {CHARACTER_PROMPT_FILE}")
        return

    with open(CHARACTER_PROMPT_FILE, "r", encoding="utf-8") as f:
        prompt_template = f.read().strip()

    targets = collect_targets(STORIES_DIR)
    
    # Apply MAX_PROCESS_NUMBER limit
    if MAX_PROCESS_NUMBER > 0:
        print(f"Limiting to {MAX_PROCESS_NUMBER} file(s) for debugging.")
        targets = targets[:MAX_PROCESS_NUMBER]

    print(f"Found {len(targets)} glossary file(s) to regenerate.\n")

    for i, target in enumerate(targets, 1):
        label = os.path.basename(target["base"])
        print(f"[{i:03d}/{len(targets):03d}] Processing: {label} ...")
        try:
            result = await regen_one(target, prompt_template)
            print(f"        {result}")
        except Exception as exc:
            print(f"        [ERROR] {label}: unexpected exception — {exc}")
            traceback.print_exc()

    print("\nDone.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
