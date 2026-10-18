# Design Document — AiVideoCreate

Version: 1.0 (October 2026)
Status: matches the current implementation in `pipeline/`

## 1. Goals & Scope

AiVideoCreate is an **end-to-end bilingual (EN/CN) AI video production pipeline**. A single channel config file (`app_xxx.py`) is the only input; from it the system automatically performs:

1. **Script writing**: Gemini generates the outline → multiple LLMs (OpenAI / DeepSeek / MiniMax / Kimi / gpt-oss) produce per-segment EN & CN scripts
2. **Text cleaning**: unified LLM-output purification (hallucination removal, formatting noise removal, SSML pause injection)
3. **TTS voice-over**: dual Azure TTS / edge-tts channels, with audio mastering (pedalboard)
4. **Image generation**: RunningHub workflows (incl. zimage), with retries and a circuit breaker
5. **Video composition**: Ken Burns-style zoompan clip rendering + FFmpeg concat, across three render backends
6. **Publishing**: YouTube title/description/tags generation and (optional) auto-upload

Non-goals: no real-time/streaming rendering; no multi-tenancy; the Colab backend only supports the single-task protocol.

## 2. Overall Architecture

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
│ script→TTS  │───▶│ image→render→upload       │ (workspace watcher)│
└─────────────┘    └────────┬─────────┘        └────────────────────┘
      │                     │  _encode_video dispatch
      │                     ▼
      │        ┌─────────────────────────────┐
      │        │      render_backends.py     │  ◀── Strategy pattern: one
      │        │ local │ github │ colab      │      interface, three render sites
      │        └───┬─────────┬─────────┬─────┘
      │            │         │         │
      │         ffmpeg    GitHubSync   Drive task_file.txt
      │        (NVENC)    Manager +    protocol (single task file)
      │                    GDrive
      ▼                     ▼
┌────────────────────────────────────────────────────────────┐
│                 core_engine.py (3k-line core library)      │
│  LLM wrappers (robust_*_call) │ TTS │ RunningHub │ FFmpeg  │
│  GitHubSyncManager │ GDrive up/down │ YouTube upload       │
│  LoggerManager │ ConcurrencyManager │ APIClients │ retries │
└────────────────────────────────────────────────────────────┘
```

Supporting layers:

- **runtime_config.py** — layered config loading & flag normalization (`PipelineRuntimeFlags`)
- **base_config.py** — default config template (pydantic model + interface config dicts)
- **tools/** — standalone scripts (downloader, ffmpeg tools, mermaid, prompt editor, ...); not part of the main chain

## 3. Key Design Decisions

### 3.1 Render location = config option (Strategy pattern)

The three render backends implement one contract: `encode(img_path, duration, clip_path) -> bool`.

| Backend | Implementation | Parallelism | Best for |
|---|---|---|---|
| `local` | `build_nvenc_zoompan_ffmpeg_cmd` + local ffmpeg, auto NVENC detection | 2 | daily use, GPU machine |
| `github` | `GitHubSyncManager` pushes images → dispatches `video_render.yml` → polls → fetches zip from GDrive | `MAX_PARALLEL_RENDERS` (≤20) | no local GPU |
| `colab` | Drive shared folder `task_file.txt` single-task protocol; Colab worker runs libx264 | 1 (protocol limit) | borrowing a free GPU |

Resolution precedence: CLI `--render-backend` > env `RENDER_BACKEND` > `cfg.RENDER_BACKEND` > legacy `USE_GIT_HUB_INTERFACE` > `local`.
Adding a backend: implement one `encode_video_xxx_sync` in `render_backends.py` and extend `VALID_BACKENDS` / `get_render_config` / `get_render_parallelism`.

### 3.2 Layered configuration (base < channel < .env < env < CLI)

`runtime_config.load_channel_runtime_config()` imports the channel file as a module, then:

1. `_SERVICE_ENV_MAPS` overlays secret-bearing env vars (`GITHUB_TOKEN`, ...) onto the `*_INTERFACE_CONFIG` dicts — **secrets never enter code**
2. `_PIPELINE_FLAG_SPECS` normalizes scattered boolean switches into the strongly-typed `PipelineRuntimeFlags` dataclass, then back-fills the legacy variable names (`REUSE_TTS`, ...) for compatibility
3. CLI overrides apply last; `--fresh` is equivalent to zeroing all reuse flags

### 3.3 Secret management

- Zero hardcoded secrets; `.env.example` is the only template
- `.gitignore` excludes `.env`, `token.json`, `client_secret*.json`, `*service_account*.json`
- `tests/test_no_hardcoded_keys.py` continuously scans in CI to prevent regressions

### 3.4 Resilience

- **Retries**: `tenacity.retry` (exponential backoff) wraps every LLM/TTS/image call (`robust_*_call` family)
- **Circuit breaker**: image generation has a circuit breaker to stop runaway failures from burning money
- **Concurrency control**: `ConcurrencyManager` provides semaphores sized per backend (TTS_SEM / NVENC_SEM, ...)
- **Process governance**: `safe_subprocess_run` enforces timeouts; `atexit` + `_emergency_sync_cleanup` kill leftover ffmpeg processes on exit
- **Reuse (REUSE_*)**: every stage's artifacts are persisted, so any run can resume from any stage and avoid re-burning API quota

### 3.5 Task traceability

Each run generates a `TASK_ID` (`<channel-prefix>_<timestamp>`), works in an isolated workspace directory, and records results to `record.csv` (`save_task_record`); `--reuse-task-id` can return to any historical task.

## 4. Data Flow (single run)

```
channel cfg (app_doac.py)
   │
   ├─ StoryPipeline
   │    Gemini outline → LLM EN/CN scripts → clean pipeline → SSML pauses
   │    → TTS (azure/edge) → master_audio_sync (pedalboard)
   │    → per segment: MediaSegment{en_text, cn_text, img_prompt, durations...}
   │
   ├─ MediaPipeline
   │    img_prompt → RunningHub → segment PNG
   │    → render_backends: PNG + duration → clip.mp4 (zoompan)
   │    → ffmpeg concat (v.txt/a.txt) → EN/CN final videos
   │    → thumbnail (add_text_to_thumbnail) → YouTube metadata (optional upload)
   │
   └─ record.csv + task records
```

## 5. Module Boundaries & Dependency Rules

```
tools/  colab/  archive/     do not depend on pipeline (standalone scripts)
pipeline/render_backends  →  pipeline/core_engine  →  pipeline/runtime_config
pipeline/app_local_runner →  all of the above
pipeline/base_config      ←  reads env vars; channel files inherit via `from base_config import *`
```

Note: `pipeline/` uses **flat imports** (no package structure; direct `import core_engine`) — a historical decision. Runs must execute inside `pipeline/` or add it to `sys.path`; `tests/conftest.py` handles this for tests.

## 6. Known Constraints

- Colab protocol has a single `task_file.txt` → parallelism is fixed at 1; libx264 there does not support overlay/watermarks
- The github backend requires `video_render.yml` in an external repo (`GITHUB_INTERFACE_CONFIG["REPO_OWNER/NAME"]`)
- Many tools/ scripts contain author-machine drive-letter paths (`I:\AiVideos`, etc.) and need per-machine adjustment

## 7. Extension Points

| To do this | Change this |
|---|---|
| Add a render backend (Modal, RunPod, ...) | `render_backends.py`: new encode function + register in VALID_BACKENDS |
| Add a channel | Copy `app_podcast.py`, adjust prompts and ASSETS_POOL |
| Add an LLM provider | `core_engine.py`: add `robust_xxx_call` following `robust_deepseek_call` |
| Swap TTS | Branching logic in `robust_tts_call` |
| Add CI checks | `.github/workflows/ci.yml` |
