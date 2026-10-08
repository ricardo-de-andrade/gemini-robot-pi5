from __future__ import annotations
"""Kinematics and coordinate system for robot joints with strict boundary enforcement."""

import logging
from typing import Dict, Tuple
from config import JOINT_LIMITS, STEPS_PER_REV, JointLimits

logger = logging.getLogger(__name__)


class KinematicsBoundaryError(ValueError):
    """Raised when a commanded movement violates physical joint limits."""
    pass


class Kinematics:
    """Manages joint positions, angles, step conversions, and motion boundary safety."""

    def __init__(self, steps_per_rev: int = STEPS_PER_REV):
        self.steps_per_rev = steps_per_rev
        self.steps_per_deg: float = self.steps_per_rev / 360.0

        # Current angle in degrees for each joint
        self.current_angles: Dict[str, float] = {
            joint: limits.home_angle for joint, limits in JOINT_LIMITS.items()
        }

        # Current step counter relative to home position (0 steps = home)
        self.current_steps: Dict[str, int] = {
            joint: 0 for joint in JOINT_LIMITS.keys()
        }

    def angle_to_steps(self, degrees: float) -> int:
        """Convert angular degrees to motor half-steps."""
        return int(round(degrees * self.steps_per_deg))

    def steps_to_angle(self, steps: int) -> float:
        """Convert motor half-steps to angular degrees."""
        return steps / self.steps_per_deg

    def validate_and_clamp_angle(self, joint: str, target_angle: float, clamp: bool = True) -> float:
        """
        Check if target angle is within allowable boundaries.
        If clamp is True, returns clamped angle and logs a warning.
        If clamp is False, raises KinematicsBoundaryError if out of bounds.
        """
        if joint not in JOINT_LIMITS:
            raise KeyError(f"Unknown joint: '{joint}'. Valid joints: {list(JOINT_LIMITS.keys())}")

        limits: JointLimits = JOINT_LIMITS[joint]

        if limits.min_angle <= target_angle <= limits.max_angle:
            return float(target_angle)

        if clamp:
            clamped = max(limits.min_angle, min(limits.max_angle, target_angle))
            logger.warning(
                f"Target angle {target_angle:.1f}° for joint '{joint}' violates limits "
                f"[{limits.min_angle}°, {limits.max_angle}°]. Clamping to {clamped:.1f}°"
            )
            return float(clamped)
        else:
            raise KinematicsBoundaryError(
                f"Target angle {target_angle:.1f}° for '{joint}' exceeds safe bounds "
                f"[{limits.min_angle}°, {limits.max_angle}°]."
            )

    def plan_absolute_movement(self, joint: str, target_angle: float, clamp: bool = True) -> Tuple[int, float]:
        """
        Calculate the required step delta to move a joint to an absolute target angle.
        
        :return: (steps_delta, final_angle)
        """
        safe_target = self.validate_and_clamp_angle(joint, target_angle, clamp=clamp)
        current = self.current_angles[joint]
        delta_angle = safe_target - current
        delta_steps = self.angle_to_steps(delta_angle)

        return delta_steps, safe_target

    def plan_relative_movement(self, joint: str, delta_angle: float, clamp: bool = True) -> Tuple[int, float]:
        """
        Calculate the required step delta to move a joint relative to its current angle.
        
        :return: (steps_delta, final_angle)
        """
        current = self.current_angles[joint]
        target_angle = current + delta_angle
        return self.plan_absolute_movement(joint, target_angle, clamp=clamp)

    def update_position(self, joint: str, actual_steps_moved: int, final_angle: float) -> None:
        """Update internal tracking after a successful movement."""
        self.current_steps[joint] += actual_steps_moved
        self.current_angles[joint] = final_angle
        logger.debug(
            f"Joint '{joint}' now at {self.current_angles[joint]:.1f}° "
            f"({self.current_steps[joint]} steps from home)"
        )

    def calibrate_home(self, joint: str | None = None) -> None:
        """
        Reset software position tracking to Home (0°).
        If joint is None, resets all joints.
        """
        joints = [joint] if joint else list(JOINT_LIMITS.keys())
        for j in joints:
            self.current_angles[j] = JOINT_LIMITS[j].home_angle
            self.current_steps[j] = 0
            logger.info(f"Joint '{j}' calibrated to home ({self.current_angles[j]}°)")

    def get_status(self) -> Dict[str, Dict[str, float | str]]:
        """Return human-readable posture status for all joints."""
        status = {}
        for joint, limits in JOINT_LIMITS.items():
            status[joint] = {
                "name": limits.name,
                "angle": round(self.current_angles[joint], 1),
                "steps": self.current_steps[joint],
                "min": limits.min_angle,
                "max": limits.max_angle,
            }
        return status
