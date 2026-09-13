# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo currently is

The root `README.md` describes an ambitious target architecture (agent/, data/, docs/ directories, an agentic tool-orchestration layer, etc.). **Most of that doesn't exist yet.** The repo contains:

- `backend/` — a FastAPI service (GeoTIFF I/O, compatibility checking, chat sessions backed by Gemini, plus an optional local scene classifier — see below)
- `frontend/` — a React + Vite + TypeScript app (Clerk auth, chat UI, image comparison views)
- `train/`, `eval/`, `models/` — a fine-tuned ConvNeXt-tiny scene/land-cover classifier: dataset prep + training scripts, a validation-accuracy script, and the (gitignored) checkpoint output directory. See "Local scene classifier" below.

Don't assume the `agent/` or `docs/` directories from the README exist — check before referencing them. When adding new backend capability, prefer extending the existing `backend/app/` package structure over inventing the README's aspirational layout unless the user is explicitly building toward it.

## Local scene classifier (`train/`, `eval/`, `models/`)

Per project decision, **no model training runs on a local dev machine** — the dataset (`training.csv` + `BENv2_lithuania_summer.lmdb`, documented in `notebooks/data/SatQueryAI Dataset_README.md`) isn't checked into this repo either. Training happens on Kaggle via `train/kaggle_notebook.ipynb` — **one self-contained file**, all logic inlined, no repo/git access needed from Kaggle. See `train/README.md` for the full workflow.

- `train/bigearthnet_lmdb.py` — shared LMDB/tensor decoding helpers.
- `train/prepare_dataset.py` — filters `training.csv` to a scene/land-cover classification subset, leak-free patch-level train/val split.
- `train/train_convnext.py` — fine-tunes `timm` ConvNeXt-tiny; saves `models/bentxt_convnext.pt`.
- `train/train_lora.py` — stretch-goal only (QLoRA on Qwen2-VL-2B-Instruct), not wired into the backend.
- `eval/run_eval.py` — validation accuracy for the trained checkpoint.
- `models/` — gitignored except `.gitignore`/`README.md`; the checkpoint lives here only after being downloaded from Kaggle.

Backend integration: `backend/app/llm/local_classifier.py` loads `models/bentxt_convnext.pt` (via `timm`/`torch`/`torchvision`, listed as optional deps in `backend/requirements.txt`) and is invoked from `app/chat/service.py` on every asset upload and chat message. It's a soft dependency — if the checkpoint or the ML libs aren't present, `SceneClassifier.available` is `False` and the rest of the app (including `pytest`) is unaffected. When available, its prediction is written into the asset's `metadata.scene_classification` field and passed as `grounding` into `ChatLLM.answer()` (both `GeminiLLM` and `FakeLLM` accept this now).

## Commands

### Backend (`backend/`)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

pytest                                # run all tests
pytest tests/test_chat.py             # run one file
pytest tests/test_chat.py::test_name -v   # run a single test
```

Config is via `.env` (see `backend/.env.example`). With no `.env`, it defaults to SQLite (`sqlite+aiosqlite:///./satquery.db`), in-memory object storage, and a `FakeLLM` echo responder — so the backend and its test suite run standalone with zero external services. Tests (`backend/tests/conftest.py`) force `DATABASE_URL` to an in-memory SQLite DB and override the Clerk auth dependency, so `pytest` never needs real credentials.

### Frontend (`frontend/`)

```bash
cd frontend
npm install
npm run dev        # Vite dev server, http://localhost:5173
npm run build       # tsc -b && vite build
npm run lint        # oxlint
npm run test        # vitest run (jsdom env)
npx vitest run src/lib/sessionJob.test.ts   # run a single test file
```

Config is via `.env.local` (see `frontend/.env.example`): `VITE_CLERK_PUBLISHABLE_KEY` (required — the app renders a "missing key" screen without it) and `VITE_API_URL` (defaults to `http://127.0.0.1:8000`).

## Architecture

### Backend request flow

`app/main.py` wires two kinds of endpoints:
- Stateless, no-auth: `POST /preview` (image → PNG preview + metadata) and `POST /compatibility` (validates an upload against a `JobType` before any model is ever called — `check_compatibility` in `app/compatibility/checker.py` never raises, it always returns a `CompatibilityResult`).
- Stateful, Clerk-authenticated: everything under `/sessions*`, defined in `app/chat/router.py` and implemented in `app/chat/service.py`.

Chat data model (`app/models.py`): `ChatSession` → many `Message` and many `Asset` (uploaded images). Every asset is stored twice in object storage: the original bytes and a rendered PNG preview (`preview_gcs_uri`), because raw GeoTIFFs/SAR files aren't browser-displayable — the frontend only ever fetches the preview.

Key seams (swap implementations without touching callers):
- `app/storage/gcs.py` — `ObjectStorage` protocol. `MemoryStorage` (no `GCS_BUCKET` set) vs `GcsStorage`. Keys are namespaced `users/{clerk_user_id}/sessions/{session_id}/{asset_id}/...`.
- `app/llm/gemini.py` — `ChatLLM` protocol. `get_llm()` picks `GeminiLLM` if `GEMINI_API_KEY` or `GOOGLE_CLOUD_PROJECT` is set, else falls back to `FakeLLM` (deterministic echo, used in tests via `set_llm`).
- `app/io/geotiff.py` — all image decoding funnels through `preview_from_bytes`: `.tif`/`.tiff` go through `rasterio` (reads CRS/bounds, guesses `optical` vs `sar` modality from band count/dtype, applies percentile-stretch or SAR log-scale for the preview), `.png`/`.jpg`/`.jpeg` go through Pillow with no georeferencing (treated as "benchmark" images, no CRS).

`app/chat/service.py` is the core business logic — session CRUD, `upload_asset` (decode → store original+preview → optionally answer a paired question via the LLM) and `send_message` (re-attaches the session's most recent asset as image context on every turn, since there's no per-message image threading yet).

### Frontend structure

- `src/App.tsx` — route table lives in `src/routes.ts` (`ROUTES`); wraps everything in `ClerkProvider` (renders a setup-error screen if the publishable key is missing) and a custom `ThemeProvider` (`src/theme.ts`, light/dark persisted via `initTheme`/`toggleTheme`).
- `src/lib/api.ts` — the only place that talks to the backend; every authenticated call takes a `getToken` function (from Clerk) and throws on non-OK responses via `readError`.
- `src/pages/` — one page per route (`AskScenePage`, `ChangeScenePage`, `HomePage`, etc.); `JobStubPages.tsx` holds not-yet-built job types (e.g. `CloudJobPage`).
- `src/components/workspace/` — the chat/comparison UI: `SplitWorkspace`, `ChatPanel`/`ChatComposer`/`ChatMessage`, `CompareSlider` (before/after image comparison, math extracted to `compareSliderMath.ts` for testing), `BeforeAfterRenderer`/`ImageRenderer` for rendering previews.
- `src/components/home/` and `src/components/landing/` — marketing/dashboard-shell components, not part of the core query pipeline.

Two job types exist end-to-end today: `ask_scene` (single image Q&A) and `before_after` (bi-temporal comparison); other job types referenced elsewhere (SAR fusion, change classification) are not yet implemented in this codebase.

## Notebooks

`notebooks/data/SatQuery Final_Dataset.ipynb` and its README document the BigEarthNet-derived dataset (QA/captioning/MCQ annotations) used for model training/fine-tuning experiments — unrelated to the backend/frontend runtime and not imported by app code.
