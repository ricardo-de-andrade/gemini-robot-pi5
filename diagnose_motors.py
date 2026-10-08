#!/usr/bin/env python3
"""
Hardware wiring diagnostic tool for ULN2003 stepper motor boards.
Tests each individual coil pin (IN1..IN4) so you can visually verify the LEDs on the board,
and then performs a slow step sweep.
"""

import sys
import time
from typing import Dict, Tuple

from config import MOTOR_PINS, BCM_TO_PHYSICAL, HALF_STEP_SEQUENCE

try:
    from gpiozero import OutputDevice
    GPIOZERO_AVAILABLE = True
except ImportError:
    print("[ERROR] gpiozero is not installed in this environment.")
    sys.exit(1)


def print_wiring_reference():
    print("\n" + "=" * 70)
    print("🤖 4-MOTOR ULN2003 GPIO & PHYSICAL PIN REFERENCE (Pi 5 Header J8)")
    print("=" * 70)
    for joint, pins in MOTOR_PINS.items():
        phys = [BCM_TO_PHYSICAL.get(p, "?") for p in pins]
        print(f"\n[{joint.upper()}]:")
        for i, (bcm, p) in enumerate(zip(pins, phys)):
            print(f"  IN{i+1} (LED {chr(65+i)}): BCM GPIO {bcm:>2}  -->  Physical Header Pin {p:>2}")
    print("=" * 70 + "\n")


def test_motor_pins(joint_name: str = "right_arm"):
    if joint_name not in MOTOR_PINS:
        print(f"[ERROR] Unknown joint: {joint_name}. Choose from: {list(MOTOR_PINS.keys())}")
        return

    pins = MOTOR_PINS[joint_name]
    phys = [BCM_TO_PHYSICAL.get(p, "?") for p in pins]

    print(f"\n--- Testing Wiring for: {joint_name.upper()} ---")
    print("We will activate each coil pin individually for 1.2 seconds.")
    print("Look at the 4 LEDs (A, B, C, D) on the ULN2003 driver board!\n")

    devices = []
    try:
        for bcm in pins:
            dev = OutputDevice(bcm, active_high=True, initial_value=False)
            devices.append(dev)

        for i, (dev, bcm, p) in enumerate(zip(devices, pins, phys)):
            led = chr(65 + i)
            print(f"  --> Turning ON IN{i+1} (LED {led}) | BCM GPIO {bcm} (Pin {p})...", flush=True)
            dev.on()
            time.sleep(1.2)
            dev.off()
            time.sleep(0.3)
            print(f"      IN{i+1} (LED {led}) OFF.")

        print("\n--- Now running a slow 512-step test sweep (~45 degrees) ---")
        seq_len = len(HALF_STEP_SEQUENCE)
        delay = 0.0030

        print("  --> Stepping FORWARD 512 steps...")
        seq_idx = 0
        for _ in range(512):
            seq_idx = (seq_idx + 1) % seq_len
            state = HALF_STEP_SEQUENCE[seq_idx]
            for d, s in zip(devices, state):
                if s:
                    d.on()
                else:
                    d.off()
            time.sleep(delay)

        # Release coils
        for d in devices:
            d.off()
        time.sleep(0.8)

        print("  --> Stepping REVERSE 512 steps...")
        for _ in range(512):
            seq_idx = (seq_idx - 1) % seq_len
            state = HALF_STEP_SEQUENCE[seq_idx]
            for d, s in zip(devices, state):
                if s:
                    d.on()
                else:
                    d.off()
            time.sleep(delay)

        for d in devices:
            d.off()

        print(f"\n✔ Test complete for {joint_name}!\n")

    except Exception as e:
        print(f"[ERROR] Failed during test: {e}")
    finally:
        for d in devices:
            try:
                d.off()
                d.close()
            except Exception:
                pass


def compare_arms():
    print("\n" + "=" * 70)
    print("🔬 ARM COMPARISON TEST: LEFT ARM (BRIGHT BASELINE) vs RIGHT ARM")
    print("=" * 70)
    print("\n1. Testing LEFT ARM (Baseline):")
    test_motor_pins("left_arm")
    print("\n2. Testing RIGHT ARM:")
    test_motor_pins("right_arm")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "right_arm"
    print_wiring_reference()
    if target == "compare":
        compare_arms()
    else:
        test_motor_pins(target)
