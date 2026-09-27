#!/usr/bin/env python
"""
Launch the P2OASys user survey for Process Factors & Life Cycle Factors.

Standalone launcher for the survey Streamlit page on port 8503.

Usage:
    python scripts/run_survey.py
    # or
    streamlit run apps/doss_ondemand/survey_page.py --server.port 8503
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main():
    survey_page = REPO_ROOT / "apps" / "doss_ondemand" / "survey_page.py"
    
    if not survey_page.exists():
        print(f"Error: Survey page not found at {survey_page}")
        sys.exit(1)
    
    # Ensure PYTHONPATH includes repo root
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH", "")
    if str(REPO_ROOT) not in python_path:
        env["PYTHONPATH"] = f"{REPO_ROOT}:{python_path}" if python_path else str(REPO_ROOT)
    
    print("Starting P2OASys Survey on http://localhost:8503")
    print("Press Ctrl+C to stop\n")
    
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(survey_page),
        "--server.port", "8503",
        "--server.headless", "true",
    ]
    
    try:
        subprocess.run(cmd, env=env, cwd=REPO_ROOT)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
