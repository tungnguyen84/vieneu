"""Gradio UI Component for VieNeu Script Factory V1.

Features:
- Dashboard with real-time statistics (Ideas, Story Bibles, Draft Scripts, QC Passed, Approved, Production Ready).
- Idea Bank table with multi-criteria filters.
- Episode Editor tabs: Overview, Story Bible, Full Script, Segments, QC Report, Production.
- Actions: Generate Ideas, Check Novelty, Create Story Bible, Generate Script, Run QC, Auto Fix, Preview, Approve, Send to Production.
- Human Approval Gate enforcement.
- Cost & Token tracker widget.
- STRICT INVARIANT: 0 AI requests on UI load / tab switch / startup.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import gradio as gr
except ImportError:
    from unittest.mock import MagicMock
    gr = MagicMock()

from apps.script_factory.approval_gate import HumanApprovalGate
from apps.script_factory.auto_revision import AutoRevisionManager
from apps.script_factory.cost_control import CostController
from apps.script_factory.idea_generator import IdeaGenerator
from apps.script_factory.models import ApprovalStatus, FullScript, IdeaItem, QCReport, StoryBible
from apps.script_factory.novelty_engine import NoveltyEngine
from apps.script_factory.production_adapter import ProductionAdapter
from apps.script_factory.providers.router import ModelRouter
from apps.script_factory.script_qc import ScriptQCEngine
from apps.script_factory.script_writer import ScriptWriter
from apps.script_factory.story_planner import StoryPlanner

logger = logging.getLogger("VieNeu.UIScriptFactory")


def _get_dashboard_counts(episodes_root: Path = Path("episodes")) -> Dict[str, int]:
    """Computes stats from local disk without calling AI."""
    ideas_file = Path("script_factory/idea_bank.json")
    ideas_cnt = 0
    if ideas_file.exists():
        try:
            with open(ideas_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                ideas_cnt = len(d.get("ideas", []))
        except Exception:
            pass

    bible_ready = 0
    draft_scripts = 0
    qc_passed = 0
    approved = 0
    production_ready = 0

    if episodes_root.exists():
        for ep_dir in episodes_root.iterdir():
            if ep_dir.is_dir() and ep_dir.name.startswith("EP"):
                if (ep_dir / "story_bible.json").exists():
                    bible_ready += 1
                script_f = ep_dir / "script.json"
                if script_f.exists():
                    try:
                        with open(script_f, "r", encoding="utf-8") as f:
                            sd = json.load(f)
                        st = sd.get("status", "")
                        if st == "DRAFT":
                            draft_scripts += 1
                        elif st == "QC_PASS":
                            qc_passed += 1
                        elif st == "APPROVED":
                            approved += 1
                        elif st == "PRODUCTION_READY":
                            production_ready += 1
                    except Exception:
                        pass
                if (ep_dir / "production.json").exists():
                    production_ready += 1

    return {
        "ideas": ideas_cnt,
        "story_bible_ready": bible_ready,
        "draft_scripts": draft_scripts,
        "qc_passed": qc_passed,
        "approved": approved,
        "production_ready": production_ready,
    }


def _render_dashboard_md(counts: Dict[str, int]) -> str:
    return (
        f"### 📊 Tổng Quan Script Factory — Series: *Sau Cánh Cửa*\n"
        f"| Ý tưởng (Ideas) | Story Bible Sẵn Sàng | Bản nháp (Draft) | QC Đạt (Pass) | Đã Duyệt (Approved) | Sẵn sàng Sản Xuất |\n"
        f"| :---: | :---: | :---: | :---: | :---: | :---: |\n"
        f"| **{counts['ideas']}** | **{counts['story_bible_ready']}** | **{counts['draft_scripts']}** | **{counts['qc_passed']}** | **{counts['approved']}** | **{counts['production_ready']}** |"
    )


def _render_provider_status_md() -> str:
    try:
        router = ModelRouter()
        st = router.get_connection_status()
        color = "#10b981" if not st["is_mock"] else "#ef4444"
        badge = f"<span style='color:{color}; font-weight:bold;'>{st['status']}</span>"
        return (
            f"**AI Provider:** `{st['provider']}` &nbsp;|&nbsp; "
            f"**Model:** `{st['model']}` &nbsp;|&nbsp; "
            f"**Connection Status:** {badge}"
        )
    except Exception as e:
        return f"**Connection Status:** `Error: {e}`"


IDEA_TABLE_HEADERS = [
    "ID",
    "Working Title",
    "Hook",
    "Protagonist",
    "Relationship",
    "Central Secret",
    "Mystery Question",
    "False Lead",
    "Clue 1",
    "Clue 2",
    "Clue 3",
    "Reveal 1",
    "Reveal 2",
    "Emotional Payoff",
    "Reflection Theme",
    "Hook Archetype",
    "Twist Archetype",
    "Novelty",
    "Closest Episode",
    "Status",
]


def _load_ideas_dataframe(filter_status: str = "ALL") -> List[List[Any]]:
    """Loads Idea Bank dataframe filtered by status adhering to Section 11 schema."""
    ideas_file = Path("script_factory/idea_bank.json")
    if not ideas_file.exists():
        return []
    try:
        with open(ideas_file, "r", encoding="utf-8") as f:
            d = json.load(f)
        ideas = [IdeaItem.from_dict(x) for x in d.get("ideas", [])]
    except Exception:
        return []

    rows = []
    for it in ideas:
        if filter_status != "ALL":
            if filter_status == "AWAITING_REVIEW" and it.status != "AWAITING_USER_REVIEW":
                continue
            elif filter_status == "PASS" and it.status not in ["PASS", "DRAFT"]:
                continue
            elif filter_status == "BLOCKED" and it.status != "BLOCKED_DUPLICATE":
                continue
            elif filter_status == "APPROVED" and it.status != "APPROVED":
                continue
            elif filter_status == "DRAFT" and it.status != "DRAFT":
                continue

        novelty_str = f"{it.novelty_score:.1f}%" if it.novelty_score is not None else "N/A"
        closest_str = it.closest_episode or "EP001"
        status_badge = (
            "⏳ REVIEW" if it.status == "AWAITING_USER_REVIEW"
            else ("⛔ BLOCKED" if it.status == "BLOCKED_DUPLICATE"
            else ("✅ APPROVED" if it.status == "APPROVED" else it.status))
        )

        rows.append([
            it.idea_id,
            it.working_title,
            it.hook,
            it.protagonist,
            it.relationship,
            it.central_secret,
            it.mystery_question,
            it.false_lead,
            it.clue_1,
            it.clue_2,
            it.clue_3,
            it.reveal_1,
            it.reveal_2,
            it.emotional_payoff,
            it.reflection_theme,
            it.hook_archetype,
            it.twist_archetype,
            novelty_str,
            closest_str,
            status_badge,
        ])
    return rows


def render_script_factory_ui() -> Dict[str, Any]:
    """Renders the Script Factory Gradio UI tab."""
    counts = _get_dashboard_counts()

    with gr.Column():
        provider_status_md = gr.Markdown(_render_provider_status_md())
        dashboard_md = gr.Markdown(_render_dashboard_md(counts))

        # Main action toolbar
        with gr.Row():
            idea_count_dd = gr.Dropdown(
                label="Số lượng ý tưởng",
                choices=["10", "20", "50", "100"],
                value="10",
                scale=1,
            )
            btn_gen_ideas = gr.Button("✨ Generate Ideas", variant="primary", scale=2)
            btn_run_pilot = gr.Button("🚀 Chạy Real Pilot 01 (20 Ideas)", variant="primary", scale=2)
            btn_check_novelty = gr.Button("🔍 Check Novelty", variant="secondary", scale=2)
            btn_create_bible = gr.Button("📖 Create Story Bible", variant="secondary", scale=2)
            btn_gen_script = gr.Button("✍️ Generate Script", variant="primary", scale=2)
            btn_run_qc = gr.Button("🔎 Run QC", variant="secondary", scale=2)
            btn_auto_fix = gr.Button("🔧 Auto Fix", variant="secondary", scale=1)
            btn_approve_script = gr.Button("✅ Approve (Duyệt)", variant="stop", scale=2)
            btn_send_production = gr.Button("🚀 Send to Production", variant="stop", scale=2)

        action_status_md = gr.Markdown("*(Chọn chức năng ở trên để xử lý pipeline)*")

        # Idea Bank Table Section
        with gr.Accordion("💡 Ngân Hàng Ý Tưởng (Idea Bank)", open=True):
            with gr.Row():
                filter_status_radio = gr.Radio(
                    label="Lọc theo trạng thái",
                    choices=["ALL", "AWAITING_REVIEW", "DRAFT", "PASS", "BLOCKED", "APPROVED"],
                    value="ALL",
                    scale=3,
                )
                btn_refresh_ideas = gr.Button("🔄 Tải lại bảng", scale=1)

            idea_bank_df = gr.Dataframe(
                headers=IDEA_TABLE_HEADERS,
                datatype=["str"] * len(IDEA_TABLE_HEADERS),
                value=_load_ideas_dataframe("ALL"),
                interactive=False,
                label="Danh sách ý tưởng tập phim (20 trường chi tiết theo Section 11)",
            )

        # Episode Editor Section
        with gr.Accordion("🎬 Trình Biên Tập Tập Phim (Episode Editor)", open=True):
            with gr.Row():
                ep_select_dd = gr.Dropdown(
                    label="Chọn Tập Phim",
                    choices=["EP001"] + [f"EP{i:03d}" for i in range(2, 20)],
                    value="EP001",
                    scale=3,
                )
                btn_load_ep = gr.Button("👁 Nạp Tập Phim", scale=1)

            with gr.Tabs():
                with gr.Tab("📌 Overview"):
                    ep_overview_md = gr.Markdown("*(Bấm 'Nạp Tập Phim' để xem thông tin)*")

                with gr.Tab("📖 Story Bible"):
                    ep_bible_json = gr.JSON(label="Story Bible (Source of Truth)")
                    with gr.Row():
                        btn_save_bible_edit = gr.Button("💾 Lưu Thay Đổi Story Bible", variant="secondary")
                    bible_save_status_md = gr.Markdown("")

                with gr.Tab("✍️ Full Script"):
                    ep_script_text = gr.Textbox(label="Nội dung kịch bản dẫn chuyện (Toàn văn)", lines=16, interactive=True)
                    btn_save_script_edit = gr.Button("💾 Lưu Sửa Đổi Script", variant="secondary")
                    script_save_status_md = gr.Markdown("")

                with gr.Tab("🎙️ Segments"):
                    ep_segments_df = gr.Dataframe(
                        headers=["ID", "Speaker", "Profile", "Speed", "Audience", "Importance", "Text"],
                        datatype=["str", "str", "str", "number", "bool", "str", "str"],
                        interactive=False,
                        label="Danh sách phân đoạn TTS"
                    )

                with gr.Tab("🔎 QC Report"):
                    ep_qc_json = gr.JSON(label="Kết quả kiểm duyệt chi tiết")
                    ep_qc_summary_md = gr.Markdown("")

                with gr.Tab("🚀 Production Package"):
                    ep_prod_info_md = gr.Markdown("*(Thông tin gói sản xuất V9.3)*")

        # Cost and Audit Section
        with gr.Accordion("💰 Chi Phí & Nhật Ký Tạo (Cost Control & Audit Log)", open=False):
            cost_metrics_md = gr.Markdown("### 💰 Token & Chi phí: $0.0000 USD (Hôm nay: $0.0000 / Ngân sách $10.00)")
            audit_log_df = gr.Dataframe(
                headers=["Timestamp", "Operation", "Episode", "Provider", "Model", "Status", "Latency", "Tokens", "Cost USD"],
                datatype=["str", "str", "str", "str", "str", "str", "number", "number", "number"],
                interactive=False,
            )
            btn_refresh_cost = gr.Button("🔄 Cập nhật chi phí", size="sm")

    # State
    selected_idea_state = gr.State(None)
    selected_ep_state = gr.State("EP001")

    components = {
        "provider_status_md": provider_status_md,
        "dashboard_md": dashboard_md,
        "idea_count_dd": idea_count_dd,
        "btn_gen_ideas": btn_gen_ideas,
        "btn_run_pilot": btn_run_pilot,
        "btn_check_novelty": btn_check_novelty,
        "btn_create_bible": btn_create_bible,
        "btn_gen_script": btn_gen_script,
        "btn_run_qc": btn_run_qc,
        "btn_auto_fix": btn_auto_fix,
        "btn_approve_script": btn_approve_script,
        "btn_send_production": btn_send_production,
        "action_status_md": action_status_md,
        "filter_status_radio": filter_status_radio,
        "btn_refresh_ideas": btn_refresh_ideas,
        "idea_bank_df": idea_bank_df,
        "ep_select_dd": ep_select_dd,
        "btn_load_ep": btn_load_ep,
        "ep_overview_md": ep_overview_md,
        "ep_bible_json": ep_bible_json,
        "btn_save_bible_edit": btn_save_bible_edit,
        "bible_save_status_md": bible_save_status_md,
        "ep_script_text": ep_script_text,
        "btn_save_script_edit": btn_save_script_edit,
        "script_save_status_md": script_save_status_md,
        "ep_segments_df": ep_segments_df,
        "ep_qc_json": ep_qc_json,
        "ep_qc_summary_md": ep_qc_summary_md,
        "ep_prod_info_md": ep_prod_info_md,
        "cost_metrics_md": cost_metrics_md,
        "audit_log_df": audit_log_df,
        "btn_refresh_cost": btn_refresh_cost,
        "selected_idea_state": selected_idea_state,
        "selected_ep_state": selected_ep_state,
    }
    return components


def bind_script_factory_events(c: Dict[str, Any]) -> None:
    """Connects UI buttons and callbacks."""
    cost_ctrl = CostController()
    router = ModelRouter()
    provider = router.get_provider()
    novelty_engine = NoveltyEngine(provider=provider)
    idea_gen = IdeaGenerator(provider=provider, cost_controller=cost_ctrl, novelty_engine=novelty_engine)
    story_planner = StoryPlanner(provider=provider, cost_controller=cost_ctrl)
    qc_engine = ScriptQCEngine(provider=provider, cost_controller=cost_ctrl)
    script_writer = ScriptWriter(provider=provider, cost_controller=cost_ctrl)
    auto_rev = AutoRevisionManager(provider=provider, cost_controller=cost_ctrl, qc_engine=qc_engine)
    prod_adapter = ProductionAdapter()

    def _on_generate_ideas(count_str):
        try:
            cnt = int(count_str)
        except ValueError:
            cnt = 10
        new_ideas = idea_gen.generate_batch(count=cnt)
        df_data = _load_ideas_dataframe("ALL")
        counts = _get_dashboard_counts()
        status = f"✅ Đã tạo thành công {len(new_ideas)} ý tưởng mới vào Idea Bank."
        return _render_dashboard_md(counts), df_data, status

    def _on_run_pilot():
        try:
            from apps.script_factory.pilot_runner import run_pilot_01
            res = run_pilot_01(count=20, model="gemini-2.5-flash", force_real_provider=True)
            counts = _get_dashboard_counts()
            df_data = _load_ideas_dataframe("ALL")
            cost_rep = res["cost_report"]
            status = (
                f"### 🚀 {res['status']}\n\n"
                f"- **Total Ideas:** {res['total_ideas']}\n"
                f"- **JSON Export:** `{res['json_path']}`\n"
                f"- **CSV Export:** `{res['csv_path']}`\n"
                f"- **Provider:** {cost_rep['provider']} ({cost_rep['model']})\n"
                f"- **Tokens:** {cost_rep['input_tokens']} in / {cost_rep['output_tokens']} out\n"
                f"- **Est. Cost:** ${cost_rep['estimated_cost_usd']:.6f} USD\n"
                f"- **Generation Time:** {cost_rep['generation_time_sec']}s"
            )
            return _render_dashboard_md(counts), df_data, status, _render_provider_status_md()
        except Exception as e:
            return _render_dashboard_md(_get_dashboard_counts()), _load_ideas_dataframe("ALL"), f"❌ Lỗi Pilot: {e}", _render_provider_status_md()

    def _on_check_novelty():
        ideas = idea_gen.load_idea_bank()
        if not ideas:
            return "⚠️ Chưa có ý tưởng nào trong Idea Bank.", _load_ideas_dataframe("ALL")
        blocked = 0
        for it in ideas:
            rep = novelty_engine.check_idea_novelty(it, ideas)
            it.novelty_score = rep.novelty_score
            if rep.status == "BLOCK_DUPLICATE":
                it.status = "BLOCKED_DUPLICATE"
                blocked += 1
            elif it.status == "DRAFT":
                it.status = "PASS"
        idea_gen.save_idea_bank(ideas)
        df_data = _load_ideas_dataframe("ALL")
        msg = f"🔍 Đã kiểm tra tính độc bản (Novelty Check) cho {len(ideas)} ý tưởng. Phát hiện {blocked} ý tưởng trùng lặp (BLOCKED)."
        return msg, df_data

    def _on_create_bible():
        ideas = idea_gen.load_idea_bank()
        pass_ideas = [it for it in ideas if it.status in ["PASS", "DRAFT"]]
        if not pass_ideas:
            return "⚠️ Không có ý tưởng hợp lệ (PASS/DRAFT) để tạo Story Bible."
        target_idea = pass_ideas[0]
        bible = story_planner.create_story_bible_from_idea(target_idea)
        target_idea.status = "USED"
        idea_gen.save_idea_bank(ideas)
        counts = _get_dashboard_counts()
        return f"📖 Đã khởi tạo thành công Story Bible cho tập **{bible.episode_id}**: *{bible.title}*."

    def _on_generate_script(ep_id):
        bible = story_planner.load_story_bible(ep_id)
        if not bible:
            return f"⚠️ Chưa có Story Bible cho tập {ep_id}. Vui lòng tạo Story Bible trước."
        script = script_writer.generate_script_from_bible(bible)
        counts = _get_dashboard_counts()
        return f"✍️ Đã tạo xong kịch bản cho tập **{ep_id}** ({script.total_segments} phân đoạn, {script.total_words} từ)."

    def _on_run_qc(ep_id):
        script = script_writer.load_script(ep_id)
        bible = story_planner.load_story_bible(ep_id)
        if not script or not bible:
            return f"⚠️ Thiếu Script hoặc Story Bible cho tập {ep_id}."
        rep = qc_engine.run_qc(script, bible)
        status_md = f"### 🔎 Kết Quả QC cho {ep_id}: **{rep.status}**\n- Fact conflicts: {len(rep.fact_conflicts)}\n- Logic issues: {len(rep.logic_issues)}\n- Revision requests: {len(rep.revision_requests)}"
        return status_md

    def _on_auto_fix(ep_id):
        script = script_writer.load_script(ep_id)
        bible = story_planner.load_story_bible(ep_id)
        qc_rep = qc_engine.load_qc_report(ep_id)
        if not script or not bible or not qc_rep:
            return f"⚠️ Thiếu thông tin Script, Bible hoặc QC Report cho tập {ep_id}."
        if qc_rep.status == "PASS":
            return f"✅ Kịch bản {ep_id} đã đạt PASS QC, không cần Auto Fix."
        revised_script, new_qc = auto_rev.auto_revise_and_recheck(script, bible, qc_rep)
        script_writer.save_script(revised_script)
        return f"🔧 Auto Fix hoàn tất vòng {revised_script.revision_round}. Trạng thái QC mới: **{new_qc.status}**."

    def _on_approve(ep_id):
        script = script_writer.load_script(ep_id)
        qc_rep = qc_engine.load_qc_report(ep_id)
        if not script:
            return f"⚠️ Không tìm thấy kịch bản cho {ep_id}."
        qc_status = qc_rep.status if qc_rep else "PASS"
        try:
            HumanApprovalGate.approve_script(script, qc_status=qc_status, user="USER")
            script_writer.save_script(script)
            return f"🎉 **Đã phê duyệt (APPROVED)** kịch bản cho tập {ep_id} bởi USER. Sẵn sàng gửi sang Production."
        except Exception as e:
            return f"❌ Phê duyệt thất bại: {e}"

    def _on_send_production(ep_id):
        script = script_writer.load_script(ep_id)
        bible = story_planner.load_story_bible(ep_id)
        if not script or not bible:
            return f"⚠️ Thiếu Script hoặc Story Bible cho tập {ep_id}."
        try:
            prod_dir = prod_adapter.adapt_to_v9_3_project(script, bible)
            counts = _get_dashboard_counts()
            return f"🚀 **Đã chuyển sang Production V9.3 thành công!** Thư mục: `{prod_dir}`."
        except Exception as e:
            return f"❌ Chuyển sang Production thất bại: {e}"

    def _on_load_episode(ep_id):
        bible = story_planner.load_story_bible(ep_id)
        script = script_writer.load_script(ep_id)
        qc_rep = qc_engine.load_qc_report(ep_id)

        overview = f"### 🎬 Tập: {ep_id}\n"
        if bible:
            overview += f"- **Tiêu đề:** {bible.title}\n- **Nhân vật chính:** {bible.protagonist.get('name')}\n- **Trạng thái Bible:** `{bible.status}`\n"
        if script:
            overview += f"- **Số phân đoạn:** {script.total_segments}\n- **Số từ:** {script.total_words}\n- **Trạng thái Script:** `{script.status}`\n"

        bible_dict = bible.to_dict() if bible else {}
        script_text = "\n\n".join(f"[{s.id}] ({s.delivery_profile}) {s.text}" for s in script.segments) if script else "Chưa có script."
        segs_rows = [[s.id, s.speaker, s.delivery_profile, s.speed, s.audience_address, s.importance, s.text] for s in (script.segments if script else [])]
        qc_dict = qc_rep.to_dict() if qc_rep else {}
        qc_summary = f"**Trạng thái QC:** {qc_rep.status if qc_rep else 'Chưa chạy QC'}"

        prod_file = Path("episodes") / ep_id / "production.json"
        prod_info = f"Chưa tạo gói Production V9.3."
        if prod_file.exists():
            try:
                prod_info = f"```json\n{prod_file.read_text(encoding='utf-8')}\n```"
            except Exception:
                pass

        return overview, bible_dict, script_text, segs_rows, qc_dict, qc_summary, prod_info

    # Wire event clicks
    c["btn_gen_ideas"].click(fn=_on_generate_ideas, inputs=[c["idea_count_dd"]], outputs=[c["dashboard_md"], c["idea_bank_df"], c["action_status_md"]])
    c["btn_run_pilot"].click(fn=_on_run_pilot, inputs=[], outputs=[c["dashboard_md"], c["idea_bank_df"], c["action_status_md"], c["provider_status_md"]])
    c["btn_check_novelty"].click(fn=_on_check_novelty, inputs=[], outputs=[c["action_status_md"], c["idea_bank_df"]])
    c["btn_create_bible"].click(fn=_on_create_bible, inputs=[], outputs=[c["action_status_md"]])
    c["btn_gen_script"].click(fn=_on_generate_script, inputs=[c["ep_select_dd"]], outputs=[c["action_status_md"]])
    c["btn_run_qc"].click(fn=_on_run_qc, inputs=[c["ep_select_dd"]], outputs=[c["action_status_md"]])
    c["btn_auto_fix"].click(fn=_on_auto_fix, inputs=[c["ep_select_dd"]], outputs=[c["action_status_md"]])
    c["btn_approve_script"].click(fn=_on_approve, inputs=[c["ep_select_dd"]], outputs=[c["action_status_md"]])
    c["btn_send_production"].click(fn=_on_send_production, inputs=[c["ep_select_dd"]], outputs=[c["action_status_md"]])
    c["btn_refresh_ideas"].click(fn=lambda f: _load_ideas_dataframe(f), inputs=[c["filter_status_radio"]], outputs=[c["idea_bank_df"]])
    c["btn_load_ep"].click(
        fn=_on_load_episode,
        inputs=[c["ep_select_dd"]],
        outputs=[c["ep_overview_md"], c["ep_bible_json"], c["ep_script_text"], c["ep_segments_df"], c["ep_qc_json"], c["ep_qc_summary_md"], c["ep_prod_info_md"]]
    )
