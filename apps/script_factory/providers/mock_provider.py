"""Deterministic Mock Provider for Offline Testing and CI/CD."""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import (
    FullScript,
    IdeaItem,
    LockedFact,
    QCReport,
    ScriptSegment,
    StoryBible,
)
from apps.script_factory.providers.base import ScriptAIProvider


class MockScriptAIProvider(ScriptAIProvider):
    """High-fidelity deterministic offline provider for Script Factory."""

    provider_name: str = "mock"

    SAMPLE_THEMES = [
        ("Bức ảnh trong phong bì niêm phong", "FAMILY_PHOTO", "Family secrets", "Tuấn", "Mẹ và chị gái", "Mẹ giấu con trai việc chị gái thực chất là mẹ ruột sinh anh khi còn vị thành niên."),
        ("Chiếc chìa khóa két sắt ở ngân hàng cũ", "OBJECT_DISCOVERY", "Inheritance", "Hải", "Hai anh em ruột", "Cha để lại bức di chúc giả để thử lòng hiếu thảo của hai con."),
        ("Tin nhắn định kỳ lúc 2 giờ sáng", "MESSAGE", "Phone mysteries", "Thanh", "Chồng", "Chồng gửi tiền hỗ trợ trại trẻ mồ côi nơi anh từng lớn lên mà sợ vợ chê cười gia cảnh nghèo khó."),
        ("Bản hợp đồng sang nhượng mảnh đất vườn", "DOCUMENT", "Property", "Nam", "Bác ruột", "Mảnh đất gia đình không phải bị chiếm đoạt mà được bác thế chấp để cứu sống Nam lúc sơ sinh."),
        ("Người khách lạ viếng mộ vào ngày giỗ", "STRANGER", "Long-hidden sacrifice", "Bình", "Người bạn thời chiến của cha", "Người cha từng nhận tội thay bạn trong quá khứ để bạn được hoàn lương."),
        ("Khoản nợ 500 triệu không có giấy biên nhận", "MONEY_ANOMALY", "Debt", "Mai", "Cha dượng", "Cha dượng âm thầm gánh nợ chữa bệnh cho mẹ Mai suốt 10 năm."),
        ("Chiếc đồng hồ cổ không bao giờ chạy", "OBJECT_DISCOVERY", "Unexplained objects", "Hoàng", "Ông nội", "Chiếc đồng hồ dừng đúng thời khắc bi kịch gia đình xảy ra 30 năm trước."),
        ("Lời thú nhận trong cuốn nhật ký trang cuối", "CONFESSION", "Marriage secrets", "Quỳnh", "Vợ chồng", "Người vợ kết hôn vì lời hứa che chở cho đứa con riêng của người yêu đã khuất."),
        ("Cuộc gọi từ số máy của người bạn đã mất tích", "PHONE_CALL", "Social deception", "Khánh", "Nhóm bạn thân", "Người bạn mất tích giả chết để trốn tránh một đường dây lừa đảo tài chính."),
        ("Khoảng trống 3 năm trong hồ sơ bệnh án", "MISSING_TIME", "Missing memories", "Dũng", "Bác sĩ điều trị", "Dũng từng hiến thận cứu em gái nhưng bị gia đình che giấu vì sợ anh tự ti.")
    ]

    def generate_ideas(
        self,
        count: int,
        existing_ideas: List[IdeaItem],
        diversity_categories: List[str],
        hook_archetypes: List[str],
        model: Optional[str] = None,
    ) -> Tuple[List[IdeaItem], int, int]:
        existing_count = len(existing_ideas)
        ideas: List[IdeaItem] = []

        for i in range(count):
            idx = (existing_count + i)
            theme_idx = idx % len(self.SAMPLE_THEMES)
            title_base, hook_arch, div_cat, protag, rel, secret = self.SAMPLE_THEMES[theme_idx]

            idea_id = f"IDEA_{idx + 1:03d}"
            title = f"{title_base} #{idx + 1}"
            hook_text = f"Khi dọn dẹp căn phòng cũ, {protag} bất ngờ tìm thấy một bí mật mà {rel.lower()} đã che giấu suốt nhiều năm..."
            clue1 = f"Manh mối 1: Dấu vết chữ viết tay và con dấu đã mờ trên phong bì."
            clue2 = f"Manh mối 2: Lời khai mâu thuẫn của những người hàng xóm lớn tuổi."
            clue3 = f"Manh mối 3: Giấy tờ chứng từ xác thực tại cơ quan lưu trữ địa phương."
            rev1 = f"Người tưởng như xa lạ thực chất lại là người có quan hệ máu mủ ruột thịt mật thiết."
            rev2 = f"Bí mật {secret.lower()}"
            payoff = f"{protag} đối thoại trực tiếp trong nước mắt, tháo gỡ hiểu lầm sâu nặng bấy lâu."
            reflection = f"Đằng sau cánh cửa gia đình, đôi khi sự im lặng không xuất phát từ phản bội mà từ nỗi sợ làm tổn thương người mình yêu thương."

            item = IdeaItem(
                idea_id=idea_id,
                working_title=title,
                hook=hook_text,
                protagonist=protag,
                relationship=rel,
                central_secret=secret,
                mystery_question=f"Tại sao sự việc lại bị che giấu suốt từng ấy năm?",
                false_lead=f"Ban đầu {protag} nghi ngờ có sự tham ô hoặc phản bội lợi ích cá nhân.",
                clue_1=clue1,
                clue_2=clue2,
                clue_3=clue3,
                reveal_1=rev1,
                reveal_2=rev2,
                emotional_payoff=payoff,
                reflection_theme=reflection,
                hook_archetype=hook_arch,
                twist_archetype=div_cat,
                estimated_strength=8.5,
                status="DRAFT"
            )
            ideas.append(item)

        input_tokens = 150 + count * 20
        output_tokens = count * 180
        return ideas, input_tokens, output_tokens

    def create_story_bible(
        self,
        idea: IdeaItem,
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        ep_id = f"EP{idea.idea_id.replace('IDEA_', '')}" if "IDEA_" in idea.idea_id else "EP002"

        protagonist_info = {
            "name": idea.protagonist,
            "char_id": idea.protagonist.upper(),
            "role": "Nhân vật chính / Người tìm kiếm sự thật",
            "age": 32,
            "description": f"Người đối diện với bí mật gia đình lớn, luôn khao khát bảo vệ sự thật."
        }
        supporting = [
            {
                "name": "Người thân",
                "char_id": "RELATIVE",
                "role": "Người nắm giữ bí mật",
                "age": 58,
                "description": "Người chịu nhiều uẩn ức và hy sinh trong quá khứ."
            }
        ]
        relationships = [
            {
                "char_a": idea.protagonist.upper(),
                "char_b": "RELATIVE",
                "relationship": idea.relationship
            }
        ]
        timeline = [
            "10 năm trước: Biến cố gia đình ban đầu xảy ra và bí mật bắt đầu được hình thành.",
            "Hiện tại: Nhân vật chính phát hiện manh mối đầu tiên và bắt đầu quá trình xác minh."
        ]
        locations = ["HOME", "OFFICE", "OLD_STREET", "ARCHIVE"]
        money_facts = [
            {"fact": "Khoản tiền liên quan", "value": "100.000.000 VND"}
        ]
        critical_facts = [
            LockedFact(fact_id="FACT_001", field="years_hidden", value="10", description="Thời gian bí mật bị chôn giấu là 10 năm.", status="LOCKED"),
            LockedFact(fact_id="FACT_002", field="money_value", value="100.000.000 VND", description="Số tiền liên đới là 100.000.000 VND.", status="LOCKED"),
            LockedFact(fact_id="FACT_003", field="relationship_nature", value=idea.relationship, description="Mối quan hệ chính xác.", status="LOCKED")
        ]

        bible = StoryBible(
            episode_id=ep_id,
            title=idea.working_title,
            protagonist=protagonist_info,
            supporting_characters=supporting,
            relationships=relationships,
            timeline=timeline,
            locations=locations,
            money_facts=money_facts,
            critical_facts=critical_facts,
            secret=idea.central_secret,
            false_lead=idea.false_lead,
            clues=[idea.clue_1, idea.clue_2, idea.clue_3],
            reveal_1=idea.reveal_1,
            reveal_2=idea.reveal_2,
            emotional_payoff=idea.emotional_payoff,
            reflection_theme=idea.reflection_theme,
            ending=f"Câu chuyện khép lại với niềm tin và sự hàn gắn.",
            status="DRAFT"
        )
        return bible, 350, 750

    def write_script(
        self,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        segments: List[ScriptSegment] = []
        host_name = series_bible.get("host", {}).get("display_name", "Minh")
        host_id = series_bible.get("host", {}).get("id", "MINH")

        # Generate exactly 85 realistic segments meeting EP001 V9.3 pacing
        # Act 1: Hook (0-8%, segs 1-6)
        fact_vals = [f.value for f in story_bible.critical_facts if f.value]
        fact_phrase = " ".join(fact_vals) if fact_vals else "100.000.000 VND"
        segments.append(ScriptSegment(id="001", speaker=host_id, text=f"Câu chuyện hôm nay mở đầu bằng một phát hiện kỳ lạ mà nhân vật chính không bao giờ nghĩ mình sẽ chạm tới.", delivery_profile="HOOK", importance="high", speed=0.98))
        segments.append(ScriptSegment(id="002", speaker=host_id, text=f"Mọi thứ bắt đầu khi {story_bible.protagonist['name']} tìm thấy những manh mối đầu tiên bị giấu kín suốt 10 năm qua.", delivery_profile="HOOK", importance="high", speed=0.98))
        segments.append(ScriptSegment(id="003", speaker=host_id, text=f"Một sự thật có liên quan trực tiếp đến {fact_phrase} và danh tính thật của người thân trong gia đình.", delivery_profile="HOOK", importance="normal", speed=0.98))
        segments.append(ScriptSegment(id="004", speaker=host_id, text=f"Chào mừng quý vị và các bạn đã quay trở lại với Sau Cánh Cửa — nơi chúng ta cùng lắng nghe những bí mật đời thường.", delivery_profile="NORMAL", importance="normal", speed=1.01))
        segments.append(ScriptSegment(id="005", speaker=host_id, text=f"Tôi là {host_name}, người sẽ đồng hành cùng quý vị trong suốt hành trình giải mã câu chuyện ngày hôm nay.", delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 2: Setup (8-20%, segs 6-16)
        for i in range(6, 17):
            aud = (i == 10)
            text = f"Trong gia đình của {story_bible.protagonist['name']}, cuộc sống vốn dĩ trôi qua trong êm đềm và trật tự nhiều năm liền." if not aud else "Nếu là bạn, khi bắt gặp một chi tiết bất thường của người thân, bạn sẽ chọn im lặng quan sát hay hỏi thẳng ngay lập tức?"
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=f"{i:03d}", speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 3: Mystery (20-35%, segs 17-29)
        for i in range(17, 30):
            aud = (i == 24)
            text = f"Sự nghi ngờ bắt đầu nảy sinh rõ nét hơn khi các chứng từ giao dịch xuất hiện với con số chính xác 100.000.000 VND." if not aud else "Có lẽ bất cứ ai trong chúng ta khi đứng trước một câu hỏi không lời đáp cũng sẽ cảm thấy bất an."
            prof = "COMMENT" if aud else "MYSTERY"
            speed = 1.025 if aud else 0.96
            segments.append(ScriptSegment(id=f"{i:03d}", speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 4: Escalation (35-50%, segs 30-42)
        for i in range(30, 43):
            aud = (i == 36)
            text = f"Giả thuyết ban đầu về sự phản bội hay tư lợi bắt đầu dẫn dắt mọi phán đoán đi theo một hướng hoàn toàn sai lệch." if not aud else "Khi tâm trí đã bị dẫn dắt bởi một định kiến, con người ta rất dễ bỏ qua những manh mối tinh tế nhất."
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=f"{i:03d}", speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 5: Investigation (50-65%, segs 43-55)
        for i in range(43, 56):
            text = f"Các chuyến đi thực tế, gặp gỡ những người liên quan tại địa chỉ cũ dần hé mở một bức tranh hoàn toàn khác."
            segments.append(ScriptSegment(id=f"{i:03d}", speaker=host_id, text=text, delivery_profile="MYSTERY", importance="normal", speed=0.96))

        # Act 6: Major Reveal (65-75%, segs 56-64)
        # STRICT RULE: Major Reveal must be delivery_profile='REVEAL', importance='critical', audience_address=False
        segments.append(ScriptSegment(id="056", speaker=host_id, text=f"Và rồi, thời khắc sự thật được đưa ra ánh sáng cũng đã đến.", delivery_profile="REVEAL", importance="critical", speed=0.92, pause_after=0.6))
        segments.append(ScriptSegment(id="057", speaker=host_id, text=f"Tài liệu lưu trữ chính thức xác nhận: {story_bible.reveal_1}", delivery_profile="REVEAL", importance="critical", speed=0.90, pause_after=0.8))
        segments.append(ScriptSegment(id="058", speaker=host_id, text=f"Toàn bộ giả thuyết ban đầu sụp đổ hoàn toàn trước chứng cứ không thể chối cãi này.", delivery_profile="REVEAL", importance="critical", speed=0.92, pause_after=0.6))

        for i in range(59, 65):
            segments.append(ScriptSegment(id=f"{i:03d}", speaker=host_id, text=f"Sự thật này không chỉ làm thay đổi cách nhìn nhận về quá khứ, mà còn khiến người trong cuộc chết lặng.", delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 7: Second Reveal / Explanation (75-85%, segs 65-73)
        segments.append(ScriptSegment(id="065", speaker=host_id, text=f"Bí mật phía sau lời nói dối suốt 10 năm qua: {story_bible.reveal_2}", delivery_profile="REVEAL", importance="critical", speed=0.92))
        for i in range(66, 74):
            segments.append(ScriptSegment(id=f"{i:03d}", speaker=host_id, text=f"Đó là một sự hy sinh thầm lặng mà không ai trong gia đình từng nghi ngờ.", delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 8: Emotional Payoff (85-93%, segs 74-80)
        for i in range(74, 81):
            aud = (i == 78)
            text = f"Cuộc đối thoại nghẹn ngào đã xóa tan mọi khoảng cách và hiểu lầm đè nặng bao năm." if not aud else "Có những nỗi đau chỉ được xoa dịu khi chúng ta đủ dũng cảm để tha thứ cho nhau."
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=f"{i:03d}", speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 9: Reflection + Ending (93-100%, segs 81-85)
        segments.append(ScriptSegment(id="081", speaker=host_id, text=f"{story_bible.reflection_theme}", delivery_profile="COMMENT", importance="normal", audience_address=True, speed=1.025))
        segments.append(ScriptSegment(id="082", speaker=host_id, text=f"Còn bạn, bạn nghĩ điều gì là quý giá nhất khi chúng ta nhìn nhận lại những người thân yêu quanh mình?", delivery_profile="COMMENT", importance="normal", audience_address=True, speed=1.025))
        segments.append(ScriptSegment(id="083", speaker=host_id, text=f"Cảm ơn quý vị và các bạn đã dành thời gian lắng nghe câu chuyện hôm nay.", delivery_profile="ENDING", importance="normal", speed=0.965))
        segments.append(ScriptSegment(id="084", speaker=host_id, text=f"Đừng quên bấm đăng ký kênh và để lại suy nghĩ của bạn ở phần bình luận bên dưới.", delivery_profile="ENDING", importance="normal", speed=0.965))
        segments.append(ScriptSegment(id="085", speaker=host_id, text=f"Tôi là Minh. Hẹn gặp lại quý vị trong tập tiếp theo của Sau Cánh Cửa. Chúc quý vị một buổi tối an lành.", delivery_profile="ENDING", importance="normal", speed=0.965))

        total_words = sum(len(s.text.split()) for s in segments)
        script = FullScript(
            episode_id=story_bible.episode_id,
            title=story_bible.title,
            host=series_bible.get("host", {"id": "MINH", "display_name": "Minh", "voice": "Binh"}),
            segments=segments,
            total_segments=len(segments),
            total_words=total_words,
            status="DRAFT"
        )
        return script, 800, 2400

    def review_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[QCReport, int, int]:
        fact_conflicts = []
        logic_issues = []
        repetition_issues = []
        revision_requests = []

        all_text = " ".join(s.text for s in script.segments)

        # Check Locked Facts
        for fact in story_bible.critical_facts:
            if fact.status == "LOCKED":
                if fact.value.lower() not in all_text.lower():
                    fact_conflicts.append({
                        "fact_id": fact.fact_id,
                        "expected": fact.value,
                        "description": f"Locked fact '{fact.field}' with value '{fact.value}' missing from script."
                    })
                    revision_requests.append(f"Incorporate locked fact {fact.field} ({fact.value}) into script narration.")

        # Check reveal interruption rule
        reveal_segs = [s for s in script.segments if s.delivery_profile == "REVEAL"]
        for rs in reveal_segs:
            if rs.audience_address:
                logic_issues.append(f"Segment {rs.id} has delivery_profile='REVEAL' but includes audience_address=True.")
                revision_requests.append(f"Remove audience address from REVEAL segment {rs.id}.")

        # Check audience interactions count (3-6)
        audience_count = sum(1 for s in script.segments if s.audience_address)
        if audience_count < 3 or audience_count > 6:
            repetition_issues.append(f"Audience interaction count is {audience_count} (Target: 3–6).")
            revision_requests.append("Adjust direct audience interaction count to be strictly between 3 and 6.")

        status = "PASS" if not fact_conflicts and not logic_issues and not revision_requests else "NEEDS_REVISION"
        report = QCReport(
            episode_id=script.episode_id,
            status=status,
            scores={
                "hook": 95.0,
                "mystery": 94.0,
                "logic": 92.0 if not logic_issues else 70.0,
                "twist": 96.0,
                "emotion": 93.0,
                "novelty": 92.0,
                "tts_readability": 98.0
            },
            fact_conflicts=fact_conflicts,
            logic_issues=logic_issues,
            repetition_issues=repetition_issues,
            revision_requests=revision_requests,
            checked_at=time.time()
        )
        return report, 1200, 450

    def revise_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        qc_report: QCReport,
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        # Targeted fix only for requested segments
        script.revision_round += 1
        for conflict in qc_report.fact_conflicts:
            val = conflict.get("expected") or conflict.get("value") or str(conflict) if isinstance(conflict, dict) else str(conflict)
            if script.segments and val:
                script.segments[2].text += f" Con số và dữ kiện chính xác được xác nhận là {val}."

        for log_iss in qc_report.logic_issues:
            if "audience_address=True" in log_iss:
                for s in script.segments:
                    if s.delivery_profile == "REVEAL":
                        s.audience_address = False

        script.status = "DRAFT"
        return script, 600, 1500

    def create_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Deterministic pseudo-embedding based on sha256 byte distribution."""
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Create a 64-dimensional float vector normalized between -1.0 and 1.0
        vec = [(b / 127.5) - 1.0 for b in h] + [(b / 127.5) - 1.0 for b in h]
        return vec[:64]
