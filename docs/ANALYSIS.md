# 整合分析

## 原目录处理结果

| 原目录 | 处理 |
|---|---|
| `Pipeline_model` = `pipiline_local`（文件完全相同） | 成为主工程 `pipeline/` |
| `pipiline_local_optimize` | **删除**：`app_local_runner`/`core_engine` 是 local 的旧版子集，无独有功能 |
| `pipeline_optimize`（modular） | **删除**：core_io/llm/media 拆分实验，未成主线 |
| `pipiline_github` | 渲染逻辑 → `RENDER_BACKEND="github"`；`GitHubSyncManager`、`encode_video_github_sync`、GDrive 取回其实已在 local 的 core_engine 里，只是 local runner 没接线，现已接上；工具脚本 → `tools/` |
| `pipeline_colab` | worker notebook 与控制端 → `colab/`；协议实现为 `RENDER_BACKEND="colab"`（`render_backends.py`）；其余是 cloud_legacy 副本，丢弃 |
| `pipeline`（cloud_legacy） | 字体 → `pipeline/assets/fonts`；频道 → `pipeline/channels_legacy`；uploader/runninghub → `tools/`；旧 runner 整体 → `archive/cloud_legacy`（可删） |

## 本次代码改动（均在 `pipeline/`）

1. **修复**：`core_engine.py` 的 `MODEL_CONFIG` 在 `"AGNES_MODEL"` 后少一个逗号 → 原 local 版本是 SyntaxError，无法导入。
2. 新增 `render_backends.py`：`resolve_render_backend` / `get_render_config` / `get_render_parallelism` / `encode_video_colab_sync` / `build_colab_ffmpeg_command`。
3. `app_local_runner.py`：`MediaPipeline` 增加 `render_backend/render_config`，新增 `_encode_video` 分发、`_encode_video_github_sync`（含重试）、`_encode_video_colab_sync`；`execute_channel` 按后端设置并发、配置/清理 GitHub 工作区；新增 `--render-backend` 参数。
4. `base_config.py`：新增 `RENDER_BACKEND`、`COLAB_INTERFACE_CONFIG`、`REPO_FONT_DIR`；`runtime_config.py`：`COLAB_DRIVE_DIR` 环境变量映射。
5. `tools/story/trait_pool.py`：从 github 版 base_config 抽出 `TRAIT_POOL`，供 regen/fix_characters 使用（local base_config 没有）。

## 安全

- 原 `pipiline_github/default.env` 末尾**粘贴了 Google 服务账号 JSON（含 private_key）**，并含真实 API Key。该文件**未**复制进新工程，也已不在新 git 历史中；新工程提供空值的 `.env.example`。**请务必轮换这些密钥**（服务账号 key、OpenAI/Gemini/SiliconFlow/RunningHub/GitHub/ImgBB）。该文件不在旧仓库的 git 跟踪中，但仍在磁盘上，请自行删除。

## 未验证 / 已知问题

- 未实际跑通完整流水线与 GitHub / Colab 端到端（需要你的密钥与云端环境），仅做了语法与导入检查。
- `channels_legacy/*` 来自旧 base_config，字段可能与新 runner 不完全匹配。
- `tools/video/youtube_factory/pretty.py` 第 581 行语法错误（原文件即如此）。
- 大量硬编码盘符路径（`I:\AiVideos`, `E:\assets`, `Y:/assets`）仍需按机器修改。
- `tools/story/*`、`prompt_editor` 内的路径是原作者机器路径。
