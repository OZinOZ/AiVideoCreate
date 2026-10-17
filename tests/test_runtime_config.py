# -*- coding: utf-8 -*-
"""Unit tests for pipeline/runtime_config.py (stdlib-only, no external services)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

import runtime_config as rc  # noqa: E402


# ---------------------------------------------------------------------------
# parse_dotenv_file
# ---------------------------------------------------------------------------

class TestParseDotenvFile:
    def test_parses_basic_pairs(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("A=1\nB=hello world\n", encoding="utf-8")
        result = rc.parse_dotenv_file(str(env))
        assert result == {"A": "1", "B": "hello world"}

    def test_strips_surrounding_quotes(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text('A="quoted"\nB=\'single\'\n', encoding="utf-8")
        result = rc.parse_dotenv_file(str(env))
        assert result == {"A": "quoted", "B": "single"}

    def test_skips_comments_and_blank_lines(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# comment\n\n  \nA=1\n# B=2\n", encoding="utf-8")
        result = rc.parse_dotenv_file(str(env))
        assert result == {"A": "1"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert rc.parse_dotenv_file(str(tmp_path / "nope.env")) == {}

    def test_empty_path_returns_empty(self):
        assert rc.parse_dotenv_file("") == {}


# ---------------------------------------------------------------------------
# _coerce_bool / _normalize_optional_path
# ---------------------------------------------------------------------------

class TestCoerceHelpers:
    @pytest.mark.parametrize("raw,expected", [
        ("1", True), ("true", True), ("YES", True), ("on", True),
        ("0", False), ("false", False), ("no", False), ("off", False),
        ("", False),
    ])
    def test_coerce_bool_strings(self, raw, expected):
        assert rc._coerce_bool(raw) is expected

    def test_coerce_bool_passthrough(self):
        assert rc._coerce_bool(True) is True
        assert rc._coerce_bool(False) is False
        assert rc._coerce_bool(None, True) is True

    def test_normalize_optional_path_empty(self):
        assert rc._normalize_optional_path("") == ""
        assert rc._normalize_optional_path(None) == ""

    def test_normalize_optional_path_relative(self, tmp_path):
        result = rc._normalize_optional_path(".env", base_dir=str(tmp_path))
        assert os.path.isabs(result)
        assert result == os.path.join(str(tmp_path), ".env")


# ---------------------------------------------------------------------------
# PipelineRuntimeFlags
# ---------------------------------------------------------------------------

class TestPipelineRuntimeFlags:
    def test_defaults_are_not_reusing(self):
        flags = rc.PipelineRuntimeFlags()
        assert flags.is_reusing is False

    def test_reuse_task_id_triggers_is_reusing(self):
        flags = rc.PipelineRuntimeFlags(reuse_task_id="DOAC_20260101")
        assert flags.is_reusing is True

    def test_reuse_video_triggers_is_reusing(self):
        flags = rc.PipelineRuntimeFlags(reuse_video=True)
        assert flags.is_reusing is True

    def test_apply_cli_overrides_sets_known_fields(self):
        flags = rc.PipelineRuntimeFlags()
        flags.apply_cli_overrides(type("Args", (), {"reuse_tts": True, "reuse_image": None})())
        assert flags.reuse_tts is True
        assert flags.reuse_image is False  # None means "not provided"

    def test_apply_cli_overrides_ignores_unknown_fields(self):
        flags = rc.PipelineRuntimeFlags()
        flags.apply_cli_overrides(type("Args", (), {"whatever": True})())
        assert flags.is_reusing is False

    def test_to_legacy_values_uses_legacy_names(self):
        flags = rc.PipelineRuntimeFlags(reuse_tts=True)
        legacy = flags.to_legacy_values()
        assert legacy["REUSE_TTS"] is True
        assert legacy["USE_RUNNINGHUB_ZIMAGE"] is True  # default preserved


# ---------------------------------------------------------------------------
# Service env overrides (secret injection path)
# ---------------------------------------------------------------------------

class TestServiceEnvOverrides:
    def test_env_overrides_interface_config(self, monkeypatch):
        module = type("Cfg", (), {})()
        module.GITHUB_INTERFACE_CONFIG = {"TOKEN": "", "REPO_OWNER": "OZinOZ"}
        monkeypatch.setenv("GITHUB_TOKEN", "tok-from-env")
        rc._apply_service_env_overrides(module)
        assert module.GITHUB_INTERFACE_CONFIG["TOKEN"] == "tok-from-env"
        # Non-secret fields untouched
        assert module.GITHUB_INTERFACE_CONFIG["REPO_OWNER"] == "OZinOZ"

    def test_missing_env_leaves_default(self, monkeypatch):
        module = type("Cfg", (), {})()
        module.GITHUB_INTERFACE_CONFIG = {"TOKEN": "default"}
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        rc._apply_service_env_overrides(module)
        assert module.GITHUB_INTERFACE_CONFIG["TOKEN"] == "default"


# ---------------------------------------------------------------------------
# load_channel_runtime_config (end-to-end layered loading, needs pydantic via base_config)
# ---------------------------------------------------------------------------

CHANNEL_TEMPLATE = """
from base_config import *
RENDER_BACKEND = "{backend}"
"""

pytest.importorskip("pydantic")


class TestLoadChannelRuntimeConfig:
    def test_channel_value_wins_over_base(self, tmp_path):
        channel = tmp_path / "app_test.py"
        channel.write_text(CHANNEL_TEMPLATE.format(backend="colab"), encoding="utf-8")
        cfg = rc.load_channel_runtime_config(str(channel))
        assert cfg.RENDER_BACKEND == "colab"

    def test_runtime_flags_attached(self, tmp_path):
        channel = tmp_path / "app_test.py"
        channel.write_text(CHANNEL_TEMPLATE.format(backend="local"), encoding="utf-8")
        cfg = rc.load_channel_runtime_config(str(channel))
        assert cfg.RUNTIME_FLAGS.split_video_segment is True
        assert "reuse_tts" in cfg.PIPELINE_FLAGS
        # legacy attribute names are back-filled for old code paths
        assert cfg.REUSE_TTS is False

    def test_cli_override_applied(self, tmp_path):
        channel = tmp_path / "app_test.py"
        channel.write_text(CHANNEL_TEMPLATE.format(backend="local"), encoding="utf-8")
        cli = type("Args", (), {"reuse_tts": True})()
        cfg = rc.load_channel_runtime_config(str(channel), cli_args=cli)
        assert cfg.REUSE_TTS is True

    def test_env_config_file_is_resolved(self, tmp_path):
        (tmp_path / "chan.env").write_text("PEXELS_API_KEY=\n", encoding="utf-8")
        channel = tmp_path / "app_test.py"
        channel.write_text(
            CHANNEL_TEMPLATE.format(backend="local")
            + 'ENV_CONFIG_FILE = "chan.env"\n',
            encoding="utf-8",
        )
        cfg = rc.load_channel_runtime_config(str(channel))
        assert cfg.ENV_CONFIG_FILE == str(tmp_path / "chan.env")
