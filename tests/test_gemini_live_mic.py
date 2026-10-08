"""Integration test verifying microphone and audio streaming with Gemini Live API."""

import argparse
import asyncio
import logging
import os
import sys
import time
import wave
from pathlib import Path

# Add project root to sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import (
    GEMINI_API_KEY,
    GEMINI_LIVE_MODEL,
    GEMINI_VOICE_NAME,
    MIC_DEVICE_INDEX,
    SPEAKER_DEVICE_INDEX,
    ROBOT_NAME,
)
from robot.agent.tools import get_tool_declarations
from robot.audio.audio_io import AudioIO

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("[ERROR] google-genai package not found.")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TestMicGeminiLive")


async def run_integration_test(audio_file: str | None = None, live_mic_timeout: float = 12.0) -> bool:
    print("\n" + "=" * 65)
    print("🧪 TEST: Microphone Integration with Gemini Live Multimodal API")
    print(f"   Model: {GEMINI_LIVE_MODEL}")
    print(f"   Voice: {GEMINI_VOICE_NAME}")
    print(f"   Input Mode: {'Simulated Physical Mic Capture File (' + audio_file + ')' if audio_file else 'Live Hardware Microphone'}")
    print("=" * 65 + "\n")

    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set in environment or .env.")
        return False

    client = genai.Client(api_key=GEMINI_API_KEY, http_options={"api_version": "v1alpha"})

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE_NAME)
            )
        ),
        system_instruction=types.Content(
            parts=[
                types.Part.from_text(
                    text=f"You are {ROBOT_NAME}, an expressive desktop robot. When you hear user speech, answer cheerily and briefly. If asked to wave, call perform_gesture with gesture='wave'."
                )
            ]
        ),
        tools=[{"function_declarations": get_tool_declarations()}],
    )

    test_passed = False
    chunks_sent = 0
    response_audio_chunks = 0
    total_audio_bytes = 0
    tool_calls_received = []

    audio_io = None
    if not audio_file:
        audio_io = AudioIO(mic_device=MIC_DEVICE_INDEX, speaker_device=SPEAKER_DEVICE_INDEX)
        audio_io.start()
        audio_io.enable_mic()

    try:
        async with client.aio.live.connect(model=GEMINI_LIVE_MODEL, config=config) as session:
            logger.info("Connected to Gemini Live session.")

            # Receiver loop
            async def receive_task():
                nonlocal test_passed, response_audio_chunks, total_audio_bytes, tool_calls_received
                try:
                    async for response in session.receive():
                        server_content = getattr(response, "server_content", None)
                        if server_content is not None:
                            model_turn = getattr(server_content, "model_turn", None)
                            if model_turn is not None:
                                for part in getattr(model_turn, "parts", []):
                                    text = getattr(part, "text", None)
                                    if text:
                                        logger.info(f"🤖 [Gemini Text]: {text}")
                                    inline_data = getattr(part, "inline_data", None)
                                    if inline_data and hasattr(inline_data, "data"):
                                        response_audio_chunks += 1
                                        total_audio_bytes += len(inline_data.data)
                                        if audio_io:
                                            audio_io.play_audio(inline_data.data)

                            turn_complete = getattr(server_content, "turn_complete", False)
                            if turn_complete:
                                logger.info("✅ Gemini finished responding turn!")
                                if response_audio_chunks > 0 or tool_calls_received:
                                    test_passed = True
                                    break

                        tool_call = getattr(response, "tool_call", None)
                        if tool_call is not None:
                            f_responses = []
                            for fc in getattr(tool_call, "function_calls", []):
                                logger.info(f"🔧 [Gemini Tool Call]: {fc.name}({fc.args})")
                                tool_calls_received.append((fc.name, dict(fc.args)))
                                call_id = getattr(fc, "id", None) or f"{fc.name}_{int(time.time()*1000)}"
                                f_responses.append(
                                    types.FunctionResponse(
                                        name=fc.name,
                                        response={"result": "Gesture executed successfully"},
                                        id=call_id,
                                    )
                                )
                            if f_responses:
                                await session.send_tool_response(function_responses=f_responses)
                except asyncio.CancelledError:
                    pass

            recv_task = asyncio.create_task(receive_task())

            if audio_file:
                # Stream pre-recorded physical microphone audio
                wf = wave.open(audio_file, "rb")
                raw_bytes = wf.readframes(wf.getnframes())
                wf.close()

                logger.info(f"Streaming {len(raw_bytes)} bytes of microphone audio ({len(raw_bytes)/32000:.2f}s)...")
                chunk_size = 3200  # 100ms at 16kHz
                for i in range(0, len(raw_bytes), chunk_size):
                    chunk = raw_bytes[i:i + chunk_size]
                    await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
                    chunks_sent += 1
                    await asyncio.sleep(0.1)

                # Send trailing digital silence to trigger server-side VAD turn completion
                logger.info("Sending trailing silence for VAD turn completion trigger...")
                silence_chunk = b"\x00" * chunk_size
                for _ in range(15):
                    await session.send_realtime_input(audio=types.Blob(data=silence_chunk, mime_type="audio/pcm;rate=16000"))
                    chunks_sent += 1
                    await asyncio.sleep(0.1)

                await asyncio.wait_for(recv_task, timeout=15.0)

            else:
                # Live mic streaming
                logger.info(f"Listening for speech through physical microphone for {live_mic_timeout}s (speak now!)...")
                async def stream_live():
                    nonlocal chunks_sent
                    try:
                        async for chunk in audio_io.stream_mic_audio():
                            chunks_sent += 1
                            await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
                    except asyncio.CancelledError:
                        pass

                stream_task = asyncio.create_task(stream_live())
                try:
                    await asyncio.wait_for(recv_task, timeout=live_mic_timeout)
                except asyncio.TimeoutError:
                    logger.info("Live mic listening window ended.")
                finally:
                    stream_task.cancel()

    finally:
        if audio_io:
            audio_io.stop()

    print("\n" + "=" * 65)
    print("📊 TEST RESULTS SUMMARY")
    print(f"   Audio Chunks Streamed:        {chunks_sent}")
    print(f"   Gemini Audio Chunks Received: {response_audio_chunks} ({total_audio_bytes} bytes)")
    print(f"   Gemini Tool Calls Received:   {len(tool_calls_received)} {tool_calls_received}")
    print(f"   Overall Test Status:          {'PASSED ✅' if test_passed else 'FAILED ❌'}")
    print("=" * 65 + "\n")

    return test_passed


def main():
    parser = argparse.ArgumentParser(description="Test microphone and Gemini Live API integration")
    parser.add_argument("--file", type=str, default="/home/ri/mic_test_capture.wav",
                        help="Path to WAV file to stream (default: /home/ri/mic_test_capture.wav)")
    parser.add_argument("--live", action="store_true",
                        help="Record from physical microphone in real-time instead of file")
    parser.add_argument("--timeout", type=float, default=12.0,
                        help="Timeout for live test in seconds")
    args = parser.parse_args()

    audio_file = None if args.live else args.file
    if audio_file and not os.path.exists(audio_file):
        print(f"[WARNING] File {audio_file} does not exist, falling back to live mic.")
        audio_file = None

    success = asyncio.run(run_integration_test(audio_file=audio_file, live_mic_timeout=args.timeout))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
