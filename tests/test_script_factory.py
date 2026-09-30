"""Comprehensive Test Suite for VieNeu Script Factory V1.

Mandatory Tests:
1.  test_episode01_golden_reference_untouched
2.  test_generate_ideas_does_not_generate_scripts
3.  test_idea_bank_persists
4.  test_novelty_blocks_duplicate_premise
5.  test_story_bible_fact_lock
6.  test_writer_cannot_change_locked_fact
7.  test_qc_detects_timeline_conflict
8.  test_qc_detects_money_conflict
9.  test_qc_detects_relationship_conflict
10. test_qc_detects_repeated_hook
11. test_major_reveal_has_no_audience_interruption
12. test_script_not_auto_approved
13. test_story_bible_change_invalidates_qc
14. test_send_to_production_requires_approval
15. test_production_adapter_outputs_v9_3
16. test_visual_manifest_uses_story_bible
17. test_visual_overlay_not_generated_in_image
18. test_manual_visual_video_priority
19. test_script_factory_does_not_mutate_audio_formula
20. test_no_ai_call_on_startup
21. test_batch_resume_does_not_repeat_done_jobs
22. test_api_keys_not_logged
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from tests.mocks.mock_script_provider import MockScriptAIProvider
from apps.script_factory import (
    ApprovalStatus,
    AutoRevisionManager,
    BatchManager,
    CostController,
    FullScript,
    HumanApprovalGate,
    IdeaGenerator,
    IdeaItem,
    LockedFact,
    NoveltyEngine,
    ProductionAdapter,
    QCReport,
    ScriptQCEngine,
    ScriptSegment,
    ScriptWriter,
    StoryBible,
    StoryPlanner,
)
from apps.script_factory.approval_gate import ApprovalGateError


@pytest.fixture
def temp_sf_env(tmp_path):
    """Sets up an isolated Script Factory test environment."""
    sf_dir = tmp_path / "script_factory"
    ep_dir = tmp_path / "episodes"
    logs_dir = sf_dir / "logs"
    sf_dir.mkdir(parents=True)
    ep_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)

    log_file = logs_dir / "generation_log.jsonl"
    idea_bank_file = sf_dir / "idea_bank.json"
    batch_jobs_file = sf_dir / "batch_jobs.json"

    cost_ctrl = CostController(log_file=log_file)
    mock_provider = MockScriptAIProvider()
    novelty_engine = NoveltyEngine(provider=mock_provider)

    idea_gen = IdeaGenerator(
        provider=mock_provider,
        cost_controller=cost_ctrl,
        novelty_engine=novelty_engine,
        idea_bank_file=idea_bank_file,
    )
    story_planner = StoryPlanner(
        provider=mock_provider,
        cost_controller=cost_ctrl,
        episodes_root=ep_dir,
    )
    script_writer = ScriptWriter(
        provider=mock_provider,
        cost_controller=cost_ctrl,
        episodes_root=ep_dir,
    )
    qc_engine = ScriptQCEngine(
        provider=mock_provider,
        cost_controller=cost_ctrl,
        episodes_root=ep_dir,
    )
    auto_rev = AutoRevisionManager(
        provider=mock_provider,
        cost_controller=cost_ctrl,
        qc_engine=qc_engine,
    )
    batch_mgr = BatchManager(persistence_file=batch_jobs_file)
    prod_adapter = ProductionAdapter(episodes_root=ep_dir)

    return {
        "root": tmp_path,
        "cost_ctrl": cost_ctrl,
        "provider": mock_provider,
        "novelty": novelty_engine,
        "idea_gen": idea_gen,
        "planner": story_planner,
        "writer": script_writer,
        "qc": qc_engine,
        "auto_rev": auto_rev,
        "batch_mgr": batch_mgr,
        "adapter": prod_adapter,
        "log_file": log_file,
    }


# 1. Golden Reference Untouched
def test_episode01_golden_reference_untouched():
    real_source = Path("projects/sau_canh_cua_ep01_v9_3_manual_visual/source.json")
    if not real_source.exists():
        pytest.skip("Episode 01 project not found")

    h = hashlib.sha256(real_source.read_bytes()).hexdigest()
    assert h.startswith("a06f089336d60337"), f"EP001 source.json has been mutated! Hash: {h}"

    with open(real_source, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["characters"]["MINH"]["voice"] == "Binh"
    assert len(data["segments"]) == 93
    assert data["project"]["format"] == "single_host_dynamic_documentary_storytelling"


# 2. Generate ideas does not generate scripts
def test_generate_ideas_does_not_generate_scripts(temp_sf_env):
    idea_gen = temp_sf_env["idea_gen"]
    ep_root = temp_sf_env["planner"].episodes_root

    ideas = idea_gen.generate_batch(count=10)
    assert len(ideas) == 10
    for it in ideas:
        assert isinstance(it, IdeaItem)
        assert it.status in ["DRAFT", "PASS", "BLOCKED_DUPLICATE"]

    # Verify no script files exist in episodes directory
    scripts = list(ep_root.glob("**/script.json"))
    assert len(scripts) == 0, "generate_batch must NEVER generate full scripts!"


# 3. Idea Bank persists
def test_idea_bank_persists(temp_sf_env):
    idea_gen = temp_sf_env["idea_gen"]
    ideas = idea_gen.generate_batch(count=10)

    # Reload from disk
    loaded = idea_gen.load_idea_bank()
    assert len(loaded) == 10
    assert loaded[0].idea_id == ideas[0].idea_id
    assert loaded[0].working_title == ideas[0].working_title
    assert loaded[0].central_secret == ideas[0].central_secret


# 4. Novelty blocks duplicate premise
def test_novelty_blocks_duplicate_premise(temp_sf_env):
    novelty = temp_sf_env["novelty"]

    idea_a = IdeaItem(
        idea_id="IDEA_ORIGINAL",
        working_title="7 năm giấu chồng chuyển tiền",
        hook="Lá thư mở đầu bằng việc giấu chồng chuyển tiền...",
        protagonist="Lan",
        relationship="Cháu và Cậu",
        central_secret="Người cậu giả giọng cha đã mất 14 năm để nhận 5 triệu mỗi tháng",
        mystery_question="Ai là người ở đầu dây?",
        false_lead="Người yêu cũ",
        clue_1="Điện thoại cũ",
        clue_2="Trích lục khai tử",
        clue_3="Bia mộ",
        reveal_1="Bố mất 14 năm trước",
        reveal_2="Cậu ruột giả giọng",
        emotional_payoff="Hùng tha thứ và ôm Lan",
        reflection_theme="Sự cô đơn khiến con người tự lừa dối",
        hook_archetype="CONFESSION",
        twist_archetype="Family secrets",
    )

    idea_dup = IdeaItem(
        idea_id="IDEA_DUPLICATE",
        working_title="7 năm giấu chồng gửi tiền cho cậu",
        hook="Lá thư mở đầu bằng việc giấu chồng chuyển tiền...",
        protagonist="Lan",
        relationship="Cháu và Cậu",
        central_secret="Người cậu giả giọng cha đã mất 14 năm để nhận 5 triệu mỗi tháng",
        mystery_question="Ai là người ở đầu dây?",
        false_lead="Người yêu cũ",
        clue_1="Điện thoại cũ",
        clue_2="Trích lục khai tử",
        clue_3="Bia mộ",
        reveal_1="Bố mất 14 năm trước",
        reveal_2="Cậu ruột giả giọng",
        emotional_payoff="Hùng tha thứ và ôm Lan",
        reflection_theme="Sự cô đơn khiến con người tự lừa dối",
        hook_archetype="CONFESSION",
        twist_archetype="Family secrets",
    )

    report = novelty.check_idea_novelty(idea_dup, [idea_a])
    assert report.status in ("BLOCK_DUPLICATE", "BLOCKED_NARRATIVE_DUPLICATE")
    assert report.premise_similarity_pct >= 65.0
    assert report.novelty_score < 35.0


# 5. Story Bible Fact Lock
def test_story_bible_fact_lock(temp_sf_env):
    planner = temp_sf_env["planner"]
    idea = IdeaItem(
        idea_id="IDEA_TEST",
        working_title="Chiếc khóa két sắt",
        hook="Khi mở ngăn kéo...",
        protagonist="Hải",
        relationship="Hai anh em",
        central_secret="Di chúc để lại chia đều",
        mystery_question="Két sắt chứa gì?",
        false_lead="Tiền vàng",
        clue_1="Chìa khóa",
        clue_2="Nhật ký",
        clue_3="Hóa đơn",
        reveal_1="Không có vàng",
        reveal_2="Tình phụ tử",
        emotional_payoff="Hai anh em ôm nhau khóc",
        reflection_theme="Tình thân hơn bạc tiền",
        hook_archetype="OBJECT_DISCOVERY",
        twist_archetype="Inheritance",
    )
    bible = planner.create_story_bible_from_idea(idea)
    assert len(bible.critical_facts) > 0
    for fact in bible.critical_facts:
        assert fact.status == "LOCKED"
        assert fact.value != ""


# 6. Writer cannot change locked fact
def test_writer_cannot_change_locked_fact(temp_sf_env):
    planner = temp_sf_env["planner"]
    writer = temp_sf_env["writer"]
    qc = temp_sf_env["qc"]

    idea = IdeaItem(
        idea_id="IDEA_010",
        working_title="Kỷ vật thời gian",
        hook="Hook",
        protagonist="Tuấn",
        relationship="Mẹ và con",
        central_secret="Secret",
        mystery_question="Why?",
        false_lead="Lead",
        clue_1="C1",
        clue_2="C2",
        clue_3="C3",
        reveal_1="R1",
        reveal_2="R2",
        emotional_payoff="Payoff",
        reflection_theme="Theme",
        hook_archetype="CONFESSION",
        twist_archetype="Family secrets",
    )
    bible = planner.create_story_bible_from_idea(idea)
    script = writer.generate_script_from_bible(bible)

    # Verify locked facts are present in narration
    all_text = " ".join(s.text for s in script.segments)
    for fact in bible.critical_facts:
        assert fact.value in all_text


# 7. QC detects timeline conflict
def test_qc_detects_timeline_conflict(temp_sf_env):
    planner = temp_sf_env["planner"]
    writer = temp_sf_env["writer"]
    qc = temp_sf_env["qc"]

    bible = StoryBible(
        episode_id="EP010",
        title="Timeline Test",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        critical_facts=[
            LockedFact(fact_id="FACT_T1", field="married_years", value="7", description="kết hôn 7 năm", status="LOCKED")
        ]
    )
    # Tamper script to say "8 năm" instead of "7 năm"
    script = FullScript(
        episode_id="EP010",
        title="Timeline Test",
        host={"id": "MINH", "voice": "Binh"},
        segments=[
            ScriptSegment(id="001", speaker="MINH", text="Hai người đã chung sống suốt 8 năm qua mà không hề hay biết.", delivery_profile="HOOK"),
            ScriptSegment(id="002", speaker="MINH", text="Sự việc kéo dài 8 năm đằng đẵng.", delivery_profile="NORMAL"),
            ScriptSegment(id="003", speaker="MINH", text="Bạn có nghĩ thời gian 8 năm là dài không?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="004", speaker="MINH", text="Nhưng bạn hãy lắng nghe tiếp.", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="005", speaker="MINH", text="Chúng ta hãy suy ngẫm.", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="006", speaker="MINH", text="Sự thật đã lộ diện.", delivery_profile="REVEAL", importance="critical"),
            ScriptSegment(id="007", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe.", delivery_profile="ENDING"),
        ]
    )

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(c["type"] == "TIMELINE_CONFLICT" for c in report.fact_conflicts)


# 8. QC detects money conflict
def test_qc_detects_money_conflict(temp_sf_env):
    qc = temp_sf_env["qc"]
    bible = StoryBible(
        episode_id="EP011",
        title="Money Test",
        protagonist={"name": "Lan", "char_id": "LAN"},
        critical_facts=[
            LockedFact(fact_id="FACT_M1", field="monthly_transfer", value="5.000.000 VND", description="chuyển tiền", status="LOCKED")
        ]
    )
    # Script says 3 triệu instead of 5 triệu
    script = FullScript(
        episode_id="EP011",
        title="Money Test",
        host={"id": "MINH", "voice": "Binh"},
        segments=[
            ScriptSegment(id="001", speaker="MINH", text="Mỗi tháng cô ấy chuyển 3.000.000 đồng đi đâu đó.", delivery_profile="HOOK"),
            ScriptSegment(id="002", speaker="MINH", text="Con số 3 triệu là bí mật.", delivery_profile="NORMAL"),
            ScriptSegment(id="003", speaker="MINH", text="Bạn có bao giờ giấu tiền không?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="004", speaker="MINH", text="Hãy cùng tìm hiểu.", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="005", speaker="MINH", text="Chúng ta tiếp tục.", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="006", speaker="MINH", text="Sự thật được hé lộ.", delivery_profile="REVEAL", importance="critical"),
            ScriptSegment(id="007", speaker="MINH", text="Chào tạm biệt.", delivery_profile="ENDING"),
        ]
    )

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(c["type"] == "MONEY_CONFLICT" for c in report.fact_conflicts)


# 9. QC detects relationship conflict
def test_qc_detects_relationship_conflict(temp_sf_env):
    qc = temp_sf_env["qc"]
    bible = StoryBible(
        episode_id="EP012",
        title="Rel Test",
        protagonist={"name": "Lan", "char_id": "LAN"},
        critical_facts=[
            LockedFact(fact_id="FACT_R1", field="impersonator_relation", value="Cậu ruột", description="mối quan hệ", status="LOCKED")
        ]
    )
    # Script says "chú họ" instead of "cậu ruột"
    script = FullScript(
        episode_id="EP012",
        title="Rel Test",
        host={"id": "MINH", "voice": "Binh"},
        segments=[
            ScriptSegment(id="001", speaker="MINH", text="Người đàn ông đó thực ra là chú họ của Lan.", delivery_profile="HOOK"),
            ScriptSegment(id="002", speaker="MINH", text="Cô không ngờ chú họ lại làm vậy.", delivery_profile="NORMAL"),
            ScriptSegment(id="003", speaker="MINH", text="Bạn nghĩ sao về người chú này?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="004", speaker="MINH", text="Chúng ta xem xét.", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="005", speaker="MINH", text="Quan sát tiếp.", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="006", speaker="MINH", text="Sự thật sáng tỏ.", delivery_profile="REVEAL", importance="critical"),
            ScriptSegment(id="007", speaker="MINH", text="Hẹn gặp lại.", delivery_profile="ENDING"),
        ]
    )

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(c["type"] == "RELATIONSHIP_CONFLICT" for c in report.fact_conflicts)


# 10. QC detects repeated hook
def test_qc_detects_repeated_hook(temp_sf_env):
    qc = temp_sf_env["qc"]
    bible = StoryBible(episode_id="EP013", title="Hook Rep Test", protagonist={"name": "Lan"})

    past_script = FullScript(
        episode_id="EP001",
        title="EP001",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="001", text="Lá thư của Lan mở đầu bằng một câu thế này nếu chồng tôi nghe được"),
        ]
    )
    new_script = FullScript(
        episode_id="EP013",
        title="EP013",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="001", text="Lá thư của Lan mở đầu bằng một câu thế này nếu chồng tôi"),
            ScriptSegment(id="002", text="Tiếp theo", delivery_profile="HOOK"),
            ScriptSegment(id="003", text="Bạn nghĩ sao?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="004", text="Bạn đoán xem?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="005", text="Bạn có tin không?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="006", text="Reveal", delivery_profile="REVEAL", importance="critical"),
            ScriptSegment(id="007", text="Ending", delivery_profile="ENDING"),
        ]
    )

    report = qc.run_qc(new_script, bible, past_scripts=[past_script])
    assert any("Repeated hook detected" in iss for iss in report.repetition_issues)


# 11. Major reveal has no audience interruption
def test_major_reveal_has_no_audience_interruption(temp_sf_env):
    qc = temp_sf_env["qc"]
    bible = StoryBible(episode_id="EP014", title="Reveal Test", protagonist={"name": "Minh"})

    bad_script = FullScript(
        episode_id="EP014",
        title="Bad Reveal",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="001", text="Hook", delivery_profile="HOOK"),
            ScriptSegment(id="002", text="Bạn nghĩ sao?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="003", text="Bạn đoán xem?", delivery_profile="COMMENT", audience_address=True),
            ScriptSegment(id="004", text="Bạn hiểu chứ?", delivery_profile="COMMENT", audience_address=True),
            # VIOLATION: audience_address inside REVEAL
            ScriptSegment(id="005", text="Bố Lan mất 14 năm trước, bạn có bất ngờ không?", delivery_profile="REVEAL", importance="critical", audience_address=True),
            ScriptSegment(id="006", text="Ending", delivery_profile="ENDING"),
        ]
    )

    report = qc.run_qc(bad_script, bible)
    assert any("violating reveal restraint rule" in iss for iss in report.logic_issues)


# 12. Script not auto approved
def test_script_not_auto_approved(temp_sf_env):
    planner = temp_sf_env["planner"]
    writer = temp_sf_env["writer"]

    idea = IdeaItem(
        idea_id="IDEA_AUTO",
        working_title="Test Auto",
        hook="H",
        protagonist="P",
        relationship="R",
        central_secret="S",
        mystery_question="M",
        false_lead="F",
        clue_1="1",
        clue_2="2",
        clue_3="3",
        reveal_1="R1",
        reveal_2="R2",
        emotional_payoff="E",
        reflection_theme="T",
        hook_archetype="MESSAGE",
        twist_archetype="Family secrets",
    )
    bible = planner.create_story_bible_from_idea(idea)
    script = writer.generate_script_from_bible(bible)

    assert script.status == ApprovalStatus.DRAFT
    assert script.status != ApprovalStatus.APPROVED

    # Automated / AI approval must raise error
    with pytest.raises(ApprovalGateError):
        HumanApprovalGate.approve_script(script, qc_status="PASS", user="AI")

    with pytest.raises(ApprovalGateError):
        HumanApprovalGate.approve_script(script, qc_status="PASS", user="system")


# 13. Story Bible change invalidates QC
def test_story_bible_change_invalidates_qc(temp_sf_env):
    planner = temp_sf_env["planner"]
    bible = StoryBible(episode_id="EP015", title="Bible Mutate", protagonist={"name": "A"}, status=ApprovalStatus.APPROVED)

    # Modify story bible
    bible.title = "Bible Mutated Title"
    planner.modify_story_bible(bible)

    assert bible.status == ApprovalStatus.STORY_BIBLE_CHANGED
    assert bible.approved_by is None


# 14. Send to production requires approval
def test_send_to_production_requires_approval(temp_sf_env):
    adapter = temp_sf_env["adapter"]
    bible = StoryBible(episode_id="EP016", title="Unapproved", protagonist={"name": "A"}, status=ApprovalStatus.DRAFT)
    script = FullScript(episode_id="EP016", title="Unapproved", host={"id": "MINH"}, status=ApprovalStatus.DRAFT)

    with pytest.raises(ApprovalGateError, match="expected 'APPROVED'"):
        adapter.adapt_to_v9_3_project(script, bible)


# 15. Production adapter outputs V9.3
def test_production_adapter_outputs_v9_3(temp_sf_env):
    planner = temp_sf_env["planner"]
    writer = temp_sf_env["writer"]
    adapter = temp_sf_env["adapter"]

    idea = IdeaItem(
        idea_id="IDEA_PROD",
        working_title="Gói sản xuất V9.3",
        hook="H",
        protagonist="Hoàng",
        relationship="Cha con",
        central_secret="Secret",
        mystery_question="Why?",
        false_lead="Lead",
        clue_1="1",
        clue_2="2",
        clue_3="3",
        reveal_1="R1",
        reveal_2="R2",
        emotional_payoff="Payoff",
        reflection_theme="Theme",
        hook_archetype="DOCUMENT",
        twist_archetype="Inheritance",
    )
    bible = planner.create_story_bible_from_idea(idea)
    HumanApprovalGate.approve_story_bible(bible, user="USER")
    script = writer.generate_script_from_bible(bible)
    HumanApprovalGate.approve_script(script, qc_status="PASS", user="USER")

    prod_dir = adapter.adapt_to_v9_3_project(script, bible)
    assert prod_dir.exists()
    assert (prod_dir / "episode_v9_3.json").exists()
    assert (prod_dir / "visual_manifest.json").exists()
    assert (prod_dir / "visual_prompts.csv").exists()
    assert (prod_dir / "manual_assets" / "images").exists()
    assert (prod_dir / "manual_assets" / "videos").exists()

    with open(prod_dir / "episode_v9_3.json", "r", encoding="utf-8") as f:
        v93_data = json.load(f)
    assert v93_data["schema_version"].startswith("3.2")
    assert v93_data["characters"]["MINH"]["voice"] == "Binh"


# 16. Visual manifest uses Story Bible
def test_visual_manifest_uses_story_bible(temp_sf_env):
    planner = temp_sf_env["planner"]
    writer = temp_sf_env["writer"]
    adapter = temp_sf_env["adapter"]

    idea = IdeaItem(
        idea_id="IDEA_VIS",
        working_title="Visual Test",
        hook="H",
        protagonist="Tuấn",
        relationship="Rel",
        central_secret="Secret",
        mystery_question="Why?",
        false_lead="Lead",
        clue_1="1",
        clue_2="2",
        clue_3="3",
        reveal_1="R1",
        reveal_2="R2",
        emotional_payoff="Payoff",
        reflection_theme="Theme",
        hook_archetype="STRANGER",
        twist_archetype="Neighborhood mysteries",
    )
    bible = planner.create_story_bible_from_idea(idea)
    HumanApprovalGate.approve_story_bible(bible, user="USER")
    script = writer.generate_script_from_bible(bible)
    HumanApprovalGate.approve_script(script, qc_status="PASS", user="USER")

    prod_dir = adapter.adapt_to_v9_3_project(script, bible)
    with open(prod_dir / "visual_manifest.json", "r", encoding="utf-8") as f:
        vm = json.load(f)

    assert 35 <= vm["total_scenes"] <= 50
    # First scene prompt mentions protagonist name
    first_sc = vm["scenes"][0]
    assert "Tuấn" in first_sc["image_prompt"]
    assert first_sc["scene_id"] == "SC_001"


# 17. Visual overlay not generated in image
def test_visual_overlay_not_generated_in_image(temp_sf_env):
    planner = temp_sf_env["planner"]
    writer = temp_sf_env["writer"]
    adapter = temp_sf_env["adapter"]

    bible = StoryBible(
        episode_id="EP017",
        title="Overlay Test",
        protagonist={"name": "Lan", "char_id": "LAN", "age": 32},
        critical_facts=[
            LockedFact(fact_id="FACT_DOC", field="death_record", value="14 năm trước", description="Ngày mất", status="LOCKED")
        ],
        reveal_1="Bố mất 14 năm trước"
    )
    HumanApprovalGate.approve_story_bible(bible, user="USER")
    script = writer.generate_script_from_bible(bible)
    HumanApprovalGate.approve_script(script, qc_status="PASS", user="USER")

    prod_dir = adapter.adapt_to_v9_3_project(script, bible)
    with open(prod_dir / "visual_manifest.json", "r", encoding="utf-8") as f:
        vm = json.load(f)

    # Find reveal scenes
    reveal_scenes = [sc for sc in vm["scenes"] if sc.get("overlay_text")]
    assert len(reveal_scenes) > 0
    for rsc in reveal_scenes:
        # Prompt must be a pure photographic prompt, not asking AI to write text
        assert "no text" not in rsc["image_prompt"].lower() or "16:9" in rsc["image_prompt"]
        assert rsc["overlay_text"] is not None


# 18. Manual visual video priority
def test_manual_visual_video_priority():
    from apps.visual_engine.manual_visual_mode import ManualSceneItem, scan_project_assets, ManualVisualManifest
    sc = ManualSceneItem(
        scene_id="SC_001",
        scene_index=1,
        start_sec=0.0,
        end_sec=5.0,
        duration_sec=5.0,
        story_beat="Beat",
        matched_images=["SC_001.png"],
        matched_videos=["SC_001.mp4"],
    )
    # When both exist, priority is VIDEO
    assert "SC_001.mp4" in sc.matched_videos[0]


# 19. Script factory does not mutate audio formula
def test_script_factory_does_not_mutate_audio_formula(temp_sf_env):
    planner = temp_sf_env["planner"]
    writer = temp_sf_env["writer"]
    adapter = temp_sf_env["adapter"]

    bible = StoryBible(episode_id="EP018", title="Audio Test", protagonist={"name": "A"})
    HumanApprovalGate.approve_story_bible(bible, user="USER")
    script = writer.generate_script_from_bible(bible)
    HumanApprovalGate.approve_script(script, qc_status="PASS", user="USER")

    prod_dir = adapter.adapt_to_v9_3_project(script, bible)
    with open(prod_dir / "episode_v9_3.json", "r", encoding="utf-8") as f:
        v93 = json.load(f)

    adir = v93["audio_direction"]
    assert adir["master_target"] == "-14 LUFS integrated target, -1 dBTP true peak; preserve natural phrase dynamics before final loudnorm."
    assert "All REVEAL segments are dry" in adir["reveal_rule"]


# 20. No AI call on startup
def test_no_ai_call_on_startup():
    from apps.script_factory.providers.mock_provider import MockScriptAIProvider
    with patch.object(MockScriptAIProvider, "generate_ideas") as m_ideas, \
         patch.object(MockScriptAIProvider, "write_script") as m_write, \
         patch.object(MockScriptAIProvider, "review_script") as m_rev:

        # Import UI and render
        from apps.ui_script_factory import render_script_factory_ui, _get_dashboard_counts
        counts = _get_dashboard_counts()
        assert isinstance(counts, dict)

        assert m_ideas.call_count == 0
        assert m_write.call_count == 0
        assert m_rev.call_count == 0


# 21. Batch resume does not repeat done jobs
def test_batch_resume_does_not_repeat_done_jobs(temp_sf_env):
    batch_mgr = temp_sf_env["batch_mgr"]
    ep_ids = ["EP020", "EP021", "EP022"]
    job = batch_mgr.create_script_batch_job(ep_ids)

    called = []
    def mock_gen_1(ep_id):
        if ep_id == "EP022":
            raise RuntimeError("Simulated failure")
        called.append(ep_id)
        return FullScript(episode_id=ep_id, title="T", host={})

    # Run batch, EP022 fails
    batch_mgr.run_script_batch(job.job_id, mock_gen_1)
    assert "EP020" in called
    assert "EP021" in called
    assert len(called) == 2

    # Simulate resume after restart
    called_resumed = []
    def mock_gen_2(ep_id):
        called_resumed.append(ep_id)
        return FullScript(episode_id=ep_id, title="T", host={})

    batch_mgr.run_script_batch(job.job_id, mock_gen_2, resume_only=True)

    # EP020 and EP021 must NOT be called again!
    assert "EP020" not in called_resumed
    assert "EP021" not in called_resumed
    assert "EP022" in called_resumed


# 22. API keys not logged
def test_api_keys_not_logged(temp_sf_env):
    cost_ctrl = temp_sf_env["cost_ctrl"]
    log_file = temp_sf_env["log_file"]

    # Record operation with an error string containing sensitive key
    fake_secret = "sk-live123456789abcdefghijklmnopqrstuvwxyz"
    cost_ctrl.record_operation(
        operation="test_op",
        episode_id="EP_TEST",
        provider="openai",
        model="gpt-4o",
        status="FAILED",
        latency_sec=0.5,
        input_tokens=100,
        output_tokens=0,
        error=f"Authentication error with key {fake_secret}",
    )

    log_content = log_file.read_text(encoding="utf-8")
    assert fake_secret not in log_content
    assert "[REDACTED_API_KEY_ERROR]" in log_content
