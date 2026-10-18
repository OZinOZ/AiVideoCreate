# -*- coding: utf-8 -*-
"""
@file ghibli_asmr_final_studio.py
@brief 严格遵循原版三大 Prompt 逻辑 + RunningHub API 增强对接 + 海底世界约束
@details 策划(P1) -> 分镜(P2) -> 提示词(P3) -> 质量审查(Critic) -> 自动化生产(P4, 含Wan2.1风格锁定) -> 声音设计(P5)
@note [IP宇宙究极版] 视觉DNA锁定 + 强制误解结构 + 92分严厉评分 + 任务档案系统 + Shot Number适配
"""

import os
import time
import json
import logging
import re
import random
import sys
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
import requests
from google import genai
from google.genai import types
from openai import OpenAI

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GhibliASMR")

# ==========================================
# [用户配置区] 核心控制台
# ==========================================

# --- 1. 运行模式选择 ---
# "1": 全自动模式 (Full Auto)
# "2": 仅生成剧本和图片 (Script & Images Only)
# "3": 仅生成视频 (Video Only)
RUN_MODE = "1"

# --- 2. Mode 3 专用路径 ---
MODE_3_TARGET_PATH = ""

# --- 3. 故事配置 (FIXED_IDEA) ---
# 如果设为 None，程序将启动 [Golden Reef Universe] 随机生成新的一集。
FIXED_IDEA = None

# ==========================================
# 第一部分：全量配置 (CONFIGURATION)
# ==========================================

class PipelineConfig:
    """统一配置管理"""
    def __init__(self):
        self.provider = SETTINGS["PROVIDER"]
        self.base_path = SETTINGS["BASE_PATH"]
        self.target_length = SETTINGS["TARGET_LENGTH"]
        self.ideas_count = SETTINGS["IDEAS_COUNT"]
        self.runninghub_key = os.getenv("RUNNINGHUB_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.wf_t2i = SETTINGS["WF_TEXT_TO_IMAGE"]
        self.wf_i2v = SETTINGS["WF_IMAGE_TO_VIDEO"]

    def validate(self):
        if not self.runninghub_key: raise ValueError("Missing RUNNINGHUB_API_KEY")
        if self.provider == "GEMINI" and not self.gemini_key: raise ValueError("Missing GEMINI_API_KEY")
        if not self.openai_key: raise ValueError("Missing OPENAI_API_KEY")

SETTINGS = {
    "PROVIDER": "GEMINI",
    "G_MODEL": "gemini-2.5-pro", 
    "O_MODEL": "gpt-4o", 
    "WF_TEXT_TO_IMAGE": "2014487614874718210",
    "WF_IMAGE_TO_VIDEO": "2015643079415439361",
    "T2I_NODE": "111",
    "BASE_PATH": "./ghibli_asmr_output",
    "TARGET_LENGTH": 1,
    "IDEAS_COUNT": 1
}

# ==========================================
# [IP宇宙核心] 随机灵感库 (The Universe Bible)
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

# --- 提示词系统 (IP DNA + 强制结构) ---
PROMPTS = {
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

# ==========================================
# 第二部分：API & 工具 (稳定增强版)
# ==========================================

def robust_json_extract(text: str) -> Optional[Dict]:
    if not text: return None
    try:
        pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.S)
        clean_text = match.group(1) if match else text
        if not match: 
            start = text.find('{'); end = text.rfind('}')
            if start != -1 and end != -1: clean_text = text[start:end+1]
        
        clean_text = re.sub(r',\s*([\]}])', r'\1', clean_text)
        return json.loads(clean_text)
    except Exception as e:
        logger.error(f"JSON 解析失败: {e}\n片段: {text[:100]}...")
        return None

def safe_request(method, url, **kwargs):
    for i in range(3):
        try:
            resp = requests.request(method, url, timeout=60, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception: time.sleep(3)
    return None

def find_url_in_response(data: Any) -> Optional[str]:
    if isinstance(data, str) and data.startswith("http"):
        if any(data.lower().endswith(ext) for ext in [".mp4", ".mov", ".png", ".jpg", ".jpeg"]):
            return data
    if isinstance(data, list):
        for item in data:
            res = find_url_in_response(item)
            if res: return res
    if isinstance(data, dict):
        for key in ["fileUrl", "downloadUrl", "url", "output"]:
            if key in data:
                res = find_url_in_response(data[key])
                if res: return res
        for value in data.values():
            res = find_url_in_response(value)
            if res: return res
    return None

def upload_public(file_path: str) -> Optional[str]:
    if not os.path.exists(file_path): return None
    logger.info(f"☁️ 上传垫图: {os.path.basename(file_path)}")
    try:
        with open(file_path, 'rb') as f:
            resp = safe_request("POST", "https://tmpfiles.org/api/v1/upload", files={'file': f})
        if resp: return resp.json()['data']['url'].replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except: pass
    return None

def download_file(url: str, save_path: str) -> bool:
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
        return True
    except: return False

def submit_task(cfg: PipelineConfig, workflow_id: str, node_info_list: List[dict], desc: str = "Task") -> Optional[str]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cfg.runninghub_key}"}
    url_run = f"https://www.runninghub.ai/openapi/v2/run/workflow/{workflow_id}"
    
    task_id = None
    for attempt in range(5):
        resp = safe_request("POST", url_run, headers=headers, json={"nodeInfoList": node_info_list})
        if not resp: time.sleep(5); continue
        try:
            r_json = resp.json()
            if r_json.get("errorCode") == "421" or "limit" in str(r_json).lower():
                logger.warning(f"🚦 队列满 (421), 等待 30s...")
                time.sleep(30); continue
            task_id = r_json.get("data", {}).get("taskId") or r_json.get("taskId")
            if task_id: break
        except: time.sleep(5)

    if not task_id: 
        logger.error(f"❌ [{desc}] 任务提交失败")
        return None

    logger.info(f"🚀 [{desc}] 提交成功: {task_id}")
    
    url_qry = "https://www.runninghub.ai/openapi/v2/query"
    start_time = time.time()
    while time.time() - start_time < 3600:
        q_resp = safe_request("POST", url_qry, headers=headers, json={"taskId": task_id})
        if not q_resp: time.sleep(10); continue
        try:
            res = q_resp.json()
            status = (res.get("status") or res.get("data", {}).get("status", "")).upper()
            if status == "SUCCESS":
                found_url = find_url_in_response(res)
                if found_url: return found_url
                return None
            elif status == "FAILED": 
                logger.error(f"❌ 任务失败: {res}")
                return None
        except: pass
        time.sleep(10)
    return None

# ==========================================
# 业务逻辑 (AI Service)
# ==========================================

class AIService:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.gemini_client = genai.Client(api_key=cfg.gemini_key)
        self.openai_client = OpenAI(api_key=cfg.openai_key)

    def call_gemini(self, prompt: str) -> Optional[str]:
        try:
            resp = self.gemini_client.models.generate_content(
                model=SETTINGS["G_MODEL"], contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return resp.text
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            return None

    def call_chatgpt_critic(self, prompt: str) -> Optional[str]:
        try:
            resp = self.openai_client.chat.completions.create(
                model=SETTINGS["O_MODEL"], messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"Critic Error: {e}")
            return None

def init_project(cfg):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p_dir = os.path.join(cfg.base_path, f"Project_{ts}")
    paths = {"images": os.path.join(p_dir, "keyframes"), "videos": os.path.join(p_dir, "clips")}
    for p in paths.values(): os.makedirs(p, exist_ok=True)
    return p_dir, paths

def run_phase1_idea(service, cfg, p_dir):
    if FIXED_IDEA:
        logger.info("📄 使用顶部 FIXED_IDEA 配置。")
        if "episode_id" not in FIXED_IDEA: FIXED_IDEA["episode_id"] = f"GRR-FIXED-{random.randint(1000,9999)}"
        if "victim_short" not in FIXED_IDEA:
            FIXED_IDEA["victim_short"] = "A cute sea creature"
            FIXED_IDEA["danger_short"] = "A trap"
        with open(os.path.join(p_dir, "01_idea.json"), "w") as f:
            json.dump({"ideas": [FIXED_IDEA]}, f, indent=4)
        return FIXED_IDEA
    
    logger.info("🌌 启动 IP 宇宙生成器: Crimson & Azure 的新任务...")
    stimuli = get_random_stimuli()
    logger.info(f"🎲 任务档案: {stimuli['episode_id']} | 受害者: {stimuli['victim']}")
    
    prompt = PROMPTS["P1_IDEA"].format(**stimuli)
    res = service.call_gemini(prompt)
    data = robust_json_extract(res)
    
    if data: 
        data["ideas"][0]["archive_data"] = stimuli
        with open(os.path.join(p_dir, "01_idea.json"), "w") as f: json.dump(data, f, indent=4)
        return data["ideas"][0]
    return None

def run_phase2_storyboard(service, idea, p_dir):
    v_short = idea.get("victim_short", "Cute Victim")
    d_short = idea.get("danger_short", "Trap")
    e_action = idea.get("archive_data", {}).get("ending", "The victim waves goodbye.")
    
    prompt = PROMPTS["P2_STORYBOARD"].format(
        idea_title=idea['title'], 
        idea_description=idea['description'],
        victim_short=v_short,
        danger_short=d_short,
        ending_action=e_action
    )
    res = service.call_gemini(prompt)
    data = robust_json_extract(res)
    if data:
        with open(os.path.join(p_dir, "02_storyboard.json"), "w") as f: json.dump(data, f, indent=4)
        return data["storyboard"]
    return None

def run_phase3_with_critic(service, storyboard, idea, p_dir):
    v_short = idea.get("victim_short", "Victim")
    d_short = idea.get("danger_short", "Trap")
    
    # 构造初始 Prompt (增加了 shot_number 的指令)
    prompt_base = PROMPTS["P3_KEYFRAMES"].format(victim_short=v_short, danger_short=d_short)
    initial_prompt = f"{prompt_base}\n\nSTORYBOARD:\n{json.dumps(storyboard)}"
    
    current_prompt = initial_prompt
    
    for attempt in range(3):
        logger.info(f"🧠 [Phase 3] 正在生成提示词 (Attempt {attempt+1}/3)...")
        res = service.call_gemini(current_prompt)
        kf_data = robust_json_extract(res)
        
        if not kf_data or "keyframes" not in kf_data:
            logger.warning("⚠️ 格式错误，重试...")
            continue
            
        if len(kf_data["keyframes"]) != 6:
             logger.warning(f"⚠️ 镜头数不对 ({len(kf_data['keyframes'])} != 6)，重写...")
             current_prompt = f"{initial_prompt}\n\nERROR: Need EXACTLY 6 shots."
             continue

        logger.info("👮‍♂️ 发送给 ChatGPT 打分 (Strict Critic)...")
        critic_input = PROMPTS["CRITIC_REVIEW"].format(prompts_json=json.dumps(kf_data))
        critic_res = service.call_chatgpt_critic(critic_input)
        c_data = robust_json_extract(critic_res)
        
        score = c_data.get("score", 0) if c_data else 0
        feedback = c_data.get("feedback", "") if c_data else "No feedback"
        logger.info(f"📊 评分: {score} | 意见: {feedback}")
        
        if score >= 92:
            logger.info("✅ 评分通过！保存提示词。")
            with open(os.path.join(p_dir, "03_keyframes.json"), "w") as f: json.dump(kf_data, f, indent=4)
            return kf_data["keyframes"]
        
        logger.warning("❌ 分数未达标 (需 >= 92)，要求 Gemini 重写...")
        current_prompt = f"{initial_prompt}\n\n**CRITIC FEEDBACK (Score {score}):** {feedback}\nFIX IT TO REACH > 92."

    logger.error("🚫 达到最大重试次数，评分未通过。")
    return None

def execute_t2i_task(cfg, scene, sid, path):
    logger.info(f"🎨 [Shot {sid}] T2I 文生图...")
    node = [{"nodeId": SETTINGS["T2I_NODE"], "fieldName": "value", "fieldValue": scene.get("image_prompt", "")},
            {"nodeId": "69", "fieldName": "width", "fieldValue": 1080}, {"nodeId": "69", "fieldName": "height", "fieldValue": 1920}]
    
    for i in range(3):
        # 注意：这里使用 sid (即 shot_number) 作为文件名后缀，确保唯一
        url = submit_task(cfg, cfg.wf_t2i, node, f"Shot{sid}_T2I")
        if url: 
            local = os.path.join(path, f"scene_{sid}.png")
            if download_file(url, local): return local
        logger.warning(f"⚠️ Shot {sid} 生图失败，重试 ({i+1}/3)...")
        time.sleep(5)
    return None

def execute_i2v_task(cfg, scene, sid, img_path, path, seed):
    logger.info(f"🎥 [Shot {sid}] I2V 图生视频...")
    pub_url = upload_public(img_path)
    if not pub_url: return False
    node = [{"nodeId": "16", "fieldName": "positive_prompt", "fieldValue": scene.get("motion_prompt", "")},
            {"nodeId": "27", "fieldName": "seed", "fieldValue": str(seed)},
            {"nodeId": "41", "fieldName": "seed", "fieldValue": str(seed)},
            {"nodeId": "18", "fieldName": "image", "fieldValue": pub_url}]
    url = submit_task(cfg, cfg.wf_i2v, node, f"Shot{sid}_I2V")
    if url: return download_file(url, os.path.join(path, f"scene_{sid}.mp4"))
    return False

def run_mode_3_video_only(service, cfg):
    p_path = MODE_3_TARGET_PATH
    if not p_path or not os.path.exists(p_path):
        logger.error("❌ MODE_3_TARGET_PATH 无效")
        return

    kf_path = os.path.join(p_path, "03_keyframes.json")
    if not os.path.exists(kf_path):
        logger.error("❌ 找不到 03_keyframes.json")
        return
        
    with open(kf_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        keyframes = data.get("keyframes", [])

    img_dir = os.path.join(p_path, "keyframes")
    vid_dir = os.path.join(p_path, "clips")
    os.makedirs(vid_dir, exist_ok=True)

    logger.info(f"🚀 启动 Mode 3: 纯视频生成 (从 {len(keyframes)} 个镜头开始)")
    master_seed = random.randint(10**12, 10**13)
    
    # Mode 3 也使用相同的 shot_number 逻辑
    for i, s in enumerate(keyframes):
        # 优先用 json 里的 shot_number，如果没有就用 i+1
        shot_num = str(s.get("shot_number", i + 1))
        
        img = os.path.join(img_dir, f"scene_{shot_num}.png")
        if os.path.exists(img):
            try: sid_int = int(shot_num)
            except: sid_int = 1
            execute_i2v_task(cfg, s, shot_num, img, vid_dir, master_seed + sid_int*17)
            time.sleep(5)
    
    logger.info("🎉 Mode 3 完成。")

def main():
    cfg = PipelineConfig()
    try: cfg.validate()
    except ValueError as e:
        logger.error(f"配置验证失败: {e}")
        return

    service = AIService(cfg)
    logger.info(f"🤖 当前运行模式: {RUN_MODE}")
    
    if RUN_MODE == "3":
        run_mode_3_video_only(service, cfg)
        return

    project_dir, paths = init_project(cfg)
    if not project_dir: return
    
    logger.info(f"📂 新项目 ID: {os.path.basename(project_dir)}")

    # Step 1
    target_idea = run_phase1_idea(service, cfg, project_dir)
    if not target_idea: return
    
    # Step 2
    storyboard = run_phase2_storyboard(service, target_idea, project_dir)
    if not storyboard: return
    
    # Step 3
    keyframes = run_phase3_with_critic(service, storyboard, target_idea, project_dir)
    if not keyframes: return 
    
    # Step 4: 批量生图
    logger.info("PHASE 4: 批量生图 (Text-to-Image)...")
    success_imgs = 0
    
    # [修复逻辑] 使用 enumerate 确保绝对不会覆盖
    for i, s in enumerate(keyframes):
        # 优先尝试从 JSON 拿 shot_number，拿不到就用 i+1 兜底
        # 这里的 shot_num 就是最终的文件名后缀 scene_X.png
        shot_num = str(s.get("shot_number", i + 1))
        
        # 将确定的 shot_num 写回字典，供后续视频生成使用
        s["_final_shot_num"] = shot_num 
        
        if execute_t2i_task(cfg, s, shot_num, paths["images"]): 
            success_imgs += 1
        time.sleep(3)
        
    if RUN_MODE == "2":
        logger.info(f"🛑 [Mode 2] 图片生成完毕。路径: {project_dir}")
        return

    if success_imgs == 0:
        logger.error("❌ 无图片生成，中止。")
        return

    logger.info("PHASE 4.5: 批量视频生成...")
    master_seed = random.randint(10**12, 10**13)
    logger.info(f"🔐 Master Seed: {master_seed}")
    
    success_vids = 0
    for s in keyframes:
        # 使用刚才保存的 _final_shot_num，确保和图片对应
        shot_num = s.get("_final_shot_num", str(s.get("shot_number", "1")))
        
        img_path = os.path.join(paths["images"], f"scene_{shot_num}.png")
        if os.path.exists(img_path):
            try: sid_int = int(shot_num)
            except: sid_int = 1
            if execute_i2v_task(cfg, s, shot_num, img_path, paths["videos"], master_seed + sid_int*17):
                success_vids += 1
        time.sleep(5)
    
    if not success_vids: return
    
    # Step 5
    if "P4_SOUND_DESIGN" in PROMPTS:
        p5_context = PROMPTS["P4_SOUND_DESIGN"].format(keyframes_json=json.dumps(keyframes))
        res = service.call_gemini(p5_context)
        if res:
            with open(os.path.join(project_dir, "04_sound.json"), "w") as f: f.write(res)
            
    logger.info(f"🎉 结束。路径: {project_dir}")

if __name__ == "__main__":
    main()