import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from PIL import Image
import os

# ===== 自动选择 CPU / GPU =====
if torch.cuda.is_available():
    device = "cuda"
    torch_dtype = torch.float16
    print(f"🟢 检测到 GPU: {torch.cuda.get_device_name(0)}")
else:
    device = "cpu"
    torch_dtype = torch.float32
    print("🟡 未检测到 GPU，使用 CPU（推理会很慢）")

print("⏳ 加载模型...")
model_path = "F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B"

processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
model = Qwen2VLForConditionalGeneration.from_pretrained(
    model_path,
    trust_remote_code=True,
    device_map=device,
    torch_dtype=torch_dtype,
)
model.eval()

print(f"✅ 模型加载成功！设备: {model.device}, dtype: {torch_dtype}")

# 用一张测试图片
image_path = "desk.jpg"  # 项目根目录下的图片

if not os.path.exists(image_path):
    print(f"❌ 图片不存在: {image_path}")
    print("请放一张图片在项目根目录，命名为 desk.jpg")
    exit()

print(f"\n📷 加载图片: {image_path}")
image = Image.open(image_path).convert("RGB")

# 多模态 prompt
query = "描述一下这张图片里有什么物体？"
print(f"\n💬 问题: {query}")

messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": query},
        ]
    }
]

# Qwen2-VL 的对话格式
text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = processor(text=text, images=image, return_tensors="pt").to(model.device)

print("⏳ 推理中...")
with torch.inference_mode():
    outputs = model.generate(
        **inputs,
        max_new_tokens=256,
        do_sample=False,
        use_cache=True,
    )
response = processor.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(f"🤖 模型回复: {response}")

# GPU 显存占用
if torch.cuda.is_available():
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
   # print(f"📊 显存占用: 已分配 {allocated:.2f} GB / 已保留 {reserved:.2f} GB")

print("\n✅ 多模态测试完成！")
