"""Automated Test Suite for V9.3.2 Dynamic Still Engine.

Verifies:
1. DynamicStillPlanner creates virtual shots following documentary reframing rules.
2. Safe crop margins (max zoom <= 1.12).
3. Shot duration thresholds (<=7s 1 shot, 7-12s 2 shots, 12-18s 3 shots, >18s 3-4 shots).
4. Real static hold inspection (longest hold <= 2.0s).
5. Integration with render_dynamic_still_scene.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from PIL import Image
import pytest

from apps.visual_engine.dynamic_still_engine import (
    DynamicStillPlanner,
    SceneVirtualPlan,
    VirtualShot,
    inspect_real_static_holds,
    render_dynamic_still_scene,
)


@pytest.fixture
def sample_test_image(tmp_path: Path) -> Path:
    """Creates a temporary test image with distinct visual patterns."""
    img_path = tmp_path / "test_still_image.png"
    img = Image.new("RGB", (1920, 1080), color=(30, 45, 60))
    img.save(img_path, "PNG")
    return img_path


def test_dynamic_still_planner_short_scene():
    planner = DynamicStillPlanner()
    plan = planner.plan_scene("SC_TEST_01", "dummy.png", 5.5)
    assert len(plan.virtual_shots) == 1
    assert plan.virtual_shots[0].composition == "WIDE"
    assert abs(plan.total_duration_sec - 5.5) < 1e-4
    for shot in plan.virtual_shots:
        assert shot.zoom_start <= 1.12
        assert shot.zoom_end <= 1.12


def test_dynamic_still_planner_medium_scene():
    planner = DynamicStillPlanner()
    plan = planner.plan_scene("SC_TEST_02", "dummy.png", 10.0)
    assert len(plan.virtual_shots) == 2
    assert plan.virtual_shots[0].composition == "WIDE"
    assert plan.virtual_shots[1].composition in ["MEDIUM", "DETAIL"]
    assert abs(plan.total_duration_sec - 10.0) < 1e-4


def test_dynamic_still_planner_long_scene():
    planner = DynamicStillPlanner()
    plan = planner.plan_scene("SC_TEST_03", "dummy.png", 15.0)
    assert len(plan.virtual_shots) == 3
    assert abs(plan.total_duration_sec - 15.0) < 1e-4


def test_dynamic_still_planner_very_long_scene():
    planner = DynamicStillPlanner()
    # 26.64s like SC_003
    plan = planner.plan_scene("SC_003", "dummy.png", 26.64)
    assert len(plan.virtual_shots) in [3, 4]
    assert abs(plan.total_duration_sec - 26.64) < 1e-4
    # All shot durations must be <= 7.5s
    for shot in plan.virtual_shots:
        assert shot.duration_sec <= 7.5
        assert shot.zoom_start <= 1.12
        assert shot.zoom_end <= 1.12


def test_render_dynamic_still_scene_and_inspect_holds(sample_test_image: Path, tmp_path: Path):
    scene_plan = SceneVirtualPlan(
        scene_id="SC_TEST",
        source_image=str(sample_test_image),
        total_duration_sec=6.0,
        virtual_shots=[
            VirtualShot(
                shot_index=1,
                start_sec=0.0,
                end_sec=3.0,
                duration_sec=3.0,
                composition="WIDE",
                motion="SLOW_PUSH_IN",
                zoom_start=1.00,
                zoom_end=1.04,
            ),
            VirtualShot(
                shot_index=2,
                start_sec=3.0,
                end_sec=6.0,
                duration_sec=3.0,
                composition="MEDIUM",
                motion="SLOW_PULL_OUT",
                zoom_start=1.06,
                zoom_end=1.02,
            ),
        ],
    )

    out_clip = tmp_path / "dynamic_clip.mp4"
    rendered = render_dynamic_still_scene(scene_plan, out_clip, tmp_path / "cache")
    assert rendered.exists()
    assert rendered.stat().st_size > 0

    # Inspect static holds using FFmpeg freezedetect
    longest_hold, freezes = inspect_real_static_holds(rendered, max_threshold=2.0)
    assert longest_hold <= 2.0
    assert len(freezes) == 0
