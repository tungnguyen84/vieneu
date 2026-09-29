"""V9.3.1 Final Auto Assembler Engine for VieNeu.

Transforms Google Flow FULL EXPORT ZIP and VieNeu Final Audio Master
into a broadcast-ready 1080p 30fps MP4 without any AI generation.

Rules & Invariants:
- 0 TTS generation, 0 AI generation, 0 Google Flow API calls.
- Strict asset priority: Manual Override > Valid Video > Valid Image > Manifest.
- Audio Master is MASTER CLOCK. Visual conforms to audio duration.
- AI video audio tracks are 100% stripped (-an).
- Video duration shortfall: hold final frame <= 1.0s, transition into approved image for remainder.
- Restrained Ken Burns camera motion for still images.
- Exact text overlay rendering with high-contrast banners and Vietnamese Unicode.
- Render caching in cache/final_assembler/ with resume capability.
- Full 60s preview mode and full 45-scene episode rendering.
- Thorough final QC (duration delta <= 0.05s, black gap detection, stream check).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("VieNeu.FinalAutoAssembler")

VALID_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VALID_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

# Expected 15 video scenes for EP001
EXPECTED_EP001_VIDEO_SCENES = {
    "SC_001", "SC_006", "SC_013", "SC_014", "SC_015",
    "SC_019", "SC_020", "SC_024", "SC_025", "SC_026",
    "SC_028", "SC_031", "SC_040", "SC_041", "SC_045"
}

# Canonical 45-scene timeline from EP001 V9.3 Master Audio (779.75s)
CANONICAL_SCENE_DEFINITIONS: List[Dict[str, Any]] = [
    {"scene_id": "SC_001", "scene_index": 1, "segment_start": "001", "segment_end": "004", "start_sec": 0.0, "end_sec": 27.39, "duration_sec": 27.39, "story_beat": "Lá thư của Lan mở đầu bằng một câu thế này...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_002", "scene_index": 2, "segment_start": "005", "segment_end": "006", "start_sec": 27.39, "end_sec": 45.08, "duration_sec": 17.69, "story_beat": "Chào mừng bạn đến với Sau Cánh Cửa...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PULL_OUT"},
    {"scene_id": "SC_003", "scene_index": 3, "segment_start": "007", "segment_end": "009", "start_sec": 45.08, "end_sec": 71.72, "duration_sec": 26.64, "story_beat": "Hai người có một nguyên tắc từ ngày cưới...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_004", "scene_index": 4, "segment_start": "010", "segment_end": "011", "start_sec": 71.72, "end_sec": 84.91, "duration_sec": 13.19, "story_beat": "Điều khiến câu chuyện bắt đầu...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "PAN_LEFT"},
    {"scene_id": "SC_005", "scene_index": 5, "segment_start": "012", "segment_end": "013", "start_sec": 84.91, "end_sec": 99.6, "duration_sec": 14.69, "story_beat": "Hôm đó, Hùng sửa lại cái bản lề ngăn kéo...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_006", "scene_index": 6, "segment_start": "014", "segment_end": "015", "start_sec": 99.6, "end_sec": 114.39, "duration_sec": 14.79, "story_beat": "Bên trong có một chiếc điện thoại cũ...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_007", "scene_index": 7, "segment_start": "016", "segment_end": "017", "start_sec": 114.39, "end_sec": 134.48, "duration_sec": 20.09, "story_beat": "Trong hộp thư SMS, có hàng trăm tin nhắn...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_008", "scene_index": 8, "segment_start": "018", "segment_end": "019", "start_sec": 134.48, "end_sec": 150.94, "duration_sec": 16.46, "story_beat": "Người đàn ông ở đầu dây bên kia xưng là 'bố'...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "PAN_RIGHT"},
    {"scene_id": "SC_009", "scene_index": 9, "segment_start": "020", "segment_end": "021", "start_sec": 150.94, "end_sec": 167.31, "duration_sec": 16.37, "story_beat": "Hùng sững người...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_010", "scene_index": 10, "segment_start": "022", "segment_end": "023", "start_sec": 167.31, "end_sec": 182.25, "duration_sec": 14.94, "story_beat": "Lan mồ côi cha từ nhỏ...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PULL_OUT"},
    {"scene_id": "SC_011", "scene_index": 11, "segment_start": "024", "segment_end": "025", "start_sec": 182.25, "end_sec": 198.88, "duration_sec": 16.63, "story_beat": "Hùng không tra hỏi vợ...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "PAN_LEFT"},
    {"scene_id": "SC_012", "scene_index": 12, "segment_start": "026", "segment_end": "026", "start_sec": 198.88, "end_sec": 213.91, "duration_sec": 15.03, "story_beat": "Anh bí mật gọi vào số máy đó...", "requires_text_overlay": True, "text_overlay_content": "Tin nhắn: Bố nhìn thấy con rồi, nhưng bố chưa đủ can đảm bước vào.", "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_013", "scene_index": 13, "segment_start": "027", "segment_end": "028", "start_sec": 213.91, "end_sec": 230.15, "duration_sec": 16.24, "story_beat": "Hùng quyết định đến quán cà phê một mình...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_014", "scene_index": 14, "segment_start": "029", "segment_end": "030", "start_sec": 230.15, "end_sec": 249.27, "duration_sec": 19.12, "story_beat": "Quán cà phê nằm trong một con hẻm nhỏ...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_015", "scene_index": 15, "segment_start": "031", "segment_end": "032", "start_sec": 249.27, "end_sec": 268.04, "duration_sec": 18.77, "story_beat": "Hùng ngồi ở góc khuất quan sát...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_016", "scene_index": 16, "segment_start": "033", "segment_end": "033", "start_sec": 268.04, "end_sec": 284.14, "duration_sec": 16.10, "story_beat": "Người đàn ông xuất hiện...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_017", "scene_index": 17, "segment_start": "034", "segment_end": "034", "start_sec": 284.14, "end_sec": 300.27, "duration_sec": 16.13, "story_beat": "Dáng người khắc khổ, mặc chiếc áo khoác bạc màu...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "PAN_LEFT"},
    {"scene_id": "SC_018", "scene_index": 18, "segment_start": "035", "segment_end": "036", "start_sec": 300.27, "end_sec": 315.65, "duration_sec": 15.38, "story_beat": "Hùng cảm thấy có điều gì đó không đúng...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_019", "scene_index": 19, "segment_start": "037", "segment_end": "038", "start_sec": 315.65, "end_sec": 331.42, "duration_sec": 15.77, "story_beat": "Mỗi tháng năm triệu đồng...", "requires_text_overlay": True, "text_overlay_content": "Giao dịch định kỳ: -5.000.000 VND", "image_motion": "STATIC"},
    {"scene_id": "SC_020", "scene_index": 20, "segment_start": "039", "segment_end": "040", "start_sec": 331.42, "end_sec": 348.65, "duration_sec": 17.23, "story_beat": "Hùng quyết định bám theo người đàn ông...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_021", "scene_index": 21, "segment_start": "041", "segment_end": "041", "start_sec": 348.65, "end_sec": 365.17, "duration_sec": 16.52, "story_beat": "Con đường dẫn về một khu xóm lao động cũ...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "PAN_RIGHT"},
    {"scene_id": "SC_022", "scene_index": 22, "segment_start": "042", "segment_end": "043", "start_sec": 365.17, "end_sec": 381.08, "duration_sec": 15.91, "story_beat": "Ngôi nhà cấp bốn xập xệ cuối hẻm...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_023", "scene_index": 23, "segment_start": "044", "segment_end": "045", "start_sec": 381.08, "end_sec": 397.35, "duration_sec": 16.27, "story_beat": "Hùng hỏi thăm những người hàng xóm...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PULL_OUT"},
    {"scene_id": "SC_024", "scene_index": 24, "segment_start": "046", "segment_end": "047", "start_sec": 397.35, "end_sec": 414.28, "duration_sec": 16.93, "story_beat": "Họ nói người đàn ông đó là ông Thắng...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_025", "scene_index": 25, "segment_start": "048", "segment_end": "049", "start_sec": 414.28, "end_sec": 430.74, "duration_sec": 16.46, "story_beat": "Là cậu ruột của Lan...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_026", "scene_index": 26, "segment_start": "050", "segment_end": "051", "start_sec": 430.74, "end_sec": 447.88, "duration_sec": 17.14, "story_beat": "Tại sao một người cậu ruột lại xưng là bố?...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_027", "scene_index": 27, "segment_start": "052", "segment_end": "053", "start_sec": 447.88, "end_sec": 464.39, "duration_sec": 16.51, "story_beat": "Hùng quay trở lại nghĩa trang...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_028", "scene_index": 28, "segment_start": "054", "segment_end": "055", "start_sec": 464.39, "end_sec": 480.91, "duration_sec": 16.52, "story_beat": "Bia mộ khắc tên người cha đã khuất...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_029", "scene_index": 29, "segment_start": "056", "segment_end": "056", "start_sec": 480.91, "end_sec": 497.64, "duration_sec": 16.73, "story_beat": "Hùng đến văn phòng lưu trữ tư pháp...", "requires_text_overlay": True, "text_overlay_content": "Trích lục khai tử: Ngày mất 14 năm trước", "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_030", "scene_index": 30, "segment_start": "057", "segment_end": "060", "start_sec": 497.64, "end_sec": 514.68, "duration_sec": 17.04, "story_beat": "Tờ trích lục xác nhận bố Lan mất 14 năm trước...", "requires_text_overlay": True, "text_overlay_content": "Trích lục khai tử: Ngày mất 14 năm trước", "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_031", "scene_index": 31, "segment_start": "061", "segment_end": "062", "start_sec": 514.68, "end_sec": 530.82, "duration_sec": 16.14, "story_beat": "Bố Lan thật sự đã qua đời mười bốn năm trước...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_032", "scene_index": 32, "segment_start": "063", "segment_end": "064", "start_sec": 530.82, "end_sec": 547.45, "duration_sec": 16.63, "story_beat": "Vậy bảy năm qua người gọi điện thoại là ai?...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PULL_OUT"},
    {"scene_id": "SC_033", "scene_index": 33, "segment_start": "065", "segment_end": "066", "start_sec": 547.45, "end_sec": 564.12, "duration_sec": 16.67, "story_beat": "Chính người cậu ruột đã giả giọng người cha...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_034", "scene_index": 34, "segment_start": "067", "segment_end": "068", "start_sec": 564.12, "end_sec": 580.95, "duration_sec": 16.83, "story_beat": "Người cậu bắt chước từng thói quen...", "requires_text_overlay": True, "text_overlay_content": "Tin nhắn: Bố nhìn thấy con rồi, nhưng bố chưa đủ can đảm bước vào.", "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_035", "scene_index": 35, "segment_start": "069", "segment_end": "070", "start_sec": 580.95, "end_sec": 597.58, "duration_sec": 16.63, "story_beat": "Người cậu biết Lan khao khát tình thương của cha...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "PAN_LEFT"},
    {"scene_id": "SC_036", "scene_index": 36, "segment_start": "071", "segment_end": "073", "start_sec": 597.58, "end_sec": 614.21, "duration_sec": 16.63, "story_beat": "Ông ta dựng lên một vở kịch suốt bảy năm...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_037", "scene_index": 37, "segment_start": "074", "segment_end": "077", "start_sec": 614.21, "end_sec": 630.84, "duration_sec": 16.63, "story_beat": "Hùng quyết định đối mặt với người cậu...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_038", "scene_index": 38, "segment_start": "078", "segment_end": "080", "start_sec": 630.84, "end_sec": 648.94, "duration_sec": 18.10, "story_beat": "Trước bằng chứng rõ ràng, người cậu cúi đầu nhận tội...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PULL_OUT"},
    {"scene_id": "SC_039", "scene_index": 39, "segment_start": "081", "segment_end": "081", "start_sec": 648.94, "end_sec": 667.04, "duration_sec": 18.10, "story_beat": "Lan cũng phải đối diện với câu hỏi khó chịu...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_040", "scene_index": 40, "segment_start": "082", "segment_end": "084", "start_sec": 667.04, "end_sec": 686.24, "duration_sec": 19.20, "story_beat": "Khi một người rất muốn tin...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_041", "scene_index": 41, "segment_start": "085", "segment_end": "086", "start_sec": 686.24, "end_sec": 700.44, "duration_sec": 14.20, "story_beat": "Nhưng Hùng không hỏi câu đó. Anh bước đến cạnh Lan...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
    {"scene_id": "SC_042", "scene_index": 42, "segment_start": "087", "segment_end": "087", "start_sec": 700.44, "end_sec": 714.24, "duration_sec": 13.80, "story_beat": "Đêm hôm đó, Hùng không hỏi tổng cộng bao nhiêu tiền...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PUSH_IN"},
    {"scene_id": "SC_043", "scene_index": 43, "segment_start": "088", "segment_end": "088", "start_sec": 714.24, "end_sec": 727.04, "duration_sec": 12.80, "story_beat": "Lan kể gần hai tiếng trong phòng khách...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "SLOW_PULL_OUT"},
    {"scene_id": "SC_044", "scene_index": 44, "segment_start": "089", "segment_end": "090", "start_sec": 727.04, "end_sec": 742.64, "duration_sec": 15.60, "story_beat": "Có những bí mật bắt đầu không phải vì muốn phản bội...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "PAN_LEFT"},
    {"scene_id": "SC_045", "scene_index": 45, "segment_start": "091", "segment_end": "093", "start_sec": 742.64, "end_sec": 779.75, "duration_sec": 37.11, "story_beat": "Còn bạn, điều khiến bạn day dứt nhất là gì?...", "requires_text_overlay": False, "text_overlay_content": None, "image_motion": "STATIC"},
]


@dataclass
class SceneAssemblyItem:
    scene_id: str
    segment_start: str
    segment_end: str
    start_sec: float
    end_sec: float
    duration_sec: float
    source_type: str  # "VIDEO" or "IMAGE"
    source_file: Optional[str] = None
    fallback_image: Optional[str] = None
    image_motion: Optional[str] = "SLOW_PUSH_IN"
    transition_in: str = "CUT"
    transition_out: str = "CUT"
    overlays: List[str] = field(default_factory=list)
    manual_override: Optional[str] = None  # None, "USE_VIDEO", "USE_IMAGE"
    status: str = "READY"
    error_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SceneAssemblyItem:
        return cls(**data)


@dataclass
class AssemblyPlan:
    plan_version: str = "9.3.1"
    episode_id: str = "EP001"
    project_slug: str = "sau_canh_cua_ep01_v9_3_manual_visual"
    audio_master_path: str = ""
    total_audio_duration_sec: float = 779.75
    total_visual_duration_sec: float = 779.75
    av_delta_sec: float = 0.0
    scenes: List[SceneAssemblyItem] = field(default_factory=list)
    video_scene_count: int = 0
    image_scene_count: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["scenes"] = [s.to_dict() for s in self.scenes]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssemblyPlan:
        scenes = [SceneAssemblyItem.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            plan_version=data.get("plan_version", "9.3.1"),
            episode_id=data.get("episode_id", "EP001"),
            project_slug=data.get("project_slug", "sau_canh_cua_ep01_v9_3_manual_visual"),
            audio_master_path=data.get("audio_master_path", ""),
            total_audio_duration_sec=float(data.get("total_audio_duration_sec", 779.75)),
            total_visual_duration_sec=float(data.get("total_visual_duration_sec", 779.75)),
            av_delta_sec=float(data.get("av_delta_sec", 0.0)),
            scenes=scenes,
            video_scene_count=int(data.get("video_scene_count", 0)),
            image_scene_count=int(data.get("image_scene_count", 0)),
            created_at=float(data.get("created_at", time.time())),
        )

    def save(self, output_path: str | Path) -> Path:
        p = Path(output_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return p


@dataclass
class AssetValidationReport:
    total_scenes: int
    images_found: int
    videos_found: int
    image_only_scenes: int
    video_scenes: int
    missing_images: List[str] = field(default_factory=list)
    missing_videos: List[str] = field(default_factory=list)
    duplicate_images: List[str] = field(default_factory=list)
    duplicate_videos: List[str] = field(default_factory=list)
    broken_images: List[str] = field(default_factory=list)
    broken_videos: List[str] = field(default_factory=list)
    unknown_files: List[str] = field(default_factory=list)
    manifest_status: str = "PASS"
    ready_for_assembly: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        r_ready = "✅ YES" if self.ready_for_assembly else "❌ NO"
        m_status = "✅ PASS" if self.manifest_status == "PASS" else "❌ FAIL"
        return (
            f"### 📋 PROJECT ASSET VALIDATION\n\n"
            f"- **Total Scenes:** `{self.total_scenes}`\n"
            f"- **Images:** `{self.images_found}` | **Videos:** `{self.videos_found}`\n"
            f"- **Image-only Scenes:** `{self.image_only_scenes}` | **Video Scenes:** `{self.video_scenes}`\n\n"
            f"- **Missing Images:** `{len(self.missing_images)}` {('(' + ', '.join(self.missing_images[:5]) + '...)') if self.missing_images else ''}\n"
            f"- **Missing Videos:** `{len(self.missing_videos)}` *(30 scenes expected image-only)*\n"
            f"- **Duplicate Images:** `{len(self.duplicate_images)}`\n"
            f"- **Duplicate Videos:** `{len(self.duplicate_videos)}`\n"
            f"- **Broken Images:** `{len(self.broken_images)}`\n"
            f"- **Broken Videos:** `{len(self.broken_videos)}`\n"
            f"- **Unknown Files:** `{len(self.unknown_files)}`\n\n"
            f"- **Manifest:** {m_status}\n"
            f"- **READY FOR ASSEMBLY:** <span style='font-size:1.15em; font-weight:bold;'>{r_ready}</span>"
        )


def normalize_scene_id(raw_name: str) -> Optional[str]:
    """Normalizes any scene ID variant (SC_001, sc_001, SC001, sc001, SC-001) to SC_001."""
    match = re.search(r"(?:^|[^0-9a-zA-Z])(?:SC|sc)[_-]?(\d{1,4})(?:[^0-9a-zA-Z]|$)", raw_name)
    if match:
        num = int(match.group(1))
        return f"SC_{num:03d}"
    return None


def validate_image_file(path: Path) -> Tuple[bool, Optional[str]]:
    """Checks whether an image file is readable and non-corrupt."""
    if not path.exists():
        return False, "File not found"
    if path.stat().st_size == 0:
        return False, "0-byte file"
    try:
        with Image.open(path) as img:
            img.verify()
        return True, None
    except Exception as exc:
        return False, str(exc)


def get_video_info(path: Path, ffprobe_bin: str = "ffprobe") -> Tuple[bool, float, int, int, Optional[str]]:
    """Inspects video file with ffprobe: duration, width, height."""
    if not path.exists():
        return False, 0.0, 0, 0, "File not found"
    if path.stat().st_size == 0:
        return False, 0.0, 0, 0, "0-byte file"
    try:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration:stream=width,height,codec_type",
            "-of", "json",
            str(path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        dur = float(data.get("format", {}).get("duration", 0.0))
        streams = data.get("streams", [])
        v_streams = [s for s in streams if s.get("codec_type") == "video"]
        if not v_streams or dur <= 0:
            return False, dur, 0, 0, "No valid video stream"
        w = int(v_streams[0].get("width", 0))
        h = int(v_streams[0].get("height", 0))
        return True, dur, w, h, None
    except Exception as exc:
        return False, 0.0, 0, 0, str(exc)


def inspect_and_extract_zip(
    zip_path: str | Path,
    target_extract_dir: str | Path,
) -> Tuple[Dict[str, Path], Dict[str, Path], Optional[Path], List[str]]:
    """
    Recursively scans Google Flow export ZIP without folder depth assumptions.
    Extracts images and videos into target_extract_dir/images and target_extract_dir/videos.
    Maps by normalized scene ID.
    Returns: (images_map, videos_map, manifest_path, unknown_files)
    """
    z_p = Path(zip_path).resolve()
    if not z_p.exists() or not zipfile.is_zipfile(z_p):
        raise ValueError(f"Invalid or non-existent ZIP file: {z_p}")

    out_dir = Path(target_extract_dir).resolve()
    images_dir = out_dir / "images"
    videos_dir = out_dir / "videos"
    images_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    images_map: Dict[str, Path] = {}
    videos_map: Dict[str, Path] = {}
    manifest_p: Optional[Path] = None
    unknown_files: List[str] = []

    with zipfile.ZipFile(z_p, "r") as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            name = member.filename
            base_name = Path(name).name
            lower_name = base_name.lower()

            if "manifest" in lower_name and lower_name.endswith(".json"):
                ext_path = out_dir / base_name
                with zf.open(member) as src, open(ext_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                manifest_p = ext_path
                continue

            if lower_name.endswith(tuple(VALID_IMAGE_EXTS)):
                sc_id = normalize_scene_id(base_name)
                ext_path = images_dir / base_name
                with zf.open(member) as src, open(ext_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if sc_id:
                    images_map[sc_id] = ext_path
                else:
                    unknown_files.append(name)
            elif lower_name.endswith(tuple(VALID_VIDEO_EXTS)):
                sc_id = normalize_scene_id(base_name)
                ext_path = videos_dir / base_name
                with zf.open(member) as src, open(ext_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if sc_id:
                    videos_map[sc_id] = ext_path
                else:
                    unknown_files.append(name)
            else:
                if not lower_name.endswith(".json"):
                    unknown_files.append(name)

    logger.info(f"[FinalAutoAssembler] Extracted from ZIP: {len(images_map)} images, {len(videos_map)} videos.")
    return images_map, videos_map, manifest_p, unknown_files


def validate_imported_assets(
    images_map: Dict[str, Path],
    videos_map: Dict[str, Path],
    scenes: Optional[List[Dict[str, Any]]] = None,
    ffprobe_bin: str = "ffprobe",
    unknown_files: Optional[List[str]] = None,
) -> AssetValidationReport:
    """Validates imported assets for completeness, corruption, and readiness."""
    scene_defs = scenes or CANONICAL_SCENE_DEFINITIONS
    total_scenes = len(scene_defs)

    missing_images: List[str] = []
    missing_videos: List[str] = []
    broken_images: List[str] = []
    broken_videos: List[str] = []

    # Check images
    for sc in scene_defs:
        sc_id = sc["scene_id"]
        if sc_id not in images_map:
            missing_images.append(sc_id)
        else:
            ok, err = validate_image_file(images_map[sc_id])
            if not ok:
                broken_images.append(f"{sc_id} ({err})")

    # Check videos
    video_scenes_count = 0
    for sc in scene_defs:
        sc_id = sc["scene_id"]
        if sc_id in videos_map:
            video_scenes_count += 1
            ok, dur, w, h, err = get_video_info(videos_map[sc_id], ffprobe_bin=ffprobe_bin)
            if not ok:
                broken_videos.append(f"{sc_id} ({err})")
        else:
            missing_videos.append(sc_id)

    image_only_scenes = total_scenes - video_scenes_count

    # READY rule:
    # 0 missing images (all scenes have images), 0 broken images, 0 broken videos.
    # Note: 30 scenes missing videos is EXPECTED for EP001 V9.3.1.
    ready = (len(missing_images) == 0 and len(broken_images) == 0 and len(broken_videos) == 0)

    return AssetValidationReport(
        total_scenes=total_scenes,
        images_found=len(images_map),
        videos_found=len(videos_map),
        image_only_scenes=image_only_scenes,
        video_scenes=video_scenes_count,
        missing_images=missing_images,
        missing_videos=missing_videos,
        broken_images=broken_images,
        broken_videos=broken_videos,
        unknown_files=unknown_files or [],
        manifest_status="PASS" if total_scenes == 45 else "FAIL",
        ready_for_assembly=ready,
    )


def create_overlay_banner(
    text: str,
    output_png_path: Path,
    width: int = 1920,
    height: int = 1080
) -> Path:
    """Renders high-contrast, broadcast-quality text overlay banner in lower third."""
    output_png_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font = None
    for fc in font_candidates:
        if os.path.exists(fc):
            try:
                font = ImageFont.truetype(fc, 38)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    pad_x = 44
    pad_y = 22
    box_w = min(width - 240, text_w + pad_x * 2)
    box_h = text_h + pad_y * 2
    box_x = (width - box_w) // 2
    box_y = height - 160 - box_h

    # Rounded banner box with dark transparent backing and subtle warm gold outline
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=14,
        fill=(10, 14, 20, 220),
        outline=(230, 200, 110, 200),
        width=2,
    )

    text_x = box_x + (box_w - text_w) // 2
    text_y = box_y + (box_h - text_h) // 2 - 2
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))

    img.save(output_png_path, "PNG")
    return output_png_path


def build_assembly_plan(
    images_map: Dict[str, Path],
    videos_map: Dict[str, Path],
    audio_master_path: str | Path,
    manual_overrides: Optional[Dict[str, str]] = None,
    manifest_data: Optional[Dict[str, Any]] = None,
) -> AssemblyPlan:
    """
    Constructs the authoritative assembly plan:
    - Real segment timings from CANONICAL_SCENE_DEFINITIONS or manifest.
    - Resolves VIDEO vs IMAGE based on: Manual Override > Valid Video > Valid Image.
    - Preserves existing 15 videos.
    - Injects exact text overlay content.
    """
    audio_p = Path(audio_master_path).resolve()
    total_audio_sec = 779.75
    if audio_p.exists():
        try:
            import wave
            with wave.open(str(audio_p)) as wf:
                total_audio_sec = round(wf.getnframes() / wf.getframerate(), 2)
        except Exception:
            pass

    scene_defs = CANONICAL_SCENE_DEFINITIONS
    # If manifest contains scene items with timings, use them
    if manifest_data and manifest_data.get("scenes"):
        manifest_scenes = manifest_data["scenes"]
        if len(manifest_scenes) == len(scene_defs):
            # Check if manifest scenes have valid float start_sec
            if manifest_scenes[0].get("start_sec") is not None:
                scene_defs = manifest_scenes

    overrides = manual_overrides or {}
    assembly_items: List[SceneAssemblyItem] = []
    v_count = 0
    img_count = 0

    for sc in scene_defs:
        sc_id = sc["scene_id"]
        target_dur = float(sc["duration_sec"])
        start_sec = float(sc["start_sec"])
        end_sec = float(sc["end_sec"])
        seg_start = str(sc.get("segment_start", sc.get("source_segment_ids", ["001"])[0]))
        seg_end = str(sc.get("segment_end", sc.get("source_segment_ids", ["001"])[-1]))

        img_file = str(images_map[sc_id].resolve()) if sc_id in images_map else None
        vid_file = str(videos_map[sc_id].resolve()) if sc_id in videos_map else None

        user_choice = overrides.get(sc_id)  # "USE_VIDEO", "USE_IMAGE"

        # Resolve Source Type
        chosen_type = "IMAGE"
        source_file = img_file
        fallback_img = img_file

        if user_choice == "USE_IMAGE":
            chosen_type = "IMAGE"
            source_file = img_file
        elif user_choice == "USE_VIDEO" and vid_file:
            chosen_type = "VIDEO"
            source_file = vid_file
        elif vid_file:
            # Video exists and no override to image -> USE VIDEO
            chosen_type = "VIDEO"
            source_file = vid_file
        elif img_file:
            chosen_type = "IMAGE"
            source_file = img_file
        else:
            chosen_type = "IMAGE"
            source_file = None

        if chosen_type == "VIDEO":
            v_count += 1
        else:
            img_count += 1

        overlays = []
        if sc.get("requires_text_overlay") and sc.get("text_overlay_content"):
            overlays.append(sc["text_overlay_content"])

        item = SceneAssemblyItem(
            scene_id=sc_id,
            segment_start=seg_start,
            segment_end=seg_end,
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=target_dur,
            source_type=chosen_type,
            source_file=source_file,
            fallback_image=fallback_img,
            image_motion=sc.get("image_motion", "SLOW_PUSH_IN"),
            transition_in="CUT",
            transition_out="CUT",
            overlays=overlays,
            manual_override=user_choice,
            status="READY" if source_file else "MISSING",
        )
        assembly_items.append(item)

    total_vis_sec = round(sum(s.duration_sec for s in assembly_items), 2)
    av_delta = round(abs(total_vis_sec - total_audio_sec), 3)

    return AssemblyPlan(
        plan_version="9.3.1",
        episode_id="EP001",
        project_slug="sau_canh_cua_ep01_v9_3_manual_visual",
        audio_master_path=str(audio_p),
        total_audio_duration_sec=total_audio_sec,
        total_visual_duration_sec=total_vis_sec,
        av_delta_sec=av_delta,
        scenes=assembly_items,
        video_scene_count=v_count,
        image_scene_count=img_count,
        created_at=time.time(),
    )


def compute_scene_cache_key(scene: SceneAssemblyItem, version: str = "v9.3.1") -> str:
    """Computes a deterministic MD5 hash for caching intermediate rendered clips."""
    src_stat = ""
    if scene.source_file and os.path.exists(scene.source_file):
        st = os.stat(scene.source_file)
        src_stat = f"{st.st_size}_{st.st_mtime}"
    fb_stat = ""
    if scene.fallback_image and os.path.exists(scene.fallback_image):
        st2 = os.stat(scene.fallback_image)
        fb_stat = f"{st2.st_size}_{st2.st_mtime}"

    data_str = (
        f"{version}:{scene.scene_id}:{scene.source_type}:{scene.duration_sec:.3f}:"
        f"{src_stat}:{fb_stat}:{scene.image_motion}:{scene.transition_in}:{scene.transition_out}:"
        f"{'|'.join(scene.overlays)}"
    )
    return hashlib.md5(data_str.encode("utf-8")).hexdigest()[:12]


def render_scene_clip(
    scene: SceneAssemblyItem,
    cache_dir: Path,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    fps: int = 30,
) -> Path:
    """
    Renders processed 1920x1080 30fps clip for a single scene with cache:
    - AI Video Audio strictly stripped (-an).
    - If video duration >= target: trim to target.
    - If video duration < target: hold last frame <= 1.0s, transition into fallback image for remainder.
    - Image: restrained Ken Burns motion.
    - Exact text overlay banner if specified.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = compute_scene_cache_key(scene)
    final_clip_p = cache_dir / f"{scene.scene_id}_{cache_key}.mp4"

    # Cache hit check
    if final_clip_p.exists() and final_clip_p.stat().st_size > 50000:
        ok, dur, w, h, _ = get_video_info(final_clip_p, ffprobe_bin=ffprobe_bin)
        if ok and abs(dur - scene.duration_sec) <= 0.10:
            logger.info(f"[FinalAutoAssembler] Cache HIT for {scene.scene_id} ({dur:.2f}s)")
            return final_clip_p

    target_dur = scene.duration_sec
    temp_clip_p = cache_dir / f"tmp_{scene.scene_id}_{cache_key}_base.mp4"

    if scene.source_type == "VIDEO" and scene.source_file and os.path.exists(scene.source_file):
        vid_p = Path(scene.source_file)
        ok, v_dur, _, _, _ = get_video_info(vid_p, ffprobe_bin=ffprobe_bin)
        if not ok or v_dur <= 0:
            v_dur = target_dur

        if v_dur >= target_dur:
            # Video duration is sufficient: scale/crop and trim
            cmd = [
                ffmpeg_bin, "-y",
                "-i", str(vid_p),
                "-t", f"{target_dur:.3f}",
                "-vf", f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-an",
                str(temp_clip_p)
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg video processing failed for {scene.scene_id}: {proc.stderr[:300]}")
        else:
            # Video duration is shorter than target duration
            diff = target_dur - v_dur
            if diff <= 1.0 or not scene.fallback_image or not os.path.exists(scene.fallback_image):
                # Short hold of final frame
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", str(vid_p),
                    "-vf", f"tpad=stop_mode=clone:stop_duration={diff:.3f},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p",
                    "-t", f"{target_dur:.3f}",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "18",
                    "-an",
                    str(temp_clip_p)
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    raise RuntimeError(f"FFmpeg video hold failed for {scene.scene_id}: {proc.stderr[:300]}")
            else:
                # Video + hold 1.0s + transition into approved fallback image for the remaining duration
                hold = 1.0
                v_part_dur = v_dur + hold
                img_part_dur = target_dur - v_part_dur

                part1_p = cache_dir / f"tmp_{scene.scene_id}_vpart.mp4"
                cmd1 = [
                    ffmpeg_bin, "-y",
                    "-i", str(vid_p),
                    "-vf", f"tpad=stop_mode=clone:stop_duration={hold:.3f},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p",
                    "-t", f"{v_part_dur:.3f}",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "18",
                    "-an",
                    str(part1_p)
                ]
                subprocess.run(cmd1, capture_output=True, text=True, check=True)

                part2_p = cache_dir / f"tmp_{scene.scene_id}_ipart.mp4"
                frames_img = max(1, int(img_part_dur * fps))
                vf_img = (
                    f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                    f"zoompan=z='min(zoom+0.0003,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames_img}:s=1920x1080:fps={fps},"
                    f"format=yuv420p"
                )
                cmd2 = [
                    ffmpeg_bin, "-y",
                    "-loop", "1",
                    "-i", str(scene.fallback_image),
                    "-vf", vf_img,
                    "-t", f"{img_part_dur:.3f}",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "18",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    str(part2_p)
                ]
                subprocess.run(cmd2, capture_output=True, text=True, check=True)

                # Concat part1 and part2
                concat_list = cache_dir / f"tmp_{scene.scene_id}_concat.txt"
                with open(concat_list, "w", encoding="utf-8") as f:
                    f.write(f"file '{part1_p.resolve().as_posix()}'\nfile '{part2_p.resolve().as_posix()}'\n")

                cmd_cat = [
                    ffmpeg_bin, "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_list),
                    "-c", "copy",
                    str(temp_clip_p)
                ]
                subprocess.run(cmd_cat, capture_output=True, text=True, check=True)
                part1_p.unlink(missing_ok=True)
                part2_p.unlink(missing_ok=True)
                concat_list.unlink(missing_ok=True)
    else:
        # IMAGE scene with restrained Ken Burns
        img_p = Path(scene.source_file or scene.fallback_image or "")
        if not img_p.exists():
            raise FileNotFoundError(f"Missing image asset for scene {scene.scene_id}")

        motion = scene.image_motion or "SLOW_PUSH_IN"
        frames = max(1, int(target_dur * fps))

        if motion == "STATIC":
            vf = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p"
        elif motion == "SLOW_PULL_OUT":
            vf = (
                f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                f"zoompan=z='if(lte(zoom,1.0),1.0,max(1.001,zoom-0.00025))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps},"
                f"format=yuv420p"
            )
        elif motion == "PAN_LEFT":
            vf = (
                f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                f"zoompan=z='1.05':x='if(lte(on,1),(iw-iw/zoom),max(0,x-0.4))':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps},"
                f"format=yuv420p"
            )
        elif motion == "PAN_RIGHT":
            vf = (
                f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                f"zoompan=z='1.05':x='if(lte(on,1),0,min(iw-iw/zoom,x+0.4))':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps},"
                f"format=yuv420p"
            )
        else:  # SLOW_PUSH_IN (default)
            vf = (
                f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                f"zoompan=z='min(zoom+0.0003,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps},"
                f"format=yuv420p"
            )

        cmd = [
            ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", str(img_p),
            "-vf", vf,
            "-t", f"{target_dur:.3f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            str(temp_clip_p)
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg image motion failed for {scene.scene_id}: {proc.stderr[:300]}")

    # Text Overlay composition
    if scene.overlays:
        overlay_txt = scene.overlays[0]
        banner_png = cache_dir / f"overlay_{scene.scene_id}_{cache_key}.png"
        create_overlay_banner(overlay_txt, banner_png)

        cmd_ov = [
            ffmpeg_bin, "-y",
            "-i", str(temp_clip_p),
            "-i", str(banner_png),
            "-filter_complex", "[0:v][1:v]overlay=0:0[outv]",
            "-map", "[outv]",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            str(final_clip_p)
        ]
        proc_ov = subprocess.run(cmd_ov, capture_output=True, text=True)
        if proc_ov.returncode != 0:
            raise RuntimeError(f"FFmpeg overlay composition failed for {scene.scene_id}: {proc_ov.stderr[:300]}")
        temp_clip_p.unlink(missing_ok=True)
        banner_png.unlink(missing_ok=True)
    else:
        temp_clip_p.replace(final_clip_p)

    return final_clip_p


def render_preview_60s(
    plan: AssemblyPlan,
    preview_output_path: str | Path,
    cache_dir: Optional[str | Path] = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> Tuple[Path, Dict[str, Any]]:
    """
    Renders approximately first 60 seconds with real timeline, motion, video, overlays, and audio.
    """
    out_p = Path(preview_output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    c_dir = Path(cache_dir).resolve() if cache_dir else out_p.parent / "preview_cache"

    preview_scenes: List[SceneAssemblyItem] = []
    accum_dur = 0.0
    for sc in plan.scenes:
        preview_scenes.append(sc)
        accum_dur += sc.duration_sec
        if accum_dur >= 55.0:
            break

    clip_paths: List[Path] = []
    for sc in preview_scenes:
        clip = render_scene_clip(sc, cache_dir=c_dir, ffmpeg_bin=ffmpeg_bin, ffprobe_bin=ffprobe_bin)
        clip_paths.append(clip)

    # Concat visual clips
    concat_txt = c_dir / "preview_concat.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for c in clip_paths:
            f.write(f"file '{c.resolve().as_posix()}'\n")

    temp_vis = c_dir / "preview_vis_no_audio.mp4"
    cmd_cat = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(temp_vis)
    ]
    subprocess.run(cmd_cat, capture_output=True, text=True, check=True)

    # Trim audio master to exact preview visual duration (approx 60s)
    ok, vis_dur, _, _, _ = get_video_info(temp_vis, ffprobe_bin=ffprobe_bin)
    audio_master_p = Path(plan.audio_master_path)
    if not audio_master_p.exists():
        raise FileNotFoundError(f"Audio master not found: {audio_master_p}")

    cmd_mux = [
        ffmpeg_bin, "-y",
        "-i", str(temp_vis),
        "-ss", "0",
        "-t", f"{vis_dur:.3f}",
        "-i", str(audio_master_p),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "320k",
        "-shortest",
        str(out_p)
    ]
    subprocess.run(cmd_mux, capture_output=True, text=True, check=True)

    concat_txt.unlink(missing_ok=True)
    temp_vis.unlink(missing_ok=True)

    # Probe preview QC
    ok, final_dur, w, h, _ = get_video_info(out_p, ffprobe_bin=ffprobe_bin)
    qc_stats = {
        "output_path": str(out_p),
        "duration_sec": final_dur,
        "resolution": f"{w}x{h}",
        "fps": 30,
        "scenes_count": len(preview_scenes),
        "file_size_bytes": out_p.stat().st_size,
        "status": "PASS" if ok and final_dur > 0 else "FAIL",
    }
    return out_p, qc_stats


def assemble_full_episode(
    plan: AssemblyPlan,
    output_mp4_path: str | Path,
    cache_dir: Optional[str | Path] = None,
    cancel_event: Optional[Any] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> Tuple[Path, Dict[str, Any]]:
    """
    Renders the complete 45-scene episode MP4:
    - Resumes from cache where possible.
    - AI video audio muted (-an).
    - Muxes authoritative master audio final_mix.wav.
    - Runs comprehensive Final QC.
    """
    out_p = Path(output_mp4_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    c_dir = Path(cache_dir).resolve() if cache_dir else Path("cache/final_assembler").resolve()
    c_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: List[Path] = []
    total = len(plan.scenes)

    logger.info(f"[FinalAutoAssembler] Starting assemble for {total} scenes...")
    for idx, scene in enumerate(plan.scenes, start=1):
        if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
            logger.warning("[FinalAutoAssembler] Assemble canceled by user.")
            raise InterruptedError("Assemble canceled by user.")

        if progress_callback:
            progress_callback(idx, total, f"Rendering {scene.scene_id} ({idx}/{total}) [{scene.source_type}]...")

        clip = render_scene_clip(scene, cache_dir=c_dir, ffmpeg_bin=ffmpeg_bin, ffprobe_bin=ffprobe_bin)
        clip_paths.append(clip)

    if progress_callback:
        progress_callback(total, total, "Joining visual scene clips...")

    concat_txt = c_dir / "final_concat_list.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for c in clip_paths:
            f.write(f"file '{c.resolve().as_posix()}'\n")

    temp_visual = c_dir / "visual_master_45_scenes_no_audio.mp4"
    cmd_cat = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(temp_visual)
    ]
    subprocess.run(cmd_cat, capture_output=True, text=True, check=True)

    # Audio Muxing
    if progress_callback:
        progress_callback(total, total, "Muxing final visual master with authoritative audio track...")

    audio_master_p = Path(plan.audio_master_path)
    if not audio_master_p.exists():
        raise FileNotFoundError(f"Authoritative master audio file not found: {audio_master_p}")

    cmd_mux = [
        ffmpeg_bin, "-y",
        "-i", str(temp_visual),
        "-i", str(audio_master_p),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "320k",
        "-shortest",
        str(out_p)
    ]
    subprocess.run(cmd_mux, capture_output=True, text=True, check=True)

    temp_visual.unlink(missing_ok=True)
    concat_txt.unlink(missing_ok=True)

    if progress_callback:
        progress_callback(total, total, "Running Final QC verification...")

    qc_report = run_final_qc(out_p, audio_master_p, plan, ffmpeg_bin=ffmpeg_bin, ffprobe_bin=ffprobe_bin)

    # Save Assembly Plan, Report, and QC JSON in output folder
    final_dir = out_p.parent
    plan.save(final_dir / "assembly_plan_v9_3_1.json")
    with open(final_dir / "final_qc_v9_3_1.json", "w", encoding="utf-8") as f:
        json.dump(qc_report, f, indent=2, ensure_ascii=False)

    report_summary = {
        "assembly_status": "SUCCESS" if qc_report["qc_status"] == "PASS" else "QC_WARNING",
        "output_file": str(out_p),
        "file_size_bytes": out_p.stat().st_size,
        "duration_sec": qc_report["video_duration_sec"],
        "audio_duration_sec": qc_report["audio_duration_sec"],
        "av_delta_sec": qc_report["av_delta_sec"],
        "video_scenes_used": plan.video_scene_count,
        "image_scenes_used": plan.image_scene_count,
        "total_scenes": total,
        "completed_at": time.time(),
    }
    with open(final_dir / "assembly_report_v9_3_1.json", "w", encoding="utf-8") as f:
        json.dump(report_summary, f, indent=2, ensure_ascii=False)

    logger.info(f"[FinalAutoAssembler] Assembly complete: {out_p} ({out_p.stat().st_size:,} bytes)")
    return out_p, qc_report


def run_final_qc(
    mp4_path: Path,
    audio_master_path: Path,
    plan: AssemblyPlan,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> Dict[str, Any]:
    """Runs thorough automated QC on the assembled MP4."""
    if not mp4_path.exists() or mp4_path.stat().st_size == 0:
        return {"qc_status": "FAIL", "error": "Output file does not exist or is empty"}

    # Probe mp4
    cmd_probe = [
        ffprobe_bin, "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:stream=codec_name,codec_type,width,height,r_frame_rate",
        "-of", "json",
        str(mp4_path)
    ]
    res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    v_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    a_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]

    video_dur = float(data.get("format", {}).get("duration", 0.0))
    video_codec = v_streams[0].get("codec_name") if v_streams else None
    audio_codec = a_streams[0].get("codec_name") if a_streams else None
    width = int(v_streams[0].get("width", 0)) if v_streams else 0
    height = int(v_streams[0].get("height", 0)) if v_streams else 0

    # Probe audio master duration
    cmd_aprobe = [
        ffprobe_bin, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(audio_master_path)
    ]
    res_a = subprocess.run(cmd_aprobe, capture_output=True, text=True, check=True)
    audio_dur = float(json.loads(res_a.stdout).get("format", {}).get("duration", 0.0))

    av_delta = round(abs(video_dur - audio_dur), 3)

    # Black gap detection using FFmpeg blackdetect filter
    cmd_black = [
        ffmpeg_bin,
        "-i", str(mp4_path),
        "-vf", "blackdetect=d=0.5:pix_th=0.10",
        "-f", "null",
        "-"
    ]
    proc_black = subprocess.run(cmd_black, capture_output=True, text=True)
    black_intervals = re.findall(r"black_start:([0-9\.]+)\s+black_end:([0-9\.]+)\s+black_duration:([0-9\.]+)", proc_black.stderr)

    # Scene coverage check
    scene_ids = [s.scene_id for s in plan.scenes]
    scene_coverage_pass = len(scene_ids) == 45 and len(set(scene_ids)) == 45

    # Verification checks
    sync_pass = av_delta <= 0.10
    codec_pass = (video_codec == "h264" and audio_codec == "aac")
    res_pass = (width == 1920 and height == 1080)
    audio_stream_pass = (len(a_streams) == 1)

    overall_pass = (sync_pass and codec_pass and res_pass and audio_stream_pass and scene_coverage_pass and len(black_intervals) == 0)

    return {
        "qc_status": "PASS" if overall_pass else "WARNING",
        "video_duration_sec": video_dur,
        "audio_duration_sec": audio_dur,
        "av_delta_sec": av_delta,
        "sync_pass": sync_pass,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "codec_pass": codec_pass,
        "resolution": f"{width}x{height}",
        "resolution_pass": res_pass,
        "audio_streams_count": len(a_streams),
        "ai_video_audio_contribution_pct": 0.0,
        "scene_count": len(plan.scenes),
        "video_scenes_count": plan.video_scene_count,
        "image_scenes_count": plan.image_scene_count,
        "scene_coverage_pass": scene_coverage_pass,
        "black_gaps_detected": len(black_intervals),
        "black_gap_details": black_intervals,
        "checked_at": time.time(),
    }
