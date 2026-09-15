# Optical-SAR Training Track

This track consumes the already-prepared BigEarthNet metadata and LMDB. It does not rebuild the dataset-preparation notebook.

Install training dependencies in Colab or a GPU environment:

```bash
pip install -r training/requirements.txt
```

The loader expects metadata with:

- `patch_id`
- `labels`
- `split` or `split_text`
- `s1_name` when SAR is stored under a separate LMDB key

```python
from training.optical_sar_dataset import BigEarthNetFusionDataset, label_vocabulary, patch_metadata

dataset = BigEarthNetFusionDataset(
    metadata_path="/content/drive/MyDrive/SatQueryAI/dataset/training.csv",
    lmdb_path="/content/drive/MyDrive/SatQueryAI/dataset/BENv2_lithuania_summer.lmdb",
    split="train",
)
sample = dataset[0]
print(sample["optical"].shape, sample["sar"].shape, sample["label"].shape)
```

The loader first tries the `patch_id` record for both modalities. If that record does not contain `VV` and `VH`, it loads a separate record using `s1_name`. A missing modality raises an explicit error rather than silently training on optical-only data.

The initial model target is scene-level multilabel classification, not segmentation. Use `OpticalSarFusionClassifier` with `BCEWithLogitsLoss`, and compare optical-only, SAR-only, and fused variants before connecting any checkpoint to the application.

## Smoke test

From the repository root, run this in Colab or an environment with the training dependencies installed:

```bash
python -m training.smoke_test \
    --metadata /content/drive/MyDrive/SatQueryAI/dataset/training.csv \
    --lmdb /content/drive/MyDrive/SatQueryAI/dataset/BENv2_lithuania_summer.lmdb \
    --split train \
    --samples 20
```

This checks real samples, finite tensors, DataLoader batching, model forward shape, and `BCEWithLogitsLoss`. It does not train or create a checkpoint.

## Sanity training

After the smoke test passes, run the minimal two-epoch training check:

```bash
python -m training.sanity_train \
    --metadata /content/drive/MyDrive/SatQueryAI/dataset/training.csv \
    --lmdb /content/drive/MyDrive/SatQueryAI/dataset/BENv2_lithuania_summer.lmdb
```

It uses at most 200 training patches, batch size 8, AdamW, and `BCEWithLogitsLoss`, with one validation pass after each epoch. It prints only train and validation loss and does not save a checkpoint.

## Validation evaluation

Evaluate a trained classifier with sigmoid thresholding:

```bash
python -m training.evaluate_fusion \
    --metadata /content/drive/MyDrive/SatQueryAI/dataset/training.csv \
    --lmdb /content/drive/MyDrive/SatQueryAI/dataset/BENv2_lithuania_summer.lmdb \
    --checkpoint /content/fusion_model.pt \
    --threshold 0.5
```

The evaluator reports micro F1, macro F1, micro precision, and micro recall for all validation patches and separately for rows where `contains_cloud_or_shadow` is true. It uses the training-split label vocabulary and does not change the model or backend.