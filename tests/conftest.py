# -*- coding: utf-8 -*-
"""Pytest configuration: make pipeline's flat-import modules importable."""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")

for path in (REPO_ROOT, PIPELINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)
