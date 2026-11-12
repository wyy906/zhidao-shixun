"""快速测 3 个候选模型哪个对我的 NV key 有权限（需要环境变量 NV_API_KEY）"""
import os
import httpx, json

key = os.environ.get('NV_API_KEY', '')
if not key:
    raise SystemExit('缺少环境变量 NV_API_KEY')
models = [
    'nvidia/nemotron-3.5-super-vl-120b-a12b',
    'meta/llama-3.2-90b-vision-instruct',
    'nvidia/cosmos-reason2-8b',
    'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
]
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}

for m in models:
    payload = {
        'model': m,
        'messages': [{'role': 'user', 'content': 'Reply with just "OK".'}],
        'max_tokens': 16,
    }
    try:
        r = httpx.post('https://integrate.api.nvidia.com/v1/chat/completions',
                       json=payload, headers=headers, timeout=30.0)
        if r.status_code == 200:
            print(f'  ✅ {m}  → 200 OK')
        else:
            detail = r.json().get('detail', r.text[:80])
            print(f'  ❌ {m}  → {r.status_code}  {detail[:80]}')
    except Exception as e:
        print(f'  ❌ {m}  → ERR {e}')
