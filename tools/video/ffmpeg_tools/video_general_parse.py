import os
import time
import subprocess
from google import genai
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
ONLY_AUDIO = True 
# 请确保此路径正确，脚本将在此目录下寻找视频和保存报告
TARGET_DIR = r"H:\OliverAI\油管小白挣钱教程大全\阿蔺Leo跨境油管视频实训营3.0"
MAX_WORKERS = 2  
MID_DIR_NAME = "中间分析结果"
# --- --- --- ---

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def set_font(run, font_name='微软雅黑', size=None, bold=False):
    """强制锁定中文字体，解决 Word 中西文字体渲染不统一的问题"""
    run.font.name = font_name
    # 关键步骤：必须显式设置东亚字体名称
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:eastAsia'), font_name)
    rPr.append(rFonts)
    
    if size:
        run.font.size = Pt(size)
    if bold:
        run.font.bold = True

def add_table_of_contents(paragraph):
    """在 Word 中插入目录域（需打开后右键点击更新）"""
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

def extract_audio_ffmpeg(video_path):
    """使用 ffmpeg 提取音频以减少上传体积并加速处理"""
    audio_temp_dir = os.path.join(TARGET_DIR, "temp_audio_cache")
    if not os.path.exists(audio_temp_dir):
        os.makedirs(audio_temp_dir)
    
    safe_name = f"audio_{hash(os.path.basename(video_path))}.mp3"
    audio_path = os.path.join(audio_temp_dir, safe_name)
    
    if os.path.exists(audio_path):
        return audio_path

    print(f"-> [转码中] {os.path.basename(video_path)}")
    command = [
        'ffmpeg', '-i', video_path,
        '-vn', '-acodec', 'libmp3lame', '-y',
        audio_path
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return audio_path
    except Exception as e:
        print(f"转码失败: {video_path}, 错误: {e}")
        return None

def prepare_file(path):
    """上传文件到 Gemini 服务器并等待处理完成"""
    base_name = os.path.basename(path)
    VIDEO_EXTS = ('.mp4', '.mkv', '.mov', '.avi', '.wmv')
    mid_results_dir = os.path.join(TARGET_DIR, MID_DIR_NAME)
    if not os.path.exists(mid_results_dir):
        os.makedirs(mid_results_dir)

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
    """分段审计核心逻辑：分而治之，杜绝 AI 偷懒"""
    print("\n[阶段 1] 正在识别教程所属领域及最新行业规则...")
    sample_context = "\n\n".join([f"档案:{item['original_name']}\n内容:{item['content']}" for item in all_summaries_data[:5]])
    id_prompt = f"请快速分析样本，给出该教程所属精准细分行业及2026年该行业最重要的3个风控/算法机制。严禁废话：\n{sample_context}"
    
    id_res = client.models.generate_content(model="gemini-2.0-flash", contents=[id_prompt])
    sector_info = id_res.text.strip()
    print(f"-> 识别结果: {sector_info}")

    print("\n[阶段 2] 正在分段审计 50 份卷宗以保留技术细节（每10个一组）...")
    chunk_reports = []
    chunk_size = 10
    for i in range(0, len(all_summaries_data), chunk_size):
        chunk = all_summaries_data[i:i + chunk_size]
        chunk_context = "\n\n".join([f"档案:{item['original_name']}\n内容:{item['content']}" for item in chunk])
        print(f"   -> 正在挖掘第 {i+1}-{i+len(chunk)} 讲的硬核参数...")
        sub_prompt = f"你现在是硬核审计员。请从以下卷宗中挖掘所有具体的【操作路径、数值参数、工具名称、反直觉细节】。严禁概括总结，只要干货：\n{chunk_context}"
        sub_res = client.models.generate_content(model="gemini-2.0-flash", contents=[sub_prompt])
        chunk_reports.append(sub_res.text)

    print("\n[阶段 3] 正在合成最终决策报告...")
    all_chunks_context = "\n\n".join(chunk_reports)
    final_expert_prompt = f"""
    你现在是【{sector_info}】领域的顶级总监。基于以下分段审计出来的硬核细节，输出最终报告。
    要求：PART 1 必须详尽，字数不少于 4000 字。严禁使用任何概括性虚词。

    ## 一、 核心商业逻辑建模
    ## 二、 必死点：2026 技术对垒审判 (引用具体编号，解释技术失效原因)，指出5个以上注定失败的陷阱
    ## 三、 黄金动作：10 个高门槛实操技术点 (必须包含具体参数/SOP/数值)
    ## 四、 ROI 真实预测 (亏损概率、回本周期、预期收益中位数)
    ## 五、 审计终论：含金量打分

    干货素材：
    {all_chunks_context}
    """
    response = client.models.generate_content(model="gemini-2.0-flash", contents=[final_expert_prompt])

    doc = Document()
    
    # 封面
    p = doc.add_heading('', 0)
    run = p.add_run('全领域视频课程深度审计与决策报告')
    set_font(run, size=24, bold=True)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_page_break()
    doc.add_heading('目录 (手动更新)', level=1)
    add_table_of_contents(doc.add_paragraph())
    doc.add_page_break()

    # PART 1
    doc.add_heading('PART 1：审计意见与实战决策', level=1)
    for line in response.text.split('\n'):
        p = doc.add_paragraph()
        if line.startswith('## '):
            run = p.add_run(line.replace('## ', ''))
            set_font(run, size=16, bold=True)
        elif line.startswith('### '):
            run = p.add_run(line.replace('### ', ''))
            set_font(run, size=14, bold=True)
        else:
            run = p.add_run(line)
            set_font(run, size=10.5)

    doc.add_page_break()
    doc.add_heading('PART 2：详细技术存证卷宗', level=1)
    for item in all_summaries_data:
        p = doc.add_heading('', level=2)
        run = p.add_run(f"档案编号: {item['original_name']}")
        set_font(run, size=12, bold=True)
        
        p = doc.add_paragraph()
        run = p.add_run(item['content'])
        set_font(run, size=9)
        doc.add_paragraph("-" * 15)

    save_path = os.path.join(TARGET_DIR, "最终全量审计报告_专业版.docx")
    doc.save(save_path)
    print(f"\n[任务大成功] 报告已生成: {save_path}")

def process_pipeline():
    VIDEO_EXTS = ('.mp4', '.mkv', '.mov', '.avi', '.wmv')
    DOC_EXTS = ('.pdf', '.docx', '.txt', '.pptx')
    mid_dir = os.path.join(TARGET_DIR, MID_DIR_NAME)
    
    # 检查是否已存在中间分析 TXT，支持增量生成
    if os.path.exists(mid_dir) and any(f.endswith('.txt') for f in os.listdir(mid_dir)):
        print(f"检测到已分析的存证 TXT，直接进入汇总审计模式...")
        all_data = []
        txt_files = sorted([f for f in os.listdir(mid_dir) if f.endswith('.txt')])
        for tf in txt_files:
            with open(os.path.join(mid_dir, tf), 'r', encoding='utf-8') as f:
                content = f.read()
                all_data.append({"original_name": tf, "content": content})
        generate_final_report(all_data)
        return

    files = sorted([os.path.join(root, f) for root, _, fs in os.walk(TARGET_DIR) 
             for f in fs if f.lower().endswith(VIDEO_EXTS + DOC_EXTS) 
             and "temp_audio_cache" not in root and MID_DIR_NAME not in root])

    if not files:
        print("未发现待处理文件。")
        return

    all_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(prepare_file, f): f for f in files}
        for index, future in enumerate(future_to_file):
            try:
                data = future.result()
                if not data: continue
                file_name = data["original_name"]
                
                # 锁死每个视频的挖掘颗粒度
                single_video_prompt = f"""
                你现在是首席技术存证员。请挖掘视频 '{file_name}'。
                【禁令】：严禁任何形式的客套话或概括语。
                必须按以下格式输出：
                1. 【具体实操路径】: (点击的菜单名、输入参数、具体的动作顺序)
                2. 【核心逻辑链】: (博主认为这件事为什么能成的底层推导)
                3. 【提到的具体数值/品牌】: (记录所有金额、百分比、工具名)
                4. 【实战细节摘要】: (至少150字描述本集最关键的操作技巧)
                """
                
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[data["file_obj"], single_video_prompt]
                )
                
                res_clean = response.text.strip()
                # 物理保存，防止中途退出
                with open(os.path.join(data["mid_dir"], f"Result_{index+1:02d}.txt"), "w", encoding="utf-8") as f:
                    f.write(res_clean)
                
                print(f"[存证成功] {file_name}")
                all_data.append({"original_name": file_name, "content": res_clean})
                # 清理临时上传文件
                client.files.delete(name=data["file_obj"].name)
            except Exception as e:
                print(f"分析失败 {file_name}: {e}")

    if all_data:
        generate_final_report(all_data)

if __name__ == "__main__":
    process_pipeline()