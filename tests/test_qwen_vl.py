import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

print("⏳ 正在加载 Qwen2-VL-2B 模型...")
model_path = "Qwen/Qwen2-VL-2B-Instruct"

try:
    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_path,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    print("✅ 模型加载成功！")
except Exception as e:
    print(f"❌ 模型加载失败: {e}")
    exit()

print("\n⏳ 测试纯文本推理...")
query = "你叫什么名字？"
inputs = processor(text=query, return_tensors="pt").to(model.device)
outputs = model.generate(**inputs, max_new_tokens=64)
response = processor.decode(outputs[0], skip_special_tokens=True)
print(f"🤖 模型回复: {response}")

print("\n✅ Qwen2-VL-2B 测试完成！")