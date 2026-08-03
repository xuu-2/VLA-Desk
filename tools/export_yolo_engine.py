"""
将 YOLOv8 PyTorch 模型导出为 TensorRT engine。

用法:
  python export_yolo_engine.py                          # 默认 yolov8n.pt → yolov8n.engine
  python export_yolo_engine.py --model yolov8s.pt        # 导出 yolov8s
  python export_yolo_engine.py --half                    # FP16 量化
  python export_yolo_engine.py --int8                    # INT8 量化（需要校准数据）

导出完成后，用以下方式启动 app:
  set VLA_DETECTOR=tensorrt
  set VLA_YOLO_MODEL=yolov8n.engine
  python app.py
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export YOLOv8 to TensorRT engine")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO .pt model path")
    parser.add_argument("--half", action="store_true", help="FP16 quantization")
    parser.add_argument("--int8", action="store_true", help="INT8 quantization (needs calibration)")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    parser.add_argument("--batch", type=int, default=1, help="Static batch size")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Model not found: {model_path}")
        return

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics not installed: pip install ultralytics")
        return

    print(f"Loading: {model_path}")
    model = YOLO(str(model_path))

    export_kwargs = {
        "format": "engine",
        "imgsz": args.imgsz,
        "batch": args.batch,
        "dynamic": False,
        "simplify": True,
    }

    if args.half:
        export_kwargs["half"] = True
        print("Using FP16")
    elif args.int8:
        export_kwargs["int8"] = True
        print("Using INT8 (requires calibration data)")

    print(f"Exporting to TensorRT (imgsz={args.imgsz}, batch={args.batch})...")
    path = model.export(**export_kwargs)
    print(f"\nExported: {path}")
    print(f"\nTo use in app:")
    print(f"  set VLA_DETECTOR=tensorrt")
    print(f"  set VLA_YOLO_MODEL={path}")
    print(f"  python app.py")


if __name__ == "__main__":
    main()
