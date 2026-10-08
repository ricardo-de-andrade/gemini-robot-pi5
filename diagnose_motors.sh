#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
source robot_venv/bin/activate
export PYTHONPATH=.
exec python3 diagnose_motors.py "$@"
