"""
PyBullet Simulation Environment for VLA-Desk
Includes desk, graspable objects (cup, bottle, phone), and KUKA iiwa robot.
"""

import pybullet as p
import pybullet_data
import numpy as np
import time
from typing import List, Dict, Optional


class PyBulletEnv:

    def __init__(self, robot_name: str = "kuka", gui: bool = True) -> None:
        self.robot_name = robot_name
        self.gui = gui
        self.connected = False
        self.physics_client = None
        self.robot_id = None
        self.plane_id = None
        self.table_id = None
        self.objects = {}
        self.end_effector_index = 6
        self.gripper_open = True

    def connect(self) -> None:
        if self.connected:
            return
        self.physics_client = p.connect(p.GUI if self.gui else p.DIRECT)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        self.connected = True

    def reset(self) -> None:
        if not self.connected:
            self.connect()

        p.resetSimulation()
        p.setGravity(0, 0, -9.81)

        # Ground
        self.plane_id = p.loadURDF("plane.urdf")

        # Desk (brown, 80cm x 60cm, height 30cm)
        table_col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.4, 0.3, 0.02])
        table_vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.4, 0.3, 0.02],
                                        rgbaColor=[0.55, 0.35, 0.15, 1])
        self.table_id = p.createMultiBody(baseMass=0,
                                          baseCollisionShapeIndex=table_col,
                                          baseVisualShapeIndex=table_vis,
                                          basePosition=[0.5, 0, 0.3])

        # Table legs
        for lx, ly in [(0.38, 0.28), (0.38, -0.28), (0.62, 0.28), (0.62, -0.28)]:
            leg_col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.02, 0.02, 0.15])
            leg_vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.02, 0.02, 0.15],
                                          rgbaColor=[0.4, 0.25, 0.1, 1])
            p.createMultiBody(baseMass=0, baseCollisionShapeIndex=leg_col,
                              baseVisualShapeIndex=leg_vis, basePosition=[lx, ly, 0.15])

        # Objects on the table
        self.objects = {}

        # Red cup
        cup_col = p.createCollisionShape(p.GEOM_CYLINDER, radius=0.03, height=0.08)
        cup_vis = p.createVisualShape(p.GEOM_CYLINDER, radius=0.03, length=0.08,
                                      rgbaColor=[0.85, 0.15, 0.15, 1])
        self.objects['cup'] = p.createMultiBody(baseMass=0.1,
                                                baseCollisionShapeIndex=cup_col,
                                                baseVisualShapeIndex=cup_vis,
                                                basePosition=[0.4, 0.12, 0.36])

        # Green bottle
        bottle_col = p.createCollisionShape(p.GEOM_CYLINDER, radius=0.025, height=0.15)
        bottle_vis = p.createVisualShape(p.GEOM_CYLINDER, radius=0.025, length=0.15,
                                         rgbaColor=[0.15, 0.65, 0.15, 1])
        self.objects['bottle'] = p.createMultiBody(baseMass=0.15,
                                                   baseCollisionShapeIndex=bottle_col,
                                                   baseVisualShapeIndex=bottle_vis,
                                                   basePosition=[0.55, -0.1, 0.395])

        # Black phone
        phone_col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.035, 0.07, 0.008])
        phone_vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.035, 0.07, 0.008],
                                        rgbaColor=[0.1, 0.1, 0.1, 1])
        self.objects['phone'] = p.createMultiBody(baseMass=0.08,
                                                  baseCollisionShapeIndex=phone_col,
                                                  baseVisualShapeIndex=phone_vis,
                                                  basePosition=[0.62, 0.08, 0.33])

        # Robot
        self.robot_id = p.loadURDF("kuka_iiwa/model.urdf",
                                   basePosition=[0, 0, 0], useFixedBase=True)
        num_joints = p.getNumJoints(self.robot_id)
        self.end_effector_index = num_joints - 1

        for i, angle in enumerate([0, 0, 0, -1.5, 0, 1.5, 0]):
            p.resetJointState(self.robot_id, i, angle)

        for _ in range(100):
            p.stepSimulation()
            if self.gui:
                time.sleep(0.01)

        print("✅ Scene ready: desk + cup + bottle + phone + robot")

    def move_to_joint_positions(self, joint_positions: List[float], duration: float = 1.0) -> None:
        for i in range(min(len(joint_positions), 7)):
            p.setJointMotorControl2(self.robot_id, i, p.POSITION_CONTROL,
                                    targetPosition=joint_positions[i], force=500)
        for _ in range(int(duration * 240)):
            p.stepSimulation()
            if self.gui:
                time.sleep(1.0 / 240.0)

    def calculate_ik(self, target_pos: List[float]) -> Optional[List[float]]:
        try:
            joints = p.calculateInverseKinematics(
                self.robot_id, self.end_effector_index, target_pos,
                p.getQuaternionFromEuler([0, np.pi / 2, 0]),
                maxNumIterations=100, residualThreshold=0.001)
            return list(joints[:7])
        except Exception as e:
            print(f"IK failed: {e}")
            return None

    def move_to(self, x: float, y: float, z: float) -> bool:
        joints = self.calculate_ik([x, y, z])
        if joints is None:
            return False
        self.move_to_joint_positions(joints)
        return True

    def move_above(self, x: float, y: float, z: float) -> bool:
        return self.move_to(x, y, z)

    def grasp(self) -> None:
        self.gripper_open = False
        for _ in range(50):
            p.stepSimulation()
            if self.gui:
                time.sleep(0.01)

    def release(self) -> None:
        self.gripper_open = True
        for _ in range(50):
            p.stepSimulation()
            if self.gui:
                time.sleep(0.01)

    def execute_action(self, action: Dict) -> bool:
        cmd = action.get('command', '')
        params = action.get('parameters', {})
        x, y, z = params.get('x', 0.4), params.get('y', 0.0), params.get('z', 0.3)

        if cmd == 'move_to':
            return self.move_to(x, y, z)
        elif cmd == 'move_above':
            return self.move_above(x, y, z)
        elif cmd == 'grasp':
            self.grasp()
            return True
        elif cmd == 'release':
            self.release()
            return True
        return False

    def execute_plan(self, actions: List[Dict]) -> None:
        for i, action in enumerate(actions):
            if not self.execute_action(action):
                print(f"Action {i+1} failed: {action}")

    def close(self) -> None:
        if self.connected:
            p.disconnect()
            self.connected = False


def main():
    print("=" * 60)
    print("  PyBullet Simulation - Desk Scene Demo")
    print("=" * 60)

    env = PyBulletEnv(gui=True)
    env.connect()
    env.reset()

    print("\nObject positions on desk:")
    print("  🔴 Cup:    [0.40, 0.12, 0.36]")
    print("  🟢 Bottle: [0.55, -0.10, 0.40]")
    print("  ⬛ Phone:  [0.62, 0.08, 0.33]")

    # Pick cup and place it to the right
    actions = [
        {"command": "move_above", "parameters": {"x": 0.4, "y": 0.12, "z": 0.5}},
        {"command": "move_to",    "parameters": {"x": 0.4, "y": 0.12, "z": 0.37}},
        {"command": "grasp",      "parameters": {}},
        {"command": "move_above", "parameters": {"x": 0.4, "y": 0.12, "z": 0.5}},
        {"command": "move_above", "parameters": {"x": 0.4, "y": -0.15, "z": 0.5}},
        {"command": "move_to",    "parameters": {"x": 0.4, "y": -0.15, "z": 0.37}},
        {"command": "release",    "parameters": {}},
        {"command": "move_above", "parameters": {"x": 0.4, "y": -0.15, "z": 0.5}},
    ]

    print("\nExecuting: pick cup → place to right side\n")
    for i, action in enumerate(actions, 1):
        print(f"  {i}/{len(actions)}: {action['command']}")
        env.execute_action(action)

    print("\n✅ Done! Close the PyBullet window to exit.")

    try:
        while True:
            p.stepSimulation()
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        env.close()


if __name__ == "__main__":
    main()
