"""
Action Planner for VLA-Desk Project

This module converts parsed language instructions and vision detections
into executable robot action sequences.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass


@dataclass
class RobotAction:
    """Single robot action command."""
    command: str  # move_to, grasp, release, move_above
    parameters: Dict[str, Any]


class ActionPlanner:
    """Generate robot action sequences from task plans and object detections."""
    
    def __init__(
        self,
        safe_height: float = 0.25,
        grasp_height: float = 0.02,
        image_width: int = 640,
        image_height: int = 480,
        workspace_width: float = 0.6,
        workspace_height: float = 0.45,
        workspace_center_x: float = 0.5,
        workspace_center_y: float = 0.0
    ) -> None:
        """Initialize action planner.
        
        Args:
            safe_height: Height to move above objects (meters)
            grasp_height: Height for grasping (meters above table)
            image_width: Camera image width (pixels)
            image_height: Camera image height (pixels)
            workspace_width: Real workspace width (meters)
            workspace_height: Real workspace depth (meters)
            workspace_center_x: X coordinate of workspace center (meters)
            workspace_center_y: Y coordinate of workspace center (meters)
        """
        self.safe_height = safe_height
        self.grasp_height = grasp_height
        self.image_width = image_width
        self.image_height = image_height
        self.workspace_width = workspace_width
        self.workspace_height = workspace_height
        self.workspace_center_x = workspace_center_x
        self.workspace_center_y = workspace_center_y
    
    def pixel_to_world(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """Convert pixel coordinates to robot world coordinates.
        
        Simple linear mapping assuming camera is looking down at workspace.
        
        Args:
            pixel_x: X coordinate in image (pixels)
            pixel_y: Y coordinate in image (pixels)
            
        Returns:
            Tuple of (world_x, world_y) in meters
        """
        # Normalize pixel coordinates to [0, 1]
        norm_x = pixel_x / self.image_width
        norm_y = pixel_y / self.image_height
        
        # Map to workspace coordinates
        # X: 0 (left) -> workspace_center_x - width/2, 1 (right) -> workspace_center_x + width/2
        world_x = self.workspace_center_x - self.workspace_width / 2 + norm_x * self.workspace_width
        
        # Y: 0 (top) -> workspace_center_y + height/2, 1 (bottom) -> workspace_center_y - height/2
        # Note: Image Y increases downward, but world Y increases forward
        world_y = self.workspace_center_y + self.workspace_height / 2 - norm_y * self.workspace_height
        
        return world_x, world_y
    
    def find_object(self, target: str, detections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find target object in detection results.
        
        Args:
            target: Object name to find (e.g., "cup", "red cup")
            detections: List of detected objects from YOLO
            
        Returns:
            Detection dict if found, None otherwise
        """
        target_lower = target.lower()
        
        # Try exact match first
        for det in detections:
            if det["label"].lower() == target_lower:
                return det
        
        # Try partial match
        for det in detections:
            if target_lower in det["label"].lower() or det["label"].lower() in target_lower:
                return det
        
        return None
    
    def estimate_destination(
        self,
        destination: str,
        detections: List[Dict[str, Any]]
    ) -> Tuple[float, float]:
        """Estimate world coordinates for destination description.
        
        Args:
            destination: Destination description (e.g., "left", "right", "center")
            detections: Current object detections (for relative positioning)
            
        Returns:
            Tuple of (world_x, world_y) coordinates
        """
        destination_lower = destination.lower()
        
        # Predefined locations
        if "left" in destination_lower or "左" in destination:
            return (self.workspace_center_x - 0.2, self.workspace_center_y)
        elif "right" in destination_lower or "右" in destination:
            return (self.workspace_center_x + 0.2, self.workspace_center_y)
        elif "center" in destination_lower or "middle" in destination_lower or "中间" in destination:
            return (self.workspace_center_x, self.workspace_center_y)
        elif "front" in destination_lower or "前" in destination:
            return (self.workspace_center_x, self.workspace_center_y + 0.15)
        elif "back" in destination_lower or "后" in destination:
            return (self.workspace_center_x, self.workspace_center_y - 0.15)
        else:
            # Default to center
            return (self.workspace_center_x, self.workspace_center_y)
    
    def plan(
        self,
        task: Dict[str, Any],
        detections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate action sequence from task and detections.
        
        Args:
            task: Parsed task from language module
                  Format: {"action": "pick|place|move", "target": "object", "destination": "..."}
            detections: Object detections from vision module
                       Format: [{"label": "cup", "center": [x, y], ...}, ...]
        
        Returns:
            Dictionary with "status" (success/error), "actions" list, and optional "message"
        """
        action_type = task.get("action", "").lower()
        target = task.get("target", "")
        destination = task.get("destination")
        
        # Find target object
        target_detection = self.find_object(target, detections)
        
        if not target_detection and action_type in ["pick", "move"]:
            return {
                "status": "error",
                "message": f"Target object '{target}' not found in scene",
                "actions": []
            }
        
        # Generate action sequence based on action type
        actions = []
        
        if action_type == "pick":
            # Convert pixel coordinates to world coordinates
            px, py = target_detection["center"]
            wx, wy = self.pixel_to_world(px, py)
            
            actions = [
                RobotAction("move_above", {"x": wx, "y": wy, "z": self.safe_height}),
                RobotAction("move_to", {"x": wx, "y": wy, "z": self.grasp_height}),
                RobotAction("grasp", {"target": target}),
                RobotAction("move_above", {"x": wx, "y": wy, "z": self.safe_height}),
            ]
        
        elif action_type == "place":
            if not destination:
                return {
                    "status": "error",
                    "message": "Place action requires destination",
                    "actions": []
                }
            
            # Estimate destination coordinates
            dest_x, dest_y = self.estimate_destination(destination, detections)
            
            actions = [
                RobotAction("move_above", {"x": dest_x, "y": dest_y, "z": self.safe_height}),
                RobotAction("move_to", {"x": dest_x, "y": dest_y, "z": self.grasp_height}),
                RobotAction("release", {}),
                RobotAction("move_above", {"x": dest_x, "y": dest_y, "z": self.safe_height}),
            ]
        
        elif action_type == "move":
            # Move object to destination
            if not destination:
                return {
                    "status": "error",
                    "message": "Move action requires destination",
                    "actions": []
                }
            
            px, py = target_detection["center"]
            wx, wy = self.pixel_to_world(px, py)
            dest_x, dest_y = self.estimate_destination(destination, detections)
            
            # Pick from current location
            actions.extend([
                RobotAction("move_above", {"x": wx, "y": wy, "z": self.safe_height}),
                RobotAction("move_to", {"x": wx, "y": wy, "z": self.grasp_height}),
                RobotAction("grasp", {"target": target}),
                RobotAction("move_above", {"x": wx, "y": wy, "z": self.safe_height}),
            ])
            
            # Move to destination
            actions.extend([
                RobotAction("move_above", {"x": dest_x, "y": dest_y, "z": self.safe_height}),
                RobotAction("move_to", {"x": dest_x, "y": dest_y, "z": self.grasp_height}),
                RobotAction("release", {}),
                RobotAction("move_above", {"x": dest_x, "y": dest_y, "z": self.safe_height}),
            ])
        
        elif action_type == "inspect":
            # Just look at the object (move above it)
            if target_detection:
                px, py = target_detection["center"]
                wx, wy = self.pixel_to_world(px, py)
                actions = [
                    RobotAction("move_above", {"x": wx, "y": wy, "z": self.safe_height}),
                ]
            else:
                return {
                    "status": "error",
                    "message": f"Cannot inspect: '{target}' not found",
                    "actions": []
                }
        
        else:
            return {
                "status": "error",
                "message": f"Unknown action type: '{action_type}'",
                "actions": []
            }
        
        # Convert RobotAction objects to dictionaries
        action_dicts = [
            {"command": act.command, "parameters": act.parameters}
            for act in actions
        ]
        
        return {
            "status": "success",
            "message": f"Generated {len(action_dicts)} actions for '{action_type}' task",
            "actions": action_dicts
        }


def main():
    """Test ActionPlanner with sample data."""
    print("=== Action Planner Test ===\n")
    
    # Initialize planner
    planner = ActionPlanner(
        safe_height=0.25,
        grasp_height=0.02,
        image_width=640,
        image_height=480
    )
    
    # Mock detection results (from YOLO)
    mock_detections = [
        {"label": "cup", "confidence": 0.92, "center": [200, 150]},
        {"label": "bottle", "confidence": 0.87, "center": [400, 200]},
        {"label": "phone", "confidence": 0.95, "center": [300, 350]},
    ]
    
    # Mock task instructions (from LLM)
    test_tasks = [
        {"action": "pick", "target": "cup"},
        {"action": "move", "target": "bottle", "destination": "left"},
        {"action": "place", "target": "phone", "destination": "center"},
        {"action": "inspect", "target": "cup"},
        {"action": "pick", "target": "keyboard"},  # Not in detections
    ]
    
    print("📦 Mock Detections:")
    for det in mock_detections:
        print(f"  - {det['label']} at pixel ({det['center'][0]}, {det['center'][1]})")
    
    print("\n" + "="*60 + "\n")
    
    # Test each task
    for i, task in enumerate(test_tasks, 1):
        print(f"Test {i}: {task}")
        print("-" * 60)
        
        result = planner.plan(task, mock_detections)
        
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        
        if result['actions']:
            print(f"\nGenerated {len(result['actions'])} actions:")
            for j, action in enumerate(result['actions'], 1):
                cmd = action['command']
                params = action['parameters']
                print(f"  {j}. {cmd}")
                
                if 'x' in params and 'y' in params and 'z' in params:
                    print(f"     → Position: ({params['x']:.3f}, {params['y']:.3f}, {params['z']:.3f})")
                elif params:
                    print(f"     → Parameters: {params}")
        
        print("\n")
    
    # Test coordinate conversion
    print("="*60)
    print("\n🗺️  Coordinate Conversion Test:\n")
    test_pixels = [(0, 0), (320, 240), (640, 480)]
    for px, py in test_pixels:
        wx, wy = planner.pixel_to_world(px, py)
        print(f"Pixel ({px:3d}, {py:3d}) → World ({wx:+.3f}, {wy:+.3f})")


if __name__ == "__main__":
    main()
