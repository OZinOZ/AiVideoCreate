"""
长篇故事剧本自动化处理流 (智能游标切片 + 上下文隔离版)
利用游标机制（目标1000字，弹性前瞻100字寻找段落结尾）进行动态切分。
利用前情提要隔离区，每次提取上一段末尾 250 字作为参考，但不混入缩写任务中。
代码严格遵循 pylint 规范，具备全链路日志记录。
"""

import os
import re
import requests

# ==========================================
# 1. 配置部分 (Configuration)
# ==========================================
LOCAL_LLM_URL = "http://localhost:1234/v1/chat/completions"
LOCAL_MODEL_ID = "gemma-4-e4b-it"

INPUT_FILE = "pearl.txt"
OUTPUT_FILE = "pearl_summary_clean.txt"

# 切片与缩写核心参数
CHUNK_TARGET_LENGTH = 1000  # 目标切片字数，降低模型认知压力
MAX_LOOKAHEAD = 100         # 遇到截断时，最多向后寻找多少字来找段落结尾
OVERLAP_LENGTH = 250        # 取上一段结尾多少字作为“前情提要”
SUMMARY_TARGET_LENGTH = 300 # 每 1000 字原文，期望缩写出的字数 (比例约 5:1)

# ==========================================
# 2. 底层逻辑函数 (Functions)
# ==========================================

def read_source_file(file_path: str) -> str:
    """读取本地源文件"""
    print(f"[步骤] 尝试读取源文件: {file_path}")
    if not os.path.exists(file_path):
        print(f"[错误] 源文件不存在: {file_path}")
        return ""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"[成功] 源文件读取完毕，共 {len(content)} 字符")
        return content
    except Exception as e:
        print(f"[错误] 读取文件异常: {str(e)}")
        return ""

def call_local_gemma(prompt: str, max_tokens: int = 4096, temperature: float = 0.2) -> str:
    """通用调用本地 Gemma 模型接口 (低温度以保证缩写准确性)"""
    print("[底层] 发起本地 Gemma API 请求...")
    payload = {
        "model": LOCAL_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    try:
        response = requests.post(LOCAL_LLM_URL, json=payload, timeout=600)
        if response.status_code == 200:
            result = response.json().get('choices', [])[0].get('message', {}).get('content', '')
            print(f"[成功] 本地 Gemma 响应接收完成，返回 {len(result)} 字符")
            return result
        print(f"[错误] 本地 API 返回异常状态码: {response.status_code}")
        print(f"[详情] 错误响应: {response.text}")
        return ""
    except Exception as e:
        print(f"[错误] 本地请求发生异常: {str(e)}")
        return ""

def extract_global_background(full_text: str) -> str:
    """从全文中提取极简背景，作为后续分块缩写的上下文罗盘"""
    print(f"[步骤] 开始提取全局背景 (全文 {len(full_text)} 字符)...")
    prompt = (
        "请阅读以下原文，提取出故事的全局背景和核心人物关系。\n"
        "要求：只需输出约 300 字的客观陈述，禁止任何格式排版和多余废话。\n\n"
        "原文如下：\n"
        f"{full_text}"
    )
    result = call_local_gemma(prompt, max_tokens=1024, temperature=0.1)
    if not result:
        print("[错误] 全局背景提取失败")
    else:
        print("[成功] 全局背景提取完毕")
    return result

def split_text_with_cursor(text: str) -> list:
    """
    智能游标切片：以 CHUNK_TARGET_LENGTH 为基准，向后寻找换行符或句号，
    最多找 MAX_LOOKAHEAD 字。若找不到则硬切。
    """
    print(f"[步骤] 正在执行游标切片 (基准: {CHUNK_TARGET_LENGTH}字, 弹性前瞻: {MAX_LOOKAHEAD}字)...")
    if not text:
        print("[错误] 待切分文本为空")
        return []

    chunks = []
    cursor = 0
    total_len = len(text)

    while cursor < total_len:
        base_end = cursor + CHUNK_TARGET_LENGTH

        if base_end >= total_len:
            chunks.append(text[cursor:].strip())
            break

        lookahead_window = text[base_end : base_end + MAX_LOOKAHEAD]
        
        # 优先找段落结尾 (\n)
        newline_pos = lookahead_window.find('\n')
        
        if newline_pos != -1:
            actual_end = base_end + newline_pos + 1
        else:
            # 退而求其次，找句号、感叹号等强标点，防止把半句话切断
            match = re.search(r'[。！？.!?]', lookahead_window)
            if match:
                actual_end = base_end + match.end()
            else:
                # 实在找不到，只能硬切
                actual_end = base_end

        chunk = text[cursor:actual_end].strip()
        if chunk:
            chunks.append(chunk)

        cursor = actual_end

    print(f"[成功] 游标切片完毕，原文本被拆分为 {len(chunks)} 个物理块。")
    return chunks

def summarize_single_chunk(shared_context: str, previous_overlap: str, chunk_text: str, index: int) -> str:
    """带隔离区的客观缩写任务"""
    print(f"[底层] 正在客观缩写第 {index} 个物理块 (原文长度: {len(chunk_text)})...")
    
    # 隔离区组装：只有非第一段才会有前情提要
    overlap_section = ""
    if previous_overlap:
        overlap_section = (
            "【前情提要（仅供衔接参考，绝对禁止将此部分内容写入缩写结果中！）】\n"
            f"{previous_overlap}\n\n"
        )

    prompt = (
        "【全局故事背景参考】\n"
        f"{shared_context}\n\n"
        f"{overlap_section}"
        "【当前缩写任务】\n"
        "请阅读底部的【待缩写原文】，进行【精炼式复述】，而不是概括。\n"
        "【严格纪律】\n"
        "1. 保留原文的叙事方式：用第三人称讲述，保留人物的原话（直接引语），不要转述成间接引语。\n"
        "2. 删除的内容仅限于：诗词赋、环境景物描写、重复的寒暄客套、说书人的插话（如‘话说’、‘且听下回分解’）。\n"
        "3. 必须保留的内容：所有对话（尽量用原话）、所有推动情节的动作、人物之间的关键互动。\n"
        "4. 禁止概括：不要说‘两人告别’，要说‘兴哥道：娘子保重。三巧儿含泪点头’。\n"
        "5. 绝对中立：不要加人物内心分析，不要加‘他心想’、‘她感到’这类描写。\n"
        "6. 绝不重复：根据【前情提要】顺着往下写，不要把前情提要里的事又写一遍。\n"
        f"7. 字数控制在 {SUMMARY_TARGET_LENGTH} 字左右。直接输出纯文本，禁止Markdown格式。\n\n"
        "【待缩写原文】\n"
        f"{chunk_text}"
    )
    
    result = call_local_gemma(prompt, max_tokens=1024, temperature=0.2)
    if not result:
        print(f"[错误] 第 {index} 个物理块缩写失败")
        return ""
    return result

def process_all_chunks(shared_context: str, chunks: list) -> str:
    """循环遍历，管理 Overlap 游标并发送请求"""
    print(f"[步骤] 开始遍历缩写所有 {len(chunks)} 个物理块...")
    full_summary = ""
    previous_overlap = ""
    
    if not chunks:
        print("[错误] 物理块列表为空，无法执行缩写")
        return ""

    for i, chunk_text in enumerate(chunks):
        print(f"  -> 进度：正在处理第 {i + 1}/{len(chunks)} 块...")
        
        chunk_result = summarize_single_chunk(shared_context, previous_overlap, chunk_text, i + 1)
        
        if chunk_result:
            full_summary += chunk_result + "\n\n"
            # 成功后，提取当前原文物理块的最后 250 字，作为下一次的 previous_overlap
            # 使用 Python 的切片功能，即使文本不足 250 字也不会越界报错
            previous_overlap = chunk_text[-OVERLAP_LENGTH:]  
        else:
            print(f"[警告] 第 {i + 1} 块返回为空，已跳过拼接。")
            # 如果失败了，重叠区保持不变，尽量让下一次循环不出错
            pass

    if not full_summary.strip():
        print("[错误] 所有物理块均缩写失败，最终文案为空")
        return ""
        
    print("[成功] 所有原文块缩写完毕并拼接完成")
    return full_summary

def save_result_to_file(content: str, file_path: str) -> bool:
    """将结果保存到本地"""
    print(f"[步骤] 准备将最终结果写入文件: {file_path}")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[成功] 文件写入完毕")
        return True
    except Exception as e:
        print(f"[错误] 写入文件异常: {str(e)}")
        return False

# ==========================================
# 3. 主函数 (Main)
# ==========================================

def main():
    """主控流程，仅负责调用底层逻辑"""
    print(">>> 启动长文处理流水线 (智能切片+上下文隔离版) <<<")

    source_text = read_source_file(INPUT_FILE)
    if not source_text:
        print(">>> 流程终止：未能获取源文本 <<<")
        return

    shared_context = extract_global_background(source_text)
    if not shared_context:
        print(">>> 流程终止：全局背景提取失败 <<<")
        return

    text_chunks = split_text_with_cursor(source_text)
    if not text_chunks:
        print(">>> 流程终止：文本切片失败 <<<")
        return

    final_clean_summary = process_all_chunks(shared_context, text_chunks)
    if not final_clean_summary:
        print(">>> 流程终止：物理块缩写全盘失败 <<<")
        return

    is_saved = save_result_to_file(final_clean_summary, OUTPUT_FILE)
    if is_saved:
        print(">>> 流水线执行成功，纯净版故事底稿已生成 <<<")
    else:
        print(">>> 流水线执行完毕，但保存文件时出现问题 <<<")

if __name__ == "__main__":
    main()