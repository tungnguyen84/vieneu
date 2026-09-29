"""Google Flow Service for JSON Export and Instruction Delivery."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.visual_pilot_03_v1_0a.google_flow_exporter import export_google_flow_app_json

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
EXPORTS_DIR = BASE_DIR / "production_pilot_03_visual_v1_0a" / "exports"


class FlowService:
    def __init__(self):
        pass

    def get_export_info(self, project_id: str) -> Dict[str, Any]:
        export_file = EXPORTS_DIR / f"{project_id}_google_flow.json"
        combined_file = EXPORTS_DIR / "PRODUCTION_PILOT_03_google_flow.json"

        is_exported = export_file.exists()
        stats = {
            "scenes": 45,
            "images": 38 if project_id == "EP003" else 37,
            "videos": 7 if project_id == "EP003" else 8,
            "characters": 6 if project_id == "EP003" else 7,
            "props": 2 if project_id == "EP003" else 3,
            "schema_version": "SCC_FLOW_V1",
            "export_status": "GOOGLE_FLOW_EXPORT_READY" if is_exported else "READY_FOR_EXPORT",
            "export_file_path": str(export_file) if is_exported else None,
            "combined_file_path": str(combined_file) if combined_file.exists() else None,
        }

        instructions = [
            "1. Mở ứng dụng Google Flow App trên trình duyệt.",
            "2. Nhấn nút Import JSON và chọn file vừa xuất.",
            "3. Tạo và duyệt Character References (ưu tiên Anchor Adult trước, sau đó Younger Variant).",
            "4. Tạo ảnh cho 45 scenes và duyệt.",
            "5. Tạo video cho các scenes được đề xuất (Recommended Videos).",
            "6. Xuất file Production ZIP từ Google Flow App.",
            "7. Quay lại Sau Cánh Cửa Studio và kéo thả file ZIP vào tab 'Assets'."
        ]

        return {
            "project_id": project_id,
            "stats": stats,
            "instructions": instructions,
            "is_exported": is_exported
        }

    def run_export(self, project_id: str) -> Dict[str, Any]:
        """Runs the SCC_FLOW_V1 exporter."""
        result = export_google_flow_app_json()
        return self.get_export_info(project_id)
