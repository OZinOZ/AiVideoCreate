# AiVideoCreate

**English** | [简体中文](README.zh-CN.md)

Bilingual (EN/CN) AI video production pipeline: **story/script (LLM) → TTS → image generation → video composition → YouTube metadata & upload**.

The render location (local machine / GitHub Actions / Colab) is a **configuration option** (`RENDER_BACKEND`), not a separate code branch — the same channel config can switch between all three environments.

> This repo was merged from multiple historical versions (`AiScripts` / `Pipeline_model` / `pipiline_github` / `pipeline_colab`, etc.). See [docs/ANALYSIS.md](docs/ANALYSIS.md) for the merge process.

## Repository Layout

```
pipeline/                      Main project (flat imports; run from inside pipeline/)
  app_local_runner.py          Entry-point runner: StoryPipeline (scripts) + MediaPipeline (media)
  core_engine.py               Core: LLM/TTS/image/FFmpeg/GitHub/GDrive/YouTube wrappers
  render_backends.py           Render-backend abstraction: local | github | colab
  base_config.py               Default config (RENDER_BACKEND, GITHUB/COLAB_INTERFACE_CONFIG, ...)
  runtime_config.py            Layered config loading: base < channel < .env < env vars < CLI
  app_doac.py app_podcast.py   Channel configs (DOAC, Podcast)
  idle_monitor.py              Idle monitoring
  assets/fonts/                17 bundled fonts (referenced via REPO_FONT_DIR)
colab/                         Colab worker notebook + Drive-protocol controller tests
tools/
  prompt_editor/               Flask prompt editor + prompt text files
  story/                       regen_characters / fix_characters / app_text_rewrite / app_doac_rewrite
  github/                      Github_clean (clean up Actions runs)
  media/ youtube/ runninghub/  Overlay transcoding, standalone YouTube uploader, RunningHub helpers
  text/                        Text processing scripts
  video/
    download/media_downloader.py   Unified stock-media downloader (merged from 10 download scripts)
    ffmpeg_tools/                  ffmpeg_tools.py (subcommands: merge/subtitle/color/convert/music) + video_course_analyzer.py
    mermaid/mermaid_video.py       Mermaid long-video generator (merged from 14 mermaid scripts)
    youtube_factory/               Consolidated YouTube video factories: story_factory / masterclass / warroom / asmr_studio / live_tools / mental
    misc/ data/                    Debug & utility scripts, media libraries
tests/                         pytest unit tests
docs/                          Design doc, config reference, merge analysis
.github/workflows/             CI: lint + pytest on every push / PR
```

## Quick Start

### Requirements

- Python 3.11+
- ffmpeg (required for local rendering; NVENC is auto-detected when an NVIDIA GPU is present)
- Optional: Google Drive for desktop (colab backend), a GitHub Actions repo (github backend)

### Installation

```bash
pip install -r requirements.txt

# Configure secrets: copy the template and fill it in. .env is gitignored — never commit real values.
copy .env.example .env        # Linux/macOS: cp .env.example .env
```

All API keys are provided via **environment variables or a `.env` file** — no keys are hardcoded in the codebase.
`ENV_CONFIG_FILE` can point to any `.env` path; variables from `.env` never override existing process environment variables.

### Running

```bash
cd pipeline
python app_local_runner.py -c app_doac.py                          # render locally
python app_local_runner.py -c app_doac.py --render-backend github  # render via GitHub Actions
python app_local_runner.py -c app_doac.py --render-backend colab   # render via Colab
```

Common CLI flags:

| Flag | Description |
|---|---|
| `-c/--config` | Channel config file (default `app_doac.py`) |
| `--render-backend` | `local` / `github` / `colab`; overrides `RENDER_BACKEND` |
| `--fresh` | Force a clean run, ignoring all REUSE flags |
| `--reuse-tts / --reuse-image / --reuse-video / --reuse-image-prompt` | Reuse intermediate artifacts |
| `--reuse-task-id <id>` | Reuse a specific task's workspace |
| `--only-generate-image` | Generate images only, skip video rendering |

### Testing

```bash
pip install pytest
pytest
```

All tests run without keys, ffmpeg, or network access; tests that depend on heavy third-party packages (e.g. `core_engine`) are skipped automatically when those are unavailable.

## Configuration

Precedence (low → high):

```
base_config.py  →  channel config app_xxx.py  →  .env (ENV_CONFIG_FILE)  →  process environment  →  CLI args
```

`RENDER_BACKEND` resolution order: CLI `--render-backend` > env var > channel/base config > legacy switch `USE_GIT_HUB_INTERFACE` > `local`. Details in [docs/CONFIG.md](docs/CONFIG.md).

| Backend | Description | Required config |
|---|---|---|
| `local` | Local ffmpeg (NVENC preferred, parallelism 2) | ffmpeg |
| `github` | Per-clip dispatch to GitHub Actions; images uploaded via ImgBB; results fetched back from Google Drive | `GITHUB_TOKEN` `IMGBB_API_KEY` `GDRIVE_FOLDER_ID` `GCP_CLIENT_ID/SECRET/REFRESH_TOKEN` |
| `colab` | Images + ffmpeg commands written to a shared Drive folder; a Colab worker renders and writes back | `COLAB_DRIVE_DIR`, plus running `colab/ffmpeg_colab_gdrive.ipynb` |

## Security

- All API keys / tokens live only in `.env` or environment variables; `.env`, `token.json`, `client_secret*.json`, and `*service_account*.json` are excluded by `.gitignore`.
- CI includes a secret-scanning test (`tests/test_no_hardcoded_keys.py`); any hardcoded key of the form `PEXELS_API_KEY = "..."` fails the build.
- Legacy keys were removed during the merge (see [docs/ANALYSIS.md](docs/ANALYSIS.md)); rotating them is still recommended as good practice.

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) — architecture & design document
- [docs/CONFIG.md](docs/CONFIG.md) — configuration reference
- [docs/ANALYSIS.md](docs/ANALYSIS.md) — multi-repo merge process
- [docs/REFACTORING.md](docs/REFACTORING.md) — cleanup & future optimization notes
