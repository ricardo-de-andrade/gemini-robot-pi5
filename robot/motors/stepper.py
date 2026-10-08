from __future__ import annotations
"""Low-level stepper motor driver for 28BYJ-48 with ULN2003 on Raspberry Pi 5."""

import logging
import time
from typing import Tuple, List

from config import HALF_STEP_SEQUENCE, STEP_DELAY_SEC, BCM_TO_PHYSICAL

logger = logging.getLogger(__name__)

# Check if gpiozero is available and functional
try:
    from gpiozero import OutputDevice
    GPIOZERO_AVAILABLE = True
except (ImportError, Exception):
    OutputDevice = None
    GPIOZERO_AVAILABLE = False


class StepperMotor:
    """Controls a single 28BYJ-48 4-phase stepper motor via a ULN2003 driver board."""

    def __init__(
        self,
        name: str,
        pins: Tuple[int, int, int, int],
        step_delay: float = STEP_DELAY_SEC,
        mock: bool = False,
        inverted: bool = False,
    ):
        """
        Initialize stepper motor.

        :param name: Identifier name for motor (e.g., 'left_arm', 'head')
        :param pins: BCM pin numbers (IN1, IN2, IN3, IN4)
        :param step_delay: Delay between half-steps in seconds
        :param mock: Force mock mode (no GPIO hardware calls)
        :param inverted: If True, inverts physical rotation direction
        """
        self.name = name
        self.pins = pins
        self.step_delay = step_delay
        self.seq_index = 0
        self.is_mock = mock or (not GPIOZERO_AVAILABLE)
        self.inverted = inverted

        self._devices: List = []

        if not self.is_mock:
            try:
                for pin in self.pins:
                    dev = OutputDevice(pin, active_high=True, initial_value=False)
                    self._devices.append(dev)
                logger.info(
                    f"Initialized hardware stepper '{self.name}' (inverted={self.inverted}) -> "
                    f"Wiring: {self.pins_description}"
                )
            except Exception as e:
                logger.warning(
                    f"Could not initialize GPIO pins {self.pins} for '{self.name}' ({e}). "
                    "Falling back to Mock mode."
                )
                self.is_mock = True
                self._devices = []
        else:
            logger.info(
                f"Initialized mock stepper '{self.name}' (inverted={self.inverted}) -> "
                f"Wiring: {self.pins_description}"
            )

    @property
    def pins_description(self) -> str:
        """Returns human-readable wiring mapping for IN1..IN4 with physical header pin numbers."""
        parts = [
            f"IN{i+1}=GPIO{p}(Pin {BCM_TO_PHYSICAL.get(p, '?')})"
            for i, p in enumerate(self.pins)
        ]
        return ", ".join(parts)

    def _set_pins(self, states: Tuple[int, int, int, int]) -> None:
        """Write 4 binary states to the IN1-IN4 pins."""
        if self.is_mock:
            return
        for dev, state in zip(self._devices, states):
            if state:
                dev.on()
            else:
                dev.off()

    def step(self, steps: int, delay_sec: float | None = None) -> None:
        """
        Perform a given number of half-steps.
        Positive steps = forward / clockwise (or counter-clockwise if inverted).
        Negative steps = reverse / counter-clockwise (or clockwise if inverted).
        """
        if steps == 0:
            return

        delay = delay_sec if delay_sec is not None else self.step_delay
        direction = 1 if steps > 0 else -1
        if self.inverted:
            direction = -direction

        total_steps = abs(steps)
        seq_length = len(HALF_STEP_SEQUENCE)

        phys_pins = [BCM_TO_PHYSICAL.get(p, "?") for p in self.pins]
        logger.info(
            f"⚡ Activating '{self.name}' ({steps:+d} steps) -> "
            f"Pulsing BCM GPIOs {self.pins} [Physical Header Pins {phys_pins}]"
        )

        for _ in range(total_steps):
            self.seq_index = (self.seq_index + direction) % seq_length
            self._set_pins(HALF_STEP_SEQUENCE[self.seq_index])
            time.sleep(delay)

        # De-energize coils to prevent heating and conserve power
        self.release()
        logger.debug(f"✔ Completed '{self.name}' {steps:+d} steps. Released coils on BCM {self.pins}.")

    def release(self) -> None:
        """De-energize all coils (safe idle)."""
        self._set_pins((0, 0, 0, 0))

    def close(self) -> None:
        """Release pins and clean up resources."""
        self.release()
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices.clear()
