"""
Enhanced PyBullet Simulation Environment for VLA-Desk
Now includes table and graspable objects!
"""

import pybullet as p
import pybullet_data
import numpy as np
import time
from typing import List, Dict, Optional


class PyBulletEnv:
    """PyBullet simulation environment with table and objects."""
    
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
        """Connect to PyBullet simulation."""
        if self.connected:
            return
        
        if self.gui:
            self.physics_client = p.connect(p.GUI)
        else:
            self.physics_client = p.connect(p.DIRECT)
        
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        self.connected = True
        
    def reset(self) -> None:
        """Reset simulation and create complete desk scene."""
        if not self.connected:
            self.connect()
        
        p.resetSimulation()
        p.setGravity(0, 0, -9.81)
        
        # Ground
        self.plane_id = p.loadURDF("plane.urdf")
        
        # Desk/Table (brown wooden)
        table_collision = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.4, 0.3, 0.02])
        table_visual = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.4, 0.3, 0.02], 
                                          rgbaColor=[0.6, 0.4, 0.2, 1])
        self.table_id = p.createMultiBody(baseMass=0, baseCollisionShapeIndex=table_collision,
                                         baseVisualShapeIndex=table_visual, 
                                         basePosition=[0.5, 0, 0.3])
        
        # Create graspable objects
        self.objects = {}
        
        # Red cup
        cup_col = p.createCollisionShape(p.GEOM_CYLINDER, radius=0.03, height=0.08)
        cup_vis = p.createVisualShape(p.GEOM_CYLINDER, radius=0.03, length=0.08,
                                      rgbaColor=[0.8, 0.1, 0.1, 1])
        self.objects['cup'] = p.createMultiBody(baseMass=0.1, baseCollisionShapeIndex=cup_col,
                                               baseVisualShapeIndex=cup_vis,
                                               basePosition=[0.4, 0.1, 0.36])
        
        # Green bottle
        bottle_col = p.createCollisionShape(p.GEOM_CYLINDER, radius=0.025, height=0.15)
        bottle_vis = p.createVisualShape(p.GEOM_CYLINDER, radius=0.025, length=0.15,
                                         rgbaColor=[0.2, 0.6, 0.2, 1])
        self.objects['bottle'] = p.createMultiBody(baseMass=0.15, baseCollisionShapeIndex=bottle_col,
                                                  baseVisualShapeIndex=bottle_vis,
                                                  basePosition=[0.5, -0.1, 0.395])
        
        # Black phone
        phone_col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.035, 0.07, 0.008])
        phone_vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.035, 0.07, 0.008],
                                        rgbaColor=[0.1, 0.1, 0.1, 1])
        self.objects['phone'] = p.createMultiBody(baseMass=0.08, baseCollisionShapeIndex=phone_col,
                                                 baseVisualShapeIndex=phone_vis,
                                                 basePosition=[0.6, 0.05, 0.33])
        
        # Load robot
        self.robot_id = p.loadURDF("kuka_iiwa/model.urdf", basePosition=[0, 0, 0], useFixedBase=True)
        
        num_joints = p.getNumJoints(self.robot_id)
        self.end_effector_index = num_joints - 1
        
        rest_poses = [0, 0, 0, -1.5, 0, 1.5, 0]
        for i in range(min(len(rest_poses), num_joints)):
            p.resetJointState(self.robot_id, i, rest_poses[i])
        
        for _ in range(100):
            p.stepSimulation()
            if self.gui:
                time.sleep(0.01)
        
        print("✅ Desk scene created!")
        print(f"   📦 Objects: {list(self.objects.keys())}")
    
    def move_to_joint_positions(self, joint_positions: List[float], duration: float = 1.0) -> None:
        for joint_idx in range(min(len(joint_positions), 7)):
            p.setJointMotorControl2(self.robot_id, joint_idx, p.POSITION_CONTROL,
                                   targetPosition=joint_positions[joint_idx], force=500)
        steps = int(duration * 240)
        for _ in range(steps):
            p.stepSimulation()
            if self.gui:
                time.sleep(1.0 / 240.0)
    
    def calculate_ik(self, target_pos: List[float]) -> Optional[List[float]]:
        target_orn = p.getQuaternionFromEuler([0, np.pi/2, 0])
        try:
            joint_positions = p.calculateInverseKinematics(
                self.robot_id, self.end_effector_index, target_pos, target_orn,
                maxNumIterations=100, residualThreshold=0.001)
            return list(joint_positions[:7])
        except Exception as e:
            print(f"IK failed: {e}")
            return None
    
    def move_to(self, x: float, y: float, z: float) -> bool:
        joint_positions = self.calculate_ik([x, y, z])
        if joint_positions is None:
            return False
        self.move_to_joint_positions(joint_positions, duration=1.0)
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
        command = action.get('command', '')
        params = action.get('parameters', {})
        
        if command == 'move_to':
            return self.move_to(params.get('x', 0.3), params.get('y', 0.0), params.get('z', 0.2))
        elif command == 'move_above':
            return self.move_above(params.get('x', 0.3), params.get('y', 0.0), params.get('z', 0.25))
        elif command == 'grasp':
            self.grasp()
            return True
        elif command == 'release':
            self.release()
            return True
        return False
    
    def execute_plan(self, actions: List[Dict]) -> None:
        for i, action in enumerate(actions):
            success = self.execute_action(action)
            if not success:
                print(f"Action {i+1} failed: {action}")
    
    def close(self) -> None:
        if self.connected:
            p.disconnect()
            self.connected = False


def main():
    """Test with complete desk scene."""
    print("="*70)
    print("  PyBullet Enhanced Simulation - With Desk & Objects")
    print("="*70)
    
    env = PyBulletEnv(gui=True)
    env.connect()
    env.reset()
    
    print(f"\n🤖 Robot ready! End effector: {env.end_effector_index}")
    print("\n📍 Object positions:")
    print(f"   🔴 Cup: [0.4, 0.1, 0.36]")
    print(f"   🟢 Bottle: [0.5, -0.1, 0.395]")
    print(f"   ⬛ Phone: [0.6, 0.05, 0.33]")
    
    test_actions = [
        {"command": "move_above", "parameters": {"x": 0.4, "y": 0.1, "z": 0.45}},
        {"command": "move_to", "parameters": {"x": 0.4, "y": 0.1, "z": 0.36}},
        {"command": "grasp", "parameters": {}},
        {"command": "move_above", "parameters": {"x": 0.4, "y": 0.1, "z": 0.45}},
        {"command": "move_above", "parameters": {"x": 0.5, "y": -0.2, "z": 0.45}},
        {"command": "move_to", "parameters": {"x": 0.5, "y": -0.2, "z": 0.36}},
        {"command": "release", "parameters": {}},
        {"command": "move_above", "parameters": {"x": 0.5, "y": -0.2, "z": 0.45}}
    ]
    
    print("\n🎬 Executing pick-and-place demo...")
    for i, action in enumerate(test_actions, 1):
        cmd = action['command']
        print(f"  {i}/{len(test_actions)}: {cmd.upper().replace('_', ' ')}")
        success = env.execute_action(action)
        print(f"    {'✓' if success else '✗'} Done\n")
        time.sleep(0.5)
    
    print("="*70)
    print("🎉 Demo completed! Now you can see objects on the desk!")
    print("="*70)
    
    try:
        while True:
            p.stepSimulation()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nClosing...")
    finally:
        env.close()


if __name__ == "__main__":
    main()
