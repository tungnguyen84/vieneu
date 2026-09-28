"""Resolvers for Visual Engine Pipeline Configuration.

Provides single source of truth for:
- Flow Project ID resolution (UI -> Preset -> Adapter Default -> Fallback)
- Video Duration resolution (Scene -> UI -> Preset -> 8s Fallback)
- Model family identifiers matching FlowKit wire protocol.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

DEFAULT_FLOW_PROJECT_ID = "b36fca1c-4d91-49eb-a7f7-5c3b7dd1598e"
OMNI_FLASH_DURATIONS: List[int] = [4, 6, 8, 10]
DEFAULT_VIDEO_DURATION: int = 8
DEFAULT_VIDEO_MODEL: str = "omni_flash"
DEFAULT_IMAGE_MODEL: str = "NANO_BANANA_PRO"

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def resolve_flow_project_id(
    ui_project_id: Optional[str] = None,
    visual_preset: Optional[Union[Dict[str, Any], Any]] = None,
    adapter_default: Optional[str] = None
) -> str:
    """Resolve active Google Flow Project ID using strict precedence:
    1. UI Project ID if user entered a non-empty string.
    2. Visual Preset 'flow_project_id'.
    3. FlowKitAdapter default / session project ID.
    4. DEFAULT_FLOW_PROJECT_ID ('b36fca1c-4d91-49eb-a7f7-5c3b7dd1598e').
    """
    if ui_project_id is not None:
        cleaned = str(ui_project_id).strip()
        if cleaned:
            return cleaned

    if visual_preset is not None:
        if isinstance(visual_preset, dict):
            pid = visual_preset.get("flow_project_id")
        else:
            pid = getattr(visual_preset, "flow_project_id", None)
        if pid and str(pid).strip():
            return str(pid).strip()

    if adapter_default is not None:
        cleaned = str(adapter_default).strip()
        if cleaned:
            return cleaned

    return DEFAULT_FLOW_PROJECT_ID


def resolve_video_duration(
    scene: Optional[Any] = None,
    ui_duration: Optional[Union[int, str]] = None,
    preset: Optional[Union[Dict[str, Any], Any]] = None
) -> int:
    """Resolve Omni 1.1 Flash clip duration (in seconds) using strict precedence:
    1. Scene-specific duration (scene.video_duration_sec).
    2. UI-selected duration (e.g. 4, 6, 8, 10, or '8s').
    3. Visual preset 'video_duration_default'.
    4. 8 seconds fallback.

    Validates that result is strictly in [4, 6, 8, 10], raising ValueError otherwise.
    """
    resolved: Optional[int] = None

    # 1. Scene-specific duration
    if scene is not None:
        scene_dur = None
        if isinstance(scene, dict):
            scene_dur = scene.get("video_duration_sec")
        else:
            scene_dur = getattr(scene, "video_duration_sec", None)

        if scene_dur is not None:
            try:
                resolved = int(round(float(scene_dur)))
            except (ValueError, TypeError):
                pass

    # 2. UI selected duration
    if resolved is None and ui_duration is not None:
        raw_ui = str(ui_duration).strip().lower().replace("s", "")
        if raw_ui:
            try:
                resolved = int(raw_ui)
            except (ValueError, TypeError):
                pass

    # 3. Visual Preset default
    if resolved is None and preset is not None:
        preset_dur = None
        if isinstance(preset, dict):
            preset_dur = preset.get("video_duration_default")
        else:
            preset_dur = getattr(preset, "video_duration_default", None)

        if preset_dur is not None:
            try:
                resolved = int(preset_dur)
            except (ValueError, TypeError):
                pass

    # 4. Fallback
    if resolved is None:
        resolved = DEFAULT_VIDEO_DURATION

    # Strict validation: never silently accept invalid duration
    if resolved not in OMNI_FLASH_DURATIONS:
        raise ValueError(
            f"Omni 1.1 Flash duration {resolved}s is invalid; "
            f"must be one of {OMNI_FLASH_DURATIONS}"
        )

    return resolved


def resolve_video_model(
    ui_model: Optional[str] = None,
    preset: Optional[Union[Dict[str, Any], Any]] = None
) -> str:
    """Resolve internal video model_family identifier matching FlowKit API."""
    if ui_model is not None:
        cleaned = str(ui_model).strip().lower()
        if "omni" in cleaned or "flash" in cleaned:
            return "omni_flash"
        if "veo" in cleaned:
            return "veo"

    if preset is not None:
        if isinstance(preset, dict):
            vm = preset.get("video_model")
        else:
            vm = getattr(preset, "video_model", None)
        if vm and str(vm).strip():
            return str(vm).strip()

    return DEFAULT_VIDEO_MODEL
