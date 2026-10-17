# -*- coding: utf-8 -*-
"""
WarRoom Engine V80.0 - Deep Sleep Edition (Luna Drift Custom)

【逻辑分层】
1. 配置层 (CONFIG): 管理 API Key、路径、模型参数。
2. 提示词层 (PROMPTS): 注入助眠心理学逻辑（低信息、高画面、去冲突）。
3. 引擎层 (ENGINE): 
    - Gemini: 负责全量长文本提取及初步“助眠化”重写。
    - OpenAI: 负责最终的“语言平滑度”与“感官降噪”润色。
4. 调度层 (MAIN): 串联全流程，分段处理，实时存档。
"""

import os
import asyncio
import re
import sys
import random
from datetime import datetime
from google import genai
from openai import OpenAI

# ==========================================
# 1. 配置中心 (请设置环境变量)
# ==========================================
CONFIG = {
    "BASE_PATH": "D:/AIGen/Output/SleepStories",
    "VIDEO_ID": "rDdoUbCFn24",  # Diary of a CEO 目标 ID
    "G_MODEL": "gemini-1.5-pro",
    "O_MODEL": "gpt-4o",
    "TARGET_DURATION_MINS": 45,
    "LANGUAGE": "English"
}

# API KEYS
G_KEY = os.getenv("GEMINI_API_KEY")
O_KEY = os.getenv("OPENAI_API_KEY")

# ==========================================
# 2. 助眠文案提示词 (核心资产)
# ==========================================

# Step 1: Gemini 提取与初稿 (负责内容深度)
PROMPT_SLEEP_ARCHITECT = """You are a sleep storyteller. 
Your task: Rewrite the following transcript into a 45-minute sleep-inducing script.

[Current Content]: {content_chunk}

[Strict Guidelines]:
1. **Low Information Density**: Remove all sharp arguments, data, or intense debates. Focus on the 'wisdom' and 'philosophy'.
2. **Atmospheric Descriptions**: Turn concepts into sensory scenes (e.g., instead of 'discipline', describe 'the quiet focus of a morning forest').
3. **Pacing**: Use long, flowing sentences. No exclamation marks. No urgency.
4. **Structure**: Each section must flow into the next like a slow river.

Output in {language}. Return a long-form narrative, not a summary."""

# Step 2: OpenAI 润色 (负责感官丝滑度)
PROMPT_SLEEP_POLISHER = """You are a professional ASMR and Sleep Script editor. 
Polish the text below to make it "acoustically soft" and "mentally relaxing".

[Text to Polish]: {draft}

[Directives]:
1. **Word Choice**: Use soft-sounding words (e.g., 'gentle', 'slowly', 'whisper', 'drifting').
2. **Grammar**: Simplify complex grammar that might cause the brain to work too hard.
3. **Breathing Pauses**: Insert '[...]' at natural resting points to indicate a 3-second pause for the narrator.
4. **Tone**: Monotonous yet warm. No high peaks in storytelling.

**Only output the polished script. No introductory text.**"""

# ==========================================
# 3. 核心引擎函数
# ==========================================

class SleepEngine:
    """处理视频内容并生成助眠文案的核心引擎"""

    def __init__(self):
        self.g_client = genai.Client(api_key=G_KEY)
        self.o_client = OpenAI(api_key=O_KEY)
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self._setup_workspace()
        self.final_script_buffer = []

    def _setup_workspace(self):
        """初始化输出目录"""
        os.makedirs(CONFIG["BASE_PATH"], exist_ok=True)
        print(f"[INIT] 工作空间已就绪: {CONFIG['BASE_PATH']}")

    async def get_gemini_draft(self, chunk_text):
        """调用 Gemini 进行长文本提取与内容重构"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 Gemini: 正在重构助眠骨架...")
        try:
            response = self.g_client.models.generate_content(
                model=CONFIG["G_MODEL"],
                contents=PROMPT_SLEEP_ARCHITECT.format(
                    content_chunk=chunk_text[:30000],  # 确保不超限
                    language=CONFIG["LANGUAGE"]
                )
            )
            return response.text
        except Exception as e:
            print(f"[ERROR] Gemini 任务失败: {e}")
            return None

    async def get_openai_polish(self, draft):
        """调用 OpenAI 进行最终的语言降噪与润色"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎭 OpenAI: 正在进行感官丝滑润色...")
        try:
            response = self.o_client.chat.completions.create(
                model=CONFIG["O_MODEL"],
                messages=[{"role": "user", "content": PROMPT_SLEEP_POLISHER.format(draft=draft)}]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[ERROR] OpenAI 任务失败: {e}")
            return draft  # 失败则保留原稿

    def save_checkpoint(self, chunk_index, content):
        """实时存档，防止程序崩溃丢失数据"""
        file_path = os.path.join(CONFIG["BASE_PATH"], f"{self.session_id}_Part_{chunk_index}.txt")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f" >>> ✅ Part {chunk_index} 已实时存档")
        except Exception as e:
            print(f"[ERROR] 存档失败: {e}")

    async def run(self, transcript_segments):
        """主执行流程"""
        print(f"--- 启动 V80.0 深度睡眠引擎 | 语言: {CONFIG['LANGUAGE']} ---")
        
        for i, segment in enumerate(transcript_segments):
            # 1. Gemini 构建初步文案
            draft = await self.get_gemini_draft(segment)
            if not draft: continue
            
            # 2. OpenAI 润色
            polished_text = await self.get_openai_polish(draft)
            
            # 3. 收集并存储
            self.final_script_buffer.append(polished_text)
            self.save_checkpoint(i+1, polished_text)
            
            # 礼貌延迟，防止 API 限流
            await asyncio.sleep(2)

        # 4. 合并最终文件
        final_file = os.path.join(CONFIG["BASE_PATH"], f"{self.session_id}_TOTAL_45MIN.txt")
        with open(final_file, "w", encoding="utf-8") as f:
            f.write("\n\n--- NEXT CHAPTER ---\n\n".join(self.final_script_buffer))
        print(f"\n🏆 任务圆满完成！最终文案: {final_file}")

# ==========================================
# 4. 数据预处理与主函数
# ==========================================

def mock_get_transcript():
    """此处应集成 youtube_transcript_api 逻辑。为了演示，模拟分段内容"""
    # 实际应用中，您可以用您 V73 里的 slice_transcript 函数处理真实数据
    return ["Part 1: About being indistractable...", "Part 2: Deep willpower techniques..."]

async def main():
    """主程序入口"""
    engine = SleepEngine()
    
    # 获取字幕 (此处建议复用您原有的 YouTube 提取逻辑)
    # segments = get_real_transcript(CONFIG["VIDEO_ID"])
    segments = mock_get_transcript() 
    
    await engine.run(segments)

if __name__ == "__main__":
    asyncio.run(main())