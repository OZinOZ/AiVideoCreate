# -*- coding: utf-8 -*-
"""Guard test: no hardcoded API keys may enter the repository.

Scans every tracked Python file for constant string assignments to
well-known secret names. A regression here fails CI before anything
reaches GitHub.

This test reads only the repository's own source files; it performs
no network access.
"""

import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Secret-bearing variable names that must never be assigned a literal value.
SECRET_NAMES = [
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GEMMA4_API_KEY",
    "AZURE_API_KEY",
    "NVIDIA_NIM_API_KEY",
    "RUNNINGHUB_API_KEY",
    "SILICONFLOW_API_KEY",
    "IMGBB_API_KEY",
    "GITHUB_TOKEN",
    "GCP_CLIENT_SECRET",
    "GCP_REFRESH_TOKEN",
]

# A non-empty literal string (not os.getenv(...), not a placeholder like 你的_xxx / your_xxx / "").
_LITERAL_ASSIGNMENT = re.compile(
    r"^\s*(?:" + "|".join(SECRET_NAMES) + r")\s*=\s*[\"']([^\"']+)[\"']\s*(#.*)?$",
    re.MULTILINE,
)

_PLACEHOLDER_RE = re.compile(
    r"^(你的|your_|<|placeholder|dummy|example|xxx)", re.IGNORECASE
)

# Known-leaked values from project history; they must never reappear anywhere.
_LEAKED_VALUES = [
    "IdTzr3peC4CJ829HfufQtkzMFD02l9QHYZq629YHd0nm1aK4sjB5lQtJ",
    "53992866-2a30a7a628aa4b99448819360",
]

SKIP_DIRS = {".git", "__pycache__", ".workbuddy", "node_modules"}
SKIP_FILES = {".env.example"}


def _iter_python_files():
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def test_no_hardcoded_secret_literals():
    offenders = []
    for path in _iter_python_files():
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        for match in _LITERAL_ASSIGNMENT.finditer(content):
            value = match.group(1)
            if value and not _PLACEHOLDER_RE.match(value):
                offenders.append((path, match.group(0).strip()))
    assert not offenders, (
        "Hardcoded secret(s) found - move them to .env / environment variables:\n"
        + "\n".join(f"  {path}: {line}" for path, line in offenders)
    )


def test_known_leaked_values_absent_from_source():
    """The Pexels/Pixabay keys removed in the 2026-10 cleanup must stay out."""
    this_file = os.path.abspath(__file__)
    for path in _iter_python_files():
        if os.path.abspath(path) == this_file:
            continue  # the sentinel values themselves live in this test
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        for leaked in _LEAKED_VALUES:
            assert leaked not in content, f"Known-leaked key found in {path}"


def test_env_example_lists_all_managed_secrets():
    with open(os.path.join(REPO_ROOT, ".env.example"), "r", encoding="utf-8") as fh:
        example = fh.read()
    for secret in SECRET_NAMES:
        assert f"{secret}=" in example, f"{secret} missing from .env.example"
