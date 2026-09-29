"""Script Factory V1 — Pilot 01 Runner.

Generates exactly 20 diverse premise ideas for 'Sau Cánh Cửa' (EP002 -> EP021 candidates)
using real AI provider (Gemini 2.5 Flash), runs Novelty QC, exports JSON/CSV reports,
and sets all ideas to AWAITING_USER_REVIEW.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.script_factory.cost_control import CostController
from apps.script_factory.idea_generator import IdeaGenerator
from apps.script_factory.models import IdeaItem
from apps.script_factory.novelty_engine import NoveltyEngine
from apps.script_factory.providers.router import ModelRouter

logger = logging.getLogger("VieNeu.Pilot01")

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
JSON_REPORT_PATH = REPORTS_DIR / "script_factory_pilot_01.json"
CSV_REPORT_PATH = REPORTS_DIR / "script_factory_pilot_01.csv"


def run_pilot_01(
    count: int = 20,
    model: str = "gemini-2.5-flash",
    force_real_provider: bool = True,
) -> Dict[str, Any]:
    """Executes Pilot 01 for Script Factory V1."""
    router = ModelRouter()
    status_info = router.get_connection_status()

    # Section 2: Block mock provider for production pilot
    if force_real_provider and status_info["is_mock"]:
        raise RuntimeError(
            "BLOCK Real Pilot: MOCK PROVIDER — NOT FOR PRODUCTION. "
            "Please configure GEMINI_API_KEY in environment or .env file before running Pilot 01."
        )

    provider = router.get_provider("idea")
    cost_ctrl = CostController()
    novelty_engine = NoveltyEngine(provider=provider)
    idea_gen = IdeaGenerator(
        provider=provider,
        cost_controller=cost_ctrl,
        novelty_engine=novelty_engine,
    )

    t_start = time.time()
    logger.info(f"Starting Pilot 01 generation: count={count}, provider={provider.provider_name}, model={model}")

    # Section 3 & 5: Generate 20 diverse ideas
    ideas = idea_gen.generate_batch(
        count=count,
        model=model,
        is_pilot=True,
    )
    duration_sec = round(time.time() - t_start, 2)

    # Section 12: Ensure all ideas are marked AWAITING_USER_REVIEW (unless blocked)
    for it in ideas:
        if it.status != "BLOCKED_DUPLICATE":
            it.status = "AWAITING_USER_REVIEW"
    idea_gen.save_idea_bank(ideas)

    # Section 13: Export Full Content to JSON and CSV
    ideas_dict_list = [it.to_dict() for it in ideas]
    
    # Export JSON
    with open(JSON_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "pilot": "PILOT_01",
                "series": "Sau Cánh Cửa",
                "timestamp": time.time(),
                "provider": provider.provider_name.upper(),
                "model": model,
                "generation_time_sec": duration_sec,
                "total_ideas": len(ideas),
                "status": "SCRIPT FACTORY PILOT 01 — 20 IDEAS READY FOR HUMAN REVIEW",
                "ideas": ideas_dict_list,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Export CSV
    csv_headers = [
        "idea_id",
        "working_title",
        "hook",
        "protagonist",
        "relationship",
        "central_secret",
        "mystery_question",
        "false_lead",
        "clue_1",
        "clue_2",
        "clue_3",
        "reveal_1",
        "reveal_2",
        "emotional_payoff",
        "reflection_theme",
        "hook_archetype",
        "twist_archetype",
        "novelty_score",
        "premise_similarity",
        "twist_similarity",
        "hook_similarity",
        "closest_episode",
        "curiosity",
        "emotional_potential",
        "mystery_potential",
        "logical_plausibility",
        "long_form_potential",
        "status",
    ]

    with open(CSV_REPORT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers, extrasaction="ignore")
        writer.writeheader()
        for it in ideas:
            writer.writerow(it.to_dict())

    # Section 14: Cost & Token Report
    recent_ops = cost_ctrl.get_audit_records()
    pilot_ops = [op for op in recent_ops if op.get("operation") == "generate_ideas"]
    in_tok = pilot_ops[-1]["input_tokens"] if pilot_ops else 0
    out_tok = pilot_ops[-1]["output_tokens"] if pilot_ops else 0

    # Pricing estimation for Gemini 2.5 Flash ($0.075 / 1M in, $0.30 / 1M out)
    est_cost = (in_tok / 1_000_000) * 0.075 + (out_tok / 1_000_000) * 0.30

    cost_report = {
        "provider": provider.provider_name.upper(),
        "model": model,
        "requests": len(pilot_ops),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "estimated_cost_usd": round(est_cost, 6),
        "generation_time_sec": duration_sec,
    }

    return {
        "status": "SCRIPT FACTORY PILOT 01 — 20 IDEAS READY FOR HUMAN REVIEW",
        "total_ideas": len(ideas),
        "json_path": str(JSON_REPORT_PATH),
        "csv_path": str(CSV_REPORT_PATH),
        "cost_report": cost_report,
        "ideas": ideas,
    }


if __name__ == "__main__":
    result = run_pilot_01()
    print("PILOT COMPLETED SUCCESSFULLY!")
    print(json.dumps(result["cost_report"], indent=2))
