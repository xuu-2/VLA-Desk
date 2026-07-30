"""
VLA-Desk Complete Demo
Integrates Vision → Language → Planning → Simulation
"""

import sys
import os
from pathlib import Path
import cv2
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from perception.yolo_detector import YOLODetector
from language.llm_planner import LLMPlanner
from planning.action_planner import ActionPlanner
from simulation.pybullet_env import PyBulletEnv


def print_separator(title: str = "") -> None:
    """Print a visual separator."""
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
    else:
        print(f"\n{'-'*70}\n")


def display_detections(image_path: str, detections: list) -> None:
    """Display image with detection annotations using OpenCV."""
    if not Path(image_path).exists():
        print(f"⚠️  Image not found: {image_path}")
        return
    
    img = cv2.imread(image_path)
    
    for det in detections:
        # Extract detection info
        label = det["label"]
        conf = det["confidence"]
        bbox = det["bbox"]
        center = det["center"]
        
        # Draw bounding box
        x1, y1, x2, y2 = map(int, bbox)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Draw center point
        cx, cy = map(int, center)
        cv2.circle(img, (cx, cy), 5, (0, 0, 255), -1)
        
        # Add label
        label_text = f"{label} {conf:.2f}"
        cv2.putText(img, label_text, (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    # Display image
    cv2.imshow("VLA-Desk - Detected Objects", img)
    print("📺 OpenCV window opened. Press any key to continue...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def main() -> None:
    """Run complete VLA-Desk demo pipeline."""
    
    print_separator("🤖 VLA-Desk Complete Demo")
    print("Vision-Language-Action Based Desktop Manipulation Assistant")
    print("Integrating: YOLO → LLM → Action Planning → PyBullet Simulation\n")
    
    # ========== Step 1: Initialize Modules ==========
    print_separator("Step 1: Initializing Modules")
    
    print("🔧 Loading YOLO Detector...")
    detector = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.5)
    print("✅ YOLO Detector ready\n")
    
    print("🔧 Loading LLM Planner...")
    try:
        planner = LLMPlanner()  # Will read from env var
        print("✅ LLM Planner ready (with API)\n")
    except ValueError:
        print("⚠️  No API key found, using fallback parser\n")
        planner = None
    
    print("🔧 Loading Action Planner...")
    action_planner = ActionPlanner(
        safe_height=0.25,
        grasp_height=0.02,
        image_width=640,
        image_height=480
    )
    print("✅ Action Planner ready\n")
    
    print("🔧 Loading PyBullet Simulation...")
    sim = PyBulletEnv(robot_name="franka_panda", gui=True)
    print("✅ Simulation Environment ready\n")
    
    # ========== Step 2: Vision - Detect Objects ==========
    print_separator("Step 2: Vision - Object Detection")
    
    # Check for test image
    test_image = "test_image.jpg"
    if not Path(test_image).exists():
        print(f"⚠️  Test image not found: {test_image}")
        print("📝 Using mock detections for demo\n")
        
        # Mock detections
        detections = [
            {
                "label": "cup",
                "confidence": 0.92,
                "bbox": [100, 150, 200, 300],
                "center": [150, 225]
            },
            {
                "label": "bottle",
                "confidence": 0.87,
                "bbox": [300, 100, 380, 280],
                "center": [340, 190]
            },
            {
                "label": "keyboard",
                "confidence": 0.95,
                "bbox": [50, 350, 450, 450],
                "center": [250, 400]
            }
        ]
    else:
        print(f"🔍 Running YOLO detection on: {test_image}")
        detections_raw = detector.detect(test_image)
        detections = detector.to_serializable(detections_raw)
        print(f"✅ Detection complete\n")
        
        # Display annotated image
        display_detections(test_image, detections)
    
    # Print detected objects
    print(f"📦 Detected {len(detections)} objects:\n")
    for i, det in enumerate(detections, 1):
        print(f"{i}. {det['label']}")
        print(f"   Confidence: {det['confidence']:.2f}")
        print(f"   Pixel Center: ({det['center'][0]:.0f}, {det['center'][1]:.0f})")
        
        # Show world coordinates
        wx, wy = action_planner.pixel_to_world(det['center'][0], det['center'][1])
        print(f"   World Position: ({wx:.3f}m, {wy:.3f}m)\n")
    
    # ========== Step 3: Language - Parse Instruction ==========
    print_separator("Step 3: Language Understanding")
    
    print("💬 Enter your instruction (or press Enter for default)")
    print("Examples:")
    print("  - pick up the cup")
    print("  - move the bottle to the left")
    print("  - place the keyboard on the table")
    print()
    
    user_input = input("Your instruction: ").strip()
    
    if not user_input:
        user_input = "pick up the cup"
        print(f"Using default: '{user_input}'\n")
    
    print(f"🗣️  Instruction: '{user_input}'")
    
    if planner:
        print("🤖 Calling LLM to parse instruction...")
        task = planner.parse_instruction(user_input)
    else:
        # Fallback parsing
        print("🔄 Using rule-based parser...")
        from language.llm_planner import LLMPlanner
        temp_planner = LLMPlanner.__new__(LLMPlanner)
        task = temp_planner._fallback_parse(user_input)
    
    print(f"✅ Parsed Task:")
    print(f"   Action: {task['action']}")
    print(f"   Target: {task['target']}")
    if task.get('destination'):
        print(f"   Destination: {task['destination']}")
    print()
    
    # ========== Step 4: Planning - Generate Actions ==========
    print_separator("Step 4: Action Planning")
    
    print("🧠 Generating robot action sequence...")
    result = action_planner.plan(task, detections)
    
    if result["status"] == "error":
        print(f"❌ Planning failed: {result['message']}")
        return
    
    print(f"✅ {result['message']}\n")
    print(f"📋 Generated {len(result['actions'])} actions:\n")
    
    for i, action in enumerate(result['actions'], 1):
        cmd = action['command']
        params = action['parameters']
        
        print(f"{i}. {cmd.upper().replace('_', ' ')}")
        
        if 'x' in params and 'y' in params and 'z' in params:
            print(f"   → Position: ({params['x']:.3f}, {params['y']:.3f}, {params['z']:.3f})")
        elif params:
            print(f"   → Parameters: {params}")
        print()
    
    # ========== Step 5: Simulation - Execute Actions ==========
    print_separator("Step 5: Simulation Execution")
    
    print("🎮 Initializing PyBullet simulation...")
    sim.connect()
    sim.reset()
    print("✅ Simulation ready\n")
    
    print("🤖 Executing action sequence...")
    print("(Note: Current simulation is a placeholder)\n")
    
    for i, action in enumerate(result['actions'], 1):
        cmd = action['command']
        params = action['parameters']
        
        print(f"Executing {i}/{len(result['actions'])}: {cmd}")
        
        # Simulate execution time
        time.sleep(0.5)
        
        # Execute in simulation (placeholder for now)
        sim.execute_plan([action])
        
        print(f"✓ Completed\n")
    
    print("✅ All actions executed successfully!")
    
    # ========== Summary ==========
    print_separator("📊 Demo Summary")
    
    print(f"Vision:    Detected {len(detections)} objects")
    print(f"Language:  Parsed '{task['action']}' action on '{task['target']}'")
    print(f"Planning:  Generated {len(result['actions'])} robot actions")
    print(f"Simulation: Executed all actions successfully")
    
    print_separator()
    print("🎉 Demo completed! VLA pipeline working end-to-end.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
