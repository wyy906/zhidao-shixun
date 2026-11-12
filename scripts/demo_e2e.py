"""🎯 桌面助手 → 后端 → NVIDIA 视觉 → 精准坐标 完整端到端演示

模拟桌面助手 _refresh_once() 的完整链路：
  1. ScreenCapturer 截图（Stub 版返回 MySQL Workbench 假图）
  2. PIL Image → base64 PNG
  3. 自动登录获取 JWT
  4. POST /api/v1/ai/guide {image_base64: ...}
  5. 后端 → NVIDIA 120B 视觉理解 → 识别 Create Schema Button
  6. DynamicGuideEngine 匹配步骤 → 返回精准坐标
  7. 悬浮层应该画绿框的位置
"""
import sys, io, base64, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

import httpx
from PIL import Image, ImageDraw

print("=" * 70)
print("🎓 智导实训 · AI 视觉指导端到端演示")
print("=" * 70)
print()

# ──────────────────────────────────────────────────────────────
# Step 1: 模拟 ScreenCapturer 截图（Stub 版返回 MySQL Workbench 假图）
# ──────────────────────────────────────────────────────────────
print("📸 Step 1: 模拟桌面助手截图（MySQL Workbench 界面）")
print("─" * 50)

W, H = 1440, 900
img = Image.new('RGB', (W, H), (245, 247, 251))
d = ImageDraw.Draw(img)
# 左侧 Schemas 面板
d.rectangle([20, 100, 260, 720], fill=(255, 255, 255), outline=(220, 220, 220))
d.text((30, 115), 'Schemas', fill=(31, 41, 55))
d.text((30, 145), '▾ student_db', fill=(31, 41, 55))
# 绿色 Create Schema 按钮 ← NVIDIA 需要识别这个
d.rectangle([140, 115, 250, 145], fill=(34, 197, 94))
d.text((150, 122), 'Create Schema', fill=(255, 255, 255))
# 中央黑色 SQL 编辑器
d.rectangle([290, 180, 1400, 680], fill=(30, 30, 30), outline=(60, 60, 60))
# 底部 Apply 按钮
d.rectangle([980, 720, 1060, 752], fill=(79, 110, 247))
# 窗口标题
d.text((20, 20), 'MySQL Workbench - student_db', fill=(31, 41, 55))
# 左侧 apply box
buf = io.BytesIO()
img.save(buf, 'PNG')
image_bytes = buf.getvalue()
image_b64 = base64.b64encode(image_bytes).decode()
print(f"   截图尺寸: {W}x{H}")
print(f"   PNG 大小: {len(image_bytes)//1024} KB")
print(f"   base64  : {len(image_b64)//1024} KB")
print()

# ──────────────────────────────────────────────────────────────
# Step 2: 自动登录获取 JWT token（桌面助手启动时自动做的事）
# ──────────────────────────────────────────────────────────────
print("🔑 Step 2: 自动登录后端 (POST /v1/auth/login)")
print("─" * 50)
r = httpx.post('http://localhost:8000/api/v1/auth/login',
               json={'username': 'admin', 'password': 'demo123'}, timeout=5)
assert r.status_code == 200, f"登录失败 {r.status_code}"
token = r.json()['token']
print(f"   ✅ 登录成功！")
print(f"   token: {token[:30]}...")
print()

# ──────────────────────────────────────────────────────────────
# Step 3: 请求 AI 指导（带截图 → 触发 NVIDIA 视觉理解）
# ──────────────────────────────────────────────────────────────
print("🤖 Step 3: 请求 AI 指导（带截图 → NVIDIA 视觉理解 → 精准坐标）")
print("─" * 50)
print("   后端链路: 截图 base64 → NVIDIA nemotron-3.5-super-vl-120B")
print("            → 视觉识别 UI 元素 → DynamicGuideEngine 匹配步骤")
print("            → 返回真实屏幕坐标")
print()

payload = {
    "experiment_id": 2,          # MySQL 实训实验
    "current_step": 1,            # 步骤索引 1 = "创建数据库"
    "screen_state": {
        "window_width": W,
        "window_height": H,
        "active_window": "MySQL Workbench - student_db",
        "process": "MySQLWorkbench.exe",
        "image_base64": image_b64,  # ← 关键！触发视觉理解
    },
}
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

t0 = time.time()
r = httpx.post('http://localhost:8000/api/v1/ai/guide',
               json=payload, headers=headers, timeout=180.0)
dt = time.time() - t0

print(f"   HTTP {r.status_code} | 耗时 {dt:.1f}s")
assert r.status_code == 200, f"请求失败: {r.text[:300]}"
print()

# ──────────────────────────────────────────────────────────────
# Step 4: 展示结果 + 验证悬浮层应该画在哪
# ──────────────────────────────────────────────────────────────
data = r.json()
t = data['target']
instruction = data['instruction']

print("=" * 70)
print("✅ 完整端到端闭环跑通！")
print("=" * 70)
print()
print("📝 AI 指导内容（悬浮气泡右上显示）:")
print("  ┌" + "─" * 60 + "┐")
for line in instruction.split("\n")[:6]:
    print(f"  │ {line[:58]:60s}│")
print("  └" + "─" * 60 + "┘")
print()

print("🎯 目标坐标（悬浮层应该画绿框的位置）:")
print(f"   label  : \"{t['label']}\"")
print(f"   x, y   : ({t['x']}, {t['y']})")
print(f"   size   : {t['width']} x {t['height']}")
print()

# 可视化验证：假图里 Create Schema 按钮在 (140,115)-(250,145)
# NVIDIA 应该识别到类似位置
REAL_BTN = {"x": 140, "y": 115, "w": 110, "h": 30}
center_x_real = REAL_BTN['x'] + REAL_BTN['w']//2
center_y_real = REAL_BTN['y'] + REAL_BTN['h']//2
center_x_nv = t['x'] + t['width']//2
center_y_nv = t['y'] + t['height']//2
dist = ((center_x_real - center_x_nv)**2 + (center_y_real - center_y_nv)**2) ** 0.5

print("📍 精度验证:")
print(f"   假图 Create Schema 中心: ({center_x_real}, {center_y_real})")
print(f"   NVIDIA 返回 target 中心: ({center_x_nv}, {center_y_nv})")
print(f"   欧氏距离: {dist:.0f} px")
if dist < 60:
    print(f"   🌟 完美匹配！误差 < 60px")
elif dist < 100:
    print(f"   ✅ 良好匹配！误差 < 100px")
else:
    print(f"   ⚠️ 匹配偏差较大（视觉模型估计 vs 假图坐标）")

# 视觉匹配判断
is_stub = abs(t['x'] - 420) < 5 and abs(t['y'] - 280) < 5
if is_stub:
    print(f"   ❌ 返回的是 stub 坐标 (420,280)，视觉理解未触发")
else:
    print(f"   🎨 返回的是 NVIDIA 视觉理解的真实坐标！")

print()
print("🖱️  桌面助手悬浮层效果:")
print(f"   ┌{''.join(['─']*t['width']):{t['width']}}┐")
print(f"   │  {t['label'][:10]:10s}  │  ← 闪烁绿框 + 四角 L 标记")
print(f"   └{''.join(['─']*t['width']):{t['width']}}┘  @ ({t['x']},{t['y']})")
print()
print("🚀 真实使用场景：")
print("   PySide6 桌面助手启动 → 截图你的 MySQL Workbench 屏幕")
print("   → 自动传给 NVIDIA → 返回 Create Schema 按钮精准坐标")
print("   → 悬浮层全屏叠加 → 闪烁绿框 + 指导气泡")
