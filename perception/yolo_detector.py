"""
YOLOv8 Object Detector for VLA-Desk Project

Supports three backends:
  - pytorch:  Ultralytics YOLO .pt
  - onnx:    ONNXRuntime .onnx (GPU or CPU)
  - tensorrt: TensorRT .engine (if available)

All backends share the same detect() interface and return List[Detection].
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import cv2
import numpy as np

from .detector_base import BaseDetector, Detection


# COCO 80 class names (YOLOv8 default)
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]


class YOLODetector(BaseDetector):
    """YOLO-based object detector supporting PyTorch / ONNX / TensorRT backends."""

    name = "yolo"

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.5,
        backend: str = "pytorch",
    ) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.backend = backend
        self.model: Optional[Any] = None
        self.trt_backend = None
        self.onnx_session = None
        self.onnx_input_name = None
        self.onnx_output_name = None
        self.onnx_img_size = 640
        self.class_names = COCO_NAMES

    def load(self) -> None:
        if self.backend == "onnx" or str(self.model_path).endswith(".onnx"):
            self._load_onnx()
        elif self.backend == "tensorrt" or str(self.model_path).endswith(".engine"):
            self._load_tensorrt()
        else:
            self._load_pytorch()

    def load_model(self) -> None:
        """Backward-compatible alias."""
        self.load()

    # ------------------------------------------------------------------ PyTorch
    def _load_pytorch(self) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise ImportError("ultralytics not installed: pip install ultralytics") from e
        print(f"Loading YOLO (PyTorch): {self.model_path}")
        self.model = YOLO(self.model_path)
        print("PyTorch YOLO loaded.")

    # ------------------------------------------------------------------ ONNX
    def _load_onnx(self) -> None:
        try:
            import onnxruntime as ort
        except ImportError as e:
            raise ImportError("onnxruntime not installed: pip install onnxruntime-gpu") from e
        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"ONNX model not found: {self.model_path}")

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        print(f"Loading YOLO (ONNX): {self.model_path}")
        self.onnx_session = ort.InferenceSession(self.model_path, providers=providers)
        self.onnx_input_name = self.onnx_session.get_inputs()[0].name
        self.onnx_output_name = self.onnx_session.get_outputs()[0].name

        # 推断输入尺寸
        shape = self.onnx_session.get_inputs()[0].shape
        if len(shape) == 4 and shape[2] != -1:
            self.onnx_img_size = int(shape[2])
        print(f"ONNX YOLO loaded (img_size={self.onnx_img_size}, providers={providers}).")

    # ------------------------------------------------------------------ TensorRT
    def _load_tensorrt(self) -> None:
        from inference.inference_backend import TensorRTBackend
        self.trt_backend = TensorRTBackend(self.model_path)
        if not self.trt_backend.load():
            raise RuntimeError(f"Failed to load TensorRT engine: {self.model_path}")
        print(f"TensorRT YOLO loaded: {self.model_path}")

    # ------------------------------------------------------------------ detect
    def detect(self, image_source) -> List[Detection]:
        if self.model is None and self.onnx_session is None and self.trt_backend is None:
            self.load_model()

        if isinstance(image_source, str):
            if not Path(image_source).exists():
                raise FileNotFoundError(f"Image not found: {image_source}")

        if self.onnx_session is not None:
            return self._detect_onnx(image_source)
        elif self.trt_backend is not None:
            return self._detect_tensorrt(image_source)
        else:
            return self._detect_pytorch(image_source)

    def _detect_pytorch(self, image_source) -> List[Detection]:
        results = self.model(image_source, conf=self.confidence_threshold, verbose=False)
        dets: List[Detection] = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                cls = int(box.cls[0].cpu().numpy())
                label = result.names[cls]
                dets.append(Detection(
                    label=label, confidence=conf,
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                    center=[float((x1 + x2) / 2), float((y1 + y2) / 2)],
                ))
        return dets

    def _detect_onnx(self, image_source) -> List[Detection]:
        if isinstance(image_source, str):
            img = cv2.imread(image_source)
        else:
            img = image_source
        if img is None:
            return []

        orig_h, orig_w = img.shape[:2]
        inp = self._preprocess_onnx(img)
        outputs = self.onnx_session.run(None, {self.onnx_input_name: inp})
        return self._postprocess_onnx(outputs[0], orig_w, orig_h)

    def _preprocess_onnx(self, img: np.ndarray) -> np.ndarray:
        """resize / letterbox / normalize / transpose / add batch dim."""
        sz = self.onnx_img_size
        # 简单 resize（不用 letterbox，足够快，精度影响小）
        resized = cv2.resize(img, (sz, sz))
        # BGR -> RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # HWC -> CHW, normalize
        chw = rgb.transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.ascontiguousarray(chw[np.newaxis])

    def _postprocess_onnx(self, output: np.ndarray, orig_w: int, orig_h: int) -> List[Detection]:
        """
        YOLOv8 ONNX output shape: (1, 84, 8400)
          84 = 4 (xywh) + 80 (classes)
          8400 = anchor points

        我们做：
          1. 按置信度过滤
          2. xywh -> xyxy
          3. 按原图尺寸缩放坐标
          4. NMS
        """
        # output: (1, 84, 8400) -> (8400, 84)
        pred = output[0].T  # (8400, 84)

        # 分离 box 和 class scores
        boxes_xywh = pred[:, :4]       # (8400, 4)
        class_scores = pred[:, 4:]    # (8400, 80)

        # 每个 anchor 的最大类别分数
        max_scores = class_scores.max(axis=1)  # (8400,)

        # 按阈值过滤
        mask = max_scores > self.confidence_threshold
        if not mask.any():
            return []

        boxes = boxes_xywh[mask]          # (N, 4)
        scores = max_scores[mask]        # (N,)
        cls_ids = class_scores[mask].argmax(axis=1)  # (N,)

        # xywh -> xyxy
        xyxy = np.zeros_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2  # x1
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2  # y1
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2  # x2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2  # y2

        # 按原图缩放
        sx = orig_w / self.onnx_img_size
        sy = orig_h / self.onnx_img_size
        xyxy[:, 0] *= sx
        xyxy[:, 2] *= sx
        xyxy[:, 1] *= sy
        xyxy[:, 3] *= sy

        # NMS（简单 IoU NMS，IoU 阈值 0.45）
        keep = self._nms(xyxy, scores, iou_threshold=0.45)

        dets: List[Detection] = []
        for idx in keep:
            x1, y1, x2, y2 = xyxy[idx]
            dets.append(Detection(
                label=self.class_names[cls_ids[idx]] if cls_ids[idx] < len(self.class_names) else f"class_{cls_ids[idx]}",
                confidence=float(scores[idx]),
                bbox=[float(x1), float(y1), float(x2), float(y2)],
                center=[float((x1 + x2) / 2), float((y1 + y2) / 2)],
            ))
        return dets

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> List[int]:
        """简单 NMS，返回保留的索引列表。"""
        if len(boxes) == 0:
            return []
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep: List[int] = []
        while order.size > 0:
            i = order[0]
            keep.append(int(i))
            if order.size == 1:
                break
            # IoU
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            inter = w * h
            iou = inter / (areas[i] + areas[order[1:]] - inter)
            order = order[1:][iou <= iou_threshold]
        return keep

    def _detect_tensorrt(self, image_source) -> List[Detection]:
        if isinstance(image_source, str):
            img = cv2.imread(image_source)
        else:
            img = image_source
        if img is None:
            return []
        inp = cv2.resize(img, (self.trt_backend.input_shape[-1], self.trt_backend.input_shape[-2]))
        inp = inp.transpose(2, 0, 1).astype(np.float32) / 255.0
        inp = np.ascontiguousarray(inp[np.newaxis])
        outputs = self.trt_backend.infer(inp)
        return self._postprocess_onnx(outputs[0], img.shape[1], img.shape[0])

    # ------------------------------------------------------------------ visualize
    def detect_and_visualize(self, image_source: str, save_path: Optional[str] = None) -> List[Detection]:
        detections = self.detect(image_source)

        if save_path:
            if isinstance(image_source, str):
                img = cv2.imread(image_source)
            else:
                img = image_source.copy()
            for det in detections:
                x1, y1, x2, y2 = map(int, det.bbox)
                cx, cy = map(int, det.center)
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.circle(img, (cx, cy), 5, (0, 0, 255), -1)
                cv2.putText(img, f"{det.label} {det.confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.imwrite(save_path, img)
            print(f"Annotated image saved to: {save_path}")
        return detections

    def to_serializable(self, detections: List[Detection]) -> List[Dict[str, Any]]:
        return [
            {"label": d.label, "confidence": d.confidence, "bbox": d.bbox, "center": d.center}
            for d in detections
        ]


def main():
    print("=== YOLOv8 Detector Test ===\n")
    detector = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.5)
    test_image = "test_image.jpg"

    if not Path(test_image).exists():
        print(f"Test image not found: {test_image}")
        return

    try:
        print(f"Running detection on: {test_image}\n")
        detections = detector.detect_and_visualize(
            image_source=test_image, save_path="output_annotated.jpg"
        )
        print(f"\nFound {len(detections)} objects:\n")
        for i, det in enumerate(detections, 1):
            print(f"{i}. {det.label} (conf: {det.confidence:.2f}) Center: ({det.center[0]:.0f}, {det.center[1]:.0f})")
        import json
        print("\nSerialized:")
        print(json.dumps(detector.to_serializable(detections), indent=2))
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
