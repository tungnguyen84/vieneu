"""Auto Revision Manager for Script Factory V1."""
from __future__ import annotations

import logging
import time
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
    ) -> Tuple[FullScript, QCReport]:
        """Runs targeted revision and re-checks with QC."""
        if script.revision_round >= MAX_REVISION_ROUNDS:
            script.status = ApprovalStatus.USER_REVIEW_REQUIRED
            logger.warning(f"[AutoRevision] Reached max revision rounds ({MAX_REVISION_ROUNDS}) for {script.episode_id}. Marking USER_REVIEW_REQUIRED.")
            return script, qc_report

        self.cost_ctrl.check_budget_pre_flight(episode_id=script.episode_id)

        t0 = time.time()
        try:
            revised_script, in_tokens, out_tokens = self.provider.revise_script(
                script=script,
                story_bible=story_bible,
                qc_report=qc_report,
                model=model,
            )
            lat = time.time() - t0
            self.cost_ctrl.record_operation(
                operation="revise_script",
                episode_id=script.episode_id,
                provider=self.provider.provider_name,
                model=model or "default",
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
                model=model or "default",
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
        elif revised_script.revision_round >= MAX_REVISION_ROUNDS:
            revised_script.status = ApprovalStatus.USER_REVIEW_REQUIRED
        else:
            revised_script.status = ApprovalStatus.NEEDS_REVISION

        return revised_script, new_qc_report
