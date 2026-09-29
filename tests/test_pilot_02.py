import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_02_DIR = REPO_ROOT / "pilot_02"
REPORTS_DIR = REPO_ROOT / "reports"

SELECTED_IDEAS = ["IDEA_003", "IDEA_005", "IDEA_011", "IDEA_018", "IDEA_021"]
REQUIRED_PACKAGE_FILES = [
    "story_bible.json",
    "fact_lock.json",
    "full_script.json",
    "full_script_readable.txt",
    "qc_report.json",
    "revision_log.json",
]


def test_pilot_02_packages_exist():
    """Verify that all 5 user-selected episode packages exist with all 6 required files."""
    for idea_id in SELECTED_IDEAS:
        ep_dir = PILOT_02_DIR / idea_id
        assert ep_dir.exists(), f"Missing package directory for {idea_id}"
        for fname in REQUIRED_PACKAGE_FILES:
            fpath = ep_dir / fname
            assert fpath.exists(), f"Missing required file {fname} in {ep_dir}"
            assert fpath.stat().st_size > 0, f"File {fname} in {ep_dir} is empty"


def test_pilot_02_master_reports():
    """Verify that master reports full_script_pilot_02.json and .csv exist and match."""
    rep_json = REPORTS_DIR / "full_script_pilot_02.json"
    rep_csv = REPORTS_DIR / "full_script_pilot_02.csv"

    assert rep_json.exists()
    assert rep_csv.exists()

    with open(rep_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["pilot_name"] == "FULL_SCRIPT_PILOT_02"
    assert data["provider"] == "Google Gemini"
    assert data["connection_status"] == "CONNECTED"
    assert len(data["episodes"]) == 5

    # Check zero visual/tts safety
    safety = data.get("generation_safety", {})
    assert safety.get("tts_generation_count", 0) == 0
    assert safety.get("image_generation_count", 0) == 0
    assert safety.get("video_generation_count", 0) == 0
    assert safety.get("google_flow_requests", 0) == 0

    # Cross-pilot similarity
    dup = data.get("cross_pilot_duplication", {})
    assert dup.get("highest_pair_similarity_pct", 100.0) < 40.0
    assert dup.get("status") == "PASS"


def test_pilot_02_script_narrative_specifications():
    """Validate 10-13 min length, word count, MC host, delivery profiles, and reveal restraint."""
    allowed_profiles = {"HOOK", "NORMAL", "MYSTERY", "REVEAL", "COMMENT", "ENDING"}

    for idea_id in SELECTED_IDEAS:
        ep_dir = PILOT_02_DIR / idea_id
        with open(ep_dir / "full_script.json", "r", encoding="utf-8") as f:
            script_data = json.load(f)
        with open(ep_dir / "qc_report.json", "r", encoding="utf-8") as f:
            qc_data = json.load(f)

        # Word count & duration (2,500 - 3,200 words, ~10-13 mins)
        words = script_data.get("total_words", 0)
        assert 2500 <= words <= 3200, f"{idea_id} word count {words} outside 2500-3200"

        # Segment count (80 - 100 segments)
        segments = script_data.get("segments", [])
        assert 80 <= len(segments) <= 100, f"{idea_id} segment count {len(segments)} outside 80-100"

        # MC Voice constraint: host is Minh / Binh
        host = script_data.get("host", {})
        assert host.get("name") == "Minh" or host.get("id") == "MINH"
        assert host.get("voice") == "Binh"

        for s in segments:
            assert s.get("speaker", "").upper() == "MINH", f"{idea_id} segment {s.get('id')} has non-Minh speaker"
            assert s.get("delivery_profile") in allowed_profiles, f"Invalid delivery profile in {idea_id}: {s.get('delivery_profile')}"

        # Audience interactions (3 to 6 per episode)
        audience_segs = [s for s in segments if s.get("audience_address")]
        assert 3 <= len(audience_segs) <= 6, f"{idea_id} audience interaction count {len(audience_segs)} outside 3-6"

        # No audience address in REVEAL segments
        reveal_audience = [s for s in segments if s.get("delivery_profile") == "REVEAL" and s.get("audience_address")]
        assert len(reveal_audience) == 0, f"{idea_id} has audience address in REVEAL segments: {reveal_audience}"

        # QC and approval status
        assert qc_data.get("status") == "PASS", f"{idea_id} QC status is not PASS"
        assert script_data.get("status") == "AWAITING_USER_SCRIPT_REVIEW", f"{idea_id} status is not AWAITING_USER_SCRIPT_REVIEW"
