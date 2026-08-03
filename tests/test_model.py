import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
import os

print("⏳ 正在加载本地 Qwen2-VL-2B 模型...")

model_path = "F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B"

if not os.path.exists(model_path):
    print(f"❌ 路径不存在: {model_path}")
    exit()

try:
    processor = AutoProcessor.from_pretrained(
        model_path,
        trust_remote_code=True,
    )
    
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_path,
        trust_remote_code=True,
        device_map="cuda" if torch.cuda.is_available() else "cpu",
        torch_dtype=torch.bfloat16,
    )
    print("✅ 模型加载成功！")
except Exception as e:
    print(f"❌ 模型加载失败: {e}")
    import traceback
    traceback.print_exc()
    exit()

print("\n⏳ 测试推理...")
query = "你叫什么名字？"
inputs = processor(text=query, return_tensors="pt").to(model.device)
outputs = model.generate(**inputs, max_new_tokens=64)
response = processor.decode(outputs[0], skip_special_tokens=True)
print(f"🤖 模型回复: {response}")

print("\n✅ 测试完成！")