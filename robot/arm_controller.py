from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import threading
import time


class ArmController:
    def __init__(
        self,
        robot_name: str = "ur5e",
        model_path: Optional[str] = None,
        gui: bool = False,
    ) -> None:
        self.robot_name = robot_name
        self.gui = gui
        self.model_path = model_path or str(
            Path(__file__).resolve().parents[1] / "simulation" / "universal_robots_ur5e" / "ur5e.xml"
        )
        self._env = None
        self._viewer = None
        self._lock = threading.RLock()

    def _launch_viewer(self, env) -> None:
        if not self.gui:
            return
        if self._viewer is not None:
            return
        try:
            import mujoco.viewer
        except Exception:
            return

        try:
            self._viewer = mujoco.viewer.launch_passive(env.model, env.data)
        except Exception:
            self._viewer = None
            return

    def _get_env(self):
        if self._env is None:
            import importlib.util
            import sys

            here = Path(__file__).resolve().parents[1]
            module_file = here / "mujoco-projects" / "ur5-vla" / "mujoco_env.py"
            module_name = "mujoco_env_vla"
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            self._env = module.MujocoUR5Env(self.model_path, use_sim_gripper=True)
            self._env.reset()
            self._launch_viewer(self._env)
        return self._env

    def show(self) -> None:
        env = self._get_env()
        self._launch_viewer(env)

    def _sync_viewer(self) -> None:
        """动作完成后强制刷新 viewer，让窗口能看到机械臂位置变化。"""
        if self._viewer is None:
            return
        try:
            self._viewer.sync()
        except Exception:
            pass

    def move_to(self, position: List[float]) -> Dict[str, object]:
        env = self._get_env()
        x, y, z = position
        result = env.move_to(x, y, z)
        self._sync_viewer()
        return {"status": "ok", "command": "move_to", "position": [float(v) for v in result.tolist()]}

    def move_above(self, position: List[float]) -> Dict[str, object]:
        env = self._get_env()
        x, y, z = position
        result = env.move_above(x, y, z)
        self._sync_viewer()
        return {"status": "ok", "command": "move_above", "position": [float(v) for v in result.tolist()]}

    def grasp(self, target: str = "") -> Dict[str, object]:
        env = self._get_env()
        env.grasp()
        self._sync_viewer()
        return {"status": "ok", "command": "grasp", "target": target}

    def release(self) -> Dict[str, object]:
        env = self._get_env()
        env.release()
        self._sync_viewer()
        return {"status": "ok", "command": "release"}

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        cmd = action.get("command", "")
        params = action.get("parameters", {})
        x, y, z = params.get("x", 0.4), params.get("y", 0.0), params.get("z", 0.3)

        if cmd == "move_to":
            return self.move_to([x, y, z])
        if cmd == "move_above":
            return self.move_above([x, y, z])
        if cmd == "grasp":
            return self.grasp(params.get("target", ""))
        if cmd == "release":
            return self.release()
        return {"status": "error", "message": f"Unsupported command: {cmd}"}

    def execute_plan(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for action in actions:
            results.append(self.execute_action(action))
        return results
