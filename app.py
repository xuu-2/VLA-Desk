"""
VLA-Desk Gradio UI - Deep Tech Style
Vision-Language-Action Desktop Manipulation Assistant
"""
import gradio as gr
import cv2
import numpy as np
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from perception.yolo_detector import YOLODetector
from language.llm_planner import LLMPlanner
from planning.action_planner import ActionPlanner

detector = None
planner = None
action_planner = None
cap = None
current_detections = []
task_log = []

LABEL_ZH = {
    "cup": "杯子", "mug": "杯子", "bottle": "瓶子",
    "pen": "笔", "pencil": "笔", "keyboard": "键盘",
    "laptop": "笔记本电脑", "mouse": "鼠标",
    "phone": "手机", "cell phone": "手机",
    "book": "书", "scissors": "剪刀"
}

def zh_label(label):
    return LABEL_ZH.get(label.lower(), label)

def add_log(msg):
    global task_log
    ts = time.strftime("%H:%M:%S")
    task_log.append(f"[{ts}] {msg}")
    if len(task_log) > 30:
        task_log = task_log[-30:]
    return "\n".join(task_log)

def init_modules():
    global detector, planner, action_planner
    try:
        detector = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.45)
        detector.load_model()
        add_log("✅ YOLO 检测器已加载")
    except Exception as e:
        add_log(f"⚠️ YOLO 加载失败: {e}")
    try:
        planner = LLMPlanner()
        add_log("✅ LLM 规划器已加载")
    except Exception as e:
        add_log(f"⚠️ LLM 加载失败（将使用规则解析）")
        planner = None
    action_planner = ActionPlanner()
    add_log("✅ 动作规划器已加载")
    add_log("🚀 VLA 桌面助手已就绪")

def capture_and_detect():
    global cap, current_detections
    if cap is None or not cap.isOpened():
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            blank = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank, "Camera Not Available", (120, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
            return blank, "❌ 摄像头不可用", add_log("❌ 摄像头打开失败")
    ret, frame = cap.read()
    if not ret:
        return None, "❌ 读取失败", add_log("❌ 帧读取失败")
    cv2.imwrite("temp_frame.jpg", frame)
    try:
        dets = detector.detect("temp_frame.jpg")
        current_detections = detector.to_serializable(dets)
        for d in current_detections:
            x1, y1, x2, y2 = map(int, d['bbox'])
            cx, cy = map(int, d['center'])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
            cv2.circle(frame, (cx, cy), 5, (255, 80, 80), -1)
            label = f"{zh_label(d['label'])} {d['confidence']:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, y1-th-10), (x1+tw+4, y1), (0, 200, 255), -1)
            cv2.putText(frame, label, (x1+2, y1-4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 30), 2)
        cv2.putText(frame, "LIVE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 100), 2)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        det_md = "### 识别结果\n\n"
        if current_detections:
            for d in current_detections:
                bar = int(d['confidence'] * 10)
                det_md += f"**{zh_label(d['label'])}** `{d['confidence']:.2f}` "
                det_md += "█"*bar + "░"*(10-bar) + "\n\n"
        else:
            det_md += "_未检测到物体_"
        return frame_rgb, det_md, add_log(f"✅ 检测到 {len(current_detections)} 个物体")
    except Exception as e:
        return frame, f"❌ 检测错误: {e}", add_log(f"❌ {e}")

def execute_instruction(instruction):
    global current_detections
    if not instruction.strip():
        return add_log("⚠️ 请输入指令"), "⚠️ 请输入指令", ""
    add_log(f"💬 指令: 「{instruction}」")
    try:
        if planner:
            task = planner.parse_instruction(instruction)
        else:
            tmp = LLMPlanner.__new__(LLMPlanner)
            task = tmp._fallback_parse(instruction)
        add_log(f"🤖 解析: {task['action']} → {task['target']}")
        if not current_detections:
            return add_log("⚠️ 请先点击「捕获检测」"), "⚠️ 未检测到物体", ""
        result = action_planner.plan(task, current_detections)
        if result["status"] == "error":
            return add_log(f"❌ {result['message']}"), f"❌ {result['message']}", ""
        actions = result['actions']
        add_log(f"✅ 生成 {len(actions)} 个动作")
        plan_md = "### 语言助手\n\n**理解与计划：**\n\n"
        for i, a in enumerate(actions, 1):
            cmd = a['command']
            params = a['parameters']
            if cmd == 'move_above':
                desc = "移动到目标上方"
            elif cmd == 'move_to':
                desc = "下降到目标位置"
            elif cmd == 'grasp':
                desc = f"抓取「{params.get('target', task['target'])}」"
            elif cmd == 'release':
                desc = "释放物体"
            else:
                desc = cmd
            plan_md += f"{i}. {desc}\n"
        status_md = f"### 执行状态\n\n🟢 **状态：计划生成完成**\n\n任务：{instruction}"
        return add_log("🎮 计划已生成"), plan_md, status_md
    except Exception as e:
        return add_log(f"❌ {e}"), f"❌ 错误: {e}", ""

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

with gr.Blocks(title="VLA 桌面助手") as demo:
    gr.HTML('<h1 id="title">🤖 VLA 桌面助手</h1>')
    gr.Markdown("_Vision-Language-Action Desktop Manipulation Assistant_")
    with gr.Row():
        with gr.Column(scale=3):
            camera_output = gr.Image(label="📹 摄像头实时画面", height=480)
            detect_btn = gr.Button("🔍 捕获检测", variant="primary", size="lg")
        with gr.Column(scale=2):
            detection_md = gr.Markdown("### 📦 识别结果\n\n_等待检测..._")
            plan_md = gr.Markdown("### 🧠 语言助手\n\n_等待指令..._")
            status_md = gr.Markdown("### 🎯 执行状态\n\n🔵 **状态：待机中**")
    with gr.Row():
        with gr.Column(scale=5):
            instruction_input = gr.Textbox(label="💬 语音指令输入",
                placeholder="请输入指令，例如：把杯子移到左边、拿起笔...", lines=2)
        with gr.Column(scale=1):
            execute_btn = gr.Button("🚀 执行任务", variant="primary", size="lg")
    with gr.Row():
        gr.Button("拿起杯子", size="sm").click(lambda: "拿起杯子", outputs=instruction_input)
        gr.Button("移动瓶子到左边", size="sm").click(lambda: "移动瓶子到左边", outputs=instruction_input)
        gr.Button("把笔放到杯子里", size="sm").click(lambda: "把笔放到杯子里", outputs=instruction_input)
    log_output = gr.Textbox(label="📋 系统日志", lines=8, max_lines=15, interactive=False)
    detect_btn.click(capture_and_detect, outputs=[camera_output, detection_md, log_output])
    execute_btn.click(execute_instruction, inputs=[instruction_input], outputs=[log_output, plan_md, status_md])
    demo.load(init_modules)

if __name__ == "__main__":
    print("="*70)
    print("  🤖 启动 VLA 桌面助手 Gradio 界面")
    print("="*70)
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True
    )
