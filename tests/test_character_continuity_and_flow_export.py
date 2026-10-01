"""Tests for Character Continuity Resolver and SCC_FLOW_V1 Export Hardening.

Verifies:
1. Character Continuity Resolver after Scene Generation:
   - Analyzes narration_summary, segment texts, prompts
   - Matches existing characters from Character Library
   - Automatically populates visible_characters[] and character_refs_required[]
2. Never allows an existing story character to disappear when mentioned (Thủy, Bà Mai, Quân, Hoàng, etc.)
3. Dependency validation before export:
   - If scene contains human subject and character_refs_required is empty -> generation_dependencies_satisfied=False & warning
4. Export JSON contains resolved character dependency:
   - character_id, name, reference_required, reference_media_id
5. Does not declare GOOGLE_FLOW_EXPORT_READY until all human scenes have character references resolved
6. Ensures 100% scene continuity across episodes
"""
import json
from pathlib import Path
import pytest

from apps.visual_engine.character_continuity_resolver import (
    CharacterContinuityResolver,
    is_human_scene,
)
from apps.visual_pilot_03_v1_0a.google_flow_exporter import (
    SCHEMA_VERSION,
    build_episode_export,
    export_episode_flow_json,
    validate_flow_export,
)


def test_character_matching_generic_and_exact():
    characters = [
        {"character_id": "CHAR_THUY", "name": "Nguyễn Thị Thủy", "gender": "FEMALE", "role": "Nhân vật chính", "description": "Vợ của Quân"},
        {"character_id": "CHAR_BA_MAI", "name": "Bà Lê Thị Mai", "gender": "FEMALE", "role": "Mẹ chồng / Người nắm giữ bí mật", "description": "Mẹ chồng cô"},
        {"character_id": "CHAR_QUAN", "name": "Trần Minh Quân", "gender": "MALE", "role": "Chồng Thủy", "description": "Chồng của Thủy"},
        {"character_id": "CHAR_HOANG", "name": "Trần Minh Hoàng", "gender": "MALE", "role": "Em chồng", "description": "Em trai Quân"},
    ]
    resolver = CharacterContinuityResolver(characters)

    # 1. Given names
    assert resolver.match_characters_in_text("Thủy ngồi bên bàn làm việc.") == ["CHAR_THUY"]
    assert resolver.match_characters_in_text("Quân bước vào phòng nhìn vợ.") == ["CHAR_THUY", "CHAR_QUAN"]
    assert resolver.match_characters_in_text("Hoàng lắp bắp không nên lời.") == ["CHAR_HOANG"]

    # 2. Honorifics and compound names
    assert "CHAR_BA_MAI" in resolver.match_characters_in_text("Bà Mai lặng lẽ rời nhà khi trời tối.")
    assert "CHAR_QUAN" in resolver.match_characters_in_text("Minh Quân đứng nhìn ra cửa sổ.")
    assert "CHAR_HOANG" in resolver.match_characters_in_text("Minh Hoàng cúi đầu im lặng.")

    # 3. Kinship terms
    assert "CHAR_BA_MAI" in resolver.match_characters_in_text("Thủy tìm thấy cuốn sổ của mẹ chồng.")
    assert "CHAR_HOANG" in resolver.match_characters_in_text("Món nợ lớn của em chồng khiến cả nhà lo lắng.")

    # 4. Negative false-positive protection (e.g. "ngày mai", "quân đội", "huy hoàng")
    assert "CHAR_BA_MAI" not in resolver.match_characters_in_text("Hôm nay và ngày mai chúng ta sẽ thảo luận.")
    assert "CHAR_QUAN" not in resolver.match_characters_in_text("Lực lượng quân đội luôn sẵn sàng bảo vệ tổ quốc.")
    assert "CHAR_HOANG" not in resolver.match_characters_in_text("Ánh hào quang huy hoàng của quá khứ.")


def test_character_continuity_across_scenes():
    characters = [
        {"character_id": "CHAR_THUY", "name": "Nguyễn Thị Thủy", "gender": "FEMALE", "role": "Nhân vật chính", "requires_approval": True},
        {"character_id": "CHAR_BA_MAI", "name": "Bà Lê Thị Mai", "gender": "FEMALE", "role": "Mẹ chồng", "requires_approval": True},
        {"character_id": "CHAR_QUAN", "name": "Trần Minh Quân", "gender": "MALE", "role": "Chồng Thủy", "requires_approval": True},
    ]
    resolver = CharacterContinuityResolver(characters)

    raw_scenes = [
        {
            "scene_id": "SC_001",
            "order": 1,
            "narration_summary": "Thủy viết một lá thư kể về sự việc bất thường trong gia đình.",
            "image_prompt": "Vietnamese woman 32 sitting at a desk, natural light",
            "visible_characters": [],
        },
        {
            "scene_id": "SC_002",
            "order": 2,
            # No name explicitly mentioned, but pronoun 'Cô' and human presence
            "narration_summary": "Cô nhận thấy không khí trong căn nhà cổ ngày một trở nên ngột ngạt.",
            "image_prompt": "Vietnamese documentary scene capturing restrained human emotion inside traditional home",
            "visible_characters": [],
        },
        {
            "scene_id": "SC_003",
            "order": 3,
            "narration_summary": "Bà Mai và Quân đứng đối diện nhau trong phòng khách.",
            "image_prompt": "Two Vietnamese family members in confrontation",
            "visible_characters": [],
        },
    ]

    resolved = resolver.resolve_scenes(raw_scenes)

    # SC_001 has Thủy
    assert "CHAR_THUY" in resolved[0]["visible_characters"]
    assert "CHAR_THUY" in resolved[0]["character_refs_required"]

    # SC_002 preserves character continuity (Thủy from pronoun 'Cô' and active continuity)
    assert "CHAR_THUY" in resolved[1]["visible_characters"]
    assert len(resolved[1]["character_refs_required"]) > 0

    # SC_003 has Bà Mai and Quân
    assert "CHAR_BA_MAI" in resolved[2]["visible_characters"]
    assert "CHAR_QUAN" in resolved[2]["visible_characters"]

    # All resolved scenes have character_dependencies matching contract
    for sc in resolved:
        assert "character_dependencies" in sc
        for dep in sc["character_dependencies"]:
            assert "character_id" in dep
            assert "name" in dep
            assert "reference_required" in dep
            assert "reference_media_id" in dep


def test_human_scene_dependency_validation_blocks_unresolved():
    export_package = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "series": "Sau Cánh Cửa",
            "production_id": "EP_TEST",
            "export_status": "GOOGLE_FLOW_EXPORT_READY"
        },
        "episodes": [{
            "episode_id": "EP_TEST",
            "title": "Test Episode",
            "audio_duration": 30.0,
            "characters": [
                {"character_id": "CHAR_A", "name": "Nguyễn Văn A", "reference_required": True, "reference_media_id": None}
            ],
            "props": [],
            "locations": [],
            "overlays": [],
            "scenes": [
                {
                    "scene_id": "SC_001",
                    "order": 1,
                    "start_time": 0.0,
                    "end_time": 30.0,
                    "duration": 30.0,
                    "visual_mode": "IMAGE_ONLY",
                    "narration_summary": "Người đàn ông đứng nhìn ra ban công vào một đêm mưa lạnh.",
                    "image_prompt": "Cinematic portrait of a 35-year-old Vietnamese man standing near the balcony, natural light, 16:9",
                    "video_prompt": None,
                    "visible_characters": [],  # UNRESOLVED human scene!
                    "character_refs_required": [],
                    "character_dependencies": [],
                    "image_media_id": None,
                    "video_media_id": None,
                    "generation_dependencies_satisfied": False,
                }
            ]
        }]
    }

    is_valid, errors = validate_flow_export(export_package)

    # Must fail validation and block GOOGLE_FLOW_EXPORT_READY
    assert is_valid is False
    assert export_package["project"]["export_status"] == "BLOCKED_QC"
    assert any("contains human subject" in err for err in errors)


def test_ep10001_export_continuity_and_dependencies():
    # Build export for EP10001
    pkg = export_episode_flow_json("EP10001")
    assert pkg["status"] == "PASS"
    assert pkg["validation_status"] == "GOOGLE_FLOW_EXPORT_READY"

    export_path = Path("production_pilot_03_visual_v1_0a/exports/EP10001_google_flow.json")
    assert export_path.exists()
    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ep = data["episodes"][0]
    scenes = ep["scenes"]

    # Verify zero character loss on scenes mentioned in prompt
    sc_001 = next(s for s in scenes if s["scene_id"] == "SC_001")
    sc_002 = next(s for s in scenes if s["scene_id"] == "SC_002")
    sc_006 = next(s for s in scenes if s["scene_id"] == "SC_006")
    sc_007 = next(s for s in scenes if s["scene_id"] == "SC_007")
    sc_041 = next(s for s in scenes if s["scene_id"] == "SC_041")
    sc_045 = next(s for s in scenes if s["scene_id"] == "SC_045")

    assert len(sc_001["visible_characters"]) > 0
    assert len(sc_001["character_refs_required"]) > 0
    assert len(sc_002["visible_characters"]) > 0
    assert len(sc_002["character_refs_required"]) > 0
    assert len(sc_006["visible_characters"]) > 0
    assert len(sc_006["character_refs_required"]) > 0
    assert len(sc_007["visible_characters"]) > 0
    assert len(sc_007["character_refs_required"]) > 0
    assert len(sc_041["visible_characters"]) > 0
    assert len(sc_041["character_refs_required"]) > 0
    assert len(sc_045["visible_characters"]) > 0
    assert len(sc_045["character_refs_required"]) > 0

    # Every scene has character dependencies populated with required keys
    for sc in scenes:
        assert isinstance(sc["character_dependencies"], list)
        for dep in sc["character_dependencies"]:
            assert "character_id" in dep
            assert "name" in dep
            assert "reference_required" in dep
            assert "reference_media_id" in dep
