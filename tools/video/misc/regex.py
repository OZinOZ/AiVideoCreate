"""
基于文本截取与预清洗的数据提取脚本。
该脚本首先裁剪掉无效的头部和尾部文本，将范围精准锁定在 Express 的专属区域内，
然后再对干净的文本片段进行正则提取。
完全遵循 pylint 规范，具备严格的异常处理与日志打印。
"""

import re
from typing import List, Optional

# ==========================================
# 1. 全局配置区 (Configuration)
# ==========================================
CONFIG = {
    "TARGET_TEXT": (
        "Paradise me of the / Enjoy 15% off "
        "Express &4 S12.80 in 4 min 6.24 am S2.23 $15.03 "
        "Max S20.85 in 8 min 6.30 am Delivery S11.71 in 5 min 6.29 am"
    ),
    "START_KEYWORD": "Express",
    "END_KEYWORDS": ["Max", "Delivery", "Travel"],
    # 经过文本清洗后，提取数字的正则变得极其简单
    "SIMPLE_PATTERN": r"[Ss$]\s*(\d+(?:\.\d{1,2})?)"
}

# ==========================================
# 2. 底层功能函数区 (Functions)
# ==========================================

def truncate_before_start(text: str, start_word: str) -> Optional[str]:
    """查找起始关键词，并截断（删除）该关键词之前的所有文本。"""
    print(f"[*] 开始执行函数: 裁剪起始节点之前的文本 (起始词: '{start_word}')")
    
    # 查找起始词的索引位置
    start_index = text.find(start_word)
    
    if start_index == -1:
        print(f"[-] 判断失败: 未能在文本中找到起始关键词 '{start_word}'。")
        return None
        
    # 从起始词开始切片，保留后面的所有内容
    truncated_text = text[start_index:]
    print(f"[+] 函数成功: 头部截断完毕。剩余文本起首: '{truncated_text[:20]}...'")
    return truncated_text

def truncate_after_ends(text: str, end_words: List[str]) -> str:
    """查找最早出现的阻断关键词，并截断（删除）该关键词及之后的所有文本。"""
    print(f"[*] 开始执行函数: 寻找阻断节点并裁剪尾部文本 (阻断词库: {end_words})")
    
    # 记录最早出现的阻断词的索引（初始化为文本总长度）
    earliest_end_index = len(text)
    found_any = False
    
    for word in end_words:
        index = text.find(word)
        if index != -1 and index < earliest_end_index:
            earliest_end_index = index
            found_any = True
            
    if not found_any:
        print("[+] 判断结果: 未发现任何阻断关键词，保留全文不作尾部裁剪。")
        return text
        
    # 截取到最早出现的阻断词之前
    clean_text = text[:earliest_end_index]
    print(f"[+] 函数成功: 尾部截断完毕。清洗后的纯净文本长度: {len(clean_text)} 字符。")
    return clean_text

def extract_target_numbers(text: str, pattern: str) -> Optional[List[str]]:
    """在清洗后的纯净文本中，使用简单正则提取所有目标金额。"""
    print("[*] 开始执行函数: 从纯净文本中提取金额数据")
    
    try:
        compiled_regex = re.compile(pattern)
        # re.findall 会直接返回所有匹配的列表
        matches = compiled_regex.findall(text)
        
        if not matches:
            print("[-] 判断失败: 未能在纯净文本中提取到任何符合规则的金额数据。")
            return None
            
        if len(matches) < 3:
            print(f"[-] 判断失败: 提取的数据数量不足 3 个。当前仅提取到: {matches}")
            return None
            
        # 如果提取到超过3个，我们只取前3个
        final_result = matches[:3]
        print(f"[+] 函数成功: 成功提取到目标数据: {final_result}")
        return final_result
        
    except re.error as err:
        print(f"[-] 函数失败: 正则表达式语法错误: {err}")
        return None

# ==========================================
# 3. 核心主控逻辑 (Main Entry Point)
# ==========================================

def main():
    """主控函数：按顺序调度文本头部截断、尾部截断以及正则提取引擎。"""
    print("====== 开始执行清洗与提取主流程 ======")
    
    raw_text = CONFIG["TARGET_TEXT"]
    print(f"\n[原始文本] {raw_text}\n")
    
    # 步骤 1: 删除 Express 前面的内容
    text_after_start = truncate_before_start(raw_text, CONFIG["START_KEYWORD"])
    if not text_after_start:
        print("[-] 流程中断：头部截取未能通过。")
        return
        
    # 步骤 2: 删除 Max/Delivery/Travel 及其后面的内容
    clean_text = truncate_after_ends(text_after_start, CONFIG["END_KEYWORDS"])
    if not clean_text:
        print("[-] 流程中断：尾部截取后文本为空。")
        return
        
    print(f"\n[纯净切片] {clean_text}\n")
        
    # 步骤 3: 在绝对安全的纯净切片里，用最简单的正则提取数据
    result = extract_target_numbers(clean_text, CONFIG["SIMPLE_PATTERN"])
    if not result:
        print("[-] 流程中断：数据提取未能完成。")
        return
        
    print("\n====== 清洗与提取流程全部圆满结束 ======")
    print(f"🎉 最终提取结果: {result}")

if __name__ == "__main__":
    main()