"""Reproducible leave-one-scene-out experiments for the five S1S2-Water scenes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from training.train import train_s1s2_water

SCENES = ["1", "5", "6", "7", "8"]


def leave_one_scene_out_splits(scenes: list[str] = SCENES) -> list[tuple[list[str], list[str]]]:
    """Return exactly one leak-free held-out split for every supplied scene."""
    if len(set(scenes)) != len(scenes) or len(scenes) < 2:
        raise ValueError("LOSO requires at least two distinct scene IDs")
    return [([scene for scene in scenes if scene != held_out], [held_out]) for held_out in scenes]


def run_loso(
    data: str | Path,
    output_dir: str | Path,
    *, epochs: int = 5, batch_size: int = 8, lr: float = 1e-3,
    pos_weight: float = 1.0, seed: int = 42, device: str | None = None,
) -> list[dict[str, Any]]:
    """Train one baseline/configuration per held-out scene; never touches final checkpoint."""
    results: list[dict[str, Any]] = []
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for train_scenes, val_scenes in leave_one_scene_out_splits():
        held_out = val_scenes[0]
        result = train_s1s2_water(
            root_dir=data, train_scenes=train_scenes, val_scenes=val_scenes,
            checkpoint_path=output / f"loso_val_scene_{held_out}_pos_weight_{pos_weight:g}.pt",
            epochs=epochs, batch_size=batch_size, lr=lr, pos_weight=pos_weight,
            seed=seed, device=device,
        )
        results.append(result)
    (output / f"loso_pos_weight_{pos_weight:g}.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run five leak-free S1S2-Water LOSO experiments.")
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("S1S2_WATER_ROOT", "/content/S1S2-Water")))
    parser.add_argument("--output-dir", type=Path, default=Path("checkpoints/loso"))
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--pos-weight", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()
    if not args.data.is_dir():
        raise SystemExit(f"Real S1S2-Water data not found: {args.data}")
    run_loso(args.data, args.output_dir, epochs=args.epochs, batch_size=args.batch_size,
             lr=args.lr, pos_weight=args.pos_weight, seed=args.seed, device=args.device)


if __name__ == "__main__":
    main()
