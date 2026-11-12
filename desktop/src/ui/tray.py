"""系统托盘"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QBrush
from PySide6.QtWidgets import QSystemTrayIcon, QMenu

from ui.main_window import MainWindow


class SystemTray(QObject):
    def __init__(self, window: MainWindow, parent=None):
        super().__init__(parent)
        self._window = window

        # 简单生成一个托盘图标
        pix = QPixmap(64, 64)
        pix.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#4f6ef7")))
        painter.setPen(QColor("#4f6ef7"))
        painter.drawRoundedRect(8, 8, 48, 48, 12, 12)
        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, "智")
        painter.end()

        self._tray = QSystemTrayIcon(QIcon(pix))
        self._tray.setToolTip("智导实训助手")

        menu = QMenu()
        act_show = QAction("显示主窗口", menu)
        act_show.triggered.connect(self._show_window)
        act_guide = QAction("暂停观察", menu)
        act_guide.triggered.connect(self._toggle_pause)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_guide)
        menu.addSeparator()
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def show(self):
        self._tray.show()

    def _show_window(self):
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def _toggle_pause(self):
        self._window._toggle_observing()

    def _quit(self):
        self._tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self._show_window()
