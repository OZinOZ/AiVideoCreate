# -*- coding: utf-8 -*-
"""
Content OS - Base Configuration Template
Contains standard blueprints, schemas, default paths, and base prompts.
All channel configs will inherit from this file.
"""

from pydantic import BaseModel, Field
import os

# =====================================================================
# 1. DEFAULT PIPELINE FLAGS & PATHS
# =====================================================================
USE_IMAGE_TEMPLATE = True

SCRIPT_REWRITE_EN = False
SCRIPT_REWRITE_CN = False

FORCE_PAUSE = True
PAUSE_DURATION = "500ms"

ONLY_GENERATE_SCRIPT = False
ONLY_GENERATE_IMAGE = False

SKIP_QA_GUARDRAIL_EN = True
SKIP_QA_GUARDRAIL_CN = False

GENERATE_YOUTUBE_ASSETS = True
AUTO_UPLOAD_TO_YOUTUBE = False 

REUSE_GEMINI_OUTLINE = False
REUSE_OPENAI_SCRIPT = False
REUSE_DEEPSEEK_SCRIPT = False
REUSE_IMAGE_PROMPT = False
REUSE_TTS = False
REUSE_IMAGE = False
REUSE_VIDEO = False


#REUSE_TASK_ID = "20260326_142811"
#REUSE_TARGET_FOLDER = "D:/AIGen/MasterFactory_Dual/20260322_180542"


BASE_WORKSPACE = "E:/OliverAI"
RECORD_CSV_PATH = os.path.join(BASE_WORKSPACE, "default", "record.csv")
LIBRARY_CSV_PATH = os.path.join(BASE_WORKSPACE, "default", "library.csv")


ASSETS_POOL = {
    "overlays": [
        os.path.join(BASE_WORKSPACE, "assets", "Overlays", "ghibli_dust.mp4"), 
        os.path.join(BASE_WORKSPACE, "assets", "Overlays", "light_rays.mp4")
    ],
    "audios": [
        os.path.join(BASE_WORKSPACE, "assets", "Audios", "bird.mp3"),
        os.path.join(BASE_WORKSPACE, "assets", "Audios", "rain.mp3"),
        os.path.join(BASE_WORKSPACE, "assets", "Audios", "forest.mp3"),
        os.path.join(BASE_WORKSPACE, "assets", "Audios", "stream.mp3")
    ]
}

FONT_FOLDER = os.path.join(BASE_WORKSPACE, "assets", "fonts")
FONT_POOL = {
    'EN': [
        'AbrilFatface.ttf',
        'Cinzel-Regular.ttf',
        'CinzelDecorative.ttf',
        'CormorantGaramond.ttf',
        'DMSerifDisplay.ttf',
        'EBGaramond.ttf',
        'LibreBaskerville.ttf',
        'Lora.ttf',
        'Merriweather.ttf',
        'PlayfairDisplay.ttf',
        'Spectral.ttf'
    ],
    'CN': [
        'LXGWWenKai.ttf',
        'MaShanZheng.ttf',
        'NotoSerifSC.ttf',
        'SmileySans.ttf',
        'ZCOOLKuaiLe.ttf',
        'ZCOOLXiaoWei.ttf'
    ]
}


# =====================================================================
# 2. THE BLUEPRINT VAULT (10 种大师级故事结构模板)
# =====================================================================

OUTLINE_BLUEPRINTS = [
    """
    [Blueprint 1: The 'In Media Res' Action Start]
    P1: Do NOT describe the setting first. Start directly with the main character performing a slow, repetitive, hypnotic physical action. Describe the sound and texture.
    P2: Slowly pull the camera back to reveal the peaceful, isolated environment.
    P3-P4: The character notices a very subtle, non-threatening anomaly in their routine. They investigate it slowly.
    P5-P6: The climax is an internal realization or a peaceful observation of nature adapting. Nothing breaks or goes wrong.
    P7-P8: The character returns to their initial repetitive action, slower now, their movements blending with the environment.
    P9-P10: A final lingering moment of absolute stillness before they naturally fall asleep, as the scene slowly fades to quiet.
    """,
    """
    [Blueprint 2: The Micro-to-Macro Sensory Pan]
    P1: Start by describing something incredibly tiny in extreme close-up (a single drop of dew, a dust mote).
    P2: Expand the view to show how this tiny element fits into the main character's peaceful sanctuary.
    P3-P4: The character goes on a short, languid walk or journey to gather a specific, mundane item.
    P5-P6: A moment of quiet awe. They witness a beautiful, natural phenomenon.
    P7-P8: The character rests, feeling the deep comforting connection between the micro and macro worlds.
    P9-P10: The perspective zooms back into a final gentle micro-detail, ending with the slow fading of light into peaceful sleep.
    """,
    """
    [Blueprint 3: The 'Sound First' Approach]
    P1: Strip away all visual descriptions. Describe only what can be heard in the absolute dark.
    P2: As a soft light source is introduced by the character, the visual world slowly paints itself around the sounds.
    P3-P4: A gentle task requires the character to follow a specific sound through their environment.
    P5-P6: The source of the sound is found—it is something comforting and ancient.
    P7-P8: The character sits beside the source of the sound, letting its rhythm dictate their slowing breathing.
    P9-P10: The light slowly dims again, leaving only the comforting sound to guide them into a deep, uninterrupted sleep.
    """,
    """
    [Blueprint 4: The 'Object POV' Anchor]
    P1: Frame the opening as if the camera is an inanimate object watching the main character enter the room.
    P2: Describe the character's heavy, tired state through their interaction with this object.
    P3-P4: The character begins a process of unwinding, shedding the layers of their day.
    P5-P6: A quiet moment of reflection where the character simply stares out of a window or into a fire.
    P7-P8: The character's breathing slows and deepens as they settle into comfort near the object.
    P9-P10: The character falls completely asleep, and the perspective lingers on the object standing silent guard over them in the dark.
    """,
    """
    [Blueprint 5: The 'Weather' Dictator]
    P1: Start with a deeply atmospheric description of gentle, enveloping weather (a thick rolling fog, a steady drizzle).
    P2: Introduce the character observing this weather from a place of absolute safety and warmth.
    P3-P4: The character performs cozy, nesting activities to contrast with the weather outside.
    P5-P6: The weather creates a beautiful, isolating effect, cutting the character off from the rest of the world.
    P7-P8: The sound of the weather becomes a lullaby, gently shifting the character's consciousness.
    P9-P10: The character's mind blurs entirely with the rhythm of the rain or wind, fading seamlessly into a deep and restful sleep.
    """,
    """
    [Blueprint 6: The 'Preparation for Rest' Ritual]
    P1: Begin with the character acknowledging that their long work is done. The opening is about the feeling of muscles relaxing.
    P2: Describe a highly specific, sensory-rich ritual the character does every night to transition from work to rest.
    P3-P4: While doing the ritual, the character interacts with a comforting pet or a beloved, silent companion.
    P5-P6: The focus shifts to the dimming of lights—extinguishing candles one by one, or watching the sun finally dip.
    P7-P8: The character settles fully into their resting place, feeling the final weight leave their tired muscles.
    P9-P10: The final descent into sleep, describing the profound physical sensation of sinking into a soft bed as the world goes incredibly quiet.
    """,
    """
    [Blueprint 7: The 'Architectural' Walkthrough]
    P1: Describe the geometry and materials of the character's sanctuary. Focus on the coldness of stone or the warmth of wood.
    P2: The character moves through this architecture, trailing their hand along the walls.
    P3-P4: The journey leads to a hidden, even quieter inner sanctum or a secret garden.
    P5-P6: A moment of profound stillness in this inner sanctum, watching dust settle or water pool.
    P7-P8: The character lies down, feeling the solid, comforting support of the architecture beneath them.
    P9-P10: They seamlessly blend into the quiet geometry of the room, their breathing matching the stillness, until completely asleep.
    """,
    """
    [Blueprint 8: The 'Lost Item' Wander]
    P1: Start with a mild, low-stakes realization that a small, comforting item is misplaced (a favorite bookmark, a smooth stone).
    P2-P4: The character undertakes a slow, wandering search through their peaceful environment, allowing for detailed descriptions.
    P5-P6: The item is found in a place of beautiful repose, triggering a wave of comforting nostalgia.
    P7-P8: Holding the item, the character feels a profound sense of completeness and safety.
    P9-P10: The comforting nostalgia washes over them completely, gently carrying them into a long, uninterrupted sleep.
    """,
    """
    [Blueprint 9: The 'Distant Observer']
    P1: Frame the opening from an extremely wide, distant perspective, looking down at the character's tiny, glowing sanctuary.
    P2: Slowly zoom in through a window, passing through layers of atmosphere, to find the character inside.
    P3-P4: Observe the character engaged in a quiet hobby (reading, knitting) without knowing their thoughts, just watching.
    P5-P6: The character pauses, seemingly feeling the peaceful weight of the night around them.
    P7-P8: The light in the sanctuary dims, the character finally giving in to the deep rest they need.
    P9-P10: The light goes out completely, and the perspective zooms back out to the vast, silent, and protective night sky.
    """,
    """
    [Blueprint 10: The 'Weight Shift']
    P1: Begin by describing the physical sensation of heaviness—gravity pulling on tired limbs, the weight of warm clothing.
    P2: The character sheds this physical weight (taking off boots, unfastening a heavy cloak).
    P3-P4: As the physical weight is removed, a mental lightness takes over. The environment seems to float or soften.
    P5-P6: A sensory experience (a sip of warm broth, the smell of cedar) completely anchors the character in the present moment.
    P7-P8: The character surrenders entirely to gravity, lying down and feeling every point of contact with their resting place.
    P9-P10: Letting the earth or bed fully support their weight, their consciousness drifts away completely into deep sleep.
    """
]

# =====================================================================
# 3. BUSINESS SCHEMA & BASE PROMPTS
# =====================================================================

from pydantic import BaseModel, Field

class SceneSegment(BaseModel):
    narrative_text: str = Field(description="Expanded narrative paragraph, approx 150 words. Pure story text.")
    scene_desc: str = Field(description="Max 10 words describing the environment and lighting for this specific paragraph.")
    emotion_desc: str = Field(description="Max 5 words describing the vibe or atmosphere.")
    action_desc: str = Field(description="Max 5 words describing the protagonist's physical state or movement.")
    # 【新增字段】：让 OpenAI 必须做单选题
    camera_shot: str = Field(description="Choose EXACTLY ONE cinematic camera shot that logically fits the action (Choices: Cinematic Wide Shot, Medium Full Shot, Over-the-shoulder Shot, Close-up, Macro Bokeh Shot, Low-angle Hero Shot, Point of View).")

class ExpandedScene(BaseModel):
    segment_1: SceneSegment
    segment_2: SceneSegment
    segment_3: SceneSegment

class YouTubeMetadata(BaseModel):
    title: str = Field(description="Natural, human-written YouTube title (max 65 chars). Focus on tangible sensory details or mild curiosity.")
    thumbnail_text: str = Field(description="A highly clickable, visual short phrase (3-5 words) for the thumbnail. Do not simply repeat the title.")
    description: str = Field(description="Compelling 2-paragraph description focusing on immersive mood, ending with a soft CTA.")
    tags: list[str] = Field(description="Array of 10-15 highly relevant SEO tags.")

# =====================================================================
# SYSTEM PROMPT CONFIGURATION (工业级防失控高可用版本)
# =====================================================================

PROMPT_CONFIG = {
    "GEMINI_OUTLINE": """
    PERSONA: You are a master storyteller specializing in sleep-inducing, deeply calming bedtime stories.
    TASK: Create a 10-paragraph story outline and extract a bilingual glossary.
    
    --- STORY SEED ---
    - Core Subject Matter: {story}
    
    --- THE BLUEPRINT (STYLE & STRUCTURE MASTER GUIDE) ---
    The following Blueprint dictates the atmospheric style, narrative focus, and pacing. You MUST filter the "Core Subject Matter" entirely through the lens of this Blueprint.
    
    {blueprint}
    
    --- STRUCTURAL RULES ---
    1. SETTING FIDELITY (CRITICAL): Ground the story entirely in the literal, physical reality of the "Core Subject Matter". Derive all sensory ASMR details exclusively from mundane, realistic elements. Do NOT hallucinate cosmic or magical elements.
    2. EXACT LENGTH: The story MUST be exactly 10 paragraphs long.
    3. PARAGRAPH DETAIL: Each paragraph outline should be approx. 150 words, providing rich physical and sensory context.
    4. TONE: ABSOLUTELY NO violence, conflicts, or high-stress situations.
    5. HARD STOP: Stop generating immediately after the JSON object is complete.
    
    --- GLOSSARY RULES ---
    1. "char_body_and_apparel": Describe the protagonist's body and clothing (~30 words). Focus ONLY on age, gender, body type, hair (length/style/color), and realistic clothing (fabrics/colors) or shoes. STRICTLY PROHIBITED: Do not include any facial features, eye color, props, personality, or background in this field.
    2. "char_facial_details": Describe the protagonist's face (~20 words). Focus ONLY on facial structure, eye color, complexion, makeup (if any), and a calm expression. STRICTLY PROHIBITED: Do not include hair, clothing, or body descriptions in this field.
    3. "names": Translate ALL proper nouns from the story outline into poetic Chinese. Keep translations short.
    
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
    """,

    "KIMI_OUTLINE": """
    PERSONA: You are a master storyteller specializing in sleep-inducing, deeply calming bedtime stories.
    TASK: Create a 10-paragraph story outline and extract a bilingual glossary.
    
    --- STORY SEED ---
    - Core Subject Matter: {story}
    
    --- THE BLUEPRINT (STYLE & STRUCTURE MASTER GUIDE) ---
    The following Blueprint dictates the atmospheric style, narrative focus, and pacing. You MUST filter the "Core Subject Matter" entirely through the lens of this Blueprint.
    
    {blueprint}
    
    --- STRUCTURAL RULES ---
    1. SETTING FIDELITY (CRITICAL): Ground the story entirely in the literal, physical reality of the "Core Subject Matter". Derive all sensory ASMR details exclusively from mundane, realistic elements. Do NOT hallucinate cosmic or magical elements.
    2. EXACT LENGTH: The story MUST be exactly 10 paragraphs long.
    3. PARAGRAPH DETAIL: Each paragraph outline should be approx. 150 words, providing rich physical and sensory context.
    4. TONE: ABSOLUTELY NO violence, conflicts, or high-stress situations.
    5. HARD STOP: Stop generating immediately after the JSON object is complete.
    
    --- GLOSSARY RULES ---
    1. "char_body_and_apparel": Describe the protagonist's body and clothing (~30 words). Focus ONLY on age, gender, body type, hair (length/style/color), and realistic clothing (fabrics/colors) or shoes. STRICTLY PROHIBITED: Do not include any facial features, eye color, props, personality, or background in this field.
    2. "char_facial_details": Describe the protagonist's face (~20 words). Focus ONLY on facial structure, eye color, complexion, makeup (if any), and a calm expression. STRICTLY PROHIBITED: Do not include hair, clothing, or body descriptions in this field.
    3. "names": Translate ALL proper nouns from the story outline into poetic Chinese. Keep translations short.
    
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
    """,

    "OPENAI_EXPAND": """
    PERSONA: You are a master literary fiction writer and a high-level ASMR mindfulness guide. You specialize in deeply immersive, hypnotic, and grounded environmental storytelling designed to induce deep relaxation and sleep.
    
    TASK: Expand the provided SINGLE story outline block into THREE distinct, flowing, ultra-slow-paced scene paragraphs. For each expanded paragraph, you will also extract precise visual metadata for image generation.
    
    --- OUTLINE BLOCK ---
    {outline}

    --- PROTAGONIST IDENTITY (STRICT COMPLIANCE) ---
    The main character in this story is EXACTLY as described here:
    {character}
    RULE: Whenever you describe the protagonist's actions, tactile sensations, or appearance, you MUST align completely with this identity. Do not invent a different persona.
    
    --- LITERARY & HYPNOTIC ASMR GUIDELINES (STRICT COMPLIANCE) ---
    1. ZERO RUSHED ACTIONS (THE RULE OF STILLNESS): Do not write rapid or complex physical movements. Focus entirely on static sensations—the feeling of gravity, the weight of fabric, or the slow shifting of light.
    2. COGNITIVE MINIMALISM: At any given moment, the listener should only process ONE sensory focus. Describe exact physical interactions/textures, but do not introduce new elements until the previous one has fully "settled".
    3. BREATH-SYNC RHYTHM: Write in a slow, flowing rhythm that mirrors calm breathing. Use long, rhythmic sentences. Each sentence should feel like one long inhale and exhale.
    4. TEMPORAL SUSPENSION: Avoid clear progression of time. Moments should feel suspended, as if nothing urgent exists in the world. Time dissolves.
    5. SUBTLE REPETITION & SENSORY GROUNDING: Gently reuse similar soothing words (drifting, suspended, melting, warmth, softness, stillness) to create comforting, hypnotic loops. Anchor the text in muted sounds and calming scents.ANTI-LAZY RULE: Do NOT overuse cliché AI metaphors. Vary your descriptive vocabulary for comfort and safety.
    6. NO INTERNAL ANXIETY: The character must exhibit absolute peace. Do not describe any internal struggle, overthinking, or sudden realizations. Start immediately with the tranquil action or physical detail.
    
    --- DATA FIELD INSTRUCTIONS ---
    You must populate the required structured output fields as follows:
    - narrative_text: Output strictly the story text (~150 words per segment). No meta-commentary, conversational closings, or emojis.
    - scene_desc: Focus ONLY on the physical environment, weather, and lighting. Keep it uncluttered (Minimalist Visuals).
    - emotion_desc: Focus ONLY on the atmosphere or internal feeling (must be peaceful/calm).
    - action_desc: Focus ONLY on what the protagonist is physically doing or their posture. Must be static/slow.
    - camera_shot: Select the most logical camera angle for the action_desc to avoid visual contradictions (e.g., do not use Point of View if describing the character's own face).
    """,

    # 【极简唯美版】：去除生硬的负面限制，纯靠正面语感引导的大道至简翻译
    "DEEPSEEK_REWRITE": """
    PERSONA: 你是一位顶级的中文翻译家兼 ASMR 睡眠散文大师。

    TASK: 请将下方这段英文睡眠故事，翻译成语流连绵不断、极具催眠节奏的中文散文。

    【核心翻译原则】:
    1. 【感性与柔和】：请用极度柔软、感性且富有文学美感的语言，来传达原文中的触觉、温度和声音。让文字自带温暖、慵懒的睡意，呈现出纯粹的自然与物理白描。
    2. 【文风纯净】：保持文笔的朴素与安全感，自然地渲染宁静的氛围。语言需充满人文温度，摒弃任何生硬的学术腔调或突兀的戏剧性画面。
    3. 【长句连绵】：摒弃短碎的机翻感。请多运用舒缓的连接词，将句子翻译得如同一泓静水般连贯、悠长、毫无波澜。
    4. 【严格格式】：原文是由 "---" 隔开的多个文本块。你必须输出完全相同数量的中文文本块，并同样使用 "---" 隔开！绝对不能合并或删除段落，不输出任何前言后语。

    [GLOSSARY FOR REFERENCE]
    {glossary}

    --- ENGLISH TEXT TO TRANSLATE ---
    {english_text}
    """,

    # 【全新升级】：保长、扩写、高呼吸感的专业催眠级英文改写 (支持 Batch)
    "REWRITE_PROMPT_EN": """
    PERSONA: You are a master sleep story writer who creates extremely calming, flowing, and beautifully descriptive bedtime narration.

    TASK: Rewrite each text block to be deeply soothing and hypnotic, while STRICTLY MAINTAINING OR INCREASING the original word count.

    CRITICAL RULE (BATCH PROCESSING):
    - The input contains multiple text blocks separated by "---".
    - You MUST return the EXACT same number of rewritten blocks, separated by "---".
    - Do NOT merge, remove, or summarize any blocks.

    STYLE & LENGTH REQUIREMENTS (VERY IMPORTANT):
    - DO NOT SUMMARIZE. The rewritten text MUST be at least as long as the original. Expand on the sensory details to stretch the pacing.
    - Use SOFT, FLOWING sentences. Instead of choppy short sentences, connect ideas with 'and', 'as', or commas to create a continuous, lulling rhythm like gentle waves.
    - Focus heavily on physical micro-sensations (e.g., the warmth of sun, the texture of wool, the soft acoustic thud of wood, the slow drift of dust).
    - Use simple, comforting, yet highly literary and elegant vocabulary.

    SLEEP OPTIMIZATION RULES:
    - Make the text feel safe, predictable, and uneventful. 
    - Reduce active plot progression (less "doing", more "being").
    - Add subtle breathing or relaxation cues (e.g., "slowly", "gently", "drifting").
    - Eliminate any dramatic tension, bright flashes, or sudden noises.

    TONE:
    - Calm, hypnotic, profoundly peaceful.

    OUTPUT:
    Return ONLY the rewritten text blocks, separated by "---". Do not add introductions.

    --- TEXT TO REWRITE ---
    {text}
    """,

    # 【全新升级】：唯美抒情、高呼吸感、专注于微观感官的专业催眠中文改写 (支持 Batch)
    "REWRITE_PROMPT_CN": """
    PERSONA: 你是一位顶级的中文睡眠故事散文大师，擅长创作极其舒缓、如流水般连绵且意境优美的睡前旁白。

    TASK: 重写每一个文本块，使其具有极深沉的安抚感和催眠效果，同时【严格保持或增加】原文的字数。

    CRITICAL RULE (核心批处理规则):
    - 输入包含多个由 "---" 分隔的文本块。
    - 你必须严格返回与原文完全相同数量的改写文本块，并且也用 "---" 分隔。
    - 绝对不能合并、删除或概括任何文本块。

    STYLE & LENGTH REQUIREMENTS (极度重要的文风与长度要求):
    - 严禁缩水与概括！改写后的文本必须至少与原文一样长。请通过扩写微观的感官细节来极大地放慢文本的节奏。
    - 使用【轻柔、连绵的长句】。绝不要写顿挫的短碎句，请多用逗号和连词将意象衔接起来，营造出像微波荡漾般连贯、催眠的语流。
    - 深度聚焦于【微观的物理感官】（例如：阳光的余温、羊毛的粗糙触感、木头发出柔软沉闷的微响、尘埃在空气中的缓慢漂浮）。
    - 使用简单、令人安心，但同时具备【极高文学修辞美感与优雅】的词汇。
    - 字数控制：每段改写请自然流淌至 150-250 字左右即可，写完即止，绝对禁止为了凑字数而生硬地来回重复车轱辘话。

    SLEEP OPTIMIZATION RULES (睡眠优化规则):
    - 让文本听起来绝对安全、可预测且毫无波澜。
    - 减少主动的剧情推进（少写“做了什么”，多写“处于什么状态”）。
    - 加入微妙的呼吸或放松暗示（例如：“缓慢地”、“轻轻地”、“渐渐沉入”）。
    - 彻底消除任何戏剧张力、刺眼的光芒或突兀的声响。

    TONE (语调):
    - 平静、催眠、极度安宁。

    OUTPUT:
    只返回改写后的文本块，并用 "---" 分隔。绝对不要输出任何前言、解释或多余的标点。

    --- 待改写文本 ---
    {text}
    """,

    "SCENE_PROMPT_OSS": """
    TASK: Generate ONE cinematic image prompt in English.

    INPUT:
    - Camera: {camera}
    - Aesthetic Anchor: {anchor}
    - Character: {character}
    - Scene Segment: {text}

    RULES:
    1. START EXACTLY WITH: {camera} of
    2. SCENE CORE: Describe one calm, static moment based on the Scene Segment. (NO aggressive action sequences, NO violence).
    3. CHARACTER: Naturally integrate the Character description into the scene if they are present.
    4. VIBE: Focus heavily on environment, beautiful lighting, texture, and atmosphere.
    5. LENGTH: Keep it between 60-80 words.
    6. FORMAT: You MUST wrap your final output completely inside <prompt> and </prompt> XML tags. OUTPUT ONLY THE XML TAGS AND NOTHING ELSE. DO NOT SAY "Here is the prompt".
    """,

    "SCENE_PROMPT_GEMINI": """
    TASK: Generate ONE cinematic image prompt in English.

    INPUT:
    - Camera: {camera}
    - Aesthetic Anchor: {anchor}
    - Character: {character}
    - Scene Segment: {text}

    RULES:
    1. START EXACTLY WITH: {camera} of
    2. SCENE CORE: Describe one calm, static moment based on the Scene Segment. (NO aggressive action sequences, NO violence).
    3. CHARACTER: Naturally integrate the Character description into the scene if they are present.
    4. VIBE: Focus heavily on environment, beautiful lighting, texture, and atmosphere.
    5. LENGTH: Keep it between 60-80 words.
    6. FORMAT: You MUST wrap your final output completely inside <prompt> and </prompt> XML tags.
    """,

 "YOUTUBE_METADATA": """
    PERSONA: You are a ruthless, data-driven YouTube Growth Hacker and CTR optimization expert, managing a cinematic healing/sleep channel. Your goal is to convert stressed, anxious, and sleep-deprived scrollers into viewers by targeting their exact emotional pain points.
    TASK: Generate highly clickable, SEO-optimized metadata based on the story.

    --- SCRIPT SUMMARY ---
    {script_summary}

    --- CRITICAL RULES (STRICT COMPLIANCE) ---
    1. TITLE (Max 65 chars): MUST use the "Pain-Point + Solution/Vibe" formula. 
       - Examples for structure only: "Fall Asleep in 15 Minutes | Cozy Rain & Guitar", "Stop Overthinking | Quiet Night Story to Calm Your Mind".
       - ANTI-LAZY RULE: DO NOT COPY THESE EXAMPLES EXACTLY. You MUST generate UNIQUE titles based on the specific themes of the {script_summary}.
       - STRICTLY PROHIBITED: Do not use abstract, poetic titles like "Gentle Whispers" or "A Night of Serenity". Be brutally direct.
       
    2. THUMBNAIL TEXT (Max 4 words): This must be a visual hook. Use high-emotion, punchy trigger words designed to stop someone scrolling at 2 AM.
       - Examples for vibe only: "CAN'T SLEEP?", "OVERTHINKING?", "FIND PEACE.", "RELAX YOUR MIND."
       - ANTI-LAZY RULE: DO NOT simply output "CAN'T SLEEP?" every time. Extract the specific psychological pain point from the {script_summary} to create a fresh hook.
       - STRICTLY PROHIBITED: Do not use soft descriptive phrases like "Calm Melodies Await".
       
    3. DESCRIPTION: 
       - Line 1-2 (SEO Priority): Explicitly state the utility using highly searched keywords.
       - Line 3-4: A brief, immersive 1-sentence summary of the actual visual story.
       - Line 5: A soft Call-to-Action (CTA) to subscribe.    4. TAGS: 15 highly targeted SEO tags focusing entirely on user search intent, NOT just the video content (e.g., "how to fall asleep fast", "stop overthinking", "sleep story for adults", "anxiety relief", "cozy ambience").
    """,

    "YOUTUBE_METADATA_CN": """
    PERSONA: 你是一位顶级的中文 ASMR 频道爆款文案策略师。
    TASK: 将以下英文的视频元数据转化为极具高点击率、反套路的中文版本。
    
    --- ENGLISH METADATA ---
    {english_metadata}
    
    --- CRITICAL RULES ---
    1. 标题 (TITLE): 保留悬念感与物理感官细节，使用网感化、吸引点击的词汇。
    2. 封面短语 (THUMBNAIL TEXT): 将标题内核提炼成极具视觉冲击力的高点击率短语（4-6个字）。突出质感或悬念，绝不能生硬重复标题。
    3. 简介 (DESCRIPTION): 语言需像电影旁白般极具画面感，结尾温柔引导关注与晚安。
    4. 标签 (TAGS): 转化为中文圈高流量助眠标签。
    """,

    "THUMBNAIL_PROMPT_OSS": """
    TASK: Generate ONE cinematic YouTube thumbnail image prompt in English.

    INPUT:
    - Script Summary: {script_summary}
    - Anchor: {anchor}
    - Style: {style}
    - Character: {character}

    RULES:
    1. Focus on a highly engaging, breathtaking wide shot that captures the essence of the story.
    2. Naturally integrate the Character description into the scene if they are present.
    3. Keep it between 50-70 words.
    4. FORMAT: You MUST wrap your final output completely inside <prompt> and </prompt> XML tags. OUTPUT ONLY THE XML TAGS AND NOTHING ELSE.
    """,

    # ==========================================
    # 终极质检护栏 (LLM-as-a-Judge Guardrails)
    # ==========================================
    "QUALITY_JUDGE_EN": """
    You are a strict Quality Assurance Judge for a highly professional ASMR/Sleep Story channel.
    Your job is to analyze the following English text and determine if it is perfectly safe, relaxing, and free of hallucinations.

    CRITICAL FAILURES (If ANY of these exist, you MUST fail the text):
    1. Technical/Scientific Data: ANY mention of explicit numbers, physics formulas, units of measurement, or scientific jargon (e.g., "0.3 Newtons", "340 m/s", "Hertz", "Fluid dynamics"). Sleep stories must be emotional and sensory, not scientific.
    2. Horror/Bizarre Surrealism: Any creepy, unsettling, violent, or overly bizarre imagery that could disturb a sleeper (e.g., monsters, blood, deep anxiety, jump scares).
    3. Token Collapse/Gibberish: Mindless repetition of the same words just to fill space.

    Analyze the text carefully. Return ONLY a valid JSON object in this exact format, with no markdown formatting or extra text:
    {{"pass": true/false, "reason": "brief explanation in English"}}

    --- TEXT TO EVALUATE ---
    {text}
    """,

    "QUALITY_JUDGE_CN": """
    PERSONA: 你是一位顶级 ASMR 睡眠频道的内容质检官。
    TASK: 你的任务是审查以下中文文本，判断其是否绝对安全、极其催眠，且没有发生大模型生成故障。

    【绝对红线】（只要触犯任意一条，必须判定为不合格）：
    1. 理科数据与生硬指标：文中出现了任何具体的数字、物理/生物学名词、测量单位（如：“0.3牛顿”、“340米/秒”、“流体力学”、“频率”、“赫兹”等）。睡眠故事必须是感性与柔和的，绝不能像科学说明书。
    2. 恐怖与诡异意象：文中出现了任何惊悚、血腥、暴力、令人不安的超现实画面（如：鬼怪、克苏鲁、极度的深渊恐惧感）。
    3. 乱码与车轱辘话：大模型因为字数限制而产生的低智商单字重复（如连续出现“低低低低低”或毫无意义的复读机段落）。

    请严格审查。只返回一个合法的 JSON 对象，绝对不要输出任何 Markdown 标记或多余的解释：
    {{"pass": true/false, "reason": "简短的中文判定理由"}}

    --- 待质检文本 ---
    {text}
    """,    
}