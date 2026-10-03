"""Auto Revision Manager for Script Factory V1."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional, Tuple

from apps.script_factory.cost_control import CostController
from apps.script_factory.models import ApprovalStatus, FullScript, QCReport, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.script_qc import ScriptQCEngine

logger = logging.getLogger("VieNeu.AutoRevision")

MAX_REVISION_ROUNDS = 3


class AutoRevisionManager:
    """Orchestrates targeted script revisions based on QC requests up to 3 rounds."""

    def __init__(
        self,
        provider: ScriptAIProvider,
        cost_controller: CostController,
        qc_engine: ScriptQCEngine,
    ):
        self.provider = provider
        self.cost_ctrl = cost_controller
        self.qc_engine = qc_engine

    def auto_revise_and_recheck(
        self,
        script: FullScript,
        story_bible: StoryBible,
        qc_report: QCReport,
        model: Optional[str] = None,
        max_rounds: int = MAX_REVISION_ROUNDS,
    ) -> Tuple[FullScript, QCReport]:
        """Runs targeted revision and re-checks with QC.

        ``max_rounds`` is the absolute round ceiling; callers that start a fresh
        repair session on an already-revised script pass a raised ceiling.
        """
        if script.revision_round >= max_rounds:
            # The round limit protects paid model calls. Safe deterministic
            # repairs (hook/ending/profile normalization) may still resolve a
            # legacy artifact without consuming another AI request.
            from apps.script_factory.script_qc import apply_targeted_repairs

            repaired_script = apply_targeted_repairs(script, story_bible, qc_report,
                allow_prose_templates=script.generation_source != 'REAL_AI')
            repaired_report = self.qc_engine.run_qc(repaired_script, story_bible, model=model)
            if repaired_report.status == "PASS":
                repaired_script.status = ApprovalStatus.QC_PASS
            else:
                repaired_script.status = ApprovalStatus.USER_REVIEW_REQUIRED
                logger.warning(
                    f"[AutoRevision] Reached max revision rounds ({MAX_REVISION_ROUNDS}) for "
                    f"{script.episode_id}; deterministic repair still requires user review."
                )
            return repaired_script, repaired_report

        self.cost_ctrl.check_budget_pre_flight(episode_id=script.episode_id)

        effective_req_model = (
            model
            or getattr(self.provider, 'requested_model', None)
            or getattr(self.provider, 'default_model', None)
            or getattr(script, 'requested_model', None)
        )

        t0 = time.time()
        from apps.script_factory.semantic_review import script_content_hash
        before_hash = script_content_hash(script)
        try:
            revised_script, in_tokens, out_tokens = self.provider.revise_script(
                script=script,
                story_bible=story_bible,
                qc_report=qc_report,
                model=effective_req_model,
            )
            if script_content_hash(revised_script) != before_hash:
                actual_m = (
                    getattr(self.provider, 'last_actual_model', None)
                    or getattr(self.provider, 'last_used_model', None)
                    or effective_req_model
                    or getattr(revised_script, 'model_name', None)
                )
                revised_script.generation_request_id = str(uuid.uuid4())
                revised_script.model_name = actual_m
                revised_script.provider_name = self.provider.provider_name
                revised_script.prompt_version = 'script-v3.6-grounded-repair'
                revised_script.writer_strategy = script.writer_strategy
                revised_script.requested_model = effective_req_model
                revised_script.actual_model = actual_m
                revised_script.total_words = sum(len(s.text.split()) for s in revised_script.segments)
            lat = time.time() - t0
            self.cost_ctrl.record_operation(
                operation="revise_script",
                episode_id=script.episode_id,
                provider=self.provider.provider_name,
                model=effective_req_model or "default",
                status="SUCCESS",
                latency_sec=lat,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
            )
        except Exception as exc:
            lat = time.time() - t0
            self.cost_ctrl.record_operation(
                operation="revise_script",
                episode_id=script.episode_id,
                provider=self.provider.provider_name,
                model=effective_req_model or "default",
                status="FAILED",
                latency_sec=lat,
                input_tokens=0,
                output_tokens=0,
                error=str(exc),
            )
            raise exc

        # Re-run QC
        new_qc_report = self.qc_engine.run_qc(revised_script, story_bible, model=model)

        if new_qc_report.status == "PASS":
            revised_script.status = ApprovalStatus.QC_PASS
        elif revised_script.revision_round >= max_rounds:
            revised_script.status = ApprovalStatus.USER_REVIEW_REQUIRED
        else:
            revised_script.status = ApprovalStatus.NEEDS_REVISION

        return revised_script, new_qc_report
