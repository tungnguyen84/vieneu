"""CLI Entry point for Exporting Google Flow App JSON.

Usage:
    python apps/production_pilot_03_export_google_flow.py
"""
import json
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.visual_pilot_03_v1_0a.google_flow_exporter import export_google_flow_app_json

if __name__ == "__main__":
    result = export_google_flow_app_json()
    print("\n" + "=" * 60)
    print("PRODUCTION PILOT 03 — GOOGLE FLOW JSON EXPORT REPORT")
    print("=" * 60)
    print(f"Schema: SCC_FLOW_V1")
    print(f"Validation Status: {result['validation_status']}")
    print("\nEP003:")
    print(f"  Scenes: {result['ep003_stats']['scenes']}")
    print(f"  Image-only: {result['ep003_stats']['image_only']}")
    print(f"  Video recommended: {result['ep003_stats']['video_recommended']}")
    print(f"  Characters: {result['ep003_stats']['characters']}")
    print(f"  Prop refs: {result['ep003_stats']['props']}")
    print(f"  Locations: {result['ep003_stats']['locations']}")
    print(f"  Overlays: {result['ep003_stats']['overlays']}")
    print("\nEP011:")
    print(f"  Scenes: {result['ep011_stats']['scenes']}")
    print(f"  Image-only: {result['ep011_stats']['image_only']}")
    print(f"  Video recommended: {result['ep011_stats']['video_recommended']}")
    print(f"  Characters: {result['ep011_stats']['characters']}")
    print(f"  Prop refs: {result['ep011_stats']['props']}")
    print(f"  Locations: {result['ep011_stats']['locations']}")
    print(f"  Overlays: {result['ep011_stats']['overlays']}")
    print("\nExported Files:")
    print(f"  - {result['combined_file']}")
    print(f"  - {result['ep003_file']}")
    print(f"  - {result['ep011_file']}")
    print("=" * 60)
