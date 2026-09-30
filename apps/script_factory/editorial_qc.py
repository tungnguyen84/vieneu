"""Script Factory V1.3.1 Editorial Quality Control Engine.

Audits final narration scripts against editorial standards:
1. MC_NAME_COLLISION: No story character named Minh (narrator collision).
2. UNMARKED_FIRST_PERSON_PROTAGONIST: No first-person narration ("Tôi và chị...", "Chính tôi...") unless quoted.
3. EPISODE_CODE_IN_NARRATION: No internal IDs like "EP021", "IDEA_018", "mã số".
4. FAKE_CONTINUATION_LANGUAGE: No fake YouTube breaks ("phần tiếp theo", "ở phần sau").
5. OVERLONG_REVEAL_BLOCK: Reveal blocks should feel concentrated (~5-9 segments).
6. REVEAL_2_REDUNDANCY: Reveal 2 must add new motive/meaning, not repeat Reveal 1.
7. GENERIC_REFLECTION: Reflection must belong specifically to this story.
8. MELODRAMA_DENSITY: Avoid clusters of heavy melodramatic metaphors ("bóng ma", "lồng kính", "rỉ máu").
9. GENERIC_AI_PROSE: Avoid generic philosophical fillers ("Có những ngôi nhà không chỉ là gạch đá...").
10. UNSUPPORTED_LEGAL_CERTAINTY: Old documents must not magically establish modern ownership.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from apps.script_factory.information_release_map import InformationReleaseMap, build_information_release_map
from apps.script_factory.leakage_guard import StoryBibleLeakageGuard
from apps.script_factory.models import FullScript, ScriptSegment, StoryBible
from apps.script_factory.spoiler_timing_guard import SpoilerTimingGuard

logger = logging.getLogger("VieNeu.EditorialQC")


@dataclass
class EditorialIssue:
    episode_id: str
    segment_id: str
    rule: str
    severity: str  # "BLOCKER", "FAIL", "WARN"
    excerpt: str
    reason: str
    suggested_fix: str

    @property
    def rule_id(self) -> str:
        return self.rule

    @property
    def description(self) -> str:
        return self.reason

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["rule_id"] = self.rule
        return d


class EditorialQCEngine:
    """Comprehensive editorial validator for Script Factory V1.3.1."""

    def __init__(self):
        self.leakage_guard = StoryBibleLeakageGuard()

    def audit_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        release_map: Optional[InformationReleaseMap] = None,
    ) -> List[EditorialIssue]:
        issues: List[EditorialIssue] = []
        ep_id = script.episode_id
        all_text = " ".join(s.text for s in script.segments)

        # 1. MC_NAME_COLLISION (Rule 1 - BLOCKER)
        # Fixed series MC: MINH. No story character should be named Minh.
        for seg in script.segments:
            # Check if Minh appears as a character reference in the story text
            # Ignore self-introductions by host in segment 004/005 ("Tôi là Minh")
            txt = seg.text
            # Look for character mentions like "Minh và Lan", "em trai Minh", "gặp Minh", "Minh làm vườn", "Minh nói"
            collision_patterns = [
                r"\bMinh\s+và\s+Lan\b",
                r"\bLan\s+và\s+Minh\b",
                r"\bngười\s+em\s+trai\s+Minh\b",
                r"\bem\s+trai\s+Minh\b",
                r"\bgiọng\s+Minh\b",
                r"\bAnh\s+Minh\b",
                r"\bMinh\s+(?:làm|nói|bước|nghĩ|hoảng|nhìn|chạy|quyết|lo|vội)\b",
                r"\bvới\s+Minh\b",
                r"\bcủa\s+Minh\b",
            ]
            for pat in collision_patterns:
                if re.search(pat, txt, re.IGNORECASE):
                    # Check if this is not the host self intro
                    if not re.search(r"Tôi là Minh, người sẽ đồng hành", txt):
                        issues.append(EditorialIssue(
                            episode_id=ep_id,
                            segment_id=seg.id,
                            rule="MC_NAME_COLLISION",
                            severity="BLOCKER",
                            excerpt=self._excerpt(txt, pat),
                            reason="Nhân vật trong câu chuyện trùng tên với MC Minh của series.",
                            suggested_fix="Đổi tên nhân vật thành Tuấn hoặc tên thuần Việt khác không trùng MC.",
                        ))
                        break

        # 2. UNMARKED_FIRST_PERSON_PROTAGONIST (Rule 2 - BLOCKER)
        # Narrator must be third-person documentary, not suddenly speaking as protagonist
        for seg in script.segments:
            txt = seg.text
            # Patterns where narrator speaks as if they are the brother/protagonist
            bad_first_person = [
                r"\bTôi\s+và\s+chị\s+Lan\b",
                r"\bTôi\s+và\s+Lan\b",
                r"\bCông\s+việc\s+của\s+tôi\s+là\s+làm\s+vườn\b",
                r"\bĐó\s+là\s+số\s+của\s+tôi\b",
                r"\bLời\s+nói\s+của\s+tôi\s+trong\s+điện\s+thoại\b",
                r"\bchính\s+bàn\s+tay\s+tôi\b",
                r"\bChính\s+tôi\s+đã\s+chọc\s+thủng\b",
                r"\bTâm\s+trạng\s+của\s+tôi\s+lúc\s+đó\b",
                r"\bLời\s+nói\s+'không\s+cố\s+ý'\s+của\s+tôi\b",
            ]
            for pat in bad_first_person:
                if re.search(pat, txt, re.IGNORECASE):
                    issues.append(EditorialIssue(
                        episode_id=ep_id,
                        segment_id=seg.id,
                        rule="UNMARKED_FIRST_PERSON_PROTAGONIST",
                        severity="BLOCKER",
                        excerpt=self._excerpt(txt, pat),
                        reason="MC người dẫn chuyện bỗng nhiên xưng 'tôi' đóng vai nhân vật trong câu chuyện mà không có dẫn thoại.",
                        suggested_fix="Chuyển về ngôi thứ ba tài liệu khách quan (ví dụ: 'Tuấn và chị Lan...', 'Chính Tuấn...').",
                    ))
                    break

        # 3. EPISODE_CODE_IN_NARRATION / INTERNAL_EPISODE_ID_SPOKEN (Rule 3 - BLOCKER)
        pub_ep_num = getattr(story_bible, "public_episode_number", None)
        spoken_ep_num_pat = re.compile(
            r"\btập\s+(?:số\s+|phim\s+|thứ\s+)?("
            r"\d+"
            r"|(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mươi|trăm|nghìn|ngàn)(?:\s+(?:một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|tám|chín|mười|mươi|trăm|nghìn|ngàn|linh|lẻ|không))*"
            r")\b",
            re.IGNORECASE,
        )
        for seg in script.segments:
            txt = seg.text
            match = re.search(
                r"\b(?:mã\s+số\s+)?(EP_?[A-Z0-9_]*\d+|IDEA_\d+|PROJ_[A-Z0-9_]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                txt,
                re.IGNORECASE,
            )
            m_spoken = spoken_ep_num_pat.search(txt)
            hit_val = None
            if match:
                hit_val = match.group(0)
            elif m_spoken:
                num_phrase = m_spoken.group(1).strip().lower()
                if pub_ep_num is None or str(pub_ep_num) != num_phrase:
                    hit_val = m_spoken.group(0)
            if hit_val:
                issues.append(EditorialIssue(
                    episode_id=ep_id,
                    segment_id=seg.id,
                    rule="EPISODE_CODE_IN_NARRATION",
                    severity="BLOCKER",
                    excerpt=self._excerpt(txt, re.escape(hit_val)),
                    reason=f"Đọc mã định danh hoặc số tập nội bộ ('{hit_val}') vào lời dẫn TTS.",
                    suggested_fix="Xóa bỏ mã số kỹ thuật, chỉ giới thiệu tên câu chuyện tự nhiên.",
                ))

        # 4. FAKE_CONTINUATION_LANGUAGE / FAKE_SERIAL_BREAK (Rule 4 - FAIL)
        for idx, seg in enumerate(script.segments):
            txt = seg.text
            match = re.search(
                r"(phần\s+tiếp\s+theo|ở\s+phần\s+sau|hãy\s+đón\s+xem|đón\s+xem\s+phần\s+sau|chúng\s+ta\s+sẽ\s+quay\s+lại\s+sau)",
                txt,
                re.IGNORECASE,
            )
            if not match and idx < len(script.segments) - 1:
                match = re.search(r"\btập\s+tiếp\s+theo\b", txt, re.IGNORECASE)
            if match:
                issues.append(EditorialIssue(
                    episode_id=ep_id,
                    segment_id=seg.id,
                    rule="FAKE_CONTINUATION_LANGUAGE",
                    severity="FAIL",
                    excerpt=self._excerpt(txt, re.escape(match.group(0))),
                    reason=f"Chứa ngôn từ phân mảnh clip YouTube giả tạo ('{match.group(0)}').",
                    suggested_fix="Sử dụng câu chuyển tiếp tự nhiên trong một tập hoàn chỉnh liền mạch.",
                ))

        # 5. OVERLONG_REVEAL_BLOCK (Rule 5 - FAIL/WARN)
        # Target primary reveal block is 5-9 segments. If > 10 consecutive segments are marked REVEAL, flag it.
        consecutive_reveal = 0
        max_consecutive_reveal = 0
        reveal_start_seg = ""
        for seg in script.segments:
            if seg.delivery_profile == "REVEAL":
                if consecutive_reveal == 0:
                    reveal_start_seg = seg.id
                consecutive_reveal += 1
                if consecutive_reveal > max_consecutive_reveal:
                    max_consecutive_reveal = consecutive_reveal
            else:
                consecutive_reveal = 0

        if max_consecutive_reveal > 9:
            issues.append(EditorialIssue(
                episode_id=ep_id,
                segment_id=reveal_start_seg,
                rule="OVERLONG_REVEAL_BLOCK",
                severity="FAIL",
                excerpt=f"Có {max_consecutive_reveal} phân đoạn liên tiếp mang nhãn REVEAL (bắt đầu từ [{reveal_start_seg}]).",
                reason=f"Khối cao trào giải thích quá dài dòng ({max_consecutive_reveal} segments > 9), làm giảm nhịp điệu kịch tính.",
                suggested_fix="Tập trung giải mã cốt lõi trong 5-8 phân đoạn, chuyển hệ quả và cảm xúc sang NORMAL/COMMENT.",
            ))

        # 6. REVEAL_2_REDUNDANCY (Rule 6 - FAIL)
        reveal_segs = [s for s in script.segments if s.delivery_profile == "REVEAL"]
        if reveal_segs:
            reveal_text = " ".join(s.text for s in reveal_segs).lower()
            motive_indicators = [
                "động cơ", "nguyên nhân", "lý do", "nỗi", "tình", "hy sinh", "ân hận", 
                "day dứt", "bảo vệ", "yêu thương", "tha thứ", "sợ hãi", "trách nhiệm",
                "hối hận", "mái ấm", "cờ bạc", "bí mật", "di nguyện"
            ]
            has_motive = any(ind in reveal_text for ind in motive_indicators)
            if not has_motive:
                issues.append(EditorialIssue(
                    episode_id=ep_id,
                    segment_id=reveal_segs[-1].id,
                    rule="REVEAL_2_REDUNDANCY",
                    severity="FAIL",
                    excerpt=self._excerpt(reveal_segs[-1].text, "sự thật"),
                    reason="Khối Reveal thiếu chiều sâu động cơ hoặc hệ quả cảm xúc/mối quan hệ.",
                    suggested_fix="Bổ sung động cơ tâm lý sâu xa và ý nghĩa cảm xúc của sự thật thứ hai.",
                ))

        # 7. GENERIC_REFLECTION (Rule 7 - WARN)
        for seg in script.segments:
            if seg.delivery_profile in ["ENDING", "COMMENT"] or int(seg.id if seg.id.isdigit() else 1) >= 75:
                txt_lower = seg.text.lower()
                generic_reflection_cliches = [
                    "cuộc đời luôn ẩn chứa",
                    "cuộc sống vốn dĩ vô thường",
                    "gia đình là nơi",
                    "điều quan trọng nhất trong cuộc sống",
                    "ranh giới giữa sự thật và bí mật đôi khi rất mong manh, nhưng tình yêu thương",
                    "cuộc sống luôn có những điều bất ngờ mà ta không thể đoán trước",
                ]
                for cl in generic_reflection_cliches:
                    if cl in txt_lower:
                        issues.append(EditorialIssue(
                            episode_id=ep_id,
                            segment_id=seg.id,
                            rule="GENERIC_REFLECTION",
                            severity="WARN",
                            excerpt=self._excerpt(seg.text, cl),
                            reason="Lời đúc kết mang tính triết lý sáo rỗng, có thể ghép vào bất kỳ tập nào.",
                            suggested_fix="Viết lại lời chiêm nghiệm gắn chặt vào bài học cụ thể từ biến cố của nhân vật này.",
                        ))
                        break

        # 8. MELODRAMA_DENSITY / MELODRAMA_DENSITY_V2 (Rule 8 - WARN/FAIL)
        melodrama_patterns = [
            r"bóng\s+ma\s+vô\s+hình",
            r"chiếc\s+lồng\s+kính\s+ngột\s+ngạt",
            r"lồng\s+kính\s+ngột\s+ngạt",
            r"sự\s+thật\s+rỉ\s+máu",
            r"vết\s+cắt\s+rỉ\s+máu",
            r"nhát\s+dao\s+vô\s+hình",
            r"ngột\s+ngạt\s+đến\s+nghẹt\s+thở",
            r"bí\s+mật\s+động\s+trời",
            r"sự\s+thật\s+động\s+trời",
            r"đòn\s+chí\s+mạng",
            r"sự\s+thật\s+kinh\s+hoàng",
            r"cuộc\s+gặp\s+gỡ\s+định\s+mệnh",
            r"đau\s+đớn\s+đến\s+tận\s+cùng",
            r"vĩ\s+đại\s+ẩn\s+giấu",
            r"mê\s+cung\s+không\s+lối\s+thoát",
            r"nấc\s+nghẹn\s+ngào\s+đến\s+xé\s+lòng",
        ]
        melodrama_found = []
        for seg in script.segments:
            for pat in melodrama_patterns:
                m = re.search(pat, seg.text, re.IGNORECASE)
                if m:
                    melodrama_found.append((seg.id, m.group(0), seg.text))

        if len(melodrama_found) >= 1:
            severity = "FAIL" if len(melodrama_found) >= 2 else "WARN"
            for s_id, term, full in melodrama_found:
                issues.append(EditorialIssue(
                    episode_id=ep_id,
                    segment_id=s_id,
                    rule="MELODRAMA_DENSITY",
                    severity=severity,
                    excerpt=self._excerpt(full, term),
                    reason=f"Mật độ ẩn dụ bi kịch hóa cao ('{term}'), làm mất đi tính điềm đạm của phim tài liệu xã hội.",
                    suggested_fix="Thay bằng hành động, chi tiết đời thường và diễn biến tâm lý chân thực.",
                ))

        # 9. GENERIC_AI_PROSE (Rule 9 - WARN)
        for seg in script.segments[:20]:
            txt = seg.text
            bad_ai_prose = [
                r"Có\s+những\s+ngôi\s+nhà",
                r"Có\s+những\s+góc\s+khuất\s+lặng\s+lẽ\s+nằm\s+ngay\s+trong",
                r"Có\s+những\s+vật\s+cũ\s+kỹ\s+bị\s+lãng\s+quên",
            ]
            for pat in bad_ai_prose:
                if re.search(pat, txt, re.IGNORECASE):
                    issues.append(EditorialIssue(
                        episode_id=ep_id,
                        segment_id=seg.id,
                        rule="GENERIC_AI_PROSE",
                        severity="WARN",
                        excerpt=self._excerpt(txt, pat),
                        reason="Câu mở đầu mang cấu trúc văn mẫu AI chung chung ('Có những...').",
                        suggested_fix="Mở đầu trực tiếp bằng chi tiết vật lý, nhân vật và sự việc cụ thể.",
                    ))
                    break

        # 10. UNSUPPORTED_LEGAL_CERTAINTY (Rule 10 - FAIL)
        for seg in script.segments:
            txt = seg.text
            bad_legal = [
                r"tờ\s+giấy\s+này\s+chứng\s+minh\s+hoàn\s+toàn",
                r"khẳng\s+định\s+quyền\s+sở\s+hữu\s+hợp\s+pháp\s+tuyệt\s+đối",
                r"chìa\s+khóa\s+pháp\s+lý\s+quan\s+trọng\s+nhất.*được\s+xác\s+định\s+hoàn\s+toàn",
                r"chứng\s+minh\s+hoàn\s+toàn\s+quyền\s+sở\s+hữu",
            ]
            for pat in bad_legal:
                if re.search(pat, txt, re.IGNORECASE):
                    issues.append(EditorialIssue(
                        episode_id=ep_id,
                        segment_id=seg.id,
                        rule="UNSUPPORTED_LEGAL_CERTAINTY",
                        severity="FAIL",
                        excerpt=self._excerpt(txt, pat),
                        reason="Khẳng định giá trị pháp lý tuyệt đối của tài liệu cũ mà thiếu quy trình trích lục/xác minh chính thức.",
                        suggested_fix="Trình bày tài liệu như một manh mối then chốt dẫn đến việc xác minh và đối chiếu hồ sơ địa chính.",
                    ))
                    break
            txt = seg.text
            bad_legal = [
                r"tờ\s+giấy\s+này\s+chứng\s+minh\s+hoàn\s+toàn",
                r"chìa\s+khóa\s+pháp\s+lý\s+quan\s+trọng\s+nhất.*được\s+xác\s+định\s+hoàn\s+toàn",
                r"chứng\s+minh\s+hoàn\s+toàn\s+quyền\s+sở\s+hữu",
            ]
            for pat in bad_legal:
                if re.search(pat, txt, re.IGNORECASE):
                    issues.append(EditorialIssue(
                        episode_id=ep_id,
                        segment_id=seg.id,
                        rule="UNSUPPORTED_LEGAL_CERTAINTY",
                        severity="FAIL",
                        excerpt=self._excerpt(txt, pat),
                        reason="Khẳng định giá trị pháp lý tuyệt đối của tài liệu cũ mà thiếu quy trình trích lục/xác minh chính thức.",
                        suggested_fix="Trình bày tài liệu như một manh mối then chốt dẫn đến việc xác minh và đối chiếu hồ sơ địa chính.",
                    ))
                    break

        # 10. STORY_BIBLE_LEAKAGE & SPOILER_TIMING (V1.3 Regression check)
        leakages = self.leakage_guard.audit_script(script)
        for lv in leakages:
            issues.append(EditorialIssue(
                episode_id=ep_id,
                segment_id=lv.segment_id,
                rule="STORY_BIBLE_LEAKAGE",
                severity="BLOCKER",
                excerpt=lv.excerpt,
                reason=lv.message,
                suggested_fix=lv.recommended_action,
            ))

        rel_map = release_map or build_information_release_map(story_bible)
        spoiler_guard = SpoilerTimingGuard(rel_map)
        spoilers = spoiler_guard.audit_script(script)
        for sv in spoilers:
            issues.append(EditorialIssue(
                episode_id=ep_id,
                segment_id=sv.segment_id,
                rule="PREMATURE_REVEAL",
                severity="BLOCKER",
                excerpt=sv.excerpt,
                reason=sv.message,
                suggested_fix=sv.recommended_action,
            ))

        return issues

    def _excerpt(self, full_text: str, pattern_or_term: str, window: int = 70) -> str:
        match = re.search(pattern_or_term, full_text, re.IGNORECASE)
        if match:
            start = max(0, match.start() - window // 2)
            end = min(len(full_text), match.end() + window // 2)
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(full_text) else ""
            return f"{prefix}{full_text[start:end]}{suffix}"
        return full_text[:90] + ("..." if len(full_text) > 90 else "")

    def evaluate_script(
        self,
        script_input: Any,
        idea_id: str = "",
        story_bible: Optional[StoryBible] = None,
    ) -> List[EditorialIssue]:
        """Convenience evaluation method accepting either FullScript, dict, or file path."""
        if isinstance(script_input, FullScript):
            script = script_input
        elif isinstance(script_input, dict):
            # Parse dict into FullScript
            segments_data = script_input.get("segments", [])
            segs = []
            for s in segments_data:
                seg_id = s.get("id") or s.get("segment_id", "001")
                segs.append(ScriptSegment(
                    id=str(seg_id).zfill(3),
                    speaker=s.get("speaker", "MINH"),
                    text=s.get("text", ""),
                    delivery_profile=s.get("delivery_profile", "NORMAL"),
                    importance=s.get("importance", "medium"),
                    audience_address=s.get("audience_address", False),
                    speed=s.get("speed", 1.0),
                    pause_before=s.get("pause_before", 0.0),
                    pause_after=s.get("pause_after", 0.0),
                ))
            script = FullScript(
                episode_id=script_input.get("episode_id", idea_id or "EP_TEST"),
                title=script_input.get("title", "Test Episode"),
                host=script_input.get("host", {"name": "Minh", "voice": "Binh"}),
                segments=segs,
            )
        else:
            raise TypeError(f"Unsupported script input type: {type(script_input)}")

        if story_bible is None:
            story_bible = StoryBible(
                episode_id=script.episode_id,
                title=script.title,
                protagonist={"name": "Nhân vật", "char_id": "NV1"},
                supporting_characters=[],
                relationships=[],
                timeline=[],
                locations=[],
                money_facts=[],
                critical_facts=[],
            )

        return self.audit_script(script, story_bible)

