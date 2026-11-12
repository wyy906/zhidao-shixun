"""测试不同 NVIDIA 视觉模型的速度和识别质量（需要环境变量 NV_API_KEY）"""
import os
import sys, io, base64, json, time
import httpx
from PIL import Image, ImageDraw

key = os.environ.get('NV_API_KEY', '')
if not key:
    raise SystemExit('缺少环境变量 NV_API_KEY')

W, H = 1440, 900
img = Image.new('RGB', (W, H), (245, 247, 251))
d = ImageDraw.Draw(img)
d.rectangle([20, 100, 260, 720], fill=(255, 255, 255), outline=(220, 220, 220))
d.text((30, 115), 'Schemas', fill=(31, 41, 55))
d.text((30, 145), '▾ student_db', fill=(31, 41, 55))
d.rectangle([140, 115, 250, 145], fill=(34, 197, 94))
d.text((150, 122), 'Create Schema', fill=(255, 255, 255))
d.text((20, 20), 'MySQL Workbench - student_db', fill=(31, 41, 55))
buf = io.BytesIO()
img.save(buf, 'PNG')
b64 = base64.b64encode(buf.getvalue()).decode()

prompt = """你是软件界面分析助手。请严格返回 JSON：
{"software":"软件名","elements":[{"name":"控件文字","control_type":"Button|Edit|Text|MenuItem","x":0,"y":0,"width":0,"height":0,"confidence":0.9}],"current_state":"一句话描述","confidence":0.9}
只列与操作相关的控件（按钮、输入框、菜单、标签页），忽略纯装饰。"""

models = [
    ('meta/llama-3.2-90b-vision-instruct', 4096),
    ('mistralai/mistral-large-4-1t-a52b', 4096),
]

for model, max_tok in models:
    print(f'\n{"="*60}')
    print(f'⏳ Testing: {model}')
    print(f'{"="*60}')

    payload = {
        'model': model,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
            ],
        }],
        'response_format': {'type': 'json_object'},
        'max_tokens': max_tok,
        'temperature': 0.1,
    }

    t0 = time.time()
    try:
        r = httpx.post(
            'https://integrate.api.nvidia.com/v1/chat/completions',
            json=payload,
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
            timeout=120.0,
        )
        dt = time.time() - t0
        print(f'HTTP {r.status_code} | {dt:.1f}s')
        if r.status_code != 200:
            print(r.text[:400])
            continue
        content = r.json()['choices'][0]['message']['content']
        c2 = str(content).strip() if content else ''
        try:
            obj = json.loads(c2)
            print(f'✅ JSON OK | software={obj.get("software","")} | elements={len(obj.get("elements",[]))}')
            for el in obj.get('elements', []):
                print(f'  • {el.get("name")!r:25s} [{el.get("control_type")}] ({el.get("x")},{el.get("y")}) conf={el.get("confidence")}')
        except Exception as e:
            print(f'❌ JSON parse error: {e}')
            print(f'   raw[:300]: {c2[:300]}')
    except Exception as e:
        print(f'❌ Exception after {time.time()-t0:.1f}s: {e}')
