import sys
from pathlib import Path

# Add project root to sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import unittest
from robot.motors.subagent import MotorControllerSubagent
from robot.agent.tools import MotorToolDispatcher, get_tool_declarations


class TestDispatcher(unittest.TestCase):

    def test_tool_declarations(self):
        tools = get_tool_declarations()
        tool_names = [t["name"] for t in tools]
        self.assertIn("control_arm", tool_names)
        self.assertIn("rotate_head", tool_names)
        self.assertIn("rotate_body", tool_names)
        self.assertIn("perform_gesture", tool_names)
        self.assertIn("get_robot_posture", tool_names)

    def test_motor_subagent_mock_gestures(self):
        subagent = MotorControllerSubagent(mock=True, step_delay=0.0001)
        dispatcher = MotorToolDispatcher(subagent)

        try:
            # Test arm control tool
            res = dispatcher.dispatch("control_arm", {"arm": "right", "position": "up"})
            self.assertEqual(res["status"], "success")

            # Test head rotation tool
            res = dispatcher.dispatch("rotate_head", {"direction": "left", "angle": 45.0})
            self.assertEqual(res["status"], "success")

            # Test body rotation tool
            res = dispatcher.dispatch("rotate_body", {"direction": "right", "angle": 30.0})
            self.assertEqual(res["status"], "success")

            # Test gesture tool
            res = dispatcher.dispatch("perform_gesture", {"gesture": "wave"})
            self.assertEqual(res["status"], "success")

            # Test posture inquiry
            res = dispatcher.dispatch("get_robot_posture", {})
            self.assertEqual(res["status"], "success")
            self.assertIn("head", res["posture"])
            self.assertIn("left_arm", res["posture"])

            # Test unknown gesture handling
            res = dispatcher.dispatch("perform_gesture", {"gesture": "fly_away"})
            self.assertEqual(res["status"], "error")

        finally:
            subagent.close()


if __name__ == "__main__":
    unittest.main()
