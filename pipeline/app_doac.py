# -*- coding: utf-8 -*-
"""
Dark Psychology - Channel Configuration
Inherits from base_config and overrides specific settings for the Dark Psychology channel.
Focuses on deep hypnosis, subconscious exploration, and psychological thriller aesthetics.
"""

# 引入底层配置项
# pylint: disable=wildcard-import, unused-wildcard-import
from base_config import *
from typing import Dict, List, Tuple, Any

# =====================================================================
# 1. 频道专属设置 (Channel Specific Configurations)
# =====================================================================

CHANNEL_NAME_CN = "安静听懂这个世界"
CHANNEL_NAME_EN = "Quietly Understand This World"

#-------------------------------------------------------
USE_GEMMA4_OPTIMIZE_TTS = False

USE_AZURE_TTS = True
model_settings = {
    "voice_cn": "zh-CN-YunjianNeural",
    "azure_tts_style": "narration-relaxed",
    "tts_voicerate": "-12%",  #Default is for edge tts
}
if USE_AZURE_TTS: 
   model_settings["tts_voicerate"] = "-30%" #for azure tts, rate is -30

AZURE_TTS_VOICE = model_settings["voice_cn"]
AZURE_TTS_STYLE = model_settings["azure_tts_style"]
TTS_VOICERATE = model_settings["tts_voicerate"]

USE_IMAGE_TEMPLATE = False

PIPELINE_FLAGS = PIPELINE_FLAGS.copy()
PIPELINE_FLAGS.update({
    "use_cn_preset_script": True,
    "use_en_preset_script": False,
    "use_runninghub_zimage": True,
    "split_video_segment": False,
    "only_generate_script": True,
    # "reuse_task_id": "PODCAST_20260422233846",
    # "reuse_gemini_outline": True,
    # "reuse_openai_script": True,
    # "reuse_deepseek_script": True,
    # "reuse_image_prompt": True,
   #  "reuse_image": True,
   #  "reuse_tts": False,
   #  "reuse_video": False,
})


# 工作区及存储路径配置
BASE_WORKSPACE = r"I:\AiVideos\DOAC\cn"
RECORD_CSV_PATH =  os.path.join(BASE_WORKSPACE, "record.csv")
LIBRARY_CSV_PATH = os.path.join(BASE_WORKSPACE, "library.csv")
SCRIPT_RESOURCE_FILE = os.path.join(BASE_WORKSPACE, "doac.csv")

ENV_CONFIG_FILE = os.path.join(BASE_WORKSPACE, "doac.env")

# =====================================================================
# 2. 频道专用的 Prompt 覆盖 (Channel Specific Prompts)
# =====================================================================

# 复制一份底层的配置字典，避免污染基础设定
PROMPT_CONFIG = PROMPT_CONFIG.copy()

PROMPT_CONFIG["SCENE_PROMPT_GEMMA4"] = """
You are an image-prompt assistant. Read the script snippet below and output ONE still-frame scene for illustration.

Style: modern noir, high contrast, silhouette, large negative space, wide angle shot, cinematic lighting. English only in JSON values.

Rules:
- One static pose only (no walking sequences, no emotion labels like "crying").
- action: max 8 words.
- characters: Use "him" or "her" only. If no specific person is mentioned in the script (e.g., describing landscapes or empty rooms), leave the characters array EMPTY [].
- clothing: only if mentioned in the snippet, else "".
- environment: one short English phrase, max 15 words (shot type + place + light + mood). Must emphasize wide framing for video panning.
- subject_count: number of people visible (0 or 1).

Output STRICT raw JSON only. DO NOT output markdown code blocks (no ```json).
{
  "subject_count": 0,
  "characters": [],
  "environment": "ultra-wide shot, empty dark cabin, window light, deep shadows"
}

SCRIPT:
{text}
"""

PROMPT_CONFIG["DEEPSEEK_YOUTUBE_PROMPT"] = """
You are a packaging expert for a "Late-Night Healing Radio" YouTube channel. Your target audience is 35-50-year-old adults who are exhausted, stressed, and looking for quiet companionship before sleep. 
Based on the provided story snippet, please generate a YouTube optimization and marketing package:

[1] YouTube Title (High CTR & Identity-Driven)
- Content Formula: [Subject's High-Status Identity] + [A Relatable Struggle/Turning Point/Life Choice]
- Rules: 
  - Must explicitly include the person's most recognizable title/role (e.g., "Airbnb CEO", "前NASA工程师").
  - Must introduce a sharp contrast or specific crisis data if available (e.g., "暴跌80%", "枯坐十年").
  - Length: Under 50 characters. NO exclamation marks (!).  
  - Language: Match the input story's language.

[2] Short Description (SEO & Retention Friendly)
- Structure:
  - Line 1: Summary of the protagonist's identity and their low point or defining moment.
  - Line 2: A reflective question inviting the audience to find peace/inspiration in their own life.
  - Line 3: Gentle Call to Action (e.g., "欢迎在评论区分享你的故事，今晚祝你晚安。").
- Rules: Strictly under 120 words. Keep it objective, calm, and fast to generate.

[3] Thumbnail Image Prompt (High-Efficiency Generation)
- Language: English. Length: Under 50 words.
- Visual Style: Cinematic, minimalist, mid-shot or profile shot of a solitary person in thought. 
- Lighting/Color: Low-light atmosphere, muted tones (amber or dim blue), soft window light or desk lamp light.
- Efficiency Rule: Avoid complex details, busy backgrounds, or heavy facial expressions. Ensure Midjourney/SD can generate it perfectly in ONE run.

[4] Thumbnail Text Overlay (Two-Line High-CTR Formula)
- Rules:
  - Line 1 (Identity/Crisis): Max 6 Chinese characters. Must highlight their high-status or the extreme crisis (e.g., "公司暴跌80%", "百亿CEO").
  - Line 2 (The Soul Hook): Max 8 Chinese characters. Focus on the emotional weight or the core human choice (e.g., "选择让别人活", "深夜无眠硬扛").
  - Ensure the text is punchy and highly legible for mobile screens. Avoid physical movement descriptions.

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



PROMPT_CONFIG["TTS_OPTIMIZE_GEMMA4"] = """
Role: TTS文本标点与语感校对专家

Task: 规范化标点并修复明显的文本逻辑错误，确保 TTS 朗读极其自然。

[核心规则]
1. 标点强制转换：
   - 删除破折号（——）、省略号（……）、分号（；）。
   - 破折号若接补充内容，请替换为“，那是”或“，也就是”。
2. 文本逻辑纠错（高优先级）：
   - 必须修复明显的词语搭配错误或错别字。
3. 保持原汁原味：
   - 严禁重写句子！除了修复错别字和标点，其余文字一个字都不准动。
   - 严禁将长句拆碎，保持原文的叙事节奏。

[执行指令]：
直接输出校对后的结果文本，禁止包含任何额外字符。

[待处理文本]： """

TRAIT_POOL: Dict[str, Dict[str, List[str]]] = {
    "heritage": {
        "M": [
            "East Asian male figure",
            "Tibetan male figure",
            "Uyghur male figure",
            "Korean male figure",
            "Japanese male figure",
            "Southwestern Chinese male figure"
        ],
        "F": [
            "East Asian female figure",
            "Tibetan female figure",
            "Uyghur female figure",
            "Korean female figure",
            "Japanese female figure",
            "Miao ethnic female figure"
        ]
    },    
    "frame": {
         "M": [
            "tall slender",
            "broad solid",
            "compact",
            "lean athletic"
        ],
        "F": [
            "tall slender",
            "petite delicate",
            "soft rounded",
            "athletic slender"
        ]
    },    
    "face": {
        "M": [
            "long angular face",
            "square wide face",
            "high cheekbones",
            "round soft face"
        ],
        "F": [
            "oval face",
            "diamond face",
            "round full face",
            "heart-shaped face"
        ]
    },    
    "eyes": {
        "M": [
            "deep set eyes",
            "narrow eyes",
            "wide eyes",
            "large eyes"
        ],
        "F": [
            "large eyes",
            "narrow eyes",
            "soft eyes",
            "luminous eyes"
        ]
    },
    "hair": {
        "M": [
            "short neat hair",
            "medium layered hair",
            "long tied hair",
            "short textured hair"
        ],
        "F": [
            "long straight hair",
            "messy bun",
            "short bob",
            "wavy shoulder hair"
        ]
    },
}

ART_STYLE_DETAILS = {
    "cinematic_concept_art": {
        "main_feature": "Cinematic concept art: atmospheric fog, dramatic lighting, film grain, emotional tone, epic composition. Highly realistic anatomy.",
        "lighting": [
            "volumetric beam, smoky",
            "chiaroscuro, dramatic",
            "harsh shadows, stark",
            "shaft of sunlight, particle"
        ],
        "specific_feature": {
            "Noir Realism": "Deep shadows, wet reflections. Psychological tension. Lens imperfections.",
            "Fantasy Silhouette": "Strong backlight. Figures as dark silhouettes. Epic scale."
        }
    },
    "cinematic_oriental_myth": {
        "main_feature": "Dark oriental fantasy cinematic concept art. Traditional elements mixed with dramatic volumetric lighting. High contrast chiaroscuro. Intricate textures catching light. NOT flat, NOT traditional ink, NO 2D shading.",
        "lighting": [
            "moonlight piercing through fog, high contrast",
            "warm lantern glow against deep blue night, dramatic",
            "volumetric beam from above, dusty atmosphere",
            "rim light highlighting character silhouette, stark"
        ],
        "specific_feature": {
            "Cinematic Silk": "Highly detailed fabric folds catching rim light, vibrant saturated colors against dark backgrounds.",
            "Dark Environment": "Deep shadows, 80% of image is mysterious dark tones, highlighting the central character.",
            "Visual Hook": "One element of extreme high-saturation color to draw the eye."
        }
    },
    "neo_noir_thriller": {
        "main_feature": "Neo-noir cinematic aesthetic. Deep pitch-black shadows mixed with highly saturated neon or environmental colored lights. Sharp focus on character clothing.",
        "lighting": [
            "harsh street light, deep shadow, high contrast",
            "neon colored reflections, wet surfaces",
            "dramatic under-lighting, suspenseful",
            "stark side-light, split face illumination"
        ],
        "specific_feature": {
            "Color Pop": "Character clothing features highly saturated colors that pop intensely against the dark noir background.",
            "Texture Emphasis": "Glossy or wet textures catching light, extreme hyper-realism.",
            "Atmospheric Depth": "Heavy rain, fog, or smoke interacting with strong directional light sources."
        }
    }  
}

 
        
ART_STYLE_DETAILS_OLD = {
    "new_chinese_ink": {
        "main_feature": "Traditional Chinese Gongbi painting. Fine precise unbroken ink outlines define every form. Flat even color fill within lines. No shading, no gradient, no bleeding, no ink wash. Colored on silk or smooth Xuan paper with even absorption. Muted mineral colors: azurite blue, malachite green, cinnabar red, ochre yellow, white lead. Hand-painted illustration. NOT photography, NOT watercolor, NOT sumi-e, NOT bleeding, NOT wet ink.",
        "lighting": [
            "soft diffuse, empty",            # 柔光散射 + 空旷寂静
            "soft diffuse, silent",           # 柔光散射 + 无声感
            "misty morning, ethereal",        # 雾蒙蒙的早晨 + 空灵
            "twilight blue, fading",          # 暮色蓝 + 渐暗
            "twilight blue, silent",          # 暮色蓝 + 寂静
            "fading light, pale",             # 渐暗的光 + 苍白
            "fading light, hollow"            # 渐暗的光 + 空洞
        ],
        "specific_feature": {
            "Gongbi Line Emphasis": "Ultra-fine continuous ink lines with even thickness. No broken lines, no bleeding. Lines define every contour precisely. White or pale silk background dominates.",
            "Flat Color Fill": "Even opaque color fills bounded by fine outlines. No shading, no wash, no gradient. Color stops at line edge. Mineral pigment matte finish.",
            "Silk Texture": "Subtle woven silk grain visible in background. Even absorption, no bleeding. Fine lines sit on top of texture.",
            "Negative Space Composition": "Figure small in vast empty silk background. White space is 60-70% of image. Fine lines define sparse elements.",
            "Mineral Color Palette": "Muted oxidized mineral colors: faded azurite blue, weathered malachite green, aged cinnabar red, ochre yellow, chalk white."
        }
    },
    
    "ukiyo_e_modern_manga": {
        "main_feature": "Ukiyo-e woodblock print aesthetic: bold outlines, flat color areas, visible grain texture, graphic compositions.",
        "lighting": [
            "flat lighting, graphic",         # 平光 + 图形感
            "flat lighting, muted",           # 平光 + 柔和
            "soft diffuse, paper texture",    # 柔光散射 + 纸纹感
            "soft diffuse, matte",            # 柔光散射 + 哑光
            "overcast gray, grain",           # 阴天 + 颗粒感
            "overcast gray, faded"            # 阴天 + 褪色感
        ],
        "specific_feature": {
            "Bold Outline Emphasis": "Thick uneven black outlines. Dramatic line weight variation. Woodblock printing imperfections.",
            "Flat Color Block": "Muted flat color areas with hard edges. No gradient. Subtle wood grain texture overlay.",
            "Noir High Contrast": "Black and white only. Deep solid shadow blocks. Scratchy cross-hatching. High drama.",
            "Wabi-sabi Texture": "Faded colors, visible paper grain, ink bleeding at edges. Aged weathered look.",
            "Graphic Flattening": "No depth of field. Stylized clouds and waves. Decorative composition."
        }
    },
    
    "impressionism": {
        "main_feature": "Impressionist oil painting: visible broken brushstrokes, optical color mixing, emphasis on light and atmosphere.",
        "lighting": [
            "overcast gray, misty",           # 阴天漫射光 + 薄雾
            "overcast gray, humid fog",       # 阴天漫射光 + 湿雾
            "soft diffuse, dusty",            # 柔光散射 + 灰尘
            "soft diffuse, hazy",             # 柔光散射 + 雾霾
            "misty morning, damp",            # 雾蒙蒙的早晨 + 潮湿
            "golden hour glow, soft haze",    # 金色时刻 + 柔雾
            "warm candlelight, smoky",        # 暖色烛光 + 烟雾
            "warm candlelight, dim"           # 暖色烛光 + 昏暗
        ],
        "specific_feature": {
            "Broken Brushstroke": "Short visible brushstrokes in every area. No smooth blending. Colors mix optically at distance.",
            "Soft Atmospheric": "Diffused edges, misty haze, overcast light. Brushstrokes visible but gentle. Dusty pastel tones.",
            "Thick Impasto": "Heavy sculptural paint application. Palette knife marks. Rough texture catches light.",
            "Pointillist Dots": "Composed entirely of small distinct dots of pure color. No lines. Dreamlike quality.",
            "En Plein Air": "Quick sketch-like strokes. Capturing fleeting light. Unfinished edge quality."
        }
    },
    
    "golden_age_illustration": {
        "main_feature": "Golden Age illustration: visible painterly strokes, strong chiaroscuro, narrative composition, warm vintage tones.",
        "lighting": [
            "warm vintage light, soft glow",      # 温暖复古光 + 柔光
            "warm amber light, nostalgic",        # 暖琥珀色光 + 怀旧感
            "strong chiaroscuro, dramatic",       # 强烈明暗 + 戏剧性
            "bold sidelight, sharp edge",         # 侧光 + 锋利边缘
            "soft pastel light, flat",            # 柔和粉彩光 + 平面感
            "gentle backlight, ethereal",         # 柔和逆光 + 空灵
            "warm domestic light, cozy",          # 温暖居家光 + 温馨
            "golden hour interior, nostalgic",    # 金色时刻室内 + 怀旧
        ],
        "specific_feature": {
            "Leyendecker Style": "Bold visible parallel strokes. Sharp highlights on fabric folds. Strong silhouettes. Masculine edges.",
            "Mucha Style": "Elegant flowing lines. Soft pastel tones. Botanical decorative borders. Feminine grace. Flat backlight.",
            "Rockwell Style": "Warm domestic lighting. Cluttered authentic environments. Humanistic micro-expressions. Nostalgic warmth.",
            "Pulp Noir Style": "Deep dramatic shadows. Harsh under-lighting. Suspenseful composition. Film grain texture.",
            "Art Deco Style": "Geometric angular forms. Architectural framing. Sharp shadows. Jazz age elegance."
        }
    },
    
    "cinematic_concept_art": {
        "main_feature": "Cinematic concept art: atmospheric fog, dramatic lighting, film grain, emotional tone, epic composition.",
        "lighting": [
            "volumetric beam, foggy",         # 体积光束 + 雾
            "volumetric beam, smoky",         # 体积光束 + 烟
            "chiaroscuro, dramatic",          # 明暗对照 + 戏剧性
            "chiaroscuro, oppressive",        # 明暗对照 + 压迫感
            "harsh shadows, stark",           # 硬阴影 +  stark
            "harsh shadows, gritty",          # 硬阴影 + 粗粝
            "shaft of sunlight, dusty",       # 阳光光束 + 灰尘
            "shaft of sunlight, particle"     # 阳光光束 + 微粒
        ],
        "specific_feature": {
            "Megalophobia Scale": "Tiny figures against colossal structures. Heavy atmospheric fog. Deep perspective. Loneliness.",
            "Minimalist Mood": "Rough painterly strokes. Extreme color contrast. Emotional over detail. Raw texture.",
            "Noir Realism": "Deep shadows, wet reflections. Voyeuristic angle. Psychological tension. Lens imperfections.",
            "Wasteland Texture": "Grimy damp surfaces. Muddy desaturated colors. Abandoned atmosphere. No polish.",
            "Fantasy Silhouette": "Strong backlight. Figures as dark silhouettes. Optical dust and fog. Epic scale."
        }
    }
}

SHOT_TYPES = [
    "Cinematic Wide Shot", 
    "Extreme Close-up", 
    "Low-angle Shot", 
    "High-angle Shot", 
    "Medium Shot", 
    "Over-the-shoulder Shot", 
    "Dutch Angle", 
    "Tracking Shot aesthetic"
]

LIGHTING_MOODS = [
    "Volumetric lighting", 
    "Chiaroscuro lighting", 
    "Soft golden hour glow", 
    "Harsh dramatic shadows", 
    "Fading twilight blue", 
    "Warm candlelight flicker",
    "Shafts of dusty sunlight", 
    "Ethereal misty morning light"
]

FEMALE_OUTFITS = [
    "cream silk blouse, taupe pencil skirt",
    "dusty pink cardigan, white dress",
    "navy wrap dress, brown leather belt",
    "grey cashmere sweater, black tailored pants",
    "white lace top, high-waisted jeans",
    "olive utility jacket, black skinny jeans",
    "burgundy velvet dress, black tights",
    "beige trench coat, white midi dress",
    "light blue button-up shirt, cream wide pants",
    "charcoal knit dress, silver necklace",
    "pale yellow sundress, woven straw belt",
    "camel wool coat, cream turtleneck, brown leggings",
    "floral chiffon blouse, navy a-line skirt",
    "sage green linen shirt, white cropped pants",
    "mauve cashmere sweater, gray pleated skirt"
]

# 男性专属服装池
MALE_OUTFITS = [
    "white oxford shirt, navy suit pants",
    "grey merino sweater, dark brown trousers",
    "black leather jacket, white tee, black jeans",
    "navy polo shirt, beige chinos",
    "charcoal blazer, light blue shirt, grey pants",
    "olive field jacket, black jeans",
    "cream linen shirt, brown corduroy pants",
    "black turtleneck, charcoal wool pants",
    "denim jacket, grey hoodie underneath, black jeans",
    "brown leather jacket, white tee, olive pants",
    "navy peacoat, light grey sweater, dark jeans",
    "burgundy cardigan, white tee, khaki chinos",
    "dark green utility jacket, black tee, cargo pants",
    "light beige safari jacket, cream shirt, brown trousers",
    "charcoal zip hoodie, white henley, black jeans"
]

RANDOM_ACTIONS = [
    "standing still", "standing with arms crossed", "standing hands in pockets",
    "sitting on chair", "sitting on floor", "sitting on bed edge",
    "lying on side", "lying on back", "lying face down",
    "kneeling on floor", "kneeling upright", "kneeling on one knee",
    "leaning against wall", "leaning forward slightly", "leaning on railing",
    "crouching down", "bending forward", "stretching arm out",
    "head bowed", "head tilted up", "turning head sideways",
    "hand on door frame", "standing in doorway", "back against door",
    "arms resting on table", "hands clasped in lap", "fingers interlaced"
]

RANDOM_ENVIRONMENTS = [
    "apartment living room, floor lamp with warm glow, large rain-streaked window at night, humid fog drifting from open balcony",
    "corner office, glass desk with phone, floor-to-ceiling window showing city rain, overcast gray light, sterile air conditioning hum",
    "restaurant dining area, white tablecloth with single candle, brick wall with framed picture, warm amber flicker, faint garlic aroma",
    "city sidewalk, metal lamppost with flickering bulb, wet asphalt reflecting neon signs, deep twilight blue, humid fog rising",
    "bedroom, crumpled white sheets on bed, tall window with sheer curtain, soft golden sunrise diffusing through fabric",
    "hotel rooftop terrace, metal railing with dew drops, panoramic night skyline, cold blue city glow reflecting from below",
    "office kitchen, stainless steel coffee maker, white cabinet wall with mug, harsh fluorescent overhead, faint burnt coffee smell",
    "park bench, wooden slats wet from rain, large oak tree trunk behind, soft overcast gray light, damp earth scent",
    "bathroom, fogged mirror above sink, tiled wall with single light, cold blue dawn through frosted window, steam rising",
    "hallway, long corridor with wooden floor, single exit sign glowing red, dim warm emergency light, echo chamber silence"
]