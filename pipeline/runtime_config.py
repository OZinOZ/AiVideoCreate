# -*- coding: utf-8 -*-
"""
Layered runtime configuration loader for channel apps.

Precedence:
1. base_config defaults
2. channel config (app_xxx.py)
3. .env pointed to by ENV_CONFIG_FILE
4. process environment variables
5. CLI overrides
"""

from __future__ import annotations

import copy
import importlib.util
import os
import sys
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass
from types import ModuleType
from typing import Any

_ENV_FILE_CACHE: dict[str, str] = {}
_ENV_FILE_LOADED: str = ""

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}

_PIPELINE_FLAG_SPECS: dict[str, tuple[str, Any]] = {
    "use_cn_preset_script": ("USE_CN_PRESET_SCRIPT", False),
    "use_en_preset_script": ("USE_EN_PRESET_SCRIPT", False),
    "only_generate_script": ("ONLY_GENERATE_SCRIPT", False),
    "only_generate_image": ("ONLY_GENERATE_IMAGE", False),
    "reuse_gemini_outline": ("REUSE_GEMINI_OUTLINE", False),
    "reuse_openai_script": ("REUSE_OPENAI_SCRIPT", False),
    "reuse_deepseek_script": ("REUSE_DEEPSEEK_SCRIPT", False),
    "reuse_image_prompt": ("REUSE_IMAGE_PROMPT", False),
    "reuse_tts": ("REUSE_TTS", False),
    "reuse_image": ("REUSE_IMAGE", False),
    "reuse_video": ("REUSE_VIDEO", False),
    "reuse_task_id": ("REUSE_TASK_ID", ""),
    "reuse_target_folder": ("REUSE_TARGET_FOLDER", ""),
    "use_runninghub_zimage": ("USE_RUNNINGHUB_ZIMAGE", True),
    "split_video_segment": ("SPLIT_VIDEO_SEGMENT", True),
}

_CLI_OVERRIDE_MAP = {
    "reuse_image_prompt": "reuse_image_prompt",
    "reuse_tts": "reuse_tts",
    "reuse_image": "reuse_image",
    "reuse_video": "reuse_video",
    "reuse_task_id": "reuse_task_id",
    "only_generate_image": "only_generate_image",
}

_SERVICE_ENV_MAPS: dict[str, dict[str, str]] = {
    "GEMMA4_INTERFACE_CONFIG": {
        "BASE_URL": "GEMMA4_BASE_URL",
        "API_KEY": "GEMMA4_API_KEY",
        "MODEL": "GEMMA4_MODEL",
    },
    "COLAB_INTERFACE_CONFIG": {
        "DRIVE_BASE_DIR": "COLAB_DRIVE_DIR",
    },
    "GITHUB_INTERFACE_CONFIG": {
        "TOKEN": "GITHUB_TOKEN",
        "IMGBB_API_KEY": "IMGBB_API_KEY",
        "GDRIVE_FOLDER_ID": "GDRIVE_FOLDER_ID",
        "GCP_CLIENT_ID": "GCP_CLIENT_ID",
        "GCP_CLIENT_SECRET": "GCP_CLIENT_SECRET",
        "GCP_REFRESH_TOKEN": "GCP_REFRESH_TOKEN",
    },
}


@dataclass
class PipelineRuntimeFlags:
    use_cn_preset_script: bool = False
    use_en_preset_script: bool = False
    only_generate_script: bool = False
    only_generate_image: bool = False
    reuse_gemini_outline: bool = False
    reuse_openai_script: bool = False
    reuse_deepseek_script: bool = False
    reuse_image_prompt: bool = False
    reuse_tts: bool = False
    reuse_image: bool = False
    reuse_video: bool = False
    reuse_task_id: str = ""
    reuse_target_folder: str = ""
    use_runninghub_zimage: bool = True
    split_video_segment: bool = True

    @property
    def is_reusing(self) -> bool:
        return any(
            [
                self.reuse_gemini_outline,
                self.reuse_openai_script,
                self.reuse_deepseek_script,
                self.reuse_image_prompt,
                self.reuse_tts,
                self.reuse_image,
                self.reuse_video,
                bool(self.reuse_task_id),
                bool(self.reuse_target_folder),
            ]
        )

    def apply_cli_overrides(self, cli_args: Any | None):
        if cli_args is None:
            return
        for cli_name, field_name in _CLI_OVERRIDE_MAP.items():
            if not hasattr(cli_args, cli_name):
                continue
            value = getattr(cli_args, cli_name)
            if value is not None:
                setattr(self, field_name, value)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_legacy_values(self) -> dict[str, Any]:
        return {
            legacy_name: getattr(self, field_name)
            for field_name, (legacy_name, _default) in _PIPELINE_FLAG_SPECS.items()
        }


def parse_dotenv_file(env_path: str) -> dict[str, str]:
    """Parse a standard .env file without overwriting existing os.environ values."""
    result: dict[str, str] = {}
    if not env_path or not os.path.isfile(env_path):
        return result
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                if key:
                    result[key] = value
    except OSError:
        return {}
    return result


def load_env_config_file(env_path: str) -> dict[str, str]:
    """Load a .env file into os.environ without clobbering process env values."""
    global _ENV_FILE_CACHE, _ENV_FILE_LOADED
    normalized_path = _normalize_optional_path(env_path)
    if not normalized_path:
        return {}
    if _ENV_FILE_LOADED == normalized_path:
        return dict(_ENV_FILE_CACHE)
    parsed = parse_dotenv_file(normalized_path)
    _ENV_FILE_CACHE = parsed
    _ENV_FILE_LOADED = normalized_path
    for key, value in parsed.items():
        os.environ.setdefault(key, value)
    return dict(parsed)


def get_loaded_env_config_file() -> str:
    return _ENV_FILE_LOADED


def load_channel_runtime_config(file_path: str, cli_args: Any | None = None) -> ModuleType:
    """Load a channel config using the final layered precedence model."""
    config_path = os.path.abspath(file_path)
    probe_module_name = f"_cfg_probe_{uuid.uuid4().hex}"
    probe_module = _import_module_from_path(config_path, probe_module_name)
    try:
        env_config_file = _normalize_optional_path(
            getattr(probe_module, "ENV_CONFIG_FILE", ""),
            base_dir=os.path.dirname(config_path),
        )
    finally:
        sys.modules.pop(probe_module_name, None)

    env_values = load_env_config_file(env_config_file)

    runtime_module_name = f"_cfg_runtime_{uuid.uuid4().hex}"
    cfg_module = _import_module_from_path(
        config_path,
        runtime_module_name,
        clear_module_names={"base_config"},
    )

    cfg_module.CONFIG_FILE = config_path
    cfg_module.ENV_CONFIG_FILE = env_config_file
    cfg_module.LOADED_ENV_VARS = env_values
    cfg_module.CONFIG_PRECEDENCE = [
        "base_config.py",
        os.path.basename(config_path),
        env_config_file or "<no .env>",
        "process environment",
        "CLI overrides",
    ]

    runtime_flags = _build_runtime_flags(cfg_module, cli_args)
    _apply_runtime_flags(cfg_module, runtime_flags)
    _apply_service_env_overrides(cfg_module)
    return cfg_module


def _build_runtime_flags(cfg_module: ModuleType, cli_args: Any | None) -> PipelineRuntimeFlags:
    raw_flags = getattr(cfg_module, "PIPELINE_FLAGS", {}) or {}
    flags = PipelineRuntimeFlags()
    for field_name, (legacy_name, default_value) in _PIPELINE_FLAG_SPECS.items():
        value = None
        if isinstance(raw_flags, dict):
            if field_name in raw_flags:
                value = raw_flags[field_name]
            elif legacy_name in raw_flags:
                value = raw_flags[legacy_name]
        if value is None and hasattr(cfg_module, legacy_name):
            value = getattr(cfg_module, legacy_name)
        if isinstance(default_value, bool):
            setattr(flags, field_name, _coerce_bool(value, default_value))
        else:
            setattr(flags, field_name, _coerce_string(value))
    flags.apply_cli_overrides(cli_args)
    return flags


def _apply_runtime_flags(cfg_module: ModuleType, runtime_flags: PipelineRuntimeFlags):
    cfg_module.RUNTIME_FLAGS = runtime_flags
    cfg_module.PIPELINE_FLAGS = runtime_flags.as_dict()
    cfg_module.REUSE_FLAGS = {
        "gemini_outline": runtime_flags.reuse_gemini_outline,
        "openai_script": runtime_flags.reuse_openai_script,
        "deepseek_script": runtime_flags.reuse_deepseek_script,
        "image_prompt": runtime_flags.reuse_image_prompt,
        "tts": runtime_flags.reuse_tts,
        "image": runtime_flags.reuse_image,
        "video": runtime_flags.reuse_video,
        "task_id": runtime_flags.reuse_task_id,
        "target_folder": runtime_flags.reuse_target_folder,
    }
    cfg_module.GENERATION_FLAGS = {
        "use_cn_preset_script": runtime_flags.use_cn_preset_script,
        "use_en_preset_script": runtime_flags.use_en_preset_script,
        "only_generate_script": runtime_flags.only_generate_script,
        "only_generate_image": runtime_flags.only_generate_image,
        "split_video_segment": runtime_flags.split_video_segment,
    }
    for legacy_name, value in runtime_flags.to_legacy_values().items():
        setattr(cfg_module, legacy_name, value)


def _apply_service_env_overrides(cfg_module: ModuleType):
    for attr_name, env_map in _SERVICE_ENV_MAPS.items():
        config_dict = copy.deepcopy(getattr(cfg_module, attr_name, {}) or {})
        if not isinstance(config_dict, dict):
            config_dict = {}
        for key, env_name in env_map.items():
            env_value = os.getenv(env_name, "")
            if env_value:
                config_dict[key] = env_value
        setattr(cfg_module, attr_name, config_dict)


def _import_module_from_path(
    module_path: str,
    module_name: str,
    clear_module_names: set[str] | None = None,
) -> ModuleType:
    module_dir = os.path.dirname(module_path)
    inserted_path = False
    if module_dir and module_dir not in sys.path:
        sys.path.insert(0, module_dir)
        inserted_path = True
    try:
        for stale_name in clear_module_names or set():
            sys.modules.pop(stale_name, None)
        sys.modules.pop(module_name, None)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to build import spec for config file: {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted_path:
            with suppress(ValueError):
                sys.path.remove(module_dir)


def _normalize_optional_path(path_value: Any, base_dir: str = "") -> str:
    path_str = str(path_value or "").strip()
    if not path_str:
        return ""
    if os.path.isabs(path_str):
        return os.path.abspath(path_str)
    if base_dir:
        return os.path.abspath(os.path.join(base_dir, path_str))
    return os.path.abspath(path_str)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_VALUES
    return bool(value)


def _coerce_string(value: Any) -> str:
    return str(value or "").strip()
