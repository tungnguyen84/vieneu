"""Read-only verification using the same validator as Studio approval/audio."""
import argparse
import json
from pathlib import Path
import sys
import urllib.request

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from studio.backend.services.artifact_lineage import validate_full_script


def verify(episode_id, api_url):
    base = BASE_DIR / 'projects' / episode_id
    script = json.loads((base / 'script/full_script.json').read_text(encoding='utf-8'))
    story = json.loads((base / 'story/story_bible.json').read_text(encoding='utf-8'))
    qc = json.loads((base / 'script/qc_report.json').read_text(encoding='utf-8'))
    disk = validate_full_script(episode_id, BASE_DIR / 'projects')
    with urllib.request.urlopen(f'{api_url.rstrip("/")}/api/projects/{episode_id}/script/status', timeout=15) as response:
        live = json.load(response)
    consistent = disk.get('script_content_hash') == live.get('script_content_hash')
    return {'episode_id':episode_id,'title':script.get('title'),
        'generation_source':script.get('generation_source'),
        'story_generation_request_id':story.get('generation_request_id'),
        'script_generation_request_id':script.get('generation_request_id'),
        'requested_model':script.get('requested_model'),'actual_model':script.get('actual_model'),
        'segments':len(script.get('segments',[])),
        'words':sum(len(s['text'].split()) for s in script.get('segments',[])),
        'qc_version':qc.get('qc_version'),'semantic_review':qc.get('semantic_review'),
        'disk_validator':disk,'live_status':live,'disk_matches_api':consistent,
        'accepted':bool(consistent and disk.get('audio_gate_allowed') and live.get('audio_gate_allowed'))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episodes', nargs='+')
    parser.add_argument('--api-url', default='http://127.0.0.1:8765')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = [verify(ep,args.api_url) for ep in args.episodes]
    payload = json.dumps(results,ensure_ascii=False,indent=2)
    if args.output:
        args.output.write_text(payload,encoding='utf-8')
    print(payload)
    raise SystemExit(0 if all(r['accepted'] for r in results) else 1)
