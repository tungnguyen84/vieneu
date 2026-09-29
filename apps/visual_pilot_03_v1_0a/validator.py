"""Fact Grounding Validator for Visual Planning V1.0a.

Validates that every factual visual claim in character bibles, prop bibles,
location bibles, scene specs, and overlay plans maps strictly to locked
story artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_BASE = BASE_DIR / "production_pilot_03"


class VisualFactGroundingValidator:
    """Validates visual facts against locked story artifacts."""

    def __init__(self, ep_id: str):
        self.ep_id = ep_id
        self.snapshot_dir = SNAPSHOT_BASE / ep_id / "script_snapshot"

        with open(self.snapshot_dir / "story_bible.json", "r", encoding="utf-8") as f:
            self.story_bible = json.load(f)

        with open(self.snapshot_dir / "fact_lock.json", "r", encoding="utf-8") as f:
            self.fact_lock = json.load(f)

        with open(self.snapshot_dir / "information_release_map.json", "r", encoding="utf-8") as f:
            self.release_map = json.load(f)

        with open(self.snapshot_dir / "full_script.json", "r", encoding="utf-8") as f:
            self.full_script = json.load(f)

        self._build_grounding_corpus()

    def _build_grounding_corpus(self):
        """Builds searchable index of grounded story facts."""
        self.grounded_facts = []

        # From fact_lock
        if isinstance(self.fact_lock, list):
            for item in self.fact_lock:
                self.grounded_facts.append({
                    "source_file": "fact_lock.json",
                    "source_field": item.get("field"),
                    "fact_id": item.get("fact_id"),
                    "value": str(item.get("value", ""))
                })

        # From story_bible critical facts
        for cf in self.story_bible.get("critical_facts", []):
            self.grounded_facts.append({
                "source_file": "story_bible.json",
                "source_field": f"critical_facts.{cf.get('field')}",
                "fact_id": cf.get("fact_id"),
                "value": str(cf.get("value", ""))
            })

        # From clues
        for i, clue in enumerate(self.story_bible.get("clues", [])):
            self.grounded_facts.append({
                "source_file": "story_bible.json",
                "source_field": f"clues[{i}]",
                "value": clue
            })

        # From timeline
        for i, t in enumerate(self.story_bible.get("timeline", [])):
            self.grounded_facts.append({
                "source_file": "story_bible.json",
                "source_field": f"timeline[{i}]",
                "value": t
            })

        # From full_script segments
        segments = self.full_script.get("segments", [])
        if not segments and isinstance(self.full_script, list):
            segments = self.full_script
        for seg in segments:
            self.grounded_facts.append({
                "source_file": "full_script.json",
                "source_field": f"segment_{seg.get('id', seg.get('segment_id'))}",
                "value": seg.get("text", "")
            })

    def verify_claim(self, claim: str, category: str = "STORY_FACT") -> dict:
        """Verifies if a specific fact claim is grounded in the corpus."""
        claim_clean = claim.strip()
        matched = []

        # 1. Direct substring match
        for gf in self.grounded_facts:
            val = gf["value"]
            if claim_clean.lower() in val.lower():
                matched.append(gf)
                break

        # 2. Token / keyword match if not direct substring
        if not matched:
            import re
            words = [w.lower() for w in re.findall(r'[\w]+', claim_clean) if len(w) >= 2]
            if words:
                for gf in self.grounded_facts:
                    val_lower = gf["value"].lower()
                    found_words = [w for w in words if w in val_lower]
                    if len(found_words) == len(words) or (len(words) >= 3 and len(found_words) / len(words) >= 0.75):
                        matched.append(gf)
                        break

        if matched:
            best = matched[0]
            return {
                "fact_claim": claim_clean,
                "category": category,
                "status": "GROUNDED",
                "source_file": best["source_file"],
                "source_field": best["source_field"],
                "confidence": 1.0
            }
        else:
            return {
                "fact_claim": claim_clean,
                "category": category,
                "status": "UNLOCKED_VISUAL_FACT",
                "source_file": None,
                "source_field": None,
                "confidence": 0.0
            }


class OverlayFactGroundingValidator:
    """Validates that text overlays contain ONLY grounded story facts."""

    def __init__(self, fact_validator: VisualFactGroundingValidator):
        self.fact_validator = fact_validator

    def validate_overlay(self, scene_id: str, overlay_text: str, declared_claims: List[str]) -> dict:
        grounded_claims = []
        ungrounded_claims = []
        source_refs = []

        for claim in declared_claims:
            res = self.fact_validator.verify_claim(claim, category="OVERLAY_FACT")
            if res["status"] == "GROUNDED":
                grounded_claims.append(claim)
                source_refs.append(f"{res['source_file']}:{res['source_field']}")
            else:
                ungrounded_claims.append(claim)

        # Detect forbidden artificial review cards
        forbidden_labels = ["bước ngoặt 1", "bước ngoặt 2", "xác minh sự thật", "tiết lộ bí mật"]
        has_forbidden_label = any(lbl in overlay_text.lower() for lbl in forbidden_labels)

        status = "PASS" if (len(ungrounded_claims) == 0 and not has_forbidden_label) else "FAIL"

        return {
            "scene_id": scene_id,
            "overlay_text": overlay_text,
            "grounded_claims": grounded_claims,
            "ungrounded_claims": ungrounded_claims,
            "source_refs": source_refs,
            "forbidden_label_detected": has_forbidden_label,
            "status": status
        }
