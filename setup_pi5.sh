#!/bin/bash
set -e

echo "=========================================================="
echo " Setting up Raspberry Pi 5 Gemini Live Robotics Agent"
echo "=========================================================="

# Check if running as root or with sudo if needed
if [ "$EUID" -eq 0 ]; then
    echo "Please do NOT run this script as root / sudo."
    echo "Run as your standard user: ./setup_pi5.sh"
    exit 1
fi

echo "[1/4] Updating package index and installing system libraries..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    libportaudio2 \
    portaudio19-dev \
    libasound2-dev \
    python3-lgpio \
    swig

echo "[2/4] Setting up Python virtual environment..."
VENV_DIR="$HOME/robot_venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
    echo "Virtual environment created at $VENV_DIR (with system-site-packages for lgpio)"
else
    echo "Virtual environment already exists at $VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

echo "[3/4] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/4] Verifying Audio & GPIO permissions..."
# Ensure user is in audio and gpio groups
sudo usermod -a -G gpio,audio "$USER"

echo ""
echo "=========================================================="
echo " Setup complete!"
echo " Remember to activate the virtual environment with:"
echo "   source ~/robot_venv/bin/activate"
echo " And set your Gemini API Key:"
echo "   export GEMINI_API_KEY='your-key-here'"
echo "=========================================================="
