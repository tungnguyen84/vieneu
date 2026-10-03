import pytest
from apps.script_factory.models import FullScript, ScriptSegment, StoryBible
from apps.script_factory.timeline_qc import audit_event_timeline, audit_evidence_scope


def test_detects_event_timeline_year_mismatch():
    bible = StoryBible(
        episode_id="EP_TEST",
        title="Bí mật hiến thận",
        protagonist={"name": "Hồng Ngọc"},
        timeline=[
            "Mốc thời gian 1 (Năm 2018): Cha của Hồng Ngọc lâm bệnh nặng, cần ghép thận gấp.",
            "Mốc thời gian 2 (Năm 2019): Hoàng Nam xuất hiện đúng lúc, âm thầm hiến thận cứu sống cha cô.",
        ]
    )
    script = FullScript(
        episode_id="EP_TEST",
        title="Bí mật hiến thận",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="001", text="Chào mừng quý vị. Tôi là Minh."),
            ScriptSegment(id="034", text="Cuốn sổ tay chính thức xác nhận chính Hoàng Nam là người đã đứng trong bóng tối, âm thầm hiến một phần cơ thể mình để cứu sống cha cô vào năm 2018."),
        ]
    )
    fact_conflicts, evidence_issues, requests = audit_event_timeline(script, bible)
    assert any(c["type"] == "TIMELINE_CONFLICT" for c in fact_conflicts)
    assert any("2018" in c["found"] for c in fact_conflicts)


def test_valid_event_timeline_year_passes():
    bible = StoryBible(
        episode_id="EP_TEST",
        title="Bí mật hiến thận",
        protagonist={"name": "Hồng Ngọc"},
        timeline=[
            "Mốc thời gian 1 (Năm 2018): Cha của Hồng Ngọc lâm bệnh nặng, cần ghép thận gấp.",
            "Mốc thời gian 2 (Năm 2019): Hoàng Nam xuất hiện đúng lúc, âm thầm hiến thận cứu sống cha cô.",
        ]
    )
    script = FullScript(
        episode_id="EP_TEST",
        title="Bí mật hiến thận",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="001", text="Chào mừng quý vị. Tôi là Minh."),
            ScriptSegment(id="034", text="Cuốn sổ tay chính thức xác nhận chính Hoàng Nam là người đã âm thầm hiến một phần cơ thể mình để cứu sống cha cô vào năm 2019."),
        ]
    )
    fact_conflicts, evidence_issues, requests = audit_event_timeline(script, bible)
    assert not any(c["type"] == "TIMELINE_CONFLICT" for c in fact_conflicts)


def test_detects_unexplained_relationship_continuity_after_breakup():
    bible = StoryBible(
        episode_id="EP_TEST",
        title="Tiếng còi tàu",
        protagonist={"name": "Vân"},
        timeline=[
            "Tháng 9/2016: Nam chủ động chia tay Trang để kết hôn với Vân.",
            "Tháng 6/2022: Nam tuyển dụng Trang vào công ty, bắt đầu chuỗi ngày ngoại tình.",
        ]
    )
    script = FullScript(
        episode_id="EP_TEST",
        title="Tiếng còi tàu",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="001", text="Chào mừng quý vị. Tôi là Minh."),
            ScriptSegment(id="039", text='"Chúng tôi chưa bao giờ kết thúc từ thời đại học," Trang nói khẽ.'),
        ]
    )
    fact_conflicts, evidence_issues, requests = audit_event_timeline(script, bible)
    assert any(c["type"] == "RELATIONSHIP_TIMELINE_CONTRADICTION" for c in fact_conflicts)


def test_explained_relationship_continuity_passes():
    bible = StoryBible(
        episode_id="EP_TEST",
        title="Tiếng còi tàu",
        protagonist={"name": "Vân"},
        timeline=[
            "Tháng 9/2016: Nam chủ động chia tay Trang để kết hôn với Vân.",
            "Tháng 6/2022: Nam tuyển dụng Trang vào công ty, bắt đầu chuỗi ngày ngoại tình.",
        ]
    )
    script = FullScript(
        episode_id="EP_TEST",
        title="Tiếng còi tàu",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="001", text="Chào mừng quý vị. Tôi là Minh."),
            ScriptSegment(id="039", text='"Chúng tôi chưa bao giờ kết thúc từ thời đại học," Trang nói khẽ trong sự ngộ nhận và tự lừa dối bản thân sau bao năm chia tay.'),
        ]
    )
    fact_conflicts, evidence_issues, requests = audit_event_timeline(script, bible)
    assert not any(c["type"] == "RELATIONSHIP_TIMELINE_CONTRADICTION" for c in fact_conflicts)


def test_detects_will_lifecycle_contradiction():
    bible = StoryBible(episode_id="EP_TEST", title="Di chúc", protagonist={"name": "Thu Ba"})
    script = FullScript(
        episode_id="EP_TEST",
        title="Di chúc",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="010", text="Sau tang lễ, ba anh em mở bức di chúc đầu tiên do người cha để lại chia đều tài sản thành ba phần."),
            ScriptSegment(id="069", text="Anh thừa nhận bản thân đã tìm thấy bản di chúc thật chia đều tài sản cho ba anh em ngay sau khi cha qua đời."),
            ScriptSegment(id="070", text="Nhưng vì sợ... anh đã tiêu hủy nó."),
        ]
    )
    fact_conflicts, evidence_issues, requests = audit_event_timeline(script, bible)
    assert any(c["type"] == "DOCUMENT_LIFECYCLE_CONTRADICTION" for c in fact_conflicts)


def test_detects_unfounded_evidence_leaps():
    bible = StoryBible(episode_id="EP_TEST", title="Hợp đồng", protagonist={"name": "Ngọc"})
    script = FullScript(
        episode_id="EP_TEST",
        title="Hợp đồng",
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id="032", text="Ngọc mở cuốn sổ ghi chép lịch trình điều trị của cha."),
            ScriptSegment(id="034", text="Cuốn sổ tay chính thức xác nhận chính Hoàng Nam là người đã hiến thận cứu cha."),
            ScriptSegment(id="037", text="Bức ảnh chứng minh hoàn toàn không phải là kẻ vô cảm hay thực dụng ích kỷ."),
        ]
    )
    evidence_issues, requests = audit_evidence_scope(script, bible)
    assert len(evidence_issues) == 2
    assert any("hiến thận" in iss["message"] for iss in evidence_issues)
    assert any("bức ảnh" in iss["message"] for iss in evidence_issues)
