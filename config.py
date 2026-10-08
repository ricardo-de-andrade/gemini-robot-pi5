from __future__ import annotations
"""Configuration for Raspberry Pi 5 4-Motor Robot & Gemini Live Agent."""

import os
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

# ==============================================================================
# 1. Hardware & Stepper Motor Configuration
# ==============================================================================

# 28BYJ-48 Stepper Motor Specs (Nominally ~4096 half-steps per 360 degree revolution)
# Gear reduction is ~63.684:1, 64 steps per internal motor revolution in half-step mode.
STEPS_PER_REV: int = 4096

# Step pulse delay (in seconds) between half-steps.
# 0.0020s (2.0ms) provides optimal speed and high torque for 28BYJ-48 on Pi 5.
STEP_DELAY_SEC: float = 0.0020

# BCM Pinout for the 4 ULN2003 Driver Boards
# Safe for Raspberry Pi 5 (RP1 I/O controller) avoiding I2C/SPI/UART conflicts.
MOTOR_PINS: Dict[str, Tuple[int, int, int, int]] = {
    # IN1, IN2, IN3, IN4
    "left_arm": (17, 27, 22, 23),
    "right_arm": (24, 25, 5, 6),
    "head": (12, 13, 16, 19),
    "body": (20, 21, 26, 18),
}

# Motor direction inversion: Set to True if joint moves in reverse direction due to physical mounting / wiring.
# Left arm is mounted mirror-image to right arm, so its rotation direction is inverted.
MOTOR_INVERTED: Dict[str, bool] = {
    "left_arm": os.getenv("MOTOR_INVERT_LEFT_ARM", "true").lower() in ("1", "true", "yes"),
    "right_arm": os.getenv("MOTOR_INVERT_RIGHT_ARM", "false").lower() in ("1", "true", "yes"),
    "head": os.getenv("MOTOR_INVERT_HEAD", "false").lower() in ("1", "true", "yes"),
    "body": os.getenv("MOTOR_INVERT_BODY", "false").lower() in ("1", "true", "yes"),
}

# 40-Pin Header Physical Pin Mapping for BCM GPIOs (Raspberry Pi 5 J8 header)
BCM_TO_PHYSICAL: Dict[int, int] = {
    2: 3, 3: 5, 4: 7, 14: 8, 15: 10, 17: 11, 18: 12, 27: 13, 22: 15,
    23: 16, 24: 18, 10: 19, 9: 21, 25: 22, 11: 23, 8: 24, 7: 26, 0: 27,
    1: 28, 5: 29, 6: 31, 12: 32, 13: 33, 19: 35, 16: 36, 26: 37, 20: 38,
    21: 40
}

# ==============================================================================
# 2. Kinematics & Angular Movement Constraints
# ==============================================================================

@dataclass(frozen=True)
class JointLimits:
    min_angle: float
    max_angle: float
    home_angle: float
    name: str
    description: str

JOINT_LIMITS: Dict[str, JointLimits] = {
    # Arms: 0 deg = down next to body, 170 deg = raised next to head.
    # Strict constraint: cannot swing backwards (< 0 deg).
    "left_arm": JointLimits(
        min_angle=0.0,
        max_angle=170.0,
        home_angle=0.0,
        name="Left Arm",
        description="0° is down at side, 170° is fully raised next to head. Cannot go backwards."
    ),
    "right_arm": JointLimits(
        min_angle=0.0,
        max_angle=170.0,
        home_angle=0.0,
        name="Right Arm",
        description="0° is down at side, 170° is fully raised next to head. Cannot go backwards."
    ),
    # Head: -90 deg = turned left, 0 deg = forward, +90 deg = turned right.
    # Strict constraint: cannot rotate backwards.
    "head": JointLimits(
        min_angle=-90.0,
        max_angle=90.0,
        home_angle=0.0,
        name="Head",
        description="-90° is full left, 0° is forward, +90° is full right. Cannot rotate backwards."
    ),
    # Body (Waist): -90 deg = turned left, 0 deg = forward, +90 deg = turned right.
    # Strict constraint: cannot rotate backwards.
    "body": JointLimits(
        min_angle=-90.0,
        max_angle=90.0,
        home_angle=0.0,
        name="Body / Waist",
        description="-90° is full left, 0° is forward, +90° is full right. Cannot rotate backwards."
    ),
}

# Half-step sequence for ULN2003 driving 28BYJ-48 (8 states for smooth movement)
# 1 = energized coil, 0 = de-energized
HALF_STEP_SEQUENCE = [
    (1, 0, 0, 0),
    (1, 1, 0, 0),
    (0, 1, 0, 0),
    (0, 1, 1, 0),
    (0, 0, 1, 0),
    (0, 0, 1, 1),
    (0, 0, 0, 1),
    (1, 0, 0, 1),
]

# ==============================================================================
# 3. Audio & Voice Configuration
# ==============================================================================

# Gemini Live Multimodal API Audio Specs
INPUT_SAMPLE_RATE: int = 16000    # 16kHz for mic input
OUTPUT_SAMPLE_RATE: int = 24000   # 24kHz for Gemini Live audio output
CHANNELS: int = 1                 # Mono
AUDIO_CHUNK_SIZE: int = 1024      # Chunk size for streaming

# Audio device indices (on Pi 5 with USB audio: 1 = USB Mic, 0 = USB Speaker)
_mic_env = os.getenv("MIC_DEVICE_INDEX")
MIC_DEVICE_INDEX: Optional[int] = int(_mic_env) if _mic_env is not None and _mic_env.strip() != "" else 1

_spk_env = os.getenv("SPEAKER_DEVICE_INDEX")
SPEAKER_DEVICE_INDEX: Optional[int] = int(_spk_env) if _spk_env is not None and _spk_env.strip() != "" else 0

# ==============================================================================
# 4. Robot Identity & Gemini Live API Configuration
# ==============================================================================

ROBOT_NAME: str = os.getenv("ROBOT_NAME", "Gemini")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
# Default model for Gemini Live Multimodal audio session
GEMINI_LIVE_MODEL: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-latest")
# Consistent, jovial female voice: Aoede
GEMINI_VOICE_NAME: str = os.getenv("GEMINI_VOICE_NAME", "Aoede")  # Aoede, Kore, Puck, Charon, Fenrir
