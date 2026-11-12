"""屏幕 / 窗口截图模块

抓取方式（按可靠性排序）：
1. capture_window()：Windows Graphics Capture 抓「指定窗口」内容 ——
   不受其他窗口遮挡，也不会把桌面助手的绿框拍进去（推荐）
2. capture_region()：mss 抓屏幕区域，兜底
3. capture_fullscreen()：全屏，无目标窗口时使用

坐标系：全部为屏幕物理像素，原点为（虚拟）桌面左上角。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from core.uia import WindowInfo, foreground_window, frame_bounds, list_windows


@dataclass
class ScreenCapture:
    """一次截图的结果"""
    image: Optional[Image.Image]
    width: int
    height: int
    window_title: str
    process_name: str
    timestamp: float
    left: int = 0
    top: int = 0
    hwnd: int = 0
    exact: bool = False        # True = 窗口级抓取（坐标可精确对应控件）


class ScreenCapturer:
    """屏幕 / 窗口截图器"""

    def __init__(self):
        self._last: Optional[ScreenCapture] = None

    # ---------- 指定窗口 ----------
    def capture_window(self, win: WindowInfo) -> ScreenCapture:
        """抓取单个窗口内容；WGC 失败时退回屏幕区域抓取"""
        left, top, width, height = frame_bounds(win.hwnd)

        img = _wgc_capture(win.hwnd)
        exact = img is not None
        if img is None:
            img = self.capture_region(left, top, width, height)
        if img is None:
            return self.capture_fullscreen()

        cap = ScreenCapture(
            image=img, width=img.width, height=img.height,
            window_title=win.title, process_name=win.exe or "unknown",
            timestamp=time.time(), left=left, top=top, hwnd=win.hwnd,
            exact=exact,
        )
        self._last = cap
        return cap

    # ---------- 屏幕区域 ----------
    def capture_region(self, left: int, top: int, width: int, height: int) -> Optional[Image.Image]:
        if width <= 0 or height <= 0:
            return None
        try:
            import mss
            with mss.mss() as sct:
                shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception:
            return None

    # ---------- 全屏 ----------
    def capture_fullscreen(self) -> ScreenCapture:
        """全屏截图；失败时 image 为 None（不伪造图片）"""
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                capture = ScreenCapture(
                    image=img,
                    width=img.width,
                    height=img.height,
                    window_title="",
                    process_name="unknown",
                    timestamp=time.time(),
                    left=monitor["left"], top=monitor["top"],
                )
        except Exception:
            # 截图失败时不伪造图片，交给调用方提示真实错误
            capture = ScreenCapture(
                image=None,
                width=0,
                height=0,
                window_title="",
                process_name="unknown",
                timestamp=time.time(),
            )
        self._last = capture
        return capture

    def save(self, path: str) -> Optional[str]:
        if self._last and self._last.image:
            self._last.image.save(path)
            return path
        return None


def pick_target_window(preferred_hwnd: int | None = None) -> Optional[WindowInfo]:
    """确定「要指导的窗口」：用户选定 > 当前前台 > 面积最大的可见窗口"""
    windows = list_windows()
    if preferred_hwnd:
        for w in windows:
            if w.hwnd == preferred_hwnd:
                return w
    fg = foreground_window()
    if fg:
        return fg
    return windows[0] if windows else None


def _wgc_capture(hwnd: int, timeout: float = 4.0) -> Optional[Image.Image]:
    """Windows Graphics Capture：按窗口抓取，不受遮挡影响"""
    try:
        from windows_capture import WindowsCapture
    except ImportError:
        return None

    frames: list = []
    done = threading.Event()

    def run():
        try:
            capture = WindowsCapture(
                window_hwnd=hwnd, cursor_capture=False, draw_border=False
            )

            @capture.event
            def on_frame_arrived(frame, capture_control):
                try:
                    frames.append((frame.frame_buffer.copy(), frame.width, frame.height))
                finally:
                    capture_control.stop()
                    done.set()

            @capture.event
            def on_closed():
                done.set()

            capture.start()
        except Exception:
            pass
        finally:
            done.set()

    threading.Thread(target=run, daemon=True).start()
    done.wait(timeout)
    if not frames:
        return None

    try:
        import numpy as np

        buf, _w, _h = frames[0]
        arr = np.ascontiguousarray(buf)
        if arr.ndim == 3 and arr.shape[2] == 4:
            return Image.fromarray(arr[:, :, [2, 1, 0]])  # BGRA → RGB
        return Image.fromarray(arr)
    except Exception:
        return None


# ---------- 兼容旧调用 ----------
def _pick_main_window() -> tuple[str, str]:
    win = pick_target_window()
    if not win:
        return "", ""
    return win.title, win.exe
