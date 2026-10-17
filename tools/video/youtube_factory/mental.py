"""
VET Assessment & Activity Automation Pipeline.
包含预检拦截机制，避免重复上传和无效 API 调用。
严格遵循 pylint 规范，具备高度模块化和详尽的执行日志。
"""

import os
import json
import time
import re
import traceback
import zipfile
from pathlib import Path

import docx
import comtypes.client
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ==========================================
# 1. 核心配置区 (Configuration)
# ==========================================
CONFIG = {
    "ROOT_DIR": Path(r"E:\Ivy"),
    "MODEL_ID": "gemini-2.0-flash",
    "RATE_LIMIT_DELAY": 1.5,
    "API_UPLOAD_TIMEOUT": 60,
    "KEYWORDS": {
        "ASSESSMENT": ["assessment", "quiz"],
        "ACTIVITY": ["activity"],
        "IGNORE": ["answer", "result", "completed", "done", "report"]
    },
    "SYSTEM_INSTRUCTION": (
        "You are a professional VET student. Answer assessment and activity tasks directly.\n"
        "STRICT PROTOCOLS:\n"
        "1. NO INTRODUCTIONS: Start directly with the task/question. No conversational filler.\n"
        "2. FORMAT: Include the original question followed by your answer. Use **Bold** for questions.\n"
        "3. STYLE: Use plain lists or bulleted lines instead of '*' formatting.\n"
        "4. CONCISENESS: Case studies and summaries must be specific and strictly follow word counts."
    )
}

# ==========================================
# 2. 物理文件与环境处理层 (File System Utilities)
# ==========================================

def extract_zip_archives(folder: Path) -> bool:
    """提取目录下所有的 ZIP 压缩包。"""
    print(f"[*] 开始执行函数: 扫描并解压 ZIP 文件 ({folder.name})")
    zip_files = list(folder.glob("*.zip"))
    if not zip_files:
        print("[+] 判断结果: 未发现 ZIP 文件，跳过解压。")
        return True

    success = True
    for zip_file in zip_files:
        print(f"[*] 正在解压: {zip_file.name}")
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(folder)
            print(f"[+] 解压成功: {zip_file.name}")
        except (zipfile.BadZipFile, OSError) as err:
            print(f"[-] 函数失败: 解压文件 {zip_file.name} 时发生错误: {err}")
            success = False
    return success

def convert_office_to_pdf(folder: Path) -> bool:
    """将目录下的 Word 和 PPT 文件转换为 PDF。"""
    print(f"[*] 开始执行函数: Office 转 PDF ({folder.name})")
    doc_files = list(folder.glob("*.doc*"))
    ppt_files = list(folder.glob("*.ppt*"))
    
    if not doc_files and not ppt_files:
        print("[+] 判断结果: 未发现 Office 文件，跳过转换。")
        return True

    try:
        word_app = comtypes.client.CreateObject("Word.Application")
        word_app.Visible = False
        ppt_app = comtypes.client.CreateObject("PowerPoint.Application")
    except OSError as err:
        print(f"[-] 函数失败: 无法启动 Office COM 组件: {err}")
        return False

    try:
        for doc_file in doc_files:
            fname_low = doc_file.name.lower()
            if fname_low.startswith("~$") or any(k in fname_low for k in CONFIG["KEYWORDS"]["IGNORE"]):
                print(f"[-] 判断失败: 文件 {doc_file.name} 属于忽略列表，跳过。")
                continue
                
            pdf_path = doc_file.with_suffix(".pdf")
            if pdf_path.exists():
                print(f"[-] 判断失败: PDF已存在，跳过 Word 转换 ({doc_file.name})")
                continue
                
            print(f"[*] 转换 Word -> PDF: {doc_file.name}")
            try:
                doc = word_app.Documents.Open(str(doc_file))
                doc.SaveAs(str(pdf_path), FileFormat=17)
                doc.Close()
                print(f"[+] 转换成功: {pdf_path.name}")
            except Exception as err:
                print(f"[-] 函数失败: Word 转换报错: {err}")

        for ppt_file in ppt_files:
            fname_low = ppt_file.name.lower()
            if fname_low.startswith("~$") or any(k in fname_low for k in CONFIG["KEYWORDS"]["IGNORE"]):
                print(f"[-] 判断失败: 文件 {ppt_file.name} 属于忽略列表，跳过。")
                continue
                
            pdf_path = ppt_file.with_suffix(".pdf")
            if pdf_path.exists():
                print(f"[-] 判断失败: PDF已存在，跳过 PPT 转换 ({ppt_file.name})")
                continue
                
            print(f"[*] 转换 PPT -> PDF: {ppt_file.name}")
            try:
                presentation = ppt_app.Presentations.Open(str(ppt_file), WithWindow=False)
                presentation.SaveAs(str(pdf_path), 32)
                presentation.Close()
                print(f"[+] 转换成功: {pdf_path.name}")
            except Exception as err:
                print(f"[-] 函数失败: PPT 转换报错: {err}")
    finally:
        try:
            word_app.Quit()
            ppt_app.Quit()
        except Exception as err:
            print(f"[-] 警告: 退出 Office 组件时发生异常: {err}")

    return True

def format_markdown_to_word(doc: docx.Document, text_line: str) -> bool:
    """将单行 Markdown 文本解析并写入 Word 文档对象中。"""
    line = text_line.strip()
    if not line:
        return False
        
    is_bullet = False
    if line.startswith('*') and not line.startswith('**'):
        is_bullet = True
        line = re.sub(r'^\*\s*', '', line)
        
    paragraph = doc.add_paragraph()
    if is_bullet:
        paragraph.style = 'List Bullet'
        
    parts = re.split(r'(\*\*.*?\*\*|\*.*?\*)', line)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run = paragraph.add_run(part.replace('**', ''))
            run.bold = True
        elif part.startswith('*') and part.endswith('*'):
            run = paragraph.add_run(part.replace('*', ''))
            run.italic = True
        else:
            paragraph.add_run(part)
    return True

# ==========================================
# 3. 核心业务辅助层 (Task Utilities)
# ==========================================

def get_assessment_output_path(folder: Path, pdf_path: Path) -> Path:
    """计算 Assessment 任务预期输出的文件路径。"""
    out_name = pdf_path.name.lower().replace("assessment", "answer").replace("quiz", "result").replace(".pdf", ".docx")
    return folder / out_name

def get_activity_output_path(folder: Path, pdf_path: Path) -> Path:
    """计算 Activity 任务预期输出的文件路径。"""
    out_name = pdf_path.stem + "_report.docx"
    return folder / out_name

def filter_valid_pdfs(folder: Path) -> list:
    """获取目录下所有的 PDF，并严格过滤掉属于 IGNORE 列表的历史生成文件。"""
    print(f"[*] 开始执行函数: 过滤有效 PDF 文件 ({folder.name})")
    all_pdfs = list(folder.glob("*.pdf"))
    valid_pdfs = []
    
    for pdf in all_pdfs:
        fname_low = pdf.name.lower()
        if any(k in fname_low for k in CONFIG["KEYWORDS"]["IGNORE"]):
            print(f"[-] 判断失败: PDF 属于忽略列表 ({pdf.name})，已剔除。")
            continue
        valid_pdfs.append(pdf)
        
    return valid_pdfs

def check_pending_tasks(folder: Path, tasks: list, task_type: str) -> list:
    """检查任务列表，返回尚未生成输出文件的待处理任务。"""
    pending = []
    for task in tasks:
        if task_type == "ASSESSMENT":
            out_path = get_assessment_output_path(folder, task)
        else:
            out_path = get_activity_output_path(folder, task)
            
        if not out_path.exists():
            pending.append(task)
        else:
            print(f"[-] 判断失败: {task_type} 输出文件已存在，跳过该任务 ({out_path.name})")
            
    return pending

# ==========================================
# 4. Gemini API 交互层 (API Handlers)
# ==========================================

def upload_file_to_gemini(client: genai.Client, file_path: Path):
    """上传文件至 Gemini 并等待处理完成。"""
    print(f"[*] 开始执行函数: 上传文件至 Gemini ({file_path.name})")
    try:
        gemini_file = client.files.upload(file=file_path)
        start_time = time.time()
        
        while gemini_file.state == "PROCESSING":
            if time.time() - start_time > CONFIG["API_UPLOAD_TIMEOUT"]:
                print(f"[-] 函数失败: 文件上传处理超时 ({file_path.name})")
                return None
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)
            
        if gemini_file.state == "FAILED":
            print(f"[-] 判断失败: API 返回文件处理失败状态 ({file_path.name})")
            return None
            
        print(f"[+] 函数成功: 文件上传并就绪 ({file_path.name})")
        return gemini_file
    except Exception as err:
        print(f"[-] 函数失败: Gemini API 上传异常: {err}")
        return None

def extract_json_safely(text: str) -> list:
    """从文本中安全地提取 JSON 数据。"""
    try:
        return json.loads(text).get('tasks', [])
    except json.JSONDecodeError:
        print("[-] 判断失败: 直接解析 JSON 失败，尝试正则清洗。")
        
    cleaned_text = re.sub(r"```(json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r"```\s*$", "", cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'\\(?![/u"\\bfnrt])', r'\\\\', cleaned_text)
    
    try:
        data = json.loads(cleaned_text)
        return data.get('tasks', []) if isinstance(data, dict) else data
    except json.JSONDecodeError:
        print("[-] 判断失败: 正则清洗后依然无法解析 JSON。")
        match = re.search(r'(\{.*\}|\[.*\])', cleaned_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get('tasks', []) if isinstance(data, dict) else data
            except Exception as err:
                print(f"[-] 函数失败: 最终结构化提取彻底失败: {err}")
    return []

def analyze_assessment_structure(client: genai.Client, main_pdf_asset) -> list:
    """利用大模型扫描 Assessment 文档结构并提取题目 JSON。"""
    print(f"[*] 开始执行函数: 解析文档试题结构")
    prompt = (
        "Analyze this assessment PDF. Identify all Task sections.\n"
        "Return ONLY JSON: {\"tasks\": [{\"engine\": \"QUIZ_ENGINE/CASE_ENGINE/PROJECT_ENGINE\", "
        "\"header\": \"...\", \"questions\": [\"...\"], \"context\": \"...\"}]}"
    )
    try:
        response = client.models.generate_content(
            model=CONFIG["MODEL_ID"],
            contents=[prompt, main_pdf_asset],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        tasks = extract_json_safely(response.text)
        print(f"[+] 函数成功: 共解析出 {len(tasks)} 个任务块。")
        return tasks
    except Exception as err:
        print(f"[-] 函数失败: 解析试题结构时发生网络或 API 错误: {err}")
        return []

def generate_assessment_answers(client: genai.Client, task: dict, assets: list) -> str:
    """针对单一 Assessment 任务引擎生成答案。"""
    engine = task.get('engine', 'QUIZ_ENGINE')
    header = task.get('header', 'Unknown Task')
    context = task.get('context', '')
    questions = task.get('questions', [])
    
    q_block = "\n".join([f"Q{i+1}: {q}" for i, q in enumerate(questions)])
    print(f"[*] 开始执行函数: 引擎执行 [{header}] -> {engine}")
    
    if engine == "PROJECT_ENGINE":
        inst = f"Context: {context}. Action: Create 3 distinct scenarios. Use 2-3 bullet points. Concise."
        tokens, temp = 3000, 0.4
    elif engine == "CASE_ENGINE":
        inst = f"Context: {context}. Action: Answer based on scenario. Use 3-4 bullet points."
        tokens, temp = 1500, 0.2
    else:
        inst = "Action: Direct answers. Max 1 sentence. Use *True* or *False*."
        tokens, temp = 800, 0.0
        
    prompt = f"TASK: {header}\n{inst}\n\nQUESTIONS:\n{q_block}"
    
    try:
        res = client.models.generate_content(
            model=CONFIG["MODEL_ID"],
            contents=[prompt] + assets,
            config=types.GenerateContentConfig(
                system_instruction=CONFIG["SYSTEM_INSTRUCTION"],
                temperature=temp,
                max_output_tokens=tokens
            )
        )
        print(f"[+] 函数成功: [{header}] 答案生成完毕。")
        return res.text
    except Exception as err:
        print(f"[-] 函数失败: 答案生成发生错误: {err}")
        return "Error generating response."

def generate_activity_content(client: genai.Client, activity_asset, material_assets: list) -> str:
    """针对 Activity 活动文件生成指定的反思或报告。"""
    print(f"[*] 开始执行函数: 分析并执行 Activity 任务")
    prompt = (
        "TASK: Read the attached Classroom Activity document.\n"
        "ACTION: Identify the specific task requested (e.g., writing a 250-word Reflective Summary) "
        "and complete it.\n"
        "CONTEXT: Use the other attached reference materials to gather theoretical knowledge and connections.\n"
        "OUTPUT: Provide ONLY the final written response. Do not include conversational filler or repeat instructions."
    )
    
    try:
        res = client.models.generate_content(
            model=CONFIG["MODEL_ID"],
            contents=[prompt, activity_asset] + material_assets,
            config=types.GenerateContentConfig(
                system_instruction=CONFIG["SYSTEM_INSTRUCTION"],
                temperature=0.4,
                max_output_tokens=2500
            )
        )
        print(f"[+] 函数成功: Activity 报告内容生成完毕。")
        return res.text
    except Exception as err:
        print(f"[-] 函数失败: Activity 生成发生错误: {err}")
        return "Error generating activity report."

# ==========================================
# 5. 业务逻辑编排层 (Pipelines)
# ==========================================

def process_assessment_task(client: genai.Client, folder: Path, main_pdf: Path, material_assets: list) -> bool:
    """编排处理单一 Assessment 任务。"""
    print(f"====== 开始执行 API 处理: Assessment ({main_pdf.name}) ======")
    out_path = get_assessment_output_path(folder, main_pdf)

    main_asset = upload_file_to_gemini(client, main_pdf)
    if not main_asset:
        return False

    tasks = analyze_assessment_structure(client, main_asset)
    results = []
    
    for task in tasks:
        ans = generate_assessment_answers(client, task, material_assets + [main_asset])
        results.append((task.get('header', 'Task'), ans))
        time.sleep(CONFIG["RATE_LIMIT_DELAY"])

    doc = docx.Document()
    doc.add_heading(f"Assessment Report: {main_pdf.stem}", 0)
    for header, content in results:
        doc.add_heading(header, level=1)
        content_cleaned = re.sub(r"^(Okay|Sure|Here|As a student|Answer).*?\n", "", content, flags=re.IGNORECASE | re.MULTILINE)
        for line in content_cleaned.split('\n'):
            format_markdown_to_word(doc, line)
        doc.add_page_break()
        
    doc.save(out_path)
    print(f"✅ Assessment 报告已生成: {out_path.name}")
    
    try:
        client.files.delete(name=main_asset.name)
    except Exception as err:
        print(f"[-] 警告: 删除临时资产失败 ({main_asset.name}): {err}")
        
    return True

def process_activity_task(client: genai.Client, folder: Path, activity_pdf: Path, material_assets: list) -> bool:
    """编排处理单一 Classroom Activity 任务。"""
    print(f"====== 开始执行 API 处理: Activity ({activity_pdf.name}) ======")
    out_path = get_activity_output_path(folder, activity_pdf)

    activity_asset = upload_file_to_gemini(client, activity_pdf)
    if not activity_asset:
        return False

    content = generate_activity_content(client, activity_asset, material_assets)
    
    doc = docx.Document()
    doc.add_heading(f"Activity Report: {activity_pdf.stem}", 0)
    content_cleaned = re.sub(r"^(Okay|Sure|Here|As a student|Answer).*?\n", "", content, flags=re.IGNORECASE | re.MULTILINE)
    for line in content_cleaned.split('\n'):
        format_markdown_to_word(doc, line)
        
    doc.save(out_path)
    print(f"✅ Activity 报告已生成: {out_path.name}")
    
    try:
        client.files.delete(name=activity_asset.name)
    except Exception as err:
        print(f"[-] 警告: 删除临时资产失败 ({activity_asset.name}): {err}")
        
    return True

def process_single_directory(client: genai.Client, folder: Path) -> bool:
    """处理单个目标文件夹的完整流水线。"""
    print(f"\n📂 正在进入目录: {folder.name}")
    extract_zip_archives(folder)
    convert_office_to_pdf(folder)

    # 第一步：获取安全的、纯净的 PDF 列表（剔除包含 ignore 关键字的文件）
    valid_pdfs = filter_valid_pdfs(folder)
    if not valid_pdfs:
        print("[-] 判断失败: 目录下没有需要处理的有效 PDF 文件，跳过后续操作。")
        return False

    # 第二步：任务分类
    raw_assessments = [f for f in valid_pdfs if any(x in f.name.lower() for x in CONFIG["KEYWORDS"]["ASSESSMENT"])]
    raw_activities = [f for f in valid_pdfs if any(x in f.name.lower() for x in CONFIG["KEYWORDS"]["ACTIVITY"])]
    materials = [f for f in valid_pdfs if f not in raw_assessments and f not in raw_activities]

    # 第三步：预检拦截 (盘点真正需要运行 API 的任务)
    print("[*] 开始执行预检：核对输出文件状态...")
    pending_assessments = check_pending_tasks(folder, raw_assessments, "ASSESSMENT")
    pending_activities = check_pending_tasks(folder, raw_activities, "ACTIVITY")

    if not pending_assessments and not pending_activities:
        print("✅ 判断结果: 所有任务均已生成结果文件，成功实施阻断拦截，未进行任何 API 上传。")
        return True

    print(f"[*] 分析结果: 拦截释放，准备处理 {len(pending_assessments)} 个 Assessment, {len(pending_activities)} 个 Activity, 挂载 {len(materials)} 个物料。")

    # 第四步：全局物料上传（仅在有真实任务时执行）
    uploaded_materials = []
    for mat_pdf in materials:
        asset = upload_file_to_gemini(client, mat_pdf)
        if asset:
            uploaded_materials.append(asset)

    # 第五步：执行管道
    for assess_pdf in pending_assessments:
        process_assessment_task(client, folder, assess_pdf, uploaded_materials)

    for act_pdf in pending_activities:
        process_activity_task(client, folder, act_pdf, uploaded_materials)

    # 第六步：清理全局物料
    print("[*] 开始清理目录下的全局缓存物料...")
    for asset in uploaded_materials:
        try:
            client.files.delete(name=asset.name)
        except Exception as err:
            print(f"[-] 警告: 无法清理参考物料 ({asset.name}): {err}")
            
    print(f"🏁 目录处理完毕: {folder.name}")
    return True

def process_all_directories(client: genai.Client, root_dir: Path):
    """扫描根目录并分发任务。"""
    directories = [x for x in root_dir.iterdir() if x.is_dir()]
    if not directories:
        print(f"[-] 判断失败: 根目录 {root_dir} 下无子文件夹。")
        return
        
    for directory in directories:
        try:
            process_single_directory(client, directory)
        except Exception as err:
            print(f"[-] 顶级函数崩溃: 处理目录 {directory.name} 时发生致命错误: {err}")
            traceback.print_exc()

# ==========================================
# 6. 主控入口 (Main Application)
# ==========================================

def main():
    """主函数：仅负责初始化环境配置与分发顶层任务。"""
    print("🚀 启动自动化作业处理系统...")
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[-] 判断失败: 未在环境中找到 GEMINI_API_KEY。")
        return

    try:
        client = genai.Client(api_key=api_key)
        process_all_directories(client, CONFIG["ROOT_DIR"])
        print("🎉 全部任务批处理圆满结束！")
    except Exception as err:
        print(f"[-] 致命错误: 客户端初始化或执行彻底失败: {err}")
        traceback.print_exc()

if __name__ == "__main__":
    main()