# -*- coding: utf-8 -*-
"""Character trait pool used by regen_characters / fix_characters."""
from typing import Dict, List

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
