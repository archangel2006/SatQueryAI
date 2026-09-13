# Training — Kaggle only, never local

Per project decision: **no model training runs on a local dev machine.** The
dataset (`training.csv` + `BENv2_lithuania_summer.lmdb`) also isn't checked
into this repo — it lives in the team Google Drive — so these scripts can't
run locally even if you wanted them to.

The actual training happens on **Kaggle**, using
[`kaggle_notebook.ipynb`](./kaggle_notebook.ipynb) in this directory —
**one file**, fully self-contained (no repo/git access needed from Kaggle,
no auxiliary scripts written out at runtime — everything is inline).

## Quick start

1. Zip the shared `dataset/` folder (`training.csv` +
   `BENv2_lithuania_summer.lmdb/`) and upload it as a new Kaggle Dataset.
2. Upload [`kaggle_notebook.ipynb`](./kaggle_notebook.ipynb) as a new Kaggle
   Notebook, attach the dataset you just created as an input, and turn on a
   GPU accelerator (Settings → Accelerator → GPU T4).
3. Edit the `DATASET_DIR` line in the notebook's config cell to match your
   attached dataset's input path.
4. Run all cells top to bottom. The first `prepare_dataset.py` run is
   `--inspect-only` — read its printed `type`/`category` value counts before
   the real filtering run in case the default keyword filter needs
   adjusting for this CSV.
5. Download the resulting `bentxt_convnext.pt` from the Output tab and drop
   it into this repo at `models/bentxt_convnext.pt`. Nothing else needs to
   change — `backend/app/llm/local_classifier.py` loads it from that path
   automatically the next time the backend starts.

## Files

- `bigearthnet_lmdb.py` — shared helpers for reading patch tensors out of the
  LMDB and turning them into RGB uint8 images.
- `prepare_dataset.py` — filters `training.csv` to a scene/land-cover
  classification subset and does a leak-free patch-level train/val split.
- `train_convnext.py` — fine-tunes `timm`'s ConvNeXt-tiny (ImageNet
  pretrained) on that subset; saves a `.pt` checkpoint containing the model
  weights + label list.
- `train_lora.py` — **stretch goal only.** Best-effort short QLoRA fine-tune
  of Qwen2-VL-2B-Instruct on a slice of the VQA rows. Not required, not
  guaranteed to converge, must never block the ConvNeXt classifier above.
- `kaggle_notebook.ipynb` — **the one file to actually run on Kaggle.** All
  of the logic above (LMDB reading, filtering/split, dataset, model,
  training loop, eval) is inlined directly in its cells — it doesn't shell
  out to or depend on any of the `.py` files in this list.

The `.py` files exist for repo readability/reuse (e.g. if you'd rather run
training from a cloned repo on a GPU box instead of Kaggle's notebook UI —
`eval/run_eval.py`, one directory up, then also applies). They're a
reference implementation kept in sync with the notebook, not a dependency
of it.

## Why Kaggle and not Colab

Either works — the notebook only assumes a Linux box with a GPU and
`/kaggle/working`-style scratch space, which Colab also provides via
`/content`. Kaggle was chosen because Kaggle Datasets give free, versioned,
attachable storage for `training.csv` + the LMDB without needing to remount
Drive every session. If you'd rather use Colab, mount Drive per
`notebooks/data/SatQueryAI Dataset_README.md` and adjust the paths in the
notebook's config cell accordingly — the training/eval scripts themselves
don't care which platform ran them.
