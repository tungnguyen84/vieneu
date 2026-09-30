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
    default_model: Optional[str] = None

    def __init__(self, default_model: Optional[str] = None, **kwargs):
        self.default_model = default_model

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
        user_topic: Optional[str] = None,
        topic_intent: Optional[Any] = None,
    ) -> Tuple[List[IdeaItem], int, int]:
        from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent

        topic_intent_obj = None
        if isinstance(topic_intent, TopicIntent):
            topic_intent_obj = topic_intent
        elif isinstance(topic_intent, dict):
            topic_intent_obj = TopicIntent.from_dict(topic_intent)
        elif user_topic:
            topic_intent_obj = extract_topic_intent(user_topic)

        existing_count = len(existing_ideas)
        ideas: List[IdeaItem] = []

        for i in range(count):
            idx = (existing_count + i)
            theme_idx = idx % len(self.SAMPLE_THEMES)
            title_base, hook_arch, div_cat, protag, rel, secret = self.SAMPLE_THEMES[theme_idx]

            idea_id = f"IDEA_{idx + 1:03d}"

            if topic_intent_obj:
                orig = topic_intent_obj.original_topic
                req1 = topic_intent_obj.required_semantic_elements[0] if topic_intent_obj.required_semantic_elements else orig
                ctx = topic_intent_obj.context
                title = f"{orig} #{idx + 1} - Góc khuất {protag}"
                hook_text = f"Tại {ctx}, {protag} bất ngờ phát hiện dấu hiệu mờ ám liên quan đến {req1} giữa {rel.lower()}..."
                secret_text = f"Bí mật {req1} tại {ctx}: {secret}"
                rev2 = f"Chân tướng sự việc về {req1} tại {ctx} không như định kiến ban đầu: {secret.lower()}"
                adherence_score = 95.0
            else:
                title = f"{title_base} #{idx + 1}"
                hook_text = f"Khi dọn dẹp căn phòng cũ, {protag} bất ngờ tìm thấy một bí mật mà {rel.lower()} đã che giấu suốt nhiều năm..."
                secret_text = secret
                rev2 = f"Bí mật {secret.lower()}"
                adherence_score = 100.0

            clue1 = f"Dấu vết chữ viết tay và con dấu đã mờ trên phong bì cũ."
            clue2 = f"Lời khai mâu thuẫn của những người hàng xóm lớn tuổi."
            clue3 = f"Giấy tờ chứng từ xác thực tại cơ quan lưu trữ địa phương."
            rev1 = f"Người tưởng như xa lạ thực chất lại là người có quan hệ mật thiết."
            payoff = f"{protag} đối thoại trực tiếp trong nước mắt, tháo gỡ hiểu lầm sâu nặng bấy lâu."
            reflection = f"Đằng sau cánh cửa đóng kín, sự thật dù bất ngờ nhưng mở ra lối thoát cho những người trong cuộc."

            item = IdeaItem(
                idea_id=idea_id,
                working_title=title,
                hook=hook_text,
                protagonist=protag,
                relationship=rel,
                central_secret=secret_text,
                mystery_question=f"Tại sao sự việc lại bị che giấu suốt từng ấy năm?",
                false_lead=f"Ban đầu {protag} nghi ngờ có sự phản bội lợi ích cá nhân.",
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
                novelty_score=8.8,
                original_user_topic=topic_intent_obj.original_topic if topic_intent_obj else None,
                topic_intent=topic_intent_obj.to_dict() if topic_intent_obj else None,
                topic_adherence_score=adherence_score if topic_intent_obj else None,
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
            ending="Câu chuyện khép lại với niềm tin và sự hàn gắn.",
            causal_chains=[
                {
                    "target": "reveal_1",
                    "cause": "Biến cố tai nạn nguy kịch 10 năm trước đòi hỏi chi phí phẫu thuật khẩn cấp.",
                    "decision": "Người thân quyết định bán mảnh đất hương hỏa và ký cam kết bảo mật khoản tiền 100.000.000 VND.",
                    "action": str(idea.reveal_1) if len(str(idea.reveal_1 or "").strip()) >= 8 else f"Thực hiện cam kết hành động: {idea.reveal_1 or 'Giao dịch cứu trợ'}",
                    "consequence": f"{idea.protagonist} được cứu sống nhưng hiểu lầm về khoản giao dịch khi phát hiện phong bì cũ.",
                    "why": "Bảo vệ sinh mạng và tương lai của người con mà không tạo mặc cảm mắc nợ.",
                    "motivation": "Không thể công khai vào thời điểm đó vì sức khỏe tâm lý của nhân vật chính chưa ổn định, giải pháp thông thường là bất khả thi.",
                    "how": "Lưu giữ chứng từ gốc tại cơ quan lưu trữ địa phương suốt 10 năm.",
                },
                {
                    "target": "reveal_2",
                    "cause": "Người thân đồng thời phát hiện bệnh nặng nhưng nguồn tài chính gia đình chỉ đủ cứu một người.",
                    "decision": "Giấu kín bệnh tình cá nhân để dồn toàn bộ 100.000.000 VND cho ca phẫu thuật của con.",
                    "action": str(idea.reveal_2) if len(str(idea.reveal_2 or "").strip()) >= 8 else f"Hành động then chốt giữ bí mật: {idea.reveal_2 or 'Khóa hồ sơ bệnh án'}",
                    "consequence": "Người cán bộ lưu trữ giữ lời hứa chỉ tiết lộ khi nhân vật chính đã trưởng thành.",
                    "why": "Tránh để gia đình suy sụp và con cái bỏ dở việc học hành.",
                    "motivation": "Nếu nói thật ngay lúc đó, nhân vật chính sẽ từ chối phẫu thuật; do đó buộc phải giữ kín hoàn toàn.",
                    "how": "Duy trì qua sự phối hợp giữ bí mật của cán bộ lưu trữ địa phương.",
                },
            ],
            knowledge_ledger=[
                {
                    "character": idea.protagonist,
                    "who_knows_what": "Ban đầu chỉ thấy phong bì niêm phong và nghi ngờ có khuất tất tài chính.",
                    "when_they_learned_it": "Khi gặp cán bộ lưu trữ và mở hồ sơ ở Hồi 6 - Hồi 7.",
                    "how_they_learned_it": "Qua chuỗi 3 manh mối và biên bản xác nhận tại địa phương.",
                    "knowledge_scope": "none",
                },
                {
                    "character": "Người thân",
                    "who_knows_what": "Nắm rõ toàn bộ nguyên nhân khoản tiền 100.000.000 VND và cam kết 10 năm trước.",
                    "when_they_learned_it": "Ngay từ thời điểm xảy ra biến cố 10 năm trước.",
                    "how_they_learned_it": "Trực tiếp ký cam kết và thực hiện sự hy sinh.",
                    "knowledge_scope": "full",
                },
            ],
            structured_clues=[
                {
                    "clue": idea.clue_1,
                    "what_it_proves": "Chứng minh có một giao dịch 100.000.000 VND từ 10 năm trước được cất giữ kín đáo.",
                    "what_it_does_NOT_prove": "Chưa chứng minh được mục đích tiêu cực hay hành vi phản bội lợi ích gia đình.",
                    "next_question": "Khoản tiền này được chuyển cho ai và nhằm mục đích gì?",
                },
                {
                    "clue": idea.clue_2,
                    "what_it_proves": "Chứng minh có nhân chứng tại địa phương biết về hoàn cảnh giao nhận hồ sơ năm xưa.",
                    "what_it_does_NOT_prove": "Chưa hé lộ nội dung chi tiết bên trong tập hồ sơ lưu trữ.",
                    "next_question": "Tập hồ sơ lưu trữ tại địa phương ghi nhận sự việc gì?",
                },
                {
                    "clue": idea.clue_3,
                    "what_it_proves": "Xác nhận khoản tiền 100.000.000 VND dùng để cứu chữa cho chính nhân vật chính.",
                    "what_it_does_NOT_prove": "Bác bỏ hoàn toàn giả thuyết sai ban đầu về sự phản bội.",
                    "next_question": "Vì sao người thân phải giấu kín sự hy sinh này suốt 10 năm?",
                },
            ],
            reveal_justifications={
                "reveal_1": {
                    "evidence_support": "Được chứng minh bởi chứng từ giao dịch (Manh mối 1) và hồ sơ lưu trữ (Manh mối 3).",
                    "motivation_support": "Nhằm cứu sống nhân vật chính mà không để lại gánh nặng tâm lý.",
                    "timeline_support": "Khớp chính xác với mốc biến cố 10 năm trước.",
                },
                "reveal_2": {
                    "evidence_support": "Được chứng minh bởi bệnh án cũ và lời xác nhận của cán bộ lưu trữ.",
                    "motivation_support": "Tình thế bắt buộc vì nguồn lực tài chính lúc đó chỉ đủ cứu một người.",
                    "character_knowledge_support": "Nhất quán với sổ cái nhận thức: chỉ người thân và cán bộ lưu trữ biết.",
                },
            },
            original_user_topic=idea.original_user_topic or (idea.topic_intent.get("original_topic") if idea.topic_intent else None),
            topic_intent=idea.topic_intent,
            topic_adherence=idea.topic_adherence_score if idea.topic_adherence_score is not None else 100.0,
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

        protag = story_bible.protagonist.get("name", "nhân vật chính") if isinstance(story_bible.protagonist, dict) else str(story_bible.protagonist)
        rel = story_bible.relationships if isinstance(story_bible.relationships, str) else "người thân trong gia đình"

        # Determine diverse opening style based on episode seed
        seed = int(hashlib.md5((story_bible.episode_id + story_bible.title).encode()).hexdigest(), 16) % 5
        openers = [
            f"Hòm thư của Sau Cánh Cửa tuần này nhận được một bức tâm thư rất dài từ {protag}, người vừa trải qua một biến cố khiến toàn bộ niềm tin gia đình bị đảo lộn.",
            f"Câu chuyện hôm nay bắt đầu từ một lá thư gửi về chương trình với những dòng chữ run rẩy của {protag}, người đã giữ kín nỗi trăn trở này suốt nhiều năm trời.",
            f"Một buổi tối muộn, hòm thư của Sau Cánh Cửa nhận được những dòng chia sẻ đầy day dứt của {protag} về một bí mật ngỡ như đã mãi ngủ yên trong quá khứ.",
            f"Một lá thư dày đặc những dòng chữ viết tay của {protag} vừa được gửi tới bàn biên tập chương trình sau nhiều tháng ngày trăn trở.",
            f"Hôm nay, Minh xin được chia sẻ cùng quý vị lá thư tâm sự đặc biệt của {protag} gửi về từ một vùng quê yên bình."
        ]
        opening_hook = openers[seed]

        fact_vals = [f.value for f in story_bible.critical_facts if f.value]
        fact_phrase = ", ".join(fact_vals) if fact_vals else "100.000.000 VND và 10 năm"

        # Act 1: HOOK (Segs 001 - 005)
        segments.append(ScriptSegment(id="001", speaker=host_id, text=f"{opening_hook} Một bí mật gia đình tưởng chừng đã vĩnh viễn bị chôn vùi nay bất ngờ lộ diện.", delivery_profile="HOOK", importance="high", speed=0.98))
        segments.append(ScriptSegment(id="002", speaker=host_id, text=f"Mọi thứ bắt đầu phát sinh khi {protag} tình cờ chạm tay vào những tài liệu và con số liên quan đến {fact_phrase}, hé lộ sự thật bị che giấu suốt 10 năm qua.", delivery_profile="HOOK", importance="high", speed=0.98))
        segments.append(ScriptSegment(id="003", speaker=host_id, text=f"Trong lá thư gửi về, {protag} nghẹn ngào viết: 'Có những ngày tôi ước mình đừng bao giờ mở chiếc hộp ấy ra, để không phải đối mặt với nỗi nghi ngờ này.'", delivery_profile="HOOK", importance="normal", speed=0.98))
        segments.append(ScriptSegment(id="004", speaker=host_id, text="Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.", delivery_profile="NORMAL", importance="normal", speed=1.01))
        segments.append(ScriptSegment(id="005", speaker=host_id, text=f"Tôi là {host_name}, người sẽ đồng hành và cùng quý vị lật mở từng trang nhật ký đời thực trong câu chuyện ngày hôm nay.", delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 2: SETUP & DAILY LIFE (Segs 006 - 016)
        setup_lines = [
            f"Theo lời {protag} chia sẻ trong lá thư gửi về chương trình, tổ ấm nhỏ từ trước đến nay luôn được chòm xóm xung quanh quý mến bởi sự thuận hòa, êm ấm và nề nếp gia phong suốt hàng chục năm qua.",
            f"Mỗi thành viên trong nhà đều có một vị trí vững chãi, luôn quan tâm, đùm bọc lẫn nhau trong từng bữa cơm chiều sau những giờ lao động miệt mài.",
            f"Thế nhưng, đằng sau sự bình yên phẳng lặng ấy, dường như luôn tồn tại một khoảng lặng mà không ai dám chạm vào trong những cuộc chuyện trò sum họp.",
            f"Đó là những ánh mắt lảng tránh mỗi khi có người vô tình nhắc lại những năm tháng xưa cũ, hay những chuyến đi xa bất chợt mà không rõ nguyên cớ.",
            f"Nếu là quý vị, khi bắt gặp một chi tiết bất thường lặp đi lặp lại của người thân yêu nhất, quý vị sẽ chọn im lặng quan sát hay hỏi thẳng ngay lập tức?", # Seg 010: Audience Address 1
            f"{protag} chọn cách im lặng, tự nhủ rằng có lẽ người thân của mình chỉ đang gánh vác một âu lo thường nhật của cuộc mưu sinh vất vả ngoài xã hội.",
            f"Cuộc sống cứ thế trôi đi trong sự yên ả, cho đến một buổi chiều cuối tuần khi {protag} nhận nhiệm vụ dọn dẹp lại căn gác cũ của gia đình.",
            f"Căn gác phủ đầy bụi thời gian, nơi chứa đựng những kỷ vật cũ kỹ từ thời thơ ấu mà đã nhiều năm không một ai trong nhà bước chân lên.",
            f"Và chính tại góc khuất ấy, một vật thể không thuộc về trật tự thường ngày đã bất ngờ xuất hiện trước mắt {protag}.",
            f"{protag} viết lại trong thư: 'Bàn tay tôi run lên khi chạm vào lớp bụi phủ trên phong bì niêm phong đã ố vàng, trực giác mách bảo đây không phải điều bình thường.'",
            f"Cảm giác bất an bắt đầu nhen nhóm, làm xáo trộn sự thanh thản vốn có bấy lâu trong tâm hồn của người con trong gia đình."
        ]
        for idx, text in enumerate(setup_lines):
            sid = f"{idx + 6:03d}"
            aud = (sid == "010")
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 3: FIRST ANOMALY & MYSTERY (Segs 017 - 028)
        mystery_lines = [
            f"Khi mở phong bì niêm phong ra, những dòng chữ viết tay mờ nhạt cùng con dấu mộc đỏ của một cơ quan lưu trữ địa phương từ 10 năm trước dần hiện ra một cách rõ nét trước mắt.",
            f"Đặc biệt, xuất hiện chứng từ giao dịch tài chính ghi rõ khoản tiền 100.000.000 VND kèm theo một bản cam kết bảo mật giữa những người trực tiếp ký tên.",
            f"Câu hỏi lớn nhất lúc này nảy sinh: Tại sao một gia đình bình dị lại có một khoản giao dịch lớn đến như vậy trong quá khứ?",
            f"{protag} đối chiếu mốc thời gian và nhận ra đó chính là giai đoạn gia đình từng trải qua biến cố mà mọi người luôn gọi là tai nạn rủi ro.",
            f"Những lời kể trước đây của người lớn bỗng nhiên xuất hiện những điểm chưa khớp về mốc thời gian và nguồn gốc số tiền.",
            f"Tại sao người thân trong nhà lại phải giấu {protag} về nguồn gốc số tiền và mối quan hệ thực sự liên quan đến bản cam kết ấy?",
            f"{protag} viết trong thư: 'Tôi đã thức trắng cả đêm hôm đó, nhìn lên trần nhà và tự hỏi người bấy lâu nay mình kính trọng rốt cuộc đang giấu điều gì?'",
            f"Có lẽ bất cứ ai trong chúng ta khi đứng trước một câu hỏi không lời đáp từ chính mái ấm của mình cũng sẽ cảm thấy chông chênh và trăn trở.", # Seg 024: Audience Address 2
            f"Sự hoài nghi bắt đầu lớn dần, khiến mọi cử chỉ ân cần thường ngày của người thân bỗng trở nên xa lạ trong mắt {protag}.",
            f"Mỗi lần chạm mặt trong bữa cơm, {protag} đều cố gắng tìm kiếm một dấu vết bối rối trên gương mặt người đối diện nhưng chỉ nhận lại sự điềm tĩnh.",
            f"Liệu có phải sự im lặng của họ là để che đậy một sai lầm trong quá khứ, hay đằng sau đó là một uẩn khúc mà họ chưa thể nói ra?",
            f"{story_bible.mystery_question} Đó chính là câu hỏi thúc đẩy {protag} quyết tâm đi tìm câu trả lời xác thực."
        ]
        for idx, text in enumerate(mystery_lines):
            sid = f"{idx + 17:03d}"
            aud = (sid == "024")
            prof = "COMMENT" if aud else "MYSTERY"
            speed = 1.025 if aud else 0.96
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 4: ESCALATION & FALSE LEAD (Segs 029 - 042)
        escalation_lines = [
            f"Quyết định tạm thời chưa hỏi trực tiếp vì sợ làm tổn thương người thân trong nhà, {protag} bắt đầu tự mình cẩn thận thu thập thêm các mảnh ghép dữ liệu còn sót lại.",
            f"Một cuốn sổ tay ghi chép sinh hoạt cũ được tìm thấy ở ngăn kéo khóa kín, bên trong có những dòng địa chỉ ở ngoại thành và tên một người cán bộ lưu trữ.",
            f"Cùng lúc đó, những lời kể rời rạc từ một người hàng xóm lâu năm càng khiến nỗi băn khoăn trong lòng {protag} tăng lên.",
            f"Người hàng xóm nhớ lại rằng năm xưa từng thấy một người đàn ông mang cặp hồ sơ lui tới cổng nhà vào những buổi chiều muộn để trao đổi giấy tờ.",
            f"Mọi phán đoán ban đầu của {protag} nhanh chóng bị dẫn dắt theo hướng tiêu cực: {story_bible.false_lead}",
            f"{protag} ngỡ rằng người thân của mình đã làm điều khuất tất, đem tài sản gia đình ra ngoài phục vụ cho một mục đích riêng tư.",
            f"Khi tâm trí chúng ta đang bị chi phối bởi nỗi nghi ngờ, con người ta rất dễ suy diễn những hành động bình thường theo hướng tiêu cực.", # Seg 036: Audience Address 3
            f"{protag} thừa nhận trong thư: 'Lúc ấy tôi bức xúc đến mức chỉ muốn hỏi thẳng ngay lập tức để làm rõ trắng đen.'",
            f"Nhưng lý trí đã giữ {protag} lại, nhắc nhở rằng cần phải tìm hiểu tận gốc chứng từ trước khi đưa ra bất kỳ nhận định nào.",
            f"Sự giằng xé giữa tình thương máu mủ và nỗi hoài nghi khiến {protag} mất ngủ suốt nhiều đêm liền.",
            f"Từng cử chỉ chăm sóc của người thân như bát canh nóng hay lời dặn dò giữ ấm đều khiến {protag} vừa thương vừa trăn trở.",
            f"Không khí trong những bữa cơm gia đình trầm lắng hẳn đi, mỗi người đều theo đuổi những suy nghĩ riêng chưa thể giãi bày.",
            f"{protag} tự nhủ rằng mình cần phải đích thân đi xác minh nguồn gốc tập chứng từ để tháo gỡ nút thắt này.",
            f"Và thế là, một chuyến đi về miền quê ngoại thành — nơi có địa chỉ ghi trong cuốn sổ cũ — đã được {protag} thực hiện vào sáng hôm sau."
        ]
        for idx, text in enumerate(escalation_lines):
            sid = f"{idx + 29:03d}"
            aud = (sid == "036")
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 5: INVESTIGATION & EVIDENCE CHAIN (Segs 043 - 055)
        investigation_lines = [
            f"Chuyến xe khách liên tỉnh đưa {protag} rời khỏi thành phố trong một buổi sớm mờ sương, mang theo trong lòng biết bao nhiêu câu hỏi ngổn ngang về chuyện quá khứ.",
            f"Nơi {protag} đặt chân đến là một vùng quê ven sông yên tĩnh, nơi những nếp nhà ngói cũ gần như vẫn giữ nguyên dáng vẻ của mười năm trước.",
            f"Tìm đến đúng địa chỉ ghi trong sổ, {protag} gặp được người cán bộ hưu trí từng phụ trách công tác lưu trữ hồ sơ của địa phương thời kỳ đó.",
            f"Manh mối thứ hai được làm rõ: {story_bible.clues[1] if len(story_bible.clues) > 1 else 'Lời kể của nhân chứng tại địa phương về người nhận tiền năm xưa.'}",
            f"Khi {protag} nhắc đến tên người thân và số tiền 100.000.000 VND, người cán bộ già trầm ngâm nhìn thật lâu rồi khẽ thở dài.",
            f"Ông chậm rãi mở chiếc tủ sắt cũ kỹ, lấy ra một tập hồ sơ bệnh án và biên bản xác nhận đã ngả màu vàng theo năm tháng.",
            f"Manh mối thứ ba làm sáng tỏ mọi nghi vấn: {story_bible.clues[2] if len(story_bible.clues) > 2 else 'Chứng từ y tế và biên bản cứu trợ mang tên nhân vật chính.'}",
            f"Những tài liệu gốc cho thấy khoản tiền kia không hề được dùng vào việc mờ ám hay tư lợi cá nhân như {protag} từng suy diễn.",
            f"{protag} cầm những trang giấy trên tay, mắt nhòe đi khi nhìn thấy chữ ký của người thân mình ở phần cam kết thanh toán chi phí.",
            f"Từng mảnh ghép của quá khứ 10 năm trước bắt đầu khớp lại với nhau, bác bỏ hoàn toàn giả thuyết sai lầm ban đầu của {protag}.",
            f"Người mà {protag} từng nghi ngờ thực chất lại là người đã âm thầm gánh vác toàn bộ biến cố năm ấy.",
            f"Càng đọc kỹ những dòng biên bản lưu trữ, {protag} càng thấm thía nỗi ân hận vì đã vội vàng trách lầm người ruột thịt.",
            f"Và toàn bộ câu chuyện phía sau biến cố mười năm trước cuối cùng đã hiện lên rõ ràng trên từng trang giấy."
        ]
        for idx, text in enumerate(investigation_lines):
            sid = f"{idx + 43:03d}"
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile="MYSTERY", importance="normal", speed=0.96))

        # Act 6: MAJOR REVEAL 1 (Scene 31 / Segs 056 - 064)
        segments.append(ScriptSegment(id="056", speaker=host_id, text="Sự thật sau 10 năm giấu kín chính thức được xác nhận qua tập hồ sơ lưu trữ có dấu mộc của cơ quan địa phương.", delivery_profile="REVEAL", importance="critical", speed=0.92, pause_after=0.6))
        segments.append(ScriptSegment(id="057", speaker=host_id, text=f"Tài liệu lưu trữ xác nhận rõ: {story_bible.reveal_1}", delivery_profile="REVEAL", importance="critical", speed=0.90, pause_after=0.8))
        segments.append(ScriptSegment(id="058", speaker=host_id, text=f"Số tiền 100.000.000 VND không phải là một vụ biển thủ hay phản bội, mà là khoản chi phí phẫu thuật khẩn cấp để cứu lấy sinh mạng của chính {protag}.", delivery_profile="REVEAL", importance="critical", speed=0.92, pause_after=0.6))

        reveal1_fallout = [
            f"Đọc đến đây, {protag} ngồi lặng xuống chiếc ghế gỗ dài nơi hàng hiên nhà ngói, hai bàn tay run rẩy nắm chặt tập hồ sơ bệnh án đã ố vàng theo năm tháng.",
            f"Hóa ra tai nạn năm xưa nghiêm trọng hơn rất nhiều so với những gì {protag} được nghe kể khi tỉnh lại trong bệnh viện.",
            f"Do tình thế cấp bách và bác sĩ yêu cầu tránh mọi kích động tâm lý cho bệnh nhân sau mổ, người thân buộc phải ký cam kết bảo mật hồ sơ và bán mảnh đất hương hỏa để lo viện phí.",
            f"Giải pháp thông thường là không thể thực hiện vì nếu biết gia đình phải bán đất và gánh nợ lớn, {protag} lúc đó sẽ suy sụp và từ chối điều trị.",
            f"Họ chấp nhận chịu tiếng là người tính toán chi li, tằn tiện từng đồng suốt mười năm, chỉ để con mình yên tâm học tập và trưởng thành.",
            f"{protag} viết trong thư gửi Minh: 'Lúc ấy tôi chỉ biết ngồi lặng đi vì thương và ân hận khi nhớ lại những lời trách móc vô tâm của mình.'"
        ]
        for idx, text in enumerate(reveal1_fallout):
            sid = f"{idx + 59:03d}"
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 7: SECOND REVEAL & DEEPER TRUTH (Scene 39 / Segs 065 - 074)
        segments.append(ScriptSegment(id="065", speaker=host_id, text=f"Bên dưới tập biên bản tài chính, một bệnh án cũ khác tiếp tục hé lộ nguyên nhân sâu xa thứ hai: {story_bible.reveal_2}", delivery_profile="REVEAL", importance="critical", speed=0.92))
        
        reveal2_lines = [
            f"Người thân năm ấy thậm chí đã phải chủ động hoãn lại ca phẫu thuật quan trọng của chính mình vì nguồn tiền mặt lúc đó trong gia đình chỉ đủ cứu duy nhất một người.",
            f"Những lần vắng nhà định kỳ không phải là đi làm ăn khuất tất, mà là những buổi vào bệnh viện tuyến huyện nhận thuốc điều trị cầm chừng.",
            f"Họ buộc phải giữ kín chuyện này với các con vì không còn lựa chọn nào khác để bảo toàn sự bình yên cho gia đình.",
            f"Toàn bộ chứng từ viện phí và đơn thuốc đều được gửi nhờ tại tủ hồ sơ của người cán bộ lưu trữ suốt 10 năm qua.",
            f"Người cán bộ già đặt tay lên vai {protag} và nói: 'Người nhà của cháu từng dặn bác chỉ được trao lại tập giấy này khi cháu đã lập nghiệp vững vàng.'",
            f"Lời dặn dò giản dị ấy giải thích trọn vẹn mọi khoảng lặng và những ánh mắt lảng tránh trong suốt một thập kỷ qua.",
            f"{protag} cẩn thận cất tập hồ sơ vào túi áo, cúi đầu cảm ơn người cán bộ rồi vội vã ra bến xe để trở về nhà.",
            f"Suốt chặng đường quay về thành phố, {protag} chỉ mong sớm được bước qua cánh cửa nhà để nói một lời xin lỗi chân thành.",
            f"Chuyến xe chiều lăn bánh qua những cánh đồng lúa, đưa người con trở về với mái ấm sau khi mọi nút thắt đã được tháo gỡ."
        ]
        for idx, text in enumerate(reveal2_lines):
            sid = f"{idx + 66:03d}"
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 8: EMOTIONAL PAYOFF & CONFRONTATION (Segs 075 - 084)
        payoff_lines = [
            f"Cánh cửa căn nhà nhỏ mở ra khi ánh đèn vàng ấm áp trong phòng khách vừa bật sáng. Người thân trong gia đình đang ngồi cặm cụi xếp lại những tấm áo cũ bên cạnh bàn ăn quen thuộc.",
            f"Khi {protag} bước vào, đặt tập hồ sơ lên bàn và gọi một tiếng nghẹn ngào, người thân khẽ dừng tay rồi ngước nhìn bằng ánh mắt hiền từ.",
            f"Không có lời trách móc hay giận hờn, chỉ có cái nắm tay thật chặt giữa hai thế hệ sau mười năm giữ kín nỗi niềm.",
            f"{story_bible.emotional_payoff}",
            f"Hai con người ngồi lại bên mâm cơm chiều đạm bạc, lần đầu tiên cùng nhau trò chuyện một cách cởi mở và thẳng thắn về toàn bộ biến cố đau thương của mười năm về trước.",
            f"Những hiểu lầm nặng nề bấy lâu được tháo gỡ bằng sự lắng nghe và sẻ chia chân thành giữa những người ruột thịt.",
            f"{protag} chủ động sắp xếp lại lịch khám sức khỏe định kỳ để trực tiếp đồng hành và chăm sóc người thân trong những năm tháng tới.",
            f"Căn nhà nhỏ trở lại với sự bình yên vốn có, nhưng giờ đây là sự bình yên của những con người đã thực sự thấu hiểu nhau.",
            f"Buổi tối ấm áp hôm ấy khép lại bằng tiếng cười nhẹ nhàng bên ấm trà sen nóng, chính thức khép lại trọn vẹn một hành trình mười năm mang nặng biết bao nỗi niềm trăn trở.",
            f"Những tờ chứng từ cũ được cất lại vào ngăn tủ gỗ như một kỷ vật nhắc nhớ về tình thương và trách nhiệm trong gia đình."
        ]
        for idx, text in enumerate(payoff_lines):
            sid = f"{idx + 75:03d}"
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile="NORMAL", importance="normal", audience_address=False, speed=1.01))

        # Act 9: CONCISE REFLECTION & ENDING (Segs 085 - 088 -> 4 segments = 4.5%)
        reflection_lines = [
            f"{story_bible.reflection_theme}",
            f"Còn quý vị thính giả, nếu đứng trước một sự im lặng đầy hy sinh như thế, quý vị sẽ nói điều gì đầu tiên với người thân của mình?", # Seg 086: Audience Address 4
            f"Cảm ơn {protag} đã tin tưởng gửi lá thư tâm sự này đến với chương trình.",
            f"Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại."
        ]
        for idx, text in enumerate(reflection_lines):
            sid = f"{idx + 85:03d}"
            aud = (sid == "086")
            prof = "COMMENT" if idx < 2 else ("NORMAL" if idx == 2 else "ENDING")
            speed = 1.025 if aud else (0.965 if prof == "ENDING" else 1.01)
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

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
        from apps.script_factory.script_qc import ScriptQCEngine
        report = ScriptQCEngine.audit_script(script, story_bible, story_formula, series_bible)
        return report, 1200, 450

    def revise_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        qc_report: QCReport,
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        from apps.script_factory.script_qc import apply_targeted_repairs

        script.revision_round += 1
        script = apply_targeted_repairs(script, story_bible, qc_report)

        for conflict in qc_report.fact_conflicts:
            ctype = conflict.get("type", "") if isinstance(conflict, dict) else ""
            if ctype in (
                "HOOK_FACT_CONTRADICTION",
                "CHARACTER_FACT_VIOLATION",
                "UNGROUNDED_CHARACTER_HALLUCINATION",
                "BLOCKED_PREMATURE_REVEAL",
                "CAUSAL_GAP",
                "CHARACTER_KNOWLEDGE_CONTRADICTION",
                "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                "INTERNAL_EPISODE_ID_SPOKEN",
            ):
                continue
            val = (conflict.get("expected") or conflict.get("value")) if isinstance(conflict, dict) else str(conflict)
            if script.segments and val and isinstance(val, str):
                target_idx = min(2, len(script.segments) - 1)
                if val.lower() not in script.segments[target_idx].text.lower():
                    script.segments[target_idx].text += f" Con số và dữ kiện chính xác được xác nhận là {val}."

        script.status = "DRAFT"
        return script, 600, 1500

    def create_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Deterministic pseudo-embedding based on sha256 byte distribution."""
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Create a 64-dimensional float vector normalized between -1.0 and 1.0
        vec = [(b / 127.5) - 1.0 for b in h] + [(b / 127.5) - 1.0 for b in h]
        return vec[:64]
