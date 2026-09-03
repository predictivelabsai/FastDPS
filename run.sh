#!/usr/bin/env bash
set -euo pipefail

if [[ ! -x .venv/bin/python ]]; then
  python3.13 -m venv .venv
fi
.venv/bin/python -m ensurepip --upgrade >/dev/null
.venv/bin/python -m pip install -e .
exec .venv/bin/python web_app.py
