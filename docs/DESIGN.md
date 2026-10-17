# Design Document — AiVideoCreate

版本：1.0（2026-10）
状态：与 `pipeline/` 当前实现一致

## 1. 目标与范围

AiVideoCreate 是一条**端到端的双语（EN/CN）AI 视频生产流水线**，把一个频道配置文件（`app_xxx.py`）作为输入，自动完成：

1. **剧本创作**：Gemini 生成大纲 → 多 LLM（OpenAI / DeepSeek / MiniMax / Kimi / gpt-oss）生成中英文分镜剧本
2. **文本清洗**：统一清洗 LLM 输出（去幻觉、去格式噪音、SSML 停顿注入）
3. **TTS 配音**：Azure TTS / edge-tts 双通道，含音频母带处理（pedalboard）
4. **图像生成**：RunningHub workflow（含 zimage），失败重试与熔断
5. **视频合成**：Ken Burns 风格 zoompan 片段渲染 + FFmpeg 拼接，支持三种渲染后端
6. **发布**：YouTube 标题/描述/标签生成与（可选）自动上传

非目标：不做实时/流式渲染；不管理多租户；Colab 后端仅支持单任务协议。

## 2. 总体架构

```
                ┌─────────────────────────────────────────────────┐
                │        app_local_runner.py  (entry point)       │
                │   CLI parsing → config loading → execute_channel│
                └────────────┬────────────────────────────────────┘
                             │
      ┌──────────────────────┼───────────────────────────┐
      │                      │                           │
┌─────────────┐    ┌──────────────────┐        ┌────────────────────┐
│StoryPipeline│    │  MediaPipeline   │        │ idle_monitor.py    │
│ 剧本/分镜/TTS│───▶│ 图像/渲染/拼接/上传│        │ (workspace 空闲监控)│
└─────────────┘    └────────┬─────────┘        └────────────────────┘
      │                     │  _encode_video dispatch
      │                     ▼
      │        ┌─────────────────────────────┐
      │        │      render_backends.py     │  ◀── 策略模式：同一接口
      │        │ local │ github │ colab      │      三种渲染位置
      │        └───┬─────────┬─────────┬─────┘
      │            │         │         │
      │         ffmpeg    GitHubSync   Drive task_file.txt
      │        (NVENC)    Manager +    协议（单任务文件）
      │                    GDrive
      ▼                     ▼
┌────────────────────────────────────────────────────────────┐
│                    core_engine.py (30k 行核心库)             │
│  LLM 封装 (robust_*_call) │ TTS │ RunningHub │ FFmpeg 工具    │
│  GitHubSyncManager │ GDrive 上传/下载 │ YouTube 上传        │
│  LoggerManager │ ConcurrencyManager │ APIClients │ 熔断/重试 │
└────────────────────────────────────────────────────────────┘
```

支撑层：

- **runtime_config.py** — 分层配置加载与标志归一化（`PipelineRuntimeFlags`）
- **base_config.py** — 默认配置模板（pydantic 模型 + 接口配置字典）
- **tools/** — 独立脚本（下载、ffmpeg 工具、mermaid、提示词编辑器等），不属于主链路

## 3. 关键设计决策

### 3.1 渲染位置 = 配置项（策略模式）

三种渲染后端实现同一契约：`encode(img_path, duration, clip_path) -> bool`。

| 后端 | 实现 | 并发 | 适用场景 |
|---|---|---|---|
| `local` | `build_nvenc_zoompan_ffmpeg_cmd` + 本机 ffmpeg，NVENC 自动检测 | 2 | 日常、有 GPU |
| `github` | `GitHubSyncManager` 推图片 → dispatch `video_render.yml` → 轮询 → GDrive 取回 zip | `MAX_PARALLEL_RENDERS`(≤20) | 本机无 GPU |
| `colab` | Drive 共享目录 `task_file.txt` 单任务协议，Colab worker 轮询执行 libx264 | 1（协议限制） | 借用免费 GPU |

解析优先级：CLI `--render-backend` > env `RENDER_BACKEND` > `cfg.RENDER_BACKEND` > legacy `USE_GIT_HUB_INTERFACE` > `local`。
新后端只需在 `render_backends.py` 增加一个 `encode_video_xxx_sync` 并扩展 `VALID_BACKENDS` / `get_render_config` / `get_render_parallelism`。

### 3.2 分层配置（base < channel < .env < env < CLI）

`runtime_config.load_channel_runtime_config()` 把频道文件作为模块动态导入，然后：

1. 用 `_SERVICE_ENV_MAPS` 把密钥类环境变量（`GITHUB_TOKEN` 等）覆盖进 `*_INTERFACE_CONFIG` 字典 —— **密钥永远不进代码**
2. 用 `_PIPELINE_FLAG_SPECS` 把散落的布尔开关归一为强类型 `PipelineRuntimeFlags` dataclass，再回填 legacy 变量名（`REUSE_TTS` 等）保持兼容
3. CLI 覆盖最后应用，`--fresh` 等价于把所有 reuse 标志清零

### 3.3 密钥管理

- 代码零硬编码密钥；`.env.example` 是唯一模板
- `.gitignore` 排除 `.env`、`token.json`、`client_secret*.json`、`*service_account*.json`
- `tests/test_no_hardcoded_keys.py` 在 CI 中持续扫描，防止回归

### 3.4 韧性设计

- **重试**：`tenacity.retry`（指数退避）包裹所有 LLM/TTS/图像调用（`robust_*_call` 系列）
- **熔断**：图像生成带 circuit breaker，防止连环失败烧钱
- **并发控制**：`ConcurrencyManager` 提供按后端动态设置大小的信号量（TTS_SEM / NVENC_SEM 等）
- **进程治理**：`safe_subprocess_run` 统一超时；`atexit` + `_emergency_sync_cleanup` 保证退出时杀掉残留 ffmpeg
- **复用（REUSE_*）**：每个阶段产物落盘，可从任意阶段恢复，避免重跑烧 API 配额

### 3.5 任务溯源

每次运行生成 `TASK_ID`（`<频道前缀>_<时间戳>`），工作目录隔离，结束写 `record.csv`（`save_task_record`），支持 `--reuse-task-id` 回到任意历史任务。

## 4. 数据流（单次运行）

```
channel cfg (app_doac.py)
   │
   ├─ StoryPipeline
   │    Gemini outline → LLM EN/CN scripts → clean pipeline → SSML pauses
   │    → TTS (azure/edge) → master_audio_sync (pedalboard)
   │    → 每段: MediaSegment{en_text, cn_text, img_prompt, durations...}
   │
   ├─ MediaPipeline
   │    img_prompt → RunningHub → segment PNG
   │    → render_backends: PNG+duration → clip.mp4（zoompan）
   │    → ffmpeg concat (v.txt/a.txt) → EN/CN 成片
   │    → 封面缩略图 (add_text_to_thumbnail) → YouTube 元数据 (可选上传)
   │
   └─ record.csv + task 记录
```

## 5. 模块边界与依赖规则

```
tools/  colab/  archive/     不依赖 pipeline（独立脚本）
pipeline/render_backends  →  pipeline/core_engine  →  pipeline/runtime_config
pipeline/app_local_runner →  上面三者
pipeline/base_config      ←  环境变量读取，被频道文件 `from base_config import *` 继承
```

注意：`pipeline/` 采用 **flat import**（无包结构，直接 `import core_engine`），这是历史决策——运行必须在 `pipeline/` 目录下或把该目录加入 `sys.path`。`tests/conftest.py` 做了相应处理。

## 6. 已知约束

- Colab 后端协议只有单个 `task_file.txt` → 并发恒为 1，libx264 不支持 overlay/水印
- github 后端依赖外部仓库的 `video_render.yml`（`GITHUB_INTERFACE_CONFIG["REPO_OWNER/NAME"]` 指向）
- `channels_legacy/*` 基于旧 base_config，字段未与新 runner 完全对齐
- 大量 tools/ 脚本包含作者机器的盘符路径（`I:\AiVideos` 等），使用前需按机器修改

## 7. 扩展点

| 想做什么 | 改哪里 |
|---|---|
| 新增渲染后端（如 Modal、RunPod） | `render_backends.py`：新增 encode 函数 + 注册 VALID_BACKENDS |
| 新增频道 | 复制 `app_podcast.py`，改文案提示词与 ASSETS_POOL |
| 新增 LLM 供应商 | `core_engine.py`：仿照 `robust_deepseek_call` 增加 `robust_xxx_call` |
| 换 TTS | `robust_tts_call` 的分流逻辑 |
| 新增 CI 检查 | `.github/workflows/ci.yml` |
