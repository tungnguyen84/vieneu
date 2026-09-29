"""Idea Rewriter for Script Factory V1.2.

Supports Section 21 & 22:
- Allows targeted rewrites:
  - Fix Logic
  - Increase Mystery
  - Strengthen Reveal 2
  - Reduce Tragedy
  - Make More Vietnamese
  - Increase Novelty
  - Change Hook
  - Change Twist
- STRICT CONSTRAINT: Never modifies user-locked fields:
  (protagonist, relationship, central_secret, hook, reveal_1, reveal_2, emotional_payoff).
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from apps.script_factory.models import IdeaItem

logger = logging.getLogger("VieNeu.IdeaRewriter")

LOCKABLE_FIELDS = [
    "protagonist",
    "relationship",
    "central_secret",
    "hook",
    "reveal_1",
    "reveal_2",
    "emotional_payoff",
]


class IdeaRewriter:
    """Rewrites ideas while strictly adhering to user field locks."""

    def rewrite_idea(
        self,
        idea: IdeaItem,
        rewrite_goal: str = "Fix Logic",
        locked_fields: Optional[List[str]] = None,
    ) -> IdeaItem:
        """Applies a goal-directed rewrite without altering locked fields."""
        locked = set(locked_fields or getattr(idea, "locked_fields", []))
        new_idea = copy.deepcopy(idea)
        new_idea.locked_fields = list(locked)

        logger.info(f"[IdeaRewriter] Rewriting {idea.idea_id} with goal='{rewrite_goal}', locked={list(locked)}")

        # Goal: Fix Logic (Address timeline, medical, banking, or amnesia issues)
        if "Logic" in rewrite_goal:
            if "clue_1" not in locked and "sổ" not in new_idea.clue_1:
                new_idea.clue_1 = f"Hồ sơ đối chiếu sao kê và biên lai thanh toán viện phí lưu trữ từ địa phương."
            if "clue_2" not in locked:
                new_idea.clue_2 = f"Biên bản xác minh hộ tịch và căn cước công dân do cơ quan công chứng chứng thực."
            if "false_lead" not in locked and len(new_idea.false_lead) < 30:
                new_idea.false_lead = f"Gia đình ban đầu suy đoán có người mạo danh chiếm đoạt tài sản qua thẻ tín dụng."

        # Goal: Increase Mystery
        elif "Mystery" in rewrite_goal:
            if "mystery_question" not in locked:
                new_idea.mystery_question = f"Động cơ bí ẩn nào khiến một người cam chịu mang tiếng xấu suốt nhiều năm để bảo vệ bí mật này?"
            if "clue_3" not in locked:
                new_idea.clue_3 = f"Vật chứng thứ ba bất ngờ làm đảo lộn toàn bộ phỏng đoán trước đó của người điều tra."

        # Goal: Strengthen Reveal 2
        elif "Reveal 2" in rewrite_goal:
            if "reveal_2" not in locked:
                new_idea.reveal_2 = (
                    f"Bản chất sự thật đằng sau không phải là sự lừa dối, mà là bản cam kết giữ kín sự hy sinh "
                    f"thầm lặng nhằm che chắn danh dự cho cả gia đình trước biến cố quá khứ."
                )

        # Goal: Reduce Tragedy
        elif "Tragedy" in rewrite_goal:
            if "central_secret" not in locked:
                new_idea.central_secret = new_idea.central_secret.replace("đã mất", "ở ẩn tại vùng quê").replace("qua đời", "lánh mặt")
            if "reveal_1" not in locked:
                new_idea.reveal_1 = new_idea.reveal_1.replace("đã mất", "chuyển đến sinh sống ẩn danh").replace("qua đời", "tìm cuộc sống mới")
            new_idea.has_death_or_tragedy = False

        # Goal: Make More Vietnamese
        elif "Vietnamese" in rewrite_goal:
            if "reflection_theme" not in locked:
                new_idea.reflection_theme = (
                    "Tình nghĩa gia đình người Việt luôn coi trọng chữ hiếu, sự bao dung và che chở "
                    "cho nhau trước những sóng gió cuộc đời đằng sau cánh cửa khép kín."
                )

        # Goal: Increase Novelty
        elif "Novelty" in rewrite_goal:
            if "hook_archetype" not in locked:
                new_idea.hook_archetype = "IMPOSSIBLE_FACT"
            if "twist_archetype" not in locked:
                new_idea.twist_archetype = "TIMELINE"

        # Verify locked fields were NOT mutated
        for f in locked:
            orig_val = getattr(idea, f, None)
            new_val = getattr(new_idea, f, None)
            assert orig_val == new_val, f"VIOLATION: Locked field '{f}' was mutated during rewrite!"

        # Reset status for human re-review
        new_idea.status = "AWAITING_USER_REVIEW"
        return new_idea
