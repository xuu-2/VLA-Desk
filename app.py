"""
VLA-Desk Gradio UI - Deep Tech Style
Vision-Language-Action Desktop Manipulation Assistant

架构:
  CameraStream  (线程1) → 持续读帧到共享 buffer
  DetectionWorker (线程2) → 持续对最新帧做 YOLO 推理
  UI 线程 → 只读缓存帧 + 缓存检测结果，零等待
  Qwen-VL → 只在指令解析时调用，不参与实时检测
"""
import gradio as gr
import cv2
import numpy as np
import torch
import time
import sys
import os
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vl.qwen_vl import QwenVLModel
from perception.yolo_detector import YOLODetector
from perception.camera_stream import CameraStream
from perception.detection_worker import DetectionWorker
from planning.action_planner import ActionPlanner

ArmController = None

vl_model = None
yolo_detector = None
camera_stream = None
detection_worker = None
action_planner = None
arm = None
current_detections = []
task_log = []

# 检测后端选择
DETECTOR_BACKEND = os.environ.get("VLA_DETECTOR", "onnx")  # pytorch | onnx | tensorrt
YOLO_MODEL_PATH = os.environ.get("VLA_YOLO_MODEL", "yolov8n.onnx")

LABEL_ZH = {
    "cup": "杯子", "mug": "杯子", "bottle": "瓶子",
    "pen": "笔", "pencil": "笔", "keyboard": "键盘",
    "laptop": "笔记本电脑", "mouse": "鼠标",
    "phone": "手机", "cell phone": "手机",
    "book": "书", "scissors": "剪刀"
}
LABEL_EN = {
    "杯子": "cup", "瓶子": "bottle", "键盘": "keyboard", "笔": "pen",
    "笔记本电脑": "laptop", "鼠标": "mouse", "手机": "phone", "书": "book",
    "剪刀": "scissors", "人": "person"
}


def zh_label(label):
    return LABEL_ZH.get(label.lower(), label)


def en_label(label):
    return LABEL_EN.get(str(label).strip(), str(label).strip().lower())


def normalize_detection_labels(detections):
    normalized = []
    for d in detections:
        item = dict(d)
        item["label"] = en_label(item.get("label", ""))
        normalized.append(item)
    return normalized


def add_log(msg):
    global task_log
    ts = time.strftime("%H:%M:%S")
    task_log.append(f"[{ts}] {msg}")
    if len(task_log) > 30:
        task_log = task_log[-30:]
    return "\n".join(task_log)


def get_log():
    return "\n".join(task_log)


def init_modules():
    global vl_model, yolo_detector, camera_stream, detection_worker
    global action_planner, arm
    add_log("Initializing...")

    # --- 检查机械臂控制器导入路径 ---
    try:
        from robot.arm_controller import ArmController as _ArmController
        globals()["ArmController"] = _ArmController
        add_log("ArmController import path OK: robot.arm_controller")
    except Exception as e:
        add_log(f"ArmController import failed: {e}")
        add_log(traceback.format_exc())
        globals()["ArmController"] = None

    # --- YOLO 检测器 ---
    backend = DETECTOR_BACKEND
    model_path = YOLO_MODEL_PATH

    # 如果指定 onnx / tensorrt，自动找对应文件
    if backend == "onnx":
        if not Path(model_path).exists():
            fallback = model_path.replace(".onnx", ".pt")
            add_log(f"ONNX model not found: {model_path}, fallback to {fallback}")
            model_path = fallback
            backend = "pytorch"
    elif backend == "tensorrt":
        engine_path = model_path.replace(".onnx", ".engine").replace(".pt", ".engine")
        if not Path(engine_path).exists():
            add_log(f"TensorRT engine not found: {engine_path}, fallback to ONNX/PyTorch")
            if Path(model_path.replace('.onnx', '.onnx')).exists():
                model_path = model_path.replace('.pt', '.onnx')
                backend = "onnx"
            else:
                backend = "pytorch"
                model_path = model_path.replace('.onnx', '.pt')
        else:
            model_path = engine_path

    try:
        yolo_detector = YOLODetector(
            model_path=model_path,
            confidence_threshold=0.35,
            backend=backend,
        )
        yolo_detector.load_model()
        add_log(f"YOLOv8 detector loaded ({backend})")
    except Exception as e:
        add_log(f"YOLO load failed: {e}")
        yolo_detector = None

    # --- 摄像头流 + 后台检测 ---
    try:
        camera_stream = CameraStream(0)
        if camera_stream.start():
            detection_worker = DetectionWorker(yolo_detector, min_interval=0.05)
            detection_worker.start(camera_stream)
            add_log("Camera stream + background detection started")
        else:
            add_log("Camera stream failed to start")
            camera_stream = None
    except Exception as e:
        add_log(f"Camera/detection init failed: {e}")
        camera_stream = None
        detection_worker = None

    # --- Qwen-VL 语义模型 ---
    try:
        vl_model = QwenVLModel(
            model_name="F:/Learn/VibeCoding/VLA-Desk/models/Qwen2-VL-2B",
            quantization="4bit" if torch.cuda.is_available() else None,
            lora_path="F:/Learn/VibeCoding/VLA-Desk/models/qwen-vl-lora",
        )
        vl_model.load()
        add_log("Qwen2-VL-2B + LoRA loaded (for instruction parsing)")
    except Exception as e:
        add_log(f"Qwen-VL load failed: {e}")
        vl_model = None

    # --- 动作规划 + 机械臂 ---
    action_planner = ActionPlanner()
    add_log("Action planner loaded")
    try:
        if ArmController is None:
            raise ImportError("robot.arm_controller is not importable")
        arm = ArmController(robot_name="ur5e", gui=True)
        add_log("MuJoCo arm controller ready (UR5e, gui=True)")
    except Exception as e:
        add_log(f"MuJoCo init failed: {e}")
        add_log(traceback.format_exc())
        arm = None
    add_log("VLA Desk ready")


# ---------------------------------------------------------------------------
# 实时刷新：只读缓存，零等待
# ---------------------------------------------------------------------------
def live_capture():
    """从 CameraStream 拿最新帧 + DetectionWorker 拿最新检测结果，直接渲染。
    不做任何推理，不阻塞。"""
    global current_detections

    if camera_stream is None:
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(blank, "Camera Not Available", (120, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
        return blank, "Camera not available", get_log()

    frame = camera_stream.read()
    if frame is None:
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(blank, "Waiting for camera...", (110, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
        return blank, "Waiting for frame...", get_log()

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 读取后台线程缓存的检测结果（零等待）
    if detection_worker is not None:
        current_detections = normalize_detection_labels(detection_worker.get_detections())
    else:
        current_detections = []

    # 画框
    for d in current_detections:
        x1, y1, x2, y2 = map(int, d['bbox'])
        cx, cy = map(int, d['center'])
        cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), (255, 200, 0), 2)
        cv2.circle(frame_rgb, (cx, cy), 5, (80, 80, 255), -1)
        label = f"{en_label(d['label'])} {d['confidence']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame_rgb, (x1, y1 - th - 10), (x1 + tw + 4, y1), (255, 200, 0), -1)
        cv2.putText(frame_rgb, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 10, 10), 2)
    cv2.putText(frame_rgb, "LIVE", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 100), 2)

    det_md = "### Detection Results\n\n"
    if current_detections:
        for d in current_detections:
            bar = int(d['confidence'] * 10)
            det_md += f"**{en_label(d['label'])}** `{d['confidence']:.2f}` "
            det_md += "|" * bar + "." * (10 - bar) + "\n\n"
    else:
        det_md += "_No objects detected_"

    return frame_rgb, det_md, get_log()


def capture_and_detect():
    """按钮触发版：和 live_capture 一样，但追加一条日志。"""
    frame_rgb, det_md, _ = live_capture()
    n = len(current_detections)
    return frame_rgb, det_md, add_log(f"Refresh: {n} objects")


# ---------------------------------------------------------------------------
# 指令执行：Qwen-VL 只在这里调用
# ---------------------------------------------------------------------------
def execute_instruction(instruction):
    global current_detections, arm, vl_model
    if not instruction.strip():
        return add_log("Please enter instruction"), "Please enter instruction", ""
    add_log(f"Instruction: {instruction}")
    try:
        if vl_model is not None:
            task = vl_model.parse_instruction(instruction)
        else:
            from language.llm_planner import LLMPlanner
            tmp = LLMPlanner.__new__(LLMPlanner)
            task = tmp._fallback_parse(instruction)
        if "action" not in task or "target" not in task:
            task.setdefault("action", "inspect")
            task.setdefault("target", "object")
        task["target"] = en_label(task.get("target", ""))
        if "destination" in task and task["destination"]:
            task["destination"] = en_label(task["destination"])
        add_log(f"Parsed: {task.get('action')} -> {task.get('target')}")
        if current_detections and "destination" not in task and task.get("action") in {"pick", "move", "place"}:
            task["destination"] = "center"
        if not current_detections and task.get("action") in ("pick", "move"):
            return add_log("Please capture first"), "No objects detected", ""
        result = action_planner.plan(task, current_detections)
        if result["status"] == "error":
            return add_log(f"Error: {result['message']}"), f"Error: {result['message']}", ""
        actions = result['actions']
        add_log(f"Generated {len(actions)} actions")

        cmd_desc = {
            "move_above": "Move above target",
            "move_to": "Descend to target",
            "grasp": "Grasp",
            "release": "Release",
        }
        plan_md = "### Plan\n\n"
        for i, a in enumerate(actions, 1):
            cmd = a['command']
            params = a['parameters']
            if cmd == "grasp":
                desc = f"Grasp {params.get('target', task.get('target', 'object'))}"
            else:
                desc = cmd_desc.get(cmd, cmd)
            plan_md += f"{i}. {desc}\n"

        status_md_lines = [f"### Execution\n\nRunning: {instruction}\n"]
        if arm is None:
            add_log("No MuJoCo controller, plan only")
            status_md = f"### Execution\n\nPlan generated (no simulation)\n\nTask: {instruction}"
            return add_log("Plan generated"), plan_md, status_md

        add_log("Executing in MuJoCo")
        for i, action in enumerate(actions, 1):
            cmd = action['command']
            desc = cmd_desc.get(cmd, cmd)
            add_log(f"  [{i}/{len(actions)}] {desc} ...")
            try:
                res = arm.execute_action(action)
                if str(res.get("status")).lower() == "error":
                    add_log(f"    Failed: {res.get('message', '')}")
                    status_md_lines.append(f"{i}. FAIL {desc}")
                    break
                status_md_lines.append(f"{i}. OK {desc}")
                pos = res.get("position")
                if pos is not None:
                    add_log(f"    EE -> ({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})")
            except Exception as e:
                add_log(f"    Exception: {e}")
                status_md_lines.append(f"{i}. ERROR {desc}")
                break
        status_md = "\n".join(status_md_lines)
        add_log("Task complete")
        return add_log("Task complete"), plan_md, status_md
    except Exception as e:
        return add_log(f"Error: {e}"), f"Error: {e}", ""


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
css = """
* { font-family: 'Inter', sans-serif; }
.gradio-container { background: linear-gradient(135deg, #1e1e2e 0%, #2d1b3d 100%) !important; }
#title { text-align: center; background: linear-gradient(90deg, #00c8ff 0%, #a855f7 100%);
-webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5em; font-weight: 700; }
.block { background: rgba(30,30,46,0.6) !important; backdrop-filter: blur(10px) !important;
border: 1px solid rgba(0,200,255,0.2) !important; border-radius: 16px !important; }
button { background: linear-gradient(135deg, #00c8ff 0%, #0096cc 100%) !important;
border: none !important; border-radius: 12px !important; font-weight: 600 !important; }
textarea, input { background: rgba(20,20,30,0.8) !important;
border: 1px solid rgba(0,200,255,0.3) !important; border-radius: 12px !important; color: #e0e0e0 !important; }
label { color: #00c8ff !important; font-weight: 600 !important; }
"""

with gr.Blocks(title="VLA Desk") as demo:
    gr.HTML('<h1 id="title">VLA Desk</h1>')
    gr.Markdown("_Vision-Language-Action Desktop Manipulation Assistant_")
    with gr.Row():
        with gr.Column(scale=3):
            camera_output = gr.Image(label="Camera", height=480, streaming=True)
            detect_btn = gr.Button("Capture", variant="primary", size="lg")
        with gr.Column(scale=2):
            detection_md = gr.Markdown("### Detection\n\n_Waiting..._")
            plan_md = gr.Markdown("### Plan\n\n_Waiting..._")
            status_md = gr.Markdown("### Status\n\n_Idle_")
    with gr.Row():
        with gr.Column(scale=5):
            instruction_input = gr.Textbox(label="Instruction",
                placeholder="e.g. pick up cup, move bottle left...", lines=2)
        with gr.Column(scale=1):
            execute_btn = gr.Button("Execute", variant="primary", size="lg")
    with gr.Row():
        gr.Button("pick up cup", size="sm").click(lambda: "拿起杯子", outputs=instruction_input)
        gr.Button("move bottle left", size="sm").click(lambda: "移动瓶子到左边", outputs=instruction_input)
        gr.Button("put pen in cup", size="sm").click(lambda: "把笔放到杯子里", outputs=instruction_input)
    log_output = gr.Textbox(label="Log", lines=8, max_lines=15, interactive=False)

    # 按钮：单次刷新（从缓存读，零等待）
    detect_btn.click(capture_and_detect, outputs=[camera_output, detection_md, log_output])
    execute_btn.click(execute_instruction, inputs=[instruction_input], outputs=[log_output, plan_md, status_md])

    # 定时刷新：每 0.1s 从缓存拿最新帧 + 检测结果
    demo.load(init_modules, outputs=log_output)
    timer = gr.Timer(value=0.1)
    timer.tick(live_capture, outputs=[camera_output, detection_md, log_output])


if __name__ == "__main__":
    print("=" * 70)
    print("  VLA Desk starting")
    print("=" * 70)
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
    )
