"""
统一检测器接口。
所有检测器（YOLO、Qwen-VL、TensorRT）都继承这个基类，
app.py 可以无差别切换。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: List[float]      # [x1, y1, x2, y2]
    center: List[float]    # [cx, cy]


class BaseDetector(ABC):
    """所有检测器的统一接口。"""

    name: str = "base"

    @abstractmethod
    def load(self) -> None:
        """加载模型权重 / 引擎。"""

    @abstractmethod
    def detect(self, frame) -> List[Detection]:
        """对一帧（numpy BGR 或文件路径）做检测，返回 Detection 列表。"""

    def to_serializable(self, detections: List[Detection]) -> List[Dict[str, Any]]:
        return [
            {"label": d.label, "confidence": d.confidence, "bbox": d.bbox, "center": d.center}
            for d in detections
        ]

    def warmup(self) -> None:
        """可选：预热模型（跑一次空推理）。"""
        pass

    def release(self) -> None:
        """可选：释放资源。"""
        pass
