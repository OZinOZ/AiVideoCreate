# Configuration Reference

## Render backend `RENDER_BACKEND`

Precedence: CLI `--render-backend` > env var `RENDER_BACKEND` > channel/base config `RENDER_BACKEND` > legacy switch `USE_GIT_HUB_INTERFACE` > `local`.

| Value | Description | Required config |
|---|---|---|
| `local` | Local ffmpeg (NVENC when available, parallelism 2) | ffmpeg |
| `github` | Per-clip dispatch to GitHub Actions `video_render.yml`; images uploaded via ImgBB; results fetched from Google Drive | `GITHUB_INTERFACE_CONFIG`; env vars `GITHUB_TOKEN IMGBB_API_KEY GDRIVE_FOLDER_ID GCP_CLIENT_ID GCP_CLIENT_SECRET GCP_REFRESH_TOKEN` |
| `colab` | Local machine writes images + ffmpeg commands into a shared Drive folder; a Colab worker renders and writes back | `COLAB_INTERFACE_CONFIG["DRIVE_BASE_DIR"]` (or `COLAB_DRIVE_DIR`), plus running `colab/ffmpeg_colab_gdrive.ipynb` |

Channel files can set it directly:

```python
from base_config import *
RENDER_BACKEND = "colab"
COLAB_INTERFACE_CONFIG = {**COLAB_INTERFACE_CONFIG, "DRIVE_BASE_DIR": r"H:\My Drive\AiGenerations"}
```

Notes:
- `github`: the repo in `GITHUB_INTERFACE_CONFIG["REPO_OWNER"/"REPO_NAME"]` must contain the `video_render.yml` workflow (not bundled in this project — it lives in your AiGenGitHub repo). Remote workspace and workflow runs are cleaned up automatically at the end.
- `colab`: the protocol has only one `task_file.txt`, so parallelism is fixed at 1; Colab uses libx264 and does not support overlays/watermarks.

## Other switches

`USE_RUNNINGHUB_ZIMAGE`, `SPLIT_VIDEO_SEGMENT`, `REUSE_*`, `ONLY_GENERATE_*`, `AUTO_UPLOAD_TO_YOUTUBE`, etc. — see `base_config.py`; CLI flags: `--fresh`, `--reuse-task-id`, `--reuse-tts`, ...

## Fonts

`base_config.REPO_FONT_DIR` points to `pipeline/assets/fonts`. Set `ASSETS_POOL["font_en"]`/`["font_cn"]` in a channel config to it for random font selection.

## Secrets

Secrets live only in `.env` / environment variables (see `.env.example`). `ENV_CONFIG_FILE` can point to a `.env` path. Variables loaded from `.env` never override existing process environment variables.
