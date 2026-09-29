"""Runner for Script Factory V1.2 Re-QC on Pilot 01.

Section 23:
- Loads existing IDEA_002 -> IDEA_021 from reports/script_factory_pilot_01.json
- Runs them through V1.2 QC (Novelty, Plausibility, Genre Guard, Clue Causality, Reveal Quality)
- Generates:
  - reports/script_factory_pilot_01_v1_2_qc.json
  - reports/script_factory_pilot_01_v1_2_qc.csv
- PRESERVES original reports/script_factory_pilot_01.json and reports/script_factory_pilot_01.csv
- ZERO external AI calls (0 Gemini, 0 Flow, 0 cost).
"""
from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from apps.script_factory.models import IdeaItem
from apps.script_factory.story_qc import StoryQCEngine

logger = logging.getLogger("VieNeu.Pilot01ReQC")

REPORTS_DIR = Path("reports")
ORIG_JSON_PATH = REPORTS_DIR / "script_factory_pilot_01.json"
V1_2_JSON_PATH = REPORTS_DIR / "script_factory_pilot_01_v1_2_qc.json"
V1_2_CSV_PATH = REPORTS_DIR / "script_factory_pilot_01_v1_2_qc.csv"


def run_pilot_01_re_qc() -> Dict[str, Any]:
    """Runs V1.2 QC over the existing 20 Pilot 01 ideas without regenerating."""
    if not ORIG_JSON_PATH.exists():
        raise FileNotFoundError(f"Original Pilot 01 report not found at {ORIG_JSON_PATH}")

    with open(ORIG_JSON_PATH, "r", encoding="utf-8") as f:
        orig_data = json.load(f)

    ideas_raw = orig_data.get("ideas", [])
    if len(ideas_raw) != 20:
        raise ValueError(f"Expected exactly 20 ideas in Pilot 01, found {len(ideas_raw)}")

    ideas = [IdeaItem.from_dict(d) for d in ideas_raw]

    qc_engine = StoryQCEngine()
    qc_reports: List[Dict[str, Any]] = []

    status_counts: Dict[str, int] = {}

    for idx, idea in enumerate(ideas):
        # Audit against other ideas in corpus
        other_corpus = [other for other in ideas if other.idea_id != idea.idea_id]
        rep = qc_engine.audit_idea(idea, corpus_ideas=other_corpus)
        qc_reports.append(rep.to_dict())

        st = idea.status
        status_counts[st] = status_counts.get(st, 0) + 1

    # Save to idea_bank.json with updated V1.2 fields
    bank_path = Path("script_factory/idea_bank.json")
    if bank_path.exists():
        bank_data = {
            "ideas": [it.to_dict() for it in ideas],
            "updated_at": time.time(),
            "total_count": len(ideas),
        }
        with open(bank_path, "w", encoding="utf-8") as f:
            json.dump(bank_data, f, ensure_ascii=False, indent=2)

    # Export JSON
    out_json_data = {
        "pilot": "PILOT_01_V1_2_QC",
        "series": "Sau Cánh Cửa",
        "timestamp": time.time(),
        "total_ideas": len(ideas),
        "status_summary": status_counts,
        "ideas": [it.to_dict() for it in ideas],
        "qc_reports": qc_reports,
    }

    with open(V1_2_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(out_json_data, f, ensure_ascii=False, indent=2)

    # Export CSV
    csv_headers = [
        "idea_id",
        "working_title",
        "status",
        "novelty_score",
        "narrative_skeleton_similarity",
        "plausibility_score",
        "genre_fit_score",
        "vietnamese_social_fit_score",
        "curiosity",
        "emotional_potential",
        "mystery_potential",
        "long_form_potential",
        "false_lead_strength",
        "reveal_1_surprise",
        "reveal_1_fairness",
        "reveal_2_surprise",
        "reveal_2_fairness",
        "reveal_2_value",
        "coincidence_count",
        "skeptical_viewer_questions",
        "logic_issues",
        "hook_archetype",
        "twist_archetype",
        "emotional_device",
        "has_death_or_tragedy",
        "title_strength",
        "title_specificity",
        "title_curiosity_gap",
        "reasons",
    ]

    with open(V1_2_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)
        for it, rep in zip(ideas, qc_reports):
            r_qc = rep.get("reveal_qc", {})
            writer.writerow([
                it.idea_id,
                it.working_title,
                it.status,
                rep.get("novelty_score"),
                rep.get("narrative_skeleton_similarity"),
                rep.get("plausibility_score"),
                rep.get("genre_fit_score"),
                rep.get("vietnamese_social_fit_score"),
                it.curiosity,
                it.emotional_potential,
                it.mystery_potential,
                it.long_form_potential,
                rep.get("false_lead_strength"),
                r_qc.get("reveal_1_surprise"),
                r_qc.get("reveal_1_fairness"),
                r_qc.get("reveal_2_surprise"),
                r_qc.get("reveal_2_fairness"),
                r_qc.get("reveal_2_value"),
                rep.get("coincidence_count"),
                " | ".join(rep.get("skeptical_viewer_questions", [])),
                " | ".join(rep.get("logic_issues", [])),
                it.hook_archetype,
                it.twist_archetype,
                rep.get("emotional_device"),
                rep.get("has_death_or_tragedy"),
                rep.get("title_strength"),
                rep.get("title_specificity"),
                rep.get("title_curiosity_gap"),
                " | ".join(rep.get("reasons", [])),
            ])

    logger.info(f"[Pilot01ReQC] Complete. Status counts: {status_counts}")
    return {
        "total_ideas": len(ideas),
        "status_summary": status_counts,
        "json_path": str(V1_2_JSON_PATH),
        "csv_path": str(V1_2_CSV_PATH),
    }


if __name__ == "__main__":
    res = run_pilot_01_re_qc()
    print("RE-QC COMPLETE:", json.dumps(res, indent=2))
