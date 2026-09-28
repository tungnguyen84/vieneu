"""Test for FlowKitAdapter in VieNeu TTS."""
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.visual_engine.flowkit_adapter import FlowKitAdapter


def test_flowkit_connection_status():
    adapter = FlowKitAdapter("http://127.0.0.1:8100")
    status = adapter.get_connection_status()

    print("\n" + "=" * 60)
    print("🎯 TEST FLOWKIT ADAPTER CONNECTION STATUS")
    print("=" * 60)
    print(f"FlowKit Server Running:  {status.flowkit_server_running}")
    print(f"Chrome Extension:        {status.extension_connected} (v{status.extension_version})")
    print(f"Flow Tab Ready:          {status.flow_tab_ready}")
    print(f"Account Session Ready:   {status.account_session_ready}")
    print(f"Session Project ID:      {status.flow_project_id}")
    print(f"Overall Connected:       {status.is_connected}")

    assert status.flowkit_server_running is True, "FlowKit server chưa chạy trên port 8100"
    assert status.extension_connected is True, "Chrome/Cốc Cốc Extension chưa kết nối"
    assert status.is_connected is True, "Toàn bộ chuỗi kết nối VieNeu ↔ FlowKit ↔ Extension chưa sẵn sàng"
    print("✅ PASS: Kết nối VieNeu ↔ FlowKit ↔ Extension ↔ Google Flow hoạt động 100%!")


if __name__ == "__main__":
    test_flowkit_connection_status()
