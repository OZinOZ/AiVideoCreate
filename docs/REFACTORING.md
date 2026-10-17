# 代码整理与优化建议（REFACTORING）

本次整理（2026-10）已完成的事项 + 后续建议，按风险从低到高排序。

## 已完成

1. **移除全部硬编码密钥**：`tools/video/download/*`（10 个文件）与 `tools/video/mermaid/mermaid.py` 中硬编码的 Pexels / Pixabay API key 改为 `os.getenv()` 读取，并加入 `.env.example`。
2. **修复 `tools/video/youtube_factory/pretty.py` 语法错误**：第 581 行 `raw_ mp3` → `raw_mp3`（原文件即无法通过编译）。
3. **补充 README / DESIGN.md / 测试 / CI**，密钥扫描纳入 CI 防回归。

## 建议：低成本、高收益（可近期做）

1. **删除 `archive/cloud_legacy/`**：已被 `pipeline/` 完全取代，ANALYSIS.md 已注明仅供参考。删除可减约 2k 行死代码。
2. **统一下载脚本**：`tools/video/download/` 下 10 个脚本 90% 重复（同一组 PEXELS/PIXABAY 逻辑反复复制）。可抽一个 `download_lib.py`（含 `ensure_dir` / `download_file` / pexels+pixabay 搜索），各脚本只保留配置差异。
3. **mermaid 系列收敛**：`tools/video/mermaid/` 下 16 个文件多为迭代版本（`mermaid_mix_4k_final` / `_safe` / `_new`），建议只保留 `mermaid_main.py` + `mermaid_func.py` 一条主线，其余移入 `archive/`。
4. **把 `pipeline/` 变成真正的包**：目前是 flat import（`import core_engine`），必须在 `pipeline/` 目录下运行。改为 `pipeline/` 包 + 相对导入（或统一 `from pipeline import ...`）后，可以从任意目录运行，测试也更干净。
5. **`__pycache__` 清理**：磁盘上残留 `cpython-311.pyc`，已被 gitignore，可随手删除。

## 建议：中等成本（结构演进）

6. **拆分 `core_engine.py`（3000+ 行）**：天然边界已存在——
   - `llm_client.py`（`robust_*_call` 系列、`safe_json_loads`、清洗管线）
   - `tts_audio.py`（Azure/edge TTS、`master_audio_sync`、SSML）
   - `image_client.py`（RunningHub、熔断）
   - `video_render.py`（ffmpeg 命令构建、`render_video_multi_segment_sync`）
   - `cloud_sync.py`（GitHubSyncManager、GDrive、YouTube）
   - `runtime.py`（LoggerManager、ConcurrencyManager、SystemController、`save_task_record`）
   
   拆分时保持 `core_engine.py` 作为兼容 facade（`from llm_client import *` 等），调用方零改动。
7. **拆分 `app_local_runner.py`（2100+ 行）**：`StoryPipeline` 与 `MediaPipeline` 是两个独立关注点，可分别成模块；`execute_channel` 中的 CLI 覆盖逻辑应下沉到 `runtime_config`（那里已有 `_CLI_OVERRIDE_MAP` 机制，目前 runner 里手写了一遍，两处并存）。
8. **频道配置 schema 化**：`app_doac.py` / `app_podcast.py` 里的字典（ASSETS_POOL、提示词）用 pydantic 模型校验，坏配置在启动时报错而不是跑到一半才炸。
9. **`validate_simple_runner_environment` 按后端校验**：当前总是检查 ffmpeg；用 `github`/`colab` 后端渲染时本机其实不需要 ffmpeg，应按 `render_backend` 分支校验必需项。

## 建议：长期

10. **产物清单 (manifest)**：每个 task 目录生成 `manifest.json`（段落、文件哈希、各阶段耗时/费用），比 `record.csv` 一行更利于断点续跑与成本核算。
11. **配置漂移检查**：`channels_legacy` 字段与新 runner 不对齐的问题，可以用 pydantic schema 对所有 `app_*.py` 做一次性静态校验，把问题在 CI 里暴露。
12. **路径去硬编码**：tools/ 下的盘符路径（`I:\AiVideos`、`E:\assets` 等）统一改为环境变量/配置文件。

## 测试与 CI

- `tests/` 覆盖：配置解析（runtime_config）、渲染后端解析（render_backends）、文本清洗函数、密钥扫描。
- CI（`.github/workflows/ci.yml`）：Python 3.11 + 3.12 双版本，ruff 语法检查 + pytest + 密钥扫描，每次 push / PR 触发。
- 有意不测的部分：LLM/TTS/图像真实调用（需要密钥且烧钱）、ffmpeg 实际渲染（CI 机器慢）。如需端到端验证，可加手动触发的 `workflow_dispatch` smoke test。
