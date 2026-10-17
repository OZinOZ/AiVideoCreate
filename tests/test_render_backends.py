# -*- coding: utf-8 -*-
"""Unit tests for pipeline/render_backends.py.

render_backends imports core_engine, which pulls heavy third-party deps
(google-genai, openai, pydub, ...). Tests are skipped automatically when
those are unavailable so the suite stays runnable on a bare machine.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

core_engine = pytest.importorskip("core_engine", reason="core_engine deps not installed")
import render_backends as rb  # noqa: E402


class _Cfg:
    RENDER_BACKEND = ""
    USE_GIT_HUB_INTERFACE = False
    GITHUB_INTERFACE_CONFIG = {}
    COLAB_INTERFACE_CONFIG = {}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("RENDER_BACKEND", raising=False)


class TestResolveRenderBackend:
    def test_defaults_to_local(self):
        assert rb.resolve_render_backend(_Cfg()) == "local"

    def test_cli_override_beats_everything(self, monkeypatch):
        monkeypatch.setenv("RENDER_BACKEND", "colab")
        cfg = _Cfg()
        cfg.RENDER_BACKEND = "github"
        assert rb.resolve_render_backend(cfg, override="local") == "local"

    def test_env_beats_channel_config(self, monkeypatch):
        monkeypatch.setenv("RENDER_BACKEND", "github")
        cfg = _Cfg()
        cfg.RENDER_BACKEND = "colab"
        assert rb.resolve_render_backend(cfg) == "github"

    def test_channel_config_used_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("RENDER_BACKEND", raising=False)
        cfg = _Cfg()
        cfg.RENDER_BACKEND = "colab"
        assert rb.resolve_render_backend(cfg) == "colab"

    def test_legacy_switch_maps_to_github(self, monkeypatch):
        monkeypatch.delenv("RENDER_BACKEND", raising=False)
        cfg = _Cfg()
        cfg.RENDER_BACKEND = ""
        cfg.USE_GIT_HUB_INTERFACE = True
        assert rb.resolve_render_backend(cfg) == "github"

    def test_case_and_whitespace_tolerated(self):
        assert rb.resolve_render_backend(_Cfg(), override="  Local ") == "local"

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown RENDER_BACKEND"):
            rb.resolve_render_backend(_Cfg(), override="lambda-labs")


class TestRenderConfigAndParallelism:
    def test_github_config_returns_copy(self):
        cfg = _Cfg()
        cfg.GITHUB_INTERFACE_CONFIG = {"REPO_OWNER": "OZinOZ"}
        result = rb.get_render_config(cfg, "github")
        assert result == {"REPO_OWNER": "OZinOZ"}
        result["REPO_OWNER"] = "mutated"
        assert cfg.GITHUB_INTERFACE_CONFIG["REPO_OWNER"] == "OZinOZ"  # deep copy semantics

    def test_colab_config(self):
        cfg = _Cfg()
        cfg.COLAB_INTERFACE_CONFIG = {"DRIVE_BASE_DIR": "X:/drive"}
        assert rb.get_render_config(cfg, "colab")["DRIVE_BASE_DIR"] == "X:/drive"

    def test_local_config_empty(self):
        assert rb.get_render_config(_Cfg(), "local") == {}

    def test_parallelism_per_backend(self):
        cfg = _Cfg()
        cfg.GITHUB_INTERFACE_CONFIG = {"MAX_PARALLEL_RENDERS": 3}
        assert rb.get_render_parallelism("local", cfg) == 2
        assert rb.get_render_parallelism("colab", cfg) == 1
        assert rb.get_render_parallelism("github", cfg) == 3

    def test_github_parallelism_clamped(self):
        cfg = _Cfg()
        cfg.GITHUB_INTERFACE_CONFIG = {"MAX_PARALLEL_RENDERS": 999}
        assert rb.get_render_parallelism("github", cfg) <= 20


class TestColabCommandBuilder:
    def test_command_uses_libx264_and_placeholders(self):
        cmd = rb.build_colab_ffmpeg_command(duration=5.0, movement="zoom_in")
        assert "libx264" in cmd
        assert "{INPUT_IMAGE}" in cmd
        assert "{OUTPUT_VIDEO}" in cmd

    def test_duration_is_encoded(self):
        cmd = rb.build_colab_ffmpeg_command(duration=7.0, movement="zoom_in")
        assert "7" in cmd


class TestEncodeVideoColabSync:
    def test_missing_drive_dir_fails_fast(self):
        assert rb.encode_video_colab_sync(
            "img.png", 5.0, "out.mp4", "zoom_in", {"DRIVE_BASE_DIR": ""}
        ) is False

    def test_nonexistent_drive_dir_fails_fast(self):
        assert rb.encode_video_colab_sync(
            "img.png", 5.0, "out.mp4", "zoom_in", {"DRIVE_BASE_DIR": "Z:/definitely/not/here"}
        ) is False
