"""Windows UI Automation 封装

为「屏幕指导」提供**精确**的窗口与控件坐标（屏幕物理像素），
避免仅靠视觉模型估计坐标带来的绿框偏移。

关键点：
- 枚举可见窗口（用于「目标窗口」选择），排除桌面助手自身与系统壳窗口
- 按 hwnd 抓取控件树，返回 name / control_type / 屏幕矩形
- 最小化窗口需先 restore，否则 UIA 只返回窗口框架、拿不到内容
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# 系统壳 / 输入法 / 显卡覆盖层等，不算「用户正在用的软件」
# 注意：不要排除 explorer.exe 与 ApplicationFrameHost.exe ——
# 文件资源管理器、系统设置（UWP）都由它们承载，用户需要在这些窗口里操作
SYSTEM_EXES = {
    "textinputhost.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "lockapp.exe", "useroobebroker.exe",
    "nvidia overlay.exe", "tabtip.exe",
}

SYSTEM_CLASSES = {"Progman", "Shell_TrayWnd", "WorkerW", "Button"}

# UIA ControlType 枚举值 → 可读类型（与教程 type_hint 对齐）
CONTROL_TYPES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
    50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator",
    50039: "SemanticZoom", 50040: "AppBar",
}


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    exe: str
    left: int
    top: int
    width: int
    height: int
    minimized: bool = False

    @property
    def process_name(self) -> str:
        return self.exe or "unknown"

    def display(self) -> str:
        name = self.title.strip() or self.exe or f"窗口 {self.hwnd}"
        if len(name) > 36:
            name = name[:35] + "…"
        tag = f"  ·  {self.exe}" if self.exe else ""
        return f"{name}{tag}"


# ==================== 窗口枚举 ====================

def _exe_of(pid: int) -> str:
    try:
        import win32api
        import win32process
        handle = win32api.OpenProcess(0x1000, False, pid)
        try:
            return win32process.GetModuleFileNameEx(handle, 0).split("\\")[-1]
        finally:
            win32api.CloseHandle(handle)
    except Exception:
        return ""


def _window_title(hwnd: int) -> str:
    """安全读取窗口标题

    直接调用 GetWindowText 会向其它进程同步发送 WM_GETTEXT；对方线程若正处于
    输入同步状态，可能抛 RPC_E_CANTCALLOUT_ININPUTSYNCCALL(0x8001010d) 把整个
    进程打崩。改用 SendMessageTimeoutW + SMTO_BLOCK|SMTO_ABORTIFHUNG，
    超时就放弃（返回空标题，该窗口不进入列表）。
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(512)
        result = ctypes.c_size_t(0)
        ok = user32.SendMessageTimeoutW(
            wintypes.HWND(hwnd), 0x000D, ctypes.c_size_t(512), buf,
            0x0002 | 0x0001, 120, ctypes.byref(result),   # ABORTIFHUNG | BLOCK
        )
        if ok:
            return buf.value
    except Exception:
        pass
    return ""


def list_windows(min_width: int = 200, min_height: int = 140) -> list[WindowInfo]:
    """列出用户可选的窗口（按面积从大到小），不含自身进程与系统窗口"""
    try:
        import win32gui
        import win32process

        my_pid = os.getpid()
        found: list[WindowInfo] = []

        # 只在 EnumWindows 回调里记录句柄：在回调中调用 GetWindowText 会向
        # 其它进程发同步消息，遇到对方正处在输入同步状态时会抛
        # RPC_E_CANTCALLOUT_ININPUTSYNCCALL(0x8001010d) 直接打崩进程。
        hwnds: list[int] = []
        win32gui.EnumWindows(lambda h, _l: hwnds.append(h), None)

        for hwnd in hwnds:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    continue
                title = _window_title(hwnd)
                cls = win32gui.GetClassName(hwnd) or ""
                if not title.strip() or cls in SYSTEM_CLASSES:
                    continue
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == my_pid:
                    continue
                exe = _exe_of(pid)
                if exe.lower() in SYSTEM_EXES:
                    continue
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                w, h = right - left, bottom - top
                if w < min_width or h < min_height:
                    continue
                found.append(WindowInfo(
                    hwnd=hwnd, title=title, exe=exe,
                    left=left, top=top, width=w, height=h,
                    minimized=bool(win32gui.IsIconic(hwnd)),
                ))
            except Exception:
                continue
        found.sort(key=lambda w: w.width * w.height, reverse=True)

        # UWP 应用会同时暴露宿主窗口和内容窗口（如「设置」两条），
        # 标题相同且区域基本重合时只保留大的那条
        result: list[WindowInfo] = []
        host = "applicationframehost.exe"
        for w in found:
            dup = False
            for k in result:
                if k.title != w.title:
                    continue
                # UWP：ApplicationFrameHost 是可见宿主，SystemSettings 等是内容窗口
                if (k.exe.lower() == host) != (w.exe.lower() == host):
                    dup = True
                    break
                if _overlap_ratio(k, w) > 0.8:
                    dup = True
                    break
            if not dup:
                result.append(w)
        return result
    except Exception:
        return []


def _overlap_ratio(a: "WindowInfo", b: "WindowInfo") -> float:
    """两个窗口矩形交集占较小者的比例"""
    left = max(a.left, b.left)
    top = max(a.top, b.top)
    right = min(a.left + a.width, b.left + b.width)
    bottom = min(a.top + a.height, b.top + b.height)
    if right <= left or bottom <= top:
        return 0.0
    inter = (right - left) * (bottom - top)
    smaller = min(a.width * a.height, b.width * b.height)
    return inter / smaller if smaller else 0.0


def foreground_window() -> Optional[WindowInfo]:
    """当前前台窗口；若前台是桌面助手自身或系统窗口，返回 None"""
    try:
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == os.getpid():
            return None
        exe = _exe_of(pid)
        if exe.lower() in SYSTEM_EXES:
            return None
        title = _window_title(hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left < 200 or bottom - top < 140:
            return None
        return WindowInfo(hwnd, title, exe, left, top, right - left, bottom - top,
                          bool(win32gui.IsIconic(hwnd)))
    except Exception:
        return None


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """返回 (left, top, width, height)，屏幕物理像素"""
    try:
        import win32gui
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return left, top, right - left, bottom - top
    except Exception:
        return 0, 0, 0, 0


def frame_bounds(hwnd: int) -> tuple[int, int, int, int]:
    """窗口真实可见边框 (left, top, width, height)

    GetWindowRect 包含不可见的缩放边框，而 WGC 抓图对应的是
    DWMWA_EXTENDED_FRAME_BOUNDS，两者相差数个像素 —— 用前者会整体偏移。
    """
    try:
        import ctypes
        from ctypes import wintypes

        class _RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        rect = _RECT()
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    return window_rect(hwnd)


def restore_and_focus(hwnd: int) -> bool:
    """把窗口从最小化恢复并置于前台，UIA 才能读到控件树"""
    try:
        import win32con
        import win32gui

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # 前台切换被系统拒绝时，用 BringWindowToTop 兜底
            win32gui.BringWindowToTop(hwnd)
        return True
    except Exception:
        return False


# ==================== UIA 控件抓取 ====================

_uia = None


def _get_uia():
    """惰性初始化 IUIAutomation（comtypes），失败返回 None"""
    global _uia
    if _uia is not None:
        return _uia or None
    try:
        import comtypes.client

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        _uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation
        )
        _uia._UIA = UIA  # type: ignore[attr-defined]
    except Exception:
        _uia = False
    return _uia or None


def collect_elements(hwnd: int, limit: int = 400) -> list[dict]:
    """抓取窗口内所有可命名控件的**屏幕坐标**

    返回 [{"name","control_type","x","y","width","height","confidence","source"}]
    UIA 不可用时返回空列表（调用方回退到视觉模型）。
    """
    uia = _get_uia()
    if not uia:
        return []
    try:
        root = uia.ElementFromHandle(hwnd)
        kids = root.FindAll(uia._UIA.TreeScope_Descendants, uia.CreateTrueCondition())
    except Exception:
        return []

    win_l, win_t, win_w, win_h = window_rect(hwnd)
    win_r, win_b = win_l + win_w, win_t + win_h

    out: list[dict] = []
    for i in range(kids.Length):
        if len(out) >= limit:
            break
        try:
            el = kids.GetElement(i)
            name = (el.CurrentName or "").strip()
            if not name:
                continue
            r = el.CurrentBoundingRectangle
            w, h = r.right - r.left, r.bottom - r.top
            if w < 3 or h < 3:
                continue
            # 只要落在窗口范围内的控件，避免弹出菜单/提示的越界坐标
            if r.right < win_l or r.left > win_r or r.bottom < win_t or r.top > win_b:
                continue
            ctype = CONTROL_TYPES.get(int(el.CurrentControlType), "Custom")
            # 容器类不参与「点这里」的定位
            if ctype in ("TitleBar", "Pane", "Window", "Group"):
                continue
            out.append({
                "name": name,
                "control_type": ctype,
                "x": int(r.left),
                "y": int(r.top),
                "width": int(w),
                "height": int(h),
                "confidence": 1.0,
                "source": "uia",
            })
        except Exception:
            continue
    return out
