import logging

import pytest

from studio.backend.services import live_log


def test_records_are_scoped_to_the_project_and_redacted():
    live_log.install()
    log = logging.getLogger("VieNeu.GeminiProvider")
    log.info("outside any request")  # not captured: no project scope
    with live_log.project_scope("EP_LOG_A", "Viết kịch bản"):
        log.info("→ Gọi gemini-3.8-flash key=AIzaSyDUMMYDUMMYDUMMYDUMMYDUMMY123")
        log.warning("quota hit for sk-abcdefghijklmnopqrstu")
    entries = live_log.read("EP_LOG_A")["entries"]
    messages = [e["message"] for e in entries]
    assert any(m.startswith("▶ Bắt đầu: Viết kịch bản") for m in messages)
    assert any("gemini-3.8-flash" in m for m in messages)
    assert all("AIzaSy" not in m and "sk-abc" not in m for m in messages)
    assert not any("outside any request" in m for m in messages)
    assert live_log.read("EP_LOG_B")["entries"] == []


def test_failure_is_logged_with_reason_and_reraised():
    live_log.install()
    with pytest.raises(ValueError):
        with live_log.project_scope("EP_LOG_C", "Sửa tự động"):
            raise ValueError("Story Bible vẫn chưa đạt")
    last = live_log.read("EP_LOG_C")["entries"][-1]
    assert last["level"] == "ERROR"
    assert "Story Bible vẫn chưa đạt" in last["message"]


def test_since_returns_only_new_entries():
    live_log.install()
    with live_log.project_scope("EP_LOG_D", "x"):
        pass
    first = live_log.read("EP_LOG_D")
    assert live_log.read("EP_LOG_D", since=first["entries"][-1]["seq"])["entries"] == []


def test_running_state_is_reported_only_during_the_request():
    live_log.install()
    with live_log.project_scope("EP_LOG_E", "Viết kịch bản"):
        assert live_log.read("EP_LOG_E")["running"]["action"] == "Viết kịch bản"
    assert live_log.read("EP_LOG_E")["running"] is None


def test_overlapping_jobs_keep_running_until_the_last_finishes():
    live_log.install()
    with live_log.project_scope("EP_LOG_F", "Tạo Cốt truyện"):
        with live_log.project_scope("EP_LOG_F", "Viết kịch bản"):
            assert live_log.read("EP_LOG_F")["running"]["count"] == 2
        assert live_log.read("EP_LOG_F")["running"]["action"] == "Tạo Cốt truyện"
    assert live_log.read("EP_LOG_F")["running"] is None
