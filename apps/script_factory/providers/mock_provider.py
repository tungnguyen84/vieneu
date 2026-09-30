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

        protag = story_bible.protagonist.get("name", "nhân vật chính") if isinstance(story_bible.protagonist, dict) else str(story_bible.protagonist)
        rel = story_bible.relationships if isinstance(story_bible.relationships, str) else "người thân trong gia đình"

        # Determine diverse opening style based on episode seed
        seed = int(hashlib.md5((story_bible.episode_id + story_bible.title).encode()).hexdigest(), 16) % 5
        openers = [
            f"Hòm thư của Sau Cánh Cửa tuần này nhận được một bức tâm thư rất dài từ {protag}, người vừa trải qua một biến cố khiến toàn bộ niềm tin gia đình bị đảo lộn.",
            f"Câu chuyện hôm nay bắt đầu từ một lá thư gửi về chương trình với những dòng chữ run rẩy của {protag}, người đã giữ kín nỗi trăn trở này suốt nhiều năm trời.",
            f"Một buổi tối muộn, hòm thư của Sau Cánh Cửa nhận được những dòng chia sẻ đầy day dứt của {protag} về một bí mật ngỡ như đã mãi ngủ yên trong quá khứ.",
            f"Có những câu chuyện chỉ có thể cất lên thành lời khi người trong cuộc không còn đủ sức gánh vác sự im lặng. Đó là lá thư của {protag} gửi đến chương trình tuần này.",
            f"Chào mừng quý vị và các bạn đã quay trở lại với Sau Cánh Cửa. Hôm nay, Minh xin được chia sẻ cùng quý vị lá thư tâm sự đặc biệt của {protag}."
        ]
        opening_hook = openers[seed]

        fact_vals = [f.value for f in story_bible.critical_facts if f.value]
        fact_phrase = ", ".join(fact_vals) if fact_vals else "100.000.000 VND và 10 năm"

        # Act 1: HOOK (Segs 001 - 005)
        segments.append(ScriptSegment(id="001", speaker=host_id, text=f"{opening_hook} Một bí mật gia đình tưởng chừng đã vĩnh viễn bị chôn vùi nay bất ngờ lộ diện.", delivery_profile="HOOK", importance="high", speed=0.98))
        segments.append(ScriptSegment(id="002", speaker=host_id, text=f"Mọi thứ bắt đầu phát sinh khi {protag} tình cờ chạm tay vào những tài liệu và con số liên quan đến {fact_phrase}, hé lộ sự thật bị che giấu suốt 10 năm qua.", delivery_profile="HOOK", importance="high", speed=0.98))
        segments.append(ScriptSegment(id="003", speaker=host_id, text=f"Trong lá thư gửi về, {protag} nghẹn ngào viết: 'Có những ngày tôi ước mình đừng bao giờ mở chiếc hộp ấy ra, để không phải đối mặt với nỗi nghi ngờ đau đớn này.'", delivery_profile="HOOK", importance="normal", speed=0.98))
        segments.append(ScriptSegment(id="004", speaker=host_id, text=f"Chào mừng quý vị thính giả đã quay trở lại với không gian của Sau Cánh Cửa — nơi chúng ta cùng lắng nghe những uẩn khúc sau mỗi cánh cửa khép kín.", delivery_profile="NORMAL", importance="normal", speed=1.01))
        segments.append(ScriptSegment(id="005", speaker=host_id, text=f"Tôi là {host_name}, người sẽ đồng hành và cùng quý vị lật mở từng trang nhật ký đời thực trong câu chuyện đầy xúc động ngày hôm nay.", delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 2: SETUP & DAILY LIFE (Segs 006 - 016)
        setup_lines = [
            f"Theo lời {protag} chia sẻ trong thư, gia đình từ trước đến nay luôn được chòm xóm ngưỡng mộ bởi sự thuận hòa, êm ấm và nề nếp gia giáo suốt hàng chục năm.",
            f"Mỗi thành viên trong nhà đều có một vị trí vững chãi, luôn quan tâm, đùm bọc lẫn nhau trong từng bữa cơm chiều sau những giờ lao động miệt mài.",
            f"Thế nhưng, đằng sau sự bình yên phẳng lặng ấy, dường như luôn tồn tại một khoảng lặng vô hình mà không ai dám chạm vào trong những cuộc chuyện trò sum họp.",
            f"Đó là những ánh mắt lảng tránh mỗi khi có người vô tình nhắc lại những năm tháng xưa cũ, hay những chuyến đi xa bất chợt mà không rõ nguyên cớ.",
            f"Nếu là quý vị, khi bắt gặp một chi tiết bất thường lặp đi lặp lại của người thân yêu nhất, quý vị sẽ chọn im lặng quan sát hay hỏi thẳng ngay lập tức?", # Seg 010: Audience Address 1
            f"{protag} chọn cách im lặng, tự nhủ rằng có lẽ người thân của mình chỉ đang gánh vác một âu lo thường nhật của cuộc mưu sinh vất vả ngoài xã hội.",
            f"Cuộc sống cứ thế trôi đi trong sự yên ả giả tạo, cho đến một buổi chiều cuối tuần khi {protag} nhận nhiệm vụ dọn dẹp lại căn gác cũ của gia đình.",
            f"Căn gác phủ đầy bụi thời gian, nơi chứa đựng những kỷ vật cũ kỹ từ thời thơ ấu mà đã nhiều năm không một ai trong nhà bước chân lên.",
            f"Và chính tại góc khuất tối tăm ấy, một vật thể không thuộc về trật tự thường ngày đã bất ngờ xuất hiện trước mắt {protag}.",
            f"{protag} viết lại trong thư: 'Bàn tay tôi run lên khi chạm vào lớp bụi phủ trên phong bì niêm phong đã ố vàng, trực giác mách bảo đây không phải điều bình thường.'",
            f"Cảm giác bất an bắt đầu nhen nhóm, phá vỡ hoàn toàn sự thanh thản vốn có bấy lâu trong tâm hồn của người con trong gia đình."
        ]
        for idx, text in enumerate(setup_lines):
            sid = f"{idx + 6:03d}"
            aud = (sid == "010")
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 3: FIRST ANOMALY & MYSTERY (Segs 017 - 028)
        mystery_lines = [
            f"Khi mở phong bì ra, những dòng chữ viết tay mờ nhạt cùng con dấu của một cơ quan lưu trữ địa phương từ 10 năm trước đập vào mắt.",
            f"Đặc biệt, xuất hiện chứng từ giao dịch tài chính ghi rõ khoản tiền 100.000.000 VND kèm theo một bản cam kết bảo mật không được tiết lộ cho bất kỳ ai.",
            f"Câu hỏi lớn nhất lúc này bùng lên dữ dội: Tại sao một gia đình bình dị lại có một khoản giao dịch bí mật lớn đến như vậy trong quá khứ?",
            f"{protag} bàng hoàng đối chiếu mốc thời gian và nhận ra đó chính là giai đoạn gia đình từng trải qua biến cố mà mọi người luôn gọi là tai nạn rủi ro.",
            f"Những lời kể trước đây của người lớn bỗng nhiên xuất hiện vô số lỗ hổng logic không thể nào giải thích một cách hợp lý và thuyết phục được.",
            f"Tại sao người thân trong nhà lại phải giấu giếm {protag} về nguồn gốc số tiền và mối quan hệ thực sự liên quan đến bản cam kết ấy?",
            f"{protag} viết trong thư: 'Tôi đã thức trắng cả đêm hôm đó, nhìn lên trần nhà và tự hỏi người bấy lâu nay mình kính trọng rốt cuộc đang che giấu điều gì?'",
            f"Có lẽ bất cứ ai trong chúng ta khi đứng trước một câu hỏi không lời đáp từ chính mái ấm của mình cũng sẽ cảm thấy chông chênh và hụt hẫng đến nghẹt thở.", # Seg 024: Audience Address 2
            f"Sự nghi ngờ như một hạt mầm độc hại bắt đầu đâm chồi, khiến mọi cử chỉ ân cần thường ngày của người thân bỗng trở nên gượng gạo trong mắt {protag}.",
            f"Mỗi lần chạm mặt trong bữa cơm, {protag} đều cố gắng tìm kiếm một dấu vết chột dạ trên gương mặt người đối diện nhưng chỉ nhận lại sự điềm tĩnh lạ lùng.",
            f"Liệu có phải sự im lặng của họ là để bảo vệ một tội lỗi trong quá khứ, hay đằng sau đó là một uẩn khúc mà họ không thể thốt nên lời?",
            f"{story_bible.mystery_question} Đó chính là câu hỏi thúc đẩy {protag} không thể tiếp tục giả vờ như không biết chuyện gì đã xảy ra."
        ]
        for idx, text in enumerate(mystery_lines):
            sid = f"{idx + 17:03d}"
            aud = (sid == "024")
            prof = "COMMENT" if aud else "MYSTERY"
            speed = 1.025 if aud else 0.96
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 4: ESCALATION & FALSE LEAD (Segs 029 - 042)
        escalation_lines = [
            f"Quyết định không hỏi trực tiếp vì sợ làm bẽ mặt người thân, {protag} bắt đầu tự mình thu thập thêm các mảnh ghép rời rạc còn sót lại trong nhà.",
            f"Một cuốn sổ tay ghi chép sinh hoạt cũ được tìm thấy ở ngăn kéo khóa kín, bên trong có những dòng địa chỉ lạ ở ngoại thành và tên một người xa lạ.",
            f"Cùng lúc đó, những lời bóng gió từ một người hàng xóm lâu năm càng như đổ thêm dầu vào ngọn lửa nghi hoặc đang âm ỉ cháy.",
            f"Người hàng xóm buột miệng kể rằng năm xưa từng thấy một người đàn ông lạ mặt thường xuyên lui tới cổng nhà vào những đêm mưa gió để giao nhận giấy tờ.",
            f"Mọi phán đoán ban đầu của {protag} nhanh chóng bị dẫn dắt theo hướng tiêu cực nhất: {story_bible.false_lead}",
            f"{protag} cho rằng người thân của mình đã phản bội lòng tin gia đình, đem tài sản và tình cảm ra ngoài phục vụ cho một toan tính ích kỷ riêng tư.",
            f"Khi tâm trí chúng ta đã bị phủ bóng bởi một định kiến xấu, con người ta rất dễ biến mọi hành động vô hại của người khác thành bằng chứng buộc tội.", # Seg 036: Audience Address 3
            f"{protag} thừa nhận trong thư: 'Lúc ấy tôi giận dữ đến mức chỉ muốn lao vào đối chất, muốn hét lên đòi lại sự công bằng cho gia đình mình.'",
            f"Nhưng một giọng nói lý trí sâu thẳm đã ngăn {protag} lại, yêu cầu phải có bằng chứng xác thực tuyệt đối trước khi đưa ra lời phán xét cuối cùng.",
            f"Sự dằn vặt giữa tình thương máu mủ và nỗi căm phẫn vì cảm giác bị lừa dối khiến {protag} sút cân và suy sụp tinh thần suốt nhiều tuần lễ.",
            f"Từng cử chỉ chăm sóc của người thân như chén canh nóng hay lời dặn dò giữ ấm nay lại khiến {protag} cảm thấy cay đắng và nặng nề hơn bao giờ hết.",
            f"Mối quan hệ trong gia đình bắt đầu rạn nứt một cách âm thầm, không khí trong nhà trở nên ngột ngạt dù không một lời to tiếng nào được phát ra.",
            f"{protag} tự nhủ rằng mình phải đích thân đi đến tận cùng sự thật, dù sự thật ấy có thể đập tan hoàn toàn ảo tưởng về một mái ấm trọn vẹn.",
            f"Và thế là, một chuyến đi bí mật về miền quê xa — nơi bắt nguồn của dòng địa chỉ trong cuốn sổ cũ — đã được {protag} âm thầm lên kế hoạch thực hiện."
        ]
        for idx, text in enumerate(escalation_lines):
            sid = f"{idx + 29:03d}"
            aud = (sid == "036")
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 5: INVESTIGATION & EVIDENCE CHAIN (Segs 043 - 055)
        investigation_lines = [
            f"Chuyến xe đò đưa {protag} rời thành phố trong một buổi sớm mờ sương, mang theo trĩu nặng những âu lo và dự cảm chẳng lành về điều sắp đối diện.",
            f"Nơi {protag} đặt chân đến là một vùng quê ven sông yên bình, nơi những nếp nhà ngói rêu phong dường như không hề thay đổi sau cả thập kỷ qua.",
            f"Tìm đến đúng địa chỉ ghi trong mảnh giấy, {protag} gặp được một cán bộ hưu trí từng phụ trách công tác lưu trữ hồ sơ của địa phương thời kỳ đó.",
            f"Manh mối thứ hai xuất hiện: {story_bible.clues[1] if len(story_bible.clues) > 1 else 'Lời kể của nhân chứng tại địa phương về người nhận tiền năm xưa.'}",
            f"Khi {protag} nhắc đến tên người thân và số tiền 100.000.000 VND, người cán bộ già bỗng nhìn chăm chú với ánh mắt đầy ngạc nhiên và thương cảm.",
            f"Ông chậm rãi mở chiếc tủ sắt cũ kỹ, lấy ra một tập hồ sơ bệnh án và biên bản xác nhận đã ngả màu vàng theo năm tháng.",
            f"Manh mối thứ ba làm sáng tỏ mọi nghi vấn: {story_bible.clues[2] if len(story_bible.clues) > 2 else 'Chứng từ y tế và biên bản cứu trợ mang tên nhân vật chính.'}",
            f"Những tài liệu gốc chứng minh rằng khoản tiền kia không hề được dùng vào việc mờ ám hay tư lợi cá nhân như {protag} từng cay đắng suy diễn.",
            f"{protag} cầm những trang giấy trên tay, mắt nhòe đi khi nhìn thấy chữ ký của người thân mình run rẩy ở phần cam kết chịu mọi tổn thất kinh tế.",
            f"Từng mảnh ghép của quá khứ 10 năm trước bắt đầu ghép nối lại với nhau, đảo lộn hoàn toàn mọi giả thuyết sai lầm ban đầu trong tâm trí {protag}.",
            f"Người mà {protag} ngỡ là kẻ phản bội thực chất lại là người đã gánh trên vai một gánh nặng khổng lồ mà không một lời kêu ca oán thán.",
            f"Càng đọc sâu vào những biên bản lưu trữ, trái tim của {protag} càng thắt lại vì nỗi ân hận tột cùng đã trót nghi oan cho người ruột thịt.",
            f"Và giây phút then chốt nhất của toàn bộ hành trình tìm kiếm sự thật này cuối cùng cũng đã hiển hiện rõ ràng trước mắt."
        ]
        for idx, text in enumerate(investigation_lines):
            sid = f"{idx + 43:03d}"
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile="MYSTERY", importance="normal", speed=0.96))

        # Act 6: MAJOR REVEAL 1 (Scene 31 / Segs 056 - 064)
        # STRICT RULE: Major Reveal must be delivery_profile='REVEAL', importance='critical', audience_address=False
        segments.append(ScriptSegment(id="056", speaker=host_id, text=f"Và rồi, sự thật lịch sử sau 10 năm giấu kín chính thức được phơi bày qua văn bản có mộc đỏ xác thực.", delivery_profile="REVEAL", importance="critical", speed=0.92, pause_after=0.6))
        segments.append(ScriptSegment(id="057", speaker=host_id, text=f"Tài liệu lưu trữ chính thức khẳng định: {story_bible.reveal_1}", delivery_profile="REVEAL", importance="critical", speed=0.90, pause_after=0.8))
        segments.append(ScriptSegment(id="058", speaker=host_id, text=f"Số tiền 100.000.000 VND và danh tính thực sự không hề là một vụ biển thủ hay phản bội, mà là cái giá để cứu lấy sinh mạng và tương lai của chính {protag}.", delivery_profile="REVEAL", importance="critical", speed=0.92, pause_after=0.6))

        reveal1_fallout = [
            f"Đọc đến đây, {protag} ngồi bệt xuống bậc thềm ủy ban xã, hai hàng nước mắt tuôn rơi không sao kìm nén nổi.",
            f"Hóa ra tai nạn năm xưa nghiêm trọng gấp nhiều lần những gì {protag} được nghe kể khi bình phục trong bệnh viện.",
            f"Để có đủ chi phí phẫu thuật giành giật mạng sống cho con, người thân đã phải bán đi mảnh đất hương hỏa duy nhất và ký cam kết gánh nợ suốt một thập kỷ.",
            f"Lý do họ chọn giữ im lặng và che giấu sự thật là vì không muốn {protag} phải lớn lên trong cảm giác mang tội nợ với gia đình.",
            f"Họ chấp nhận để bản thân chịu tiếng xấu là người tính toán chi li, tằn tiện từng đồng, chỉ để con mình được ngẩng cao đầu bước vào đời một cách thanh thản.",
            f"{protag} viết trong thư gửi Minh: 'Lúc ấy tôi cảm thấy mình là đứa con bất hiếu và nông nổi nhất trên cõi đời này, khi đã đem lòng nghi ngờ người yêu thương mình nhất.'"
        ]
        for idx, text in enumerate(reveal1_fallout):
            sid = f"{idx + 59:03d}"
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 7: SECOND REVEAL & DEEPER TRUTH (Scene 39 / Segs 065 - 074)
        segments.append(ScriptSegment(id="065", speaker=host_id, text=f"Thế nhưng, bức màn bí mật vẫn còn một tầng uẩn khúc sâu sắc hơn nữa: {story_bible.reveal_2}", delivery_profile="REVEAL", importance="critical", speed=0.92))
        
        reveal2_lines = [
            f"Người thân năm ấy thậm chí đã phải giấu đi chính căn bệnh hiểm nghèo của mình để dồn toàn bộ nguồn lực tài chính chữa trị cho {protag}.",
            f"Những lần vắng nhà bí ẩn không phải là đi gặp người tình hay làm ăn mờ ám, mà là những ngày một mình vào viện chạy chữa trong âm thầm.",
            f"Họ sợ rằng nếu nói ra, cả gia đình sẽ suy sụp và {protag} sẽ từ bỏ con đường học vấn đang rộng mở phía trước.",
            f"Sự hy sinh thầm lặng đến tột cùng ấy đã được gói gọn trong chiếc hộp gỗ khóa kín suốt 10 năm trời ròng rã.",
            f"Người cán bộ lưu trữ nắm lấy tay {protag} và nói: 'Bác của cháu từng dặn bác chỉ được giao tập hồ sơ này khi cháu đã đủ trưởng thành và vững vàng trong cuộc sống.'",
            f"Từng lời nói của người xưa như nhát dao cứa vào tâm can, làm tan biến mọi hoài nghi và để lại một niềm biết ơn vô bờ bến.",
            f"{protag} ôm chặt tập hồ sơ vào lòng, vội vã quay trở lại bến xe trong buổi chiều tà để trở về nhà sớm nhất có thể.",
            f"Trong suốt chuyến đi trở về, lòng {protag} chỉ đau đáu một ý nghĩ duy nhất: phải quỳ xuống xin lỗi và ôm lấy người thân trước khi quá muộn.",
            f"Khoảng cách địa lý hàng trăm cây số bỗng trở nên dài vô tận đối với một người con đang mang trong lòng sự ân hận và tình yêu thương dâng trào."
        ]
        for idx, text in enumerate(reveal2_lines):
            sid = f"{idx + 66:03d}"
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile="NORMAL", importance="normal", speed=1.01))

        # Act 8: EMOTIONAL PAYOFF & CONFRONTATION (Segs 075 - 082)
        payoff_lines = [
            f"Cánh cửa nhà mở ra khi ánh đèn vàng trong phòng khách đã được thắp sáng. Người thân đang ngồi cặm cụi đan lại chiếc áo len cũ bên mâm cơm phần.",
            f"Khi {protag} bước vào, đặt tập hồ sơ lên bàn và nghẹn ngào gọi tiếng gọi ruột thịt, người thân khẽ giật mình rồi chậm rãi buông đôi que đan xuống.",
            f"Không có lời trách móc, không có sự giận hờn. Chỉ có một ánh mắt hiền từ bao dung nhìn người con đã thấu hiểu tất cả.",
            f"{story_bible.emotional_payoff}",
            f"Trong cuộc đời này, có những nỗi đau chỉ được chữa lành khi chúng ta đủ dũng cảm để đối diện với sự thật và mở rộng tấm lòng tha thứ cho nhau.", # Seg 078: Audience Address 4
            f"Hai con người ôm lấy nhau trong nước mắt, trút bỏ hoàn toàn gánh nặng tâm lý đè nặng lên mái ấm gia đình suốt cả một thập kỷ qua.",
            f"Mâm cơm nguội hôm ấy bỗng trở nên ấm áp lạ thường, bởi vì từ nay giữa họ không còn bất kỳ bức tường ngăn cách nào nữa.",
            f"{protag} nhận ra rằng tài sản quý giá nhất mà cha mẹ để lại không phải là tiền tài hay đất đai, mà là tình yêu thương vô điều kiện dám hy sinh tất cả."
        ]
        for idx, text in enumerate(payoff_lines):
            sid = f"{idx + 75:03d}"
            aud = (sid == "078")
            prof = "COMMENT" if aud else "NORMAL"
            speed = 1.025 if aud else 1.01
            segments.append(ScriptSegment(id=sid, speaker=host_id, text=text, delivery_profile=prof, importance="normal", audience_address=aud, speed=speed))

        # Act 9: REFLECTION & ENDING (Segs 083 - 088)
        reflection_lines = [
            f"{story_bible.reflection_theme}",
            f"Còn quý vị thính giả, quý vị nghĩ điều gì là quan trọng nhất khi chúng ta nhìn nhận lại những người thân yêu đang ngày ngày lặng lẽ bên cạnh mình?", # Seg 084: Audience Address 5
            f"Đôi khi, sự im lặng của cha mẹ hay người thân không phải là sự xa cách, mà là chiếc áo giáp kiên cố nhất họ dựng lên để che chở cho chúng ta trước bão giông cuộc đời.",
            f"Cảm ơn {protag} đã tin tưởng gửi gắm lá thư tâm sự vô cùng xúc động này đến với Sau Cánh Cửa. Cảm ơn quý thính giả đã dành trọn vẹn thời gian lắng nghe.",
            f"Nếu câu chuyện hôm nay chạm đến trái tim quý vị, đừng quên bấm chia sẻ và để lại những suy nghĩ của mình ở phần bình luận bên dưới.",
            f"Tôi là Minh. Xin kính chúc quý vị và gia đình một buổi tối an lành, ấm áp và trọn vẹn yêu thương. Hẹn gặp lại quý vị trong tập tiếp theo của Sau Cánh Cửa."
        ]
        for idx, text in enumerate(reflection_lines):
            sid = f"{idx + 83:03d}"
            aud = (sid == "084")
            prof = "COMMENT" if idx < 3 else "ENDING"
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
