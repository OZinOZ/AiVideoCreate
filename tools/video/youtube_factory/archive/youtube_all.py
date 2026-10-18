# -*- coding: utf-8 -*-
"""
WarRoom Engine V72.0 - 实时监视版 (The Live Monitor)

【核心升级】
1. 实时预览：控制台直接打印每个步骤生成的前 20 个字。
   - 让你一眼看出 Gemini 是否在说人话。
   - 让你一眼看出 DeepSeek 是否在认真挑刺。
2. 异常早停：如果预览内容不对（比如出现代码、乱码），你可以立刻 Ctrl+C 止损。
3. 继承功能：保留了 V71 的全程监控 Log 文件和 V70 的断点续存保护。
"""

import os
import json
import asyncio
import re
import sys
import signal
import random
from datetime import datetime
from contextlib import asynccontextmanager

from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from openai import AsyncOpenAI

TIMESTAMPS_INPUT = """
02:02 Being indistractable
10:21 4 steps to avoid distractions
17:37 10-minute rule to beat procrastination
27:40 Prevent distraction & improve sex life
34:56 How to become disciplined & have strong willpower
47:33 The power of time allocation
53:33 Stop burnout
01:00:27 Stop blaming social media
01:10:17 Overcoming our traumas and improving confidence
01:20:39 Why is there a rise in ADHD?
01:37:31 Last guest’s question
"""

# ==========================================
# 1. API 配置
# ==========================================
G_KEY = os.getenv("GEMINI_API_KEY")
O_KEY = os.getenv("OPENAI_API_KEY")
S_KEY = os.getenv("SILICONFLOW_API_KEY")

CONFIG = {
    "BASE_PATH": "D:/AIGen/Output",
    "VIDEO_ID": "rDdoUbCFn24", 
    "G_MODEL": "gemini-2.5-pro", 
    "O_MODEL": "gpt-4o",
    "D_MODEL": "deepseek-ai/DeepSeek-V3",
    "MAX_RETRIES": 3,
    "PASS_SCORE": 85 
}

# ==========================================
# 2. 范文库
# ==========================================
GRITTY_EXAMPLES = """
【满分范文 - Option A (视觉流)】
(Block 1: 特写镜头)
光标在空白文档上闪烁。第一下，第二下，第三下。你盯着它，觉得它像一把倒计时的刀。
(Block 2: 心理旁白)
你不敢动。你怕敲下的第一个字是垃圾。你怕那个完美的幻象破碎。这种僵硬不叫慎重，叫懦弱。
(Block 3: 结尾)
敲下去。哪怕是乱码。

【满分范文 - Option B (节奏流)】
(Block 1: 情绪断奏)
你不是累。
你是空。
油箱没油是累，引擎空转是空。
(Block 2: 节奏推进)
你拼命踩油门。
转速表爆表。
车轮陷在泥里纹丝不动。
这不叫努力。
这叫自毁。
(Block 3: 结尾)
熄火。下车。

【满分范文 - Option C (洞察流)】
(Block 1: 现象重构)
我们买课、买书、买各种效率工具。像是在给即将沉没的船刷漆。
(Block 2: 深度归因)
我们痴迷于“准备工作”，因为准备是安全的。而“行动”是危险的。我们用消费的快感，抵消了行动的痛感。这是弱者的止痛药。
(Block 3: 结尾)
把书扔了。去干活。
"""

# ==========================================
# 3. 提示词
# ==========================================
PROMPT_GEMINI_DRAFT = """你是一个冷酷的现实主义者。
请模仿【满分范文】，创作 3 个变体。
必须保留 (Block 1)/(Block 2)/(Block 3) 标签。

【范文】：{examples}
【素材】：{content_chunk}

【要求】：
1. **拒绝温和**：要刺痛观众。
2. **结构锁死**：Option A (视觉) / Option B (节奏) / Option C (洞察)。
3. **内容**：不要写废话，直接切入痛点。

输出纯文本。"""

PROMPT_DEEPSEEK_CRITIC = """你是一个毒舌主编。
请点评这段文案（由 Gemini 生成）：
"{draft}"

【挑刺标准】：
1. **不够狠**：是不是还在讲大道理？我要的是揭穿！
2. **没画面**：开头是不是太抽象？给我具体的物体！
3. **逻辑软**：是不是在以此充好？

请给出 3 条简短的修改意见。"""

PROMPT_GPT_POLISH = """你是一个文字大师（风格类似 Fight Club 的 Tyler Durden）。
这是 Gemini 写初稿，DeepSeek 给的意见。请你重写一遍。

【初稿】：
"{draft}"

【DeepSeek 意见】：
{critique}

【教父指令】：
1. **保持粗粝感**：不要把它改得温文尔雅！保持那种短促、有力、冷酷的调性。
2. **优化流动性**：让句子像子弹一样上膛。去掉所有翻译腔。
3. **保留结构**：依然是 Option A/B/C。

直接输出优化后的文案。"""

PROMPT_ENDING_DIRECTOR = """你是一个动作指导。
原来的结尾不够有力。
【原结尾】："{original_ending}"
【指令】：**{director_order}**
请重写结尾。极短。像命令。"""

DIRECTOR_ORDERS = [
    "给我一个**粗暴的物理动作**。",
    "用一个**反直觉的短句**。",
    "用一个**冷酷的二选一**。",
    "用**极简的时间指令**。"
]

class WarRoomEngine:
    def __init__(self):
        self.g_client = genai.Client(api_key=G_KEY)
        self.o_client = AsyncOpenAI(api_key=O_KEY)
        self.s_client = AsyncOpenAI(api_key=S_KEY, base_url="https://api.siliconflow.com/v1")
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self._ensure_dirs()
        self.all_scripts_buffer = []
        self.should_stop = False
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        print("\n🛑 收到中止信号 (Ctrl+C)！正在停止...")
        self.should_stop = True

    def _ensure_dirs(self):
        for d in ["scripts_monitor", "raw"]: 
            os.makedirs(os.path.join(CONFIG["BASE_PATH"], d), exist_ok=True)

    def log(self, msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    # 辅助函数：生成预览文本
    def get_preview(self, text):
        if not text: return "❌ [空内容]"
        # 去掉换行符，多余空格，截取前30个字符
        clean = text.replace('\n', ' ').strip()
        # 如果是 Option 开头，尝试往后截一点
        clean = re.sub(r'### Option [A-C] \(.*?\) ###', '', clean).strip() 
        return f"📄 {clean[:25]}..."

    def log_surveillance(self, stage, content):
        debug_path = os.path.join(CONFIG["BASE_PATH"], "scripts_monitor", f"{self.session_id}_Debug_Log.txt")
        try:
            with open(debug_path, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime('%H:%M:%S')
                f.write(f"\n{'='*20} [{timestamp}] {stage} {'='*20}\n")
                f.write(f"{str(content).strip()}\n")
                f.write(f"{'-'*50}\n")
        except: pass

    def save_results(self):
        if not self.all_scripts_buffer: return None
        full_path = os.path.join(CONFIG["BASE_PATH"], "scripts_monitor", f"{self.session_id}_Final.txt")
        try:
            with open(full_path, "w", encoding="utf-8") as f: 
                f.writelines(self.all_scripts_buffer)
        except Exception as e:
            self.log(f"❌ 存档失败: {e}")
            return None
        return full_path

    @asynccontextmanager
    async def session_scope(self):
        try: yield
        finally: 
            await self.o_client.close()
            await self.s_client.close()

    def parse_timestamps(self, text):
        lines = text.strip().split('\n')
        milestones = []
        for line in lines:
            match = re.search(r'(\d+):(\d+)(?::(\d+))?\s+(.*)', line)
            if match:
                h = int(match.group(1)) if match.group(3) else 0
                m = int(match.group(2)) if match.group(3) else int(match.group(1))
                s = int(match.group(3)) if match.group(3) else int(match.group(2))
                total_seconds = h * 3600 + m * 60 + s
                milestones.append({'time': total_seconds, 'title': match.group(4)})
        return milestones

    def slice_transcript(self, transcript_data, milestones):
        chunks = []
        milestones.append({'time': 999999, 'title': 'END'})
        for i in range(len(milestones) - 1):
            text_segment = [e['text'] for e in transcript_data if milestones[i]['time'] <= e['start'] < milestones[i+1]['time']]
            if text_segment: chunks.append({'title': milestones[i]['title'], 'text': " ".join(text_segment)})
        return chunks

    async def ending_reshoot(self, draft):
        if not draft: return ""
        try:
            options = re.split(r'(### Option [A-C] ###|Option [A-C]:|Option [A-C])', draft)
            if len(options) < 2: return draft

            final_output = ""
            for i in range(1, len(options), 2):
                header = options[i]
                body = options[i+1].strip()
                if not body: continue

                match = re.search(r'(.*?)\(Block 3\)(.*)', body, re.DOTALL)
                if not match: 
                    parts = body.split('\n\n')
                    if len(parts) > 1:
                        body_prefix = "\n\n".join(parts[:-1])
                        original_ending = parts[-1]
                    else:
                        final_output += f"{header}\n{body}\n\n"; continue
                else:
                    body_prefix = match.group(1).strip()
                    original_ending = match.group(2).strip()

                order = random.choice(DIRECTOR_ORDERS)
                try:
                    res = self.g_client.models.generate_content(
                        model=CONFIG["G_MODEL"],
                        contents=PROMPT_ENDING_DIRECTOR.format(original_ending=original_ending, director_order=order)
                    )
                    new_ending = res.text.strip()
                    self.log_surveillance(f"Python Reshoot ({header})", f"Directive: {order}\nOld: {original_ending}\nNew: {new_ending}")
                except: new_ending = original_ending

                clean_body = body_prefix.replace('(Block 1)', '').replace('(Block 2)', '\n\n').strip()
                final_output += f"{header}\n{clean_body}\n\n{new_ending}\n\n{'-'*30}\n\n"
            
            return final_output if final_output.strip() else draft

        except Exception as e:
            self.log(f"   ⚠️ 修片异常: {e}")
            return draft

    async def process_chunk(self, chunk_text, title):
        self.log_surveillance(f"START PROCESSING: {title}", "")

        # 1. Gemini Draft
        try:
            self.log(f"   🤖 Gemini: 初稿搭建...")
            res_g = self.g_client.models.generate_content(model=CONFIG["G_MODEL"], contents=PROMPT_GEMINI_DRAFT.format(examples=GRITTY_EXAMPLES, content_chunk=chunk_text[:15000]))
            draft = res_g.text
            self.log(f"      {self.get_preview(draft)}") # 【新增】打印预览
            self.log_surveillance("Gemini Draft", draft)
        except Exception as e:
            self.log(f"   ❌ Gemini 失败: {e}")
            return None

        # 2. DeepSeek Critique
        try:
            self.log(f"   🦂 DeepSeek: 毒舌质检...")
            res_d = await self.s_client.chat.completions.create(model=CONFIG["D_MODEL"], messages=[{"role": "user", "content": PROMPT_DEEPSEEK_CRITIC.format(draft=draft)}])
            critique = res_d.choices[0].message.content
            self.log(f"      {self.get_preview(critique)}") # 【新增】打印预览
            self.log_surveillance("DeepSeek Critique", critique)
        except Exception as e:
            critique = "保持更锋利的语感。"
            self.log(f"   ⚠️ DeepSeek 跳过: {e}")

        # 3. GPT-4o Polish
        try:
            self.log(f"   🥊 GPT-4o: 教父润色...")
            res_o = await self.o_client.chat.completions.create(model=CONFIG["O_MODEL"], messages=[{"role": "user", "content": PROMPT_GPT_POLISH.format(draft=draft, critique=critique)}])
            polished = res_o.choices[0].message.content
            self.log(f"      {self.get_preview(polished)}") # 【新增】打印预览
            self.log_surveillance("GPT-4o Polish", polished)
        except Exception as e:
            polished = draft
            self.log(f"   ⚠️ GPT-4o 跳过: {e}")

        # 4. Python Director
        self.log(f"   🎬 Python: 结尾重拍...")
        final = await self.ending_reshoot(polished)
        self.log(f"      {self.get_preview(final)}") # 【新增】打印预览
        self.log_surveillance("Final Output", final)
        
        return final

    async def start(self):
        self.log(f"启动 V72.0 实时监视版 | Session: {self.session_id}")
        
        saved_path = "无文件生成"
        if not all([G_KEY, O_KEY, S_KEY]): self.log("❌ 缺 Key"); return

        try:
            ts = YouTubeTranscriptApi().fetch(CONFIG["VIDEO_ID"], languages=['en', 'zh-Hans']).to_raw_data()
            chunks = self.slice_transcript(ts, self.parse_timestamps(TIMESTAMPS_INPUT))
        except Exception as e: self.log(f"Error: {e}"); return

        async with self.session_scope():
            for i, chunk in enumerate(chunks):
                if self.should_stop: break
                
                safe_title = re.sub(r'[\\/*?:"<>|]', "", chunk['title'])
                self.log(f"\n🎥 [{i+1}/{len(chunks)}] 制作: {safe_title}")
                
                final_script = await self.process_chunk(chunk['text'], safe_title)
                
                if final_script:
                    self.all_scripts_buffer.append(f"### {chunk['title']} ###\n{final_script}\n\n")
                    path = self.save_results()
                    if path: 
                        saved_path = path
                        print(f"   >>> ✅ 已存档")
                else:
                    self.log("   ⚠️ 生成失败")

        self.log(f"\n🏆 全部完成。\n📄 结果文件: {saved_path}\n🕵️ 监控日志: {os.path.join(CONFIG['BASE_PATH'], 'scripts_monitor', f'{self.session_id}_Debug_Log.txt')}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    engine = WarRoomEngine()
    try: asyncio.run(engine.start())
    except KeyboardInterrupt: engine.save_results(); sys.exit(0)