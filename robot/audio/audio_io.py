from __future__ import annotations
"""Robust audio streaming I/O for USB Microphone input and USB Speaker output on Raspberry Pi 5.

Features:
- Automatic hardware rate negotiation (probes hardware for 16kHz/24kHz, 48kHz, 44.1kHz, etc.)
- Transparent real-time resampling between hardware rates and Gemini Live API (16kHz in / 24kHz out)
- Automatic USB audio device discovery (filters out non-functional or HDMI-only devices)
- State-preserving resampling with audioop (including audioop-lts on Python 3.13) / numpy fallback
- Glitch-free byte-level ring buffering to prevent audio gaps, clicks, and lost samples
"""

import asyncio
import logging
import queue
import threading
import time
from typing import AsyncGenerator, Optional, List, Dict, Tuple

from config import (
    INPUT_SAMPLE_RATE,   # Target: 16000 Hz for Gemini Live
    OUTPUT_SAMPLE_RATE,  # Target: 24000 Hz for Gemini Live
    CHANNELS,
    AUDIO_CHUNK_SIZE,
    MIC_DEVICE_INDEX,
    SPEAKER_DEVICE_INDEX,
)

logger = logging.getLogger(__name__)

# Check for audioop (standard library in Python 3.9 - 3.11, audioop-lts in 3.13+)
try:
    import audioop
    AUDIOOP_AVAILABLE = True
except ImportError:
    audioop = None
    AUDIOOP_AVAILABLE = False

# Check for numpy
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

# Check for sounddevice
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    sd = None
    SOUNDDEVICE_AVAILABLE = False


def resample_pcm_chunk(
    pcm_bytes: bytes,
    in_rate: int,
    out_rate: int,
    state: Optional[Tuple] = None,
) -> Tuple[bytes, Optional[Tuple]]:
    """
    Resample 16-bit mono PCM bytes from in_rate to out_rate.
    Maintains filter state between consecutive chunks to avoid clicks/glitches.

    :return: (resampled_pcm_bytes, new_state)
    """
    if in_rate == out_rate or not pcm_bytes:
        return pcm_bytes, state

    # 1. Preferred: audioop.ratecv (fast C-implementation, stateful)
    if AUDIOOP_AVAILABLE:
        try:
            converted, new_state = audioop.ratecv(pcm_bytes, 2, 1, in_rate, out_rate, state)
            return converted, new_state
        except Exception as e:
            logger.debug(f"audioop.ratecv failed: {e}, attempting numpy fallback")

    # 2. Fallback: NumPy linear interpolation
    if NUMPY_AVAILABLE:
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            if len(samples) == 0:
                return b"", None
            num_out = int(round(len(samples) * out_rate / in_rate))
            if num_out == 0:
                return b"", None
            x_orig = np.linspace(0, 1, len(samples), endpoint=False)
            x_new = np.linspace(0, 1, num_out, endpoint=False)
            resampled = np.interp(x_new, x_orig, samples).astype(np.int16)
            return resampled.tobytes(), None
        except Exception as e:
            logger.debug(f"numpy resample failed: {e}")

    # 3. Simple integer ratio fallback
    if in_rate > out_rate and in_rate % out_rate == 0:
        ratio = in_rate // out_rate
        return pcm_bytes[:: ratio * 2], None

    return pcm_bytes, None


def list_audio_devices() -> List[Dict[str, str | int]]:
    """List available audio input and output devices with supported characteristics."""
    if not SOUNDDEVICE_AVAILABLE:
        print("sounddevice library is not available.")
        return []

    try:
        devices = sd.query_devices()
        dev_list = []
        for i, dev in enumerate(devices):
            dev_list.append({
                "index": i,
                "name": dev["name"],
                "max_inputs": dev["max_input_channels"],
                "max_outputs": dev["max_output_channels"],
                "default_samplerate": int(dev["default_samplerate"]),
            })
        return dev_list
    except Exception as e:
        logger.error(f"Failed to query audio devices: {e}")
        return []


def auto_detect_devices() -> Tuple[Optional[int], Optional[int]]:
    """
    Auto-detect physical USB microphone and USB speaker devices on Raspberry Pi.
    Filters out virtual ALSA devices that report false channel capabilities.
    """
    if not SOUNDDEVICE_AVAILABLE:
        return None, None

    mic_index = None
    speaker_index = None

    try:
        devices = sd.query_devices()
        virtual_names = {"sysdefault", "samplerate", "speex", "upmix", "vdownmix", "dmix"}

        # Pass 1: Match by exact hardware chipset signatures
        # USB Mic is "USB PnP Sound Device"
        # USB Speaker is "UACDemoV1.0"
        for i, dev in enumerate(devices):
            name = dev["name"].lower().strip()
            if any(name == v or name.startswith(v) for v in virtual_names):
                continue
            if mic_index is None and ("pnp" in name or "mic" in name) and dev["max_input_channels"] > 0:
                mic_index = i
            if speaker_index is None and ("uacdemo" in name or "speaker" in name) and dev["max_output_channels"] > 0:
                speaker_index = i

        # Pass 2: Match any USB audio device with appropriate channels
        for i, dev in enumerate(devices):
            name = dev["name"].lower().strip()
            if any(name == v or name.startswith(v) for v in virtual_names):
                continue
            if "usb" in name:
                if mic_index is None and dev["max_input_channels"] > 0 and i != speaker_index:
                    mic_index = i
                if speaker_index is None and dev["max_output_channels"] > 0 and i != mic_index:
                    if "hdmi" not in name:
                        speaker_index = i

        # Pass 3: Fallback to any hardware device
        for i, dev in enumerate(devices):
            name = dev["name"].lower().strip()
            if any(name == v or name.startswith(v) for v in virtual_names):
                continue
            if mic_index is None and dev["max_input_channels"] > 0 and i != speaker_index:
                mic_index = i
            if speaker_index is None and dev["max_output_channels"] > 0 and i != mic_index:
                if "hdmi" not in name:
                    speaker_index = i

        # Ultimate fallback
        if mic_index is None:
            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    mic_index = i
                    break
        if speaker_index is None:
            for i, dev in enumerate(devices):
                if dev["max_output_channels"] > 0 and ("hdmi" not in dev["name"].lower() or speaker_index is None):
                    speaker_index = i
                    if "hdmi" not in dev["name"].lower():
                        break

    except Exception as e:
        logger.error(f"Device auto-detection failed: {e}")

    return mic_index, speaker_index


def probe_supported_sample_rate(
    device: Optional[int],
    kind: str,
    desired_rate: int,
) -> int:
    """
    Find a sample rate supported by the hardware device.
    Tests desired_rate first, then standard hardware rates (48000, 44100, 32000, 16000).
    """
    if not SOUNDDEVICE_AVAILABLE:
        return desired_rate

    candidate_rates = [desired_rate, 48000, 32000, 44100, 24000, 8000]

    for rate in candidate_rates:
        try:
            if kind == "input":
                sd.check_input_settings(
                    device=device,
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                )
            else:
                sd.check_output_settings(
                    device=device,
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                )
            logger.info(f"Hardware {kind} device ({device}) negotiated sample rate: {rate} Hz")
            return rate
        except Exception:
            continue

    logger.warning(
        f"Could not confirm sample rate for {kind} device ({device}). "
        f"Defaulting to {desired_rate} Hz."
    )
    return desired_rate


class AudioIO:
    """
    Manages robust audio capture from microphone and playback through speaker,
    with automatic sample rate negotiation, software resampling, and glitch-free
    streaming ring buffering.
    """

    def __init__(
        self,
        input_rate: int = INPUT_SAMPLE_RATE,    # Target rate for Gemini (16000 Hz)
        output_rate: int = OUTPUT_SAMPLE_RATE,  # Target rate from Gemini (24000 Hz)
        channels: int = CHANNELS,
        chunk_size: int = AUDIO_CHUNK_SIZE,
        mic_device: Optional[int] = MIC_DEVICE_INDEX,
        speaker_device: Optional[int] = SPEAKER_DEVICE_INDEX,
    ):
        self.target_input_rate = input_rate
        self.target_output_rate = output_rate
        self.channels = channels
        self.chunk_size = chunk_size

        # Resolve devices (explicit or auto-detected)
        auto_mic, auto_spk = auto_detect_devices()
        self.mic_device = mic_device if mic_device is not None else auto_mic
        self.speaker_device = speaker_device if speaker_device is not None else auto_spk

        # Hardware-negotiated rates and channels (populated on start)
        self.actual_input_rate = self.target_input_rate
        self.actual_output_rate = self.target_output_rate
        self.spk_channels = 1

        # Queues & Buffers (bounded to 32 chunks = ~2s to absorb network jitter without dropping audio)
        self.input_queue: queue.Queue = queue.Queue(maxsize=32)
        self._spk_buffer = bytearray()
        self._buffer_lock = threading.Lock()
        self._last_playback_time = 0.0
        self._playback_active = False
        self._prebuffer_threshold = 0
        self._mic_enabled = False

        # Resampling state trackers
        self._mic_resample_state: Optional[Tuple] = None
        self._spk_resample_state: Optional[Tuple] = None

        self._in_stream = None
        self._out_stream = None
        self._running = False
        self.is_suppressed_fn: Optional[Callable[[], bool]] = None

    def enable_mic(self) -> None:
        """Enable microphone capture and clear any residual buffered audio."""
        self.clear_mic_buffer()
        self._mic_enabled = True
        logger.info("Microphone input enabled.")

    def disable_mic(self) -> None:
        """Disable microphone capture and clear queue."""
        self._mic_enabled = False
        self.clear_mic_buffer()
        logger.info("Microphone input disabled.")

    def clear_mic_buffer(self) -> None:
        """Purge all buffered microphone chunks to guarantee zero latency."""
        while not self.input_queue.empty():
            try:
                self.input_queue.get_nowait()
            except queue.Empty:
                break

    def _mic_callback(self, indata, frames, time_info, status):
        """Callback from sounddevice for captured microphone audio."""
        if not self._mic_enabled:
            return  # Drop audio only when mic is completely disabled (e.g. bootup)

        if status:
            if getattr(status, "input_overflow", False):
                logger.debug(f"Mic status (overflow): {status}")
            else:
                logger.warning(f"Mic status: {status}")
        try:
            if hasattr(indata, "ndim") and indata.ndim > 1 and indata.shape[1] > 1:
                # Downmix multi-channel mic to mono
                mono = indata[:, 0].copy()
                raw = mono.tobytes()
            elif hasattr(indata, "tobytes"):
                raw = indata.tobytes()
            else:
                raw = bytes(indata)

            try:
                self.input_queue.put_nowait(raw)
            except queue.Full:
                # Discard oldest chunk so stream is always 100% fresh and real-time
                try:
                    self.input_queue.get_nowait()
                except queue.Empty:
                    pass
                self.input_queue.put_nowait(raw)
        except Exception as e:
            logger.error(f"Error in mic callback: {e}")

    def _speaker_callback(self, outdata, frames, time_info, status):
        """Callback from sounddevice to feed playback buffer smoothly using jitter buffer."""
        if status:
            logger.debug(f"Speaker status: {status}")
        try:
            bytes_needed = frames * 2
            chunk = b""
            with self._buffer_lock:
                if self._playback_active:
                    avail_bytes = min(len(self._spk_buffer), bytes_needed)
                    chunk = bytes(self._spk_buffer[:avail_bytes])
                    del self._spk_buffer[:avail_bytes]
                    if avail_bytes > 0:
                        self._last_playback_time = time.time()
                    if len(self._spk_buffer) == 0:
                        self._playback_active = False

            if chunk and NUMPY_AVAILABLE:
                samples = np.frombuffer(chunk, dtype=np.int16)
                n = len(samples)
                if outdata.ndim == 1:
                    outdata[:n] = samples
                    if n < frames:
                        outdata[n:] = 0
                elif outdata.shape[1] == 1:
                    outdata[:n, 0] = samples
                    if n < frames:
                        outdata[n:, 0] = 0
                else:
                    for ch in range(outdata.shape[1]):
                        outdata[:n, ch] = samples
                    if n < frames:
                        outdata[n:, :] = 0
            else:
                if hasattr(outdata, "fill"):
                    outdata.fill(0)
                else:
                    outdata[:] = b"\x00" * len(outdata)
        except Exception as e:
            logger.error(f"Error in speaker callback: {e}")
            if hasattr(outdata, "fill"):
                outdata.fill(0)

    def start(self) -> None:
        """Probe hardware rates, initialize streams, and start I/O."""
        if not SOUNDDEVICE_AVAILABLE:
            logger.warning("sounddevice is not available. Running in silent audio mock mode.")
            self._running = True
            return

        # 1. Probe hardware-compatible sample rates
        self.actual_input_rate = probe_supported_sample_rate(
            self.mic_device, "input", self.target_input_rate
        )
        self.actual_output_rate = probe_supported_sample_rate(
            self.speaker_device, "output", self.target_output_rate
        )

        # 2. Determine speaker channel capability (e.g. stereo for USB speaker)
        self.spk_channels = 1
        if self.speaker_device is not None:
            try:
                info = sd.query_devices(self.speaker_device)
                max_out = info.get("max_output_channels", 1)
                self.spk_channels = min(2, max(1, max_out))
            except Exception:
                self.spk_channels = 1

        logger.info(
            f"Audio Config -> Mic Device [{self.mic_device}]: {self.actual_input_rate} Hz mono "
            f"(resampling to {self.target_input_rate} Hz for Gemini)"
        )
        logger.info(
            f"Audio Config -> Speaker Device [{self.speaker_device}]: {self.actual_output_rate} Hz ({self.spk_channels}ch) "
            f"(resampling from {self.target_output_rate} Hz from Gemini)"
        )

        in_blocksize = int(round(self.chunk_size * self.actual_input_rate / self.target_input_rate))
        out_blocksize = int(round(self.chunk_size * self.actual_output_rate / self.target_output_rate))

        StreamInClass = sd.InputStream if NUMPY_AVAILABLE else sd.RawInputStream
        StreamOutClass = sd.OutputStream if NUMPY_AVAILABLE else sd.RawOutputStream

        try:
            self._in_stream = StreamInClass(
                samplerate=self.actual_input_rate,
                channels=1,
                dtype="int16",
                blocksize=in_blocksize,
                device=self.mic_device,
                callback=self._mic_callback,
            )
            self._out_stream = StreamOutClass(
                samplerate=self.actual_output_rate,
                channels=self.spk_channels,
                dtype="int16",
                blocksize=out_blocksize,
                device=self.speaker_device,
                callback=self._speaker_callback,
            )
            self._in_stream.start()
            self._out_stream.start()
            self._prebuffer_threshold = int(0.20 * self.actual_output_rate * 2)
            self._playback_active = False
            self._running = True
            logger.info("Audio I/O streams started successfully.")
        except Exception as e:
            logger.error(f"Error starting audio hardware streams: {e}")
            self._running = False
            raise

    @property
    def is_playing(self) -> bool:
        """Returns True if audio is queued or actively outputting through the speaker."""
        with self._buffer_lock:
            if len(self._spk_buffer) > 0:
                return True
        return (time.time() - getattr(self, "_last_playback_time", 0.0)) < 0.18

    async def wait_playback_done(self, timeout: float = 6.0) -> None:
        """Wait asynchronously until speaker playback buffer has fully drained."""
        start = time.time()
        while self.is_playing and (time.time() - start) < timeout:
            await asyncio.sleep(0.05)

    async def stream_mic_audio(self) -> AsyncGenerator[bytes, None]:
        """
        Asynchronously yield microphone audio PCM chunks resampled
        to 16000 Hz for the Gemini Live API.
        Streams real audio directly to Gemini Live for native server-side VAD,
        with half-duplex echo suppression while the robot speaker is playing.
        """
        last_voice_log = 0.0

        while self._running:
            # Drain queue only if severe lag develops (> 1.5 seconds backlog)
            while self.input_queue.qsize() > 24:
                try:
                    self.input_queue.get_nowait()
                except queue.Empty:
                    break

            try:
                raw_chunk = self.input_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.015)
                continue

            if not raw_chunk or not self._mic_enabled:
                continue

            resampled_chunk, self._mic_resample_state = resample_pcm_chunk(
                raw_chunk,
                in_rate=self.actual_input_rate,
                out_rate=self.target_input_rate,
                state=self._mic_resample_state,
            )

            if not resampled_chunk:
                continue

            # Echo suppression: when speaker is outputting, send silence to prevent self-triggering
            if self.is_playing:
                yield b"\x00" * len(resampled_chunk)
                continue

            # Compute RMS level for monitoring / logging
            if NUMPY_AVAILABLE:
                samples = np.frombuffer(resampled_chunk, dtype=np.int16)
                rms = float(np.sqrt(np.mean(samples.astype(np.float64)**2)))
            elif AUDIOOP_AVAILABLE:
                rms = float(audioop.rms(resampled_chunk, 2))
            else:
                rms = 0.0

            if rms >= 550.0 and (time.time() - last_voice_log > 2.5):
                logger.info(f"🎤 Hearing audio (RMS: {rms:.0f})...")
                last_voice_log = time.time()

            yield resampled_chunk

    def play_audio(self, pcm_bytes: bytes) -> None:
        """
        Queue raw PCM 16-bit audio data from Gemini Live (24000 Hz) for playback,
        resampling to the speaker's native hardware rate with jitter pre-buffering.
        """
        if not self._running or not pcm_bytes:
            return

        # Resample 24000 Hz from Gemini -> hardware speaker rate
        resampled_bytes, self._spk_resample_state = resample_pcm_chunk(
            pcm_bytes,
            in_rate=self.target_output_rate,
            out_rate=self.actual_output_rate,
            state=self._spk_resample_state,
        )

        with self._buffer_lock:
            self._spk_buffer.extend(resampled_bytes)
            # Bound buffer to prevent lag accumulation (> 5 seconds)
            max_bytes = int(5 * self.actual_output_rate * 2)
            if len(self._spk_buffer) > max_bytes:
                del self._spk_buffer[:len(self._spk_buffer) - max_bytes]

            # Activate playback once pre-buffer threshold is reached
            if len(self._spk_buffer) >= self._prebuffer_threshold:
                self._playback_active = True

    def flush_playback(self) -> None:
        """Trigger immediate playback of whatever audio is in the buffer (e.g. at end of turn)."""
        with self._buffer_lock:
            if len(self._spk_buffer) > 0:
                self._playback_active = True

    def clear_speaker_buffer(self) -> None:
        """Immediately clear pending audio in speaker buffer (e.g. on interruption)."""
        with self._buffer_lock:
            self._spk_buffer.clear()
            self._playback_active = False

    def stop(self) -> None:
        """Stop and close audio streams."""
        self._running = False
        if self._in_stream:
            try:
                self._in_stream.stop()
                self._in_stream.close()
            except Exception:
                pass
            self._in_stream = None

        if self._out_stream:
            try:
                self._out_stream.stop()
                self._out_stream.close()
            except Exception:
                pass
            self._out_stream = None

        with self._buffer_lock:
            self._spk_buffer.clear()
            self._playback_active = False

        logger.info("Audio I/O stopped.")
