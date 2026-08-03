"""LoRA / QLoRA fine-tuning for Qwen2-VL (2B).

Usage:
  # 4-bit QLoRA 微调（8GB 显存推荐）
  python vl/finetune.py --model models/Qwen2-VL-2B --data data/qwen_vl_minimal_train.jsonl --output models/qwen-vl-lora --qlora
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from torch.utils.data import Dataset


# --------------------------------------------------------------------------- 数据
@dataclass
class Sample:
    image: str
    prompt: str
    response: str


class VLDataset(Dataset):
    """JSONL 格式数据集，每行: {"image": "path", "prompt": "...", "response": "..."}"""

    def __init__(self, jsonl_path: str, base_dir: Optional[str] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path(jsonl_path).resolve().parent
        self.samples: List[Sample] = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                img = item["image"]
                if not Path(img).is_absolute():
                    resolved = self.base_dir / img
                    if not resolved.exists():
                        resolved = self.base_dir.parent / img
                    img = str(resolved)
                self.samples.append(Sample(image=img, prompt=item["prompt"], response=item["response"]))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Sample:
        return self.samples[idx]


# --------------------------------------------------------------------------- 模型
def _resolve_dtype():
    if torch.cuda.is_available():
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return torch.float32


def build_lora_model(model_name: str, qlora: bool = False, trust_remote_code: bool = True):
    """加载 Qwen2-VL 并挂上 LoRA adapter。qlora=True 时用 4-bit 量化加载。"""
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, TaskType

    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=trust_remote_code)

    load_kwargs: Dict[str, Any] = {
        "trust_remote_code": trust_remote_code,
        "torch_dtype": _resolve_dtype(),
    }
    if torch.cuda.is_available():
        load_kwargs["device_map"] = "auto"
    else:
        load_kwargs["device_map"] = "cpu"

    if qlora and torch.cuda.is_available():
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=load_kwargs["torch_dtype"],
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        print("Using 4-bit QLoRA")

    model = Qwen2VLForConditionalGeneration.from_pretrained(model_name, **load_kwargs)

    # gradient checkpointing：用计算换显存，大幅降低 OOM 风险
    model.gradient_checkpointing_enable()
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    # 冻结所有参数，只训练 LoRA
    for p in model.parameters():
        p.requires_grad = False

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()
    return model, processor


# --------------------------------------------------------------------------- collator
def make_collate_fn(processor):
    from PIL import Image

    def collate(batch: List[Sample]) -> Dict[str, Any]:
        # 缩小图片到最大 448px，减少视觉 token 数量，大幅省显存
        images = []
        for s in batch:
            img = Image.open(s.image).convert("RGB")
            max_px = 448
            if max(img.size) > max_px:
                ratio = max_px / max(img.size)
                img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)))
            images.append(img)

        full_texts = []
        prompt_texts = []
        for s in batch:
            messages = [
                {"role": "user", "content": [
                    {"type": "image"},
                    {"type": "text", "text": s.prompt},
                ]},
                {"role": "assistant", "content": [{"type": "text", "text": s.response}]},
            ]
            full = processor.apply_chat_template(messages, tokenize=False)
            full_texts.append(full)

            prompt_msgs = [{"role": "user", "content": [
                {"type": "image"},
                {"type": "text", "text": s.prompt},
            ]}]
            prompt_only = processor.apply_chat_template(prompt_msgs, tokenize=False, add_generation_prompt=True)
            prompt_texts.append(prompt_only)

        inputs = processor(text=full_texts, images=images, return_tensors="pt", padding=True)

        # 构建 labels：prompt 部分设为 -100 (ignore)，只对 response 计 loss
        labels = inputs["input_ids"].clone()
        for i, prompt_text in enumerate(prompt_texts):
            prompt_ids = processor(text=prompt_text, images=images[i:i+1], return_tensors="pt")
            prompt_len = prompt_ids["input_ids"].shape[1]
            labels[i, :prompt_len] = -100

        inputs["labels"] = labels
        return inputs

    return collate


# --------------------------------------------------------------------------- 训练
def fine_tune(
    model_name: str,
    dataset_path: str,
    output_dir: str,
    epochs: int = 1,
    lr: float = 2e-5,
    qlora: bool = False,
) -> None:
    from transformers import Trainer, TrainingArguments

    print(f"Loading model: {model_name}")
    model, processor = build_lora_model(model_name, qlora=qlora)
    device = next(model.parameters()).device
    print(f"Model device: {device}")

    ds = VLDataset(dataset_path)
    print(f"Dataset: {len(ds)} samples")

    collate_fn = make_collate_fn(processor)

    training_kwargs: Dict[str, Any] = dict(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=lr,
        num_train_epochs=epochs,
        logging_steps=1,
        save_strategy="epoch",
        report_to="none",
        remove_unused_columns=False,
        dataloader_pin_memory=False,
        gradient_checkpointing=True,
    )
    if torch.cuda.is_available():
        training_kwargs["fp16"] = not torch.cuda.is_bf16_supported()
        training_kwargs["bf16"] = torch.cuda.is_bf16_supported()

    # 尝试用 8-bit Adam 优化器（bitsandbytes），省一半优化器显存
    optim = "adamw_8bit"
    try:
        import bitsandbytes  # noqa: F401
        training_kwargs["optim"] = optim
        print(f"Using optimizer: {optim}")
    except ImportError:
        print("bitsandbytes not available, using default optimizer")

    args = TrainingArguments(**training_kwargs)
    trainer = Trainer(model=model, args=args, train_dataset=ds, data_collator=collate_fn)

    print("Starting training ...")
    trainer.train()

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    processor.save_pretrained(out)
    print(f"LoRA adapter saved to {out}")
    print(f"To use: model = PeftModel.from_pretrained(base_model, '{out}')")


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA/QLoRA fine-tuning for Qwen2-VL-2B")
    parser.add_argument("--model", default="F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B",
                        help="Base model path or HF name")
    parser.add_argument("--data", required=True, help="JSONL dataset path")
    parser.add_argument("--output", required=True, help="Output directory for LoRA adapter")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--qlora", action="store_true", help="Use 4-bit QLoRA (saves VRAM)")
    args = parser.parse_args()
    fine_tune(args.model, args.data, args.output, epochs=args.epochs, lr=args.lr, qlora=args.qlora)


if __name__ == "__main__":
    main()
