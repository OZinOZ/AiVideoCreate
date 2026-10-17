import os
import time
import subprocess
from google import genai
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from moviepy import VideoFileClip 
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
ONLY_AUDIO = True 
TARGET_DIR = r"H:\OliverAI\油管小白挣钱教程大全\阿蔺Leo跨境油管视频实训营3.0"
MAX_WORKERS = 2  
MID_DIR_NAME = "中间分析结果"
# --- --- --- ---

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def extract_audio_ffmpeg(video_path):
    audio_temp_dir = os.path.join(TARGET_DIR, "temp_audio_cache")
    if not os.path.exists(audio_temp_dir): os.makedirs(audio_temp_dir)
    safe_name = f"audio_{hash(os.path.basename(video_path))}.mp3"
    audio_path = os.path.join(audio_temp_dir, safe_name)
    if os.path.exists(audio_path): return audio_path
    print(f"-> [转码中] {os.path.basename(video_path)}")
    command = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-y', audio_path]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return audio_path
    except Exception as e:
        print(f"转码彻底失败: {video_path}, 错误: {e}")
        return None

def prepare_file(path):
    base_name = os.path.basename(path)
    VIDEO_EXTS = ('.mp4', '.mkv', '.mov', '.avi', '.wmv')
    mid_results_dir = os.path.join(TARGET_DIR, MID_DIR_NAME)
    if not os.path.exists(mid_results_dir): os.makedirs(mid_results_dir)
    target_path = path
    if ONLY_AUDIO and path.lower().endswith(VIDEO_EXTS):
        target_path = extract_audio_ffmpeg(path)
        if not target_path: return None
    print(f"-> [上传中] {base_name}")
    uploaded_file = client.files.upload(file=target_path)
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
    return {"original_name": base_name, "file_obj": uploaded_file, "mid_dir": mid_results_dir}

def generate_final_report(all_summaries_data):
    print("\n正在发动首席审计官模式，进行【硬核技术对垒】分析...")
    
    # 将 50 个 txt 的内容全部拼接，并带上明显的来源标记
    full_context_for_ai = ""
    for item in all_summaries_data:
        full_context_for_ai += f"--- START OF {item['original_name']} ---\n{item['content']}\n--- END ---\n\n"
    
    final_expert_prompt = f"""
    你现在是拥有 10 年实操经验的 YouTube 运营总监。你需要对以下 50 份技术存证进行【审计】。
    
    【强制要求】：
    1. 严禁使用任何概括性废话（如：质量参差不齐、内容为王）。
    2. 每一条结论必须关联具体的卷宗编号。例如：(参考 Result_14 的 YPP 逻辑)。
    3. 2026 实时验证：利用你知识库中 2026 年的最新规则（如：C2PA 协议、AI 内容标签强制要求、美区住宅 IP 检测机制），审判培训内容的真实性。

    ## 一、 逻辑“脱水”：揭发培训中的骗局与过时招式
    （请直接指出 10 个博主提到的、但在 2026 年属于“自杀行为”的操作。必须说清楚：博主是怎么教的？为什么现在这招必死？例如：Result_43 的暴力起号在 2026 年是如何被算法指纹秒杀的。）

    ## 二、 10 个“真金白银”的底层技术动作
    （从 50 个卷宗中通过横向对比，提炼出目前依然极度有效的 10 个细节点。
    格式：动作名称 + 卷宗索引 + 2026 避风控逻辑 + 详细操作指令。）

    ## 三、 工具链审计：哪些是智商税？哪些是护城河？
    （针对卷宗里反复出现的 Heygen, VidIQ, Artlist 等，结合 2026 年最新平替给出红黑榜。如果不买付费版能不能做？必须给结论。）

    ## 四、 3 个月 5 万元 投入产出比（ROI）残酷预测
    （假设按照这 50 个视频的操作，投入 5 万元购买设备和工具，3 个月内：
    1. 账号被封禁/限流的概率中位数（基于 2026 现状）。
    2. 真实回本周期预测（剔除博主夸大的成分）。）

    ## 五、 总结：这套培训的真实含金量
    （给出一个百分比，并说明剩下的百分比是什么。）

    原始存证卷宗：
    {full_context_for_ai}
    """
    
    response = client.models.generate_content(
        model="gemini-2.0-flash", # 使用 Flash 2.0 确保逻辑推理强度
        contents=[final_expert_prompt]
    )
    
    doc = Document()
    # 标题页
    title = doc.add_heading('YouTube 运营技术审计与实操决策手册', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"生成日期: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_page_break()

    # PART 1: 审计与决策
    doc.add_heading('PART 1：审计意见与实战决策', level=1)
    for line in response.text.split('\n'):
        if line.startswith('## '):
            doc.add_heading(line.replace('## ', ''), level=2)
        elif line.startswith('### '):
            doc.add_heading(line.replace('### ', ''), level=3)
        else:
            doc.add_paragraph(line)
    doc.add_page_break()

    # PART 2: 原始卷宗
    doc.add_heading('PART 2：分集干货存证原件', level=1)
    for item in all_summaries_data:
        doc.add_heading(f"档案编号: {item['original_name']}", level=2)
        doc.add_paragraph(item['content'])
        doc.add_paragraph("-" * 15)

    save_path = os.path.join(TARGET_DIR, "YouTube_全量审计报告_专业对垒版.docx")
    doc.save(save_path)
    print(f"\n[重磅完成] 拒绝偷懒的深度报告已生成: {save_path}")

def process_pipeline():
    VIDEO_EXTS = ('.mp4', '.mkv', '.mov', '.avi', '.wmv')
    DOC_EXTS = ('.pdf', '.docx', '.txt', '.pptx')
    mid_dir = os.path.join(TARGET_DIR, MID_DIR_NAME)
    
    if os.path.exists(mid_dir) and any(f.endswith('.txt') for f in os.listdir(mid_dir)):
        print(f"检测到存证 TXT，正在汇总生成...")
        all_data = []
        txt_files = sorted([f for f in os.listdir(mid_dir) if f.endswith('.txt')])
        for tf in txt_files:
            with open(os.path.join(mid_dir, tf), 'r', encoding='utf-8') as f:
                content = f.read()
                # 这里假设txt第一行是原始文件名，如果不是，则通过结果名对应
                all_data.append({"original_name": tf, "content": content})
        generate_final_report(all_data)
        return

    files = sorted([os.path.join(root, f) for root, _, fs in os.walk(TARGET_DIR) 
             for f in fs if f.lower().endswith(VIDEO_EXTS + DOC_EXTS) 
             and "temp_audio_cache" not in root and MID_DIR_NAME not in root])

    all_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(prepare_file, f): f for f in files}
        for index, future in enumerate(future_to_file):
            try:
                data = future.result()
                if not data: continue
                file_name = data["original_name"]
                
                # 强化版 Prompt：明确禁止废话开头结尾
                single_video_prompt = f"""
                你现在是硬核存证员。请挖掘视频 '{file_name}'。
                【禁令】：严禁任何形式的客套话（如“好的”、“没问题”、“希望有帮助”），严禁概括。
                直接按以下格式输出：

                1. 【具体实操路径】: (点击的菜单、输入参数等)
                2. 【博主的核心逻辑链】: (为什么能成的推导)
                3. 【提到的具体数值/品牌】: (CPM/RPM/工具名)
                4. 【实战细节摘要】: (至少150字的核心经验)
                """
                
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[data["file_obj"], single_video_prompt]
                )
                
                res_clean = response.text.strip()
                with open(os.path.join(data["mid_dir"], f"Result_{index+1:02d}.txt"), "w", encoding="utf-8") as f:
                    f.write(res_clean)
                
                print(f"[存证成功] {file_name}")
                all_data.append({"original_name": file_name, "content": res_clean})
                client.files.delete(name=data["file_obj"].name)
            except Exception as e:
                print(f"分析失败 {file_name}: {e}")

    if all_data:
        generate_final_report(all_data)

if __name__ == "__main__":
    process_pipeline()