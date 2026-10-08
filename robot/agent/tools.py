from __future__ import annotations
"""Function declarations and tool dispatcher for the Gemini Live API."""

import logging
from typing import Any, Dict, List, Optional
from robot.motors.subagent import MotorControllerSubagent

logger = logging.getLogger(__name__)


def get_tool_declarations() -> List[Dict[str, Any]]:
    """Return JSON schema declarations for Gemini function calling."""
    return [
        {
            "name": "control_arm",
            "description": (
                "Controls the robot's physical arm(s). Arms can move up (next to head, 170°) "
                "or down (next to body, 0°). Cannot rotate backwards behind the body."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "arm": {
                        "type": "STRING",
                        "description": "Which arm to move ('left', 'right', or 'both')",
                        "enum": ["left", "right", "both"]
                    },
                    "position": {
                        "type": "STRING",
                        "description": "Preset position: 'up' (next to head), 'down' (next to body), or 'halfway'",
                        "enum": ["up", "down", "halfway"]
                    },
                    "angle": {
                        "type": "NUMBER",
                        "description": "Optional specific angle in degrees from 0 (down) to 170 (up)."
                    }
                },
                "required": ["arm"]
            }
        },
        {
            "name": "rotate_head",
            "description": (
                "Rotates the robot's head side to side. "
                "Angle limits are -90° (left) to +90° (right). Cannot rotate backwards."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "direction": {
                        "type": "STRING",
                        "description": "Preset direction to turn head towards",
                        "enum": ["left", "right", "center"]
                    },
                    "angle": {
                        "type": "NUMBER",
                        "description": "Target angle in degrees: negative for left (-90° max), positive for right (+90° max)."
                    }
                }
            }
        },
        {
            "name": "rotate_body",
            "description": (
                "Rotates the robot's waist/body side to side. "
                "Angle limits are -90° (left) to +90° (right). Cannot rotate backwards."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "direction": {
                        "type": "STRING",
                        "description": "Preset direction to turn body towards",
                        "enum": ["left", "right", "center"]
                    },
                    "angle": {
                        "type": "NUMBER",
                        "description": "Target angle in degrees: negative for left (-90° max), positive for right (+90° max)."
                    }
                }
            }
        },
        {
            "name": "perform_gesture",
            "description": (
                "Performs an expressive multi-joint physical gesture. Use this while talking "
                "to express emotions or react naturally to the conversation."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "gesture": {
                        "type": "STRING",
                        "description": "The expressive gesture to perform",
                        "enum": ["wave", "nod", "celebrate", "look_around", "reset_home"]
                    },
                    "arm": {
                        "type": "STRING",
                        "description": "Optional arm for wave gesture ('left', 'right', or 'both', defaults to 'both')",
                        "enum": ["left", "right", "both"]
                    }
                },
                "required": ["gesture"]
            }
        },
        {
            "name": "get_robot_posture",
            "description": "Returns the current angles and step counts for all 4 joints.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        }
    ]


class MotorToolDispatcher:
    """Dispatches Gemini Live API tool call requests to the Motor Controller Subagent."""

    def __init__(self, subagent: MotorControllerSubagent):
        self.subagent = subagent

    def dispatch(self, function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the requested function on the motor subagent and return structured output."""
        logger.info(f"Tool call received: {function_name} with arguments: {args}")

        try:
            if function_name == "control_arm":
                arm = args.get("arm", "right")
                pos = args.get("position")
                angle = args.get("angle")
                result = self.subagent.move_arm(arm=arm, position=pos, angle=angle)
                return {"status": "success", "result": result}

            elif function_name == "rotate_head":
                direction = args.get("direction")
                angle = args.get("angle")
                result = self.subagent.rotate_head(direction=direction, angle=angle)
                return {"status": "success", "result": result}

            elif function_name == "rotate_body":
                direction = args.get("direction")
                angle = args.get("angle")
                result = self.subagent.rotate_body(direction=direction, angle=angle)
                return {"status": "success", "result": result}

            elif function_name == "perform_gesture":
                gesture = args.get("gesture")
                arm = args.get("arm", "both")
                if gesture == "wave":
                    result = self.subagent.wave(arm=arm)
                elif gesture == "nod":
                    result = self.subagent.nod()
                elif gesture == "celebrate":
                    result = self.subagent.celebrate()
                elif gesture == "look_around":
                    result = self.subagent.look_around()
                elif gesture == "reset_home":
                    result = self.subagent.reset_to_home()
                else:
                    return {"status": "error", "message": f"Unknown gesture '{gesture}'"}
                return {"status": "success", "result": result}

            elif function_name == "get_robot_posture":
                posture = self.subagent.get_posture()
                return {"status": "success", "posture": posture}

            else:
                return {"status": "error", "message": f"Unknown tool '{function_name}'"}

        except Exception as e:
            logger.error(f"Error dispatching tool {function_name}: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
