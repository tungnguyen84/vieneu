import json
import os
import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.script_factory.models import IdeaItem, ApprovalStatus
from apps.script_factory.providers.mock_provider import MockScriptAIProvider
from apps.script_factory.providers.router import ModelRouter, RouterConfig
from apps.script_factory.idea_generator import IdeaGenerator
from apps.script_factory.cost_control import CostController
from apps.ui_script_factory import IDEA_TABLE_HEADERS, _render_provider_status_md


def test_series_bible_has_exactly_6_delivery_profiles():
    bible_path = Path("script_factory/series_bible.json")
    assert bible_path.exists()
    with open(bible_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    profiles = data["delivery_profiles"]
    expected = {"HOOK", "NORMAL", "MYSTERY", "REVEAL", "COMMENT", "ENDING"}
    assert set(profiles.keys()) == expected
    assert len(profiles) == 6


def test_mock_provider_blocks_real_pilot(tmp_path):
    cost_ctrl = CostController(log_file=tmp_path / "gen_log.jsonl")
    mock_prov = MockScriptAIProvider()
    idea_gen = IdeaGenerator(provider=mock_prov, cost_controller=cost_ctrl, idea_bank_file=tmp_path / "bank.json")

    with pytest.raises(RuntimeError) as exc_info:
        idea_gen.generate_batch(count=20, is_pilot=True)
    assert "MOCK PROVIDER — NOT FOR PRODUCTION" in str(exc_info.value)


def test_provider_status_reporting():
    router = ModelRouter(config=RouterConfig(preferred_provider="mock"))
    st = router.get_connection_status()
    assert "provider" in st
    assert "model" in st
    assert "status" in st


def test_idea_table_headers_has_20_required_fields():
    expected = [
        "ID", "Working Title", "Hook", "Protagonist", "Relationship",
        "Central Secret", "Mystery Question", "False Lead", "Clue 1", "Clue 2", "Clue 3",
        "Reveal 1", "Reveal 2", "Emotional Payoff", "Reflection Theme",
        "Hook Archetype", "Twist Archetype", "Novelty", "Closest Episode", "Status"
    ]
    assert IDEA_TABLE_HEADERS == expected
    assert len(IDEA_TABLE_HEADERS) == 20


def test_idea_item_has_diagnostic_fields():
    item = IdeaItem(
        idea_id="IDEA_TEST",
        working_title="T",
        hook="H",
        protagonist="P",
        relationship="R",
        central_secret="S",
        mystery_question="Q",
        false_lead="FL",
        clue_1="C1", clue_2="C2", clue_3="C3",
        reveal_1="R1", reveal_2="R2",
        emotional_payoff="EP",
        reflection_theme="RT",
        hook_archetype="HA",
        twist_archetype="TA",
        curiosity=9.0,
        emotional_potential=8.5,
        mystery_potential=8.0,
        logical_plausibility=9.5,
        long_form_potential=8.8,
    )
    d = item.to_dict()
    assert d["curiosity"] == 9.0
    assert d["logical_plausibility"] == 9.5


def test_pilot_01_report_file_integrity():
    report_path = Path("reports/script_factory_pilot_01.json")
    if not report_path.exists():
        pytest.skip("Pilot 01 report not found")

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["pilot"] == "PILOT_01"
    assert data["provider"] == "GEMINI"
    ideas = data["ideas"]
    assert len(ideas) == 20

    ids = [i["idea_id"] for i in ideas]
    expected_ids = [f"IDEA_{idx:03d}" for idx in range(2, 22)]
    assert ids == expected_ids

    import collections
    hooks = collections.Counter([i["hook_archetype"] for i in ideas])
    twists = collections.Counter([i["twist_archetype"] for i in ideas])

    # Section 7: Min 8 unique hooks, max 3 per hook
    assert len(hooks) >= 8, f"Unique hooks {len(hooks)} < 8"
    assert max(hooks.values()) <= 3, f"Max hook {max(hooks.values())} > 3"

    # Section 8: Min 6 unique twists, max 4 per twist
    assert len(twists) >= 6, f"Unique twists {len(twists)} < 6"
    assert max(twists.values()) <= 4, f"Max twist {max(twists.values())} > 4"

    # Section 10: All novelty scores >= 60.0
    for i in ideas:
        assert i["novelty_score"] >= 60.0, f"{i['idea_id']} novelty {i['novelty_score']} < 60.0"
        assert i["status"] == "AWAITING_USER_REVIEW"

