#!/usr/bin/env python
"""STRETCH GOAL — best-effort, short QLoRA fine-tune of Qwen2-VL-2B-Instruct on a
small slice of the VQA rows in training.csv.

Not guaranteed to converge (or even finish cleanly) in a Kaggle session's
time/memory budget — this is explicitly optional per plan.md and must not
block train_convnext.py or the backend integration, which are the required
deliverables. Only run this if you have time left over after those are done.

DO NOT RUN LOCALLY. Needs a GPU (a T4 16GB is enough for 4-bit QLoRA on the
2B model) and the dataset. See train/README.md.

Usage (on Kaggle):
    pip install -U transformers peft bitsandbytes accelerate
    python train_lora.py \
        --csv /kaggle/input/satqueryai-dataset/training.csv \
        --lmdb /kaggle/input/satqueryai-dataset/BENv2_lithuania_summer.lmdb \
        --output-dir /kaggle/working/bentxt_lora \
        --max-rows 400 --max-steps 200
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bigearthnet_lmdb import load_patch_sample, open_lmdb_env, sample_to_rgb_uint8  # noqa: E402

VQA_TYPE_KEYWORDS = ["vqa", "binary", "mcq", "grounding", "bounding", "caption"]


def build_rows(csv_path: str, lmdb_path: str, max_rows: int, type_keywords: list[str], seed: int) -> list[dict]:
    df = pd.read_csv(csv_path)
    typ = df["type"].astype(str).str.lower()
    mask = typ.apply(lambda v: any(k in v for k in type_keywords))
    n_match = int(mask.sum())
    if n_match == 0:
        return []
    subset = df[mask].sample(n=min(max_rows, n_match), random_state=seed)

    env = open_lmdb_env(lmdb_path)
    rows = []
    for _, row in subset.iterrows():
        sample = load_patch_sample(env, row["patch_id"])
        if sample is None:
            continue
        rgb = sample_to_rgb_uint8(sample)
        rows.append(
            {
                "image": Image.fromarray(rgb),
                "question": str(row["input"]),
                "answer": str(row["output"]),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", required=True)
    parser.add_argument("--lmdb", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-model", default="Qwen/Qwen2-VL-2B-Instruct")
    parser.add_argument("--max-rows", type=int, default=400)
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--type-keywords", nargs="*", default=VQA_TYPE_KEYWORDS)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoProcessor,
        BitsAndBytesConfig,
        Qwen2VLForConditionalGeneration,
        Trainer,
        TrainingArguments,
    )

    print("Building training examples from CSV + LMDB (this may take a minute)...")
    rows = build_rows(args.csv, args.lmdb, args.max_rows, args.type_keywords, args.seed)
    print(f"Built {len(rows)} VQA training examples.")
    if not rows:
        print(
            "No rows matched --type-keywords; inspect training.csv['type'].value_counts() "
            "(see prepare_dataset.py --inspect-only) and retry with matching keywords."
        )
        return

    processor = AutoProcessor.from_pretrained(args.base_model)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        args.base_model, quantization_config=bnb_config, device_map="auto"
    )
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    def collate(batch):
        texts, images = [], []
        for ex in batch:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": ex["question"]},
                    ],
                }
            ]
            prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            texts.append(prompt + ex["answer"])
            images.append(ex["image"])
        enc = processor(text=texts, images=images, return_tensors="pt", padding=True)
        enc["labels"] = enc["input_ids"].clone()
        return enc

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        max_steps=args.max_steps,
        learning_rate=args.lr,
        logging_steps=10,
        save_strategy="no",
        bf16=True,
        report_to=[],
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=rows, data_collator=collate)
    trainer.train()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output_dir)
    processor.save_pretrained(args.output_dir)
    print(f"Saved LoRA adapter to {args.output_dir}")


if __name__ == "__main__":
    main()
