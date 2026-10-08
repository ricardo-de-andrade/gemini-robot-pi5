"""Unit tests for StepperMotor direction inversion and step sequence."""

import unittest
from robot.motors.stepper import StepperMotor, HALF_STEP_SEQUENCE


class TestStepperMotor(unittest.TestCase):
    def test_stepper_normal_direction(self):
        motor = StepperMotor(name="test_normal", pins=(1, 2, 3, 4), mock=True, inverted=False)
        self.assertEqual(motor.seq_index, 0)
        self.assertFalse(motor.inverted)

        # 1 step forward
        motor.step(1)
        self.assertEqual(motor.seq_index, 1)

        # 1 step reverse
        motor.step(-1)
        self.assertEqual(motor.seq_index, 0)

    def test_stepper_inverted_direction(self):
        motor = StepperMotor(name="test_inverted", pins=(1, 2, 3, 4), mock=True, inverted=True)
        self.assertEqual(motor.seq_index, 0)
        self.assertTrue(motor.inverted)

        # 1 step forward should step in reverse sequence when inverted
        seq_len = len(HALF_STEP_SEQUENCE)
        motor.step(1)
        self.assertEqual(motor.seq_index, seq_len - 1)

        # 1 step reverse should step forward in sequence when inverted
        motor.step(-1)
        self.assertEqual(motor.seq_index, 0)


if __name__ == "__main__":
    unittest.main()
