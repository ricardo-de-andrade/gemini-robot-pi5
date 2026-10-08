#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi
# Calibrate USB mic gain across all possible ALSA card indices (0, 1, 2, 3, Device)
for c in 0 1 2 3 Device; do
    amixer -c "$c" sset Mic 2 >/dev/null 2>&1 || true
done
source robot_venv/bin/activate
export PYTHONPATH=.
export PYTHONUNBUFFERED=1
exec python3 -m robot.main --run "$@"
