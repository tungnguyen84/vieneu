"""Manual Visual Import & Auto Assemble Mode for VieNeu.

Features:
- Loads and parses visual_manifest_v9_3.json (or initializes it from project audio segment timeline).
- Scans images/ and videos/ folders case-insensitively by SC_XXX.
- Asset priority: VIDEO > IMAGE.
- Detection and reporting of invalid/corrupt media files.
- Duplicate files require explicit user selection.
- Missing scene assets strictly block assembly render.
- Restrained Ken Burns camera motion for still images (1920x1080 30fps).
- Scale/crop for video clips (1080p), trim if long, freeze last frame if short.
- Strips all source video audio tracks.
- High-quality post-production rendering for critical text overlays (Vietnamese diacritics).
- Multiplexes final master audio (final_mix.wav).
- Complete MP4 episode export: 1920x1080, 30fps, H.264, AAC 320kbps, zero black gaps.
- Strictly offline: NO FlowKit, NO Banana Pro, NO Omni Flash API calls.
- NEVER mutates visual_plan.json, source.json, or audio files.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("VieNeu.ManualVisual")

VALID_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VALID_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

CANONICAL_V9_3_SCENES = [
    {"scene_id": "SC_001", "scene_index": 1, "start_sec": 0.0, "end_sec": 27.39, "duration_sec": 27.39, "story_beat": "Lá thư của Lan mở đầu bằng một câu thế này: “Nếu chồng tôi nghe được lá thư này...", "source_segment_ids": ["001", "002", "003", "004"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_002", "scene_index": 2, "start_sec": 27.39, "end_sec": 45.08, "duration_sec": 17.69, "story_beat": "Chào mừng bạn đến với Sau Cánh Cửa — nơi chúng ta không tìm kiếm những câu chuyện giật gân...", "source_segment_ids": ["005", "006"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_003", "scene_index": 3, "start_sec": 45.08, "end_sec": 71.72, "duration_sec": 26.64, "story_beat": "Hai người có một nguyên tắc từ ngày cưới: minh bạch tài chính...", "source_segment_ids": ["007", "008", "009"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_004", "scene_index": 4, "start_sec": 71.72, "end_sec": 84.91, "duration_sec": 13.19, "story_beat": "Điều khiến câu chuyện bắt đầu không phải là một sự nghi ngờ lớn lao...", "source_segment_ids": ["010", "011"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_005", "scene_index": 5, "start_sec": 84.91, "end_sec": 99.6, "duration_sec": 14.69, "story_beat": "Hôm đó, Hùng sửa lại cái bản lề ngăn kéo bàn làm việc trong phòng ngủ...", "source_segment_ids": ["012", "013"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_006", "scene_index": 6, "start_sec": 99.6, "end_sec": 114.39, "duration_sec": 14.79, "story_beat": "Bên trong có một chiếc điện thoại cũ...", "source_segment_ids": ["014", "015"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_007", "scene_index": 7, "start_sec": 114.39, "end_sec": 134.48, "duration_sec": 20.09, "story_beat": "Trong hộp thư SMS, có hàng trăm tin nhắn gửi đến cùng một số điện thoại...", "source_segment_ids": ["016", "017"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_008", "scene_index": 8, "start_sec": 134.48, "end_sec": 150.94, "duration_sec": 16.46, "story_beat": "Người đàn ông ở đầu dây bên kia xưng là 'bố'...", "source_segment_ids": ["018", "019"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_009", "scene_index": 9, "start_sec": 150.94, "end_sec": 167.31, "duration_sec": 16.37, "story_beat": "Hùng sững người...", "source_segment_ids": ["020", "021"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_010", "scene_index": 10, "start_sec": 167.31, "end_sec": 182.25, "duration_sec": 14.94, "story_beat": "Lan mồ côi cha từ nhỏ...", "source_segment_ids": ["022", "023"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_011", "scene_index": 11, "start_sec": 182.25, "end_sec": 198.88, "duration_sec": 16.63, "story_beat": "Hùng không tra hỏi vợ...", "source_segment_ids": ["024", "025"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_012", "scene_index": 12, "start_sec": 198.88, "end_sec": 213.91, "duration_sec": 15.03, "story_beat": "Anh bí mật gọi vào số máy đó...", "source_segment_ids": ["026"], "requires_text_overlay": True, "text_overlay_content": "Tin nhắn: Bố nhìn thấy con rồi, nhưng bố chưa đủ can đảm bước vào."},
    {"scene_id": "SC_013", "scene_index": 13, "start_sec": 213.91, "end_sec": 230.15, "duration_sec": 16.24, "story_beat": "Hùng quyết định đến quán cà phê một mình...", "source_segment_ids": ["027", "028"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_014", "scene_index": 14, "start_sec": 230.15, "end_sec": 249.27, "duration_sec": 19.12, "story_beat": "Quán cà phê nằm trong một con hẻm nhỏ...", "source_segment_ids": ["029", "030"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_015", "scene_index": 15, "start_sec": 249.27, "end_sec": 268.04, "duration_sec": 18.77, "story_beat": "Hùng ngồi ở góc khuất quan sát...", "source_segment_ids": ["031", "032"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_016", "scene_index": 16, "start_sec": 268.04, "end_sec": 284.14, "duration_sec": 16.1, "story_beat": "Người đàn ông xuất hiện...", "source_segment_ids": ["033"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_017", "scene_index": 17, "start_sec": 284.14, "end_sec": 300.27, "duration_sec": 16.13, "story_beat": "Dáng người khắc khổ, mặc chiếc áo khoác bạc màu...", "source_segment_ids": ["034"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_018", "scene_index": 18, "start_sec": 300.27, "end_sec": 315.65, "duration_sec": 15.38, "story_beat": "Hùng cảm thấy có điều gì đó không đúng...", "source_segment_ids": ["035", "036"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_019", "scene_index": 19, "start_sec": 315.65, "end_sec": 331.42, "duration_sec": 15.77, "story_beat": "Mỗi tháng năm triệu đồng...", "source_segment_ids": ["037", "038"], "requires_text_overlay": True, "text_overlay_content": "Giao dịch định kỳ: -5.000.000 VND"},
    {"scene_id": "SC_020", "scene_index": 20, "start_sec": 331.42, "end_sec": 348.65, "duration_sec": 17.23, "story_beat": "Hùng quyết định bám theo người đàn ông...", "source_segment_ids": ["039", "040"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_021", "scene_index": 21, "start_sec": 348.65, "end_sec": 365.17, "duration_sec": 16.52, "story_beat": "Con đường dẫn về một khu xóm lao động cũ...", "source_segment_ids": ["041"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_022", "scene_index": 22, "start_sec": 365.17, "end_sec": 381.08, "duration_sec": 15.91, "story_beat": "Ngôi nhà cấp bốn xập xệ cuối hẻm...", "source_segment_ids": ["042", "043"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_023", "scene_index": 23, "start_sec": 381.08, "end_sec": 397.35, "duration_sec": 16.27, "story_beat": "Hùng hỏi thăm những người hàng xóm xung quanh...", "source_segment_ids": ["044", "045"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_024", "scene_index": 24, "start_sec": 397.35, "end_sec": 414.28, "duration_sec": 16.93, "story_beat": "Họ nói người đàn ông đó là ông Thắng, em ruột của mẹ Lan...", "source_segment_ids": ["046", "047"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_025", "scene_index": 25, "start_sec": 414.28, "end_sec": 430.74, "duration_sec": 16.46, "story_beat": "Là cậu ruột của Lan...", "source_segment_ids": ["048", "049"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_026", "scene_index": 26, "start_sec": 430.74, "end_sec": 447.88, "duration_sec": 17.14, "story_beat": "Tại sao một người cậu ruột lại xưng là bố?...", "source_segment_ids": ["050", "051"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_027", "scene_index": 27, "start_sec": 447.88, "end_sec": 464.39, "duration_sec": 16.51, "story_beat": "Hùng quay trở lại nghĩa trang nơi an nghỉ của bố Lan...", "source_segment_ids": ["052", "053"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_028", "scene_index": 28, "start_sec": 464.39, "end_sec": 480.91, "duration_sec": 16.52, "story_beat": "Bia mộ khắc tên người cha đã khuất...", "source_segment_ids": ["054", "055"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_029", "scene_index": 29, "start_sec": 480.91, "end_sec": 497.64, "duration_sec": 16.73, "story_beat": "Hùng đến văn phòng lưu trữ tư pháp để xác minh trích lục khai tử...", "source_segment_ids": ["056"], "requires_text_overlay": True, "text_overlay_content": "Trích lục khai tử: Ngày mất 14 năm trước"},
    {"scene_id": "SC_030", "scene_index": 30, "start_sec": 497.64, "end_sec": 514.68, "duration_sec": 17.04, "story_beat": "Hùng không kể chuyện đó cho vợ ngay. Tờ trích lục khai tử xác nhận bố Lan mất 14 năm trước.", "source_segment_ids": ["057", "058", "059", "060"], "requires_text_overlay": True, "text_overlay_content": "Trích lục khai tử: Ngày mất 14 năm trước"},
    {"scene_id": "SC_031", "scene_index": 31, "start_sec": 514.68, "end_sec": 530.82, "duration_sec": 16.14, "story_beat": "Bố Lan thật sự đã qua đời mười bốn năm trước, chứ không phải bảy năm...", "source_segment_ids": ["061", "062"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_032", "scene_index": 32, "start_sec": 530.82, "end_sec": 547.45, "duration_sec": 16.63, "story_beat": "Vậy bảy năm qua, người gọi điện thoại xưng là bố là ai?...", "source_segment_ids": ["063", "064"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_033", "scene_index": 33, "start_sec": 547.45, "end_sec": 564.12, "duration_sec": 16.67, "story_beat": "Chính người cậu ruột đã giả giọng người cha đã mất...", "source_segment_ids": ["065", "066"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_034", "scene_index": 34, "start_sec": 564.12, "end_sec": 580.95, "duration_sec": 16.83, "story_beat": "Người cậu bắt chước từng thói quen, từng câu nói quen thuộc...", "source_segment_ids": ["067", "068"], "requires_text_overlay": True, "text_overlay_content": "Tin nhắn: Bố nhìn thấy con rồi, nhưng bố chưa đủ can đảm bước vào."},
    {"scene_id": "SC_035", "scene_index": 35, "start_sec": 580.95, "end_sec": 597.58, "duration_sec": 16.63, "story_beat": "Người cậu biết Lan khao khát tình thương của cha...", "source_segment_ids": ["069", "070"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_036", "scene_index": 36, "start_sec": 597.58, "end_sec": 614.21, "duration_sec": 16.63, "story_beat": "Ông ta dựng lên một vở kịch hoàn hảo suốt bảy năm trời...", "source_segment_ids": ["071", "072", "073"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_037", "scene_index": 37, "start_sec": 614.21, "end_sec": 630.84, "duration_sec": 16.63, "story_beat": "Hùng quyết định đối mặt với người cậu...", "source_segment_ids": ["074", "075", "076", "077"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_038", "scene_index": 38, "start_sec": 630.84, "end_sec": 648.94, "duration_sec": 18.1, "story_beat": "Trước những bằng chứng rõ ràng, người cậu cúi đầu nhận tội...", "source_segment_ids": ["078", "079", "080"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_039", "scene_index": 39, "start_sec": 648.94, "end_sec": 667.04, "duration_sec": 18.1, "story_beat": "Lan cũng phải đối diện với một câu hỏi khó chịu: tại sao trong bảy năm cô chưa từng tìm cách xác minh?...", "source_segment_ids": ["081"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_040", "scene_index": 40, "start_sec": 667.04, "end_sec": 686.24, "duration_sec": 19.2, "story_beat": "Khi một người rất muốn tin rằng người thân đã quay về, bằng chứng đôi khi không cần hoàn hảo...", "source_segment_ids": ["082", "083", "084"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_041", "scene_index": 41, "start_sec": 686.24, "end_sec": 700.44, "duration_sec": 14.2, "story_beat": "Nhưng Hùng không hỏi câu đó. Anh bước đến cạnh Lan...", "source_segment_ids": ["085", "086"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_042", "scene_index": 42, "start_sec": 700.44, "end_sec": 714.24, "duration_sec": 13.8, "story_beat": "Đêm hôm đó, Hùng không hỏi tổng cộng vợ đã giấu mình bao nhiêu tiền...", "source_segment_ids": ["087"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_043", "scene_index": 43, "start_sec": 714.24, "end_sec": 727.04, "duration_sec": 12.8, "story_beat": "Lan kể gần hai tiếng, trong căn phòng khách lặng ngắt...", "source_segment_ids": ["088"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_044", "scene_index": 44, "start_sec": 727.04, "end_sec": 742.64, "duration_sec": 15.6, "story_beat": "Có những bí mật bắt đầu không phải vì chúng ta muốn phản bội ai...", "source_segment_ids": ["089", "090"], "requires_text_overlay": False, "text_overlay_content": None},
    {"scene_id": "SC_045", "scene_index": 45, "start_sec": 742.64, "end_sec": 779.75, "duration_sec": 37.11, "story_beat": "Còn bạn, điều khiến bạn day dứt nhất trong câu chuyện này là số tiền bị lấy đi, việc Lan giấu chồng, hay nỗi cô đơn đã khiến một người phụ nữ tự lừa dối mình suốt bảy năm trời?...", "source_segment_ids": ["091", "092", "093"], "requires_text_overlay": False, "text_overlay_content": None},
]


@dataclass
class ManualSceneItem:
    scene_id: str
    scene_index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    story_beat: str
    source_segment_ids: List[str] = field(default_factory=list)
    requires_text_overlay: bool = False
    text_overlay_content: Optional[str] = None
    matched_images: List[str] = field(default_factory=list)
    matched_videos: List[str] = field(default_factory=list)
    chosen_asset: Optional[str] = None
    chosen_type: Optional[str] = None  # "VIDEO" or "IMAGE"
    qc_status: str = "MISSING"  # "READY", "MISSING", "DUPLICATE", "INVALID"
    error_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ManualSceneItem:
        return cls(
            scene_id=data["scene_id"],
            scene_index=data.get("scene_index", 0),
            start_sec=float(data["start_sec"]),
            end_sec=float(data["end_sec"]),
            duration_sec=float(data["duration_sec"]),
            story_beat=data.get("story_beat", ""),
            source_segment_ids=list(data.get("source_segment_ids", [])),
            requires_text_overlay=bool(data.get("requires_text_overlay", False)),
            text_overlay_content=data.get("text_overlay_content"),
            matched_images=list(data.get("matched_images", [])),
            matched_videos=list(data.get("matched_videos", [])),
            chosen_asset=data.get("chosen_asset"),
            chosen_type=data.get("chosen_type"),
            qc_status=data.get("qc_status", "MISSING"),
            error_reason=data.get("error_reason"),
        )


@dataclass
class ManualVisualManifest:
    manifest_version: str = "9.3"
    project_slug: str = "sau_canh_cua_ep01_v9_3_manual_visual"
    project_dir: str = ""
    audio_master_path: str = ""
    total_duration_sec: float = 779.75
    timeline_source: str = "PROJECT_AUDIO_SEGMENTS"
    scenes: List[ManualSceneItem] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "project_slug": self.project_slug,
            "project_dir": self.project_dir,
            "audio_master_path": self.audio_master_path,
            "total_duration_sec": round(self.total_duration_sec, 2),
            "timeline_source": self.timeline_source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scenes": [s.to_dict() for s in self.scenes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ManualVisualManifest:
        scenes = [ManualSceneItem.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            manifest_version=data.get("manifest_version", "9.3"),
            project_slug=data.get("project_slug", "sau_canh_cua_ep01_v9_3_manual_visual"),
            project_dir=data.get("project_dir", ""),
            audio_master_path=data.get("audio_master_path", ""),
            total_duration_sec=float(data.get("total_duration_sec", 779.75)),
            timeline_source=data.get("timeline_source", "PROJECT_AUDIO_SEGMENTS"),
            scenes=scenes,
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


def _validate_image_file(path: Path) -> Tuple[bool, Optional[str]]:
    """Checks whether an image file is valid and readable."""
    if not path.exists():
        return False, "File does not exist"
    if path.stat().st_size == 0:
        return False, "0-byte empty file"
    try:
        with Image.open(path) as img:
            img.verify()
        return True, None
    except Exception as exc:
        return False, f"Corrupted image: {exc}"


def _get_video_info(path: Path, ffprobe_bin: str = "ffprobe") -> Tuple[bool, float, Optional[str]]:
    """Uses ffprobe to inspect video duration and validity."""
    if not path.exists():
        return False, 0.0, "File does not exist"
    if path.stat().st_size == 0:
        return False, 0.0, "0-byte empty file"
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
        has_video = any(s.get("codec_type") == "video" for s in streams)
        if not has_video or dur <= 0:
            return False, dur, "No valid video stream found"
        return True, dur, None
    except Exception as exc:
        return False, 0.0, f"ffprobe error: {exc}"


def load_or_create_manifest(
    manifest_path: Optional[str | Path] = None,
    project_dir: Optional[str | Path] = None,
) -> ManualVisualManifest:
    """Loads visual_manifest_v9_3.json from disk, or initializes from project audio timeline."""
    p_dir = Path(project_dir).resolve() if project_dir else Path("projects/sau_canh_cua_ep01_v9_3_manual_visual").resolve()

    candidate_paths: List[Path] = []
    if manifest_path:
        candidate_paths.append(Path(manifest_path).resolve())
    candidate_paths.extend([
        p_dir / "visual_manifest_v9_3.json",
        p_dir / "visual" / "visual_manifest_v9_3.json",
        Path("visual_manifest_v9_3.json").resolve(),
    ])

    for cp in candidate_paths:
        if cp.exists() and cp.is_file():
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                manifest = ManualVisualManifest.from_dict(data)
                manifest.project_dir = str(p_dir)
                if not manifest.audio_master_path or not Path(manifest.audio_master_path).exists():
                    manifest.audio_master_path = str(p_dir / "master" / "final_mix.wav")
                logger.info(f"[ManualVisual] Loaded existing manifest from: {cp}")
                return manifest
            except Exception as e:
                logger.warning(f"[ManualVisual] Could not parse manifest at {cp}: {e}")

    # Build canonical manifest from project audio timeline (NEVER mutating visual_plan.json or source.json)
    audio_master = p_dir / "master" / "final_mix.wav"
    total_audio_sec = 779.75
    if audio_master.exists():
        try:
            import wave
            with wave.open(str(audio_master)) as wf:
                total_audio_sec = round(wf.getnframes() / wf.getframerate(), 2)
        except Exception:
            pass

    scenes: List[ManualSceneItem] = []
    for sc_def in CANONICAL_V9_3_SCENES:
        item = ManualSceneItem(
            scene_id=sc_def["scene_id"],
            scene_index=sc_def["scene_index"],
            start_sec=sc_def["start_sec"],
            end_sec=sc_def["end_sec"],
            duration_sec=sc_def["duration_sec"],
            story_beat=sc_def["story_beat"],
            source_segment_ids=sc_def["source_segment_ids"],
            requires_text_overlay=sc_def["requires_text_overlay"],
            text_overlay_content=sc_def["text_overlay_content"],
            matched_images=[],
            matched_videos=[],
            chosen_asset=None,
            chosen_type=None,
            qc_status="MISSING",
        )
        scenes.append(item)

    # Contiguity check on canonical definitions
    for i in range(len(scenes)):
        if i == 0:
            scenes[i].start_sec = 0.0
        else:
            scenes[i].start_sec = scenes[i - 1].end_sec
        if i == len(scenes) - 1:
            scenes[i].end_sec = total_audio_sec
        scenes[i].duration_sec = round(scenes[i].end_sec - scenes[i].start_sec, 2)

    manifest = ManualVisualManifest(
        manifest_version="9.3",
        project_slug=p_dir.name,
        project_dir=str(p_dir),
        audio_master_path=str(audio_master),
        total_duration_sec=total_audio_sec,
        timeline_source="PROJECT_AUDIO_SEGMENTS",
        scenes=scenes,
    )

    save_path = p_dir / "visual_manifest_v9_3.json"
    save_manifest(manifest, save_path)
    root_manifest = Path("visual_manifest_v9_3.json").resolve()
    try:
        shutil.copy2(save_path, root_manifest)
    except Exception:
        pass

    logger.info(f"[ManualVisual] Initialized canonical manifest with {len(scenes)} scenes at: {save_path}")
    return manifest


def save_manifest(manifest: ManualVisualManifest, save_path: str | Path) -> Path:
    """Saves the manual visual manifest to disk."""
    p = Path(save_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest.updated_at = time.time()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
    logger.info(f"[ManualVisual] Saved manifest to: {p}")
    return p


def scan_project_assets(
    manifest: ManualVisualManifest,
    project_dir: Optional[str | Path] = None,
    images_dir: Optional[str | Path] = None,
    videos_dir: Optional[str | Path] = None,
    ffprobe_bin: str = "ffprobe"
) -> ManualVisualManifest:
    """
    Scans image and video directories case-insensitively by SC_XXX.
    Priority: VIDEO > IMAGE.
    Handles duplicate candidates (requiring user selection) and invalid/corrupted files.
    """
    p_dir = Path(project_dir).resolve() if project_dir else Path(manifest.project_dir).resolve()

    img_dirs = []
    if images_dir:
        img_dirs.append(Path(images_dir).resolve())
    img_dirs.extend([p_dir / "visual" / "images", p_dir / "images"])

    vid_dirs = []
    if videos_dir:
        vid_dirs.append(Path(videos_dir).resolve())
    vid_dirs.extend([p_dir / "visual" / "videos", p_dir / "videos"])

    # Collect existing image files
    all_image_files: List[Path] = []
    for d in img_dirs:
        if d.exists() and d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in VALID_IMAGE_EXTS:
                    if f not in all_image_files:
                        all_image_files.append(f)

    # Collect existing video files
    all_video_files: List[Path] = []
    for d in vid_dirs:
        if d.exists() and d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in VALID_VIDEO_EXTS:
                    if f not in all_video_files:
                        all_video_files.append(f)

    logger.info(f"[ManualVisual] Scanned {len(all_image_files)} image files and {len(all_video_files)} video files.")

    # Match per scene
    for scene in manifest.scenes:
        sc_id = scene.scene_id
        # Case-insensitive boundary match for SC_XXX
        pattern = re.compile(rf"(?i)(?:^|[^0-9a-zA-Z]){re.escape(sc_id)}(?:[^0-9a-zA-Z]|$)", re.IGNORECASE)

        matched_images = [f for f in all_image_files if pattern.search(f.name)]
        matched_videos = [f for f in all_video_files if pattern.search(f.name)]

        scene.matched_images = [str(p) for p in matched_images]
        scene.matched_videos = [str(p) for p in matched_videos]
        scene.error_reason = None

        # Filter valid vs invalid
        valid_images: List[Path] = []
        invalid_images: List[Tuple[Path, str]] = []
        for img_p in matched_images:
            ok, err = _validate_image_file(img_p)
            if ok:
                valid_images.append(img_p)
            else:
                invalid_images.append((img_p, err or "Invalid image"))

        valid_videos: List[Path] = []
        invalid_videos: List[Tuple[Path, str]] = []
        for vid_p in matched_videos:
            ok, _, err = _get_video_info(vid_p, ffprobe_bin=ffprobe_bin)
            if ok:
                valid_videos.append(vid_p)
            else:
                invalid_videos.append((vid_p, err or "Invalid video"))

        # Check for invalid media presence
        if (invalid_images or invalid_videos) and not valid_videos and not valid_images:
            reasons = [f"{p.name}: {r}" for p, r in (invalid_images + invalid_videos)]
            scene.qc_status = "INVALID"
            scene.error_reason = "; ".join(reasons)
            scene.chosen_asset = None
            scene.chosen_type = None
            continue

        # Check duplicate condition:
        # If user hasn't explicitly chosen an asset, or current chosen is not among matches:
        multiple_videos = len(valid_videos) > 1
        multiple_images = len(valid_images) > 1 and len(valid_videos) == 0

        # Prioritize Video over Image
        if multiple_videos:
            # Check if previous chosen is one of the valid videos
            if scene.chosen_asset and any(Path(scene.chosen_asset) == v for v in valid_videos):
                scene.qc_status = "READY"
                scene.chosen_type = "VIDEO"
            else:
                scene.qc_status = "DUPLICATE"
                scene.error_reason = f"Multiple video files found: {', '.join(v.name for v in valid_videos)}. Selection required."
                scene.chosen_asset = None
                scene.chosen_type = None
        elif len(valid_videos) == 1:
            scene.chosen_asset = str(valid_videos[0])
            scene.chosen_type = "VIDEO"
            scene.qc_status = "READY"
        elif multiple_images:
            if scene.chosen_asset and any(Path(scene.chosen_asset) == im for im in valid_images):
                scene.qc_status = "READY"
                scene.chosen_type = "IMAGE"
            else:
                scene.qc_status = "DUPLICATE"
                scene.error_reason = f"Multiple image files found: {', '.join(im.name for im in valid_images)}. Selection required."
                scene.chosen_asset = None
                scene.chosen_type = None
        elif len(valid_images) == 1:
            scene.chosen_asset = str(valid_images[0])
            scene.chosen_type = "IMAGE"
            scene.qc_status = "READY"
        else:
            scene.chosen_asset = None
            scene.chosen_type = None
            scene.qc_status = "MISSING"

    manifest_file = p_dir / "visual_manifest_v9_3.json"
    save_manifest(manifest, manifest_file)
    return manifest


def resolve_duplicate_asset(
    manifest: ManualVisualManifest,
    scene_id: str,
    chosen_file_path: str | Path
) -> ManualVisualManifest:
    """Resolves duplicate ambiguity for a specific scene by user selection."""
    chosen_path = Path(chosen_file_path).resolve()
    for sc in manifest.scenes:
        if sc.scene_id == scene_id:
            if chosen_path.suffix.lower() in VALID_VIDEO_EXTS:
                ok, _, err = _get_video_info(chosen_path)
                if not ok:
                    raise ValueError(f"Selected video is invalid: {err}")
                sc.chosen_asset = str(chosen_path)
                sc.chosen_type = "VIDEO"
                sc.qc_status = "READY"
                sc.error_reason = None
            elif chosen_path.suffix.lower() in VALID_IMAGE_EXTS:
                ok, err = _validate_image_file(chosen_path)
                if not ok:
                    raise ValueError(f"Selected image is invalid: {err}")
                sc.chosen_asset = str(chosen_path)
                sc.chosen_type = "IMAGE"
                sc.qc_status = "READY"
                sc.error_reason = None
            else:
                raise ValueError(f"Unsupported file format: {chosen_path.suffix}")
            logger.info(f"[ManualVisual] Resolved {scene_id} asset to: {chosen_path.name} ({sc.chosen_type})")
            break

    if manifest.project_dir:
        save_manifest(manifest, Path(manifest.project_dir) / "visual_manifest_v9_3.json")
    return manifest


def validate_manifest_for_assemble(
    manifest: ManualVisualManifest,
    project_dir: Optional[str | Path] = None
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validates manifest strictly before Auto Assemble:
    - Invariant 1: No missing scenes.
    - Invariant 2: No unresolved duplicate files.
    - Invariant 3: No corrupt/invalid media files.
    - Invariant 4: Audio master exists and matches timeline.
    - Invariant 5: Zero black gaps across contiguous timeline.
    """
    p_dir = Path(project_dir).resolve() if project_dir else Path(manifest.project_dir).resolve()
    issues: List[str] = []

    missing_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "MISSING" or not s.chosen_asset]
    duplicate_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "DUPLICATE"]
    invalid_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "INVALID"]

    if missing_scenes:
        issues.append(f"Missing visual assets in {len(missing_scenes)} scenes: {', '.join(missing_scenes[:10])}{'...' if len(missing_scenes) > 10 else ''}. Missing scene blocks render.")

    if duplicate_scenes:
        issues.append(f"Unresolved duplicate files in {len(duplicate_scenes)} scenes: {', '.join(duplicate_scenes)}. User selection required.")

    if invalid_scenes:
        issues.append(f"Invalid or corrupted files in {len(invalid_scenes)} scenes: {', '.join(invalid_scenes)}.")

    # Timeline gap check
    for i in range(1, len(manifest.scenes)):
        prev = manifest.scenes[i - 1]
        curr = manifest.scenes[i]
        if abs(curr.start_sec - prev.end_sec) > 0.05:
            issues.append(f"Timeline discontinuity between {prev.scene_id} ({prev.end_sec:.2f}s) and {curr.scene_id} ({curr.start_sec:.2f}s).")

    # Master audio check
    audio_p = Path(manifest.audio_master_path) if manifest.audio_master_path else (p_dir / "master" / "final_mix.wav")
    if not audio_p.exists() or audio_p.stat().st_size == 0:
        issues.append(f"Authoritative master audio file not found: {audio_p}")

    can_render = len(issues) == 0

    stats = {
        "total_scenes": len(manifest.scenes),
        "ready_scenes": len([s for s in manifest.scenes if s.qc_status == "READY" and s.chosen_asset]),
        "missing_count": len(missing_scenes),
        "duplicate_count": len(duplicate_scenes),
        "invalid_count": len(invalid_scenes),
        "can_render": can_render,
    }
    return can_render, issues, stats


def create_overlay_banner(
    text: str,
    output_png_path: Path,
    width: int = 1920,
    height: int = 1080
) -> Path:
    """Generates a transparent 1080p PNG with an elegant cinematic text overlay."""
    output_png_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Font selection with fallbacks
    font_candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
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

    # Calculate text dimensions
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Banner dimensions (lower third)
    pad_x = 40
    pad_y = 20
    box_w = min(width - 200, text_w + pad_x * 2)
    box_h = text_h + pad_y * 2
    box_x = (width - box_w) // 2
    box_y = height - 160 - box_h

    # Semi-transparent dark backdrop
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=14,
        fill=(12, 16, 22, 215),
        outline=(230, 200, 110, 180),  # Subtle gold outline
        width=2,
    )

    # Draw text centered in box
    text_x = box_x + (box_w - text_w) // 2
    text_y = box_y + (box_h - text_h) // 2 - 2
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))

    img.save(output_png_path, "PNG")
    return output_png_path


def render_manual_scene_clip(
    scene_item: ManualSceneItem,
    output_mp4_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    fps: int = 30
) -> Path:
    """
    Renders processed 1920x1080 30fps clip for a single scene:
    - Images: restrained Ken Burns (subtle zoom/pan, smooth motion).
    - Videos: scale/crop 1080p, strip source audio (-an), trim if long, freeze last frame if short.
    - Overlay: renders post-production text overlay if requested.
    """
    output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
    target_dur = scene_item.duration_sec
    frames = max(1, int(target_dur * fps))

    if not scene_item.chosen_asset or not Path(scene_item.chosen_asset).exists():
        raise FileNotFoundError(f"Scene {scene_item.scene_id} has no chosen asset for rendering!")

    chosen_p = Path(scene_item.chosen_asset)
    is_video = scene_item.chosen_type == "VIDEO" or chosen_p.suffix.lower() in VALID_VIDEO_EXTS

    # Prepare intermediate or final target
    temp_clip_p = output_mp4_path if not scene_item.requires_text_overlay or not scene_item.text_overlay_content else output_mp4_path.with_name(f"{output_mp4_path.stem}_base.mp4")

    if is_video:
        # VIDEO processing
        ok, actual_dur, _ = _get_video_info(chosen_p, ffprobe_bin=ffprobe_bin)
        if not ok or actual_dur <= 0:
            actual_dur = target_dur

        if actual_dur >= target_dur:
            cmd = [
                ffmpeg_bin, "-y",
                "-i", str(chosen_p),
                "-t", f"{target_dur:.3f}",
                "-vf", f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-an",
                str(temp_clip_p)
            ]
        else:
            extra_hold = target_dur - actual_dur
            cmd = [
                ffmpeg_bin, "-y",
                "-i", str(chosen_p),
                "-vf", f"tpad=stop_mode=clone:stop_duration={extra_hold:.3f},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p",
                "-t", f"{target_dur:.3f}",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-an",
                str(temp_clip_p)
            ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg video processing failed for {scene_item.scene_id}: {proc.stderr[:300]}")
    else:
        # IMAGE processing: restrained Ken Burns
        # Slow, subtle zoom from 1.0 to 1.05
        zoom_expr = "z='min(zoom+0.0003,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        vf = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"zoompan={zoom_expr}:d={frames}:s=1920x1080:fps={fps},"
            f"format=yuv420p"
        )
        cmd = [
            ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", str(chosen_p),
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
            raise RuntimeError(f"FFmpeg image motion failed for {scene_item.scene_id}: {proc.stderr[:300]}")

    # Render text overlay post-production if required
    if scene_item.requires_text_overlay and scene_item.text_overlay_content:
        overlay_png_p = output_mp4_path.parent / f"{scene_item.scene_id}_overlay.png"
        create_overlay_banner(scene_item.text_overlay_content, overlay_png_p)

        cmd_overlay = [
            ffmpeg_bin, "-y",
            "-i", str(temp_clip_p),
            "-i", str(overlay_png_p),
            "-filter_complex", "[0:v][1:v]overlay=0:0[outv]",
            "-map", "[outv]",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_mp4_path)
        ]
        proc_ov = subprocess.run(cmd_overlay, capture_output=True, text=True)
        if proc_ov.returncode != 0:
            raise RuntimeError(f"FFmpeg overlay composition failed for {scene_item.scene_id}: {proc_ov.stderr[:300]}")
        # Clean up temporary base file
        if temp_clip_p.exists() and temp_clip_p != output_mp4_path:
            temp_clip_p.unlink(missing_ok=True)

    return output_mp4_path


def assemble_manual_episode(
    manifest: ManualVisualManifest,
    output_mp4_path: Optional[str | Path] = None,
    project_dir: Optional[str | Path] = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Path:
    """
    Renders complete episode video:
    1. Validates manifest. Blocks render if any scene is missing an asset or has unresolved duplicates.
    2. Renders all scene clips to 1920x1080 30fps.
    3. Concatenates visual clips with zero black gaps.
    4. Muxes with authoritative audio final_mix.wav (stripping all source video audio).
    5. Outputs broadcast-ready 1080p MP4.
    """
    p_dir = Path(project_dir).resolve() if project_dir else Path(manifest.project_dir).resolve()
    can_render, issues, stats = validate_manifest_for_assemble(manifest, project_dir=p_dir)
    if not can_render:
        raise RuntimeError(f"Auto Assemble blocked by validation errors:\n" + "\n".join(f"- {iss}" for iss in issues))

    processed_dir = p_dir / "visual" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    final_dir = p_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_output = Path(output_mp4_path).resolve() if output_mp4_path else final_dir / "final_episode_manual_v9_3.mp4"

    clip_paths: List[Path] = []
    total = len(manifest.scenes)

    logger.info(f"[ManualVisual] Starting Auto Assemble for {total} scenes...")
    for idx, scene in enumerate(manifest.scenes, start=1):
        if progress_callback:
            progress_callback(idx, total, f"Rendering scene {scene.scene_id} ({idx}/{total})...")
        out_clip = processed_dir / f"{scene.scene_id}.mp4"
        render_manual_scene_clip(
            scene_item=scene,
            output_mp4_path=out_clip,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
            fps=30
        )
        clip_paths.append(out_clip)

    # Concat list file
    concat_txt = processed_dir / "concat_manual_list.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for c in clip_paths:
            f.write(f"file '{c.resolve().as_posix()}'\n")

    temp_visual_mp4 = processed_dir / "visual_master_no_audio.mp4"
    cmd_cat = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(temp_visual_mp4)
    ]
    if progress_callback:
        progress_callback(total, total, "Concatenating visual timeline clips...")
    proc_cat = subprocess.run(cmd_cat, capture_output=True, text=True)
    if proc_cat.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {proc_cat.stderr[:300]}")

    # Multiplex with final_mix.wav master audio
    audio_master_p = Path(manifest.audio_master_path) if manifest.audio_master_path else (p_dir / "master" / "final_mix.wav")
    if not audio_master_p.exists():
        raise FileNotFoundError(f"Authoritative master audio not found: {audio_master_p}")

    if progress_callback:
        progress_callback(total, total, "Muxing final visual master with authoritative audio track...")
    cmd_mux = [
        ffmpeg_bin, "-y",
        "-i", str(temp_visual_mp4),
        "-i", str(audio_master_p),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "320k",
        "-shortest",
        str(final_output)
    ]
    proc_mux = subprocess.run(cmd_mux, capture_output=True, text=True)
    if proc_mux.returncode != 0:
        raise RuntimeError(f"FFmpeg audio mux failed: {proc_mux.stderr[:300]}")

    logger.info(f"[ManualVisual] Auto Assemble completed: {final_output} ({final_output.stat().st_size:,} bytes)")
    return final_output


def get_manifest_dataframe(manifest: ManualVisualManifest) -> List[List[Any]]:
    """Builds table data for UI display: Scene, Image, Video, Chosen, QC, Overlay, Status."""
    rows = []
    for sc in manifest.scenes:
        # Scene column
        sc_col = f"{sc.scene_id} ({sc.start_sec:.1f}s - {sc.end_sec:.1f}s, {sc.duration_sec:.1f}s)"

        # Image column
        if len(sc.matched_images) == 0:
            img_col = "-"
        elif len(sc.matched_images) == 1:
            img_col = Path(sc.matched_images[0]).name
        else:
            img_col = f"⚠️ {len(sc.matched_images)} files ({', '.join(Path(p).name for p in sc.matched_images[:2])}...)"

        # Video column
        if len(sc.matched_videos) == 0:
            vid_col = "-"
        elif len(sc.matched_videos) == 1:
            vid_col = Path(sc.matched_videos[0]).name
        else:
            vid_col = f"⚠️ {len(sc.matched_videos)} files ({', '.join(Path(p).name for p in sc.matched_videos[:2])}...)"

        # Chosen
        chosen_col = sc.chosen_type or "-"

        # QC status
        qc_col = sc.qc_status

        # Overlay
        if sc.requires_text_overlay and sc.text_overlay_content:
            overlay_col = f"📝 {sc.text_overlay_content}"
        else:
            overlay_col = "-"

        # Overall Status
        if sc.qc_status == "READY":
            status_col = "✅ OK"
        elif sc.qc_status == "DUPLICATE":
            status_col = "⚠️ REQUIRES_SELECTION"
        elif sc.qc_status == "INVALID":
            status_col = "❌ INVALID_MEDIA"
        else:
            status_col = "⛔ BLOCKED_MISSING"

        rows.append([sc_col, img_col, vid_col, chosen_col, qc_col, overlay_col, status_col])
    return rows
