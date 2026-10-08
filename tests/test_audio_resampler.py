from __future__ import annotations
"""Unit tests for audio resampling and rate negotiation."""

import sys
from pathlib import Path

# Add project root to sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import unittest
from robot.audio.audio_io import resample_pcm_chunk


class TestAudioResampler(unittest.TestCase):

    def test_identity_resample(self):
        """Resampling with identical input and output rates should return original data."""
        data = b"\x01\x00\x02\x00\x03\x00" * 100
        resampled, state = resample_pcm_chunk(data, 16000, 16000)
        self.assertEqual(resampled, data)

    def test_downsample_48k_to_16k(self):
        """Downsampling 48000 Hz to 16000 Hz (3:1 ratio)."""
        data = b"\x05\x00" * 480
        resampled, state = resample_pcm_chunk(data, 48000, 16000)
        num_samples_out = len(resampled) // 2
        self.assertEqual(num_samples_out, 160)

    def test_upsample_24k_to_48k(self):
        """Upsampling 24000 Hz to 48000 Hz (1:2 ratio)."""
        data = b"\x07\x00" * 240
        resampled, state = resample_pcm_chunk(data, 24000, 48000)
        num_samples_out = len(resampled) // 2
        self.assertAlmostEqual(num_samples_out, 480, delta=2)

    def test_fractional_44k1_to_16k(self):
        """Downsampling 44100 Hz to 16000 Hz."""
        data = b"\x03\x00" * 441
        resampled, state = resample_pcm_chunk(data, 44100, 16000)
        num_samples_out = len(resampled) // 2
        self.assertAlmostEqual(num_samples_out, 160, delta=2)

    def test_state_continuity(self):
        """Verify state is maintained across streaming chunks without raising exceptions."""
        chunk1 = b"\x10\x00" * 480
        chunk2 = b"\x20\x00" * 480
        out1, state = resample_pcm_chunk(chunk1, 48000, 16000, state=None)
        out2, state = resample_pcm_chunk(chunk2, 48000, 16000, state=state)
        self.assertTrue(len(out1) > 0)
        self.assertTrue(len(out2) > 0)


if __name__ == "__main__":
    unittest.main()
