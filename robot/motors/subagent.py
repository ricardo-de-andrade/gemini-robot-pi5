from __future__ import annotations
"""Motor Controller Subagent: Background thread executive for physical robot actions."""

import logging
import queue
import threading
import time
from typing import Dict, Literal, Optional, Callable, Any

from config import MOTOR_PINS, MOTOR_INVERTED, STEP_DELAY_SEC
from robot.motors.stepper import StepperMotor
from robot.motors.kinematics import Kinematics

logger = logging.getLogger(__name__)


class MotorControllerSubagent:
    """
    Autonomous subagent managing 4 stepper motors with thread-safe queue execution
    and high-level robot gestures.
    """

    def __init__(self, mock: bool = False, step_delay: float = STEP_DELAY_SEC):
        self.mock = mock
        self.step_delay = step_delay
        self.kinematics = Kinematics()

        # Initialize the 4 Stepper Motors
        self.motors: Dict[str, StepperMotor] = {}
        for joint_name, pins in MOTOR_PINS.items():
            self.motors[joint_name] = StepperMotor(
                name=joint_name,
                pins=pins,
                step_delay=step_delay,
                mock=mock,
                inverted=MOTOR_INVERTED.get(joint_name, False),
            )

        # Work queue and background worker thread for non-blocking execution
        self._action_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._process_queue,
            name="MotorSubagentWorker",
            daemon=True
        )
        self._worker_thread.start()

        # Lock to ensure only one movement sequence runs at a time
        self._motion_lock = threading.RLock()
        logger.info("Motor Controller Subagent initialized and worker running.")

    @property
    def is_moving(self) -> bool:
        """Returns True if the motor motion lock is currently held (robot is physically moving)."""
        acquired = self._motion_lock.acquire(blocking=False)
        if acquired:
            self._motion_lock.release()
            return False
        return True

    def _process_queue(self) -> None:
        """Worker loop executing queued actions sequentially."""
        while not self._stop_event.is_set():
            try:
                task = self._action_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            func, args, kwargs, callback = task
            try:
                with self._motion_lock:
                    result = func(*args, **kwargs)
                if callback:
                    callback(result, None)
            except Exception as e:
                logger.error(f"Error executing motor task {func.__name__}: {e}", exc_info=True)
                if callback:
                    callback(None, e)
            finally:
                self._action_queue.task_done()

    def submit_action(
        self,
        func: Callable,
        *args: Any,
        callback: Optional[Callable[[Any, Optional[Exception]], None]] = None,
        **kwargs: Any
    ) -> None:
        """Submit an action asynchronously to the subagent's execution queue."""
        self._action_queue.put((func, args, kwargs, callback))

    # =========================================================================
    # Direct Motor Operations (Synchronous / Internal)
    # =========================================================================

    def _move_joint_absolute(self, joint: str, target_angle: float) -> str:
        """Move single joint to an absolute target angle."""
        if joint not in self.motors:
            raise KeyError(f"Invalid joint '{joint}'")

        with self._motion_lock:
            steps, final_angle = self.kinematics.plan_absolute_movement(joint, target_angle, clamp=True)
            if steps != 0:
                logger.info(f"Moving '{joint}' to {final_angle:.1f}° ({steps:+d} steps) -> Driving {self.motors[joint].pins_description}...")
                self.motors[joint].step(steps)
                self.kinematics.update_position(joint, steps, final_angle)
            return f"{joint} reached {final_angle:.1f}°"

    def _move_joint_relative(self, joint: str, delta_angle: float) -> str:
        """Move single joint relative to current angle."""
        if joint not in self.motors:
            raise KeyError(f"Invalid joint '{joint}'")

        with self._motion_lock:
            steps, final_angle = self.kinematics.plan_relative_movement(joint, delta_angle, clamp=True)
            if steps != 0:
                logger.info(f"Moving '{joint}' by {delta_angle:.1f}° to {final_angle:.1f}° ({steps:+d} steps) -> Driving {self.motors[joint].pins_description}...")
                self.motors[joint].step(steps)
                self.kinematics.update_position(joint, steps, final_angle)
            return f"{joint} at {final_angle:.1f}°"

    def _move_joints_simultaneous(self, targets: Dict[str, float]) -> str:
        """Move multiple joints concurrently using threads while holding _motion_lock."""
        with self._motion_lock:
            plans = {}
            for joint, target_angle in targets.items():
                if joint not in self.motors:
                    continue
                steps, final_angle = self.kinematics.plan_absolute_movement(joint, target_angle, clamp=True)
                plans[joint] = (steps, final_angle)

            threads = []
            for joint, (steps, final_angle) in plans.items():
                if steps != 0:
                    logger.info(f"Moving '{joint}' to {final_angle:.1f}° ({steps:+d} steps) -> Driving {self.motors[joint].pins_description}...")
                    t = threading.Thread(target=self.motors[joint].step, args=(steps,))
                    threads.append((t, joint, steps, final_angle))
                    t.start()

            for t, joint, steps, final_angle in threads:
                t.join()
                self.kinematics.update_position(joint, steps, final_angle)

            return ", ".join(f"{j} reached {ang:.1f}°" for j, (_, ang) in plans.items())

    # =========================================================================
    # High-Level Robot Actions (Synchronous implementations dispatched to worker)
    # =========================================================================

    def move_arm(
        self,
        arm: Literal["left", "right", "both"],
        position: Optional[Literal["up", "down", "halfway"]] = None,
        angle: Optional[float] = None
    ) -> str:
        """
        Move robot arm(s) up (towards head), down (towards body), or to a specific angle.
        Enforces: 0° <= angle <= 170° (no backward motion).
        """
        if angle is None:
            if position == "up":
                target_angle = 160.0
            elif position == "halfway":
                target_angle = 90.0
            else:  # "down" or default
                target_angle = 0.0
        else:
            target_angle = float(angle)

        if arm == "both":
            return self._move_joints_simultaneous({"left_arm": target_angle, "right_arm": target_angle})
        elif arm == "left":
            return self._move_joint_absolute("left_arm", target_angle)
        else:
            return self._move_joint_absolute("right_arm", target_angle)

    def rotate_head(
        self,
        direction: Optional[Literal["left", "right", "center"]] = None,
        angle: Optional[float] = None
    ) -> str:
        """
        Rotate robot head left or right (-90° to +90°). Cannot rotate backwards.
        """
        if angle is None:
            if direction == "left":
                target_angle = -60.0
            elif direction == "right":
                target_angle = 60.0
            else:  # "center"
                target_angle = 0.0
        else:
            target_angle = float(angle)
            if direction == "left" and target_angle > 0:
                target_angle = -target_angle

        return self._move_joint_absolute("head", target_angle)

    def rotate_body(
        self,
        direction: Optional[Literal["left", "right", "center"]] = None,
        angle: Optional[float] = None
    ) -> str:
        """
        Rotate robot waist/body left or right (-90° to +90°).
        """
        if angle is None:
            if direction == "left":
                target_angle = -45.0
            elif direction == "right":
                target_angle = 45.0
            else:  # "center"
                target_angle = 0.0
        else:
            target_angle = float(angle)
            if direction == "left" and target_angle > 0:
                target_angle = -target_angle

        return self._move_joint_absolute("body", target_angle)

    def wave(self, arm: Literal["left", "right", "both"] = "both") -> str:
        """Raise arm to waving level and move up and down to wave warmly and briskly."""
        logger.info(f"Performing friendly wave gesture with {arm} arm(s)")
        if arm == "both":
            # 1. Raise both arms together to 85°
            self._move_joints_simultaneous({"left_arm": 85.0, "right_arm": 85.0})
            time.sleep(0.04)

            # 2. Gentle wave up and down
            self._move_joints_simultaneous({"left_arm": 102.0, "right_arm": 102.0})
            time.sleep(0.04)
            self._move_joints_simultaneous({"left_arm": 75.0, "right_arm": 75.0})
            time.sleep(0.04)

            # 3. Lower both arms smoothly back to home position (0°)
            self._move_joints_simultaneous({"left_arm": 0.0, "right_arm": 0.0})
            return "Waved with both arms simultaneously"
        else:
            target_joint = "left_arm" if arm == "left" else "right_arm"
            self._move_joint_absolute(target_joint, 85.0)
            time.sleep(0.04)
            self._move_joint_absolute(target_joint, 102.0)
            time.sleep(0.04)
            self._move_joint_absolute(target_joint, 75.0)
            time.sleep(0.04)
            self._move_joint_absolute(target_joint, 0.0)
            return f"Waved with {arm} arm"

    def nod(self) -> str:
        """Shake head slightly left and right as an acknowledgment."""
        logger.info("Performing head acknowledgment nod/turn")
        self._move_joint_absolute("head", 20.0)
        time.sleep(0.05)
        self._move_joint_absolute("head", -20.0)
        time.sleep(0.05)
        self._move_joint_absolute("head", 0.0)
        return "Head acknowledged"

    def celebrate(self) -> str:
        """Raise both arms, wiggle body left and right, then lower."""
        logger.info("Performing celebrate gesture")
        self.move_arm(arm="both", angle=160.0)
        time.sleep(0.1)
        self._move_joint_absolute("body", 30.0)
        time.sleep(0.1)
        self._move_joint_absolute("body", -30.0)
        time.sleep(0.1)
        self._move_joint_absolute("body", 0.0)
        time.sleep(0.1)
        self.move_arm(arm="both", position="down")
        return "Celebrated happily"

    def look_around(self) -> str:
        """Survey environment by turning head left, then right, then center."""
        logger.info("Performing look around gesture")
        self._move_joint_absolute("head", -60.0)
        time.sleep(0.3)
        self._move_joint_absolute("head", 60.0)
        time.sleep(0.3)
        self._move_joint_absolute("head", 0.0)
        return "Looked around"

    def reset_to_home(self) -> str:
        """Safely return all joints to zero/home position."""
        logger.info("Resetting all joints to home position (0°)")
        for joint in ["left_arm", "right_arm", "head", "body"]:
            self._move_joint_absolute(joint, 0.0)
        return "All joints returned to Home (0°)"

    def get_posture(self) -> Dict[str, Dict[str, float | str]]:
        """Get current posture details from kinematics."""
        return self.kinematics.get_status()

    def close(self) -> None:
        """Shut down background worker and release motor pins."""
        self._stop_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)

        for motor in self.motors.values():
            motor.close()
        logger.info("Motor Controller Subagent shutdown successfully.")
