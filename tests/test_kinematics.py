import sys
from pathlib import Path

# Add project root to sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import unittest
from robot.motors.kinematics import Kinematics, KinematicsBoundaryError
from config import JOINT_LIMITS


class TestKinematics(unittest.TestCase):

    def test_initial_posture(self):
        k = Kinematics()
        status = k.get_status()
        for joint, lim in JOINT_LIMITS.items():
            self.assertEqual(status[joint]["angle"], lim.home_angle)
            self.assertEqual(status[joint]["steps"], 0)

    def test_arm_boundaries(self):
        k = Kinematics()
        # Left Arm: valid range is 0° to 170°
        # Forward valid movement
        steps, angle = k.plan_absolute_movement("left_arm", 90.0)
        self.assertEqual(angle, 90.0)
        self.assertGreater(steps, 0)

        # Moving backwards past 0° must be clamped to 0°
        steps, angle = k.plan_absolute_movement("left_arm", -30.0, clamp=True)
        self.assertEqual(angle, 0.0)

        # Test error raising when clamp=False
        with self.assertRaises(KinematicsBoundaryError):
            k.plan_absolute_movement("left_arm", -10.0, clamp=False)

        # Exceeding max angle (e.g. 200°) must clamp to 170°
        steps, angle = k.plan_absolute_movement("left_arm", 200.0, clamp=True)
        self.assertEqual(angle, 170.0)

    def test_head_and_body_boundaries(self):
        k = Kinematics()
        # Head: valid range is -90° to +90°
        # Left turn
        steps, angle = k.plan_absolute_movement("head", -60.0)
        self.assertEqual(angle, -60.0)
        self.assertLess(steps, 0)

        # Rotating backwards past -90° must clamp to -90°
        steps, angle = k.plan_absolute_movement("head", -120.0, clamp=True)
        self.assertEqual(angle, -90.0)

        # Rotating backwards past +90° must clamp to +90°
        steps, angle = k.plan_absolute_movement("head", 150.0, clamp=True)
        self.assertEqual(angle, 90.0)

    def test_step_conversion_accuracy(self):
        k = Kinematics(steps_per_rev=4096)
        # 360 deg = 4096 steps
        # 90 deg = 1024 steps
        # 180 deg = 2048 steps
        self.assertEqual(k.angle_to_steps(90.0), 1024)
        self.assertEqual(k.angle_to_steps(180.0), 2048)
        self.assertEqual(k.angle_to_steps(0.0), 0)
        self.assertAlmostEqual(k.steps_to_angle(1024), 90.0, places=2)

    def test_position_tracking(self):
        k = Kinematics()
        steps, target = k.plan_absolute_movement("right_arm", 45.0)
        k.update_position("right_arm", steps, target)

        self.assertEqual(k.current_angles["right_arm"], 45.0)
        self.assertEqual(k.current_steps["right_arm"], steps)

        # Calibrate home reset
        k.calibrate_home("right_arm")
        self.assertEqual(k.current_angles["right_arm"], 0.0)
        self.assertEqual(k.current_steps["right_arm"], 0)


if __name__ == "__main__":
    unittest.main()
