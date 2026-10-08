from __future__ import annotations
"""Main CLI launcher and diagnostic tools for Raspberry Pi 5 Robot."""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path so script can be executed directly from anywhere
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import JOINT_LIMITS, MOTOR_PINS, ROBOT_NAME
from robot.audio.audio_io import list_audio_devices, AudioIO
from robot.motors.subagent import MotorControllerSubagent
from robot.agent.live_agent import GeminiLiveRobotAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("RobotMain")


def test_motors(mock: bool = False) -> None:
    """Diagnostic tool to step each motor safely and verify wiring."""
    print("\n" + "=" * 60)
    print("🛠️  RUNNING STEPPER MOTOR DIAGNOSTIC TEST")
    print(f"   Mode: {'MOCK' if mock else 'HARDWARE (Pi 5 GPIO)'}")
    print("=" * 60)

    subagent = MotorControllerSubagent(mock=mock)
    try:
        for joint, pins in MOTOR_PINS.items():
            limit = JOINT_LIMITS[joint]
            print(f"\n▶ Testing joint: '{limit.name}' ({joint}) on BCM pins {pins}...")
            print(f"  Description: {limit.description}")

            if "arm" in joint:
                # Test arm movement (0° -> 45° -> 0°)
                print("  Moving arm UP to 45°...")
                subagent._move_joint_absolute(joint, 45.0)
                time.sleep(0.5)
                print("  Moving arm DOWN to 0° (home)...")
                subagent._move_joint_absolute(joint, 0.0)
                time.sleep(0.5)
            else:
                # Test head / body rotation (-30° -> +30° -> 0°)
                print("  Rotating LEFT to -30°...")
                subagent._move_joint_absolute(joint, -30.0)
                time.sleep(0.5)
                print("  Rotating RIGHT to +30°...")
                subagent._move_joint_absolute(joint, 30.0)
                time.sleep(0.5)
                print("  Centering to 0° (home)...")
                subagent._move_joint_absolute(joint, 0.0)
                time.sleep(0.5)

            print(f"  ✅ Joint '{joint}' test completed.")

        print("\n🎉 All 4 motors tested successfully!")
    finally:
        subagent.close()


def test_audio(mic_device: int | None = None, speaker_device: int | None = None) -> None:
    """Test USB microphone capture and USB speaker playback with rate negotiation."""
    print("\n" + "=" * 60)
    print("🎙️  AUDIO HARDWARE DIAGNOSTIC TEST")
    print("=" * 60)

    devices = list_audio_devices()
    print("\nAvailable Audio Devices:")
    for d in devices:
        in_ch = d["max_inputs"]
        out_ch = d["max_outputs"]
        tag = []
        if in_ch > 0:
            tag.append(f"IN: {in_ch}ch")
        if out_ch > 0:
            tag.append(f"OUT: {out_ch}ch")
        print(f"  [{d['index']}] {d['name']} ({', '.join(tag)}, default: {d['default_samplerate']} Hz)")

    audio = AudioIO(mic_device=mic_device, speaker_device=speaker_device)
    try:
        audio.start()
        audio.enable_mic()
        print(f"\n✅ Microphone negotiated: Device [{audio.mic_device}] @ {audio.actual_input_rate} Hz (target: {audio.target_input_rate} Hz)")
        print(f"✅ Speaker negotiated: Device [{audio.speaker_device}] @ {audio.actual_output_rate} Hz ({audio.spk_channels}ch, target: {audio.target_output_rate} Hz)")

        print("\nRecording 3 seconds from microphone (speak now!)...")
        recorded_chunks = []
        start_time = time.time()
        while time.time() - start_time < 3.0:
            try:
                data = audio.input_queue.get(timeout=0.2)
                recorded_chunks.append(data)
            except Exception:
                continue

        raw_bytes = b"".join(recorded_chunks)
        print(f"Captured {len(raw_bytes)} bytes of raw PCM audio at {audio.actual_input_rate} Hz.")

        # Pause mic so it doesn't buffer during playback
        if audio._in_stream:
            try:
                audio._in_stream.stop()
            except Exception:
                pass

        if raw_bytes:
            from robot.audio.audio_io import resample_pcm_chunk
            # Convert captured audio into 24kHz (Gemini format) then play back via resampler
            gemini_format_bytes, _ = resample_pcm_chunk(raw_bytes, audio.actual_input_rate, audio.target_output_rate)
            print(f"Resampled to {len(gemini_format_bytes)} bytes for Gemini format ({audio.target_output_rate} Hz).")
            print("Playing back audio through speaker (via resampler)...")
            audio.play_audio(gemini_format_bytes)
            # Wait for playback to complete
            time.sleep(3.5)
            print("🎉 Audio diagnostic test completed successfully!")
        else:
            print("\n⚠️  No audio data captured (0 bytes).")
            print("Troubleshooting steps:")
            print(f"  1. Selected device was index [{audio.mic_device}].")
            inputs = [d for d in devices if d['max_inputs'] > 0]
            if inputs:
                print("     Try targeting other available microphone device indices:")
                for inp in inputs:
                    print(f"       python3 -m robot.main --test-audio --mic-device {inp['index']}")
            print("  2. Run 'alsamixer' in your terminal, press F6 to select your USB card, and ensure Capture/Mic is unmuted.")

    finally:
        audio.stop()


def test_gesture(gesture_name: str, mock: bool = False) -> None:
    """Test a specific high-level gesture."""
    print(f"\nExecuting gesture: '{gesture_name}'...")
    subagent = MotorControllerSubagent(mock=mock)
    try:
        if gesture_name == "wave":
            subagent.wave(arm="right")
        elif gesture_name == "nod":
            subagent.nod()
        elif gesture_name == "celebrate":
            subagent.celebrate()
        elif gesture_name == "look_around":
            subagent.look_around()
        elif gesture_name == "home":
            subagent.reset_to_home()
        else:
            print(f"Unknown gesture '{gesture_name}'. Available: wave, nod, celebrate, look_around, home")
    finally:
        subagent.close()


def run_agent(mock_motors: bool = False, mic_device: int | None = None, speaker_device: int | None = None) -> None:
    """Run the live conversational agent."""
    agent = GeminiLiveRobotAgent(mock_motors=mock_motors)
    if mic_device is not None:
        agent.audio_io.mic_device = mic_device
    if speaker_device is not None:
        agent.audio_io.speaker_device = speaker_device
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\nExiting agent...")


def main():
    parser = argparse.ArgumentParser(description=f"{ROBOT_NAME} - Raspberry Pi 5 Gemini Live Robotics Agent")
    parser.add_argument("--run", action="store_true", help="Start the Gemini Live voice agent")
    parser.add_argument("--test-motors", action="store_true", help="Run 4-motor diagnostic test")
    parser.add_argument("--test-audio", action="store_true", help="Test USB microphone and speaker")
    parser.add_argument("--gesture", type=str, choices=["wave", "nod", "celebrate", "look_around", "home"],
                        help="Run a specific expressive gesture")
    parser.add_argument("--mock-motors", action="store_true", help="Run motors in simulated/mock mode")
    parser.add_argument("--mic-device", type=int, default=None, help="Explicit audio input device index")
    parser.add_argument("--speaker-device", type=int, default=None, help="Explicit audio output device index")

    args = parser.parse_args()

    if args.test_motors:
        test_motors(mock=args.mock_motors)
    elif args.test_audio:
        test_audio(mic_device=args.mic_device, speaker_device=args.speaker_device)
    elif args.gesture:
        test_gesture(args.gesture, mock=args.mock_motors)
    elif args.run:
        run_agent(mock_motors=args.mock_motors, mic_device=args.mic_device, speaker_device=args.speaker_device)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
