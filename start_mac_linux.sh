#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if [ ! -f .venv/chargesynth_installed.txt ]; then
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/chargesynth_installed.txt
fi
if [ ! -f .env ]; then cp .env.example .env; fi
exec .venv/bin/python run.py
