"""验证 /screen-guide：识别真实桌面软件 → 匹配教程 → 教程步骤目标坐标"""
import io, time
import httpx
import mss
from PIL import Image

with mss.mss() as sct:
    shot = sct.grab(sct.monitors[0])
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
# 压缩到长边 1280（与桌面助手一致）
if max(img.size) > 1280:
    r = 1280 / max(img.size)
    img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
buf = io.BytesIO()
img.save(buf, "PNG")
png = buf.getvalue()
print(f"📸 截图 {img.width}x{img.height}  {len(png)//1024} KB\n")

t0 = time.time()
r = httpx.post(
    "http://localhost:8000/api/v1/ai/screen-guide",
    files={"file": ("s.png", png, "image/png")},
    data={"software_hint": "", "step_index": "0"},
    timeout=300.0,
)
dt = time.time() - t0
print(f"HTTP {r.status_code} | {dt:.1f}s\n")
j = r.json()
if not j.get("available"):
    print("视觉不可用:", j.get("reason")); raise SystemExit(1)

print(f"识别软件   : {j.get('software')}")
print(f"窗口标题   : {j.get('window_title')}")
print(f"界面状态   : {j.get('current_state')}")
print(f"识别控件数 : {len(j.get('elements') or [])}")
print()
tut = j.get("tutorial")
if tut:
    print(f"✅ 命中教程 : {tut['display_name']}（{len(tut['steps'])} 步）")
    print(f"   简介: {tut['intro']}")
    print(f"   当前步骤: {j.get('step_index')} / {len(tut['steps'])-1}")
else:
    print("⚠️ 未命中教程，返回通用建议")
print()
print("--- 指导文字 ---")
print(j.get("instruction"))
print()
t = j.get("target")
if t:
    print(f"🎯 教程目标: 「{t.get('name')}」 @ ({t.get('x')},{t.get('y')}) "
          f"{t.get('width')}x{t.get('height')} [{t.get('control_type')}]")
else:
    print("🎯 无目标")
