"""
民间故事 Word 文档自动提取脚本。
功能：从复杂的 Word 文档中，根据特定规则（数字+标题开头，时间地点结尾）提取故事。
输出：每个故事生成独立的 txt 文件，并汇总所有故事信息生成 Excel 表格。
"""

import os
import re
import unicodedata
from typing import List, Dict, Optional
import docx
import pandas as pd

# ==========================================
# 1. 配置区域 (CONFIGURATION)
# ==========================================
# 输入与输出路径配置
INPUT_WORD_PATH = "E:/AiScripts/word_process/story-1.docx"  # 请替换为您的 Word 文档实际路径
OUTPUT_TXT_DIR = "E:/AiScripts/word_process/extracted_stories"    # 独立故事文本输出目录
OUTPUT_EXCEL_PATH = "E:/AiScripts/word_process/stories_summary.xlsx" # 汇总 Excel 输出路径

# 正则表达式匹配规则
# 匹配开头：如 "038. 蓑衣的由来"，兼容中文句号、顿号等
PATTERN_START = r"^\s*(\d{1,4})[\.．、\s]\s*(.+)$"
# 匹配结尾：如 "采录时间、地点：1986年5月于巴县丰威乡"
PATTERN_END = r"^\s*采录时间.*?地点[：:](.*)$"
# 分行的采录地点行，如 "采录地点*柳河县" "采录地点：某某"
PATTERN_END_LOCATION_ONLY = re.compile(r"^\s*采录地点\s*(.*)$")
# 附加信息匹配（可选提取）；兼容 "讲 述者，…" "采录者；…" 等
PATTERN_NARRATOR = re.compile(
    r"^\s*讲\s*述者\s*[：:，,；;、]\s*(.+)$"
)
PATTERN_RECORDER = re.compile(
    r"^\s*采录\s*(?:者|录)\s*[：:；;，,、．.*＊]\s*(.+)$"
)


# ==========================================
# 2. 底层函数区域 (CORE FUNCTIONS)
# ==========================================
def initialize_environment(output_dir: str) -> bool:
    """初始化输出环境，确保输出目录存在"""
    print("[初始化] 检查并创建输出目录...")
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"[初始化] 成功创建输出目录: {output_dir}")
        else:
            print(f"[初始化] 输出目录已存在: {output_dir}")
        return True
    except Exception as e:
        print(f"[初始化失败] 无法创建输出目录: {e}")
        return False


def clean_story_title(title: str) -> str:
    """去掉标题中的引号、项目符号、括号/方括号注、空白、数字及 Unicode 标点（Excel / 文件名共用）。"""
    if not title:
        return title
    raw = title.strip()
    s = raw
    for ch in (
        '"',
        "'",
        "＂",
        "「",
        "」",
        "『",
        "』",
        "\u201c",
        "\u201d",
        "\u2018",
        "\u2019",
    ):
        s = s.replace(ch, "")
    for _ in range(4):
        s2 = re.sub(r"（[^）]*）", "", s)
        s2 = re.sub(r"\([^)]*\)", "", s2)
        s2 = re.sub(r"\[[^\]]*\]", "", s2)
        s2 = re.sub(r"【[^】]*】", "", s2)
        if s2 == s:
            break
        s = s2
    for ch in "•·●○▪▫◦※＊*":
        s = s.replace(ch, "")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[0-9０-９]", "", s)
    for ch in "（）()[]【】":
        s = s.replace(ch, "")
    s = "".join(c for c in s if not unicodedata.category(c).startswith("P"))
    return s if s else raw


def normalize_title_for_excel(title: str) -> str:
    """Excel「故事标题」列：与 clean_story_title 一致。"""
    return clean_story_title(title)


def _strip_recorded_location_suffix(rest: str) -> str:
    """去掉采录地点后的前导分隔符（含 * ； 半角句号等）。"""
    return re.sub(r"^[*＊：:；,，．.、\s]+", "", rest.strip())


def story_end_time_location(text: str) -> Optional[str]:
    """若本段为故事结尾元数据，返回写入「采录时间地点」的字符串，否则 None。"""
    t = text.strip()
    if not t:
        return None
    m = re.match(PATTERN_END, t, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = PATTERN_END_LOCATION_ONLY.match(t)
    if m:
        rest = m.group(1).strip()
        return _strip_recorded_location_suffix(rest) if rest else ""
    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\s*采录地点\s*(.*)$", line)
        if m:
            rest = m.group(1).strip()
            return _strip_recorded_location_suffix(rest) if rest else ""
    # 同一行内「采录者*… 采录时间*… 采录地点*…」：段首不是采录地点，取最后一次「采录地点」后的内容
    if "采录地点" in t and ("采录时间" in t or "采录者" in t):
        idx = t.rfind("采录地点")
        tail = t[idx + len("采录地点") :].strip()
        return _strip_recorded_location_suffix(tail) if tail else ""
    return None


def story_sort_key(story: Dict) -> int:
    """按故事编号数值排序（用于 Excel / 输出顺序）。"""
    raw = str(story.get("number", "0")).strip()
    try:
        return int(raw)
    except ValueError:
        return 0


def read_word_paragraphs(file_path: str) -> Optional[List[str]]:
    """读取 Word 文档中的所有段落文本"""
    print(f"[读取文件] 准备读取文档: {file_path}")
    if not os.path.exists(file_path):
        print(f"[读取文件失败] 找不到指定的文件: {file_path}")
        return None

    try:
        doc = docx.Document(file_path)
        paragraphs = [para.text for para in doc.paragraphs]
        print(f"[读取文件] 成功读取文档，共 {len(paragraphs)} 个段落。")
        return paragraphs
    except Exception as e:
        print(f"[读取文件失败] 解析 Word 文档发生异常: {e}")
        return None


def extract_stories_from_text(paragraphs: List[str]) -> Optional[List[Dict]]:
    """核心状态机：根据正则规则从段落中提取故事结构"""
    print("[提取逻辑] 开始执行故事特征匹配与提取...")
    
    stories: List[Dict] = []
    current_story: Optional[Dict] = None
    is_in_story = False
    
    try:
        for index, para in enumerate(paragraphs):
            text = para.strip()
            if not text:
                continue

            # 1. 检查是否为故事开头
            match_start = re.match(PATTERN_START, text)
            if match_start:
                if is_in_story and current_story is not None:
                    # 容错处理：上一个故事没有标准结尾，但遇到了新的故事开头
                    print(f"[提取警告] 故事 {current_story['number']} 未发现标准结尾，已强制闭合。")
                    current_story['content_text'] = "\n".join(current_story['content_list'])
                    stories.append(current_story)
                
                is_in_story = True
                story_num = match_start.group(1).strip()
                story_title = match_start.group(2).strip()
                print(f"[提取状态] 发现故事起始标点 -> 编号: {story_num}, 标题: {story_title}")
                
                current_story = {
                    'number': story_num,
                    'title': story_title,
                    'narrator': '',
                    'recorder': '',
                    'time_location': '',
                    'content_list': [text] # 保存包含标题在内的完整正文
                }
                continue

            # 2. 如果正在收集故事内容
            if is_in_story and current_story is not None:
                current_story['content_list'].append(text)
                
                # 尝试提取讲述人和采录人信息
                match_narrator = PATTERN_NARRATOR.match(text)
                if match_narrator:
                    current_story['narrator'] = match_narrator.group(1).strip()

                match_recorder = PATTERN_RECORDER.match(text)
                if match_recorder:
                    current_story['recorder'] = match_recorder.group(1).strip()

                # 3. 检查是否为故事结尾（合并行「采录时间、地点：…」或单独「采录地点*…」等）
                end_meta = story_end_time_location(text)
                if end_meta is not None:
                    current_story['time_location'] = end_meta
                    current_story['content_text'] = "\n".join(current_story['content_list'])
                    stories.append(current_story)
                    print(f"[提取状态] 发现故事结束标点 -> 故事 {current_story['number']} 收集完毕。")
                    is_in_story = False
                    current_story = None

        # 循环结束后，处理可能卡在缓冲区里的最后一个故事
        if is_in_story and current_story is not None:
             print(f"[提取警告] 文档结束，故事 {current_story['number']} 缺乏结尾标签，已强制闭合。")
             current_story['content_text'] = "\n".join(current_story['content_list'])
             stories.append(current_story)

        print(f"[提取完成] 共成功提取 {len(stories)} 个故事。")
        return stories

    except Exception as e:
        print(f"[提取失败] 状态机处理过程中发生异常: {e}")
        return None


def sanitize_filename(filename: str) -> str:
    """清理文件名：Windows 非法字符 + 控制字符（含 Tab，否则会 Errno 22）。"""
    s = re.sub(r'[\\/*?:"<>|]', "", filename)
    # Tab、换行等控制字符在 Windows 文件名中非法
    s = re.sub(r"[\x00-\x1f\x7f]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(" .")
    return s if s else "untitled"


def save_stories_to_txt(stories: List[Dict], output_dir: str) -> bool:
    """将提取的故事列表分别保存为独立的 txt 文件"""
    print(f"[文件输出] 准备将故事写入独立 txt 文件，目标文件夹: {output_dir}")
    if not stories:
        print("[文件输出失败] 故事列表为空，跳过 txt 写入。")
        return False
        
    success_count = 0
    used_paths: set = set()
    try:
        for story in stories:
            safe_title = sanitize_filename(clean_story_title(story['title']))
            base_name = f"{story['number']}_{safe_title}"
            file_name = f"{base_name}.txt"
            file_path = os.path.join(output_dir, file_name)
            dup = 2
            while file_path in used_paths:
                file_name = f"{base_name}_{dup}.txt"
                file_path = os.path.join(output_dir, file_name)
                dup += 1
            used_paths.add(file_path)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(story.get('content_text', ''))
            success_count += 1
            
        print(f"[文件输出] 成功写入 {success_count}/{len(stories)} 个 txt 文件。")
        return True
    except Exception as e:
        print(f"[文件输出失败] 写入 txt 文件时发生异常: {e}")
        return False


def save_stories_to_excel(stories: List[Dict], excel_path: str) -> bool:
    """将提取的故事列表汇总输出为 Excel 表格"""
    print(f"[表格输出] 准备生成汇总 Excel，目标路径: {excel_path}")
    if not stories:
        print("[表格输出失败] 故事列表为空，跳过 Excel 写入。")
        return False
        
    try:
        # 构建适合 DataFrame 的数据结构
        data_for_excel = []
        for story in stories:
            data_for_excel.append({
                '故事编号': story['number'],
                '故事标题': normalize_title_for_excel(story['title']),
                '讲述者': story['narrator'],
                '采录者': story['recorder'],
                '采录时间地点': story['time_location'],
                '完整内容长度(字符数)': len(story.get('content_text', ''))
            })
            
        df = pd.DataFrame(data_for_excel)
        df.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"[表格输出] 成功保存 Excel 文件: {excel_path}")
        return True
    except Exception as e:
        print(f"[表格输出失败] 保存 Excel 文件时发生异常: {e}")
        return False


# ==========================================
# 3. 顶层入口 (MAIN ENGINE)
# ==========================================
def main():
    """主调度函数：仅负责控制底层函数的流转与错误阻断"""
    print("========== 自动提取故事工作流 启动 ==========")
    
    # 1. 环境初始化
    if not initialize_environment(OUTPUT_TXT_DIR):
        print("[主流程中断] 环境初始化失败，终止运行。")
        return

    # 2. 读取 Word 文档
    paragraphs = read_word_paragraphs(INPUT_WORD_PATH)
    if paragraphs is None:
        print("[主流程中断] 读取 Word 文档失败，终止运行。")
        return

    # 3. 提取故事结构
    stories = extract_stories_from_text(paragraphs)
    if stories is None or len(stories) == 0:
        print("[主流程中断] 未能从文档中提取出任何有效故事，终止运行。")
        return

    stories.sort(key=story_sort_key)

    # 4. 输出 txt 文本
    if not save_stories_to_txt(stories, OUTPUT_TXT_DIR):
         print("[主流程警告] TXT 文件保存环节出现异常。")

    # 5. 输出 Excel 汇总表
    if not save_stories_to_excel(stories, OUTPUT_EXCEL_PATH):
        print("[主流程警告] Excel 表格生成环节出现异常。")

    print("========== 自动提取故事工作流 结束 ==========")


if __name__ == "__main__":
    main()