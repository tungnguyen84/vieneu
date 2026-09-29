"""CLI Entry point for Production Pilot 03 Visual Planning V1.0a.

Usage:
    python apps/production_pilot_03_visual_v1_0a_builder.py
"""
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.visual_pilot_03_v1_0a.builder import run_visual_pipeline_v1_0a

if __name__ == "__main__":
    run_visual_pipeline_v1_0a()
