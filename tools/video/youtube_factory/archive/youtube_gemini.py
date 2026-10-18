# -*- coding: utf-8 -*-
"""
WarRoom Engine V73.0 - 沉默杀手版 (The Silent Assassin)

【核心逻辑】
1. 回归 V65 架构：Gemini 独角戏，确保“粗粝感”和“三段式结构”。
2. 禁言模式：后期修片 Prompt 极度严厉，禁止 AI 输出任何“明白”、“方案如下”等废话。
3. 实时存档：保留 V70 的防弹存档机制，跑一条存一条。
"""

import os
import asyncio
import re
import sys
import signal
import random
from datetime import datetime
from contextlib import asynccontextmanager

from youtube_transcript_api import YouTubeTranscriptApi
from google import genai

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
# 1. API 配置 (回归单核 Gemini)
# ==========================================
G_KEY = os.getenv("GEMINI_API_KEY")

CONFIG = {
    "BASE_PATH": "D:/AIGen/Output",
    "VIDEO_ID": "rDdoUbCFn24", 
    "G_MODEL": "gemini-1.5-pro", 
    "MAX_RETRIES": 3,
    "PASS_SCORE": 85 
}

# ==========================================
# 2. 范文库 (V62/V65 经典款)
# ==========================================
CINEMATIC_EXAMPLES = """
【满分范文 - Option A (视觉流)】
(Block 1: 特写镜头)
我们打开邮箱，看了一眼标题，然后迅速关掉。手机震动了一下，我们拿起来，滑开，却忘了原本要干什么。
(Block 2: 心理旁白)
我们不是忙，是不敢。不敢面对那封可能带来麻烦的邮件，不敢结束这个能暂时逃避现实的短视频。我们在用手脚的忙碌，掩盖心里的恐惧。
(Block 3: 结尾)
盯着那封邮件。直到恐惧消失。

【满分范文 - Option B (节奏流)】
(Block 1: 情绪断奏)
你不是在等状态。
你是在等一个“不会失败”的保证。
所以你迟迟不肯动笔。
(Block 2: 节奏推进)
只要不开始，
你就永远拥有“我本可以做得完美”的幻觉。
这是一种最隐蔽的贪婪。
(Block 3: 结尾)
写一句废话。烂开始，也是开始。

【满分范文 - Option C (洞察流)】
(Block 1: 现象重构)
我们把日程表排满，会议、健身、学习。看起来很上进，但这其实是另一种形式的懒惰。
(Block 2: 深度归因)
因为“瞎忙”很简单，只需要像机器一样执行。而“思考”很难，因为必须面对取舍的痛苦。我们用战术上的勤奋，成功掩盖了战略上的苍白。
(Block 3: 结尾)
敢给自己留一小时空白吗？世界不会因为你停下就塌了。
"""

# ==========================================
# 3. 提示词 (沉默指令)
# ==========================================

# Step 1: 结构暴君
PROMPT_STRUCTURAL_WRITER = """你是一个严谨的电影编剧。
请模仿【满分范文】的**三段式结构**，创作 3 个变体。

【学习对象】：{examples}
【当前素材】：{content_chunk}

【核心指令】：
1. **必须保留标签**：每个 Option 必须包含 (Block 1), (Block 2), (Block 3)。
2. **Block 1 (揭穿)**：用画面或短句，直接揭穿误区。
3. **Block 2 (归因)**：深度剖析心理机制。
4. **Block 3 (暂存)**：先写一个结尾。

【输出格式】：
### Option A ###
(Block 1) ...
(Block 2) ...
(Block 3) ...

### Option B ###
(同上)

### Option C ###
(同上)

输出纯文本。"""

# Step 2: 沉默杀手 (只输出结果)
PROMPT_ENDING_DIRECTOR = """你是一个文字编辑器。
请根据指令重写这段结尾。

【原结尾】："{original_ending}"
【指令】：**{director_order}**

【绝对禁令】：
1. **禁止对话**：不要说“明白”、“方案如下”、“我是导演”。
2. **禁止选项**：不要列出“方案A、方案B”，**只给我这一个最终结果**。
3. **禁止解释**：直接输出重写后的句子。

**只输出重写后的那一行字！**"""

DIRECTOR_ORDERS = [
    "把它改成一个**具体的物理动作**（如：扔掉手机，关上门）。",
    "用一个**极短的反直觉短句**。",
    "用一个**冷酷的二选一**。",
    "用**时间紧迫感**收尾（如：就现在）。"
]

class WarRoomEngine:
    def __init__(self):
        self.g_client = genai.Client(api_key=G_KEY)
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self._ensure_dirs()
        self.all_scripts_buffer = []
        self.should_stop = False
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        print("\n🛑 收到中止信号 (Ctrl+C)！正在停止...")
        self.should_stop = True

    def _ensure_dirs(self):
        for d in ["scripts_silent", "raw"]: 
            os.makedirs(os.path.join(CONFIG["BASE_PATH"], d), exist_ok=True)

    def log(self, msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def save_results(self):
        if not self.all_scripts_buffer: return None
        full_path = os.path.join(CONFIG["BASE_PATH"], "scripts_silent", f"{self.session_id}_Final.txt")
        try:
            with open(full_path, "w", encoding="utf-8") as f: 
                f.writelines(self.all_scripts_buffer)
        except Exception as e:
            self.log(f"❌ 存档失败: {e}")
            return None
        return full_path

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

    # 4. 后期导演修片 (修复戏精问题)
    def clean_director_output(self, text):
        # 如果AI还是输出了 "方案一：xxx"，强制提取最后一部分
        lines = text.strip().split('\n')
        # 取最后一行非空行，通常是结果
        last_line = lines[-1].strip()
        # 去掉常见的戏精前缀
        last_line = re.sub(r'^(方案.|结尾|修改后|Output|Result)[:：]\s*', '', last_line)
        return last_line

    async def ending_reshoot(self, draft):
        if not draft: return ""
        try:
            # 宽松分割 Option
            options = re.split(r'(### Option [A-C] ###|Option [A-C])', draft)
            if len(options) < 2: return draft

            final_output = ""
            for i in range(1, len(options), 2):
                header = options[i].strip()
                body = options[i+1].strip()
                if not body: continue

                # 提取 Block 3
                match = re.search(r'(.*?)\(Block 3\)(.*)', body, re.DOTALL)
                if not match: 
                    # 兜底：取最后一段
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
                    # 【核心清洗】
                    new_ending = self.clean_director_output(res.text)
                except: new_ending = original_ending

                clean_body = body_prefix.replace('(Block 1)', '').replace('(Block 2)', '\n\n').strip()
                final_output += f"{header}\n{clean_body}\n\n{new_ending}\n\n{'-'*30}\n\n"
            
            return final_output if final_output.strip() else draft

        except Exception as e:
            self.log(f"   ⚠️ 修片异常: {e}，保留原文")
            return draft

    # 核心工作流
    async def process_chunk(self, chunk_text):
        # 1. Gemini Draft
        try:
            self.log("   🤖 Gemini: 搭建骨架...")
            res_g = self.g_client.models.generate_content(model=CONFIG["G_MODEL"], contents=PROMPT_STRUCTURAL_WRITER.format(examples=CINEMATIC_EXAMPLES, content_chunk=chunk_text[:15000]))
            draft = res_g.text
        except: return None

        # 2. Python Director (Reshoot)
        self.log("   🎬 Python: 沉默修片...")
        final = await self.ending_reshoot(draft)
        return final

    async def start(self):
        self.log(f"启动 V73.0 沉默杀手版 | Session: {self.session_id}")
        saved_path = "无文件生成"
        if not G_KEY: self.log("❌ 缺 Key"); return

        try:
            ts = YouTubeTranscriptApi().fetch(CONFIG["VIDEO_ID"], languages=['en', 'zh-Hans']).to_raw_data()
            chunks = self.slice_transcript(ts, self.parse_timestamps(TIMESTAMPS_INPUT))
        except Exception as e: self.log(f"Error: {e}"); return

        for i, chunk in enumerate(chunks):
            if self.should_stop: break
            
            safe_title = re.sub(r'[\\/*?:"<>|]', "", chunk['title'])
            self.log(f"\n🎥 [{i+1}/{len(chunks)}] 制作: {safe_title}")
            
            final_script = await self.process_chunk(chunk['text'])
            
            if final_script:
                self.all_scripts_buffer.append(f"### {chunk['title']} ###\n{final_script}\n\n")
                path = self.save_results()
                if path: 
                    saved_path = path
                    print(f"   >>> ✅ 已存档")
            else:
                self.log("   ⚠️ 生成失败")

        self.log(f"\n🏆 全部完成。最终文件: {saved_path}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    engine = WarRoomEngine()
    try: asyncio.run(engine.start())
    except KeyboardInterrupt: engine.save_results(); sys.exit(0)