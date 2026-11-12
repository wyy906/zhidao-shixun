"""测试 nemotron-3.5-super-vl-120b-a12b 视觉理解（需要环境变量 NV_API_KEY）"""
import os
import sys, io, base64, json
from pathlib import Path

from PIL import Image, ImageDraw
import httpx

# 造一张真的 MySQL Workbench 风格假截图
W, H = 1440, 900
img = Image.new('RGB', (W, H), (245, 247, 251))
d = ImageDraw.Draw(img)
d.rectangle([20, 100, 260, 720], fill=(255,255,255), outline=(220,220,220))
d.text((30, 115), 'Schemas', fill=(31,41,55))
d.text((30, 145), '▾ student_db', fill=(31,41,55))
d.text((40, 170), '▴ Tables', fill=(107,114,128))
d.text((40, 195), '  student', fill=(17,24,39))
d.text((40, 220), '  course', fill=(17,24,39))
d.rectangle([140,115,250,145], fill=(34,197,94))
d.text((150,122), 'Create Schema', fill=(255,255,255))
d.rectangle([290,180,1400,680], fill=(30,30,30), outline=(60,60,60))
d.text((300,195), 'SQL Editor', fill=(156,163,175))
d.rectangle([980,720,1060,752], fill=(79,110,247))
d.text((1000,728), 'Apply', fill=(255,255,255))
d.text((20,20), 'MySQL Workbench - student_db', fill=(31,41,55))

buf = io.BytesIO(); img.save(buf, 'PNG')
b64 = base64.b64encode(buf.getvalue()).decode()

# 也存一份真图方便事后看
out_path = Path(__file__).resolve().parent.parent / 'docs' / 'test_mock_ui.png'
out_path.parent.mkdir(exist_ok=True)
img.save(out_path)
print(f'📸 假截图已保存: {out_path}  ({W}x{H})')

api_key = os.environ.get('NV_API_KEY', '')
if not api_key:
    raise SystemExit('缺少环境变量 NV_API_KEY')
model = 'nvidia/nemotron-3.5-super-vl-120b-a12b'

payload = {
    'model': model,
    'messages': [
        {'role': 'system', 'content': (
            'You are a software UI analyzer. Analyze the screenshot of a desktop application. '
            'Return ONLY a single JSON object with these exact keys (no markdown, no explanation):\n'
            '{\n'
            '  "software": "name of the application",\n'
            '  "window_title": "window title",\n'
            '  "elements": [\n'
            '    {"name": "button label/icon meaning", "control_type": "Button|Edit|Text|Menu|TreeItem|Document|Tab|Dialog", "x": 0, "y": 0, "width": 0, "height": 0, "confidence": 1.0}\n'
            '  ],\n'
            '  "current_state": "brief description of what the UI is showing",\n'
            '  "confidence": 0.95\n'
            '}\n'
            'Coordinates are in pixels relative to image top-left. '
            'Only list interactive controls (buttons, inputs, menus, tabs), ignore decorative elements.'
        )},
        {'role': 'user', 'content': [
            {'type': 'text', 'text': 'Analyze this screenshot of a software UI and return the JSON.'},
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
        ]},
    ],
    'max_tokens': 2048,
    'temperature': 0.1,
}
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}

print(f'\n🚀 POST https://integrate.api.nvidia.com/v1/chat/completions')
print(f'   model = {model}')
print(f'   image = {len(b64)//1024} KB base64')
print('   (120B 模型推理可能 30-60 秒，请耐心等...)')
print()

r = httpx.post('https://integrate.api.nvidia.com/v1/chat/completions',
               json=payload, headers=headers, timeout=90.0)
print(f'HTTP {r.status_code}  ({len(r.content)//1024} KB resp)')
if r.status_code != 200:
    print(r.text[:500])
    raise SystemExit(1)

raw = r.json()['choices'][0]['message']['content']
print()
print('=== 模型原始回复 ===')
print(raw[:800])
print()

# 清洗 + 解析
cleaned = raw.strip()
if cleaned.startswith('```'):
    cleaned = cleaned.strip('`')
    if cleaned.startswith('json'):
        cleaned = cleaned[4:].strip()
obj = json.loads(cleaned)

print('=== 结构化解析结果 ===')
print(f'  software        : {obj.get("software")}')
print(f'  window_title    : {obj.get("window_title")}')
print(f'  current_state   : {obj.get("current_state")}')
print(f'  confidence      : {obj.get("confidence")}')
print(f'  elements count  : {len(obj.get("elements", []))}')
print()
print('  识别到的控件:')
for el in obj.get('elements', [])[:12]:
    print(f'    · {el.get("control_type","?"):12s} ({el.get("x",0):4d},{el.get("y",0):4d})-({el.get("width",0):3d}x{el.get("height",0):3d}) conf={el.get("confidence",0):.2f}  "{el.get("name","")}"')

# 保存结果
result_path = Path(__file__).resolve().parent.parent / 'docs' / 'visual_result.json'
result_path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'\n✅ 完整结果已保存: {result_path}')
