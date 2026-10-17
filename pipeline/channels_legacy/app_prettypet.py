# -*- coding: utf-8 -*-
"""
Pet & Pretty - Channel Configuration
Inherits from base_config and overrides specific settings for the Elira & Lumi adventure.
"""

from base_config import *

# 1. 频道专属设置
CHANNEL_NAME = "Dream Pet Girl Journal" 
CHANNEL_NAME_CN = "梦境少女萌宠日记" 


ONLY_GENERATE_SCRIPT = True
ONLY_GENERATE_IMAGE = False

# REUSE_TASK_ID = "TANKTAIL_20260329040447"
REUSE_GEMINI_OUTLINE = False
REUSE_OPENAI_SCRIPT = False
REUSE_DEEPSEEK_SCRIPT = False
REUSE_IMAGE_PROMPT = False
REUSE_TTS = False
REUSE_IMAGE = False
REUSE_VIDEO = False

BASE_WORKSPACE = r"I:\AiVideos\PrettyPet"
RECORD_CSV_PATH = r"I:\AiVideos\PrettyPet\record.csv"
LIBRARY_CSV_PATH = r"I:\AiVideos\PrettyPet\library.csv"

FIX_CHARACTERS = True
HUMAN_CHARACTER = {
    "Elira": "A young woman with long, flowing silver hair, and a small luminescent star-shaped mark on her cheek."
}
PET_CHARACTER = {
    "Lumi": "A small, mystical fox made of swirling celestial light and fur that glows like a nebula, trailing stardust as it moves."
}

# 2. 频道专用的 Prompt 覆盖
# 复制一份底层的配置字典，避免污染基础设定
PROMPT_CONFIG = PROMPT_CONFIG.copy()

# 覆盖生成大纲的 Prompt，植入固定的人设和动态的服装变量
# 【Gemini 大纲生成】：引入 {human_info} 和 {pet_info} 占位符，提取规则也改为泛指
PROMPT_CONFIG["GEMINI_OUTLINE"] = """
    PERSONA: You are a master storyteller specializing in lighthearted, healing, and cozy adventure journals featuring the deep companionship between a human and their magical pet.
    TASK: Create a 10-paragraph story outline and extract a bilingual glossary.
    
    --- STORY SEED ---
    - Core Inspiration: {story}
    - Main Characters (STRICT COMPLIANCE): 
      1. Human Protagonist: {human_info}
      2. Pet Companion: {pet_info}
      3. Human's Outfit for this episode: {character}
    - Atmospheric Style: {style}
    
    --- THE BLUEPRINT (STYLE & STRUCTURE MASTER GUIDE) ---
    The following Blueprint dictates the narrative focus, pacing, and vibe. You MUST filter the "Core Subject Matter" entirely through the lens of this Blueprint.
    
    {blueprint}
    
    --- STRUCTURAL RULES ---
    1. VIBE & TONE: Focus on cheerful exploration, heartwarming companionship, and healing moments. ABSOLUTELY NO violence, dark conflicts, or high-stress situations.
    2. EXACT LENGTH: The story MUST be exactly 10 paragraphs long.
    3. PARAGRAPH DETAIL: Each paragraph outline should be approx. 150 words, providing rich physical and sensory context suitable for visually stunning and cinematic generation.
    4. HARD STOP: Stop generating immediately after the JSON object is complete.
    
    --- GLOSSARY RULES (CRITICAL FOR SAFE IMAGE GENERATION) ---
    1. "char_body_and_apparel": Describe the human protagonist's body, hair, and clothing (~30 words). Focus ONLY on age, gender, body type, hair, and realistic clothing or shoes based on "{character}". STRICTLY PROHIBITED: Do not include any facial features, eye color, props, personality, or background in this field.
    2. "char_facial_details": Describe the human protagonist's face (~20 words). Focus ONLY on facial structure, eye color, complexion, makeup, specific facial marks, and a cheerful or serene expression. STRICTLY PROHIBITED: Do not include hair, clothing, or body descriptions in this field.
    3. "names": Translate ALL proper nouns (including character and pet names) from the story outline into poetic, adventurous Chinese. Keep translations short.
    
    --- OUTPUT FORMAT (STRICT JSON) ---
    You MUST output ONLY a valid JSON object. Follow this exact structure:
    {{
        "outline": [
            "para1 text (150 words)...", 
            "para2 text...", 
            "...", 
            "para10 text..."
        ],
        "glossary": {{
            "char_body_and_apparel": "Description of body, hair, and clothing only...",
            "char_facial_details": "Description of facial features and expression only...",
            "names": {{
                "First Proper Noun": "Poetic Chinese Translation",
                "...": "Translate ALL proper nouns..."
            }}
        }}
    }}
    """

# 【OpenAI 细节扩写】：引入防幻觉硬控，并增加 CHARACTER INTEGRATION RULES 强制特征融合
PROMPT_CONFIG["OPENAI_EXPAND"] = """
    PERSONA: You are a master literary fiction writer specializing in cheerful, immersive, and heartwarming adventure journals. 
    TASK: Expand the provided SINGLE story outline block into THREE distinct, flowing scene paragraphs focusing on companionship and discovery. For each expanded paragraph, you will also extract precise visual metadata for image generation.
    
    --- OUTLINE BLOCK ---
    {outline}

    --- PROTAGONIST IDENTITY & ENTITY LOCK (CRITICAL STRICT COMPLIANCE) ---
    The ONLY characters allowed in this story are:
    1. The Human: {human_info}
    2. The Pet: {pet_info}
    
    FATAL ERROR PREVENTION: 
    - DO NOT mix up their identities. The pet is the animal; the human is the person.
    - ABSOLUTELY NO NEW CHARACTERS. Do not invent any friends or other animals.
    - The adventure is strictly a solo journey between the human and the pet.
    
    --- CHARACTER INTEGRATION RULES ---
    You MUST cleverly weave the specific visual traits of the characters naturally into their actions, the environment's lighting, and their physical interactions. For example, if the human has a glowing mark or silver hair, show how it catches the light; if the pet trails stardust, show the physical effect it leaves on the environment. Do not just list their traits; show them interacting with the world.

    --- LITERARY STYLE GUIDELINES (STRICT COMPLIANCE) ---
    1. START IMMEDIATELY: Start directly with the action, sound, or physical detail of the adventure. Do not use introductory filler phrases.
    2. SENSORY PHYSICS & COMPANIONSHIP: Describe exact physical interactions, vibrant environments, and the warm interactions between the protagonist and their companion.
    3. PACING & CONTINUITY: Write in a lighthearted, observant, and healing rhythm suitable for a cozy travel vlog/journal. The three segments must flow seamlessly from one to the next, forming a cohesive 450-word scene.
    
    --- DATA FIELD INSTRUCTIONS ---
    You must populate the required structured output fields as follows:
    - narrative_text: Output strictly the story text (~150 words per segment). No meta-commentary, conversational closings, or emojis.
    - scene_desc: Focus ONLY on the physical environment, weather, and lighting.
    - emotion_desc: Focus ONLY on the atmosphere or internal feeling (e.g., cheerful, curious, serene).
    - action_desc: Focus ONLY on what the protagonist is physically doing or their posture.
    - camera_shot: Select the most logical camera angle for the action_desc to avoid visual contradictions.
    """


# 【中文散文重写】：褪去“催眠/睡意”，注入“灵动/阳光/治愈”，打造高质量的纪录片旁白感
PROMPT_CONFIG["DEEPSEEK_REWRITE"] = """
    PERSONA: 你是一位顶级的中文翻译家兼治愈系探险日志作家。

    TASK: 请将下方这段英文探险故事，翻译成语流轻快、充满生机且极具画面感的中文散文（Vlog旁白风格）。

    【核心翻译原则】:
    1. 【灵动与治愈】：请用轻快、温暖且富有文学美感的语言，来传达原文中的奇遇、陪伴感和自然之美。让文字自带阳光、微风和治愈的力量，呈现出充满好奇心的探险白描。
    2. 【文风纯净】：保持文笔的清新与安全感，自然地渲染欢快的氛围。语言需充满人文温度，摒弃任何生硬的学术腔调、恐怖或突兀的戏剧性冲突。
    3. 【节奏明快】：摒弃短碎的机翻感。请多运用生动的动作描写与感官词汇，将句子翻译得如同一场轻松的徒步旅行般连贯、愉悦、引人入胜。
    4. 【严格格式】：原文是由 "---" 隔开的多个文本块。你必须输出完全相同数量的中文文本块，并同样使用 "---" 隔开！绝对不能合并或删除段落，不输出任何前言后语。

    [GLOSSARY FOR REFERENCE]
    {glossary}

    --- ENGLISH TEXT TO TRANSLATE ---
    {english_text}
"""
