# AiVideoCreate

[English](README.md) | **简体中文**

双语 (EN/CN) AI 视频生产流水线：**故事/剧本 (LLM) → TTS → 图像生成 → 视频合成 → YouTube 元数据与上传**。

渲染位置（本机 / GitHub Actions / Colab）是一个**配置项**（`RENDER_BACKEND`），而不是独立代码分支——同一套频道配置可以在这三种环境之间切换。

> 本仓库由多个历史版本（`AiScripts` / `Pipeline_model` / `pipiline_github` / `pipeline_colab` 等）合并而成，合并过程见 [docs/ANALYSIS.md](docs/ANALYSIS.md)。

## 目录结构

```
pipeline/                      主工程（flat import，需在 pipeline/ 目录下运行）
  app_local_runner.py          入口 runner：StoryPipeline（剧本）+ MediaPipeline（媒体）
  core_engine.py               核心：LLM/TTS/图像/FFmpeg/GitHub/GDrive/YouTube 封装
  render_backends.py           渲染后端抽象：local | github | colab
  base_config.py               默认配置（RENDER_BACKEND、GITHUB/COLAB_INTERFACE_CONFIG 等）
  runtime_config.py            分层配置加载：base < 频道 < .env < 环境变量 < CLI
  app_doac.py app_podcast.py   频道配置（DOAC、播客）
  channels_legacy/             旧云端版频道（prettypet/psychology/tanktail），未在新 runner 验证
  idle_monitor.py              空闲监控
  assets/fonts/                17 款字体（通过 REPO_FONT_DIR 引用）
colab/                         Colab worker notebook + Drive 协议控制端测试
tools/
  prompt_editor/               Flask 提示词编辑器 + 提示词文本
  story/                       regen_characters / fix_characters / app_text_rewrite / app_doac_rewrite
  github/                      Github_clean（清理 Actions runs）
  media/ youtube/ runninghub/  overlay 转码、独立 YouTube 上传器、RunningHub 辅助
  text/ video/                 文本处理与零散视频脚本（下载、ffmpeg、mermaid、youtube_factory 等）
archive/cloud_legacy/          最早版本 runner（已被 pipeline/ 取代，仅供参考，可删）
docs/                          设计文档、配置说明、整合分析
tests/                         pytest 单元测试
.github/workflows/             CI：每次 push / PR 自动运行 lint + pytest
```

## 快速开始

### 环境要求

- Python 3.11+
- ffmpeg（本机渲染需要；有 NVIDIA GPU 时自动尝试 NVENC）
- 可选：Google Drive 桌面端（colab 后端）、GitHub Actions 仓库（github 后端）

### 安装

```bash
pip install -r requirements.txt

# 配置密钥：复制模板并填写，.env 已被 gitignore，不要提交真实值
copy .env.example .env        # Linux/macOS: cp .env.example .env
```

所有密钥通过**环境变量或 `.env` 文件**提供，代码中没有任何硬编码密钥。
`ENV_CONFIG_FILE` 可以指向任意 `.env` 路径；`.env` 中的变量不会覆盖已有的进程环境变量。

### 运行

```bash
cd pipeline
python app_local_runner.py -c app_doac.py                          # 本机渲染
python app_local_runner.py -c app_doac.py --render-backend github  # GitHub Actions 渲染
python app_local_runner.py -c app_doac.py --render-backend colab   # Colab 渲染
```

常用 CLI 参数：

| 参数 | 说明 |
|---|---|
| `-c/--config` | 频道配置文件（默认 `app_doac.py`） |
| `--render-backend` | `local` / `github` / `colab`，覆盖配置中的 `RENDER_BACKEND` |
| `--fresh` | 强制全新运行，忽略所有 REUSE 标志 |
| `--reuse-tts / --reuse-image / --reuse-video / --reuse-image-prompt` | 复用中间产物 |
| `--reuse-task-id <id>` | 复用指定任务的工作目录 |
| `--only-generate-image` | 只生成图片不渲染视频 |

### 测试

```bash
pip install pytest
pytest
```

测试全部可在无密钥、无 ffmpeg 的环境下运行；依赖重度第三方库（如 `core_engine`）的测试在缺依赖时自动跳过。

## 配置体系

优先级（低 → 高）：

```
base_config.py  →  频道配置 app_xxx.py  →  .env (ENV_CONFIG_FILE)  →  进程环境变量  →  CLI 参数
```

渲染后端 `RENDER_BACKEND` 的解析顺序：CLI `--render-backend` > 环境变量 > 频道/基础配置 > 旧开关 `USE_GIT_HUB_INTERFACE` > `local`。详见 [docs/CONFIG.md](docs/CONFIG.md)。

| 后端 | 说明 | 必需配置 |
|---|---|---|
| `local` | 本机 ffmpeg（NVENC 优先，并发 2） | ffmpeg |
| `github` | 逐片段 dispatch GitHub Actions，图片经 ImgBB 上传，成品从 Google Drive 取回 | `GITHUB_TOKEN` `IMGBB_API_KEY` `GDRIVE_FOLDER_ID` `GCP_CLIENT_ID/SECRET/REFRESH_TOKEN` |
| `colab` | 本机把图片+ffmpeg 命令写入 Drive 共享目录，Colab worker 渲染后回写 | `COLAB_DRIVE_DIR`，并运行 `colab/ffmpeg_colab_gdrive.ipynb` |

## 安全

- 所有 API key / token 只放在 `.env` 或环境变量中；`.env`、`token.json`、`client_secret*.json`、`*service_account*.json` 均已被 `.gitignore` 排除。
- CI 中包含密钥扫描步骤（`tests/test_no_hardcoded_keys.py`），任何以 `PEXELS_API_KEY = "..."` 形式硬编码的密钥都会导致构建失败。
- 历史遗留密钥已在整合时全部清除（详见 [docs/ANALYSIS.md](docs/ANALYSIS.md)），相关 key 建议照常轮换。

## 文档

- [docs/DESIGN.md](docs/DESIGN.md) — 架构与设计文档（英文）
- [docs/CONFIG.md](docs/CONFIG.md) — 配置项详解（英文）
- [docs/ANALYSIS.md](docs/ANALYSIS.md) — 多版本仓库整合过程（英文）
- [docs/REFACTORING.md](docs/REFACTORING.md) — 代码整理与后续优化建议（英文）
