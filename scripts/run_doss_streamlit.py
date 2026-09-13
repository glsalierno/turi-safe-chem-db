#!/usr/bin/env python3
"""Thin launcher: streamlit run apps/doss_ondemand/app.py --server.port 8502"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
env = os.environ.copy()
pp = env.get("PYTHONPATH", "")
env["PYTHONPATH"] = str(REPO) + (os.pathsep + pp if pp else "")

cmd = [
    sys.executable, "-m", "streamlit", "run",
    str(REPO / "apps" / "doss_ondemand" / "app.py"),
    "--server.port", "8502",
]
raise SystemExit(subprocess.call(cmd, env=env))
