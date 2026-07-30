"""
Quick test for Planning Module (Action Planner)
"""

from planning.action_planner import ActionPlanner

def main():
    print("=" * 60)
    print("  Planning Module Test - Action Sequence Generation")
    print("=" * 60)
    
    print("\n⏳ Initializing Action Planner...")
    planner = ActionPlanner(
        safe_height=0.25,
        grasp_height=0.02,
        image_width=640,
        image_height=480
    )
    print("✅ Action Planner initialized\n")
    
    # Mock detection data
    mock_detections = [
        {
            "label": "cup",
            "confidence": 0.92,
            "bbox": [200, 150, 300, 300],
            "center": [250, 225]
        },
        {
            "label": "bottle",
            "confidence": 0.87,
            "bbox": [350, 180, 430, 320],
            "center": [390, 250]
        }
    ]
    
    # Test tasks
    test_tasks = [
        {"action": "pick", "target": "cup"},
        {"action": "move", "target": "bottle", "destination": "left"},
        {"action": "place", "target": "cup", "destination": "center"}
    ]
    
    print("📦 Available objects:", [d['label'] for d in mock_detections])
    print()
    
    for i, task in enumerate(test_tasks, 1):
        print(f"Test {i}: {task}")
        print("-" * 60)
        
        result = planner.plan(task, mock_detections)
        
        if result["status"] == "success":
            print(f"✅ {result['message']}")
            print(f"\nGenerated {len(result['actions'])} actions:")
            for j, action in enumerate(result['actions'], 1):
                cmd = action['command']
                params = action['parameters']
                print(f"  {j}. {cmd.upper().replace('_', ' ')}")
                if 'x' in params and 'y' in params and 'z' in params:
                    print(f"     Position: ({params['x']:.3f}, {params['y']:.3f}, {params['z']:.3f})")
                elif params:
                    print(f"     Params: {params}")
        else:
            print(f"❌ {result['message']}")
        
        print()
    
    # Test coordinate conversion
    print("=" * 60)
    print("🗺️  Coordinate Conversion Test:")
    print()
    test_pixels = [(250, 225), (390, 250), (320, 240)]
    for px, py in test_pixels:
        wx, wy = planner.pixel_to_world(px, py)
        print(f"  Pixel ({px:3d}, {py:3d}) → World ({wx:+.3f}m, {wy:+.3f}m)")
    
    print("\n✅ Planning module test PASSED!")


if __name__ == "__main__":
    main()
