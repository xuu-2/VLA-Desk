"""测试微调(LoRA)和剪枝后的 Qwen2-VL 模型。

用法:
  # 测试基础模型
  python test_optimized.py

  # 测试 LoRA 微调模型
  python test_optimized.py --lora models/qwen-vl-lora

  # 测试剪枝模型
  python test_optimized.py --pruned models/qwen-vl-pruned

  # 同时测试 LoRA + 剪枝（先加载剪枝模型，再挂 LoRA）
  python test_optimized.py --pruned models/qwen-vl-pruned --lora models/qwen-vl-lora
"""
import argparse
import os
import time

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration


def load_model(base_model, lora_path=None, pruned_path=None):
    """加载模型，可选挂载 LoRA adapter 或加载剪枝模型。"""
    model_path = pruned_path if pruned_path else base_model
    print(f"⏳ 加载模型: {model_path}")

    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)

    if torch.cuda.is_available():
        dtype = torch.float16
        device = "cuda"
    else:
        dtype = torch.float32
        device = "cpu"

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_path,
        trust_remote_code=True,
        device_map=device,
        torch_dtype=dtype,
    )
    model.eval()

    # 挂载 LoRA adapter
    if lora_path:
        from peft import PeftModel
        print(f"⏳ 加载 LoRA adapter: {lora_path}")
        model = PeftModel.from_pretrained(model, lora_path)
        if hasattr(model, "merge_and_unload"):
            model = model.merge_and_unload()
            print("✅ LoRA 已合并到基础模型")
        model.eval()

    print(f"✅ 模型加载成功！设备: {device}")
    return model, processor


def run_inference(model, processor, image_path, question, max_new_tokens=256):
    """跑一次推理，返回回复文本和耗时。"""
    image = Image.open(image_path).convert("RGB")

    messages = [
        {"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": question},
        ]}
    ]

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=text, images=image, return_tensors="pt")
    inputs = {k: v.to(model.device) if hasattr(v, "to") else v for k, v in inputs.items()}

    start = time.time()
    with torch.inference_mode():
        outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False, use_cache=True)
    elapsed = time.time() - start

    response = processor.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return response, elapsed


def main():
    parser = argparse.ArgumentParser(description="测试微调/剪枝后的 Qwen2-VL 模型")
    parser.add_argument("--base", default="F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B",
                        help="基础模型路径")
    parser.add_argument("--lora", default=None, help="LoRA adapter 路径")
    parser.add_argument("--pruned", default=None, help="剪枝模型路径")
    parser.add_argument("--image", default="desk.jpg", help="测试图片路径")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"❌ 图片不存在: {args.image}")
        return

    # 标注当前模式
    mode = "基础模型"
    if args.pruned and args.lora:
        mode = "剪枝 + LoRA"
    elif args.lora:
        mode = "LoRA 微调"
    elif args.pruned:
        mode = "剪枝模型"
    print(f"=== 测试模式: {mode} ===\n")

    model, processor = load_model(args.base, lora_path=args.lora, pruned_path=args.pruned)

    # 多组测试
    test_cases = [
        ("描述一下这张图片里有什么物体？", "视觉描述"),
        ("请识别桌面上的主要物体，并用 JSON 返回。", "物体检测"),
        ("把杯子移到左边。", "指令解析"),
        ("拿起杯子。", "指令解析"),
    ]

    for question, category in test_cases:
        print(f"\n{'='*60}")
        print(f"📷 [{category}] {question}")
        response, elapsed = run_inference(model, processor, args.image, question)
        print(f"🤖 回复: {response}")
        print(f"⏱️ 耗时: {elapsed:.2f}s")

    # 显存统计
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
       # print(f"\n{'='*60}")
       #print(f"📊 显存占用: 已分配 {allocated:.2f} GB / 已保留 {reserved:.2f} GB")

    print(f"\n✅ {mode} 测试完成！")


if __name__ == "__main__":
    main()
