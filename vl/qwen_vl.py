from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: List[float]
    center: List[float]


class QwenVLModel:
    def __init__(
        self,
        model_name: str = "F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B",
        device_map: str = "auto",
        torch_dtype: Optional[str] = None,
        offload_folder: Optional[str] = None,
        quantization: Optional[str] = None,
        lora_path: Optional[str] = None,
    ) -> None:
        self.model_name = model_name
        self.device_map = device_map
        self.torch_dtype = torch_dtype
        self.offload_folder = offload_folder
        self.quantization = quantization
        self.lora_path = lora_path
        self.processor = None
        self.model = None

    def load(self) -> None:
        try:
            import torch
            from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
        except ImportError as e:
            raise ImportError(
                "Qwen VL dependencies missing. Install: pip install transformers torch accelerate"
            ) from e

        self.processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)

        kwargs: Dict[str, Any] = {
            "device_map": self.device_map,
            "trust_remote_code": True,
        }
        if self.offload_folder:
            kwargs["offload_folder"] = self.offload_folder
        if self.torch_dtype:
            kwargs["torch_dtype"] = getattr(torch, self.torch_dtype)
        else:
            kwargs["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32

        if self.quantization == "4bit":
            try:
                from transformers import BitsAndBytesConfig
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=kwargs["torch_dtype"],
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
            except Exception as e:
                raise RuntimeError(f"4-bit quantization requested but unavailable: {e}")
        elif self.quantization == "8bit":
            try:
                from transformers import BitsAndBytesConfig
                kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
            except Exception as e:
                raise RuntimeError(f"8-bit quantization requested but unavailable: {e}")

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(self.model_name, **kwargs)

        # 挂载 LoRA adapter（如果指定了路径且存在）
        if self.lora_path and os.path.isdir(self.lora_path):
            try:
                from peft import PeftModel
                self.model = PeftModel.from_pretrained(self.model, self.lora_path)
                if hasattr(self.model, "merge_and_unload"):
                    self.model = self.model.merge_and_unload()
                print(f"✅ LoRA adapter 已加载并合并: {self.lora_path}")
            except Exception as e:
                print(f"⚠️ LoRA adapter 加载失败，使用基础模型: {e}")

        self.model.eval()

    def _ensure_loaded(self) -> None:
        if self.model is None or self.processor is None:
            self.load()

    def _chat(self, image: Optional[Image.Image], prompt: str, max_new_tokens: int = 256) -> str:
        self._ensure_loaded()
        assert self.processor is not None and self.model is not None

        import torch

        messages = [{"role": "user", "content": []}]
        if image is not None:
            messages[0]["content"].append({"type": "image", "image": image})
        messages[0]["content"].append({"type": "text", "text": prompt})

        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[image] if image is not None else None, return_tensors="pt")
        # device_map="auto" 时由 Accelerate 负责放置输入，避免手动移动到 meta device。
        input_device = next(self.model.parameters()).device
        inputs = {k: v.to(input_device) if hasattr(v, "to") else v for k, v in inputs.items()}

        with torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                use_cache=True,
            )

        input_len = inputs["input_ids"].shape[1]
        out = self.processor.batch_decode(generated[:, input_len:], skip_special_tokens=True)[0]
        return out

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取 JSON，支持简单嵌套。"""
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start:end+1]
            try:
                return json.loads(candidate)
            except Exception:
                # 逐步缩小范围尝试
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start:i+1])
                            except Exception:
                                pass
                            start = text.find("{", i)
                pass
        return None

    # --- 物体名称中英对照 ---
    OBJECT_KEYWORDS = {
        "cup": ["杯子", "保温杯", "水杯", "cup"],
        "mug": ["马克杯", "mug"],
        "bottle": ["瓶子", "保温壶", "水壶", "bottle"],
        "phone": ["手机", "phone"],
        "mouse": ["鼠标", "mouse"],
        "keyboard": ["键盘", "keyboard"],
        "book": ["书", "book"],
        "pen": ["笔", "pen"],
        "pencil": ["铅笔", "pencil"],
        "scissors": ["剪刀", "scissors"],
        "bowl": ["碗", "bowl"],
        "plate": ["盘子", "plate"],
        "box": ["盒子", "box"],
        "charger": ["充电器", "charger"],
        "cable": ["线", "cable"],
        "laptop": ["笔记本电脑", "laptop"],
        "monitor": ["显示器", "monitor"],
        "speaker": ["音箱", "speaker"],
        "headphones": ["耳机", "headphones"],
        "watch": ["手表", "watch"],
        "wallet": ["钱包", "wallet"],
        "key": ["钥匙", "key"],
        "glasses": ["眼镜", "glasses"],
        "remote": ["遥控器", "remote"],
        "can": ["罐", "can"],
        "jar": ["罐子", "jar"],
        "container": ["容器", "container"],
    }

    @classmethod
    def _extract_objects_from_text(cls, text: str) -> List[Dict[str, Any]]:
        """从自然语言描述中提取物体。"""
        text_lower = text.lower()
        found = []
        seen = set()
        for label, keywords in cls.OBJECT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower and label not in seen:
                    seen.add(label)
                    found.append({
                        "label": label,
                        "confidence": 0.75,
                        "bbox": [0, 0, 0, 0],
                        "center": [0, 0],
                    })
                    break
        return found

    def detect(self, image_path: str) -> List[Detection]:
        img = Image.open(image_path).convert("RGB")

        # 先尝试让模型输出 JSON
        prompt_json = (
            "请仔细观察这张桌面图片，识别出所有主要物体。\n"
            "只返回 JSON，不要任何其他文字。格式如下：\n"
            '{"type":"detection","objects":[{"label":"杯子","confidence":0.9,"bbox":[x1,y1,x2,y2],"center":[cx,cy]}]}\n'
            "其中 bbox 是物体的边界框 [x1,y1,x2,y2]，center 是中心点 [cx,cy]，"
            "坐标基于图片像素。"
        )
        out = self._chat(img, prompt_json, max_new_tokens=512)

        # 尝试从 JSON 提取
        data = self._extract_json(out)
        if data and (data.get("type") == "detection" or "objects" in data):
            objects = data.get("objects", data.get("detections", []))
            dets: List[Detection] = []
            for obj in objects:
                try:
                    dets.append(Detection(
                        label=str(obj.get("label", "object")),
                        confidence=float(obj.get("confidence", 0.5)),
                        bbox=[float(x) for x in obj.get("bbox", [0, 0, 0, 0])],
                        center=[float(x) for x in obj.get("center", [0, 0])],
                    ))
                except Exception:
                    pass
            if dets:
                return dets

        # JSON 失败，回退到自然语言描述提取
        prompt_desc = "请简洁列出这张图片里的所有物体名称，每行一个。"
        out_desc = self._chat(img, prompt_desc, max_new_tokens=256)
        objects = self._extract_objects_from_text(out_desc)

        # 如果描述法也没找到，再用第一次的输出再试一次
        if not objects:
            objects = self._extract_objects_from_text(out)

        return [
            Detection(
                label=obj["label"],
                confidence=obj["confidence"],
                bbox=obj["bbox"],
                center=obj["center"],
            )
            for obj in objects
        ]

    def parse_instruction(self, instruction: str) -> Dict[str, Any]:
        prompt = (
            "请将以下桌面机器人指令解析为 JSON，只返回 JSON，不要其他文字。格式：\n"
            '{"type":"task","action":"pick|place|move|inspect","target":"物体名","destination":"可选目标位置"}\n\n'
            f"指令：{instruction}"
        )
        out = self._chat(None, prompt, max_new_tokens=128)
        data = self._extract_json(out)
        if data is None:
            # 回退到关键词匹配
            inst_lower = instruction.lower()
            action = "inspect"
            if "拿" in instruction or "抓" in instruction or "pick" in inst_lower:
                action = "pick"
            elif "放" in instruction or "place" in inst_lower:
                action = "place"
            elif "移" in instruction or "move" in inst_lower:
                action = "move"
            target = "object"
            for label, keywords in self.OBJECT_KEYWORDS.items():
                for kw in keywords:
                    if kw in instruction or kw.lower() in inst_lower:
                        target = label
                        break
                if target != "object":
                    break
            data = {"type": "task", "action": action, "target": target}
        if data.get("type") != "task":
            data = {"type": "task", **data}
        return data

    def detect_and_visualize(self, image_source: str, save_path: Optional[str] = None) -> List[Detection]:
        dets = self.detect(image_source)
        if save_path:
            import cv2
            img = cv2.imread(image_source)
            for d in dets:
                if d.bbox != [0, 0, 0, 0]:
                    x1, y1, x2, y2 = map(int, d.bbox)
                    cx, cy = map(int, d.center)
                    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.circle(img, (cx, cy), 4, (0, 0, 255), -1)
                    cv2.putText(img, f"{d.label} {d.confidence:.2f}", (x1, max(10, y1 - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.imwrite(save_path, img)
        return dets

    def to_serializable(self, detections: Sequence[Detection]) -> List[Dict[str, Any]]:
        return [dat.__dict__ for dat in detections]
