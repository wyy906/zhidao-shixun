"""测试 /api/v1/ai/analyze-screen 端点（multipart/form-data 上传截图）"""
import sys, io, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

import httpx
from PIL import Image, ImageDraw

# 生成假图
W, H = 1440, 900
img = Image.new('RGB', (W, H), (245, 247, 251))
d = ImageDraw.Draw(img)
d.rectangle([20, 100, 260, 720], fill=(255, 255, 255), outline=(220, 220, 220))
d.text((30, 115), 'Schemas', fill=(31, 41, 55))
d.text((30, 145), '▾ student_db', fill=(31, 41, 55))
d.rectangle([140, 115, 250, 145], fill=(34, 197, 94))
d.text((150, 122), 'Create Schema', fill=(255, 255, 255))
d.rectangle([290, 180, 1400, 680], fill=(30, 30, 30), outline=(60, 60, 60))
d.text((20, 20), 'MySQL Workbench - student_db', fill=(31, 41, 55))
buf = io.BytesIO()
img.save(buf, 'PNG')

files = {'file': ('test.png', buf.getvalue(), 'image/png')}
data = {
    'software_hint': 'MySQL Workbench',
    'current_step': '1',
    'current_step_title': '创建数据库',
}

print('🚀 POST /api/v1/ai/analyze-screen (multipart/form-data)')
print('   后端链路: 上传截图 → NVIDIA 120B 视觉 → 返回结构化界面')
print()
r = httpx.post(
    'http://localhost:8000/api/v1/ai/analyze-screen',
    files=files, data=data, timeout=120.0,
)
print(f'HTTP {r.status_code}')
result = r.json()
print()
print(f'available: {result["available"]}')
if result.get('analysis'):
    a = result['analysis']
    print(f'software: {a["software"]}')
    print(f'window_title: {a["window_title"]}')
    print(f'current_state: {a["current_state"][:100]}')
    print(f'elements: {len(a["elements"])}')
    print()
    for i, el in enumerate(a['elements']):
        print(f'  [{i}] {el["name"]!r:30s} [{el["control_type"]:12s}] '
              f'({el["x"]},{el["y"]}) {el["width"]}x{el["height"]} conf={el["confidence"]}')
else:
    print(json.dumps(result, indent=2, ensure_ascii=False)[:800])
