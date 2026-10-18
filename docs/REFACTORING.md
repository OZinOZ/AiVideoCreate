# Refactoring Notes & Recommendations

What has already been done + suggested follow-ups, ordered by risk (low → high).

## Completed

1. **Removed all hardcoded secrets**: the Pexels / Pixabay API keys hardcoded in the download/mermaid scripts now load via `os.getenv()` and are listed in `.env.example`.
2. **Fixed the syntax error in `tools/video/youtube_factory/pretty.py`**: line 581 `raw_ mp3` → `raw_mp3` (the file never compiled as shipped).
3. **Fixed undefined names found by ruff**: missing `List` import in `pipeline/core_engine.py`, missing `import re` in the mermaid scripts.
4. **Fixed a real bug in `PATTERN_AI_PREFIXES`** (core_engine.py): the regex could not match label lines with two consecutive words (`--- Chinese Script ---`, `[Translation Result]`), even though these are its own documented examples. Rewritten as a label-word-sequence pattern; verified it still leaves normal sentences untouched.
5. **Script consolidation** (October 2026):
   - `tools/video/download/*` (10 scripts) → `media_downloader.py`
   - `tools/video/mermaid/*` (14 scripts) → `mermaid_video.py`
   - `tools/video/ffmpeg_tools/*` → `ffmpeg_tools.py` (subcommands: merge/subtitle/color/convert/music) + `video_course_analyzer.py`
   - `tools/video/youtube_factory/*` → consolidated factories: `story_factory.py`, `masterclass.py`, `warroom.py`, `asmr_studio.py`, `live_tools.py` (+ `mental.py`)
6. **Legacy directories deleted** (content remains recoverable from git history): `archive/cloud_legacy/`, `pipeline/channels_legacy/`, `tools/video/youtube_factory/archive/`. No code referenced any of them.
7. **README / DESIGN.md / tests / CI added**; secret scanning is part of CI to prevent regressions.

## Recommended: low cost, high value (near term)

1. **Turn `pipeline/` into a real package**: it currently uses flat imports (`import core_engine`) and must run from inside `pipeline/`. Converting to a package with relative imports (or uniform `from pipeline import ...`) allows running from anywhere and makes testing cleaner.
2. **`__pycache__` hygiene**: stale pycache directories are gitignored but can be deleted from disk as needed.

## Recommended: medium cost (structural evolution)

3. **Split `core_engine.py` (3k+ lines)**: natural seams already exist —
   - `llm_client.py` (`robust_*_call` family, `safe_json_loads`, cleaning pipeline)
   - `tts_audio.py` (Azure/edge TTS, `master_audio_sync`, SSML)
   - `image_client.py` (RunningHub, circuit breaker)
   - `video_render.py` (ffmpeg command building, `render_video_multi_segment_sync`)
   - `cloud_sync.py` (GitHubSyncManager, GDrive, YouTube)
   - `runtime.py` (LoggerManager, ConcurrencyManager, SystemController, `save_task_record`)
   
   Keep `core_engine.py` as a compatibility facade (`from llm_client import *`, ...) so callers need zero changes.
4. **Split `app_local_runner.py` (2.1k+ lines)**: `StoryPipeline` and `MediaPipeline` are two separate concerns and deserve their own modules. The CLI-override logic inside `execute_channel` should sink into `runtime_config` (which already has `_CLI_OVERRIDE_MAP`; the runner currently re-implements it by hand, and the two coexist).
5. **Schema-validate channel configs**: wrap the dicts in `app_doac.py` / `app_podcast.py` (ASSETS_POOL, prompts) with pydantic models so bad configs fail at startup instead of mid-run.
6. **Make `validate_simple_runner_environment` backend-aware**: it always checks for ffmpeg; when rendering via `github`/`colab` the local machine does not need ffmpeg. Validate only what the selected backend requires.
7. **Consolidate `tools/video/misc/`**: seven loose debug/utility scripts (`debug_models`, `debug_yta`, `verify_fix`, `regex`, ...) — review which are still used and merge or drop the rest.

## Recommended: long term

8. **Run manifests**: generate `manifest.json` per task directory (segments, file hashes, per-stage duration/cost) — far better for resume and cost accounting than one `record.csv` row.
9. **De-hardcode paths**: drive-letter paths in tools/ (`I:\AiVideos`, `E:\assets`, ...) should become env vars / a config file.

## Testing & CI

- `tests/` covers: config parsing (runtime_config), render-backend resolution (render_backends), text-cleaning functions, secret scanning.
- CI (`.github/workflows/ci.yml`): Python 3.11 + 3.12, ruff syntax check + pytest + secret scan, on every push / PR.
- Intentionally not tested: real LLM/TTS/image calls (need keys, cost money), actual ffmpeg rendering (slow on CI). If end-to-end verification is needed, add a manually-triggered `workflow_dispatch` smoke test.
