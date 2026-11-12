"""并发验证：视觉请求进行中，/health 是否仍能正常响应（验证事件循环未被阻塞）"""
import io, threading, time
import httpx
import mss
from PIL import Image

BASE = "http://localhost:8000"

# 准备真实截图
with mss.mss() as sct:
    shot = sct.grab(sct.monitors[0])
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
buf = io.BytesIO()
img.save(buf, "PNG")
png = buf.getvalue()
print(f"📸 真实截图 {img.width}x{img.height}, {len(png)//1024} KB")
print()

vision_result = {}

def do_vision():
    t0 = time.time()
    try:
        r = httpx.post(
            f"{BASE}/api/v1/ai/analyze-screen",
            files={"file": ("s.png", png, "image/png")},
            data={"software_hint": "桌面"},
            timeout=300.0,
        )
        vision_result["status"] = r.status_code
        vision_result["elapsed"] = time.time() - t0
        j = r.json()
        vision_result["elements"] = len(j.get("analysis", {}).get("elements", [])) if j.get("analysis") else 0
    except Exception as e:
        vision_result["error"] = str(e)
        vision_result["elapsed"] = time.time() - t0

th = threading.Thread(target=do_vision, daemon=True)
print("🚀 启动视觉请求（后台线程，预计 30-60s）")
th.start()
time.sleep(1)  # 确保请求已发出

print("⏱️  视觉请求进行中，并发探测 /health：")
health_ok = 0
health_fail = 0
start = time.time()
while th.is_alive() and time.time() - start < 280:
    t0 = time.time()
    try:
        r = httpx.get(f"{BASE}/health", timeout=5.0)
        dt = time.time() - t0
        if r.status_code == 200:
            health_ok += 1
            print(f"   ✅ health 200 ({dt*1000:.0f}ms)")
        else:
            health_fail += 1
            print(f"   ⚠️  health {r.status_code}")
    except Exception as e:
        health_fail += 1
        print(f"   ❌ health 超时/失败: {type(e).__name__}")
    time.sleep(2)

th.join(timeout=10)
print()
print("=" * 60)
print("📊 并发验证结果")
print("=" * 60)
print(f"   /health 成功: {health_ok} 次")
print(f"   /health 失败: {health_fail} 次")
if "error" in vision_result:
    print(f"   视觉请求   : ❌ {vision_result['error']} ({vision_result['elapsed']:.1f}s)")
else:
    print(f"   视觉请求   : ✅ HTTP {vision_result.get('status')} "
          f"({vision_result.get('elapsed',0):.1f}s, {vision_result.get('elements',0)} 个元素)")
print()
if health_fail == 0 and health_ok > 0:
    print("🌟 修复有效！视觉长请求期间 /health 始终畅通，事件循环未被阻塞。")
else:
    print("⚠️  仍有阻塞，需要进一步排查。")
