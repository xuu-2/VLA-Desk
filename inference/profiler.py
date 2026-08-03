"""
推理管线性能分析工具。
分阶段计时 + GPU/CPU/显存占用 + 瓶颈诊断。

用法:
  python inference/profiler.py                          # 跑默认 YOLO 测试
  python inference/profiler.py --backend yolo             # 只测 YOLO (PyTorch)
  python inference/profiler.py --backend yolo --engine models/yolov8n.engine  # TensorRT
  python inference/profiler.py --backend qwen            # 测 Qwen-VL 检测
  python inference/profiler.py --compare                  # 比较所有可用后端
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# 确保能 import 项目模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# 阶段计时
# ---------------------------------------------------------------------------
@dataclass
class StageTiming:
    name: str
    times: List[float] = field(default_factory=list)

    def add(self, t: float) -> None:
        self.times.append(t)

    @property
    def avg(self) -> float:
        return sum(self.times) / len(self.times) if self.times else 0.0

    @property
    def min(self) -> float:
        return min(self.times) if self.times else 0.0

    @property
    def max(self) -> float:
        return max(self.times) if self.times else 0.0

    @property
    def p50(self) -> float:
        if not self.times:
            return 0.0
        s = sorted(self.times)
        return s[len(s) // 2]

    @property
    def p99(self) -> float:
        if not self.times:
            return 0.0
        s = sorted(self.times)
        idx = int(len(s) * 0.99)
        return s[min(idx, len(s) - 1)]

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "count": len(self.times),
            "avg_ms": round(self.avg * 1000, 2),
            "min_ms": round(self.min * 1000, 2),
            "max_ms": round(self.max * 1000, 2),
            "p50_ms": round(self.p50 * 1000, 2),
            "p99_ms": round(self.p99 * 1000, 2),
        }


class StageTimer:
    """上下文管理器 + 手动计时。"""

    def __init__(self, registry: Dict[str, StageTiming]):
        self.registry = registry
        self.name: Optional[str] = None
        self.t0: float = 0.0

    def __call__(self, name: str) -> "StageTimer":
        self.name = name
        if name not in self.registry:
            self.registry[name] = StageTiming(name)
        return self

    def __enter__(self) -> "StageTimer":
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        elapsed = time.perf_counter() - self.t0
        if self.name:
            self.registry[self.name].add(elapsed)

    def mark(self, name: str, t: float) -> None:
        if name not in self.registry:
            self.registry[name] = StageTiming(name)
        self.registry[name].add(t)


# ---------------------------------------------------------------------------
# 硬件监控
# ---------------------------------------------------------------------------
class HardwareMonitor:
    """采集 GPU / CPU / 内存指标。"""

    def __init__(self) -> None:
        self.has_gpu = False
        try:
            import torch
            self.has_gpu = torch.cuda.is_available()
        except ImportError:
            pass
        self.has_pynvml = False
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            self.has_pynvml = True
        except Exception:
            pass
        self.has_psutil = False
        try:
            import psutil  # type: ignore
            self.has_psutil = True
        except ImportError:
            pass

    def snapshot(self) -> Dict[str, Any]:
        snap: Dict[str, Any] = {}
        # CPU
        if self.has_psutil:
            import psutil
            snap["cpu_percent"] = round(psutil.cpu_percent(interval=0.1), 1)
            snap["ram_gb"] = round(psutil.virtual_memory().used / 1024**3, 2)
            snap["ram_percent"] = round(psutil.virtual_memory().percent, 1)
        # GPU (torch)
        if self.has_gpu:
            import torch
            snap["gpu_alloc_gb"] = round(torch.cuda.memory_allocated() / 1024**3, 2)
            snap["gpu_reserved_gb"] = round(torch.cuda.memory_reserved() / 1024**3, 2)
        # GPU (NVML — 更详细的利用率)
        if self.has_pynvml:
            import pynvml
            try:
                h = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                snap["gpu_util_percent"] = util.gpu
                snap["gpu_mem_util_percent"] = util.memory
                temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                snap["gpu_temp_c"] = temp
            except Exception:
                pass
        return snap

    def release(self) -> None:
        if self.has_pynvml:
            try:
                import pynvml
                pynvml.nvmlShutdown()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 各阶段单独测试
# ---------------------------------------------------------------------------
def benchmark_yolo_pytorch(
    image_path: str,
    model_path: str = "yolov8n.pt",
    warmup: int = 3,
    iters: int = 30,
) -> Tuple[Dict[str, StageTiming], List[Dict[str, Any]]]:
    """分阶段计时 YOLO PyTorch 推理。"""
    from perception.yolo_detector import YOLODetector
    import cv2

    registry: Dict[str, StageTiming] = {}
    timer = StageTimer(registry)
    hw = HardwareMonitor()
    hw_snapshots: List[Dict[str, Any]] = []

    det = YOLODetector(model_path=model_path, confidence_threshold=0.35, backend="pytorch")

    with timer("load_model"):
        det.load_model()

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read: {image_path}")

    # warmup
    for _ in range(warmup):
        det.detect(img)

    for i in range(iters):
        with timer("read_image"):
            frame = img.copy()

        with timer("preprocess"):
            # 这里尽量不做磁盘 I/O，只保留极少量准备工作
            frame = np.ascontiguousarray(frame)

        t0 = time.perf_counter()
        dets = det.detect(frame)
        timer.mark("inference", time.perf_counter() - t0)

        t0 = time.perf_counter()
        serialized = det.to_serializable(dets)
        timer.mark("postprocess", time.perf_counter() - t0)

        with timer("serialize"):
            _ = json.dumps(serialized)

        if i % 5 == 0:
            hw_snapshots.append(hw.snapshot())

    hw.release()
    return registry, hw_snapshots


def benchmark_yolo_onnx(
    image_path: str,
    onnx_path: str,
    warmup: int = 3,
    iters: int = 30,
) -> Tuple[Dict[str, StageTiming], List[Dict[str, Any]]]:
    """分阶段计时 YOLO ONNXRuntime 推理。"""
    from perception.yolo_detector import YOLODetector

    registry: Dict[str, StageTiming] = {}
    timer = StageTimer(registry)
    hw = HardwareMonitor()
    hw_snapshots: List[Dict[str, Any]] = []

    det = YOLODetector(model_path=onnx_path, confidence_threshold=0.35, backend="onnx")

    with timer("load_model"):
        det.load_model()

    import cv2
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read: {image_path}")

    # warmup
    for _ in range(warmup):
        det.detect(img)

    for i in range(iters):
        with timer("read_image"):
            frame = img.copy()

        with timer("preprocess"):
            frame = np.ascontiguousarray(frame)

        t0 = time.perf_counter()
        dets = det.detect(frame)
        timer.mark("inference", time.perf_counter() - t0)

        t0 = time.perf_counter()
        serialized = det.to_serializable(dets)
        timer.mark("postprocess", time.perf_counter() - t0)

        with timer("serialize"):
            _ = json.dumps(serialized)

        if i % 5 == 0:
            hw_snapshots.append(hw.snapshot())

    hw.release()
    return registry, hw_snapshots


def benchmark_yolo_tensorrt(
    image_path: str,
    engine_path: str,
    warmup: int = 3,
    iters: int = 30,
) -> Tuple[Dict[str, StageTiming], List[Dict[str, Any]]]:
    """分阶段计时 YOLO TensorRT 推理。"""
    from inference.inference_backend import TensorRTBackend
    import cv2

    registry: Dict[str, StageTiming] = {}
    timer = StageTimer(registry)
    hw = HardwareMonitor()
    hw_snapshots: List[Dict[str, Any]] = []

    trt = TensorRTBackend(engine_path)
    with timer("load_engine"):
        ok = trt.load()
    if not ok:
        hw.release()
        return registry, hw_snapshots

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read: {image_path}")

    dummy = np.random.randn(*trt.input_shape).astype(np.float32)
    for _ in range(warmup):
        trt.infer(dummy)

    for i in range(iters):
        with timer("read_image"):
            frame = img.copy()

        with timer("preprocess"):
            resized = cv2.resize(frame, (trt.input_shape[-1], trt.input_shape[-2]))
            input_data = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
            input_data = np.ascontiguousarray(input_data[np.newaxis])

        t0 = time.perf_counter()
        outputs = trt.infer(input_data)
        timer.mark("inference", time.perf_counter() - t0)

        with timer("postprocess"):
            _ = outputs

        with timer("serialize"):
            _ = json.dumps({"ok": True})

        if i % 5 == 0:
            hw_snapshots.append(hw.snapshot())

    trt.release()
    hw.release()
    return registry, hw_snapshots


def benchmark_qwen_vl(
    image_path: str,
    model_name: str = "F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B",
    warmup: int = 1,
    iters: int = 5,
    lora_path: Optional[str] = "F:/Learn/VibeCoding/VLA-Desk/models/qwen-vl-lora",
) -> Tuple[Dict[str, StageTiming], List[Dict[str, Any]]]:
    """分阶段计时 Qwen-VL 检测推理。"""
    from vl.qwen_vl import QwenVLModel

    registry: Dict[str, StageTiming] = {}
    timer = StageTimer(registry)
    hw = HardwareMonitor()
    hw_snapshots: List[Dict[str, Any]] = []

    model = QwenVLModel(
        model_name=model_name,
        quantization="4bit",
        lora_path=lora_path,
    )

    with timer("load_model"):
        model.load()

    # warmup
    model.detect(image_path)

    for i in range(iters):
        with timer("read_image"):
            from PIL import Image
            img = Image.open(image_path).convert("RGB")

        with timer("preprocess"):
            import torch
            messages = [{"role": "user", "content": [
                {"type": "image", "image": img},
                {"type": "text", "text": "识别图中物体，返回 JSON。"},
            ]}]
            text = model.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = model.processor(text=[text], images=[img], return_tensors="pt")
            inputs = {k: v.to(model.model.device) if hasattr(v, "to") else v for k, v in inputs.items()}

        t0 = time.perf_counter()
        with torch.inference_mode():
            generated = model.model.generate(**inputs, max_new_tokens=256, do_sample=False)
        timer.mark("inference", time.perf_counter() - t0)

        with timer("postprocess"):
            input_len = inputs["input_ids"].shape[1]
            out = model.processor.batch_decode(generated[:, input_len:], skip_special_tokens=True)[0]
            data = model._extract_json(out)
            if data is None:
                model._extract_objects_from_text(out)

        if i % 2 == 0:
            hw_snapshots.append(hw.snapshot())

    hw.release()
    return registry, hw_snapshots


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------
def print_report(
    title: str,
    registry: Dict[str, StageTiming],
    hw_snapshots: List[Dict[str, Any]],
) -> None:
    print(f"\n{'='*70}")
    print(f"  📊 {title}")
    print(f"{'='*70}")

    # 阶段计时
    total_avg = sum(s.avg for s in registry.values() if s.name != "load_model")
    print(f"\n{'阶段':<20} {'avg(ms)':>10} {'p50(ms)':>10} {'p99(ms)':>10} {'占比':>8}")
    print("-" * 62)
    for name, stage in registry.items():
        s = stage.summary()
        pct = (stage.avg / total_avg * 100) if total_avg > 0 else 0
        if name == "load_model":
            print(f"{name:<20} {s['avg_ms']:>10.2f} {'--':>10} {'--':>10} {'(一次性)':>8}")
        else:
            print(f"{name:<20} {s['avg_ms']:>10.2f} {s['p50_ms']:>10.2f} {s['p99_ms']:>10.2f} {pct:>7.1f}%")
    print("-" * 62)
    print(f"{'总推理(不含加载)':<20} {total_avg*1000:>10.2f} ms")
    fps = 1.0 / total_avg if total_avg > 0 else 0
    print(f"{'FPS':<20} {fps:>10.1f}")

    # 硬件占用
    if hw_snapshots:
        print(f"\n--- 硬件占用（采样 {len(hw_snapshots)} 次）---")
        keys = set()
        for snap in hw_snapshots:
            keys.update(snap.keys())
        for k in sorted(keys):
            vals = [s.get(k) for s in hw_snapshots if k in s]
            if vals and isinstance(vals[0], (int, float)):
                print(f"  {k:<25} avg={sum(vals)/len(vals):.1f}  max={max(vals):.1f}")

    # 瓶颈分析
    print(f"\n--- 瓶颈分析 ---")
    infer_stages = {k: v for k, v in registry.items() if k != "load_model"}
    if infer_stages:
        bottleneck = max(infer_stages.values(), key=lambda s: s.avg)
        print(f"  最慢阶段: {bottleneck.name} ({bottleneck.avg*1000:.2f} ms)")
        if bottleneck.name == "inference":
            print(f"  → 推理是瓶颈，可考虑 TensorRT / 量化 / 减小模型")
        elif bottleneck.name in ("preprocess", "read_image"):
            print(f"  → 数据搬运是瓶颈，可考虑多线程读取 / pipeline 并行")
        elif bottleneck.name == "postprocess":
            print(f"  → 后处理是瓶颈，可考虑 NMS 优化 / 批处理")
        elif bottleneck.name == "serialize":
            print(f"  → 序列化是瓶颈，可考虑用 orjson / 减小输出")


# ---------------------------------------------------------------------------
# 时间复杂度分析
# ---------------------------------------------------------------------------
def print_complexity_analysis() -> None:
    print(f"\n{'='*70}")
    print("  📐 时间复杂度分析")
    print(f"{'='*70}\n")

    stages = [
        ("read_image", "O(H×W)", "读一帧，受分辨率影响", "用 CameraStream 后台线程预读"),
        ("preprocess", "O(H×W)", "resize / 归一化 / 转置", "用 CUDA preprocessing / 预分配 buffer"),
        ("inference (YOLO)", "O(N×C×H×W)", "N=batch, C=通道, 受输入尺寸", "TensorRT / 减小输入尺寸 / 量化"),
        ("inference (Qwen-VL)", "O(L²×D)", "L=序列长度(含图片token), D=hidden", "减小图片分辨率 / 量化 / KV-cache"),
        ("postprocess", "O(B×K)", "B=候选框数, K=类别数, NMS 是 O(B²)", "用 batched NMS / GPU NMS / 先验框过滤"),
        ("serialize", "O(D)", "D=检测数, 通常是几十", "orjson / 跳过未用字段"),
    ]

    print(f"{'阶段':<25} {'复杂度':<15} {'说明'}")
    print("-" * 80)
    for name, comp, desc, opt in stages:
        print(f"{name:<25} {comp:<15} {desc}")
        print(f"{'':>25} {'':>15} → 优化: {opt}")
    print()

    print("关键参数:")
    print("  摄像头 640×480 → YOLO 输入 640×640 → 图片 token 数 ~ 256")
    print("  Qwen-VL 序列长度 L = 图片token + 文本token ≈ 300-500")
    print("  L² × D 中 D=1536 (Qwen2-VL-2B hidden dim)")
    print("  → L²=250000, D=1536 → ~3.8亿次乘加 (单层)")
    print("  → 28 层 → ~107亿次乘加 (这就是为什么 Qwen-VL 比 YOLO 慢 100x)")


# ---------------------------------------------------------------------------
# 智能指针 / 零拷贝分析
# ---------------------------------------------------------------------------
def print_data_flow_analysis() -> None:
    print(f"\n{'='*70}")
    print("  🔗 数据流 / 零拷贝分析")
    print(f"{'='*70}\n")

    flows = [
        ("摄像头 → CameraStream", "共享内存 numpy array + threading.Lock", "已有", "无拷贝，只传引用"),
        ("CameraStream → DetectionWorker", "frame.copy() + imwrite 临时文件", "⚠️ 有拷贝", "可直接传 numpy array 给 YOLO，跳过 imwrite"),
        ("DetectionWorker → app.py", "dict 列表 (序列化后)", "⚠️ 序列化", "可传 Detection 对象引用，延迟序列化"),
        ("YOLO 内部 preprocess", "numpy → torch tensor → GPU", "有 2 次拷贝", "可用 CUDA preprocessing 避免一次"),
        ("YOLO → postprocess", "GPU tensor → cpu() → numpy", "⚠️ D2H 拷贝", "可用 pinned memory 异步拷贝"),
        ("Qwen-VL preprocess", "PIL → processor → tensor → GPU", "有 3 次拷贝", "可从 cv2 frame 直接构造 tensor"),
    ]

    print(f"{'数据流':<35} {'当前方式':<30} {'状态'}")
    print("-" * 90)
    for flow, method, status, opt in flows:
        print(f"{flow:<35} {method:<30} {status}")
        if opt:
            print(f"{'':>35} → 优化: {opt}")
    print()

    print("智能指针使用情况:")
    print("  Python 层: numpy array 本身是引用计数 + 零拷贝传递")
    print("  Threading 层: Lock 保护共享帧，已经是正确的共享方式")
    print("  ⚠️ imwrite + imread: 产生磁盘 I/O 和编解码开销，应该去掉")
    print("  ⚠️ det.to_serializable(): 提前序列化，如果下游不需要 JSON 则浪费")


# ---------------------------------------------------------------------------
# 并行化建议
# ---------------------------------------------------------------------------
def print_parallel_analysis(registry: Dict[str, StageTiming]) -> None:
    print(f"\n{'='*70}")
    print("  ⚡ 并行化可行性分析")
    print(f"{'='*70}\n")

    total = sum(s.avg for s in registry.values() if s.name != "load_model")
    if total == 0:
        print("  无数据")
        return

    print(f"{'阶段':<20} {'耗时(ms)':>10} {'占比':>8} {'能否并行':>10} {'建议'}")
    print("-" * 85)

    stages_info = [
        ("read_image", "可", "CameraStream 线程已在后台，与推理并行"),
        ("preprocess", "可", "用 CUDA stream 异步预处理，与上一帧推理重叠"),
        ("inference", "不可", "主瓶颈，GPU 占满，只能换更快的引擎"),
        ("postprocess", "可", "可以在 CPU 线程跑，不阻塞下一帧推理"),
        ("serialize", "可", "延迟到真正需要 JSON 时再做"),
    ]

    for name, parallel, suggestion in stages_info:
        stage = registry.get(name)
        ms = stage.avg * 1000 if stage else 0
        pct = (stage.avg / total * 100) if stage and total > 0 else 0
        print(f"{name:<20} {ms:>10.2f} {pct:>7.1f}% {parallel:>10}   {suggestion}")

    print()
    print("理想 pipeline (重叠执行):")
    print("  Frame N+1 读取  ──┐")
    print("  Frame N 预处理  ──┤──→ Frame N-1 推理 ──→ Frame N-2 后处理")
    print("  这样只要 inference 是瓶颈，总 FPS ≈ 1/inference_time")
    print()


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="推理管线性能分析")
    parser.add_argument("--backend", choices=["yolo", "yolo-onnx", "yolo-trt", "qwen", "all"],
                        default="yolo", help="测试后端")
    parser.add_argument("--image", default="desk.jpg", help="测试图片")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO PyTorch 模型路径")
    parser.add_argument("--onnx", default="yolov8n.onnx", help="YOLO ONNX 模型路径")
    parser.add_argument("--engine", default="models/yolov8n.engine", help="TensorRT engine 路径")
    parser.add_argument("--qwen-model", default="F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B")
    parser.add_argument("--lora", default="F:/Learn/VibeCoding/VLA-Desk/models/qwen-vl-lora")
    parser.add_argument("--iters", type=int, default=30, help="测试迭代次数")
    parser.add_argument("--warmup", type=int, default=3, help="预热次数")
    parser.add_argument("--compare", action="store_true", help="比较所有可用后端")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    if not Path(args.image).exists():
        print(f"❌ 图片不存在: {args.image}")
        return

    results: Dict[str, Any] = {}

    if args.compare or args.backend in ("yolo", "all"):
        print("\nTesting YOLO (PyTorch)...")
        reg, hw = benchmark_yolo_pytorch(args.image, args.model, args.warmup, args.iters)
        if not args.json:
            print_report("YOLO PyTorch", reg, hw)
        results["yolo_pytorch"] = {"stages": {k: v.summary() for k, v in reg.items()}, "hw": hw}

    if args.compare or args.backend in ("yolo-onnx", "all"):
        if Path(args.onnx).exists():
            print("\nTesting YOLO (ONNXRuntime)...")
            reg, hw = benchmark_yolo_onnx(args.image, args.onnx, args.warmup, args.iters)
            if not args.json:
                print_report("YOLO ONNXRuntime", reg, hw)
            results["yolo_onnx"] = {"stages": {k: v.summary() for k, v in reg.items()}, "hw": hw}
        else:
            print(f"\nONNX model not found: {args.onnx}, skipping")
            print(f"   Export with: python export_yolo_engine.py --model {args.model}")

    if args.compare or args.backend in ("yolo-trt", "all"):
        if Path(args.engine).exists():
            print("\nTesting YOLO (TensorRT)...")
            reg, hw = benchmark_yolo_tensorrt(args.image, args.engine, args.warmup, args.iters)
            if not args.json:
                print_report("YOLO TensorRT", reg, hw)
            results["yolo_tensorrt"] = {"stages": {k: v.summary() for k, v in reg.items()}, "hw": hw}
        else:
            print(f"\nTensorRT engine not found: {args.engine}, skipping")
            print(f"   Export with: yolo export model {args.model} format engine")

    if args.compare or args.backend in ("qwen", "all"):
        print("\nTesting Qwen-VL...")
        reg, hw = benchmark_qwen_vl(args.image, args.qwen_model, max(1, args.warmup),
                                    min(args.iters, 5), args.lora)
        if not args.json:
            print_report("Qwen-VL 2B + LoRA", reg, hw)
        results["qwen_vl"] = {"stages": {k: v.summary() for k, v in reg.items()}, "hw": hw}

    if not args.json:
        print_complexity_analysis()
        print_data_flow_analysis()
        if "yolo_pytorch" in results:
            reg = {k: StageTiming(k, [v["avg_ms"]/1000]) for k, v in results["yolo_pytorch"]["stages"].items()}
            print_parallel_analysis(reg)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
