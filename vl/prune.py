"""Structured pruning for Qwen2-VL-2B.

Prunes MLP and attention linear layers by magnitude (L1 norm of output neurons),
physically shrinking layer dimensions. Only targets the LLM decoder — the vision
encoder is left untouched to preserve visual feature quality.

Usage:
  python vl/prune.py --model models/Qwen2-VL-2B --output models/qwen-vl-pruned --sparsity 0.1
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import torch
from torch import nn


def magnitude_prune_linear(layer: nn.Linear, sparsity: float) -> nn.Linear | None:
    """Remove entire output neurons (rows of weight) with smallest L1 norm."""
    with torch.no_grad():
        weight = layer.weight.data
        num_out = weight.shape[0]
        num_prune = int(round(num_out * sparsity))
        if num_prune == 0 or num_prune >= num_out:
            return None

        norms = weight.abs().sum(dim=1)
        threshold = torch.kthvalue(norms, num_prune).values
        mask = norms > threshold
        indices = mask.nonzero(as_tuple=True)[0]

        new_layer = nn.Linear(
            in_features=layer.in_features,
            out_features=len(indices),
            bias=(layer.bias is not None),
        )
        new_layer.weight.data = weight[indices].clone()
        if layer.bias is not None:
            new_layer.bias.data = layer.bias.data[indices].clone()
        return new_layer


def prune_model(
    model: nn.Module,
    sparsity: float = 0.1,
    target_keywords: Tuple[str, ...] = ("mlp.gate_proj", "mlp.up_proj", "mlp.down_proj", "self_attn.q_proj", "self_attn.v_proj"),
    skip_keywords: Tuple[str, ...] = ("visual", "vision", "merger", "patch"),
) -> nn.Module:
    """Apply structured pruning to LLM decoder linear layers (skip vision encoder)."""
    pruned = 0
    total = 0
    for name, module in list(model.named_modules()):
        if not isinstance(module, nn.Linear):
            continue
        if not any(kw in name for kw in target_keywords):
            continue
        if any(kw in name for kw in skip_keywords):
            continue

        total += 1
        new_layer = magnitude_prune_linear(module, sparsity)
        if new_layer is None:
            continue

        parent_name, _, child_name = name.rpartition(".")
        parent = model.get_submodule(parent_name) if parent_name else model
        setattr(parent, child_name, new_layer)
        pruned += 1

    print(f"Pruned {pruned}/{total} linear layers (sparsity={sparsity})")
    return model


def prune_and_save(
    model_name: str,
    output_dir: str,
    sparsity: float = 0.1,
    trust_remote_code: bool = True,
) -> None:
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=trust_remote_code)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_name,
        device_map="cpu",
        trust_remote_code=trust_remote_code,
        torch_dtype=torch.float32,
    )
    prune_model(model, sparsity=sparsity)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    processor.save_pretrained(out)
    model.save_pretrained(out)
    print(f"Pruned model saved to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Structured pruning for Qwen2-VL-2B")
    parser.add_argument("--model", default="F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B")
    parser.add_argument("--output", required=True)
    parser.add_argument("--sparsity", type=float, default=0.1,
                        help="Fraction of neurons to prune (0.0-1.0). Start with 0.1")
    args = parser.parse_args()
    prune_and_save(args.model, args.output, sparsity=args.sparsity)


if __name__ == "__main__":
    main()
