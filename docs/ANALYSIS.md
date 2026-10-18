# Merge Analysis

## How the original directories were handled

| Original directory | Disposition |
|---|---|
| `Pipeline_model` = `pipiline_local` (files identical) | became the main project `pipeline/` |
| `pipiline_local_optimize` | **deleted**: its `app_local_runner`/`core_engine` were old subsets of local, no unique features |
| `pipeline_optimize` (modular) | **deleted**: core_io/llm/media split experiment, never the mainline |
| `pipiline_github` | render logic → `RENDER_BACKEND="github"`; `GitHubSyncManager`, `encode_video_github_sync`, GDrive retrieval were already in local's core_engine — the local runner just wasn't wired up; now connected. Utility scripts → `tools/` |
| `pipeline_colab` | worker notebook & controller → `colab/`; protocol implemented as `RENDER_BACKEND="colab"` (`render_backends.py`); the rest were cloud_legacy duplicates, dropped |
| `pipeline` (cloud_legacy) | fonts → `pipeline/assets/fonts`; uploader/runninghub → `tools/`; old runner → `archive/cloud_legacy` |

## Code changes made during the merge (all in `pipeline/`)

1. **Fix**: `MODEL_CONFIG` in `core_engine.py` was missing a comma after `"AGNES_MODEL"` → the original local version was a SyntaxError and could not even be imported.
2. Added `render_backends.py`: `resolve_render_backend` / `get_render_config` / `get_render_parallelism` / `encode_video_colab_sync` / `build_colab_ffmpeg_command`.
3. `app_local_runner.py`: `MediaPipeline` gained `render_backend/render_config`, new `_encode_video` dispatch, `_encode_video_github_sync` (with retries), `_encode_video_colab_sync`; `execute_channel` sets parallelism and configures/cleans the GitHub workspace per backend; new `--render-backend` flag.
4. `base_config.py`: added `RENDER_BACKEND`, `COLAB_INTERFACE_CONFIG`, `REPO_FONT_DIR`; `runtime_config.py`: `COLAB_DRIVE_DIR` env mapping.
5. `tools/story/trait_pool.py`: extracted `TRAIT_POOL` from the github-version base_config for regen/fix_characters (local base_config didn't have it).

## Security

- The original `pipiline_github/default.env` had a **Google service-account JSON (with private_key) pasted at the end**, plus real API keys. That file was **not** copied into the new project and is not in the new git history; the new project ships an empty-valued `.env.example`. **Rotate those secrets** (service-account key, OpenAI/Gemini/SiliconFlow/RunningHub/GitHub/ImgBB) as good practice. The file was not tracked in the old repo's git, but remained on disk — delete it manually.
- October 2026 cleanup: the Pexels/Pixabay keys hardcoded in `tools/video/download/*` and `tools/video/mermaid/mermaid.py` were replaced with `os.getenv()` reads and added to `.env.example`; the only git commit containing them was rewritten locally before the repo was ever pushed, so no secret history exists on GitHub. `tests/test_no_hardcoded_keys.py` now guards against regressions.

## Unverified / known issues

- The full pipeline and the GitHub / Colab backends were never run end-to-end during the merge (requires secrets and cloud environments); only syntax and import checks were performed.
- ~~`tools/video/youtube_factory/pretty.py` line 581 syntax error (broken in the original file).~~ Fixed (October 2026): `raw_ mp3` → `raw_mp3`.
- Many hardcoded drive-letter paths (`I:\AiVideos`, `E:\assets`, `Y:/assets`) still need per-machine adjustment.
- Paths inside `tools/story/*` and `prompt_editor` are the original author's machine paths.

## Post-merge cleanup (October 2026)

- `tools/video/download/*` (10 scripts) consolidated into `media_downloader.py`; `tools/video/mermaid/*` (14 scripts) into `mermaid_video.py`; `ffmpeg_tools/*` into `ffmpeg_tools.py` + `video_course_analyzer.py`; `youtube_factory/*` rewritten into consolidated factories (`story_factory` / `masterclass` / `warroom` / `asmr_studio` / `live_tools`).
- Legacy directories deleted (content remains recoverable from git history): `archive/cloud_legacy/`, `pipeline/channels_legacy/` (prettypet/psychology/tanktail), `tools/video/youtube_factory/archive/` (16 superseded scripts). No code referenced any of them.
