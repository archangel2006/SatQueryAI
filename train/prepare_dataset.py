#!/usr/bin/env python
"""Filter the raw SatQuery training.csv down to a fast-training scene/land-cover
classification subset, with a leak-free patch-level train/val split.

DO NOT RUN THIS ON A LOCAL DEV MACHINE. `training.csv` and
`BENv2_lithuania_summer.lmdb` are not in this repo checkout — they live in
the team Google Drive / a Kaggle dataset. Run this on Kaggle (see
train/README.md and train/kaggle_notebook.ipynb) or Colab with the dataset
attached.

Step 1: inspect what's actually in the CSV before filtering:
    python prepare_dataset.py --csv /path/to/training.csv --lmdb /path/to/BENv2_lithuania_summer.lmdb \
        --output-dir /tmp/prepared --inspect-only

That prints value counts for `type` and `category` so you can confirm which
values mean "scene/land-cover classification" (as opposed to VQA, grounding,
or bounding-box tasks) in this particular CSV, and pass matching
--category-keywords / --type-keywords if the defaults below don't match.

Step 2: run for real (drop --inspect-only):
    python prepare_dataset.py --csv /path/to/training.csv --lmdb /path/to/BENv2_lithuania_summer.lmdb \
        --output-dir /path/to/prepared
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bigearthnet_lmdb import load_patch_sample, open_lmdb_env  # noqa: E402

DEFAULT_CATEGORY_KEYWORDS = [
    "land cover",
    "land-cover",
    "landcover",
    "scene",
    "classif",
    "dominant",
    "predominant",
]


def inspect(df: pd.DataFrame) -> None:
    print(f"Loaded {len(df)} rows, {df['patch_id'].nunique()} unique patch_ids.")
    print("\n--- df['type'].value_counts() ---")
    print(df["type"].value_counts(dropna=False))
    print("\n--- df['category'].value_counts() ---")
    print(df["category"].value_counts(dropna=False))
    print(
        "\nInspect the values above. If none of them obviously mean "
        "'scene/land-cover classification' (as opposed to VQA, grounding, or "
        "bounding-box tasks), pass --category-keywords / --type-keywords to "
        "override the default filter, then re-run without --inspect-only."
    )


def filter_classification_rows(
    df: pd.DataFrame,
    category_keywords: list[str],
    type_keywords: list[str],
) -> pd.DataFrame:
    cat = df["category"].astype(str).str.lower()
    typ = df["type"].astype(str).str.lower()
    cat_mask = (
        cat.apply(lambda v: any(k in v for k in category_keywords))
        if category_keywords
        else pd.Series(False, index=df.index)
    )
    type_mask = (
        typ.apply(lambda v: any(k in v for k in type_keywords))
        if type_keywords
        else pd.Series(False, index=df.index)
    )
    return df[cat_mask | type_mask].copy()


def dedupe_to_one_row_per_patch(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Keep exactly one QA row per patch_id (its `output` becomes the class label)."""
    return (
        df.sample(frac=1.0, random_state=seed)
        .drop_duplicates(subset="patch_id", keep="first")
        .reset_index(drop=True)
    )


def drop_rare_labels(df: pd.DataFrame, label_col: str, min_count: int) -> pd.DataFrame:
    counts = df[label_col].value_counts()
    keep = counts[counts >= min_count].index
    return df[df[label_col].isin(keep)].copy()


def stratified_subset(df: pd.DataFrame, label_col: str, max_rows: int, seed: int) -> pd.DataFrame:
    if len(df) <= max_rows:
        return df
    frac = max_rows / len(df)
    return (
        df.groupby(label_col, group_keys=False)
        .apply(lambda g: g.sample(frac=frac, random_state=seed) if len(g) > 1 else g)
        .reset_index(drop=True)
    )


def patch_level_split(df: pd.DataFrame, val_frac: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    patch_ids = df["patch_id"].unique()
    rng = np.random.default_rng(seed)
    rng.shuffle(patch_ids)
    n_val = max(1, int(len(patch_ids) * val_frac))
    val_ids = set(patch_ids[:n_val])
    train_df = df[~df["patch_id"].isin(val_ids)].copy()
    val_df = df[df["patch_id"].isin(val_ids)].copy()
    overlap = set(train_df["patch_id"]) & set(val_df["patch_id"])
    assert not overlap, f"Leaky split: {len(overlap)} patch_ids in both train and val."
    return train_df, val_df


def validate_lmdb_join(df: pd.DataFrame, lmdb_path: str, sample_size: int = 20) -> None:
    env = open_lmdb_env(lmdb_path)
    n_ids = df["patch_id"].nunique()
    sample_ids = df["patch_id"].drop_duplicates().sample(n=min(sample_size, n_ids), random_state=0)

    missing = 0
    first_keys = None
    for pid in sample_ids:
        sample = load_patch_sample(env, pid)
        if sample is None:
            missing += 1
        elif first_keys is None:
            first_keys = sorted(sample.keys())

    print(f"LMDB join check: {missing}/{len(sample_ids)} sampled patch_ids missing from LMDB.")
    if first_keys is not None:
        print(f"Sample tensor keys (verify against bigearthnet_lmdb.py band constants): {first_keys}")
    if missing:
        print(
            "WARNING: some patch_ids in the filtered CSV are not present in the LMDB. "
            "Those rows will fail at training time."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", required=True, help="Path to training.csv")
    parser.add_argument("--lmdb", required=True, help="Path to BENv2_lithuania_summer.lmdb directory")
    parser.add_argument("--output-dir", required=True, help="Where to write train.csv / val.csv / labels.json")
    parser.add_argument("--inspect-only", action="store_true", help="Print type/category value counts and exit")
    parser.add_argument("--category-keywords", nargs="*", default=DEFAULT_CATEGORY_KEYWORDS)
    parser.add_argument("--type-keywords", nargs="*", default=[])
    parser.add_argument("--label-column", default="output", help="Column to use as the classification label")
    parser.add_argument("--min-label-count", type=int, default=20)
    parser.add_argument("--max-rows", type=int, default=4000)
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    print(f"Loaded {len(df)} rows / {df['patch_id'].nunique()} patches from {args.csv}")

    if args.inspect_only:
        inspect(df)
        return

    filtered = filter_classification_rows(df, args.category_keywords, args.type_keywords)
    print(f"After type/category filter: {len(filtered)} rows / {filtered['patch_id'].nunique()} patches")
    if filtered.empty:
        print(
            "No rows matched the filter. Re-run with --inspect-only to see the actual "
            "type/category values in this CSV, then pass matching --category-keywords / --type-keywords."
        )
        return

    filtered[args.label_column] = filtered[args.label_column].astype(str).str.strip()
    deduped = dedupe_to_one_row_per_patch(filtered, args.seed)
    print(f"After one-row-per-patch dedupe: {len(deduped)} rows")

    cleaned = drop_rare_labels(deduped, args.label_column, args.min_label_count)
    print(
        f"After dropping labels with < {args.min_label_count} examples: "
        f"{len(cleaned)} rows, {cleaned[args.label_column].nunique()} classes"
    )
    if cleaned.empty:
        print("Nothing left after dropping rare labels — lower --min-label-count and retry.")
        return

    subset = stratified_subset(cleaned, args.label_column, args.max_rows, args.seed)
    print(f"After subsetting to <= {args.max_rows} rows: {len(subset)} rows")

    train_df, val_df = patch_level_split(subset, args.val_frac, args.seed)
    print(f"Train: {len(train_df)} rows / {train_df['patch_id'].nunique()} patches")
    print(f"Val:   {len(val_df)} rows / {val_df['patch_id'].nunique()} patches")
    print("Zero patch_id overlap between train/val confirmed (asserted above).")

    validate_lmdb_join(subset, args.lmdb)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_df.to_csv(out_dir / "train.csv", index=False)
    val_df.to_csv(out_dir / "val.csv", index=False)
    labels = sorted(subset[args.label_column].unique())
    (out_dir / "labels.json").write_text(json.dumps(labels, indent=2))
    print(f"Wrote {out_dir / 'train.csv'}, {out_dir / 'val.csv'}, {out_dir / 'labels.json'}")


if __name__ == "__main__":
    main()
