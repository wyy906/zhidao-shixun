"""测试 NVIDIA 视觉 API —— 走完整 provider 链路（需要环境变量 NV_API_KEY）"""
import os, sys, io, base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

from PIL import Image, ImageDraw
from app.engines.visual.provider import get_visual_provider

# 造一张假的 MySQL Workbench 截图
W, H = 1440, 900
img = Image.new('RGB', (W, H), (245, 247, 251))
d = ImageDraw.Draw(img)
d.rectangle([20,100,260,720], fill=(255,255,255), outline=(220,220,220))
d.text((30,115), 'Schemas', fill=(31,41,55))
d.text((30,145), '▾ student_db', fill=(31,41,55))
d.rectangle([140,115,250,145], fill=(34,197,94))
d.text((150,122), 'Create Schema', fill=(255,255,255))
d.rectangle([290,180,1400,680], fill=(30,30,30), outline=(60,60,60))
d.text((300,195), 'SQL Editor', fill=(156,163,175))
d.rectangle([980,720,1060,752], fill=(79,110,247))
d.text((1000,728), 'Apply', fill=(255,255,255))
d.text((20,20), 'MySQL Workbench - student_db', fill=(31,41,55))

buf = io.BytesIO(); img.save(buf, 'PNG')
b64 = base64.b64encode(buf.getvalue()).decode()

p = get_visual_provider()
# 强制覆盖单例里的旧值（绕过 .env 缓存）
p.base_url = 'https://integrate.api.nvidia.com/v1'
p.api_key = os.environ.get('NV_API_KEY', '')
if not p.api_key:
    raise SystemExit('缺少环境变量 NV_API_KEY')
p.model = 'microsoft/phi-3-vision-128k-instruct'

print(f'>>> Provider: {p.base_url}')
print(f'>>> Model:    {p.model}')
print(f'>>> Key:      {p.api_key[:12]}...')
print()

# 不走 provider，直接裸调，绕过 response_format 可能的兼容问题
import httpx, json

payload = {
    'model': p.model,
    'messages': [
        {'role': 'system', 'content': (
            'You are a software UI analyzer. '
            'Return ONLY a JSON object with keys: '
            'software (string), window_title (string), '
            'elements (array of {name, control_type, x, y, width, height, confidence}), '
            'current_state (string), confidence (float 0-1). '
            'Coordinates are in pixels relative to the image top-left. '
            'Do not wrap in markdown code blocks.'
        )},
        {'role': 'user', 'content': [
            {'type': 'text', 'text': 'Analyze this software screenshot and return JSON.'},
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
        ]},
    ],
    'max_tokens': 2048,
    'temperature': 0.1,
}
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {p.api_key}'}

print('>>> POST chat/completions ...', flush=True)
try:
    r = httpx.post(f'{p.base_url}/chat/completions', json=payload, headers=headers, timeout=60.0)
    print(f'HTTP {r.status_code}  ({len(r.content)} bytes)')
    if r.status_code != 200:
        print(r.text[:500])
    else:
        content = r.json()['choices'][0]['message']['content']
        print()
        print('=== 模型原始回复 ===')
        print(content[:500])
        print()
        try:
            parsed = json.loads(content.strip().strip('`'))
            print('=== 解析后的 JSON ===')
            import json as j; print(j.dumps(parsed, indent=2, ensure_ascii=False)[:1500])
        except Exception as e:
            print(f'JSON 解析失败: {e}')
except Exception as e:
    print(f'异常: {e}')
