"""
app.py - Main entry point for Sentinel AI Security & Hardware Telemetry Suite.
"""
import sys
from pathlib import Path

# Ensure project root is always first in sys.path regardless of launch cwd
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.dashboard import main

if __name__ == "__main__":
    main()
