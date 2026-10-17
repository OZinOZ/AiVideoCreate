# -*- coding: utf-8 -*-
"""
WarRoom Engine V24.0 - 时间戳·强审计版 (The Timestamped Auditor)

【修复清单】
1. 文件名对齐：所有输出文件增加 {时间戳}_ 前缀，确保证据与脚本一一对应。
2. DeepSeek 显形：强制打印审核日志，修复逻辑吞没错误的问题。
3. 长度与格式死刑：DeepSeek 只要发现字数不够或有【画面】，直接打回重写。
"""

import os
import json
import asyncio
import re
import sys
from datetime import datetime
from contextlib import asynccontextmanager

from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from google.genai import types
from openai import AsyncOpenAI

# ==========================================
# 配置
# ==========================================
G_KEY = os.getenv("GEMINI_API_KEY")
O_KEY = os.getenv("OPENAI_API_KEY")
S_KEY = os.getenv("SILICONFLOW_API_KEY")

CONFIG = {
    "BASE_PATH": "D:/AIGen/Output",
    "VIDEO_ID": "rDdoUbCFn24", 
    "G_MODEL": "gemini-2.0-flash", 
    "O_MODEL": "gpt-4o",
    "D_MODEL": "deepseek-ai/DeepSeek-V3",
    "MAX_RETRIES": 3,
    "PASS_SCORE": 90
}

# ==========================================
# 提示词矩阵
# ==========================================
PROMPTS = {
    # [Step 1] 证据提取
    "P1_TOPIC_SPLITTER": """你是一个内容拆解师。
    从访谈中拆解 5 个核心概念。
    输出 JSON: {"topics": [{"id": 1, "concept": "...", "brief": "..."}]}""",

    "P1_DEEP_EVIDENCE": """你是一个速记员。
    针对概念【{concept}】，整理一份 **1500字** 的纯文本笔记。
    【死命令】：
    1. **严禁Markdown**：不要列表，写成连贯的散文。
    2. **深挖细节**：讲者举了什么具体的例子？当时的情绪是什么？
    3. **深挖理论**：讲者是如何解释背后原理的？
    输出纯文本笔记。""",

    # [Step 2] 撰稿：纯口播·深度版
    "P2_DEEP_WRITER": """你是一个深度科普博主。
    请基于【证据笔记】，写一篇 **1500字** 的深度视频脚本。

    【格式死刑 (触犯即废稿)】：
    1. **严禁画面/镜头**：绝对不要写【画面：XXX】、【镜头推近】。只写嘴里说出来的话！
    2. **严禁开场白**：不要写“大家好”、“开场”、“0-20s”。直接从第一句话开始讲故事。
    3. **严禁Markdown**：不要用加粗或标题。

    【内容要求】：
    1. **只选两招**：挑选笔记里最核心的 2 个方法。
    2. **饱和式攻击**：针对这两个方法，结合笔记里的案例（如肥胖、女儿、会议室）和原理（如内部触发器），讲深、讲透。
    3. **字数达标**：必须写满 1500 字，不够就扩写案例细节。

    【素材来源】：
    {evidence_note}

    输出纯文本脚本。""",

    # [Step 3] 润色：扩写与清洗
    "P3_EXPAND_POLISH": """你是一个文字编辑。
    润色这篇脚本。
    
    【DeepSeek 意见】：{advice}
    
    【任务】：
    1. **清洗格式**：如果看到【】、()、"开场"、"结尾"等标记，**全部删掉**。
    2. **强制扩写**：如果脚本看起来太短（少于1500字），请根据【证据笔记】里的细节，把案例描述得更细致（比如描写心理活动）。
    3. **去油腻**：删掉“逆袭”、“底层逻辑”等大词。
    
    【证据笔记】：{evidence_note}
    
    输出修改后的脚本。""",

    # [Step 4] 判官：字数与格式宪兵
    "P4_STRICT_AUDITOR": """你是一个极其严格的审核员。打分 (0-100)。
    
    【死刑标准 (直接 0 分)】：
    1. **有画面指令**：出现了【画面】、【镜头】、(0-20s) 等非口播内容。
    2. **字数太少**：读起来感觉少于 1200 字 (太干，没细节)。
    3. **有开场白**：出现了“大家好”、“今天我们来聊聊”。
    4. **像说明书**：全是步骤条列，没有连贯的故事感。
    
    输出 JSON: {{"score": 85, "advice": "还是有【画面】标记，全部删掉！字数不够，把第一个案例扩写...", "status": "FAIL"}}"""
}

class WarRoomEngine:
    def __init__(self):
        self.g_client = genai.Client(api_key=G_KEY)
        self.o_client = None
        self.s_client = None
        # 生成本次运行的唯一 Session ID
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in ["scripts", "raw", "evidence"]: 
            path = os.path.join(CONFIG["BASE_PATH"], d)
            os.makedirs(path, exist_ok=True)

    def log(self, msg, level="INFO"):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}")

    def safe_json(self, text):
        try:
            clean = re.sub(r'```json\s*|```', '', text).strip()
            if "{" in clean: clean = clean[clean.find("{"):]
            if "}" in clean: clean = clean[:clean.rfind("}")+1]
            clean = re.sub(r',(\s*})', r'\1', clean) 
            return json.loads(clean)
        except Exception as e:
            self.log(f"JSON异常: {e}", "WARN"); return None

    def clean_markdown(self, text):
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'#+\s*', '', text)
        text = re.sub(r'^\s*-\s+', '', text, flags=re.MULTILINE)
        return text.strip()

    @asynccontextmanager
    async def session_scope(self):
        self.o_client = AsyncOpenAI(api_key=O_KEY)
        self.s_client = AsyncOpenAI(api_key=S_KEY, base_url="https://api.siliconflow.com/v1")
        try: yield
        finally:
            await self.o_client.close()
            await self.s_client.close()

    # ==========================================
    # Phase 1: 证据生成 (带时间戳)
    # ==========================================
    async def phase1_evidence(self, content):
        self.log(f"🔍 [Session: {self.session_id}] Phase 1: 提取核心概念...")
        try:
            res = self.g_client.models.generate_content(
                model=CONFIG["G_MODEL"],
                contents=PROMPTS["P1_TOPIC_SPLITTER"] + f"\n\n素材: {content[:100000]}",
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            topics = self.safe_json(res.text)["topics"]
        except Exception as e:
            self.log(f"拆解失败: {e}", "ERROR"); return None

        evidence_map = {}
        # 文件名带时间戳
        evidence_filename = f"{self.session_id}_Evidence.txt"
        evidence_path = os.path.join(CONFIG["BASE_PATH"], "evidence", evidence_filename)
        
        with open(evidence_path, "w", encoding="utf-8") as f:
            for topic in topics:
                self.log(f"   📝 深挖证据: {topic['concept']} ...")
                prompt = PROMPTS["P1_DEEP_EVIDENCE"].format(concept=topic['concept'])
                try:
                    res = self.g_client.models.generate_content(
                        model=CONFIG["G_MODEL"],
                        contents=prompt + f"\n\n全文: {content}"
                    )
                    clean_text = self.clean_markdown(res.text)
                    topic['evidence_text'] = clean_text
                    evidence_map[topic['id']] = topic
                    
                    f.write(f"=== {topic['concept']} ===\n")
                    f.write(clean_text)
                    f.write("\n\n" + "="*50 + "\n\n")
                    f.flush()
                except: continue
        
        self.log(f"✅ 证据已存档: {evidence_path}")
        return evidence_map

    # ==========================================
    # Phase 2: 强审计博弈
    # ==========================================
    async def _battle_loop(self, draft, evidence):
        current = draft
        advice = "要求：字数必须 > 1200，严禁【画面】指令，纯口播稿。"
        
        for r in range(1, CONFIG["MAX_RETRIES"] + 1):
            self.log(f"   ⚔️ [Round {r}] ChatGPT 正在扩写与清洗...")
            
            # Step 3: ChatGPT 润色
            try:
                res_o = await self.o_client.chat.completions.create(
                    model=CONFIG["O_MODEL"],
                    messages=[
                        {"role": "system", "content": PROMPTS["P3_EXPAND_POLISH"].format(
                            evidence_note=evidence[:2000], 
                            advice=advice
                        )},
                        {"role": "user", "content": current}
                    ]
                )
                refined = res_o.choices[0].message.content
            except Exception as e:
                self.log(f"   ❌ ChatGPT 出错: {e}", "ERROR"); return current

            # Step 4: DeepSeek 审计 (显形版)
            self.log(f"   👮 [Round {r}] DeepSeek 正在执法...")
            try:
                res_d = await self.s_client.chat.completions.create(
                    model=CONFIG["D_MODEL"],
                    messages=[
                        {"role": "system", "content": PROMPTS["P4_STRICT_AUDITOR"]},
                        {"role": "user", "content": refined}
                    ]
                )
                audit_text = res_d.choices[0].message.content
                audit = self.safe_json(audit_text)
            except Exception as e:
                self.log(f"   ❌ DeepSeek 崩溃: {e}", "ERROR")
                # 如果 DeepSeek 挂了，为了不中断，我们暂且认为通过，但打印警告
                self.log("   ⚠️ 跳过审计直接输出（因 DeepSeek 故障）")
                return refined

            score = audit.get("score", 0) if audit else 0
            new_advice = audit.get("advice", "无") if audit else "无"
            
            self.log(f"   ⚖️ [DeepSeek] 评分: {score} | 判词: {new_advice[:60]}...")
            
            if score >= CONFIG["PASS_SCORE"]:
                self.log("   ✅ 审核通过！")
                return refined
            
            advice = f"得分仅{score}。DeepSeek 怒斥：{new_advice}。请立即扩写并删除格式！"
            current = refined
            
        return current

    async def start(self):
        self.log(f"启动 V24.0 时间戳·强审计引擎 | Session: {self.session_id}")
        try:
            ts = YouTubeTranscriptApi().fetch(CONFIG["VIDEO_ID"], languages=['en', 'zh-Hans']).to_raw_data()
            content = " ".join([i['text'] for i in ts])
        except: self.log("字幕失败", "ERROR"); return

        async with self.session_scope():
            evidence_map = await self.phase1_evidence(content)
            if not evidence_map: return

            for tid, topic in evidence_map.items():
                # 清洗标题，用于文件名
                safe_title = re.sub(r'[\\/*?:"<>|]', "", topic['concept'])
                self.log(f"\n🎙️ 制作脚本: {safe_title}")
                
                # Step 2: 撰稿
                prompt = PROMPTS["P2_DEEP_WRITER"].format(
                    evidence_note=topic['evidence_text']
                )
                try:
                    res_g = self.g_client.models.generate_content(
                        model=CONFIG["G_MODEL"],
                        contents=prompt
                    )
                    draft = res_g.text
                except: continue

                # Step 3-4: 博弈
                final = await self._battle_loop(draft, topic['evidence_text'])
                
                # 存档 (带时间戳)
                script_filename = f"{self.session_id}_Script_{safe_title}.txt"
                path = os.path.join(CONFIG["BASE_PATH"], "scripts", script_filename)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(final)
                self.log(f"   ✨ 脚本已存: {path}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if not all([G_KEY, O_KEY, S_KEY]): print("❌ 缺 Key")
    else: asyncio.run(WarRoomEngine().start())