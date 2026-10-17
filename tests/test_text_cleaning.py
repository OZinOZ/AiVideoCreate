# -*- coding: utf-8 -*-
"""Unit tests for core_engine's pure text-processing helpers.

These functions are the deterministic part of the LLM output cleaning
pipeline; everything here runs without network, keys, or ffmpeg.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

core_engine = pytest.importorskip("core_engine", reason="core_engine deps not installed")


class TestRemovePureSymbols:
    def test_removes_divider_lines(self):
        text = "Hello\n----------\nWorld\n********\n====\n"
        result = core_engine.remove_pure_symbols(text)
        assert "----" not in result
        assert "Hello" in result and "World" in result

    def test_keeps_normal_lines(self):
        text = "This is --- a normal line"
        assert core_engine.remove_pure_symbols(text) == text


class TestRemoveAiHallucinations:
    def test_removes_script_headers(self):
        text = "--- Chinese Script ---\n正文第一行"
        result = core_engine.remove_ai_hallucinations(text)
        assert "Chinese Script" not in result
        assert "正文第一行" in result

    def test_removes_labeled_output_line(self):
        text = "English Output:\ncontent"
        result = core_engine.remove_ai_hallucinations(text)
        assert "English Output" not in result
        assert "content" in result


class TestCleanFormatting:
    def test_collapses_excessive_blank_lines(self):
        assert core_engine.clean_formatting("a\n\n\n\n\nb") == "a\n\nb"

    def test_strips_outer_whitespace(self):
        assert core_engine.clean_formatting("  hello  ") == "hello"

    def test_empty_string_passthrough(self):
        assert core_engine.clean_formatting("") == ""


class TestRunCleanPipeline:
    def test_full_chain(self):
        raw = "--- Chinese Script ---\n\n\n正文内容\n=====\n\n\n"
        result = core_engine.run_clean_pipeline(raw)
        assert "Chinese Script" not in result
        assert "=====" not in result
        assert result == "正文内容"

    def test_empty_input_returns_empty(self):
        assert core_engine.run_clean_pipeline("") == ""


class TestSafeJsonLoads:
    def test_plain_json(self):
        assert core_engine.safe_json_loads('{"a": 1}') == {"a": 1}

    def test_markdown_fenced_json(self):
        text = '```json\n{"a": 1}\n```'
        assert core_engine.safe_json_loads(text) == {"a": 1}

    def test_json_embedded_in_prose(self):
        text = 'Sure! Here you go: {"a": 2} hope that helps'
        assert core_engine.safe_json_loads(text) == {"a": 2}

    def test_garbage_returns_empty_dict(self):
        assert core_engine.safe_json_loads("no json at all") == {}


class TestStr2Bool:
    @pytest.mark.parametrize("raw,expected", [
        ("true", True), ("Yes", True), ("1", True), ("Y", True),
        ("false", False), ("No", False), ("0", False), ("n", False),
    ])
    def test_known_values(self, raw, expected):
        assert core_engine.str2bool(raw) is expected

    def test_bool_passthrough(self):
        assert core_engine.str2bool(True) is True

    def test_invalid_raises(self):
        with pytest.raises(Exception):
            core_engine.str2bool("maybe")


class TestWrapChineseText:
    def test_wraps_long_text(self):
        text = "一二三四五六七八九十百千"
        lines = core_engine.wrap_chinese_text(text, max_len=5).split("\n")
        assert len(lines) == 3
        assert all(len(line) <= 5 for line in lines)

    def test_breaks_at_punctuation(self):
        lines = core_engine.wrap_chinese_text("一二三四，六七八九十", max_len=12).split("\n")
        assert lines[0] == "一二三四，"

    def test_short_text_single_line(self):
        assert "\n" not in core_engine.wrap_chinese_text("短文", max_len=12)
