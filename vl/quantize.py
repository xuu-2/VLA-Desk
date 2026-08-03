from __future__ import annotations

import argparse
from pathlib import Path


def quantize_model(
    model_name: str,
    output_dir: str,
    load_in_4bit: bool = True,
    trust_remote_code: bool = True,
) -> None:
    try:
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig
    except ImportError as e:
        raise ImportError("Install transformers, torch, bitsandbytes") from e

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=load_in_4bit,
        load_in_8bit=not load_in_4bit,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    ) if load_in_4bit else BitsAndBytesConfig(load_in_8bit=True)

    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=trust_remote_code)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_name,
        device_map="auto",
        trust_remote_code=trust_remote_code,
        quantization_config=bnb_config,
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    processor.save_pretrained(output)
    model.save_pretrained(output)
    print(f"Quantized model saved to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantize Qwen2.5-VL model")
    parser.add_argument("--model", default="Qwen/Qwen2.5-VL-3B-Instruct")
    parser.add_argument("--output", required=True)
    parser.add_argument("--bit", choices=["4", "8"], default="4")
    args = parser.parse_args()
    quantize_model(args.model, args.output, load_in_4bit=args.bit == "4")


if __name__ == "__main__":
    main()
