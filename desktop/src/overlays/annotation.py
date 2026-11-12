"""屏幕悬浮标注层 —— 透明无边框窗口叠加在全屏之上

设计要点：
- WindowStaysOnTop + FramelessWindowHint + WA_TranslucentBackground
- 绘制绿色/蓝色边框 + 指向箭头 + 标签
- 接收主窗口的 guide_updated 信号更新标注
- 可以被用户临时隐藏
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QGuiApplication,
)
from PySide6.QtWidgets import QWidget


class GuideOverlay(QWidget):
    """全屏透明悬浮层 —— 绘制标注框和指导文字

    坐标约定：外部传入的一律是「屏幕物理像素」，这里统一换算成 Qt 逻辑像素
    （devicePixelRatio≠1 时屏幕坐标与逻辑坐标不一致，直接画会整体偏移）。

    必须鼠标穿透：否则这一层会挡住用户点击被框住的控件。
    """

    def __init__(self):
        super().__init__(None)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput   # 鼠标/键盘事件穿透到下层窗口
            | Qt.NoDropShadowWindowHint
        )

        # 目标区域（物理像素）
        self._target_rect: QRect | None = None
        self._target_label: str = ""
        # 指导文字
        self._guide_text: str = ""
        # 气泡外观（可关闭 / 调透明度 / 换位置，避免遮挡右上角内容）
        self._bubble_enabled = True
        self._bubble_opacity = 70
        self._bubble_corner = "bottom-right"
        # 计数器（用于闪烁动画）
        self._tick = 0

        # 铺满整个虚拟桌面（多显示器也能覆盖）
        screen = QGuiApplication.primaryScreen()
        self._virt_geo = screen.virtualGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.setGeometry(self._virt_geo)

        # 动画定时器
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(600)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

    # ============ 对外接口 ============
    def set_target(self, x: int, y: int, w: int, h: int, label: str = ""):
        """x/y/w/h 为屏幕物理像素"""
        dpr = self.devicePixelRatioF() or 1.0
        left = int(x / dpr) - self._virt_geo.left()
        top = int(y / dpr) - self._virt_geo.top()
        self._target_rect = QRect(left, top, max(int(w / dpr), 8), max(int(h / dpr), 8))
        self._target_label = label
        self.update()

    def set_guide_text(self, text: str):
        self._guide_text = text
        self.update()

    def set_bubble_enabled(self, enabled: bool):
        self._bubble_enabled = bool(enabled)
        self.update()

    def set_bubble_opacity(self, percent: int):
        self._bubble_opacity = max(20, min(int(percent), 100))
        self.update()

    def set_bubble_corner(self, corner: str):
        self._bubble_corner = corner or "top-right"
        self.update()

    def clear_target(self):
        """只清掉目标框，保留指导文字"""
        self._target_rect = None
        self.update()

    def clear(self):
        self._target_rect = None
        self._guide_text = ""
        self.update()

    # ============ 动画 ============
    def _on_anim_tick(self):
        self._tick += 1
        self.update()

    # ============ 绘制 ============
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 半透明暗色遮罩（可选，让非目标区域稍微暗一点）
        # painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

        # 1) 绘制目标矩形
        if self._target_rect:
            self._draw_target(painter, self._target_rect, self._target_label)

        # 2) 绘制指导文字气泡
        if self._guide_text:
            self._draw_guide_bubble(painter)

    def _draw_target(self, painter: QPainter, rect: QRect, label: str):
        # 闪烁：交替显示实线和稍淡色
        alpha = 230 if self._tick % 2 == 0 else 160
        pen = QPen(QColor(34, 197, 94, alpha), 3)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(34, 197, 94, 40)))
        painter.drawRoundedRect(rect, 6, 6)

        # 四角 L 形标记
        corner_len = 18
        thick = 3
        pen = QPen(QColor(34, 197, 94), thick)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        # 左上
        painter.drawLine(rect.topLeft().x(), rect.topLeft().y(), rect.topLeft().x() + corner_len, rect.topLeft().y())
        painter.drawLine(rect.topLeft().x(), rect.topLeft().y(), rect.topLeft().x(), rect.topLeft().y() + corner_len)
        # 右上
        painter.drawLine(rect.topRight().x(), rect.topRight().y(), rect.topRight().x() - corner_len, rect.topRight().y())
        painter.drawLine(rect.topRight().x(), rect.topRight().y(), rect.topRight().x(), rect.topRight().y() + corner_len)
        # 左下
        painter.drawLine(rect.bottomLeft().x(), rect.bottomLeft().y(), rect.bottomLeft().x() + corner_len, rect.bottomLeft().y())
        painter.drawLine(rect.bottomLeft().x(), rect.bottomLeft().y(), rect.bottomLeft().x(), rect.bottomLeft().y() - corner_len)
        # 右下
        painter.drawLine(rect.bottomRight().x(), rect.bottomRight().y(), rect.bottomRight().x() - corner_len, rect.bottomRight().y())
        painter.drawLine(rect.bottomRight().x(), rect.bottomRight().y(), rect.bottomRight().x(), rect.bottomRight().y() - corner_len)

        # 标签（默认放在矩形上方，贴近屏幕边缘时自动移到下方/内侧）
        if label:
            painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            label_rect = QRect(rect.left(), rect.top() - 28, max(120, len(label) * 8 + 20), 24)
            if label_rect.top() < 0:
                label_rect.moveTop(rect.bottom() + 4)
            if label_rect.right() > self.width():
                label_rect.moveRight(self.width() - 4)
            if label_rect.left() < 0:
                label_rect.moveLeft(0)
            if label_rect.bottom() > self.height():
                label_rect.moveBottom(rect.top() - 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(34, 197, 94)))
            painter.drawRoundedRect(label_rect, 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(label_rect, Qt.AlignCenter, label)

    def _draw_guide_bubble(self, painter: QPainter):
        """绘制指导文字气泡

        - 可整体关闭（不遮挡屏幕）
        - 透明度可调
        - 位置可选四角；若与目标框重叠会自动换到不遮挡的一角
        """
        if not self._bubble_enabled or not self._guide_text.strip():
            return

        margin = 16
        max_w = 320
        padding = 12
        font = QFont("Microsoft YaHei", 10)
        painter.setFont(font)

        text_w = max_w - padding * 2
        br = painter.boundingRect(
            QRect(0, 0, text_w, 4000), Qt.TextWordWrap, self._guide_text
        )
        w = max_w
        h = br.height() + padding * 2 + 6

        corners = {
            "top-right": QRect(self.width() - w - margin, margin, w, h),
            "bottom-right": QRect(self.width() - w - margin, self.height() - h - margin, w, h),
            "top-left": QRect(margin, margin, w, h),
            "bottom-left": QRect(margin, self.height() - h - margin, w, h),
        }
        order = [self._bubble_corner] + [c for c in corners if c != self._bubble_corner]
        if self._bubble_corner not in corners:
            order = list(corners)

        bubble = corners[order[0]]
        if self._target_rect:
            avoid = self._target_rect.adjusted(-12, -12, 12, 12)
            for name in order:
                if not corners[name].intersects(avoid):
                    bubble = corners[name]
                    break

        alpha = int(255 * self._bubble_opacity / 100)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(31, 41, 55, alpha)))
        painter.drawRoundedRect(bubble, 10, 10)

        # 顶部色条
        top_bar = QRect(bubble.left(), bubble.top(), bubble.width(), 3)
        painter.setBrush(QBrush(QColor(79, 110, 247, alpha)))
        painter.drawRoundedRect(top_bar, 2, 2)

        painter.setPen(QColor(255, 255, 255, 240))
        text_rect = bubble.adjusted(padding, padding + 6, -padding, -padding)
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignTop, self._guide_text)
