#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "pipeline")))
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import re
import json
import asyncio
import pandas as pd
import traceback
import sys
import time
import random
from typing import Tuple
from core_engine import robust_deepseek_call, load_env_config_file

# 配置文件路径
ENV_CONFIG_FILE = os.path.join(r"I:\AiVideos\podcast", "podcast.env")
SCRIPT_RESOURCE_FILE = r"I:\AiVideos\podcast\script_resource.xlsx"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 如果指定了 ENV_CONFIG_FILE，先加载它，使 DeepSeek API Key 等环境变量可用
if ENV_CONFIG_FILE:
    load_env_config_file(ENV_CONFIG_FILE)

# 提示词文件路径
PROMPT_FILES = {
    "content": os.path.join(SCRIPT_DIR, "深夜提示词.txt"),
    "character": os.path.join(SCRIPT_DIR, "图片提示词.txt"),
    "youtube": os.path.join(SCRIPT_DIR, "标题提示词.txt")
}


def load_excel_titles():
    """读取 Excel 文件，返回 cn_rewrite 不是 'yes' 的前10个标题"""
    try:
        if not os.path.exists(SCRIPT_RESOURCE_FILE):
            print(f"Excel file not found: {SCRIPT_RESOURCE_FILE}")
            return []

        df = pd.read_excel(SCRIPT_RESOURCE_FILE)
        print(f"Excel loaded, total rows: {len(df)}")
        
        # 筛选 cn_rewrite 不是 'yes' 的行
        filtered_df = df[df['cn_rewrite'] != 'yes']
        print(f"Filtered rows (cn_rewrite != 'yes'): {len(filtered_df)}")

        # 取前10个，返回 title 和 path
        titles_data = []
        for _, row in filtered_df.head(10).iterrows():
            title = str(row.get("title", "")).strip()
            path = str(row.get("path", "")).strip()
            titles_data.append({
                "title": title,
                "path": path
            })

        return titles_data
    except Exception as e:
        print(f"Error loading Excel: {e}")
        traceback.print_exc()
        return []

def read_file_content(file_path):
    """读取文件内容"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return ""

def _extract_json_from_text(text):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()

    def try_parse(candidate):
        try:
            return json.loads(candidate)
        except Exception:
            return None

    parsed = try_parse(text)
    if parsed is not None:
        return parsed

    # 兼容 DeepSeek 返回的附加说明文本，把首尾的 JSON 块抽取出来
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            parsed = try_parse(candidate)
            if parsed is not None:
                return parsed

    return None


def save_content(content, base_path):
    """保存内容到文件"""
    try:
        base_name = os.path.splitext(base_path)[0]

        content_json = _extract_json_from_text(content)
        if content_json is not None:
            glossary_file = f"{base_name}_glossary.json"
            existing_data = None

            if os.path.exists(glossary_file):
                with open(glossary_file, 'r', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                    except Exception:
                        existing_data = None

            if isinstance(content_json, dict):
                if isinstance(existing_data, dict):
                    existing_data.update(content_json)
                else:
                    existing_data = content_json
            elif isinstance(content_json, list):
                if isinstance(existing_data, list):
                    existing_data.extend(content_json)
                else:
                    existing_data = content_json
            else:
                existing_data = content_json

            with open(glossary_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

            return f"已保存 JSON 到 {glossary_file}"

        # 文本格式：保存到 _cn.txt
        cn_file = f"{base_name}_cn.txt"
        with open(cn_file, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"已保存文本到 {cn_file}"

    except Exception as e:
        return f"保存失败: {e}"

def inspect_tts_safety(task_id: str, text: str) -> Tuple[bool, str]:
    """
    TTS 播音级质检探针。
    严格拦截任何可能导致 Azure TTS 引擎抽搐、爆音或违和的内容。
    返回: (是否通过质检, 具体的错误原因日志)
    """
    if not text or not text.strip():
        return False, "文本为空"

    error_reasons = []

    # ==========================================
    # 雷区 1：英文字母 (导致中英文引擎强制切换，产生生硬的机器感)
    # ==========================================
    if re.search(r'[a-zA-Z]', text):
        error_reasons.append("包含英文字母")

    # ==========================================
    # 雷区 3：连续重复标点 (如 "！！！" 或 "？？？"，导致 AI 断句引擎崩溃)
    # 匹配任何连续出现 2 次及以上的常用标点
    # ==========================================
    if re.search(r'([！!？?。，；：])\1{1,}', text):
        error_reasons.append("包含连续重复标点")

    # ==========================================
    # 雷区 4：无法连读的特殊网络符号 (导致强行读出"井号"、"艾特")
    # ==========================================
    if re.search(r'[@#$%^&*<>{}\[\]\\]', text):
        error_reasons.append("包含特殊数学/网络符号")

    # ==========================================
    # 雷区 5：生硬的数字组合 (视你的频道风格而定，可选择性开启)
    # 很多时候 "120万" 读出来不如 "一百二十万" 有文学感。
    # 如果检测到阿拉伯数字，可以提醒人工改成中文数字。
    # ==========================================
    if re.search(r'[0-9]', text):
        error_reasons.append("包含阿拉伯数字 (建议人工转为中文大写以保语感)")

    # 综合判定
    if error_reasons:
        # 把所有触发的死因拼成一句话返回
        return False, " | ".join(error_reasons)
    
    return True, "PASS"

def complete_task(path, title, check_status):
    """标记任务为完成，并记录TTS质检结果"""
    print(f"Complete request: title='{title}', path='{path}', check='{check_status}'")
    if not path:
        print("路径为空，无法标记")
        return False

    try:
        if not os.path.exists(SCRIPT_RESOURCE_FILE):
             print(f"Excel文件未找到: {SCRIPT_RESOURCE_FILE}")
             return False

        # 读取 Excel
        df = pd.read_excel(SCRIPT_RESOURCE_FILE)
        
        # 查找匹配的行 (优先匹配 path，因为 path 更具唯一性)
        mask = (df['path'] == path)
        
        if mask.any():
            df.loc[mask, 'cn_rewrite'] = 'yes'
            df.loc[mask, 'check'] = check_status
            # 保存回 Excel
            df.to_excel(SCRIPT_RESOURCE_FILE, index=False)
            print(f"Marked as complete in Excel: {title}")
            return True
        else:
            print(f"Could not find matching row for: {title} ({path})")
            return False

    except Exception as e:
        print(f"Error updating Excel: {e}")
        traceback.print_exc()
        return False

async def main():
    print("----- 自动化文案重写流程开始 -----")
    
    # 1. 载入所有未完成的行
    titles = load_excel_titles()
    if not titles:
        print("没有找到 cn_rewrite != 'yes' 的行，流程结束。")
        return False
        
    # 取第一行
    target = titles[0]
    title = target["title"]
    path = target["path"]
    
    print(f"目标任务: [{title}]")
    print(f"目标文件路径: {path}")
    
    # 读取原始文本
    content = read_file_content(path)
    if not content:
        print(f"未能读取到文件内容或文件为空: {path}")
        return False
        
    print(f"原始文本长度: {len(content)} 字符")
    
    # 2. 读取各项提示词
    prompt_content = read_file_content(PROMPT_FILES["content"])
    prompt_character = read_file_content(PROMPT_FILES["character"])
    prompt_youtube = read_file_content(PROMPT_FILES["youtube"])
    
    if not prompt_content or not prompt_character or not prompt_youtube:
        print("提示词文件不完整，请检查是否有 深夜提示词.txt, 图片提示词.txt, 标题提示词.txt ！")
        return False

    # 3. 生成改写文案 - 调用 DeepSeek
    print("\n>>> 正在调用 DeepSeek 进行【文案改写】...")
    target_words = 5500
    final_prompt = f"""{prompt_content}【原文内容】{content}"""
    
    rewritten_content = await robust_deepseek_call(final_prompt, max_tokens=16384, clean_output=False, temperature=1.2)
    
    print(">>> 正在进行 Markdown 清理...")
    clean_text = re.sub(r'\*\*.*?\*\*', '', rewritten_content)
    clean_text = clean_text.replace("#", "")
    rewritten_content = re.sub(r'\n\s*\n', '\n', clean_text).strip()
        
    print(">>> 正在进行 TTS 播音质检...")
    is_safe, check_reason = inspect_tts_safety("", rewritten_content)
    check_status = "pass" if is_safe else "fail"
    print(f">>> 质检结果: {check_status} ({check_reason})")

    # 这个文案有可能带有 markdown 的，我们需要保存
    print(">>> 文案改写完成，正在保存...")
    actual_len = len(rewritten_content)
    print(f">>> 实际输出长度: {actual_len} 字 (目标: {target_words} 字)")
    print(f">>> first 500 chars: {rewritten_content[:500]}")
    
    res1 = save_content(rewritten_content, path)
    print(res1)
    
    # 4. 生成角色和图片参数 - 调用 DeepSeek
    print("\n>>> 正在调用 DeepSeek 进行【图片参数生成】...")
    character_prompt = f"{prompt_character}\n\n{rewritten_content}"
    character_json_str = await robust_deepseek_call(character_prompt, max_tokens=1500, clean_output=False)
    
    print(">>> 图片参数生成完成，正在保存...")
    res2 = save_content(character_json_str, path)
    print(res2)
    
    # 5. 生成 YouTube 信息 - 调用 DeepSeek
    print("\n>>> 正在调用 DeepSeek 进行【YouTube 参数生成】...")
    youtube_prompt = f"{prompt_youtube}\n\n{rewritten_content}"
    youtube_json_str = await robust_deepseek_call(youtube_prompt, max_tokens=1500, clean_output=False)
            
    print(">>> 正在保存 YouTube 参数...")
    res3 = save_content(youtube_json_str, path)
    print(res3)
    
    # 6. 将任务标记为处理完毕
    print(f"\n>>> 正在将 Excel 中的 {title} 标记为完成 (Check: {check_status})...")
    complete_task(path, title, check_status)
    
    print("----- 自动化文案重写流程全部结束 -----")
    return True


async def run_with_retry():
    """执行主程序，成功后等待 5 分钟 + random(10-30秒) 后重试，直到失败。"""
    while True:
        try:
            success = await main()
            if success:
                # 成功后等待 5 分钟 + 随机 10-30 秒
                wait_seconds = 300 + random.randint(10, 30)
                print(f"\n✓ 任务成功完成，将在 {wait_seconds} 秒后进行下一轮...")
                await asyncio.sleep(wait_seconds)
                print("\n\n" + "="*60)
                print("开始下一轮")
                print("="*60 + "\n")
            else:
                print("\n✗ 任务执行失败，停止重试。")
                break
        except Exception as e:
            print(f"\n✗ 执行过程中出错: {e}")
            traceback.print_exc()
            break


if __name__ == '__main__':
    # 设置事件循环策略以避免 Windows 异步事件循环关闭问题
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(run_with_retry())
    except KeyboardInterrupt:
        print("\n\n中断信号收到，程序退出。")
        sys.exit(0)