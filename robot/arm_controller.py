from typing import Dict, List


class ArmController:
    def __init__(self, robot_name: str = "franka_panda") -> None:
        self.robot_name = robot_name

    def move_to(self, position: List[float]) -> Dict[str, object]:
        return {"status": "ok", "command": "move_to", "position": position}

    def grasp(self, target: str) -> Dict[str, object]:
        return {"status": "ok", "command": "grasp", "target": target}
