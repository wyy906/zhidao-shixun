"""列出 NVIDIA API Catalog 当前可用的视觉/多模态模型（需要环境变量 NV_API_KEY）"""
import os
import httpx, json

key = os.environ.get('NV_API_KEY', '')
if not key:
    raise SystemExit('缺少环境变量 NV_API_KEY')
r = httpx.get('https://integrate.api.nvidia.com/v1/models',
              headers={'Authorization': f'Bearer {key}'}, timeout=15)
print(f'HTTP {r.status_code}')
if r.status_code != 200:
    print(r.text[:300])
    raise SystemExit(1)

data = r.json()
models = data.get('data', [])
print(f'Total models: {len(models)}')
print()

keywords = ['vision', 'vl', 'multimodal', 'large-4', 'super-vl', 'cosmos', 'omni',
            'qwen', 'deepseek-vl', 'chatvl', 'internvl', 'llama-3.2']

visual_models = []
for m in models:
    vid = m.get('id', '')
    owned = m.get('owned_by', '')
    txt = (vid + owned).lower()
    if any(k in txt for k in keywords):
        visual_models.append(vid)
        print(f'  ✅ {vid}  ({owned})')

print()
print(f'共发现 {len(visual_models)} 个视觉/多模态相关模型')
