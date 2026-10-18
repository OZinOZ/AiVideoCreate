# -*- coding: utf-8 -*-
"""
Ghibli ASMR Studio (统一版)  —— 合并自 asmr.py 与 asmr_chatgpt.py

预设 (--preset):
  rescue  原 asmr.py  : Golden Reef Rescue IP宇宙 / 6镜头 / ChatGPT 92分评审 / 三种运行模式
  locked  原 asmr_chatgpt.py : Flux2 Klein 9B + Wan2.1 Locked Edition (Blueprint锁定 + 主种子)

运行模式 (--mode, 仅 rescue 有评审; locked 同样支持):
  1 全自动   2 仅剧本+图片   3 仅视频 (需 --project 指向已有项目目录)

环境变量: RUNNINGHUB_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY
所有 Prompt 保持原文。
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GhibliASMR")

# ==========================================
# 公共配置
# ==========================================
COMMON = {
    "O_MODEL": "gpt-4o",
    "WF_TEXT_TO_IMAGE": "2014487614874718210",
    "WF_IMAGE_TO_VIDEO": "2015643079415439361",
    "T2I_NODE": "111",
}

# ==========================================
# [rescue] IP 宇宙随机灵感库
# ==========================================
def get_random_stimuli():
    ep_id = f"GRR-EP-{random.randint(1000, 9999)}"

    victims = [
        "A Baby Sperm Whale (round head, tiny eyes, looks lost)",
        "A Giant Green Sea Turtle (golden shell patterns, gentle eyes)",
        "A Spotted Eagle Ray (smiling face, flapping soft wings)",
        "A Chubby Manatee (slow moving, peaceful)",
        "A Confused Sunfish (Mola Mola) (large flat body, clumsy)",
        "A Family of Clownfish (huddled together in fear)",
        "A Tiny Seahorse (curled tail, shaking with fear)"
    ]

    dangers = [
        "A tangle of transparent Nylon Fishing Net",
        "A tight Plastic Six-Pack Ring",
        "A thick rough Rope knotted around the tail",
        "A ghost Fishing Line wrapped around the body",
        "A heavy fallen Branch pinning it down"
    ]

    endings = [
        "The Victim nuzzles Crimson's claw in gratitude.",
        "The Victim performs a happy spin before swimming away.",
        "Azure waves a long antenna as the Victim fades into the blue.",
        "Crimson clicks his claws softly like a goodbye salute."
    ]

    return {
        "episode_id": ep_id,
        "victim": random.choice(victims),
        "danger": random.choice(dangers),
        "ending": random.choice(endings)
    }

# ==========================================
# Prompt 系统 (原文)
# ==========================================
PROMPTS_RESCUE = {
    "P1_IDEA": """
You are the Showrunner for 'Golden Reef Rescue'.
**EPISODE ID**: {episode_id}
**VARIABLES**: Victim: {victim} | Danger: {danger} | Ending: {ending}

**UNIVERSE RULES**:
- **Heroes**: Crimson (Red Crab) & Azure (Blue Lobster).
- **Tone**: Misunderstood "Attack" -> Rescue -> Warmth.

**TASK**: 
Write the episode summary following the Misunderstanding Formula.
Output JSON: {{"ideas": [{{"id":1, "episode_id": "{episode_id}", "title": "Golden Reef Rescue: [Victim]", "description": "...", "shot_count": 6, "victim_short": "[Short visual desc]", "danger_short": "[Short visual desc]"}}]}}
""",

    "P2_STORYBOARD": """
You are a Visual Storyboard Director (Ghibli Specialist).
Story Context: {idea_description}
**Target: 6 Shots (Strict IP Formula)**.

**CORE CHARACTERS (MUST APPEAR)**:
- **Crimson**: Red Round Crab (Big Claws).
- **Azure**: Blue-Purple Lobster (Long Antennae).
- **Victim**: {victim_short}.

**NARRATIVE ARC (The "Misunderstanding" Formula)**:
1. **Shot 1 (0-4s): The Threat**. Wide shot. Crimson and Azure rush aggressively towards the [Victim]. Claws raised high. The [Victim] looks terrified. **Vibe: Panic/Ambush**.
2. **Shot 2 (4-8s): The Fear**. Close-up on [Victim]'s face. Eyes wide, struggling against **{danger_short}**, backing away from the approaching [Helper].
3. **Shot 3 (8-12s): The Suspense**. Crimson's massive claw snaps shut *right next* to the [Victim]'s neck/body. It looks like a bite! **Peak Tension**.
4. **Shot 4 (12-16s): The Reveal**. Extreme Close-up (Macro). Reveal Crimson's claw is actually **snipping the {danger_short}**. Azure helps pull the debris away. **Vibe: Relief**.
5. **Shot 5 (16-20s): The Release**. The {danger_short} falls away. A burst of bubbles rises. The [Victim] stretches freely.
6. **Shot 6 (20-24s): The Connection**. {ending_action}. Warm golden sunlight fills the screen. **Vibe: Healing**.

Output JSON: {{"storyboard": [{{"scene_id": 1, "description": "..."}}, ...]}}
""",

    "P3_KEYFRAMES": """
You are a Master Visual Planner of **Ghibli Underwater Rescue**.
Design the "Keyframe" image prompts and "Motion" prompts.

**HERO VISUAL DNA (DO NOT CHANGE)**:
- **Crimson (Crab)**: Wide oval body, two oversized rounded claws, small black eyes on short stalks, matte deep crimson shell.
- **Azure (Lobster)**: Long segmented body, blue-to-purple gradient, thin elegant claws, two long antennae extending backward.
- **Environment**: Golden Reef. Turquoise water with eternal golden sunlight beams (Tyndall effect).

**STRICT SHOT STRUCTURE (DO NOT DEVIATE)**:
- **Shots 1-3**: MUST look like an aggressive ATTACK/AMBUSH. Claws open, fast movement, dynamic shadows.
- **Shot 4**: MUST be the REVEAL. Extreme close-up of cutting the Danger.
- **Shot 5**: Debris falls away. Bubbles rise.
- **Shot 6**: Emotional resolution. Soft focus, warm light.

**CHARACTERS FOR THIS SCENE**:
- Victim: {victim_short}
- Danger: {danger_short}

**MOTION (ASMR)**:
- Focus on: "Claws snapping (visual)", "Debris falling", "Bubbles rising", "Slow gentle drifting".

**OUTPUT FORMAT**:
Use 'shot_number' (1, 2, 3...) for the sequence. 'scene_id' represents the episode ID (usually 1).

Output JSON: {{"keyframes": [{{"scene_id": 1, "shot_number": 1, "image_prompt": "...", "motion_prompt": "..."}}]}}
""",

    "CRITIC_REVIEW": """
You are a Strict Art Director for Studio Ghibli.
Review the Prompts.

**Strict Checklist (Pass only if > 92)**:
1. **Visual DNA**: Do Crimson and Azure match their specific descriptions? (Red Round Crab / Blue Purple Lobster).
2. **Structure**: Does Shot 1-3 look like a threat? Does Shot 4 reveal the rescue?
3. **Style**: Is it Ghibli Watercolor?
4. **Anatomy**: Are the animals physically correct?

Input: {prompts_json}
Output JSON ONLY: {{"score": 92, "feedback": "Perfect."}} (If < 92, give specific critique).
"""
}

PROMPTS_LOCKED = {}

PROMPTS_LOCKED["P1_IDEA"] = """
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

PROMPTS_LOCKED["P2_STORYBOARD"] = """
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

PROMPTS_LOCKED["P3_KEYFRAMES"] = """
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

PRESETS = {
    "rescue": {
        "desc": "Golden Reef Rescue (原 asmr.py): 6镜头 + 92分评审",
        "prompts": PROMPTS_RESCUE,
        "g_model": "gemini-2.5-pro",
        "base_path": "./ghibli_asmr_output",
        "use_format": True,     # 模板中的 {{ }} 由 str.format 还原
        "t2i_size": (1080, 1920),
        "critic": True,
        "needs_openai": True,
    },
    "locked": {
        "desc": "Locked Edition (原 asmr_chatgpt.py): Blueprint锁定 + 主种子",
        "prompts": PROMPTS_LOCKED,
        "g_model": "gemini-2.0-flash",
        "base_path": "./ghibli_locked_output",
        "use_format": False,    # 模板含裸 JSON 花括号，只替换指定占位符
        "t2i_size": None,
        "critic": False,
        "needs_openai": False,
    },
}


def fill(preset: Dict, key: str, **kw) -> str:
    """填充 Prompt 模板, 不改动模板文字。"""
    tpl = preset["prompts"][key]
    if preset["use_format"]:
        return tpl.format(**kw)
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl

# ==========================================
# API & 工具
# ==========================================
def robust_json_extract(text: str) -> Optional[Dict]:
    if not text:
        return None
    try:
        pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.S)
        clean_text = match.group(1) if match else text
        if not match:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                clean_text = text[start:end + 1]
        clean_text = re.sub(r',\s*([\]}])', r'\1', clean_text)
        return json.loads(clean_text)
    except Exception as e:
        logger.error(f"JSON 解析失败: {e}\n片段: {text[:100]}...")
        return None


def safe_request(method, url, **kwargs):
    for _ in range(3):
        try:
            resp = requests.request(method, url, timeout=60, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception:
            time.sleep(3)
    return None


def find_url_in_response(data: Any) -> Optional[str]:
    if isinstance(data, str) and data.startswith("http"):
        if any(data.lower().endswith(ext) for ext in [".mp4", ".mov", ".png", ".jpg", ".jpeg"]):
            return data
    if isinstance(data, list):
        for item in data:
            res = find_url_in_response(item)
            if res:
                return res
    if isinstance(data, dict):
        for key in ["fileUrl", "downloadUrl", "url", "output"]:
            if key in data:
                res = find_url_in_response(data[key])
                if res:
                    return res
        for value in data.values():
            res = find_url_in_response(value)
            if res:
                return res
    return None


def upload_public(file_path: str) -> Optional[str]:
    if not os.path.exists(file_path):
        return None
    logger.info(f"☁️ 上传垫图: {os.path.basename(file_path)}")
    try:
        with open(file_path, 'rb') as f:
            resp = safe_request("POST", "https://tmpfiles.org/api/v1/upload", files={'file': f})
        if resp:
            return resp.json()['data']['url'].replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception:
        pass
    return None


def download_file(url: str, save_path: str) -> bool:
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception:
        return False


def submit_task(rh_key: str, workflow_id: str, node_info_list: List[dict], desc: str = "Task") -> Optional[str]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {rh_key}"}
    url_run = f"https://www.runninghub.ai/openapi/v2/run/workflow/{workflow_id}"

    task_id = None
    for _ in range(5):
        resp = safe_request("POST", url_run, headers=headers, json={"nodeInfoList": node_info_list})
        if not resp:
            time.sleep(5)
            continue
        try:
            r_json = resp.json()
            if r_json.get("errorCode") == "421" or "limit" in str(r_json).lower():
                logger.warning("🚦 队列满 (421), 等待 30s...")
                time.sleep(30)
                continue
            task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
            if task_id:
                break
        except Exception:
            time.sleep(5)

    if not task_id:
        logger.error(f"❌ [{desc}] 任务提交失败")
        return None

    logger.info(f"🚀 [{desc}] 提交成功: {task_id}")

    url_qry = "https://www.runninghub.ai/openapi/v2/query"
    start_time = time.time()
    while time.time() - start_time < 3600:
        q_resp = safe_request("POST", url_qry, headers=headers, json={"taskId": task_id})
        if not q_resp:
            time.sleep(10)
            continue
        try:
            res = q_resp.json()
            status = (res.get("status") or res.get("data", {}).get("status", "")).upper()
            if status in ("SUCCESS", "COMPLETED"):
                return find_url_in_response(res)
            elif status in ("FAILED", "ERROR"):
                logger.error(f"❌ 任务失败: {res}")
                return None
        except Exception:
            pass
        time.sleep(10)
    return None


class AIService:
    def __init__(self, g_model: str, o_model: str, need_openai: bool):
        from google import genai
        from google.genai import types
        self._types = types
        self.g_model = g_model
        self.o_model = o_model
        self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.openai_client = None
        if need_openai:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def call_gemini(self, prompt: str) -> Optional[str]:
        try:
            resp = self.gemini_client.models.generate_content(
                model=self.g_model, contents=prompt,
                config=self._types.GenerateContentConfig(response_mime_type="application/json")
            )
            return resp.text
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            return None

    def call_chatgpt_critic(self, prompt: str) -> Optional[str]:
        try:
            resp = self.openai_client.chat.completions.create(
                model=self.o_model, messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"Critic Error: {e}")
            return None

# ==========================================
# 流程
# ==========================================
def init_project(base_path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p_dir = os.path.join(base_path, f"Project_{ts}")
    paths = {"images": os.path.join(p_dir, "keyframes"), "videos": os.path.join(p_dir, "clips")}
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return p_dir, paths


def dump(p_dir, name, data):
    with open(os.path.join(p_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def phase1_idea(service, preset, p_dir, fixed_idea):
    if preset is PRESETS["rescue"]:
        if fixed_idea:
            logger.info("📄 使用 --idea-file 配置。")
            if "episode_id" not in fixed_idea:
                fixed_idea["episode_id"] = f"GRR-FIXED-{random.randint(1000, 9999)}"
            if "victim_short" not in fixed_idea:
                fixed_idea["victim_short"] = "A cute sea creature"
                fixed_idea["danger_short"] = "A trap"
            dump(p_dir, "01_idea.json", {"ideas": [fixed_idea]})
            return fixed_idea

        logger.info("🌌 启动 IP 宇宙生成器: Crimson & Azure 的新任务...")
        stimuli = get_random_stimuli()
        logger.info(f"🎲 任务档案: {stimuli['episode_id']} | 受害者: {stimuli['victim']}")
        data = robust_json_extract(service.call_gemini(fill(preset, "P1_IDEA", **stimuli)))
        if data:
            data["ideas"][0]["archive_data"] = stimuli
            dump(p_dir, "01_idea.json", data)
            return data["ideas"][0]
        return None

    data = robust_json_extract(service.call_gemini(fill(preset, "P1_IDEA")))
    if data and data.get("ideas"):
        dump(p_dir, "01_idea.json", data)
        return data["ideas"][0]
    return None


def phase2_storyboard(service, preset, idea, p_dir):
    if preset is PRESETS["rescue"]:
        prompt = fill(
            preset, "P2_STORYBOARD",
            idea_title=idea['title'],
            idea_description=idea['description'],
            victim_short=idea.get("victim_short", "Cute Victim"),
            danger_short=idea.get("danger_short", "Trap"),
            ending_action=idea.get("archive_data", {}).get("ending", "The victim waves goodbye."),
        )
        data = robust_json_extract(service.call_gemini(prompt))
        if data:
            dump(p_dir, "02_storyboard.json", data)
            return data["storyboard"]
        return None

    data = robust_json_extract(service.call_gemini(fill(preset, "P2_STORYBOARD", idea_title=idea["title"])))
    if data:
        dump(p_dir, "02_storyboard.json", data)
    return data  # locked: 完整 JSON (含 blueprint / environment_lock)


def phase3_keyframes(service, preset, storyboard, idea, p_dir):
    if preset is PRESETS["rescue"]:
        prompt_base = fill(preset, "P3_KEYFRAMES",
                           victim_short=idea.get("victim_short", "Victim"),
                           danger_short=idea.get("danger_short", "Trap"))
        initial_prompt = f"{prompt_base}\n\nSTORYBOARD:\n{json.dumps(storyboard)}"
        current_prompt = initial_prompt

        for attempt in range(3):
            logger.info(f"🧠 [Phase 3] 正在生成提示词 (Attempt {attempt + 1}/3)...")
            kf_data = robust_json_extract(service.call_gemini(current_prompt))

            if not kf_data or "keyframes" not in kf_data:
                logger.warning("⚠️ 格式错误，重试...")
                continue

            if len(kf_data["keyframes"]) != 6:
                logger.warning(f"⚠️ 镜头数不对 ({len(kf_data['keyframes'])} != 6)，重写...")
                current_prompt = f"{initial_prompt}\n\nERROR: Need EXACTLY 6 shots."
                continue

            logger.info("👮‍♂️ 发送给 ChatGPT 打分 (Strict Critic)...")
            critic_input = fill(preset, "CRITIC_REVIEW", prompts_json=json.dumps(kf_data))
            c_data = robust_json_extract(service.call_chatgpt_critic(critic_input))

            score = c_data.get("score", 0) if c_data else 0
            feedback = c_data.get("feedback", "") if c_data else "No feedback"
            logger.info(f"📊 评分: {score} | 意见: {feedback}")

            if score >= 92:
                logger.info("✅ 评分通过！保存提示词。")
                dump(p_dir, "03_keyframes.json", kf_data)
                return kf_data["keyframes"]

            logger.warning("❌ 分数未达标 (需 >= 92)，要求 Gemini 重写...")
            current_prompt = f"{initial_prompt}\n\n**CRITIC FEEDBACK (Score {score}):** {feedback}\nFIX IT TO REACH > 92."

        logger.error("🚫 达到最大重试次数，评分未通过。")
        return None

    kf = robust_json_extract(service.call_gemini(
        fill(preset, "P3_KEYFRAMES", storyboard_json=json.dumps(storyboard, ensure_ascii=False))))
    if kf and kf.get("keyframes"):
        dump(p_dir, "03_keyframes.json", kf)
        return kf["keyframes"]
    return None


def shot_id(scene: Dict, i: int) -> str:
    return str(scene.get("shot_number", scene.get("scene_id", i + 1)))


def to_int(s: str) -> int:
    try:
        return int(s)
    except Exception:
        return 1


def t2i(rh_key, preset, scene, sid, path):
    logger.info(f"🎨 [Shot {sid}] T2I 文生图...")
    node = [{"nodeId": COMMON["T2I_NODE"], "fieldName": "value", "fieldValue": scene.get("image_prompt", "")}]
    if preset["t2i_size"]:
        w, h = preset["t2i_size"]
        node += [{"nodeId": "69", "fieldName": "width", "fieldValue": w},
                 {"nodeId": "69", "fieldName": "height", "fieldValue": h}]
    for i in range(3):
        url = submit_task(rh_key, COMMON["WF_TEXT_TO_IMAGE"], node, f"Shot{sid}_T2I")
        if url:
            local = os.path.join(path, f"scene_{sid}.png")
            if download_file(url, local):
                return local
        logger.warning(f"⚠️ Shot {sid} 生图失败，重试 ({i + 1}/3)...")
        time.sleep(5)
    return None


def i2v(rh_key, scene, sid, img_path, path, seed):
    logger.info(f"🎥 [Shot {sid}] I2V 图生视频...")
    pub_url = upload_public(img_path)
    if not pub_url:
        return False
    node = [{"nodeId": "16", "fieldName": "positive_prompt", "fieldValue": scene.get("motion_prompt", "")},
            {"nodeId": "27", "fieldName": "seed", "fieldValue": str(seed)},
            {"nodeId": "41", "fieldName": "seed", "fieldValue": str(seed)},
            {"nodeId": "18", "fieldName": "image", "fieldValue": pub_url}]
    url = submit_task(rh_key, COMMON["WF_IMAGE_TO_VIDEO"], node, f"Shot{sid}_I2V")
    if url:
        return download_file(url, os.path.join(path, f"scene_{sid}.mp4"))
    return False


def run_video_only(rh_key, project_path):
    if not project_path or not os.path.exists(project_path):
        logger.error("❌ --project 路径无效")
        return
    kf_path = os.path.join(project_path, "03_keyframes.json")
    if not os.path.exists(kf_path):
        logger.error("❌ 找不到 03_keyframes.json")
        return
    with open(kf_path, "r", encoding="utf-8") as f:
        keyframes = json.load(f).get("keyframes", [])

    img_dir = os.path.join(project_path, "keyframes")
    vid_dir = os.path.join(project_path, "clips")
    os.makedirs(vid_dir, exist_ok=True)

    logger.info(f"🚀 启动 Mode 3: 纯视频生成 (从 {len(keyframes)} 个镜头开始)")
    master_seed = random.randint(10**12, 10**13)
    for i, s in enumerate(keyframes):
        sid = shot_id(s, i)
        img = os.path.join(img_dir, f"scene_{sid}.png")
        if os.path.exists(img):
            i2v(rh_key, s, sid, img, vid_dir, master_seed + to_int(sid) * 17)
            time.sleep(5)
    logger.info("🎉 Mode 3 完成。")


def main():
    ap = argparse.ArgumentParser(description="Ghibli ASMR Studio (rescue / locked)")
    ap.add_argument("--preset", choices=list(PRESETS), default="rescue")
    ap.add_argument("--list", action="store_true", help="列出预设")
    ap.add_argument("--mode", choices=["1", "2", "3"], default="1", help="1全自动 2仅剧本+图片 3仅视频")
    ap.add_argument("--project", default="", help="mode 3 的项目目录")
    ap.add_argument("--idea-file", default="", help="(rescue) 固定 idea 的 JSON 文件")
    ap.add_argument("--base-path", default="")
    ap.add_argument("--g-model", default="")
    ap.add_argument("--o-model", default=COMMON["O_MODEL"])
    args = ap.parse_args()

    if args.list:
        for k, v in PRESETS.items():
            print(f"  {k:8s} {v['desc']}")
        return

    preset = PRESETS[args.preset]
    rh_key = os.getenv("RUNNINGHUB_API_KEY")
    missing = [k for k, ok in [("RUNNINGHUB_API_KEY", rh_key),
                               ("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY") or args.mode == "3"),
                               ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY") or not preset["needs_openai"] or args.mode == "3")]
               if not ok]
    if missing:
        logger.error(f"配置验证失败: Missing {', '.join(missing)}")
        return

    logger.info(f"🤖 预设: {args.preset} | 运行模式: {args.mode}")
    if args.mode == "3":
        run_video_only(rh_key, args.project)
        return

    service = AIService(args.g_model or preset["g_model"], args.o_model, preset["needs_openai"])
    fixed_idea = None
    if args.idea_file:
        with open(args.idea_file, "r", encoding="utf-8") as f:
            fixed_idea = json.load(f)

    project_dir, paths = init_project(args.base_path or preset["base_path"])
    logger.info(f"📂 新项目 ID: {os.path.basename(project_dir)}")

    idea = phase1_idea(service, preset, project_dir, fixed_idea)
    if not idea:
        return
    storyboard = phase2_storyboard(service, preset, idea, project_dir)
    if not storyboard:
        return
    keyframes = phase3_keyframes(service, preset, storyboard, idea, project_dir)
    if not keyframes:
        return

    logger.info("PHASE 4: 批量生图 (Text-to-Image)...")
    success_imgs = 0
    for i, s in enumerate(keyframes):
        sid = shot_id(s, i)
        s["_final_shot_num"] = sid
        if t2i(rh_key, preset, s, sid, paths["images"]):
            success_imgs += 1
        time.sleep(3)

    if args.mode == "2":
        logger.info(f"🛑 [Mode 2] 图片生成完毕。路径: {project_dir}")
        return
    if success_imgs == 0:
        logger.error("❌ 无图片生成，中止。")
        return

    logger.info("PHASE 4.5: 批量视频生成...")
    master_seed = random.randint(10**12, 10**13)
    logger.info(f"🔐 Master Seed: {master_seed}")
    ok = 0
    for s in keyframes:
        sid = s["_final_shot_num"]
        img_path = os.path.join(paths["images"], f"scene_{sid}.png")
        if os.path.exists(img_path):
            if i2v(rh_key, s, sid, img_path, paths["videos"], master_seed + to_int(sid) * 17):
                ok += 1
        time.sleep(5)
    logger.info(f"🎉 结束 ({ok}/{len(keyframes)} 视频)。路径: {project_dir}")


if __name__ == "__main__":
    main()
