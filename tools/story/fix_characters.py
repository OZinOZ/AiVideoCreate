#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "pipeline")))
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
fix_characters.py
-----------------
Scan all JSON files under STORIES_DIR.
For each JSON that contains a 'characters' dict where ALL values
already embed gender (male/female) and age (N years old),
extract gender + age and regenerate the value using _build_character_prompt.

No DeepSeek call is made — this is a purely local procedural rebuild
using the latest TRAIT_POOL from base_config.py.
"""

import os
import re
import sys
import json
import random
import traceback
from typing import Dict, List, Optional

# ── path config ────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
STORIES_DIR = r"I:\AiVideos\podcast\extracted_stories"

MAX_PROCESS_NUMBER = 0  # 0 = process all; N = stop after N files

# ── bootstrap ──────────────────────────────────────────────────────────────────
sys.path.insert(0, SCRIPT_DIR)
from core_engine import log_status
from trait_pool import TRAIT_POOL

# ── helpers ───────────────────────────────────────────────────────────────────

# Regex patterns to detect the "old" format inside a character description value
_RE_GENDER = re.compile(r'\b(male|female)\b', re.IGNORECASE)
_RE_AGE    = re.compile(r'\b(\d{1,3})\s+years?\s+old\b', re.IGNORECASE)


def _select_trait_unique(trait_category: str, gender: str, existing_descs: str) -> str:
    """Like _select_trait but avoids any option already present in existing_descs."""
    pool = TRAIT_POOL.get(trait_category)
    if not pool:
        return ""
    options = list(pool.get(gender, pool.get("ANY", [])))
    if not options:
        return ""
    random.shuffle(options)
    for candidate in options:
        if candidate.lower() not in existing_descs.lower():
            return candidate
    # All options already used → fall back to pure random
    return random.choice(options)


def _build_character_prompt(name: str, gender: str, age: int,
                            existing_chars: Optional[Dict[str, str]] = None) -> str:
    """Assembles the final visual prompt string from TRAIT_POOL.
    
    existing_chars: already-built {name: description} dict for the current file.
    Each selected trait will not duplicate any trait found in those descriptions.
    """
    log_status("BUILDER", f"Assembling traits for [{name}] ({gender}, {age}yo)...", "INFO")

    # Flatten all already-generated descriptions into one searchable string
    existing_descs = " ".join((existing_chars or {}).values())

    heritage    = _select_trait_unique("heritage", gender, existing_descs)
    gender_text = "male" if gender == "M" else "female"
    frame       = _select_trait_unique("frame",    gender, existing_descs)
    face        = _select_trait_unique("face",     gender, existing_descs)
    eye         = _select_trait_unique("eyes",     gender, existing_descs)
    hair        = _select_trait_unique("hair",     gender, existing_descs)

    prompt_parts = [
        heritage,
        f"{gender_text}, {age} years old",
        frame,
        face,
        eye,
        hair
    ]
    return ", ".join(p for p in prompt_parts if p)


def _parse_gender_age(value: str):
    """
    Extract (gender_code, age) from a description string.
    Returns ("M"|"F", int) or None if not found.
    """
    gender_match = _RE_GENDER.search(value)
    age_match    = _RE_AGE.search(value)
    if not gender_match or not age_match:
        return None
    gender_code = "M" if gender_match.group(1).lower() == "male" else "F"
    age = int(age_match.group(1))
    return gender_code, age


def _needs_rebuild(characters: dict) -> bool:
    """
    Return True iff `characters` is a non-empty dict AND every value
    contains both a gender marker and an age marker.
    """
    if not isinstance(characters, dict) or not characters:
        return False
    return all(_parse_gender_age(str(v)) is not None for v in characters.values())


def collect_json_files(stories_dir: str) -> list[str]:
    """Return sorted list of all .json file paths under stories_dir."""
    paths = []
    for fname in os.listdir(stories_dir):
        if fname.endswith(".json"):
            paths.append(os.path.join(stories_dir, fname))
    return sorted(paths)


def fix_one(json_path: str) -> str:
    """
    Process a single JSON file.
    Returns a status string describing what happened.
    """
    label = os.path.basename(json_path)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return f"[SKIP] {label}: cannot read JSON — {exc}"

    characters = data.get("characters")
    if not isinstance(characters, dict):
        return f"[SKIP] {label}: no 'characters' dict"

    if not _needs_rebuild(characters):
        return f"[SKIP] {label}: values don't all match gender+age pattern"

    # Rebuild every character value
    new_chars: Dict[str, str] = {}
    for name, old_value in characters.items():
        parsed = _parse_gender_age(str(old_value))
        if parsed is None:
            # Should not happen given _needs_rebuild check, but guard anyway
            log_status("FIX", f"Could not parse gender/age for '{name}', keeping original.", "WARN")
            new_chars[name] = old_value
            continue
        gender_code, age = parsed
        new_chars[name] = _build_character_prompt(name, gender_code, age, existing_chars=new_chars)
        log_status("FIX", f"  [{name}] {gender_code} {age}yo → rebuilt", "OK")


    # Write back — only overwrite 'characters', protect all other fields
    data["characters"] = new_chars
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"[ERROR] {label}: failed to write — {exc}"

    return f"[OK]    {label}: rebuilt {len(new_chars)} character(s)"


def main():
    json_files = collect_json_files(STORIES_DIR)

    if MAX_PROCESS_NUMBER > 0:
        print(f"Limiting to {MAX_PROCESS_NUMBER} file(s) for debugging.")
        json_files = json_files[:MAX_PROCESS_NUMBER]

    print(f"Found {len(json_files)} JSON file(s) to inspect in {STORIES_DIR}\n")

    ok = skip = err = 0
    for i, path in enumerate(json_files, 1):
        label = os.path.basename(path)
        print(f"[{i:03d}/{len(json_files):03d}] {label}")
        try:
            result = fix_one(path)
            print(f"        {result}")
            if result.startswith("[OK]"):
                ok += 1
            else:
                skip += 1
        except Exception as exc:
            print(f"        [ERROR] {label}: unexpected exception — {exc}")
            traceback.print_exc()
            err += 1

    print(f"\nDone. OK={ok}  skipped={skip}  errors={err}")


if __name__ == "__main__":
    main()
