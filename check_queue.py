import json
import os

cache_path = 'queue_cache.json'
if not os.path.exists(cache_path):
    print('No queue_cache.json found')
else:
    data = json.load(open(cache_path, 'r', encoding='utf-8'))
    queue = data.get('queue', [])
    print(f'Total items: {len(queue)}')
    for i, it in enumerate(queue):
        print(f'\nItem {i}:')
        print(f'  status        = {it.get("status")}')
        print(f'  resume_from_step = {it.get("resume_from_step")}')
        print(f'  step_index    = {it.get("step_index")}')
        print(f'  progress      = {it.get("progress")}')
        print(f'  message       = {str(it.get("message",""))[:80]}')
        print(f'  video         = {str(it.get("video",""))[:60]}')
        print(f'  draft_id      = {it.get("draft_id")}')
        cfg = it.get("config", {})
        print(f'  tts_engine    = {cfg.get("tts_engine")}')
