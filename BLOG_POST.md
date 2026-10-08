# Building an Embodied AI Robot with Raspberry Pi 5 and Gemini 2.0 Multimodal Live API

*How to bridge physical stepper motors, a Raspberry Pi 5, and Google’s low-latency Live API into a voice-driven, gesturing desktop robot.*

---

![Robot Header Image](https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=80)
*Photo credit: Unsplash*

Over the past two years, conversational AI has become virtually ubiquitous. Yet for all their intelligence, most Large Language Models remain trapped behind browser tabs and chat bubbles. They can write poetry, diagnose obscure bugs, and debate philosophy—but they cannot wave hello, tilt their head when listening, or react physically to their environment.

I wanted to change that.

In this project, I set out to build an embodied, physical desktop robot powered by a **Raspberry Pi 5** and **Google’s Gemini 2.0 Multimodal Live API**. The robot engages in real-time, bidirectional voice conversations—listening, interrupting, and speaking with near-zero latency—while physically actuating its arms, head, and body through coordinated stepper motor gestures.

Here is the story of how it was built, the architecture behind it, and the hard-won hardware and software lessons learned along the way.

---

## 1. High-Level Architecture

The robot’s architecture splits into three main layers:

```
                    ┌──────────────────────────────────────────┐
                    │      Google Gemini 2.0 Live API          │
                    │   (Bidirectional WebSocket Audio/Events) │
                    └────────────────────▲─────────────────────┘
                                         │ Full-Duplex PCM
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │          Raspberry Pi 5 Brain           │
                    │  • Audio IO Engine (PyAudio / ALSA)     │
                    │  • Async Gesture & Kinematics Engine    │
                    │  • Non-blocking LGPIO Motor Controller  │
                    └────────────────────┬────────────────────┘
                                         │ 16 GPIO Control Pins
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │      4x ULN2003 Darlington Drivers      │
                    │   + External 5V 3A Regulated PSU Rail   │
                    └────────────────────┬────────────────────┘
                                         │
        ┌───────────────┬────────────────┴───────────────┬───────────────┐
        ▼               ▼                                ▼               ▼
 ┌─────────────┐ ┌──────────────┐                 ┌─────────────┐ ┌─────────────┐
 │  Left Arm   │ │  Right Arm   │                 │    Head     │ │    Body     │
 │  (28BYJ-48) │ │  (28BYJ-48)  │                 │  (28BYJ-48) │ │  (28BYJ-48) │
 └─────────────┘ └──────────────┘                 └─────────────┘ └─────────────┘
```

1. **Multimodal Live Brain**: A WebSocket connection to Google's Gemini 2.0 Multimodal Live API streaming 16kHz PCM audio bidirectionally.
2. **Audio I/O Pipeline**: Real-time microphone capture and asynchronous speaker playback running in non-blocking worker threads.
3. **Physical Actuation**: Four 28BYJ-48 5V geared stepper motors driven by ULN2003 Darlington arrays over 16 dedicated Raspberry Pi 5 GPIO pins.

---

## 2. Hardware & Bill of Materials

| Component | Role | Details |
| :--- | :--- | :--- |
| **Raspberry Pi 5** | Main Computer | 8GB RAM, Raspberry Pi OS 64-bit (Debian 12 Bookworm). |
| **Official 27W USB-C PSU** | Pi Power | Clean 5.1V / 5A dedicated power rail for the Pi 5. |
| **4x 28BYJ-48 Steppers** | Actuators | 5V 4-phase geared stepper motors (64:1 gear reduction). |
| **4x ULN2003 Driver Boards** | Motor Drivers | Darlington transistor arrays with indicator LEDs. |
| **External 5V DC Power Supply** | Motor Power | 5V 3A dedicated supply (crucial for stepper current draw). |
| **USB Microphone & Speaker** | Voice I/O | Standard plug-and-play USB audio devices. |
| **Jumper Wires & Breadboard** | Interconnects | Common ground distribution and 16 signal lines. |

> **⚠️ Rule #1 of Stepper Motors on Raspberry Pi:**  
> Never power motors directly from the Raspberry Pi’s 5V GPIO header. Four 28BYJ-48 steppers can draw upwards of 1.2A to 1.6A simultaneously. Pulling that current through the Pi's onboard power rail will cause brownouts, USB drops, and SD card corruption. An external power supply is essential.

---

## 3. Real-Time Conversation with Gemini 2.0 Live

The conversational engine is powered by Google's **Gemini 2.0 Multimodal Live API** (`gemini-2.5-flash-native-audio-latest` / Gemini Live endpoints). 

Unlike traditional "turn-based" voice assistants that stitch together speech-to-text (STT), text generation (LLM), and text-to-speech (TTS), the Live API operates on **native audio streaming**:

- **Bidirectional Streaming**: Audio is captured via `pyaudio` at 16,000 Hz / 16-bit PCM and streamed as base64 chunks directly to the model over a persistent WebSocket.
- **Natural Cadence & Interruption**: The model understands vocal inflection, hesitations, and allows natural interruptions without awkward pauses.
- **Personality & Voice**: Configured with the **Aoede** voice—a warm, jovial persona named **Gemini** who greets you with an upbeat intro and coordinated arm gestures.

```python
# Startup Greeting & Gesturing
async def on_startup(self):
    logger.info("Triggering greeting: Hello there human!!")
    await asyncio.gather(
        self.play_audio_file("robot/audio/greeting_aoede.wav"),
        self.kinematics.gesture_wave_hello()
    )
```

---

## 4. Designing the Motor & Kinematics Engine

The 28BYJ-48 stepper motors have a 64:1 internal gear reduction and 64 half-steps per motor revolution, yielding **4,096 half-steps per 360° output rotation** (~0.088° per step).

### 4-Phase Half-Stepping Sequence
To maximize torque and achieve ultra-smooth mechanical motion, we implemented an 8-state half-stepping sequence:

```python
HALF_STEP_SEQ = [
    [1, 0, 0, 0],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 0],
    [0, 0, 1, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
]
```

### Expressive Gestures
Through an asynchronous `KinematicsEngine`, the robot performs high-level physical routines without blocking the conversational audio loop:
- **`gesture_wave_hello()`**: Lifts the right arm and waves between 30° and 60° back and forth.
- **`gesture_nod()`**: Smoothly pitches the head down and up in agreement.
- **`gesture_celebrate()`**: Raises both arms simultaneously while oscillating the torso.
- **`gesture_tilt()`**: Tilts the head inquisitively when listening to user questions.

---

## 5. Hard-Won Engineering Lessons & Debugging

Building hardware projects rarely goes smoothly on the first try. Here are four real challenges we encountered and resolved during this build:

### 1. The "Dim ULN2003 LEDs" Mystery (Common Ground Failure)
When we first connected the right arm driver board, all four indicator LEDs on the ULN2003 glowed very dimly, and the motor hummed without rotating.
- **Root Cause**: The external 5V power supply ground was not tied back to the Raspberry Pi’s ground pin.
- **Fix**: The Raspberry Pi's 3.3V logic signals require a unified reference voltage. Connecting Pi `GND (Pin 6/14)` to the external PSU `GND` completed the circuit, restoring full brightness to the LEDs and immediate full-torque rotation.

### 2. The Mirror-Image Arm Inversion
When testing the robot's waving sequence, the right arm moved forward as expected, but the left arm moved backwards into the chassis.
- **Root Cause**: The left and right arm motors are physically mounted facing opposite directions (mirror symmetry). 
- **Fix**: Rather than physically flipping brackets, we added motor inversion flags in `config.py`:
  ```python
  MOTOR_INVERT_LEFT_ARM = True
  MOTOR_INVERT_RIGHT_ARM = False
  ```
  The kinematics engine transparently reverses step sequences whenever the inversion flag is set.

### 3. Raspberry Pi 5 & The Death of `RPi.GPIO`
Developers coming from Raspberry Pi 3 or 4 are accustomed to `import RPi.GPIO as GPIO`. On the Raspberry Pi 5, the Broadcom BCM2712 processor offloads all GPIO to a dedicated custom I/O controller (the **RP1** chip). As a result, direct `/dev/gpiomem` register access is deprecated.
- **Fix**: We built the stepper driver using modern character-device GPIO (`lgpio` and `gpiod`), guaranteeing compatibility across Raspberry Pi OS Bookworm kernels.

### 4. Preventing WebSocket Audio Keepalive Drops
During long periods of silence, the WebSocket connection to Gemini Live was dropping with code `1011: keepalive ping timeout`.
- **Fix**: Implemented a background heartbeat task alongside the audio streaming loop that sends silence frames or keepalive pings whenever microphone input drops below threshold, keeping the session alive indefinitely.

---

## 6. How to Run It Yourself

### 1. Clone the Repository
```bash
git clone https://github.com/ricardo-de-andrade/gemini-robot-pi5.git
cd gemini-robot-pi5
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and insert your Gemini API key from [Google AI Studio](https://aistudio.google.com/):
```bash
cp .env.example .env
nano .env
```
*(Never commit `.env` to version control!)*

### 3. Run Hardware Diagnostics
Before launching the full AI stack, verify each motor and audio interface:
```bash
# Diagnostic tool to test GPIO pins, coils, and rotation
python3 diagnose_motors.py --motor right_arm --sweep

# Test USB microphone and speaker
./test_audio.sh
```

### 4. Launch the Live Voice Agent
```bash
./run.sh
```

---

## 7. What's Next?

With physical embodiment and real-time conversation working, the next milestones are:
1. **Gemini Vision Integration**: Connecting a Raspberry Pi Camera Module 3 so the robot can see what you are holding up and comment on objects in real-time.
2. **3D Printed Chassis**: Designing an open-source printable enclosure to house the Pi 5, drivers, speaker, and articulated arms.
3. **Autonomous Behaviors**: Adding face-tracking panning so the robot maintains eye contact as you move around the room.

---

## Conclusion

Embodied AI transforms the experience of interacting with machine intelligence. When an AI greets you with a physical wave and looks directly at you while conversing, it crosses the threshold from a digital tool to a presence.

Check out the full open-source code and wiring diagrams on GitHub:  
👉 **[GitHub: ricardo-de-andrade/gemini-robot-pi5](https://github.com/ricardo-de-andrade/gemini-robot-pi5)**

If you enjoyed this build, leave a star on the repo or drop a comment below!
