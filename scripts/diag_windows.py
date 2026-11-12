"""诊断：列出当前所有可见顶层窗口（面积/标题/进程），用于确定主窗口筛选规则"""
import os
import win32gui
import win32process
import win32api

my_pid = os.getpid()
rows = []


def cb(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd):
        return
    title = win32gui.GetWindowText(hwnd)
    if not title:
        return
    cls = win32gui.GetClassName(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
    except Exception:
        return
    w, h = r - l, b - t
    exe = ""
    try:
        ph = win32api.OpenProcess(0x1000, False, pid)
        try:
            exe = win32process.GetModuleFileNameEx(ph, 0).split("\\")[-1]
        finally:
            win32api.CloseHandle(ph)
    except Exception:
        pass
    rows.append((w * h, w, h, title[:40], cls[:22], exe, pid == my_pid))


win32gui.EnumWindows(cb, None)
rows.sort(reverse=True)
print(f"{'面积':>10} {'尺寸':>12} {'进程':<22} {'自身':<4} 标题 / 类名")
for area, w, h, title, cls, exe, own in rows[:15]:
    print(f"{area:>10} {w:>5}x{h:<6} {exe:<22} {str(own):<4} {title} [{cls}]")
