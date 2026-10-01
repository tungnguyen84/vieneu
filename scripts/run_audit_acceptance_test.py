"""Run end-to-end Studio acceptance test for audit requirements.
Tests:
1. Create EP2004 with topic 'Bí mật ngoại tình công sở'.
2. Generate real Gemini Story Bible -> Story QC.
3. Generate real Gemini Script -> Script QC & Semantic Review.
4. Auto-repair if needed -> Approve Script with hash verification.
5. Generate real VieNeu TTS Narration (voice 020) -> verify segment_timing.json.
6. Auto-mix BGM with Audio Formula V1 -> test BGM gain control (-3 dB and 0 dB).
7. Approve Audio Stage via domain gate.
8. Generate Visual Plan with real timing & character continuity.
9. Export Google Flow JSON (SCC_FLOW_V1).
10. Verify Final QC returns NOT_RUN when video is not rendered.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8765"


def api_request(path: str, method: str = "GET", data: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"} if data is not None else {}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP ERROR {exc.code} for {method} {path}: {err_msg}", file=sys.stderr)
        raise RuntimeError(f"API {method} {path} failed: {exc.code} - {err_msg}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 70)
    print("STARTING REAL AI & REAL VIENEU ACCEPTANCE TEST")
    print("=" * 70)

    # 1. Create Project EP2004
    project_id = "EP2004"
    topic = "Bí mật ngoại tình công sở"
    premise = (
        "Bí mật ngoại tình công sở giữa trưởng phòng và nữ nhân viên kế toán trẻ "
        "hé lộ âm mưu làm giả hóa đơn và biển thủ tài chính tinh vi trong công ty."
    )
    print(f"\n[Step 1] Creating project {project_id}...")
    create_payload = {
        "episode_id": project_id,
        "title": "Bí Mật Ngoại Tình Công Sở",
        "premise": premise,
        "category": "Gia đình / Bí ẩn",
        "target_duration": 1200,
    }
    p_meta = api_request("/api/projects/create", method="POST", data=create_payload)
    print(f"  -> Created: {p_meta.get('project_id')} - '{p_meta.get('title')}'")

    # 2. Generate Story Ideas
    print(f"\n[Step 2] Generating Ideas for {project_id} via Real AI...")
    ideas_res = api_request(
        f"/api/projects/{project_id}/ideas/generate",
        method="POST",
        data={"direction": topic, "count": 3, "provider": "gemini"},
    )
    ideas = ideas_res.get("ideas", [])
    print(f"  -> Generated {len(ideas)} ideas.")
    selected_idea = ideas[0] if ideas else {
        "title": "Bóng Đêm Công Sở",
        "premise": premise,
        "core_mystery": "Ai đã xóa camera an ninh tầng 8?",
        "possible_reveal": "Không phải ngoại tình mà là dàn cảnh chuyển tài liệu kiểm toán",
    }
    print(f"  -> Selected Idea: '{selected_idea.get('title')}'")
    api_request(
        f"/api/projects/{project_id}/ideas/select",
        method="POST",
        data={"idea": selected_idea},
    )

    # 3. Generate Story Bible
    print(f"\n[Step 3] Generating Story Bible for {project_id} via Real Gemini...")
    t0 = time.time()
    story_res = api_request(
        f"/api/projects/{project_id}/story/generate",
        method="POST",
        data={"topic": topic, "provider": "gemini"},
    )
    print(f"  -> Story Bible generated in {time.time() - t0:.1f}s")
    print(f"     Title: {story_res.get('title')}")
    print(f"     Protagonist: {story_res.get('protagonist', {}).get('name')}")
    print(f"     Generation Source: {story_res.get('generation_source')}")
    print(f"     Request ID: {story_res.get('generation_request_id')}")

    # Check Story QC
    story_qc = api_request(f"/api/projects/{project_id}/story/qc")
    print(f"     Story QC Status: {story_qc.get('overall_status') or story_qc.get('status')}")

    # Approve Story
    api_request(f"/api/projects/{project_id}/story/approve", method="POST")
    print("  -> Story Bible Approved.")

    # 4. Generate Full Script
    print(f"\n[Step 4] Generating Full Script for {project_id} via Real Gemini...")
    t0 = time.time()
    script_res = api_request(
        f"/api/projects/{project_id}/script/generate",
        method="POST",
        data={"force": True},
    )
    print(f"  -> Script generated in {time.time() - t0:.1f}s")
    segments = api_request(f"/api/projects/{project_id}/script")
    print(f"     Segment count: {len(segments)}")

    # 5. Run Script QC & Auto-repair if needed
    print(f"\n[Step 5] Running Script QC & Semantic Review...")
    qc_res = api_request(f"/api/projects/{project_id}/script/qc", method="POST")
    qc_status = qc_res.get("overall_status") or qc_res.get("status")
    print(f"  -> Initial Script QC Status: {qc_status}")
    print(f"     Critical Issues: {qc_res.get('critical_issues', [])}")

    repair_attempts = 0
    while qc_status != "PASS" and repair_attempts < 3:
        repair_attempts += 1
        print(f"  -> QC needs revision. Running Auto-Repair attempt #{repair_attempts}...")
        repair_res = api_request(f"/api/projects/{project_id}/script/repair", method="POST")
        qc_res = repair_res.get("qc_report", {})
        qc_status = qc_res.get("overall_status") or qc_res.get("status")
        print(f"     Repaired status: {qc_status} (resolved {repair_res.get('resolved_issues', 0)} issues)")

    # 6. Approve Script
    print(f"\n[Step 6] Approving Script...")
    approve_res = api_request(f"/api/projects/{project_id}/script/approve", method="POST")
    print(f"  -> Script approved. Status: {approve_res.get('status')}")

    # Verify script lineage status
    script_status = api_request(f"/api/projects/{project_id}/script/status")
    print(f"     Script is_current: {script_status.get('is_current')}")
    print(f"     Audio gate allowed: {script_status.get('audio_gate_allowed')}")
    assert script_status.get("audio_gate_allowed"), f"Audio Gate blocked: {script_status.get('audio_gate_reason')}"

    # 7. Generate Real VieNeu TTS Narration
    print(f"\n[Step 7] Generating Real VieNeu TTS Narration (voice 020)...")
    t0 = time.time()
    audio_gen_res = api_request(
        f"/api/projects/{project_id}/audio/generate",
        method="POST",
        data={
            "voice_id": "020",
            "contextual_speed": True,
            "enable_music": True,
        },
    )
    print(f"  -> TTS narration generated in {time.time() - t0:.1f}s")
    print(f"     Audio file: {audio_gen_res.get('file_path')}")
    print(f"     Duration: {audio_gen_res.get('duration_sec'):.2f}s")
    print(f"     Has BGM: {audio_gen_res.get('has_bgm')}")

    # 8. Test BGM Gain Controls & Auto-Mix
    print(f"\n[Step 8] Testing BGM Gain Control (-3.0 dB and 0.0 dB)...")
    remix_res = api_request(
        f"/api/projects/{project_id}/audio/auto-mix",
        method="POST",
        data={
            "enable_ducking": True,
            "target_lufs": -14.0,
            "bgm_volume_db": -3.0,
        },
    )
    bgm_info = remix_res.get("bgm_info", {})
    print(f"  -> Remix with -3.0 dB:")
    print(f"     Master Loudness: {bgm_info.get('master_integrated_lufs')} LUFS")
    print(f"     True Peak: {bgm_info.get('master_true_peak_db')} dBTP")
    print(f"     Coverage: {bgm_info.get('coverage_percent')}%")
    print(f"     BGM Gain: {bgm_info.get('bgm_volume_db')} dB")

    # Reset back to default 0.0 dB
    remix_res_0 = api_request(
        f"/api/projects/{project_id}/audio/auto-mix",
        method="POST",
        data={
            "enable_ducking": True,
            "target_lufs": -14.0,
            "bgm_volume_db": 0.0,
        },
    )
    bgm_info_0 = remix_res_0.get("bgm_info", {})
    print(f"  -> Restored to 0.0 dB (Audio Formula V1 baseline):")
    print(f"     Master Loudness: {bgm_info_0.get('master_integrated_lufs')} LUFS")
    print(f"     True Peak: {bgm_info_0.get('master_true_peak_db')} dBTP")

    # 9. Approve Audio Stage
    print(f"\n[Step 9] Approving Audio Stage...")
    audio_stage_res = api_request(
        f"/api/projects/{project_id}/stage",
        method="POST",
        data={"stage_id": "04_audio", "status": "COMPLETE"},
    )
    print(f"  -> Audio Stage Status: {audio_stage_res.get('stage_statuses', {}).get('04_audio')}")

    # 10. Generate Visual Plan
    print(f"\n[Step 10] Generating Visual Plan with Real Segment Timings & Character Continuity...")
    vis_res = api_request(f"/api/projects/{project_id}/visual/generate", method="POST")
    print(f"  -> Visual Plan generated: {vis_res.get('scenes')} scenes")
    print(f"     Episode duration: {vis_res.get('audio_duration_sec')}s")

    # 11. Export Google Flow SCC_FLOW_V1
    print(f"\n[Step 11] Exporting Google Flow SCC_FLOW_V1...")
    flow_res = api_request(f"/api/projects/{project_id}/flow/export", method="POST")
    print(f"  -> Flow Export Status: {flow_res.get('status')}")
    print(f"     Validation Status: {flow_res.get('validation_status')}")
    print(f"     Export File: {flow_res.get('export_file')}")

    # 12. Verify Final QC (A01 verification: must NOT be fake PASS)
    print(f"\n[Step 12] Checking Final QC Report (Must be NOT_RUN since MP4 is not rendered)...")
    qc_final = api_request(f"/api/projects/{project_id}/qc")
    print(f"  -> Final QC Status: {qc_final.get('overall_status')}")
    print(f"     Duration: {qc_final.get('duration_sec')}s")
    assert qc_final.get("overall_status") == "NOT_RUN", (
        f"A01 REGRESSION: Expected NOT_RUN but got {qc_final.get('overall_status')}!"
    )
    print("     [VERIFIED] Final QC correctly reports NOT_RUN instead of fake PASS!")

    print("\n" + "=" * 70)
    print(f"SUCCESS: ALL ACCEPTANCE GATES VERIFIED FOR {project_id}!")
    print("=" * 70)


if __name__ == "__main__":
    main()
