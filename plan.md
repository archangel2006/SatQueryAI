# Dev 6 scope & plan — SatQuery AI

## Context

The original `SatQuery_AI_Master_Build_Plan.pdf` assumed a 9-day sprint starting ~Sept 5, but that window has passed (today is Sept 13) and the available time is **one day**. The actual codebase has also diverged from that plan: instead of the planned tool-orchestrator architecture (task inference → solution searcher → tool registry → merge/confidence/trace), what exists is a simpler Clerk-authenticated chat app where every answer comes straight from the Gemini API (`backend/app/llm/gemini.py`). There is no local model, no `train/`, `eval/`, or `models/` directory, and no pluggable VQA tool layer to slot a fine-tuned model into.

The problem this plan solves: the problem statement mandates a genuine remote-sensing domain adaptation (a model fine-tuned on BigEarthNet, actually called at inference time — the verification checklist explicitly says "confirm it is load-bearing, not just a training slide"). Right now that doesn't exist at all. Given a one-day budget and Colab-T4-class GPU access, this plan picks the fastest path to a real, demonstrably-integrated fine-tuned model over the original plan's fuller (multi-day) scope.

Dataset groundwork already exists (done by a teammate, not Dev 6): `notebooks/data/training.csv` (185,443 QA rows over 8,363 patches, columns include `patch_id`, `input`, `output`, `type`, `category`, `split_text`, lat/long, season, climate_zone) joined to `BENv2_lithuania_summer.lmdb` (Sentinel-1/2 tensors) via `patch_id`. This is the unfiltered raw join — not yet trimmed to a training-ready subset.

## Scope for today

**In scope:**
1. Data prep — filter the existing CSV to a fast-training subset, patch-level train/val split.
2. ConvNeXt-tiny scene/land-cover classifier fine-tune — the master plan's own "mandatory adaptation deliverable," and the fastest realistic path to a genuinely trained model in a single day (CPU/T4-feasible, no multi-hour VLM training).
3. Integration — get the trained classifier **actually invoked** from the live backend on a real upload, not left in a notebook. This directly satisfies the "load-bearing, not a training slide" checklist item and is the highest-priority item today.
4. A minimal validation-accuracy check.
5. Stretch, only if time remains after 1–4: a short/best-effort QLoRA fine-tune of Qwen2-VL-2B-Instruct on a small subset (a few hundred steps, not convergence).

**Out of scope today:** full RSVQA/VRSBench/CDVQA benchmark suites, the conversation manager, the knowledge base, and training Qwen2-VL LoRA to convergence. These are dropped, not deferred to "later today" — there isn't time.

## Step-by-step

1. **Data prep** — `train/prepare_dataset.py` (new)
   - Load `notebooks/data/training.csv`; before writing filter logic, inspect the actual `type`/`category` values in the CSV directly to identify which rows correspond to scene/land-cover classification vs. VQA/grounding/bounding-box.
   - Subset to a size that trains fast (a few thousand rows, well under the original plan's 8–10k if needed for time), split train/val by unique `patch_id` (never split within a patch, to avoid leakage).
   - Join to `BENv2_lithuania_summer.lmdb` via `patch_id` for the image tensors.

2. **ConvNeXt-tiny fine-tune** — `train/train_convnext.py` (new)
   - `timm` ConvNeXt-tiny, ImageNet-pretrained, fine-tune classification head (unfreeze last block only if time allows).
   - Save checkpoint to `models/bentxt_convnext.pt` (matches the master plan's naming, keeps a path future devs will recognize).

3. **Eval** — `eval/run_eval.py` (new, single script — not the master plan's three separate benchmark runners)
   - Val-split accuracy for the trained classifier. This is the only eval deliverable today.

4. **Integration (critical path)** — the current backend has no VQA "tool" abstraction to plug into, just `GeminiLLM` implementing the `ChatLLM` protocol in `backend/app/llm/gemini.py`, called from `backend/app/chat/service.py`'s `upload_asset`/`send_message`.
   - Add a small local-model wrapper (e.g. `backend/app/llm/local_classifier.py`) that loads `models/bentxt_convnext.pt` and classifies an uploaded scene's preview image.
   - Wire it into `app/chat/service.py` so the classification genuinely runs on real uploads — e.g. injected as grounding context into the Gemini system prompt, or returned as a labeled field alongside the answer. The bar is "verifiably runs on a live request," not any particular UI treatment.

5. **Stretch (only if 1–4 are done with time to spare)** — `train/train_lora.py` (new): short QLoRA fine-tune of Qwen2-VL-2B-Instruct (LLaMA-Factory or a minimal custom script) on a small slice of the VQA rows; save adapter to `models/bentxt_lora/`. Do not let this block or delay 1–4.

## Files touched/created
- `train/prepare_dataset.py`, `train/train_convnext.py`, `eval/run_eval.py` (new)
- `train/train_lora.py` (new, stretch only)
- `models/bentxt_convnext.pt`, optionally `models/bentxt_lora/` (generated artifacts — need a `models/.gitignore` since no `models/` dir exists yet in this repo)
- `backend/app/llm/local_classifier.py` (new) and small edits to `backend/app/chat/service.py` (and possibly `backend/app/llm/gemini.py`) to call it

## Verification
- `prepare_dataset.py`: print row counts before/after filtering and confirm zero `patch_id` overlap between train/val splits.
- `train_convnext.py`: training loss decreases across epochs; `eval/run_eval.py` prints a val accuracy number that isn't chance-level.
- Backend smoke test: run `uvicorn app.main:app --reload` in `backend/`, upload a real sample image through the existing `/sessions/{id}/assets` flow, and confirm the classifier's output appears in the response/logs for that specific request (not a hardcoded stub) — this is the concrete proof of "load-bearing."
- `cd backend && pytest` still passes after the integration change, so the existing chat/compatibility tests aren't broken.
