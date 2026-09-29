import json
import urllib.request

BASE_URL = "http://127.0.0.1:8765"


def post(url, data):
    req = urllib.request.Request(
        f"{BASE_URL}{url}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def get(url):
    req = urllib.request.Request(f"{BASE_URL}{url}")
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def run_acceptance():
    print("=== 1. AI Providers ===")
    s, p_status = get("/api/ai/providers")
    print(f"Status: {s}, Connected: {p_status['has_connected_provider']}")

    print("=== 2. Next Episode ID ===")
    s, next_id_data = get("/api/projects/next-id")
    next_id = next_id_data["episode_id"]
    print(f"Next ID: {next_id}")

    test_ep = next_id
    print("=== 3. Project Creation ===")
    s, proj = post("/api/projects/create", {
        "episode_id": test_ep,
        "title": "Tap Thu Nghiem Web Test",
        "premise": "Nguoi chau phat hien chiec hom thu bi an nam 1990.",
        "target_duration": 1200,
        "category": "Gia đình / Bí ẩn",
    })
    print(f"Created Project: {proj['project_id']}, title: {proj['title']}")

    print("=== 4. Generate AI Ideas ===")
    s, ideas_res = post(f"/api/projects/{test_ep}/ideas/generate", {
        "direction": "BI MAT GIA DINH",
        "count": 5,
    })
    ideas = ideas_res.get("ideas", [])
    print(f"Generated {len(ideas)} ideas.")
    assert len(ideas) > 0, "No ideas generated"

    print("=== 5. CHON TAP NAY (Select Idea) ===")
    chosen = ideas[0]
    s, sel_res = post(f"/api/projects/{test_ep}/ideas/select", {
        "idea": chosen,
    })
    print(f"Select Idea status: {s}, 01_idea status: {sel_res['stage_statuses']['01_idea']}")
    assert sel_res["stage_statuses"]["01_idea"] == "APPROVED"

    print("=== 6. Story Bible Query (Premise Grounding) ===")
    s, story_before = get(f"/api/projects/{test_ep}/story")
    print(f"Story premise pre-filled: {bool(story_before['premise'])}, length: {len(story_before['premise'])}")
    assert len(story_before["premise"]) > 10

    print("=== 7. Generate Story Bible ===")
    s, bible_res = post(f"/api/projects/{test_ep}/story/generate", {
        "topic": story_before["premise"],
    })
    print(f"Story Bible generated: {s}, Has Fact Lock: {'fact_lock' in bible_res}")
    assert "fact_lock" in bible_res

    print("=== 8. Approve Story Bible ===")
    s, app_res = post(f"/api/projects/{test_ep}/story/approve", {})
    print(f"Story Approved: {app_res['stage_statuses']['02_story']}")
    assert app_res["stage_statuses"]["02_story"] == "APPROVED"

    print("=== 9. Generate Full Script V1.3.1a ===")
    s, script_res = post(f"/api/projects/{test_ep}/script/generate", {"force": False})
    segments = script_res["script"]["segments"]
    qc_stat = script_res["qc_report"].get("status") or script_res["qc_report"].get("overall_status")
    print(f"Script Generated: {s}, Segments: {len(segments)}, QC status: {qc_stat}")
    assert len(segments) >= 40

    print("=== 10. Query Script QC & Full Text ===")
    s, qc_res = get(f"/api/projects/{test_ep}/script/qc")
    print(f"QC Status: {qc_res.get('status')}")
    s, full_res = get(f"/api/projects/{test_ep}/script/full")
    print(f"Full Script text length: {len(full_res['text'])}")
    assert len(full_res["text"]) > 100

    print("=== VERIFY EP001, EP003, EP011 UNTOUCHED ===")
    from pathlib import Path
    assert (Path("episodes/EP001").exists() or Path("episodes/EP001/story_bible.json").exists())
    for ep in ["EP003", "EP011"]:
        s, ep_data = get(f"/api/projects/{ep}")
        print(f"Pilot {ep}: Status {s}, Scenes: {ep_data['scene_count']}")
        assert ep_data["scene_count"] == 45

    print("\n>>> ALL 10 STEPS PASSED SUCCESSFULLY! FULL PIPELINE VERIFIED! <<<")


if __name__ == "__main__":
    run_acceptance()
