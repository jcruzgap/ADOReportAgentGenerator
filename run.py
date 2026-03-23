"""Convenience entry point: python run.py [config_path]"""
import subprocess
import sys
import os

root = os.path.dirname(os.path.abspath(__file__))
sys.exit(
    subprocess.call(
        [sys.executable, "-m", "agent-py"] + sys.argv[1:],
        cwd=root,
    )
)
