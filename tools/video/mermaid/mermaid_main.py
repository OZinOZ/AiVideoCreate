"""!
@file main.py
@brief 视频生成主流水线 V18.2.8
@details 物理修正：找回所有 [Step X] 打印。锁定右上角 Subscribe 坐标与假透明抠图。
@author Gemini AI
"""

import os
import json
import sys
import random
from openai import OpenAI
import mermaid_func as mf

def init_context():
    """!
    @brief 初始化项目上下文配置。
    @return tuple (DATA, CFG, STYLES, BACKUP, PATHS)
    """
    config_json_path = "mermaid.json"
    if not os.path.exists(config_json_path):
        print("❌ [Fatal Error] 配置文件缺失，物理熔断。")
        sys.exit(1)
    with open(config_json_path, "r", encoding="utf-8") as f_in:
        project_data = json.load(f_in)
    cfg_config = project_data["CONFIG"]
    path_mapping = {k: os.path.join(cfg_config["BASE_DIR"], v) for k, v in {
        "music": "music", "bg": "background", "mermaid": "mermaid_assets",
        "branding": "branding", "temp_std": "temp_standardized",
        "temp_video": "temp_video.mp4", "temp_audio_raw": "temp_audio_raw.wav",
        "temp_audio_mastered": "temp_audio_mastered.mp3", 
        "overlay_json": "overlay_plan.json", "concat_list": "concat_list.txt"
    }.items()}
    path_mapping["output"] = os.path.join(cfg_config["BASE_DIR"], f"FINAL_MASTER_V{project_data['PROJ_VERSION']}.mp4")
    path_mapping["motion_cache"] = os.path.join(path_mapping["temp_std"], "motion_metadata.json")
    return project_data, cfg_config, project_data["STYLE_POOL"], project_data["BACKUP_CAPTIONS"], path_mapping

DATA, CFG, STYLES, BACKUP, PATHS = init_context()

def fetch_safe_captions():
    """!
    @brief 字幕语义采集。
    @return list[str]
    """
    print("📡 [API] 正在采集字幕语义...")
    api_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    gathered_captions = []
    try:
        for prompt_key in ["20 melancholy ocean", "20 healing ocean"]:
            api_resp = api_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role":"user","content":f"{prompt_key} JSON array."}],
                timeout=CFG["API_TIMEOUT"]
            )
            gathered_captions.extend(json.loads(api_resp.choices[0].message.content.strip()))
    except Exception:
        gathered_captions = list(BACKUP)
    return [c["text"] if isinstance(c, dict) and "text" in c else str(c) for c in gathered_captions]

def render_final_fusion(render_plan, video_limit_seconds):
    """!
    @brief [Step 6] 融合渲染原子调度。
    @param render_plan 渲染计划字典。
    @param video_limit_seconds 时长限制。
    @return bool
    """
    print("🔥 [Step 6] 启动融合渲染调度 (透明度修复版)...")
    ffmpeg_inputs = ["-i", PATHS["temp_video"], "-i", PATHS["temp_audio_mastered"]]
    filter_steps = ["[0:v]setpts=PTS-STARTPTS,format=yuva420p[base]"]
    current_label = "[base]"
    def get_index(): return ffmpeg_inputs.count("-i")

    # 1. Branding (右上角锁定补丁)
    sub_path = os.path.join(PATHS["branding"], "subscribe.png")
    if render_plan.get("branding") and os.path.exists(sub_path):
        input_idx = get_index(); ffmpeg_inputs += ["-i", sub_path]
        enable_str = "+".join([f"between(t,{b['start']},{b['end']})" for b in render_plan["branding"]])
        # 补丁：chromakey 移除棋盘格底色，锁定右上角
        filter_steps.append(f"[{input_idx}:v]chromakey=0xCBCBCB:0.15:0.1,scale=220:-1[sub_clean]")
        filter_steps.append(f"{current_label}[sub_clean]overlay=x=W-w-100:y=100:enable='{enable_str}'[v_sub]")
        current_label = "[v_sub]"

    # 2. Mermaid (黑框防护)
    m_dir = PATHS["mermaid"]
    m_segs = render_plan.get("mermaid", {}).get("segments", [])
    if m_segs and os.path.exists(m_dir):
        webm_files = [os.path.join(m_dir, f) for f in os.listdir(m_dir) if f.endswith(".webm")]
        valid_webms = [f for f in webm_files if mf.check_webm_vp9(f)]
        if valid_webms:
            idx_m = get_index(); ffmpeg_inputs += ["-stream_loop", "-1", "-i", random.choice(valid_webms)]
            m_enable = "+".join([f"between(t,{s['start']},{s['end']})" for s in m_segs])
            filter_steps.append(f"[{idx_m}:v]colorkey=0x000000:0.1:0.1,scale=iw*{CFG['MERMAID_SCALE']}:-1[m_v]")
            filter_steps.append(f"{current_label}[m_v]overlay=x=120:y=H-h-120:enable='{m_enable}'[v_m]")
            current_label = "[v_m]"

    # 3. Captions
    for i, item in enumerate(render_plan.get("captions", [])):
        if item['start'] > video_limit_seconds: break
        draw_call = (f"drawtext=text='{item['text']}':fontfile='C\\:/Windows/Fonts/{item['font']}':"
                     f"fontsize={item['size']}:fontcolor={item['color']}@0.8:x=(w-text_w)/2:y=h*{item['y']}:"
                     f"enable='between(t,{item['start']},{item['end']})'")
        next_v_label = f"[v_txt{i}]"; filter_steps.append(f"{current_label}{draw_call}{next_v_label}"); current_label = next_v_label

    final_cmd = ["ffmpeg", "-y", "-hwaccel", "cuda", *ffmpeg_inputs, "-filter_complex", ";".join(filter_steps), "-map", current_label, "-map", "1:a:0", "-c:v", "h264_nvenc", "-b:v", "55M", "-shortest", PATHS["output"]]
    return mf.run_ffmpeg_task(final_cmd, "Final Fusion Master")

def main():
    """! @brief 生产流水线调度核心。全量找回 Step 打印。 """
    print(f"🚀 Mermaid Engine V{DATA['PROJ_VERSION']} - [Stability Orchestration]")
    
    # [Step 1] 资产筛选
    selected_assets_list = mf.select_video_assets(CFG)
    if not selected_assets_list:
        sys.exit(1)
    
    # [Step 1.5] 状态审计
    motion_results = mf.perform_incremental_motion_analysis(selected_assets_list, PATHS["motion_cache"])
    
    # [Step 2] 审计调度
    valid_std_pool = mf.standardize_video_batch(motion_results, PATHS, CFG)

    final_concat_list = []
    current_acc_duration = 0
    target_sec = CFG["TARGET_DURATION"]
    
    print(f"🧪 [Step 2.5] 随机补齐时长 (目标: {target_sec}s)...")
    intro_candidates = [p for p in valid_std_pool if "intro" in os.path.basename(p).lower()]
    body_pool = [p for p in valid_std_pool if "intro" not in os.path.basename(p).lower()]
    
    if intro_candidates:
        intro_file = intro_candidates[0]
        final_concat_list.append(intro_file)
        current_acc_duration += mf.get_video_duration(intro_file)
    
    while current_acc_duration < target_sec:
        pick = random.choice(body_pool if body_pool else valid_std_pool)
        dur = mf.get_video_duration(pick)
        if dur > 0:
            final_concat_list.append(pick)
            current_acc_duration += dur
            
    if len(final_concat_list) > 1 and intro_candidates:
        body_part = final_concat_list[1:]
        random.shuffle(body_part)
        final_concat_list = [final_concat_list[0]] + body_part
    else:
        random.shuffle(final_concat_list)

    # [Step 3] 物理拼接
    print("🔥 [Step 3] 执行物理拼接(Concat)...")
    if not mf.build_concat_file(final_concat_list, PATHS["concat_list"]):
        sys.exit(1)
    mf.run_ffmpeg_task(["ffmpeg", "-y", "-hwaccel", "cuda", "-f", "concat", "-safe", "0", "-fflags", "+genpts", "-i", PATHS["concat_list"], "-c", "copy", PATHS["temp_video"]], "Concat")
    
    # [Step 4] 音频 Mastering
    phys_dur_val = mf.get_video_duration(PATHS["temp_video"])
    mf.finalize_audio_mastering(PATHS, phys_dur_val, CFG)

    # [Step 5] 计划构建
    final_plan_obj = mf.build_overlay_plan(phys_dur_val, fetch_safe_captions(), STYLES)
    with open(PATHS["overlay_json"], "w", encoding="utf-8") as f_p: json.dump(final_plan_obj, f_p, indent=2)

    # [Step 6] 融合交付
    if render_final_fusion(final_plan_obj, phys_dur_val):
        print(f"✨ 交付成功: {PATHS['output']}")

if __name__ == "__main__":
    main()