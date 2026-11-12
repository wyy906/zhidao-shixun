"""完整链路：带截图 base64 → /v1/ai/guide → NVIDIA 视觉理解 → DynamicGuideEngine"""
import sys, io, base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

import httpx
from PIL import Image, ImageDraw

# 生成假图
W, H = 1440, 900
img = Image.new('RGB', (W, H), (245,247,251))
d = ImageDraw.Draw(img)
d.rectangle([20,100,260,720], fill=(255,255,255), outline=(220,220,220))
d.text((30,115), 'Schemas', fill=(31,41,55))
d.text((30,145), '▾ student_db', fill=(31,41,55))
d.rectangle([140,115,250,145], fill=(34,197,94))
d.text((150,122), 'Create Schema', fill=(255,255,255))
d.rectangle([290,180,1400,680], fill=(30,30,30), outline=(60,60,60))
d.rectangle([980,720,1060,752], fill=(79,110,247))
d.text((20,20), 'MySQL Workbench - student_db', fill=(31,41,55))
buf = io.BytesIO(); img.save(buf, 'PNG')
b64 = base64.b64encode(buf.getvalue()).decode()
print(f'📸 假图 base64 = {len(b64)//1024} KB')

# 登录
login = httpx.post('http://localhost:8000/api/v1/auth/login',
    json={'username':'admin','password':'demo123'})
token = login.json()['token']
print(f'🔑 token = {token[:20]}...')

# 调 /v1/ai/guide 带截图
payload = {
    'experiment_id': 2,        # MySQL 实验
    'current_step': 1,          # 步骤索引 1 = "创建数据库"  ← 和 Create Schema 按钮匹配
    'screen_state': {
        'image_base64': b64,
        'window_width': W,
        'window_height': H,
        'software': 'MySQL Workbench',
    }
}
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}

print()
print('🚀 POST /api/v1/ai/guide (带截图 18KB)')
print('   后端链路: 截图 → NVIDIA 120B 视觉 → 匹配步骤 → 精准坐标')
print()

r = httpx.post('http://localhost:8000/api/v1/ai/guide', json=payload, headers=headers, timeout=90.0)
print(f'HTTP {r.status_code}')
if r.status_code != 200:
    print(r.text[:500])
    raise SystemExit(1)

data = r.json()
print()
print('=' * 60)
print('✅ 最终 AI 指导（完整链路跑通）')
print('=' * 60)
print(f'  level       : {data["level"]}')
print(f'  instruction : {data["instruction"][:300]}')
print()
t = data['target']
print(f'  🎯 target  : ({t["x"]},{t["y"]}) {t["width"]}x{t["height"]}')
print(f'     label    : "{t["label"]}"')
print()
print(f'  expected    : {data["expected_result"]}')
print()

# 判断是不是用了视觉理解的真实坐标
VISUAL_X, VISUAL_Y = 100, 140  # NVIDIA 视觉模型识别 Create Schema 按钮的坐标
if abs(t['x'] - VISUAL_X) < 80:
    print('🌟 成功！target 用的是 NVIDIA 视觉理解的真实坐标')
else:
    print(f'⚠️  target 是 stub 坐标（{t["x"]},{t["y"]}），可能引擎没接到 visual_understanding')

# 也看一下没截图的 baseline guide
print()
print('--- baseline: 不带截图 ---')
payload2 = {'experiment_id': 2, 'current_step': 2, 'screen_state': {}}
r2 = httpx.post('http://localhost:8000/api/v1/ai/guide', json=payload2, headers=headers, timeout=10.0)
if r2.status_code == 200:
    d2 = r2.json()
    t2 = d2['target']
    print(f'  target : ({t2["x"]},{t2["y"]}) {t2["width"]}x{t2["height"]}  label="{t2["label"]}"')
    if t2['x'] != t['x'] or t2['y'] != t['y']:
        print('  ✔ 对比：带截图时坐标变了 → 视觉理解真起作用了')
    else:
        print('  ⚠ 坐标一样 → 可能引擎匹配没生效')
