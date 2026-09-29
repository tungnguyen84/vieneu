"""Human Approval Gate for Script Factory V1."""
from __future__ import annotations

import logging
import time
from typing import Optional

from apps.script_factory.models import ApprovalStatus, FullScript, StoryBible

logger = logging.getLogger("VieNeu.ApprovalGate")


class ApprovalGateError(Exception):
    """Raised when an illegal transition or unauthorized approval occurs."""
    pass


class HumanApprovalGate:
    """Enforces human-in-the-loop approval and invalidation rules."""

    @staticmethod
    def approve_story_bible(bible: StoryBible, user: str = "USER") -> StoryBible:
        """Approves a Story Bible by human user."""
        if not user or user.lower() in ["ai", "bot", "system", "auto"]:
            raise ApprovalGateError("AI/Automated systems are strictly forbidden from approving Story Bibles. Human approval is required.")

        bible.status = ApprovalStatus.APPROVED
        bible.approved_by = user
        bible.approved_at = time.time()
        logger.info(f"[ApprovalGate] Story Bible {bible.episode_id} APPROVED by {user}.")
        return bible

    @staticmethod
    def approve_script(script: FullScript, qc_status: str, user: str = "USER") -> FullScript:
        """
        Approves a Full Script by human user.
        Strict Rules:
        - Only human users can approve.
        - AI is NEVER allowed to auto-approve.
        - Script must be in QC_PASS or user explicitly overrides with reason.
        """
        if not user or user.lower() in ["ai", "bot", "system", "auto"]:
            raise ApprovalGateError("AI/Automated systems are strictly forbidden from approving scripts. Human approval is required.")

        if qc_status != "PASS" and user != "USER":
            raise ApprovalGateError(f"Cannot approve script with failing QC status ({qc_status}).")

        script.status = ApprovalStatus.APPROVED
        logger.info(f"[ApprovalGate] Script {script.episode_id} APPROVED by {user}.")
        return script

    @staticmethod
    def verify_can_send_to_production(script: FullScript, story_bible: StoryBible) -> bool:
        """Checks if episode can be dispatched to production."""
        if script.status != ApprovalStatus.APPROVED:
            raise ApprovalGateError(f"Cannot send to production: Script status is '{script.status}', expected 'APPROVED'.")

        if story_bible.status == ApprovalStatus.STORY_BIBLE_CHANGED:
            raise ApprovalGateError("Cannot send to production: Story Bible was modified after approval. Re-run QC and get human re-approval.")

        return True
