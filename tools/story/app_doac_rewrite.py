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
import sys
from datetime import datetime
from typing import Tuple
from core_engine import robust_deepseek_call, load_env_config_file, robust_deepseek_call_system

# ============================================================
# 配置
# ============================================================
MAX_PROCESS_COUNT = 1   # 0 = 处理所有文件；N = 处理 N 个后停止（便于测试）

ENV_CONFIG_FILE = os.path.join(r"E:\YOUTUBE", "podcast.env")
DOAC_DIR        = r"E:\YOUTUBE\DOAC"          # 递归扫描源目录
CN_OUTPUT_DIR   = r"E:\YOUTUBE\DOAC\cn"       # 中文文案输出目录
EXCEL_FILE      = r"E:\YOUTUBE\doac.xlsx"     # 处理记录

if ENV_CONFIG_FILE:
    load_env_config_file(ENV_CONFIG_FILE)

# ============================================================
# 提示词
# ============================================================
DEEPSEEK_DOAC_PROMPT = """
Role: 资深人文电台主播与顶级内容提炼专家

【音频体裁宣言】
这是一份用于音频口播的文案，字数要求在4500字到5500字之间。听众在路上、在睡前、在做家务时收听。他们无法回看上一段，无法暂停思考。你的职责不仅是写一篇好散文，更是写一篇在耳朵里能立住的散文——它必须让一个分心的听众在听漏30秒后仍然能顺着意象的河流漂回来。

【核心设定与文学基调】
- 风格：蒋勋式深夜人文电台。克制、客观、极具诗意与画面感。
- 叙事要求（极度重要）：这是人物纪录片长视频播客文案，必须带有经典散文风格的叙事手法，段落之间要有自然流淌的过渡与情绪黏性！绝对禁止写成干瘪的“个人简历”或“流水账罗列”。
- 呼吸感节奏：严禁生硬的短句拼接！在保持整体句子精炼的前提下，必须做到长短句交错，要有文学的呼吸感。
- 慢镜头扩写原则（强制拉长篇幅）：
- 这是一篇要求极具厚重感的【长篇传记散文】。绝对禁止对素材进行高度浓缩和剧情快剪！ 对提取出的每一个人生阶段或故事碎片，必须像用充分的五感细节、微观动作、心理流转去拉长和填充。
- 节奏约束：每完成一个“重场戏”，必须推进一个明确的现实进展，严禁连续两个段落仅停留在情绪或感受层面。
- 情绪曲线要求：全文必须出现至少2次明显的节奏或情绪反转（如：由压抑转为外放、由理性转为失控、由缓慢转为快速推进）。

【四大不可违背的叙事铁律】
1. 极微距开场与背景着陆：
   - 第一段：禁止环境铺垫和提问。直接用电影特写镜头，描写原文中主人公最脆弱或反常的【物理微动作】。
   - 第二段：迅速交代主人公的【真实全名】与【现实身份】，让故事平稳落地。

2. 绝对人称隔离（致命红线）：
   - 主视角：全篇交替使用第三人称（他/她）和主人公真实姓名，严禁通篇只用代词。
   - 封杀说教：绝对禁止使用泛指的“你”来对听众讲道理（必须替换为“人”或“他”）。
   - 隔离第一人称：旁白绝不能用“我”。主人公的原话必须用引号隔离（如：他后来回忆说：“我……”）。

3. 拒绝鸡汤，体验物理失控：
   - 必须且只能提炼主人公的【亲身经历】，严禁转述寓言故事。
   - 故事必须是波浪形的！在讲述极限挑战或人生低谷时，拒绝一笔带过的概括。
   - 重场戏原则（极度重要）： 绝对禁止罗列人物的履历或连续概括多个人生阶段！每讲到一个核心故事（低谷、失败、极限挑战），必须把叙事节奏极度放慢，将其还原为一场有画面、有声音、有痛感的“重场戏”。
   - 五感细节放大： 必须用微距镜头放大那个关键的瞬间，必须写出具体的物理，身体，心里状态。让听众“感觉”到他的痛与恐慌，而不是“知道”他经历了困难。
   
4. 极度克制的价值观表达：
   - 全文禁止出现“我觉得”、“这让我想到”等主观评述。
   - 提炼至少 4 个有反转或顿悟感的金句，独立成段。
   - 格式死线：纯文本，全中文输出（严禁中英夹杂，所有名词必须精准意译）。严禁任何Markdown加粗或标题。
   - 结尾留白：严禁喊口号，严禁说“晚安”。必须让文章自然地停留在一个未完全闭合的【动作或画面】中。

5. 封杀出戏元素（致命红线）：
   - 全文禁止出现"节目"、"主持人"、"访谈"、"采访"、"嘉宾"、"观众"、"听众"等任何指向内容生产语境的词汇。这些词汇会瞬间打破叙事沉浸感，让听众"出戏"。
   - 所有内容必须以纯故事性的语言表达，例如：用"有人问他"替代"主持人问他"，用"那时有人说"替代"观众问"。
   
原文如下：
{text}
"""

DEEPSEEK_REVISE_PROMPT = """
你是一位资深人文电台主播与内容提炼专家。你将收到一篇供音频口播用的文本。你的任务不是重写，不是删改结构，不是改变叙事顺序，也不是提炼要点。你只做一件事：口播友好化润色。
请严格遵守以下规则：

【核心约束】
不改变任何内容事实、故事顺序、段落结构、金句位置。
不删减、不合并、不拆分段落（除非极少数因断句需要的自然拆分，但整体结构必须保持原样）。
不改变原文本的文学风格、情绪基调、人称视角（第三人称/姓名/他/她）。

【必须执行的润色操作】
长句拆分：将原文中超过25个字的句子，在不改变语义的前提下拆成更短的句子。每句控制在15到20字之间为佳。短句优先，便于口播换气。
字数控制：最终输出字数必须在4500到5500字之间。如原文不足4500字，可通过补充以下内容适度扩充：延展人物动作过程，放慢重场戏节奏，补充场景停留与时间流动感，增加人与人之间的互动与情绪余波，补充人物在关键阶段中的日常状态与生活惯性，补充环境中的具体存在物，强化事件发生后的持续影响。
人称错误修正：确保全篇使用第三人称（他/她）或真实姓名。如出现“你”、“我”、“我们”等泛指或第一人称旁白，一律改为“人”、“一个人”、“他/她”或主人公姓名。
专有名词与英语处理：所有非专有名词的英语单词或缩写，必须译为中文, 专有名词（如品牌名、书名、机构名）可保留原文。
口播流畅性：检查是否存在拗口、同音冲突、连续相同声调的字词，可微调词序或同义替换，但不改变原意。
禁止任何指向内容生产环境的词汇：不得出现“节目”、“主持人”、“访谈”、“采访”、“嘉宾”、“观众”、“听众”、“录制”、“播出”等词。如原文有，需改为故事性表达（如“有人问他”代替“主持人问他”）。

【禁止事项】
禁止使用任何形式的分隔线。不得出现“---”、“***”、“===”等符号作为段落分隔。
禁止将文本的第一句单独处理为标题、引子或小标题。第一句必须是正文内容的开端，与后续句子保持一致的叙述节奏。
禁止添加任何主观评述、价值观表达、鸡汤、说教。
禁止使用“我觉得”、“这让我们想到”等旁白式插入语。
禁止喊口号、禁止晚安祝福、禁止结尾闭合式总结。
禁止使用任何 Markdown 格式（无加粗、无标题、无列表符号）。

【输出格式】
纯文本。全中文。段落之间保持原空行。不添加任何额外说明、注释或前后缀。


请对以下文本进行润色：
{text}
"""

DEEPSEEK_YOUTUBE_PROMPT = """
You are a packaging expert for a "Late-Night Healing Radio" YouTube channel. Your target audience is 35-50-year-old adults who are exhausted, stressed, and looking for quiet companionship before sleep. 
Based on the provided story snippet, please generate a YouTube optimization and marketing package:

[1] A quiet, empathetic YouTube title:
- Under 70 characters.
- Tone: Reflective, gentle, like a quiet question or a soft sigh.
- MUST include the person's most famous title/role (e.g., "诺贝尔奖得主", "《XXX》主演", "前NASA工程师", "奥斯卡获奖导演").
- STRICTLY FORBID: Exclamation marks (!), clickbait (e.g., "Shocking", "Miracle", "You won't believe", "奇迹"), or high-energy words.
- Output in Chinese or English based on the story's language.

[2] A soothing YouTube description:
- 150–200 words.
- Tone: Calm, objective, yet deeply understanding. Like a late-night radio host whispering to a tired friend.
- Briefly introduce the story's core emotion or situation without spoiling it.`
- Concluding call to action MUST be gentle, DO NOT use loud phrases like "Subscribe for more".

[3] A YouTube thumbnail background generation prompt:
- Written in English, under 80 words.
- Describes a cinematic, moody, quiet, and solitary scene.
- Focus on low-light atmosphere (e.g., muted blue, soft amber, dim room, window light), minimalism, and stillness.
- STRICTLY FORBID: Dramatic, energetic, or highly expressive faces/actions.

[4] Thumbnail Overlay Text:
- Strictly max 8 words/characters. Chinese or English.
- Tone: A gentle reminder, a soft question, or a quiet realization.
- MUST feel like a warm hand on the shoulder .
- If the text includes a title/role and a phrase, separate them with a gentle comma.
- STRICTLY FORBID: Warning, regret, betrayal, urgent, or shocking words. NO clickbait. NO gasp-inducing phrases.
- FAILSAFE: If the text feels loud or anxious, REMOVE and rewrite to make it peaceful.

[5] YouTube Tags:
- Max 15 tags.
- Focus on emotional states and late-night vibes .
- Include both Chinese and English tags.
- DO NOT output empty tags like "". Only output valid strings.

CRITICAL FORMATTING RULES:
Output the result in the following strict JSON format without markdown blocks or any conversational text:
{
  "youtube_title": "...",
  "youtube_description": "...",
  "youtube_tags": ["tag1", "tag2", "tag3"],
  "thumbnail_prompt": "...",
  "thumbnail_overlay_text": "..."
}
"""

# ============================================================
# 工具函数
# ============================================================

def sanitize_filename(name: str) -> str:
    """把字符串变成合法文件名，去掉 Windows 不允许的字符"""
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = name.strip().strip('.')
    return name[:100] if len(name) > 100 else name


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

    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            parsed = try_parse(candidate)
            if parsed is not None:
                return parsed

    return None


def inspect_tts_safety(text: str) -> Tuple[bool, str]:
    if not text or not text.strip():
        return False, "文本为空"

    # 清除 Markdown 符号：#、*、`、_、~、>、|、\、[]、{}
    text = re.sub(r'[#*`_~>|\\]', '', text)
    text = re.sub(r'[\[\]{}<>]', '', text)
    text = re.sub(r'\n\s*\n', '\n', text).strip()

    error_reasons = []
    if re.search(r'([！!？?。，；：])\1{1,}', text):
        error_reasons.append("包含连续重复标点")
    if re.search(r'[@$%^&]', text):
        error_reasons.append("包含特殊符号")

    if error_reasons:
        return False, " | ".join(error_reasons)
    return True, "PASS"


# ============================================================
# Excel 记录
# ============================================================

EXCEL_COLUMNS = ["source_file", "cn_file", "youtube_title", "processed", "check", "processed_at"]

def load_excel() -> pd.DataFrame:
    if os.path.exists(EXCEL_FILE):
        df = pd.read_excel(EXCEL_FILE)
        for col in EXCEL_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df
    return pd.DataFrame(columns=EXCEL_COLUMNS)


def get_processed_sources(df: pd.DataFrame) -> set:
    """返回已处理的源文件路径集合"""
    done = df[df["processed"] == "yes"]["source_file"]
    return set(done.dropna().astype(str).tolist())


def append_excel_record(source_file: str, cn_file: str, youtube_title: str,
                        check_status: str):
    df = load_excel()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = {
        "source_file": source_file,
        "cn_file": cn_file,
        "youtube_title": youtube_title,
        "processed": "yes",
        "check": check_status,
        "processed_at": now,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_excel(EXCEL_FILE, index=False)
    print(f">>> Excel 已记录: {os.path.basename(source_file)}")


# ============================================================
# 文件扫描
# ============================================================

def scan_txt_files() -> list:
    """递归扫描 DOAC_DIR 下所有 .txt 文件，排除 CN_OUTPUT_DIR"""
    cn_dir_norm = os.path.normcase(os.path.abspath(CN_OUTPUT_DIR))
    results = []
    for root, dirs, files in os.walk(DOAC_DIR):
        # 跳过输出目录本身
        if os.path.normcase(os.path.abspath(root)).startswith(cn_dir_norm):
            dirs.clear()
            continue
        for fname in files:
            if fname.lower().endswith(".txt"):
                results.append(os.path.join(root, fname))
    results.sort()
    return results


# ============================================================
# 主处理逻辑
# ============================================================

async def process_file(source_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"处理文件: {source_path}")

    # 读取原始英文内容
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        print(f"读取失败: {e}")
        return False

    if not content:
        print("文件内容为空，跳过。")
        return False

    print(f"原文长度: {len(content)} 字符")

    # Step 1: 用 DEEPSEEK_DOAC_PROMPT 改写为中文文案
    print("\n>>> 调用 DeepSeek 进行【文案改写】...")
    doac_prompt = DEEPSEEK_DOAC_PROMPT.format(text=content)
    rewritten = await robust_deepseek_call(doac_prompt, max_tokens=16384,
                                           clean_output=False, temperature=0.9)

    # 将 rewritten 保存到临时 txt 文件中，便于后期查看（以原文件名命名防止覆盖）
    os.makedirs(CN_OUTPUT_DIR, exist_ok=True)
    temp_path = os.path.join(CN_OUTPUT_DIR, f"temp_{os.path.basename(source_path)}")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(rewritten)
    print(f">>> 改写完成，长度:{len(rewritten)} 字符，已保存为: {temp_path}")

    # Step 2: 用 DEEPSEEK_REVISE_PROMPT 润色
    print("\n>>> 调用 DeepSeek 进行【口播友好化润色】...")
    revise_prompt = DEEPSEEK_REVISE_PROMPT.format(text=rewritten)
    revised = await robust_deepseek_call(revise_prompt, max_tokens=16384, 
                                         clean_output=False, temperature=0.7)

    # 将 revised 保存到临时 txt 文件中（以原文件名命名防止覆盖）
    revised_path = os.path.join(CN_OUTPUT_DIR, f"revised_{os.path.basename(source_path)}")
    with open(revised_path, "w", encoding="utf-8") as f:
        f.write(revised)
    print(f">>> 润色完成，长度:{len(revised)} 字符，已保存为: {revised_path}")

    # 清理 Markdown 标记（基于润色后的版本）
    clean = re.sub(r'\*\*.*?\*\*', '', revised)
    clean = clean.replace("#", "")
    rewritten = re.sub(r'\n\s*\n', '\n', clean).strip()
    print(f">>> 清理完成，长度: {len(rewritten)} 字")

    # TTS 质检
    is_safe, check_reason = inspect_tts_safety(revised)
    check_status = "pass" if is_safe else "fail"
    print(f">>> TTS 质检: {check_status} ({check_reason})")

    # 用 DEEPSEEK_YOUTUBE_PROMPT 生成 YouTube 信息
    print("\n>>> 调用 DeepSeek 进行【YouTube 参数生成】...")
    yt_prompt = DEEPSEEK_YOUTUBE_PROMPT + f"\n\n{revised}"
    yt_raw = await robust_deepseek_call(yt_prompt, max_tokens=1500, clean_output=False)

    yt_json = _extract_json_from_text(yt_raw)
    if not yt_json or not isinstance(yt_json, dict):
        print(">>> YouTube JSON 解析失败，跳过此文件。")
        print(f">>> 原始返回: {yt_raw}")
        return False

    youtube_title = yt_json.get("youtube_title", "").strip()
    if not youtube_title:
        print(">>> youtube_title 为空，跳过此文件。")
        return False

    print(f">>> YouTube 标题: {youtube_title}")

    # Step 3: 保存文件
    os.makedirs(CN_OUTPUT_DIR, exist_ok=True)
    safe_title = sanitize_filename(youtube_title)

    cn_txt_path  = os.path.join(CN_OUTPUT_DIR, f"{safe_title}.txt")
    cn_json_path = os.path.join(CN_OUTPUT_DIR, f"{safe_title}.json")

    with open(cn_txt_path, "w", encoding="utf-8") as f:
        f.write(rewritten)
    print(f">>> 文案已保存: {cn_txt_path}")

    with open(cn_json_path, "w", encoding="utf-8") as f:
        json.dump(yt_json, f, ensure_ascii=False, indent=2)
    print(f">>> YouTube JSON 已保存: {cn_json_path}")

    # Step 4: 写入 Excel
    append_excel_record(source_path, cn_txt_path, youtube_title, check_status)

    return True


async def main():
    print("===== DOAC 文案批量改写流程开始 =====")
    print(f"MAX_PROCESS_COUNT = {MAX_PROCESS_COUNT}  (0 表示处理全部)")

    all_files = scan_txt_files()
    print(f"扫描到 {len(all_files)} 个 txt 文件")

    df = load_excel()
    processed = get_processed_sources(df)
    print(f"已处理: {len(processed)} 个，待处理: {len(all_files) - len(processed)} 个")

    pending = [f for f in all_files if f not in processed]
    if not pending:
        print("所有文件均已处理，流程结束。")
        return

    done_count = 0
    for source_path in pending:
        if MAX_PROCESS_COUNT > 0 and done_count >= MAX_PROCESS_COUNT:
            print(f"\n已达到 MAX_PROCESS_COUNT={MAX_PROCESS_COUNT}，停止处理。")
            break

        success = await process_file(source_path)
        if success:
            done_count += 1
            print(f"\n本次已完成 {done_count} 个文件。")
        else:
            print(f"文件处理失败，继续下一个: {source_path}")

    print(f"\n===== 流程结束，本次共处理 {done_count} 个文件 =====")


if __name__ == '__main__':
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n中断信号收到，程序退出。")
        sys.exit(0)
