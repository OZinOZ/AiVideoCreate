# 配置说明

## 渲染后端 `RENDER_BACKEND`

优先级：CLI `--render-backend` > 环境变量 `RENDER_BACKEND` > 频道/ base 配置 `RENDER_BACKEND` > 旧开关 `USE_GIT_HUB_INTERFACE` > `local`。

| 值 | 说明 | 必需配置 |
|---|---|---|
| `local` | 本机 ffmpeg (有 NVENC 用 NVENC，并发 2) | ffmpeg |
| `github` | 逐片段 dispatch GitHub Actions `video_render.yml`，图片经 ImgBB 上传，成品从 Google Drive 取回 | `GITHUB_INTERFACE_CONFIG`; 环境变量 `GITHUB_TOKEN IMGBB_API_KEY GDRIVE_FOLDER_ID GCP_CLIENT_ID GCP_CLIENT_SECRET GCP_REFRESH_TOKEN` |
| `colab` | 本机把图片+ffmpeg 命令写入 Drive 共享目录，Colab worker 渲染后回写 | `COLAB_INTERFACE_CONFIG["DRIVE_BASE_DIR"]` (或 `COLAB_DRIVE_DIR`)，并运行 `colab/ffmpeg_colab_gdrive.ipynb` |

频道文件里可直接写：

```python
from base_config import *
RENDER_BACKEND = "colab"
COLAB_INTERFACE_CONFIG = {**COLAB_INTERFACE_CONFIG, "DRIVE_BASE_DIR": r"H:\My Drive\AiGenerations"}
```

注意：
- `github`：仓库 `GITHUB_INTERFACE_CONFIG["REPO_OWNER"/"REPO_NAME"]` 里需要有 `video_render.yml` workflow（本项目未包含，来自你的 AiGenGitHub 仓库）。结束时会自动清理远端工作区和 workflow runs。
- `colab`：协议只有一个 `task_file.txt`，所以并发固定为 1；Colab 用 libx264，不支持 overlay/水印。

## 其他开关

`USE_RUNNINGHUB_ZIMAGE`、`SPLIT_VIDEO_SEGMENT`、`REUSE_*`、`ONLY_GENERATE_*`、`AUTO_UPLOAD_TO_YOUTUBE` 等见 `base_config.py`；
命令行：`--fresh`、`--reuse-task-id`、`--reuse-tts` 等。

## 字体

`base_config.REPO_FONT_DIR` 指向 `pipeline/assets/fonts`。在频道配置里把 `ASSETS_POOL["font_en"]`/`["font_cn"]` 设成它即可随机取字体。

## 密钥

只放 `.env` / 环境变量（见 `.env.example`）。`ENV_CONFIG_FILE` 可指向 `.env` 路径。
