from __future__ import annotations

import argparse
import dataclasses
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import mujoco
import numpy as np

try:
    import mujoco.viewer as _mujoco_viewer_mod
except Exception:  # pragma: no cover - viewer is optional
    _mujoco_viewer_mod = None


ArrayLike = Union[Sequence[float], np.ndarray]

_ACTION_TARGET_KEY = "target"

# 末端执行器 site 的候选名（含 UR5e 官方模型里的 attachment_site）
_EE_SITE_CANDIDATES = (
    "attachment_site",
    "ee_site",
    "tool0",
    "ee",
    "gripper_site",
    "tcp",
    "wrist_site",
)

# UR5 标准 6 个手臂关节
_UR5_ARM_JOINTS = (
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_joint",
    "wrist_1_joint",
    "wrist_2_joint",
    "wrist_3_joint",
)

# UR5e 官方 keyframe（home 位）
_UR5E_HOME_QPOS = np.array([-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0.0], dtype=float)


@dataclasses.dataclass
class GripperConfig:
    joint_names: Tuple[str, ...] = (
        "finger_joint",
        "left_finger_joint",
        "right_finger_joint",
        "robotiq_85_left_knuckle_joint",
        "robotiq_85_right_knuckle_joint",
        "robotiq_85_left_inner_knuckle_joint",
        "robotiq_85_right_inner_knuckle_joint",
        "robotiq_85_left_finger_tip_joint",
        "robotiq_85_right_finger_tip_joint",
    )
    open_value: float = 0.04
    close_value: float = 0.0


class MujocoUR5Env:
    """UR5 / UR5e 的 MuJoCo 仿真环境。

    直接吃官方 ur5e.xml（含 actuator）或裸 URDF（无 actuator 时自动回退到运动学驱动）。
    末端执行器 site 用 attachment_site；夹爪若模型没有关节，则在末端 site 处
    用可视化 geom 模拟开合。
    """

    def __init__(
        self,
        model_path: str,
        gripper_config: Optional[GripperConfig] = None,
        timestep: Optional[float] = None,
        max_steps_per_move: int = 500,
        pos_tol: float = 1e-3,
        damping: float = 1e-2,
        use_sim_gripper: bool = True,
    ) -> None:
        self.model_path = os.path.abspath(model_path)
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        self.model = mujoco.MjModel.from_xml_path(self.model_path)
        self.data = mujoco.MjData(self.model)
        if timestep is not None:
            self.model.opt.timestep = float(timestep)

        self.max_steps_per_move = int(max_steps_per_move)
        self.pos_tol = float(pos_tol)
        self.damping = float(damping)
        self.gripper_config = gripper_config or GripperConfig()
        self.use_sim_gripper = bool(use_sim_gripper)

        # 手臂关节探测
        self._arm_joint_names = self._detect_arm_joint_names()
        if len(self._arm_joint_names) < 6:
            raise RuntimeError(
                f"Expected at least 6 arm joints, found {len(self._arm_joint_names)}: {self._arm_joint_names}"
            )
        self._arm_qposadr = [self.model.jnt_qposadr[self.model.joint(j).id] for j in self._arm_joint_names]
        self._arm_dofadr = [self.model.jnt_dofadr[self.model.joint(j).id] for j in self._arm_joint_names]
        self._arm_dof_indices = [adr for adr in self._arm_dofadr if adr >= 0]

        # 末端 site
        self._ee_site_id = self._detect_ee_site_id()
        self._ee_body_id = self.model.site_bodyid[self._ee_site_id]

        # 执行器探测：模型有 actuator 且对应手臂关节时，用 ctrl 驱动
        self._arm_actuator_ids = self._detect_arm_actuator_ids()
        self._use_ctrl = len(self._arm_actuator_ids) >= len(self._arm_joint_names)

        # 夹爪关节（真实关节）
        self._gripper_joint_ids = self._detect_gripper_joint_ids()
        self._gripper_actuator_ids = self._detect_gripper_actuator_ids()
        self._gripper_joint_names = [self.model.joint(jid).name for jid in self._gripper_joint_ids]
        self._gripper_range = self._detect_gripper_range()
        self._gripper_open_state = True
        self._gripper_ctrl_targets: List[float] = []

        # 无真实夹爪关节时，直接跳过模拟夹爪几何的动态修改
        # 这样能避免对只读/不可变模型字段赋值导致的 runtime error。
        self._sim_gripper_geom_ids: List[int] = []

        mujoco.mj_forward(self.model, self.data)

    # ------------------------------------------------------------------ 探测
    def _detect_arm_joint_names(self) -> List[str]:
        available = {self.model.joint(i).name for i in range(self.model.njnt)}
        names = [name for name in _UR5_ARM_JOINTS if name in available]
        if len(names) >= 6:
            return names[:6]
        hinge_names = [
            self.model.joint(i).name
            for i in range(self.model.njnt)
            if self.model.joint(i).type == mujoco.mjtJoint.mjJNT_HINGE
        ]
        return hinge_names[:6]

    def _detect_ee_site_id(self) -> int:
        for name in _EE_SITE_CANDIDATES:
            try:
                return mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, name)
            except Exception:
                continue
        if self.model.nsite > 0:
            return 0
        raise RuntimeError(
            "No site found for end-effector target. Please add a site (e.g. 'attachment_site') "
            "to the UR5 TCP in the model."
        )

    def _detect_arm_actuator_ids(self) -> List[int]:
        ids: List[int] = []
        for jname in self._arm_joint_names:
            for a in range(self.model.nu):
                trntype = self.model.actuator_trntype[a]
                if trntype != mujoco.mjtTrn.mjTRN_JOINT:
                    continue
                jid = int(self.model.actuator_trnid[a][0])
                if jid < 0:
                    continue
                if self.model.joint(jid).name == jname:
                    ids.append(a)
                    break
        return ids

    def _detect_gripper_joint_ids(self) -> List[int]:
        ids: List[int] = []
        for name in self.gripper_config.joint_names:
            try:
                jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            except Exception:
                continue
            if jid >= 0:
                ids.append(jid)
        if ids:
            return ids
        found: List[int] = []
        for i in range(self.model.njnt):
            jname = self.model.joint(i).name or ""
            if any(k in jname.lower() for k in ("finger", "grip", "gripper", "jaw")):
                found.append(i)
        return found

    def _detect_gripper_actuator_ids(self) -> List[int]:
        ids: List[int] = []
        for jid in self._gripper_joint_ids:
            jname = self.model.joint(jid).name
            for a in range(self.model.nu):
                if self.model.actuator_trntype[a] != mujoco.mjtTrn.mjTRN_JOINT:
                    continue
                trn_jid = int(self.model.actuator_trnid[a][0])
                if trn_jid == jid or self.model.joint(trn_jid).name == jname:
                    ids.append(a)
                    break
        return ids

    def _detect_gripper_range(self) -> Tuple[float, float]:
        if not self._gripper_joint_ids:
            return (self.gripper_config.close_value, self.gripper_config.open_value)
        lows, highs = [], []
        for jid in self._gripper_joint_ids:
            if self.model.jnt_range.shape[0] > jid:
                lows.append(float(self.model.jnt_range[jid][0]))
                highs.append(float(self.model.jnt_range[jid][1]))
        if lows and highs:
            return (float(np.mean(lows)), float(np.mean(highs)))
        return (self.gripper_config.close_value, self.gripper_config.open_value)

    def _add_sim_gripper_geoms(self) -> List[int]:
        """无真实夹爪时，在末端 site body 上追加两个可视化手指 geom，用于在 viewer 里看到开合。"""
        body_id = self._ee_body_id
        if body_id < 0:
            return []
        ids: List[int] = []
        side_offset = 0.04
        length = 0.06
        for side, sign in (("left", 1.0), ("right", -1.0)):
            # 直接在模型上追加 geom：通过临时改表实现
            self.model.ngeom += 1
            gid = self.model.ngeom - 1
            self.model.geom_bodyid[gid] = body_id
            self.model.geom_pos[gid] = [sign * side_offset, 0.0, 0.0]
            self.model.geom_size[gid] = [0.005, 0.005, length]
            self.model.geom_quat[gid] = [1.0, 0.0, 0.0, 0.0]
            self.model.geom_rgba[gid] = [0.2, 0.8, 0.2, 1.0]
            self.model.geom_type[gid] = mujoco.mjtGeom.mjGEOM_CAPSULE
            self.model.geom_contype[gid] = 0
            self.model.geom_conaffinity[gid] = 0
            self.model.geom_dataid[gid] = -1
            self.model.geom_matid[gid] = -1
            self.model.geom_texrepeat[gid] = [1.0, 1.0]
            self.model.geom_texuniform[gid] = 0
            self.model.geom_group[gid] = 2
            ids.append(gid)
        return ids

    # ------------------------------------------------------------------ 状态
    @property
    def ee_pos(self) -> np.ndarray:
        return np.array(self.data.site_xpos[self._ee_site_id], dtype=float)

    @property
    def ee_mat(self) -> np.ndarray:
        return np.array(self.data.site_xmat[self._ee_site_id].reshape(3, 3), dtype=float)

    def reset(self, qpos: Optional[ArrayLike] = None) -> None:
        mujoco.mj_resetData(self.model, self.data)
        if qpos is not None:
            qpos = np.asarray(qpos, dtype=float)
            n = min(len(qpos), self.model.nq)
            self.data.qpos[:n] = qpos[:n]
        else:
            # 默认用 UR5e home 位填手臂关节
            for value, adr in zip(_UR5E_HOME_QPOS, self._arm_qposadr):
                if adr >= 0:
                    self.data.qpos[adr] = float(value)
            if self._use_ctrl:
                for value, aid in zip(_UR5E_HOME_QPOS, self._arm_actuator_ids):
                    self.data.ctrl[aid] = float(value)
        if self._gripper_actuator_ids:
            self._apply_gripper_target(1.0)
        mujoco.mj_forward(self.model, self.data)

    # ------------------------------------------------------------------ IK
    def _ik_target_qpos(self, target_pos: np.ndarray) -> np.ndarray:
        """用阻尼最小二乘雅可比迭代求解手臂关节角（不直接写入仿真状态）。"""
        q_arm = np.array(
            [self.data.qpos[adr] for adr in self._arm_qposadr], dtype=float
        )
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        for _ in range(self.max_steps_per_move):
            mujoco.mj_forward(self.model, self.data)
            err = target_pos - self.ee_pos
            if np.linalg.norm(err) <= self.pos_tol:
                break
            mujoco.mj_jacSite(self.model, self.data, jacp, jacr, self._ee_site_id)
            j = jacp[:, self._arm_dof_indices]
            jt = j.T
            damping_mat = self.damping * np.eye(3)
            dq = jt @ np.linalg.solve(j @ jt + damping_mat, err)
            # 限制单步幅度，避免抖动
            step = float(np.clip(0.5, 0.0, 1.0))
            q_arm = q_arm + dq * step
            for value, adr in zip(q_arm, self._arm_qposadr):
                self.data.qpos[adr] = float(value)
        mujoco.mj_forward(self.model, self.data)
        return q_arm

    def _set_arm_ctrl(self, q_arm: np.ndarray) -> None:
        for value, aid in zip(q_arm, self._arm_actuator_ids):
            self.data.ctrl[aid] = float(value)
        # 保持夹爪当前目标状态（避免手臂控制覆盖夹爪 ctrl）
        if self._gripper_actuator_ids:
            for aid, target in zip(self._gripper_actuator_ids, self._gripper_ctrl_targets):
                self.data.ctrl[aid] = float(target)

    # ------------------------------------------------------------------ 动作
    def move_to(
        self,
        x: float,
        y: float,
        z: float,
        *,
        tolerance: Optional[float] = None,
        max_steps: Optional[int] = None,
    ) -> np.ndarray:
        target = np.array([x, y, z], dtype=float)
        tol = float(self.pos_tol if tolerance is None else tolerance)
        steps = int(self.max_steps_per_move if max_steps is None else max_steps)

        if self._use_ctrl:
            # 有 actuator：IK 出目标关节角，再用 ctrl 位置控制 + 仿真步进收敛
            self._ik_target_qpos(target)
            target_qpos = np.array(
                [self.data.qpos[adr] for adr in self._arm_qposadr], dtype=float
            )
            self._set_arm_ctrl(target_qpos)
            for i in range(steps):
                mujoco.mj_step(self.model, self.data)
                if i % 2 == 0:
                    mujoco.mj_forward(self.model, self.data)
                err = np.linalg.norm(target - self.ee_pos)
                if err <= tol:
                    break
        else:
            # 无 actuator：直接写 qpos + forward 做运动学移动
            self._ik_target_qpos(target)
            for i in range(steps):
                err = np.linalg.norm(target - self.ee_pos)
                if err <= tol:
                    break
                self._ik_target_qpos(target)
                if i % 2 == 0:
                    mujoco.mj_forward(self.model, self.data)
        return self.ee_pos.copy()

    def move_above(self, x: float, y: float, z: float, height: float = 0.12) -> np.ndarray:
        return self.move_to(x, y, z + height)

    # ------------------------------------------------------------------ 夹爪
    def _apply_gripper_target(self, open_amount: float) -> None:
        open_amount = float(np.clip(open_amount, 0.0, 1.0))
        if self._gripper_actuator_ids:
            # 对称双指：left 向负方向，right 向正方向
            low, high = -0.02, 0.02
            left_target = high if open_amount >= 0.5 else low
            right_target = low if open_amount >= 0.5 else high
            self._gripper_ctrl_targets = [left_target, right_target]
            self._gripper_open_state = open_amount >= 0.5
            for aid, target in zip(self._gripper_actuator_ids, self._gripper_ctrl_targets):
                self.data.ctrl[aid] = float(target)
            for _ in range(80):
                mujoco.mj_step(self.model, self.data)
        elif self._gripper_joint_ids:
            low, high = self._gripper_range
            target = low + (high - low) * open_amount
            for jid in self._gripper_joint_ids:
                adr = self.model.jnt_qposadr[jid]
                self.data.qpos[adr] = target
            mujoco.mj_forward(self.model, self.data)
        elif self._sim_gripper_geom_ids:
            offset = 0.0 if open_amount <= 0.5 else 0.05
            self._set_sim_gripper_offset(offset)

    def _set_sim_gripper_offset(self, offset: float) -> None:
        # 模拟夹爪几何已被移除（动态修改 ngeom 不可靠），此处空实现。
        pass

    def grasp(self) -> None:
        self._apply_gripper_target(0.0)

    def release(self) -> None:
        self._apply_gripper_target(1.0)

    # ------------------------------------------------------------------ 动作分发
    def execute_action(self, action: Union[str, Dict[str, Any]]) -> Any:
        if isinstance(action, str):
            action = {"type": action}
        action_type = action.get("type")
        if action_type == "move_to":
            return self.move_to(*action[_ACTION_TARGET_KEY])
        if action_type == "move_above":
            target = action[_ACTION_TARGET_KEY]
            height = float(action.get("height", 0.12))
            return self.move_above(*target, height=height)
        if action_type == "grasp":
            return self.grasp()
        if action_type == "release":
            return self.release()
        raise ValueError(f"Unsupported action type: {action_type}")

    def render(self, viewer: Any) -> None:
        if viewer is not None:
            viewer.sync()

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            mujoco.mj_step(self.model, self.data)

    # ------------------------------------------------------------------ demo
    def pick_and_place_demo(
        self,
        pick_xyz: Sequence[float] = (0.4, 0.2, 0.05),
        place_xyz: Sequence[float] = (0.4, -0.2, 0.05),
        approach_height: float = 0.15,
        settle_steps: int = 60,
    ) -> None:
        pick_xyz = tuple(map(float, pick_xyz))
        place_xyz = tuple(map(float, place_xyz))
        self.release()
        self.move_above(*pick_xyz, height=approach_height)
        self.move_to(*pick_xyz)
        self.grasp()
        self.step(settle_steps)
        self.move_above(*pick_xyz, height=approach_height)
        self.move_above(*place_xyz, height=approach_height)
        self.move_to(*place_xyz)
        self.release()
        self.step(settle_steps)
        self.move_above(*place_xyz, height=approach_height)
        mujoco.mj_forward(self.model, self.data)


def _make_viewer_if_available(model: mujoco.MjModel, data: mujoco.MjData):
    if _mujoco_viewer_mod is None:
        return None
    try:
        return _mujoco_viewer_mod.launch_passive(model, data)
    except Exception:
        return None


def _default_model_path() -> str:
    # 默认指向仓库内 VLA-Desk 的官方 UR5e 模型
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "simulation", "universal_robots_ur5e", "ur5e.xml"),
        os.path.join(here, "..", "..", "simulation", "universal_robots_ur5e", "scene.xml"),
        os.path.join(here, "..", "simulation", "universal_robots_ur5e", "ur5e.xml"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="UR5/UR5e MuJoCo environment demo")
    parser.add_argument(
        "--model",
        default=_default_model_path(),
        help="Path to the UR5 MuJoCo XML model (ur5e.xml / scene.xml)",
    )
    parser.add_argument(
        "--pick", nargs=3, type=float, default=(0.4, 0.2, 0.05), help="Pick position x y z"
    )
    parser.add_argument(
        "--place", nargs=3, type=float, default=(0.4, -0.2, 0.05), help="Place position x y z"
    )
    parser.add_argument("--no-viewer", action="store_true", help="Run without opening a viewer")
    args = parser.parse_args()

    print(f"Loading model: {args.model}")
    env = MujocoUR5Env(args.model)
    env.reset()
    viewer = None if args.no_viewer else _make_viewer_if_available(env.model, env.data)

    try:
        print("Running pick-and-place demo ...")
        env.pick_and_place_demo(args.pick, args.place)
        print("Demo finished. End-effector position:", env.ee_pos)
        if viewer is not None:
            while viewer.is_running():
                mujoco.mj_step(env.model, env.data)
                viewer.sync()
                time.sleep(env.model.opt.timestep)
    finally:
        if viewer is not None:
            viewer.close()


if __name__ == "__main__":
    main()
