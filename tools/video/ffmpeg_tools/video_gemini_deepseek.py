import os
import time
import subprocess
import random
import re
from google import genai
from openai import OpenAI
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from concurrent.futures import ThreadPoolExecutor

# ================= 配置区 =================
ONLY_AUDIO = True 
TARGET_DIR = r"H:\OliverAI\油管小白挣钱教程大全\阿蔺Leo跨境油管视频实训营3.0"
MAX_WORKERS = 2  
MID_DIR_NAME = "中间分析结果"
RETRY_LIMIT = 3
PASS_SCORE = 85  # 现在的 85 分含金量极高，全是废话会直接得 0 分

api_keys = {
    "gemini": os.environ.get("GEMINI_API_KEY"),
    "siliconflow": os.environ.get("SILICONFLOW_API_KEY")
}

gemini_client = genai.Client(api_key=api_keys["gemini"])
client_ds = OpenAI(api_key=api_keys["siliconflow"], base_url="https://api.siliconflow.com/v1")
DS_MODEL = "deepseek-ai/DeepSeek-V3"
# ==========================================

def set_font(run, font_name='微软雅黑', size=None, bold=False):
    run.font.name = font_name
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:eastAsia'), font_name)
    rPr.append(rFonts)
    if size: run.font.size = Pt(size)
    if bold: run.font.bold = True

def add_table_of_contents(paragraph):
    run = paragraph.add_run()
    set_font(run)
    fldChar = OxmlElement('w:fldChar')
    fldChar.set(qn('w:fldCharType'), 'begin')
    run._r.append(fldChar)
    run = paragraph.add_run()
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
    run._r.append(instrText)
    run = paragraph.add_run()
    fldChar = OxmlElement('w:fldChar')
    fldChar.set(qn('w:fldCharType'), 'separate')
    run._r.append(fldChar)
    run = paragraph.add_run()
    run.text = "右键点击此处，选择“更新域”以生成目录"
    fldChar = OxmlElement('w:fldChar')
    fldChar.set(qn('w:fldCharType'), 'end')
    run._r.append(fldChar)

def ds_audit_logic(file_name, gemini_content):
    """补丁 2：零容忍审计员。只审来源结构，不审修辞。"""
    print(f"   [硬核审计] DeepSeek 正在剥离 [EXT] 废话: {file_name}")
    system_prompt = "你是零容忍审计员。你的任务是揪出所有不在视频里、靠AI脑补的常识内容。"
    user_prompt = f"""
    请对以下报告进行“来源结构审计”：
    
    【判定准则】：
    1. 统计报告中标注为 [SRC] (原内容)、[DERIVED] (推导)、[EXT] (外部常识) 的段落。
    2. 核心规则：
       - 若 [EXT] 内容（常识、公理、大纲）超过 3 处，或字数占比超过 10% -> 给 20 分。
       - 若存在未标注 [SRC/DERIVED/EXT] 的段落 -> 给 0 分。
       - 必须有至少 3 个具体的、带[分:秒]且描述了具体操作/参数的 [SRC] 标签 -> 给予 90 分以上。
    
    仅输出一个最终得分（0-100），不要任何废话：\n{gemini_content}
    """
    try:
        resp = client_ds.chat.completions.create(
            model=DS_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1
        )
        score_match = re.search(r'\d+', resp.choices[0].message.content)
        return int(score_match.group()) if score_match else 0
    except Exception as e:
        print(f"   [审计异常] {e}，默认拦截。")
        return 0

def fingerprint_challenge(file_obj, original_analysis):
    """补丁 3：指纹挑战。随机抽查模型没写过的细节。"""
    challenges = [
        "找一个你刚才分析中没用过的时间点，逐字抄写一句主讲人提到的具体原句（15字以上）",
        "列出视频中出现过但未被你刚才分析提到的一个具体工具名、网页链接或数值参数",
        "视频里主讲人在演示操作时，屏幕上出现的任何一个非通用的具体文本内容是什么？"
    ]
    task = random.choice(challenges)
    print(f"   [挑战环节] 随机抽查: {task}")
    challenge_prompt = f"""
    【指纹挑战 - 严禁作弊】
    基于刚才的视频内容，请回答：{task}
    要求：必须是原视频真实细节，且不能与你刚才生成的分析内容重复。
    """
    try:
        res = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=[file_obj, challenge_prompt])
        return f"\n【指纹挑战存证】：\n{res.text.strip()}"
    except: return "\n【指纹挑战存证】：挑战执行异常。"

def extract_audio_ffmpeg(video_path):
    audio_temp_dir = os.path.join(TARGET_DIR, "temp_audio_cache")
    if not os.path.exists(audio_temp_dir): os.makedirs(audio_temp_dir)
    safe_name = f"audio_{hash(os.path.basename(video_path))}.mp3"
    audio_path = os.path.join(audio_temp_dir, safe_name)
    if os.path.exists(audio_path): return audio_path
    command = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-y', audio_path]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return audio_path
    except: return None

def prepare_file(path):
    base_name = os.path.basename(path)
    mid_dir = os.path.join(TARGET_DIR, MID_DIR_NAME)
    if not os.path.exists(mid_dir): os.makedirs(mid_dir)
    target_path = path
    if ONLY_AUDIO and path.lower().endswith(('.mp4', '.mkv', '.mov', '.avi')):
        target_path = extract_audio_ffmpeg(path)
        if not target_path: return None
    print(f"-> [上传中] {base_name}")
    uploaded_file = gemini_client.files.upload(file=target_path)
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(2)
        uploaded_file = gemini_client.files.get(name=uploaded_file.name)
    return {"original_name": base_name, "file_obj": uploaded_file, "mid_dir": mid_dir}

def generate_final_report(all_summaries_data):
    # 汇总逻辑增加了对标签的过滤，确保最终报告只保留干货
    print("\n[阶段 1] 正在识别教程领域...")
    sample_context = "\n\n".join([f"档案:{item['original_name']}\n{item['content']}" for item in all_summaries_data[:5]])
    id_res = gemini_client.models.generate_content(
        model="gemini-2.0-flash", 
        contents=[f"识别细分行业及3个风控规则，仅输出结论：\n{sample_context}"]
    )
    sector_info = id_res.text.strip()

    print("\n[阶段 2] 分层深度审计汇总（每10个一组）...")
    chunk_reports = []
    for i in range(0, len(all_summaries_data), 10):
        chunk = all_summaries_data[i:i+10]
        chunk_context = "\n\n".join([f"档案:{item['original_name']}\n{item['content']}" for item in chunk])
        res = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[f"你是审计官。从以下带标签的卷宗中，提取所有 [SRC] 和 [DERIVED] 的硬核细节，丢弃所有 [EXT] 内容：\n{chunk_context}"]
        )
        chunk_reports.append(res.text)

    print("\n[阶段 3] 合成 4000 字决策报告...")
    all_chunks_context = "\n\n".join(chunk_reports)
    final_prompt = f"""你现在是【{sector_info}】顶级总监。基于以上纯干货细节，输出决策报告。
    要求：PART 1 必须极其详尽。每一条结论必须关联具体的视频细节。
    一、 核心商业逻辑建模
    二、 必死点：2026 技术对垒（禁止出现AI泛滥等废话，要写具体的实操陷阱）
    三、 黄金动作：10 个高门槛实操点 (带参数/SOP)
    四、 ROI 残酷预测
    五、 审计终论
    素材来源：\n{all_chunks_context}"""
    
    response = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=[final_prompt])

    doc = Document()
    p = doc.add_heading('', 0); run = p.add_run('深度审计与实战决策手册'); set_font(run, size=24, bold=True)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()
    doc.add_heading('目录 (手动更新)', level=1)
    add_table_of_contents(doc.add_paragraph()); doc.add_page_break()

    doc.add_heading('PART 1：专家决策指南', level=1)
    for line in response.text.split('\n'):
        p = doc.add_paragraph()
        if line.startswith('## '):
            run = p.add_run(line.replace('## ', '')); set_font(run, size=16, bold=True)
        elif line.startswith('### '):
            run = p.add_run(line.replace('### ', '')); set_font(run, size=14, bold=True)
        else:
            run = p.add_run(line); set_font(run, size=10.5)

    doc.add_page_break()
    doc.add_heading('PART 2：详细存证档案', level=1)
    for item in all_summaries_data:
        p = doc.add_heading('', level=2); run = p.add_run(f"档案编号: {item['original_name']}"); set_font(run, size=12, bold=True)
        p = doc.add_paragraph(); run = p.add_run(item['content']); set_font(run, size=9)
        doc.add_paragraph("-" * 15)

    save_path = os.path.join(TARGET_DIR, "最终全量审计报告_防摸鱼增强版.docx")
    doc.save(save_path)
    print(f"\n[任务大成功] 报告已生成: {save_path}")

def process_pipeline():
    mid_dir = os.path.join(TARGET_DIR, MID_DIR_NAME)
    if os.path.exists(mid_dir) and any(f.endswith('.txt') for f in os.listdir(mid_dir)):
        print("检测到旧 TXT，正在执行汇总...")
        all_data = []
        txt_files = sorted([f for f in os.listdir(mid_dir) if f.endswith('.txt')])
        for tf in txt_files:
            with open(os.path.join(mid_dir, tf), 'r', encoding='utf-8') as f:
                all_data.append({"original_name": tf, "content": f.read()})
        generate_final_report(all_data)
        return

    files = sorted([os.path.join(root, f) for root, _, fs in os.walk(TARGET_DIR) 
             for f in fs if f.lower().endswith(('.mp4', '.mkv', '.mov', '.avi'))
             and "temp_audio_cache" not in root and MID_DIR_NAME not in root])

    all_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(prepare_file, f): f for f in files}
        for index, future in enumerate(future_to_file):
            try:
                data = future.result(); file_name = data["original_name"]
                
                # 补丁 1：内容来源标注协议
                prompt = f"""你现在是【存证型分析器】。
                【铁律】：你输出的每一句话必须标注来源：
                - [SRC][分:秒]：直接来自视频内容。
                - [DERIVED]：基于 [SRC] 的直接推导。
                - [EXT]：行业常识（若超过 10% 则分析失败）。
                
                请挖掘 '{file_name}'。给出具体的点击路径、硬核参数和 3 个原句指纹。"""
                
                res = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=[data['file_obj'], prompt])
                content = res.text.strip()

                # DeepSeek 来源占比审计
                score = ds_audit_logic(file_name, content)
                if score < PASS_SCORE:
                    print(f"   ❌ 质量不佳或[EXT]常识过多 ({score}分)，正在重做...")
                    retry_prompt = "刚才的分析全是AI常识废话。现在要求你必须标注 [SRC]，且字数必须占 90% 以上。重新分析！"
                    res = gemini_client.models.generate_content(model="gemini-2.0-flash", contents=[data['file_obj'], retry_prompt])
                    content = res.text.strip()

                # 增加随机挑战，防止模型在 [SRC] 标签里造假
                challenge_res = fingerprint_challenge(data['file_obj'], content)
                content += challenge_res

                with open(os.path.join(data["mid_dir"], f"Result_{index+1:02d}.txt"), "w", encoding="utf-8") as f:
                    f.write(content)
                all_data.append({"original_name": file_name, "content": content})
                gemini_client.files.delete(name=data["file_obj"].name)
                print(f"[存证成功] {file_name}")
            except Exception as e: print(f"分析失败: {e}")

    if all_data:
        generate_final_report(all_data)
    else:
        print("未发现有效视频文件。")

if __name__ == "__main__":
    try:
        process_pipeline()
    except KeyboardInterrupt:
        print("\n[用户中断] 任务已停止。")
    except Exception as e:
        print(f"\n[崩溃日志]: {e}")