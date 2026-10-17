# -*- coding: utf-8 -*-
"""
Dark Psychology - Channel Configuration
Inherits from base_config and overrides specific settings for the Dark Psychology channel.
Focuses on deep hypnosis, subconscious exploration, and psychological thriller aesthetics.
"""

# 引入底层配置项
# pylint: disable=wildcard-import, unused-wildcard-import
from base_config import *


# =====================================================================
# 1. 频道专属设置 (Channel Specific Configurations)
# =====================================================================

CHANNEL_NAME = "Dark Psychology Insights"

# 核心生成模式设置：顺序读取 CSV
STORY_GENERATE_MODE = "SEQUENCE"

# 工作区及存储路径配置
BASE_WORKSPACE = r"I:\AiVideos\DarkPsychology"
RECORD_CSV_PATH = r"I:\AiVideos\DarkPsychology\record_dark.csv"
LIBRARY_CSV_PATH = r"I:\AiVideos\DarkPsychology\library_dark.csv"

# 复用目标文件夹配置
REUSE_TARGET_FOLDER = r"I:\AiVideos\DarkPsychology\20260323_151247"


# =====================================================================
# 2. 频道专用的 Prompt 覆盖 (Channel Specific Prompts)
# =====================================================================

# 复制一份底层的配置字典，避免污染基础设定
PROMPT_CONFIG = PROMPT_CONFIG.copy()

# 覆盖生成大纲的 Prompt，植入暗黑心理学/催眠师的人设和动态元素
PROMPT_CONFIG["GEMINI_OUTLINE"] = """
    PERSONA: You are a master of dark psychology, a skilled hypnotist, and a storyteller exploring the deep subconscious.
    TASK: Create an 8-paragraph psychological journey outline and extract a bilingual glossary based on the inputs below.
    
    --- STORY SEED ---
    - Core Inspiration: {story}
    - Main Characters: 
      1. Victor: A sophisticated, sharp-dressed psychological guide with a piercing, analytical gaze and a calm, hypnotic voice.
      2. The Shadow Self: A fluid, shifting entity made of subtle shadows and smoke, representing the deep subconscious mind.
      3. Victor's Item of Focus for this episode: {character}
    - Atmospheric Style: {style} (e.g., Neo-noir, high contrast chiaroscuro, psychological thriller vibes)
    
    --- THE BLUEPRINT (CRITICAL STRICT COMPLIANCE) ---
    You MUST completely abandon your default narrative habits (e.g., Do not start with "In the heart of..."). 
    You MUST strictly follow the narrative structure, pacing, and perspective dictated by the following Blueprint, adapting the "sleep" aspects into a "deep hypnotic trance" or "subconscious surrender":
    
    {blueprint}
    
    --- STRUCTURAL RULES ---
    1. The story MUST be exactly 8 paragraphs long, mapping directly to the Blueprint.
    2. LENGTH: Each paragraph outline MUST be highly detailed, approximately 200 to 250 words. Provide rich sensory details focusing on the feeling of mental gravity, ticking clocks, and hypnotic suggestions.
    3. ABSOLUTELY NO gore or extreme violence; the tension must be purely psychological and atmospheric.
    4. GLOSSARY: Extract proper nouns/psychological terms used and provide sophisticated Chinese translations.
    
    --- OUTPUT FORMAT ---
    You MUST output ONLY a valid JSON object. No markdown:
    {{
      "outline": ["para1", "para2", "para3", "para4", "para5", "para6", "para7", "para8"],
      "glossary": {{"English Name": "Chinese Translation"}}
    }}
"""

# 覆盖生成画面的 Prompt，确保输出符合暗黑心理学/新黑色电影的视觉美学
PROMPT_CONFIG["SCENE_PROMPT_GEMINI"] = """
    PERSONA: Cinematic visual director specializing in neo-noir and psychological thrillers.
    TASK: Output ONLY the final English image prompt string describing a beautiful, tense, yet static scene based on the text.
    
    --- VISUAL FRAMEWORK ---
    - AESTHETIC ANCHOR: {anchor} (Ensure elements of chiaroscuro, cinematic low-key lighting, and psychological depth)
    
    --- CORE CHARACTERS (STRICT COMPLIANCE) ---
    You MUST explicitly include the following character descriptions in the image prompt, seamlessly integrating them into the scene:
    1. Victor: A sophisticated man in a tailored dark suit, with a piercing, analytical gaze, standing in the shadows.
    2. Focal Item: Holding or observing {character}
    3. The Shadow: Subtle, stylized smoke or geometric shadows stretching across the environment, symbolizing the subconscious.
    
    --- SCRIPT SEGMENT (READ CAREFULLY) ---
    {text}
    
    --- RULES ---
    1. DYNAMIC CAMERA SELECTION: Analyze the SCRIPT SEGMENT's psychological tension. You MUST select the SINGLE most appropriate camera shot from this exact list:
       [Extreme Close-up, Medium Shot, Cinematic Wide Shot, Over-the-shoulder Shot, Low-angle Hero Shot, Bird's-eye View, Macro Bokeh Shot, Dutch Angle].
    2. START FORMAT: Your output MUST start EXACTLY with your chosen camera angle (e.g., "Dutch Angle of..." or "Extreme Close-up of..."). DO NOT default to Wide Shot.
    3. INTEGRATION: Describe the specific environment from the text, ensuring Victor and the shadow elements are positioned effectively.
    4. You MUST append exactly [{anchor}] at the very end of your output.
    5. DO NOT use markdown. Output ONLY the prompt string.
"""

