import sys
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
import json
from pathlib import Path
from apps.production_story import (
    validate_story_json,
    clean_text_for_tts,
    compute_segment_hash,
    apply_audio_speed
)

def test_validation():
    with open('src/vieneu/assets/voices_v3_turbo.json', encoding='utf-8') as f:
        voices_data = json.load(f)
    available_voices = [(k, k) for k in voices_data['presets'].keys()]

    with open('tests/test_pilot_story.json', encoding='utf-8') as f:
        pilot = json.load(f)

    is_valid, err, proj_info, chars_map, warnings, stats = validate_story_json(pilot, available_voices)
    print("Is Valid:", is_valid)
    assert is_valid, f"Validation failed: {err}"
    print("Project info:", proj_info['title'], "| Slug:", proj_info['slug'])
    print("Characters detected:")
    for cid, cdata in chars_map.items():
        print(f"  {cid}: display={cdata['display_name']}, req={cdata['requested_voice']}, mapped={cdata['voice']}, status={cdata['match_status']}")
    
    assert "MINH" in chars_map and "LAN" in chars_map, "Must detect MINH and LAN"
    assert chars_map["MINH"]["voice"] == "Thanh Bình", f"MINH should map to Thanh Bình (Binh), got {chars_map['MINH']['voice']}"
    assert chars_map["LAN"]["voice"] == "Trúc Ly", f"LAN should map to Trúc Ly (Ly), got {chars_map['LAN']['voice']}"
    assert stats["segment_count"] == 92, f"Must have 92 segments, got {stats['segment_count']}"
    print("Stats:", stats)

    # Test clean_text_for_tts
    sample_txt = "[thở dài] Nếu chồng tôi nghe được lá thư này... [quiet_confession]"
    cleaned = clean_text_for_tts(sample_txt)
    print("Clean text test:")
    print("  Original:", sample_txt)
    print("  Cleaned: ", cleaned)
    assert "[thở dài]" in cleaned, "Native tag [thở dài] must be kept"
    assert "[quiet_confession]" not in cleaned, "Metadata tag [quiet_confession] must be removed"
    print("✅ All validation tests passed!")

if __name__ == "__main__":
    test_validation()
