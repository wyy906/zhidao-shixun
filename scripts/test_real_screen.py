"""真实屏幕截图 → /analyze-screen 视觉理解验证

用 mss 抓取当前真实屏幕，POST 到后端 /api/v1/ai/analyze-screen，
验证 NVIDIA 视觉模型能识别真实桌面上的 UI 元素。
"""
import io, sys, time
import httpx
import mss
from PIL import Image

print("=" * 66)
print("🖥️  真实屏幕截图 → NVIDIA 视觉理解 验证")
print("=" * 66)
print()

# 1. 真实截图
print("📸 Step 1: mss 抓取当前屏幕")
with mss.mss() as sct:
    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
    shot = sct.grab(monitor)
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
print(f"   屏幕分辨率: {img.width} x {img.height}")

buf = io.BytesIO()
img.save(buf, "PNG")
png_bytes = buf.getvalue()
print(f"   PNG 大小: {len(png_bytes)//1024} KB")
print()

# 2. 上传到后端视觉接口
print("🤖 Step 2: POST /api/v1/ai/analyze-screen")
print("   (后端会压缩图片到长边 1280px，再送 NVIDIA 120B)")
print()
t0 = time.time()
r = httpx.post(
    "http://localhost:8000/api/v1/ai/analyze-screen",
    files={"file": ("screen.png", png_bytes, "image/png")},
    data={
        "software_hint": "Windows 桌面 / 当前活动窗口",
        "current_step": "1",
        "current_step_title": "识别屏幕可操作元素",
    },
    timeout=300.0,
)
dt = time.time() - t0
print(f"   HTTP {r.status_code} | 耗时 {dt:.1f}s")
print()

if r.status_code != 200:
    print("❌ 请求失败:", r.text[:400])
    sys.exit(1)

result = r.json()
if not result.get("available"):
    print("⚠️  视觉 API 不可用:", result.get("reason"))
    sys.exit(1)

a = result.get("analysis")
if not a:
    print("❌ 视觉模型返回为空:", result.get("message"))
    sys.exit(1)

print("=" * 66)
print("✅ NVIDIA 视觉模型成功识别真实屏幕！")
print("=" * 66)
print(f"  检测软件    : {a['software']}")
print(f"  窗口标题    : {a['window_title']}")
print(f"  界面状态    : {a['current_state'][:90]}")
print(f"  整体置信度  : {a['confidence']}")
print(f"  识别控件数  : {len(a['elements'])}")
print()
print("  识别到的 UI 元素:")
for i, el in enumerate(a["elements"][:12]):
    print(f"    [{i:2d}] {el['name'][:34]:34s} "
          f"[{el['control_type']:10s}] "
          f"({el['x']:4d},{el['y']:4d}) {el['width']:4d}x{el['height']:<4d} "
          f"conf={el['confidence']}")
print()
print(f"⏱️  真实链路耗时: {dt:.1f}s（含截图上传 + 图片压缩 + 120B 推理）")
