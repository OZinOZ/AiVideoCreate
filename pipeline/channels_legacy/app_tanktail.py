# -*- coding: utf-8 -*-
"""
Tank & Tail Talk - Channel Configuration
Inherits from base_config and overrides specific settings.
"""

from base_config import *

# 1. 频道专属设置
CHANNEL_NAME = "Tank & Tail Talk" 
CHANNEL_NAME_CN = "月海漂流" 

ONLY_GENERATE_SCRIPT = False
ONLY_GENERATE_IMAGE = False

# REUSE_TASK_ID = "TANKTAIL_20260329040447"
REUSE_GEMINI_OUTLINE = False
REUSE_OPENAI_SCRIPT = False
REUSE_DEEPSEEK_SCRIPT = False
REUSE_IMAGE_PROMPT = False
REUSE_TTS = False
REUSE_IMAGE = False
REUSE_VIDEO = False

BASE_WORKSPACE = r"I:\AiVideos\TankTailTalk"
RECORD_CSV_PATH = r"I:\AiVideos\TankTailTalk\record.csv"
LIBRARY_CSV_PATH = r"I:\AiVideos\TankTailTalk\library.csv"
