# -*- coding: utf-8 -*-
"""
@file content_factory_5min_fixed.py
@brief 视频建模 -> Gemini 创作 -> OpenAI 口播剪辑 -> 16 篇 5 分钟口播资产
@details 针对【4–5 分钟口播】重新设计长度与主编策略
"""

import os
import json
import hashlib
from docx import Document
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from google.genai import types
from openai import OpenAI

# ==========================================
# 第一部分：配置 (CONFIGURATION)
# ==========================================
G_KEY = os.getenv("GEMINI_API_KEY")
O_KEY = os.getenv("OPENAI_API_KEY")

CONFIG = {
    "G_MODEL": "gemini-2.0-flash",
    "O_MODEL": "gpt-4o",
    "VIDEO_ID": "rDdoUbCFn24",
    "OUTPUT_DIR": "./final_production_assets",

    # 🔥 为 5 分钟口播重新设计的主编 Prompt
    "EDITOR_PROMPT": """
你不是写文章，你是在【对着手机前置摄像头说话】。

场景：
- 晚上
- 一个人
- 没提纲
- 没观众互动
- 不是演讲，也不是分享经验

写作规则（非常重要）：
1. 禁止“大家好”“今天聊聊”“谢谢大家”
2. 禁止总结句、方法论句
3. 允许句子断裂、重复、犹豫
4. 不体面瞬间必须是：
   - 当下很羞耻
   - 不太想被别人知道
   - 说出来会停顿的那种
5. 不要试图“给别人启发”
6. 字数控制在 650–850 字
7. 听起来像：一个人边想边说

返回 JSON：
{
  "draft": "...",
  "visuals": [...]
}
"""
}

# ==========================================
# 第二部分：基础函数
# ==========================================

def safe_json_load(text):
    try:
        if not text:
            return None
        start = text.find('{')
        end = text.rindex('}') + 1
        return json.loads(text[start:end])
    except Exception as e:
        print(f"[ERROR] JSON 解析失败: {e}")
        return None


def fetch_transcript_pro(vid):
    try:
        print(f"[INFO] 抓取字幕: {vid}")
        api = YouTubeTranscriptApi()
        data = api.fetch(vid, languages=['en', 'zh-Hans']).to_raw_data()
        return " ".join([i['text'] for i in data])
    except:
        try:
            return " ".join([t['text'] for t in YouTubeTranscriptApi.get_transcript(vid)])
        except:
            return None


def call_gemini_pro(client, prompt):
    try:
        resp = client.models.generate_content(
            model=CONFIG["G_MODEL"],
            contents=f"{prompt}\n\n[STRICT] 若无法输出合法 JSON，请返回 null。",
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return safe_json_load(resp.text)
    except Exception as e:
        print(f"[ERROR] Gemini 调用失败: {e}")
        return None


def call_openai_editor(client, draft):
    try:
        print("[PROCESS] OpenAI 正在进行 5 分钟口播剪辑...")
        resp = client.chat.completions.create(
            model=CONFIG["O_MODEL"],
            messages=[
                {"role": "system", "content": CONFIG["EDITOR_PROMPT"]},
                {
                    "role": "user",
                    "content": f"""
以下文本来自 AI 草稿。
目标：剪成【4–5 分钟可直接口播】。

原文如下：
----------------
{draft}
----------------
"""
                }
            ],
            temperature=0.4
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] OpenAI 剪辑失败: {e}")
        return draft


def save_pro_docx(title, content, filename):
    doc = Document()
    doc.add_heading(title, 0)
    for line in content.split('\n'):
        if line.strip():
            doc.add_paragraph(line.strip())
    path = os.path.join(CONFIG["OUTPUT_DIR"], filename)
    doc.save(path)
    print(f"[SUCCESS] 已生成: {filename}")

# ==========================================
# 第三部分：主流程
# ==========================================

def main():
    if not G_KEY or not O_KEY:
        print("[ERROR] 缺少 API KEY")
        return

    g_client = genai.Client(api_key=G_KEY)
    o_client = OpenAI(api_key=O_KEY)

    os.makedirs(CONFIG["OUTPUT_DIR"], exist_ok=True)

    transcript = fetch_transcript_pro(CONFIG["VIDEO_ID"])
    if not transcript:
        return

    print("[PHASE 1] 提取 5 个核心观点")
    p1_prompt = f"""
从以下内容中提取 5 个【可用于个人口播的视频观点】。
要求：偏情绪 / 冲突 / 真实感。
返回 JSON：
{{"points": [{{"id": 1, "summary": "..."}}]}}

TEXT:
{transcript[:25000]}
"""
    p1_res = call_gemini_pro(g_client, p1_prompt)
    points = p1_res.get("points", []) if p1_res else []
    if not points:
        return

    overview = "\n\n".join([f"观点{p['id']}: {p['summary']}" for p in points])
    save_pro_docx("核心观点总览", overview, "00_核心观点总览.docx")

    for p in points:
        pid = p["id"]
        summary = p["summary"]
        h = hashlib.md5(summary.encode()).hexdigest()[:8]

        print(f"\n>>> 处理观点 {pid}")

        g_prompt = f"""
基于以下观点，撰写一篇【800字以内】中文口播稿，
适合 4–5 分钟真人对镜头表达。

要求：
- 第一人称
- 插入 1–2 个【不体面瞬间】
- 不要总结升华
- 情绪递进明显

返回 JSON：
{{
  "draft": "...",
  "visuals": [
    {{"intent": "...", "prompt": "...", "style": "..."}}
  ]
}}

观点：
{summary}
"""
        g_res = call_gemini_pro(g_client, g_prompt)
        if not g_res:
            continue

        save_pro_docx(
            f"观点{pid}_Gemini原稿",
            g_res.get("draft", ""),
            f"P{pid}_{h}_01_Gemini原稿.docx"
        )

        edited = call_openai_editor(o_client, g_res.get("draft", ""))
        save_pro_docx(
            f"观点{pid}_OpenAI终稿",
            edited,
            f"P{pid}_{h}_02_OpenAI终稿.docx"
        )

        with open(
            os.path.join(CONFIG["OUTPUT_DIR"], f"P{pid}_{h}_03_视觉方案.json"),
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(g_res.get("visuals", []), f, ensure_ascii=False, indent=2)

    print("\n[FINISH] 5 分钟口播资产全部生成完毕")


if __name__ == "__main__":
    main()
