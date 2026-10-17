# -*- coding: utf-8 -*-
"""
Ghibli ASMR Studio - Flux2 Klein 9B + Wan2.1 Locked Edition
强化版：
- Blueprint锁定
- Motion物理协议
- Wan2.1主种子风格一致系统
"""

import os
import time
import json
import logging
import re
import random
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import requests
from google import genai
from google.genai import types
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GhibliASMR_LOCKED")

# =========================
# 配置
# =========================

SETTINGS = {
    "PROVIDER": "GEMINI",
    "G_MODEL": "gemini-2.0-flash",
    "O_MODEL": "gpt-4o",
    "WF_TEXT_TO_IMAGE": "2014487614874718210",
    "WF_IMAGE_TO_VIDEO": "2015643079415439361",
    "T2I_NODE": "111",
    "BASE_PATH": "./ghibli_locked_output",
    "TARGET_LENGTH": 1,
    "IDEAS_COUNT": 1
}

# =========================
# 强化 Prompt 系统
# =========================

PROMPTS = {}

PROMPTS["P1_IDEA"] = """
You are an underwater cinematic ritual designer.

STRICT RULES:
- Only ONE marine creature.
- Purely physical task.
- Must end with clear physical final frame.

Output JSON:
{
 "ideas":[
   {
     "id":1,
     "title":"",
     "main_creature":"",
     "core_activity":"",
     "final_frame":"",
     "shot_count":8
   }
 ]
}
"""

PROMPTS["P2_STORYBOARD"] = """
Based on idea: {idea_title}

You MUST define:

{
 "character_blueprint":{
   "species":"",
   "body_color":"",
   "eye_shape":"",
   "limb_structure":"",
   "distinct_feature":"",
   "size_ratio":"small"
 },
 "environment_lock":{
   "water_color":"",
   "light_type":"",
   "seafloor_type":"",
   "background_elements":""
 },
 "storyboard":[
   {
     "scene_id":1,
     "physical_action":"",
     "visual_result":""
   }
 ]
}
"""

PROMPTS["P3_KEYFRAMES"] = """
INPUT STORYBOARD JSON:
{storyboard_json}

GLOBAL STYLE:
Studio Ghibli watercolor, pastel underwater, cinematic volumetric light.

ANTI HUMAN LOCK:
no humans, no upright, no hands, no fingers.

MOTION PHYSICS PROTOCOL:
Each motion must include:
- direction
- speed
- contact
- environment reaction

Output JSON:
{
 "keyframes":[
   {
     "scene_id":1,
     "image_prompt":"",
     "motion_prompt":""
   }
 ]
}
"""

# =========================
# 工具函数
# =========================

def safe_json_loads(text):
    if not text:
        return None
    try:
        match = re.search(r'(\{.*\})', text, re.S)
        clean = match.group(1) if match else text
        clean = re.sub(r',\s*([\]}])', r'\1', clean)
        return json.loads(clean)
    except:
        return None

def safe_request(method, url, **kwargs):
    for _ in range(3):
        try:
            r = requests.request(method, url, timeout=60, **kwargs)
            r.raise_for_status()
            return r
        except:
            time.sleep(3)
    return None

# =========================
# AI 服务
# =========================

class AIService:
    def __init__(self):
        if SETTINGS["PROVIDER"] == "GEMINI":
            self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        else:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def call(self, prompt):
        try:
            if SETTINGS["PROVIDER"] == "GEMINI":
                resp = self.client.models.generate_content(
                    model=SETTINGS["G_MODEL"],
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                return resp.text
            else:
                resp = self.client.chat.completions.create(
                    model=SETTINGS["O_MODEL"],
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"AI error: {e}")
            return None

# =========================
# RunningHub
# =========================

def submit_task(workflow_id, node_info_list):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('RUNNINGHUB_API_KEY')}"
    }

    url = f"https://www.runninghub.ai/openapi/v2/run/workflow/{workflow_id}"
    r = safe_request("POST", url, headers=headers, json={"nodeInfoList": node_info_list})
    if not r:
        return None

    task_id = r.json().get("data", {}).get("taskId")
    if not task_id:
        return None

    query_url = "https://www.runninghub.ai/openapi/v2/query"

    for _ in range(180):
        time.sleep(10)
        q = safe_request("POST", query_url, headers=headers, json={"taskId": task_id})
        if not q:
            continue
        data = q.json()
        status = data.get("data", {}).get("status", "").upper()
        if status in ["SUCCESS", "COMPLETED"]:
            results = data.get("data", {}).get("results", [])
            for item in results:
                url = item.get("url")
                if url:
                    return url
        if status in ["FAILED", "ERROR"]:
            return None
    return None

# =========================
# 主流程
# =========================

def main():

    service = AIService()

    project_dir = os.path.join(
        SETTINGS["BASE_PATH"],
        datetime.now().strftime("Project_%Y%m%d_%H%M%S")
    )
    os.makedirs(project_dir, exist_ok=True)

    # ===== Phase 1 =====
    p1 = service.call(PROMPTS["P1_IDEA"])
    idea = safe_json_loads(p1)["ideas"][0]

    # ===== Phase 2 =====
    p2 = service.call(PROMPTS["P2_STORYBOARD"].format(
        idea_title=idea["title"]
    ))
    storyboard_full = safe_json_loads(p2)

    # ===== Phase 3 =====
    p3 = service.call(PROMPTS["P3_KEYFRAMES"].format(
        storyboard_json=json.dumps(storyboard_full, ensure_ascii=False)
    ))
    keyframes = safe_json_loads(p3)["keyframes"]

    # ===== Seed 锁定系统 =====
    master_seed = random.randint(10**12, 10**13 - 1)
    logger.info(f"MASTER SEED: {master_seed}")

    for scene in keyframes:
        sid = scene["scene_id"]
        scene_seed = master_seed + sid * 17

        # ===== T2I =====
        t2i_nodes = [
            {"nodeId": SETTINGS["T2I_NODE"], "fieldName": "value", "fieldValue": scene["image_prompt"]}
        ]

        img_url = submit_task(SETTINGS["WF_TEXT_TO_IMAGE"], t2i_nodes)
        if not img_url:
            continue

        # ===== I2V =====
        i2v_nodes = [
            {"nodeId": "16", "fieldName": "positive_prompt", "fieldValue": scene["motion_prompt"]},
            {"nodeId": "27", "fieldName": "seed", "fieldValue": str(scene_seed)},
            {"nodeId": "41", "fieldName": "seed", "fieldValue": str(scene_seed)},
            {"nodeId": "18", "fieldName": "image", "fieldValue": img_url}
        ]

        submit_task(SETTINGS["WF_IMAGE_TO_VIDEO"], i2v_nodes)

    logger.info("全部完成")

if __name__ == "__main__":
    main()
