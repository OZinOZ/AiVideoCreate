# -*- coding: utf-8 -*-
"""
Pluggable clip-render backends for the media pipeline.

    local  - ffmpeg on this machine (default)
    github - GitHub Actions workflow (core_engine.encode_video_github_sync)
    colab  - Google Colab worker coordinated through a shared Google Drive folder
             (worker: colab/ffmpeg_colab_gdrive.ipynb)

Selection precedence: CLI --render-backend > env RENDER_BACKEND > cfg.RENDER_BACKEND
> legacy cfg.USE_GIT_HUB_INTERFACE > "local".
"""

import json
import os
import shlex
import shutil
import threading
import time
import uuid
from typing import Any, Optional

from core_engine import build_nvenc_zoompan_ffmpeg_cmd, log_status

VALID_BACKENDS = ("local", "github", "colab")

# The Drive protocol has exactly one task_file.txt, so only one colab render may be in flight.
_COLAB_LOCK = threading.Lock()


def resolve_render_backend(cfg: Any, override: Optional[str] = None) -> str:
    """Return the active render backend name."""
    raw = override or os.getenv("RENDER_BACKEND") or getattr(cfg, "RENDER_BACKEND", "") or ""
    backend = str(raw).strip().lower()
    if not backend:
        backend = "github" if getattr(cfg, "USE_GIT_HUB_INTERFACE", False) else "local"
    if backend not in VALID_BACKENDS:
        raise ValueError(f"Unknown RENDER_BACKEND {backend!r}; expected one of {VALID_BACKENDS}")
    return backend


def get_render_config(cfg: Any, backend: str) -> dict:
    """Return the backend-specific config dict (empty for local)."""
    if backend == "github":
        return dict(getattr(cfg, "GITHUB_INTERFACE_CONFIG", {}) or {})
    if backend == "colab":
        return dict(getattr(cfg, "COLAB_INTERFACE_CONFIG", {}) or {})
    return {}


def get_render_parallelism(backend: str, cfg: Any) -> int:
    """How many clip renders may run at once for this backend."""
    if backend == "github":
        gh_cfg = getattr(cfg, "GITHUB_INTERFACE_CONFIG", {}) or {}
        return max(1, min(int(gh_cfg.get("MAX_PARALLEL_RENDERS", 8) or 8), 20))
    if backend == "colab":
        return 1
    return 2


# ---------------------------------------------------------------------------
# Colab / Google Drive backend
# ---------------------------------------------------------------------------

def build_colab_ffmpeg_command(duration: float, movement: str, fps: int = 25) -> str:
    """Build the ffmpeg command template the Colab worker will run.

    The worker replaces {INPUT_IMAGE} and {OUTPUT_VIDEO} with absolute paths on its side.
    Same Ken Burns filter chain as the local renderer, but libx264 (Colab ffmpeg builds usually lack NVENC).
    """
    cmd = build_nvenc_zoompan_ffmpeg_cmd(
        img_path="{INPUT_IMAGE}",
        duration=duration,
        clip_path="{OUTPUT_VIDEO}",
        movement=movement,
        fps=fps,
    )
    idx = cmd.index("-c:v")
    cmd = cmd[:idx] + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                       "-pix_fmt", "yuv420p", "{OUTPUT_VIDEO}"]
    return shlex.join(cmd)


def _read_task_file(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
        return json.loads(content) if content else None
    except (OSError, json.JSONDecodeError):
        return None  # Drive may be mid-sync; caller just retries


def encode_video_colab_sync(
    img_path: str,
    duration: float,
    clip_path: str,
    movement: str,
    colab_config: dict,
) -> bool:
    """Render one clip on the Colab worker through the shared Drive folder."""
    drive_dir = colab_config.get("DRIVE_BASE_DIR", "")
    poll = float(colab_config.get("POLL_INTERVAL_SECONDS", 3))
    max_wait = float(colab_config.get("MAX_WAIT_SECONDS", 900))
    sync_wait = float(colab_config.get("SYNC_WAIT_SECONDS", 180))
    fps = int(colab_config.get("FPS", 25))
    if not drive_dir or not os.path.isdir(drive_dir):
        log_status("COLAB", f"DRIVE_BASE_DIR not found: {drive_dir!r}", "ERROR")
        return False

    task_file = os.path.join(drive_dir, "task_file.txt")
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    task_dir = os.path.join(drive_dir, task_id)
    image_name = f"{task_id}{os.path.splitext(img_path)[1] or '.png'}"

    with _COLAB_LOCK:
        try:
            # Wait for any previous task to be cleared by its owner.
            deadline = time.time() + max_wait
            while time.time() < deadline:
                prev = _read_task_file(task_file) if os.path.exists(task_file) else None
                if not prev or prev.get("status") not in ("start", "running"):
                    break
                time.sleep(poll)

            os.makedirs(task_dir, exist_ok=True)
            shutil.copy2(img_path, os.path.join(task_dir, image_name))
            payload = {
                "image": f"{task_id}/{image_name}",  # relative path: works for Windows and Linux
                "command": build_colab_ffmpeg_command(duration, movement, fps),
                "status": "start",
            }
            with open(task_file, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=4)
            log_status("COLAB", f"[{task_id}] Task written, waiting for Colab worker...", "INFO")

            deadline = time.time() + max_wait
            video_rel = ""
            while time.time() < deadline:
                data = _read_task_file(task_file)
                status = (data or {}).get("status")
                if status == "success":
                    video_rel = data.get("video", "")
                    break
                if status == "fail":
                    log_status("COLAB", f"[{task_id}] Worker reported failure.", "ERROR")
                    return False
                time.sleep(poll)
            else:
                log_status("COLAB", f"[{task_id}] Timed out after {max_wait:.0f}s.", "ERROR")
                return False

            video_abs = os.path.join(drive_dir, video_rel)
            deadline = time.time() + sync_wait
            last_size = -1
            while time.time() < deadline:
                if os.path.isfile(video_abs):
                    size = os.path.getsize(video_abs)
                    if size > 0 and size == last_size:
                        os.makedirs(os.path.dirname(clip_path) or ".", exist_ok=True)
                        shutil.copy2(video_abs, clip_path)
                        log_status("COLAB", f"[{task_id}] Clip ready: {os.path.basename(clip_path)}", "SUCCESS")
                        return True
                    last_size = size
                time.sleep(poll)
            log_status("COLAB", f"[{task_id}] Video did not sync back: {video_abs}", "ERROR")
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log_status("COLAB", f"[{task_id}] Render failed: {exc!r}", "ERROR")
            return False
        finally:
            try:
                if os.path.exists(task_file):
                    os.remove(task_file)
                shutil.rmtree(task_dir, ignore_errors=True)
            except OSError:
                pass
