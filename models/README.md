# models/

Generated model artifacts go here. Nothing in this directory is checked into
git (see `.gitignore`) except this file — checkpoints are produced by
training runs on Kaggle, not committed to the repo.

- `bentxt_convnext.pt` — the fine-tuned ConvNeXt-tiny scene/land-cover
  classifier. Produced by `train/kaggle_notebook.ipynb` (or
  `train/train_convnext.py` run manually on Kaggle/Colab). See
  `train/README.md` for how to generate it. Once present here,
  `backend/app/llm/local_classifier.py` loads it automatically — no backend
  code or config changes needed.
- `bentxt_lora/` — optional stretch-goal QLoRA adapter from
  `train/train_lora.py`. Not consumed by the backend today.

If this file is missing, the backend's local classifier silently disables
itself (logs a warning) and the chat app keeps working normally via Gemini
alone — it's a soft dependency, not a hard requirement to run the app.
