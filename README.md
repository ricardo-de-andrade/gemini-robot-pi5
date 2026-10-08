 # Liverpool: Raspberry Pi 5 Gemini Live Robotics Agent

An interactive, physically-embodied robot powered by a **Raspberry Pi 5**, **Google's Gemini Multimodal Live API**, and **4x 28BYJ-48 stepper motors with ULN2003 drivers**.

The robot features real-time bidirectional voice conversation with conversational gesturing: waving hello, nodding, celebrating, looking around, and actuating its arms, head, and body smoothly while talking.

---

## 📋 Table of Contents
- [Liverpool: Raspberry Pi 5 Gemini Live Robotics Agent](#liverpool-raspberry-pi-5-gemini-live-robotics-agent)
  - [📋 Table of Contents](#-table-of-contents)
  - [1. Prerequisites \& Bill of Materials](#1-prerequisites--bill-of-materials)
    - [Core Hardware](#core-hardware)
    - [Software Requirements](#software-requirements)
  - [2. Setting Up a Brand New Raspberry Pi 5 from Scratch](#2-setting-up-a-brand-new-raspberry-pi-5-from-scratch)
    - [Step A: Flash Raspberry Pi OS using Raspberry Pi Imager](#step-a-flash-raspberry-pi-os-using-raspberry-pi-imager)
    - [Step B: First Boot \& Connecting via SSH](#step-b-first-boot--connecting-via-ssh)
    - [Step C: Update the OS \& Install Git](#step-c-update-the-os--install-git)
  - [3. Transferring \& Installing the Project](#3-transferring--installing-the-project)
    - [Option A: Transfer Files from your Computer via SCP](#option-a-transfer-files-from-your-computer-via-scp)
    - [Option B: Clone via Git](#option-b-clone-via-git)
    - [Run the Automated Setup Script on the Pi](#run-the-automated-setup-script-on-the-pi)
  - [4. Hardware Wiring \& Electrical Architecture](#4-hardware-wiring--electrical-architecture)
    - [40-Pin GPIO Wiring Matrix](#40-pin-gpio-wiring-matrix)
  - [5. Hardware Diagnostics \& Verification](#5-hardware-diagnostics--verification)
    - [1. Activate the Virtual Environment](#1-activate-the-virtual-environment)
    - [2. Verify Stepper Motors \& Individual Wiring Pins](#2-verify-stepper-motors--individual-wiring-pins)
    - [3. Verify USB Audio](#3-verify-usb-audio)
    - [4. Test Pre-programmed Gestures](#4-test-pre-programmed-gestures)
  - [6. Running the Gemini Live Voice Agent](#6-running-the-gemini-live-voice-agent)
    - [Step A: Configure API Key \& Environment](#step-a-configure-api-key--environment)
    - [Step B: Launch the Robot](#step-b-launch-the-robot)
  - [7. Running Automatically on Boot (Systemd Service)](#7-running-automatically-on-boot-systemd-service)
  - [8. Troubleshooting \& FAQ](#8-troubleshooting--faq)
    - [Issue: "All 4 LEDs on the ULN2003 board are dim and the motor does not move"](#issue-all-4-leds-on-the-uln2003-board-are-dim-and-the-motor-does-not-move)
    - [Issue: "Left arm moves backwards during wave"](#issue-left-arm-moves-backwards-during-wave)
    - [Issue: "No response from Gemini Live or speech gets cut off"](#issue-no-response-from-gemini-live-or-speech-gets-cut-off)
    - [Issue: "Pi disconnected from Wi-Fi after unplugging Ethernet"](#issue-pi-disconnected-from-wi-fi-after-unplugging-ethernet)
    - [Issue: "USB audio device cards swap after reboot / re-plugging"](#issue-usb-audio-device-cards-swap-after-reboot--re-plugging)
    - [Issue: "Motors vibrate or hum but do not turn"](#issue-motors-vibrate-or-hum-but-do-not-turn)
    - [Issue: "RPi.GPIO is not available on Raspberry Pi 5"](#issue-rpigpio-is-not-available-on-raspberry-pi-5)

---

## 1. Prerequisites & Bill of Materials

### Core Hardware
- **Raspberry Pi 5** (4GB or 8GB recommended).
- **Official Raspberry Pi 27W USB-C Power Supply** (dedicated to the Pi 5).
- **MicroSD Card** (32GB or 64GB, Class A2 rated recommended) or NVMe SSD HAT.
- **4x 28BYJ-48 5V Stepper Motors** with **ULN2003 Driver Boards** (HiLetgo kit).
- **External 5V DC Power Supply** (5V, 2.5A to 3.0A minimum) for powering the 4 stepper driver boards.
- **USB Microphone** (any standard USB microphone / mic dongle).
- **USB Speaker** (or USB sound card with 3.5mm speaker).
- **Female-to-Female Jumper Wires** (at least 20 wires).

### Software Requirements
- **Raspberry Pi OS (64-bit)** (Debian 12 Bookworm).
- **Google Gemini API Key** with access to the Gemini 2.0 Multimodal Live API ([Google AI Studio](https://aistudio.google.com/)).

---

## 2. Setting Up a Brand New Raspberry Pi 5 from Scratch

Follow these instructions if you are starting with a brand-new, unconfigured Raspberry Pi board.

### Step A: Flash Raspberry Pi OS using Raspberry Pi Imager

1. Download and install **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)** on your Mac, Windows, or Linux PC.
2. Insert your microSD card into your computer's card reader.
3. Open Raspberry Pi Imager:
   - **Raspberry Pi Device**: Select **Raspberry Pi 5**.
   - **Operating System**: Select **Raspberry Pi OS (64-bit)** *(Debian Bookworm)*.
   - **Storage**: Select your microSD card.
4. Click **Next**. When prompted *"Would you like to apply OS customization settings?"*, click **EDIT SETTINGS**:
   - **General Tab**:
     - **Set hostname**: `robotpi` (or `liverpool`)
     - **Set username and password**: Username `pi` (or your preferred username), enter a secure password.
     - **Configure wireless LAN**: Enter your Wi-Fi SSID and Wi-Fi password. Select your Wireless LAN country.
     - **Set locale settings**: Choose your Timezone and Keyboard layout.
   - **Services Tab**:
     - Check **Enable SSH**.
     - Select **Use password authentication** (or insert your SSH public key).
5. Click **Save**, then click **YES** to begin writing and verifying the OS image.

---

### Step B: First Boot & Connecting via SSH

1. Remove the microSD card from your computer and insert it into the microSD slot on your Raspberry Pi 5.
2. Plug the USB microphone and USB speaker into the USB ports of the Pi 5.
3. Plug in the official 27W USB-C power supply to boot the Pi.
4. Wait approximately 60–90 seconds for the Pi to complete its initial partition resize and connect to Wi-Fi.
5. On your Mac/PC, open a Terminal and connect via SSH:
   ```bash
   ssh pi@robotpi.local
   ```
   *(If prompted "Are you sure you want to continue connecting (yes/no)?", type `yes` and enter your password).*

> [!TIP]
> If `ssh pi@robotpi.local` cannot find the host, check your home router's DHCP client list to locate the Pi's local IP address (e.g., `192.168.1.150`), and connect using:
> ```bash
> ssh pi@192.168.1.150
> ```

---

### Step C: Update the OS & Install Git

Once logged into your Pi, run a full system update:
```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git
```

---

## 3. Transferring & Installing the Project

### Option A: Transfer Files from your Computer via SCP
If the code is currently on your computer:
```bash
# Run this from your computer terminal (where the 'liverpool' folder resides):
scp -r /path/to/liverpool pi@robotpi.local:~/liverpool
```

### Option B: Clone via Git
If hosted in a Git repository:
```bash
cd ~
git clone <your-repo-url> liverpool
```

### Run the Automated Setup Script on the Pi
```bash
cd ~/liverpool
chmod +x setup_pi5.sh
./setup_pi5.sh
```

The script automatically:
1. Installs system audio and GPIO libraries (`libportaudio2`, `portaudio19-dev`, `python3-lgpio`).
2. Creates an isolated virtual environment at `~/robot_venv` linked with system packages.
3. Installs `google-genai`, `gpiozero`, `sounddevice`, `numpy`, and `python-dotenv`.
4. Adds your user to the `audio` and `gpio` groups.

---

## 4. Hardware Wiring & Electrical Architecture

> [!CAUTION]
> **CRITICAL POWER WARNING**:
> **Never** power the 4 ULN2003 stepper driver boards from the Raspberry Pi 5's 5V rail.
> 4 stepper motors moving at the same time draw over 1.2 Amps. This will overload the Pi's power rail, triggering brownout resets or hardware damage.
>
> 1. Power the Raspberry Pi 5 using its **USB-C power adapter**.
> 2. Power all 4 ULN2003 boards from an **external 5V (2.5A–3A) power supply**.
> 3. **Connect the External Power Supply's GND to one of the Raspberry Pi GND pins (Pin 6, 14, 20, or 39)**. This shared ground reference is essential for the GPIO logic signals.

### 40-Pin GPIO Wiring Matrix

| Joint | Motor Model | Driver Board Pins | Pi 5 BCM GPIO | Physical Header Pin # | Orientation / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Left Arm** | 28BYJ-48 5V | **IN1, IN2, IN3, IN4** | **GPIO 17, 27, 22, 23** | **Pins 11, 13, 15, 16** | Inverted (`MOTOR_INVERTED=True`) for mirror mounting |
| **Right Arm** | 28BYJ-48 5V | **IN1, IN2, IN3, IN4** | **GPIO 24, 25, 5, 6** | **Pins 18, 22, 29, 31** | Normal orientation (Watch out: Pin 30 is GND) |
| **Head (Neck)** | 28BYJ-48 5V | **IN1, IN2, IN3, IN4** | **GPIO 12, 13, 16, 19** | **Pins 32, 33, 36, 35** | Normal pan (-90° to +90°) |
| **Body (Waist)**| 28BYJ-48 5V | **IN1, IN2, IN3, IN4** | **GPIO 20, 21, 26, 18** | **Pins 38, 40, 37, 12** | Normal pan (-90° to +90°) |
| **Common GND** | — | **Driver Board GND (-)** | **Pi GND** | **Pin 6, 14, 20, or 39** | Mandatory common logic reference |
| **Driver Power**| — | **Driver Board VCC (+)**| **External +5V PSU** | *(Do not connect to Pi)* | 5V / 3A dedicated motor rail |

*For complete diagrams, ASCII header pinout, and wiring rules, see [WIRING.md](file:///Users/rdeandrade/Downloads/liverpool_robot_pi5/WIRING.md).*

---

## 5. Hardware Diagnostics & Verification

Before starting the live agent, verify your audio devices, motor wiring, and individual LED indicators:

### 1. Activate the Virtual Environment
```bash
source ~/robot_venv/bin/activate
cd ~/liverpool
```

### 2. Verify Stepper Motors & Individual Wiring Pins
We provide an interactive diagnostic tool to test each coil pin individually with 1.2-second pulses so you can watch the 4 indicator LEDs (A, B, C, D) on each ULN2003 board:

```bash
# Test each pin of right_arm individually (watch LEDs A, B, C, D):
./diagnose_motors.sh right_arm

# Side-by-side comparison (Left Arm bright baseline vs Right Arm):
./diagnose_motors.sh compare

# Full 45° step test across all 4 motors:
./test_motors.sh
```

### 3. Verify USB Audio
Test microphone recording, dynamic device discovery, and speaker playback:
```bash
./test_audio.sh
```
*This command auto-detects your USB microphone and speaker by hardware chipset signature, records 3 seconds of sound, and plays it back through the speaker.*

### 4. Test Pre-programmed Gestures
```bash
python3 -m robot.main --gesture wave
python3 -m robot.main --gesture celebrate
python3 -m robot.main --gesture look_around
```

---

## 6. Running the Gemini Live Voice Agent

### Step A: Configure API Key
Create a `.env` file from the provided template:
```bash
cp .env.example .env
nano .env
```
Add your Gemini API key:
```env
GEMINI_API_KEY=AIzaSy...your-actual-api-key-here
GEMINI_LIVE_MODEL=gemini-2.5-flash-native-audio-latest
GEMINI_VOICE_NAME=Aoede
```
Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

### Step B: Launch the Robot
Use the launcher script, which automatically calibrates ALSA microphone gain to suppress fan noise below the speech threshold and starts the agent:
```bash
./run.sh
```

On bootup, Gemini will:
1. Play a warm spoken greeting through the USB speaker (*"Hello there human!! I'm Gemini, your friendly desktop companion!"*).
2. Wave both arms synchronously forward and upward.
3. Connect to the Gemini Live native audio session and listen for your voice.

Speak naturally:
- *"Hi Gemini, can you hear me? Wave your arms!"*
- *"Who are you and what can you do?"*
- *"Look to your left, then celebrate!"*

---

## 7. Running Automatically on Boot (Systemd Service)

To turn your Raspberry Pi into a dedicated, autonomous desktop companion that starts automatically when powered on:

1. Copy the systemd service file to the system directory:
   ```bash
   sudo cp ~/liverpool/robot.service /etc/systemd/system/
   ```
2. Reload systemd and enable the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable robot.service
   ```
3. Start the service immediately:
   ```bash
   sudo systemctl start robot.service
   ```
4. View live logs in real time:
   ```bash
   journalctl -u robot.service -f
   ```

---

## 8. Troubleshooting & FAQ

### Issue: "All 4 LEDs on the ULN2003 board are dim and the motor does not move"
*(While the other arm's controller LEDs are bright and working normally)*
- **Root Cause**: The ULN2003 board is not receiving its +5V supply. The LEDs are dimly glowing via parasitic 3.3V leakage from the GPIO logic pins, which provides zero torque.
- **Fix 1 (Most Common)**: Check the **black plastic jumper cap** on the ULN2003 board next to the power pins labeled `5-12V`. It must bridge the two pins. If it fell off during disassembly, replace it.
- **Fix 2**: Check that the `+` (VCC) power wire is plugged into **Pin 2 or Pin 4 (5V)**, not **Pin 1 or Pin 17 (3.3V)**!
- **Fix 3 (5-Second Isolation Test)**: Unplug the white 5-pin motor connector from the board. If the LEDs immediately light up brightly, the motor connector is misaligned or the motor coil has an internal short. If they stay dim, the issue is the power wire or missing jumper cap.

### Issue: "Left arm moves backwards during wave"
- **Cause**: The left arm motor is mounted facing outwards in reverse orientation relative to the right arm.
- **Fix**: Direction inversion is handled in software via `MOTOR_INVERTED['left_arm'] = True` in `config.py` (or `MOTOR_INVERT_LEFT_ARM=true` in `.env`).

### Issue: "No response from Gemini Live or speech gets cut off"
- **Cause**: High ambient microphone gain causes room/fan noise to continuously exceed the speech threshold (550 RMS), preventing Gemini's server-side Voice Activity Detection (VAD) from detecting silence turn completion.
- **Fix**: `run.sh` automatically calibrates capture volume across all ALSA cards to **gain 2** (12%, +2.97dB). You can also run:
  ```bash
  amixer -c Device sset Mic 2
  sudo alsactl store
  ```

### Issue: "Pi disconnected from Wi-Fi after unplugging Ethernet"
- **Cause**: NetworkManager has no saved Wi-Fi credentials for your network.
- **Fix**: Connect to your Wi-Fi using `nmcli`:
  ```bash
  sudo nmcli dev wifi connect "<YOUR_SSID>" password "<YOUR_PASSWORD>"
  ```
  NetworkManager will save the connection with `connection.autoconnect: yes`.

### Issue: "USB audio device cards swap after reboot / re-plugging"
- **Cause**: Linux enumerates USB 3.0 before USB 2.0. Swapping ports changes ALSA card numbers (`card 0` vs `card 1`).
- **Fix**: Dynamic audio auto-detection in `robot/audio/audio_io.py` automatically binds devices by chipset name (`USB PnP Sound Device` for mic, `UACDemoV1.0` for speaker), making the system completely port-agnostic.

### Issue: "Motors vibrate or hum but do not turn"
- **Cause**: Out-of-order phase wiring or low voltage.
- **Fix**: Run `./diagnose_motors.sh <joint>` to test each coil pin individually. Ensure the external power supply is providing at least 5.0V under load.

### Issue: "RPi.GPIO is not available on Raspberry Pi 5"
- **Cause**: Pi 5 uses the new RP1 southbridge chip, which breaks legacy `RPi.GPIO`.
- **Fix**: This project natively uses `gpiozero` and `lgpio`, which are fully compatible with Pi 5 and Bookworm.
