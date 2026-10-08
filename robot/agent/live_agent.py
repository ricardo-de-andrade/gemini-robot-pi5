from __future__ import annotations
"""Gemini Multimodal Live API Agent with real-time audio and autonomous motor gesturing."""

import asyncio
import logging
import os
import re
import sys
from typing import List, Optional, Set

from config import (
    ROBOT_NAME,
    GEMINI_API_KEY,
    GEMINI_LIVE_MODEL,
    GEMINI_VOICE_NAME,
)
from robot.audio.audio_io import AudioIO
from robot.motors.subagent import MotorControllerSubagent
from robot.agent.tools import get_tool_declarations, MotorToolDispatcher

logger = logging.getLogger(__name__)

# Check for google-genai SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GENAI_AVAILABLE = False


ROBOT_SYSTEM_PROMPT = f"""You are {ROBOT_NAME}, an enthusiastic, cheerful, and jovial physical desktop robot companion with REAL mechanical arms, head, and body powered by stepper motors on a Raspberry Pi 5.
You speak with a warm, lively, and upbeat female tone (Aoede).

YOUR PHYSICAL HARDWARE:
- Dual mechanical arms: Left and Right arms. You wave and move them proudly!
- Motorized head: Rotates side-to-side (-90° full left, 0° center, +90° full right).
- Motorized body: Rotates waist side-to-side (-90° to +90°).

CRITICAL PHYSICAL ACTION RULES:
1. YOU HAVE REAL PHYSICAL ARMS! NEVER say you do not have physical arms.
2. Whenever the user greets you, says hello, asks if you can hear them, asks you to wave, or mentions your arms, YOU MUST INCLUDE [WAVE] in your speech to physically wave both arms!
3. To express physical movements during your speech, always include action tags:
   - [WAVE]: Wave both arms energetically (use on greetings and when asked to wave).
   - [WAVE_LEFT]: Wave your left arm.
   - [WAVE_RIGHT]: Wave your right arm.
   - [ARMS_UP]: Raise both arms high in excitement.
   - [ARMS_DOWN]: Lower arms down to your side.
   - [NOD]: Shake/nod your head in agreement or acknowledgment.
   - [CELEBRATE]: Raise both arms and wiggle body in celebration.
   - [LOOK_AROUND]: Turn head left and right to survey the room.
   - [HEAD_LEFT], [HEAD_RIGHT], [HEAD_CENTER]: Turn head.
   - [BODY_LEFT], [BODY_RIGHT], [BODY_CENTER]: Turn body.
4. Speak concisely, warmly, and naturally in 1-2 lively sentences. Always include motion tags like [WAVE] so your body moves while you talk!
"""

GESTURE_TAGS = {
    "[WAVE]": lambda sub: sub.wave("both"),
    "[WAVE_LEFT]": lambda sub: sub.wave("left"),
    "[WAVE_RIGHT]": lambda sub: sub.wave("right"),
    "[NOD]": lambda sub: sub.nod(),
    "[CELEBRATE]": lambda sub: sub.celebrate(),
    "[LOOK_AROUND]": lambda sub: sub.look_around(),
    "[HEAD_LEFT]": lambda sub: sub.rotate_head("left"),
    "[HEAD_RIGHT]": lambda sub: sub.rotate_head("right"),
    "[HEAD_CENTER]": lambda sub: sub.rotate_head("center"),
    "[BODY_LEFT]": lambda sub: sub.rotate_body("left"),
    "[BODY_RIGHT]": lambda sub: sub.rotate_body("right"),
    "[BODY_CENTER]": lambda sub: sub.rotate_body("center"),
    "[ARMS_UP]": lambda sub: sub.move_arm("both", position="up"),
    "[ARMS_DOWN]": lambda sub: sub.move_arm("both", position="down"),
    "[ARMS_HALFWAY]": lambda sub: sub.move_arm("both", position="halfway"),
    "[RESET_HOME]": lambda sub: sub.reset_to_home(),
}


class GeminiLiveRobotAgent:
    """Manages real-time bidirectional audio streaming with Gemini Live API and motor executive."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = GEMINI_LIVE_MODEL,
        voice_name: str = GEMINI_VOICE_NAME,
        mock_motors: bool = False,
    ):
        self.api_key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.voice_name = voice_name
        self.mock_motors = mock_motors

        if not self.api_key:
            logger.warning("No GEMINI_API_KEY provided. Please set the GEMINI_API_KEY environment variable.")

        # Initialize Motor Subagent and Dispatcher
        self.motor_subagent = MotorControllerSubagent(mock=mock_motors)
        self.tool_dispatcher = MotorToolDispatcher(self.motor_subagent)

        # Initialize Audio I/O
        self.audio_io = AudioIO()
        self._executed_tags_in_turn = set()

        self._greeting_completed = asyncio.Event()
        self._running = True
        self._is_speaking_logged = False
        self._user_speaking_logged = False
        self._agent_speaking_logged = False
        self._current_user_text: List[str] = []
        self._current_agent_text: List[str] = []
        self._current_turn_raw_text: str = ""

    def _trigger_gestures_from_text(self, text: str) -> None:
        """Parse action tags from Gemini's response text and execute physical movements."""
        for tag, action in GESTURE_TAGS.items():
            if tag in text and tag not in self._executed_tags_in_turn:
                self._executed_tags_in_turn.add(tag)
                asyncio.get_event_loop().run_in_executor(None, action, self.motor_subagent)

    async def _mic_send_loop(self, session) -> None:
        """Stream microphone PCM audio chunks to the Gemini Live session."""
        try:
            async for chunk in self.audio_io.stream_mic_audio():
                if not chunk:
                    continue
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            logger.info("Mic send loop cancelled.")
            raise
        except Exception as e:
            if "closed" in str(e).lower() or "keepalive" in str(e).lower():
                logger.info(f"Mic send loop closed: {e}")
            else:
                logger.error(f"Error in mic streaming loop: {e}")
            raise

    async def _receive_loop(self, session) -> None:
        """Receive audio output and action tags across infinite multi-turn conversations."""
        logger.info("Gemini Live receive loop started.")
        try:
            while self._running:
                async for response in session.receive():
                    # Handle incoming audio playback & model text
                    server_content = getattr(response, "server_content", None)
                    if server_content is not None:
                        interrupted = getattr(server_content, "interrupted", False)
                        if interrupted:
                            logger.info("⚡ [Gemini Live] Interrupted by user voice.")
                            self.audio_io.clear_speaker_buffer()

                        # 1. Real-time transcript of what the user is saying
                        input_tx = getattr(server_content, "input_transcription", None)
                        if input_tx and getattr(input_tx, "text", None):
                            chunk = input_tx.text
                            self._current_user_text.append(chunk)
                            if not self._user_speaking_logged:
                                print(f"\n👤 [User]: {chunk}", end="", flush=True)
                                self._user_speaking_logged = True
                            else:
                                print(chunk, end="", flush=True)

                        # 2. Real-time transcript of what Gemini is saying & gesture triggering
                        output_tx = getattr(server_content, "output_transcription", None)
                        if output_tx and getattr(output_tx, "text", None):
                            chunk = output_tx.text
                            self._current_turn_raw_text += chunk
                            self._trigger_gestures_from_text(self._current_turn_raw_text)
                            clean_chunk = re.sub(r"\[[A-Z_]+\]", "", chunk)
                            if clean_chunk:
                                self._current_agent_text.append(clean_chunk)
                                if not self._agent_speaking_logged:
                                    print(f"\n🤖 [{ROBOT_NAME}]: {clean_chunk}", end="", flush=True)
                                    self._agent_speaking_logged = True
                                else:
                                    print(clean_chunk, end="", flush=True)

                        model_turn = getattr(server_content, "model_turn", None)
                        if model_turn is not None:
                            for part in getattr(model_turn, "parts", []):
                                text = getattr(part, "text", None)
                                is_thought = getattr(part, "thought", False)
                                if text and text.strip():
                                    self._current_turn_raw_text += text
                                    self._trigger_gestures_from_text(self._current_turn_raw_text)
                                    clean_text = re.sub(r"\[[A-Z_]+\]", "", text).strip()
                                    if is_thought:
                                        logger.debug(f"Gemini thought: {clean_text}")
                                    elif not output_tx and not self._agent_speaking_logged and clean_text:
                                        print(f"\n🤖 [{ROBOT_NAME}]: {clean_text}", flush=True)
                                        self._current_agent_text.append(clean_text)
                                inline_data = getattr(part, "inline_data", None)
                                if inline_data is not None and getattr(inline_data, "data", None):
                                    self.audio_io.play_audio(inline_data.data)

                        if getattr(server_content, "turn_complete", False):
                            self._executed_tags_in_turn.clear()
                            self._current_turn_raw_text = ""
                            if self._user_speaking_logged or self._agent_speaking_logged:
                                print()
                            if self._current_user_text:
                                user_str = "".join(self._current_user_text).strip()
                                if user_str:
                                    logger.info(f"👤 [User]: {user_str}")
                                self._current_user_text.clear()
                            if self._current_agent_text:
                                agent_str = "".join(self._current_agent_text).strip()
                                if agent_str:
                                    logger.info(f"🤖 [{ROBOT_NAME}]: {agent_str}")
                                self._current_agent_text.clear()
                            self._user_speaking_logged = False
                            self._agent_speaking_logged = False
                            self._is_speaking_logged = False
                            self.audio_io.flush_playback()
                            if not self._greeting_completed.is_set():
                                self._greeting_completed.set()
        except asyncio.CancelledError:
            logger.info("Receive loop cancelled.")
            raise
        except Exception as e:
            if "closed" in str(e).lower() or "keepalive" in str(e).lower() or "1000" in str(e):
                logger.info(f"Receive loop session closed: {e}")
            else:
                logger.error(f"Error in receive loop: {e}")
            raise

    async def run(self) -> None:
        """Start the live voice conversation and robotics agent."""
        if not GENAI_AVAILABLE:
            print("\n[ERROR] 'google-genai' SDK is not installed.")
            print("Please run: pip install google-genai>=0.8.0\n")
            sys.exit(1)

        if not self.api_key:
            print("\n[ERROR] GEMINI_API_KEY environment variable is not set.")
            print("Please set your key: export GEMINI_API_KEY='AIzaSy...'\n")
            sys.exit(1)

        # Setup GenAI client
        client = genai.Client(
            api_key=self.api_key,
            http_options={"api_version": "v1alpha"}
        )

        # Disable websockets library keepalive ping timeout since live audio
        # is constantly streaming on the connection and proxies can drop ping/pong frames
        if hasattr(client, "_api_client") and hasattr(client._api_client, "_websocket_ssl_ctx"):
            client._api_client._websocket_ssl_ctx["ping_interval"] = None
            client._api_client._websocket_ssl_ctx["ping_timeout"] = None

        # Configure Live Session (pure realtime audio without tool conflicts)
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=ROBOT_SYSTEM_PROMPT)]
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=700,
                )
            ),
        )

        print("\n" + "=" * 60)
        print(f"🤖 Starting {ROBOT_NAME}: Gemini Live Voice & Robotics Agent")
        print(f"   Model: {self.model}")
        print(f"   Voice: {self.voice_name} (jovial female)")
        print(f"   Motors Mock Mode: {self.mock_motors}")
        print("   Press Ctrl+C to stop.")
        print("=" * 60 + "\n")

        # Start Audio hardware with microphone muted during bootup sequence
        self.audio_io.start()
        self.audio_io.disable_mic()

        # 1. Startup gesture & spoken greeting
        logger.info(f"Performing startup dual-arm wave and spoken greeting from {ROBOT_NAME}...")
        greeting_wav_path = os.path.join(os.path.dirname(__file__), "..", "audio", "greeting_aoede.wav")
        if os.path.exists(greeting_wav_path):
            try:
                import wave
                with wave.open(greeting_wav_path, "rb") as wf:
                    greeting_pcm = wf.readframes(wf.getnframes())
                self.audio_io.play_audio(greeting_pcm)
                print(f"\n🤖 [{ROBOT_NAME}]: Hello there human!! I'm Gemini, your friendly desktop companion! It's great to be here!", flush=True)
            except Exception as e:
                logger.warning(f"Could not play greeting audio: {e}")

        # Execute dual-arm wave gesture
        await asyncio.get_event_loop().run_in_executor(
            None, self.motor_subagent.wave, "both"
        )

        # Wait for greeting audio playback to finish draining through speaker
        await self.audio_io.wait_playback_done(timeout=10.0)

        # 2. Connect to pure Gemini Live session with resilient auto-reconnect
        logger.info(f"🚀 Startup complete! {ROBOT_NAME} is listening for your voice...")

        try:
            while self._running:
                logger.info("Connecting to Gemini Live session...")
                try:
                    async with client.aio.live.connect(model=self.model, config=config) as session:
                        logger.info("Connected to Gemini Live session.")

                        # Clear any stale audio accumulated during connection phase
                        self.audio_io.clear_mic_buffer()
                        self.audio_io.enable_mic()

                        receive_task = asyncio.create_task(self._receive_loop(session))
                        mic_task = asyncio.create_task(self._mic_send_loop(session))

                        done, pending = await asyncio.wait(
                            [mic_task, receive_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in pending:
                            task.cancel()
                        for task in done:
                            if task.exception():
                                raise task.exception()

                except (asyncio.CancelledError, KeyboardInterrupt):
                    logger.info("Shutting down session...")
                    break
                except Exception as e:
                    err_msg = str(e)
                    if "credits are depleted" in err_msg.lower() or "billing" in err_msg.lower():
                        print("\n" + "!" * 64)
                        print("❌ GEMINI API BILLING / CREDITS ERROR")
                        print("Your Google AI Studio project prepayment credits are depleted.")
                        print("!" * 64 + "\n")
                        break
                    elif "api key not valid" in err_msg.lower():
                        print("\n" + "!" * 64)
                        print("❌ GEMINI API KEY INVALID")
                        print("Please check your GEMINI_API_KEY in .env")
                        print("!" * 64 + "\n")
                        break
                    else:
                        if self._running:
                            logger.warning(f"Gemini Live session disconnected: {e}. Reconnecting in 1s...")
                            await asyncio.sleep(1.0)
        finally:
            self.stop()

    def stop(self) -> None:
        """Clean up audio and motors."""
        self._running = False
        logger.info("Stopping agent resources...")
        self.audio_io.stop()
        self.motor_subagent.close()
        print("Robot agent safely stopped.")
