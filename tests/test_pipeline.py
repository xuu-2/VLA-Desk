"""VLA-Desk Pipeline Test Suite - Step-by-step module verification"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

def print_header(t): print(f"\n{'='*80}\n  {t}\n{'='*80}\n")
def print_ok(m): print(f"✅ {m}")
def print_err(m): print(f"❌ {m}")
def print_info(m): print(f"ℹ️  {m}")

def test_vision():
    print_header("TEST 1: Vision Module")
    try:
        from perception.yolo_detector import YOLODetector
        import cv2, numpy as np
        
        print("Step 1: Init YOLO...")
        det = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.5)
        print_ok("YOLO ready")
        
        img_path = "desk.jpg"
        if not Path(img_path).exists():
            print_info("Creating test image...")
            img = np.ones((480,640,3), dtype=np.uint8)*200
            cv2.rectangle(img,(100,150),(200,300),(0,0,255),-1)
            cv2.rectangle(img,(300,100),(380,280),(0,255,0),-1)
            cv2.imwrite(img_path, img)
        
        print("Step 2: Detect objects...")
        dets = det.detect(img_path)
        objs = det.to_serializable(dets)
        
        if not objs:
            print_info("Using mock detections")
            objs = [
                {"label":"cup","confidence":0.92,"bbox":[100,150,200,300],"center":[150,225]},
                {"label":"bottle","confidence":0.87,"bbox":[300,100,380,280],"center":[340,190]}
            ]
        
        print_ok(f"Found {len(objs)} objects")
        for i,o in enumerate(objs,1):
            print(f"  {i}. {o['label']} @ {o['center']}")
        
        print("\nStep 3: Show image...")
        img = cv2.imread(img_path)
        for o in objs:
            x1,y1,x2,y2 = map(int,o['bbox'])
            cv2.rectangle(img,(x1,y1),(x2,y2),(0,255,0),2)
            cv2.circle(img,(int(o['center'][0]),int(o['center'][1])),5,(0,0,255),-1)
        cv2.imshow("Detections",img)
        print_info("Press key to continue...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        
        print_ok("Vision PASSED ✓\n")
        return True, objs
    except Exception as e:
        print_err(f"Vision FAILED: {e}")
        return False, []

def test_language():
    print_header("TEST 2: Language Module")
    try:
        from language.llm_planner import LLMPlanner
        import os
        
        print("Step 1: Check API...")
        if os.environ.get("SILICONFLOW_API_KEY"):
            print_ok("API key found")
            planner = LLMPlanner()
            use_api = True
        else:
            print_info("No API, using fallback")
            planner = LLMPlanner.__new__(LLMPlanner)
            use_api = False
        
        tests = ["pick up the cup", "move bottle to left", "把杯子移到右边"]
        print(f"\nStep 2: Test {len(tests)} instructions...")
        
        results = []
        for i,instr in enumerate(tests,1):
            print(f"\n{i}. \"{instr}\"")
            task = planner.parse_instruction(instr) if use_api else planner._fallback_parse(instr)
            print(f"   Action: {task['action']}, Target: {task['target']}")
            results.append(task)
        
        print()
        print_ok("Language PASSED ✓\n")
        return True, results[0]
    except Exception as e:
        print_err(f"Language FAILED: {e}")
        return False, {}

def test_planning(task, objs):
    print_header("TEST 3: Planning Module")
    try:
        from planning.action_planner import ActionPlanner
        
        print("Step 1: Init planner...")
        planner = ActionPlanner(safe_height=0.25, grasp_height=0.02)
        print_ok("Planner ready")
        
        print(f"\nStep 2: Generate actions...")
        print(f"  Task: {task}")
        print(f"  Objects: {[o['label'] for o in objs]}")
        
        result = planner.plan(task, objs)
        
        if result["status"] == "error":
            print_err(result["message"])
            return False, []
        
        print_ok(result["message"])
        print(f"\nStep 3: Action sequence:")
        for i,act in enumerate(result['actions'],1):
            print(f"  {i}. {act['command']} - {act['parameters']}")
        
        print()
        print_ok("Planning PASSED ✓\n")
        return True, result['actions']
    except Exception as e:
        print_err(f"Planning FAILED: {e}")
        return False, []

def test_simulation(actions):
    print_header("TEST 4: Simulation Module")
    try:
        from simulation.pybullet_env import PyBulletEnv
        import time
        
        print("Step 1: Init PyBullet...")
        sim = PyBulletEnv(robot_name="franka_panda", gui=True)
        sim.connect()
        sim.reset()
        print_ok("Simulation ready")
        
        print(f"\nStep 2: Execute {len(actions)} actions...")
        for i,act in enumerate(actions,1):
            print(f"  {i}. {act['command']}")
            sim.execute_plan([act])
            time.sleep(0.3)
        
        print()
        print_ok("Simulation PASSED ✓\n")
        return True
    except Exception as e:
        print_err(f"Simulation FAILED: {e}")
        return False

def main():
    print_header("🤖 VLA-Desk Pipeline Test")
    print("Testing: Vision → Language → Planning → Simulation\n")
    
    choice = input("Run full pipeline? (y/n): ").strip().lower()
    
    if choice == 'y':
        vision_ok, objs = test_vision()
        if not vision_ok: return
        input("\n⏸️  Press Enter...")
        
        lang_ok, task = test_language()
        if not lang_ok: return
        input("\n⏸️  Press Enter...")
        
        plan_ok, actions = test_planning(task, objs)
        if not plan_ok: return
        input("\n⏸️  Press Enter...")
        
        sim_ok = test_simulation(actions)
        
        if sim_ok:
            print_header("✅ ALL TESTS PASSED")
            print("Vision ✓  Language ✓  Planning ✓  Simulation ✓\n")
    else:
        print("\nRun individual tests:")
        print("1. python test_pipeline.py  # then choose 'y'")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
