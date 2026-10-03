import json, sys, os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

EPISODES = ["EP2014", "EP2015", "EP2016"]
BASE_DIR = Path("D:/App/VieNeuTTS")
PROJECTS_DIR = BASE_DIR / "projects"

from apps.script_factory.vietnamese_cleaner import find_garbled_vietnamese_issues

results = []

for ep_id in EPISODES:
    ep_dir = PROJECTS_DIR / ep_id
    script_path = ep_dir / "script" / "full_script.json"
    story_path = ep_dir / "story" / "story_bible.json"
    qc_path = ep_dir / "script" / "qc_report.json"
    project_path = ep_dir / "project.json"

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)
    with open(story_path, "r", encoding="utf-8") as f:
        story_data = json.load(f)
    with open(qc_path, "r", encoding="utf-8") as f:
        qc_data = json.load(f)
    with open(project_path, "r", encoding="utf-8") as f:
        project_data = json.load(f)

    # Check garbled issues across segments
    garbled_findings = []
    for s in script_data.get("segments", []):
        issues = find_garbled_vietnamese_issues(s.get("text", ""))
        if issues:
            garbled_findings.append({"seg": s["id"], "issues": issues})

    stages = project_data.get("stages", {})
    script_stage = stages.get("script", {})

    ep_info = {
        "episode_id": ep_id,
        "title": story_data.get("working_title") or story_data.get("title"),
        "user_topic": story_data.get("user_topic") or story_data.get("topic_intent", {}).get("original_topic"),
        "script_stage_status": script_stage.get("status"),
        "qc_status": qc_data.get("status"),
        "audio_gate_allowed": script_stage.get("status") == "APPROVED" and qc_data.get("status") == "PASS",
        "generation_source": script_data.get("generation_source"),
        "requested_model": script_data.get("requested_model"),
        "actual_model": script_data.get("actual_model") or script_data.get("model_name"),
        "story_generation_request_id": story_data.get("generation_request_id"),
        "script_generation_request_id": script_data.get("generation_request_id"),
        "total_segments": len(script_data.get("segments", [])),
        "total_words": script_data.get("total_words") or sum(len(s["text"].split()) for s in script_data.get("segments", [])),
        "garbled_issues_count": len(garbled_findings),
        "hook_text": script_data.get("segments", [])[0]["text"] if script_data.get("segments") else "",
        "reveal_text": script_data.get("segments", [])[len(script_data.get("segments", []))//2]["text"] if script_data.get("segments") else "",
        "climax_text": script_data.get("segments", [])[-2]["text"] if script_data.get("segments") else "",
        "ending_text": script_data.get("segments", [])[-1]["text"] if script_data.get("segments") else "",
    }
    results.append(ep_info)

print(json.dumps(results, ensure_ascii=False, indent=2))
