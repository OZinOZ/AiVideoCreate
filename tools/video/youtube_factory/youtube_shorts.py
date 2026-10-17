# -*- coding: utf-8 -*-
"""
WarRoom Engine V65.0 - 结构暴君 + 后期导演版
(The Ironclad Director)

【核心逻辑】
1. 结构暴君 (Step 1)：使用 V62 的高标准范文，强制要求 (Block 1/2/3) 标签，确保逻辑三段式不丢失。
2. 精准手术 (Step 2)：Python 自动识别 (Block 3)，只对结尾进行“随机化重写”。
3. 绝对品控：既有深度的逻辑归因，又有不重复的动作结尾。
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

# 配置
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
# 3. 结构化范文库 (回归 V62 高标准)
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
# 4. 提示词 (双阶段)
# ==========================================

# Step 1: 结构暴君 (保证逻辑三段式)
PROMPTS = {
    "P1_STRUCTURAL_WRITER": """你是一个严谨的电影编剧。
    请模仿【满分范文】的**三段式结构**，创作 3 个变体。

    【学习对象 - 满分范文 (必须保留 Block 1/2/3 标签)】：
    {examples}

    【当前素材】：
    {content_chunk}

    【核心指令】：
    1. **必须保留标签**：每个 Option 必须包含 (Block 1), (Block 2), (Block 3)。
    2. **Block 1 (揭穿)**：用画面或短句，直接揭穿误区。
    3. **Block 2 (归因)**：深度剖析心理机制 (恐惧/逃避/完美主义)。
    4. **Block 3 (暂存)**：先写一个结尾，哪怕老套也没关系（后面会改）。

    【输出格式】：
    ### Option A ###
    (Block 1) ...
    (Block 2) ...
    (Block 3) ...

    ### Option B ###
    (同上)

    ### Option C ###
    (同上)

    输出纯文本。""",

    # Step 2: 导演修片 (只改 Block 3)
    "P2_ENDING_DIRECTOR": """你是一个极简主义导演。
    我要重拍这个结尾。原来的太说教了。
    
    【原结尾】：
    "{original_ending}"
    
    【导演指令】：
    **{director_order}**
    
    请输出**重写后的 Block 3**。不要带括号，直接给内容。"""
}

# 导演指令库 (确保结尾不重样)
DIRECTOR_ORDERS = [
    "给我一个**具体的物理动作**。例如：'把手机扔远点'，'关上电脑'，'深呼吸'。",
    "用一个**反直觉的短句**。例如：'停下才是最快的'，'烂开始也是开始'。",
    "用一个**冷酷的二选一**。例如：'要么忍受无聊，要么忍受平庸'。",
    "用**时间紧迫感**收尾。例如：'就现在。这一分钟。'。",
    "用**极简的否定句**。例如：'别想了。去做。'。"
]

class WarRoomEngine:
    def __init__(self):
        self.g_client = genai.Client(api_key=G_KEY)
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
        for d in ["scripts_ironclad", "raw"]: 
            os.makedirs(os.path.join(CONFIG["BASE_PATH"], d), exist_ok=True)

    def log(self, msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def save_results(self):
        if not self.all_scripts_buffer: return
        full_path = os.path.join(CONFIG["BASE_PATH"], "scripts_ironclad", f"{self.session_id}_Final.txt")
        try:
            with open(full_path, "w", encoding="utf-8") as f: f.writelines(self.all_scripts_buffer)
            self.log(f"\n💾 [已保存] {full_path}")
        except: pass

    @asynccontextmanager
    async def session_scope(self):
        try: yield
        finally: await self.s_client.close()

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

    # 核心逻辑：结构解析 + 后期修片
    async def post_production(self, draft):
        # 1. 拆分 Option
        options = re.split(r'(### Option [A-C] ###)', draft)
        final_output = ""
        
        for i in range(1, len(options), 2):
            header = options[i]
            body = options[i+1].strip()
            
            # 2. 提取 Block 3
            # 正则匹配 (Block 3) 及其后的内容
            match = re.search(r'(.*?)\(Block 3\)(.*)', body, re.DOTALL)
            
            if not match:
                # 如果 AI 没按格式写，直接跳过修片，保留原样（防止报错）
                final_output += f"{header}\n{body}\n\n"
                continue

            body_prefix = match.group(1).strip() # Block 1 + Block 2
            original_ending = match.group(2).strip()
            
            # 3. 随机抽取导演指令
            order = random.choice(DIRECTOR_ORDERS)
            
            # 4. 调用 Gemini 重写 Block 3
            try:
                res = self.g_client.models.generate_content(
                    model=CONFIG["G_MODEL"],
                    contents=PROMPTS["P2_ENDING_DIRECTOR"].format(
                        original_ending=original_ending,
                        director_order=order
                    )
                )
                new_ending = res.text.strip()
                self.log(f"   🎬 [修片] 指令: {order[:10]}... -> 完成")
            except:
                new_ending = original_ending # 失败保底

            # 5. 清洗标签并组装
            # 去掉 (Block 1) (Block 2) 标签，只留换行，让阅读更流畅
            clean_body = body_prefix.replace('(Block 1)', '').replace('(Block 2)', '\n\n').strip()
            
            final_output += f"{header}\n{clean_body}\n\n{new_ending}\n\n{'-'*30}\n\n"
            
        return final_output

    async def start(self):
        self.log(f"启动 V65.0 结构暴君 + 后期导演版 | Session: {self.session_id}")
        try:
            ts = YouTubeTranscriptApi().fetch(CONFIG["VIDEO_ID"], languages=['en', 'zh-Hans']).to_raw_data()
            chunks = self.slice_transcript(ts, self.parse_timestamps(TIMESTAMPS_INPUT))
        except Exception as e: self.log(f"Error: {e}"); return

        async with self.session_scope():
            for i, chunk in enumerate(chunks):
                if self.should_stop: break
                
                safe_title = re.sub(r'[\\/*?:"<>|]', "", chunk['title'])
                self.log(f"\n🎥 [{i+1}/{len(chunks)}] 制作: {safe_title}")
                
                # Step 1: 结构暴君 (强制三段式)
                try:
                    prompt = PROMPTS["P1_STRUCTURAL_WRITER"].format(
                        examples=CINEMATIC_EXAMPLES,
                        content_chunk=chunk['text'][:15000]
                    )
                    res_g = self.g_client.models.generate_content(model=CONFIG["G_MODEL"], contents=prompt)
                    draft = res_g.text
                except: continue

                # Step 2: 后期修片 (只修 Block 3)
                final_script = await self.post_production(draft)
                
                self.all_scripts_buffer.append(f"### {chunk['title']} ###\n{final_script}\n\n")
                print(f"   >>> 完成: 3 个变体已生成并修片。")

        self.save_results()

if __name__ == "__main__":
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    if not all([G_KEY, O_KEY, S_KEY]):
        print("❌ 缺 Key")
    else:
        engine = WarRoomEngine()
        try: asyncio.run(engine.start())
        except KeyboardInterrupt: engine.save_results(); sys.exit(0)