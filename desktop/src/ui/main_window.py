"""主窗口

显示：当前实验信息、当前识别的软件、AI 指导内容、屏幕标注开关、暂停/停止。
悬浮层是独立的透明窗口，不在主窗口内。
"""
from __future__ import annotations

import base64
import io
import threading
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QLineEdit, QTextEdit, QStatusBar, QMessageBox,
    QFormLayout, QDialog, QComboBox, QSlider,
)

from config.settings import DesktopSettings, save_settings
from core.screen import ScreenCapturer, pick_target_window
from core.uia import (
    WindowInfo, collect_elements, foreground_window, list_windows,
    restore_and_focus, window_rect,
)
from network.api_client import AIBackendClient
from overlays.annotation import GuideOverlay

# 绿框来源说明（UIA 是像素级精确坐标，视觉模型是估算）
SOURCE_TEXT = {
    "uia": "UIA 精确坐标",
    "vision": "视觉估计坐标",
    "heuristic": "估算位置",
}


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, settings: DesktopSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("智导实训助手 - 设置")
        self.setMinimumWidth(400)
        self._settings = settings

        form = QFormLayout()
        self.url_edit = QLineEdit(settings.backend_url)
        self.token_edit = QLineEdit(settings.token)
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.interval_edit = QLineEdit(str(settings.poll_interval_ms))

        form.addRow("后端 API 地址", self.url_edit)
        form.addRow("访问令牌", self.token_edit)
        form.addRow("轮询间隔 (ms)", self.interval_edit)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btn_row)

    def accept(self):
        try:
            int(self.interval_edit.text())
        except ValueError:
            QMessageBox.warning(self, "提示", "轮询间隔必须是整数")
            return
        self._settings.backend_url = self.url_edit.text().strip()
        self._settings.token = self.token_edit.text().strip()
        self._settings.poll_interval_ms = int(self.interval_edit.text())
        save_settings(self._settings)
        super().accept()


class MainWindow(QMainWindow):
    """桌面助手主窗口"""

    guide_updated = Signal(str, dict)  # 指导文字 + 目标坐标
    _request_done = Signal(dict)       # 后台请求完成 → 回到主线程更新 UI
    _experiments_loaded = Signal(list)  # 实验列表加载完成
    _experiment_ready = Signal(dict)    # 实验详情加载完成 → 进入实验模式
    _experiment_done = Signal(bool)     # 实验提交完成

    def __init__(self, settings: DesktopSettings):
        super().__init__()
        self._settings = settings
        self._capturer = ScreenCapturer()
        self._client = AIBackendClient(settings)

        self.setWindowTitle("智导实训助手")
        self.resize(600, 760)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self._build_ui()
        self._connect_timer()

        # 启动时自动登录后端（获取 JWT token）
        if not self._client.token:
            ok = self._client.auto_login()
            if ok:
                self.statusBar().showMessage("✅ 已自动登录后端")
            else:
                self.statusBar().showMessage("⚠️ 后端未连接，暂无识别结果")

        # 创建悬浮层（独立透明窗口，鼠标穿透）
        self._overlay = GuideOverlay()
        self._apply_bubble_settings()
        self.guide_updated.connect(self._on_guide_updated)

        # 后台请求完成 → 回到主线程更新 UI
        self._request_done.connect(self._apply_request_result)
        self._experiments_loaded.connect(self._on_experiments_loaded)
        self._experiment_ready.connect(self._on_experiment_ready)
        self._experiment_done.connect(self._on_experiment_done)

        # 防止并发请求
        self._requesting = False

        # 教程状态（翻页时本地切换，无需重新调视觉接口）
        self._tutorial: dict | None = None
        self._elements: list[dict] = []
        self._step_index = 0
        # 实验模式状态（老师导入的实验）
        self._experiment: dict | None = None
        self._exp_steps: list[dict] = []
        self._exp_step = 0
        self._last_window_items: list[tuple[int, str]] = []
        # 无法读取控件的窗口：自动视觉识别只尝试一次，之后由用户手动触发
        self._vision_tried: set[int] = set()
        # 用户最后使用过的外部窗口（自动模式下优先跟随它）
        self._last_external_hwnd: int | None = None

        # 启动时显示（如果开启了 overlay）
        if settings.overlay_enabled:
            self._overlay.show()

        # 初始化可选窗口列表
        self._refresh_window_list(force=True)

        # 登录成功后拉取老师导入的实验
        QTimer.singleShot(1200, self._load_experiments)

        # 启动 3 秒后立即触发一次分析，避免用户干等一个轮询周期
        QTimer.singleShot(3000, self._refresh_once)

    def _on_guide_updated(self, text: str, target: dict):
        """接收新指导 → 更新悬浮层"""
        if not self.chk_overlay.isChecked():
            return
        if not self.chk_annotation.isChecked() or target.get("x") is None:
            # 只显示文字，不标注（视觉未识别到明确目标时也如此，避免画错位置）
            self._overlay.clear()
            self._overlay.set_guide_text(text)
        else:
            self._overlay.set_target(
                target.get("x", 400),
                target.get("y", 300),
                target.get("width", 140),
                target.get("height", 44),
                target.get("label", ""),
            )
            self._overlay.set_guide_text(text)
        if not self._overlay.isVisible():
            self._overlay.show()

    # ================= UI =================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部 Logo
        logo_row = QHBoxLayout()
        logo = QLabel("🎓 智导实训")
        logo.setStyleSheet("font-size: 18px; font-weight: 700; color: #4f6ef7;")
        logo_row.addWidget(logo)
        logo_row.addStretch()
        btn_settings = QPushButton("⚙ 设置")
        btn_settings.clicked.connect(self._open_settings)
        logo_row.addWidget(btn_settings)
        layout.addLayout(logo_row)

        # 实验信息区
        exp_box = QGroupBox("当前模式")
        exp_layout = QVBoxLayout(exp_box)

        # 选择老师导入的实验（选中即进入实验模式，逐步指导）
        exp_row = QHBoxLayout()
        exp_row.setContentsMargins(0, 0, 0, 0)
        self.cmb_experiment = QComboBox()
        self.cmb_experiment.setMinimumWidth(230)
        self.cmb_experiment.setToolTip("选择导入的实验后，助手会按实验步骤逐步标注")
        self.cmb_experiment.addItem("（不使用实验，跟随窗口）", 0)
        self.cmb_experiment.currentIndexChanged.connect(self._on_experiment_changed)
        btn_exp = QPushButton("⟳")
        btn_exp.setFixedWidth(32)
        btn_exp.setToolTip("刷新实验列表")
        btn_exp.clicked.connect(self._load_experiments)
        exp_row.addWidget(self.cmb_experiment, 1)
        exp_row.addWidget(btn_exp)
        exp_layout.addLayout(exp_row)

        self.lbl_exp_title = QLabel("通用屏幕指导（识别真实桌面）")
        self.lbl_exp_title.setStyleSheet("font-weight: 600;")
        self.lbl_exp_step = QLabel("等待识别...")
        exp_layout.addWidget(self.lbl_exp_title)
        exp_layout.addWidget(self.lbl_exp_step)
        layout.addWidget(exp_box)

        # 识别状态区
        recog_box = QGroupBox("屏幕识别")
        recog_layout = QFormLayout(recog_box)

        # 目标窗口选择（同时打开多个软件时，明确要指导哪一个）
        win_row = QHBoxLayout()
        win_row.setContentsMargins(0, 0, 0, 0)
        self.cmb_window = QComboBox()
        self.cmb_window.setMinimumWidth(230)
        self.cmb_window.setToolTip("选择要指导的窗口；选「自动」则跟随当前前台窗口")
        self.cmb_window.currentIndexChanged.connect(self._on_target_window_changed)
        btn_windows = QPushButton("⟳")
        btn_windows.setFixedWidth(32)
        btn_windows.setToolTip("刷新窗口列表")
        btn_windows.clicked.connect(lambda: self._refresh_window_list(force=True))
        win_row.addWidget(self.cmb_window, 1)
        win_row.addWidget(btn_windows)
        recog_layout.addRow("目标窗口", win_row)

        self.lbl_software = QLabel("—")
        self.lbl_window = QLabel("—")
        self.lbl_elements = QLabel("0")
        recog_layout.addRow("当前软件", self.lbl_software)
        recog_layout.addRow("活动窗口", self.lbl_window)
        recog_layout.addRow("可识别控件", self.lbl_elements)
        layout.addWidget(recog_box)

        # AI 指导区（含教程翻页）
        ai_box = QGroupBox("AI 实时指导")
        ai_layout = QVBoxLayout(ai_box)

        tut_row = QHBoxLayout()
        self.btn_prev_step = QPushButton("◀ 上一步")
        self.btn_prev_step.clicked.connect(self._tutorial_prev)
        self.btn_next_step = QPushButton("下一步 ▶")
        self.btn_next_step.clicked.connect(self._tutorial_next)
        self.lbl_tut_name = QLabel("")
        self.lbl_tut_name.setStyleSheet("color: #4f6ef7; font-weight: 600;")
        self.btn_prev_step.setEnabled(False)
        self.btn_next_step.setEnabled(False)
        self.btn_copy_guide = QPushButton("📋 复制")
        self.btn_copy_guide.setToolTip("复制当前指导内容（也可以直接在文本框里选中后 Ctrl+C）")
        self.btn_copy_guide.clicked.connect(self._copy_guide)
        tut_row.addWidget(self.lbl_tut_name, 1)
        tut_row.addWidget(self.btn_copy_guide)
        tut_row.addWidget(self.btn_prev_step)
        tut_row.addWidget(self.btn_next_step)
        ai_layout.addLayout(tut_row)

        self.txt_guide = QTextEdit()
        self.txt_guide.setReadOnly(True)
        self.txt_guide.setMinimumHeight(260)
        self.txt_guide.setStyleSheet("font-size: 13px; line-height: 160%;")
        self.txt_guide.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.txt_guide.setPlaceholderText("AI 会识别当前桌面软件，并在这里给出对应教程...")
        ai_layout.addWidget(self.txt_guide)
        layout.addWidget(ai_box, 1)

        # 开关区
        toggle_row = QHBoxLayout()
        self.chk_overlay = QCheckBox("启用屏幕悬浮标注")
        self.chk_overlay.setChecked(self._settings.overlay_enabled)
        self.chk_overlay.stateChanged.connect(self._on_overlay_toggled)
        self.chk_annotation = QCheckBox("显示目标框")
        self.chk_annotation.setChecked(self._settings.annotation_enabled)
        self.chk_annotation.stateChanged.connect(self._on_annotation_toggled)
        toggle_row.addWidget(self.chk_overlay)
        toggle_row.addWidget(self.chk_annotation)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # 教程气泡：可关闭 / 调透明度 / 换位置（默认右上角容易挡住内容）
        bubble_row = QHBoxLayout()
        self.chk_bubble = QCheckBox("显示文字气泡")
        self.chk_bubble.setChecked(self._settings.bubble_enabled)
        self.chk_bubble.stateChanged.connect(self._on_bubble_toggled)
        self.cmb_corner = QComboBox()
        for label, key in (("右上", "top-right"), ("右下", "bottom-right"),
                           ("左上", "top-left"), ("左下", "bottom-left")):
            self.cmb_corner.addItem(label, key)
        idx = self.cmb_corner.findData(self._settings.bubble_corner)
        self.cmb_corner.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_corner.currentIndexChanged.connect(self._on_bubble_corner_changed)
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(30, 100)
        self.slider_opacity.setValue(self._settings.bubble_opacity)
        self.slider_opacity.setFixedWidth(80)
        self.slider_opacity.valueChanged.connect(self._on_bubble_opacity_changed)
        self.lbl_opacity = QLabel(f"{self._settings.bubble_opacity}%")
        self.lbl_opacity.setFixedWidth(34)
        bubble_row.addWidget(self.chk_bubble)
        bubble_row.addWidget(QLabel("位置"))
        bubble_row.addWidget(self.cmb_corner)
        bubble_row.addWidget(QLabel("透明度"))
        bubble_row.addWidget(self.slider_opacity)
        bubble_row.addWidget(self.lbl_opacity)
        bubble_row.addStretch()
        layout.addLayout(bubble_row)

        # 控制按钮
        ctrl_row = QHBoxLayout()
        self.btn_start = QPushButton("▶ 开始观察")
        self.btn_start.clicked.connect(self._toggle_observing)
        self.btn_refresh = QPushButton("🔄 立即刷新")
        self.btn_refresh.setToolTip("重新识别；必要时会调用视觉模型做深度识别")
        self.btn_refresh.clicked.connect(lambda: self._refresh_once(force_vision=True))
        ctrl_row.addWidget(self.btn_start)
        ctrl_row.addWidget(self.btn_refresh)
        layout.addLayout(ctrl_row)

        # 状态栏
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def _copy_guide(self):
        """复制当前 AI 指导内容到剪贴板（方便粘贴代码/命令）"""
        text = self.txt_guide.toPlainText()
        if not text.strip():
            self.statusBar().showMessage("暂无可复制的指导内容")
            return
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage("✅ 已复制当前指导内容")

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self)
        dlg.exec()

    # ================= 目标窗口 =================
    def _refresh_window_list(self, force: bool = False):
        """刷新可选窗口（列表没变化时不动，避免打断用户选择）"""
        windows = list_windows()
        items = [(w.hwnd, w.title) for w in windows]
        if not force and items == self._last_window_items:
            return
        self._last_window_items = items

        prev = self.cmb_window.currentData() if self.cmb_window.count() else None
        self.cmb_window.blockSignals(True)
        self.cmb_window.clear()
        self.cmb_window.addItem("自动（跟随前台窗口）", None)
        for w in windows:
            self.cmb_window.addItem(w.display(), w.hwnd)
            self.cmb_window.setItemData(
                self.cmb_window.count() - 1, f"{w.title}\n{w.exe}", Qt.ToolTipRole
            )
        idx = self.cmb_window.findData(prev) if prev is not None else 0
        self.cmb_window.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_window.blockSignals(False)

    def _selected_hwnd(self) -> int | None:
        data = self.cmb_window.currentData()
        try:
            return int(data) if data else None
        except (TypeError, ValueError):
            return None

    def _on_target_window_changed(self, _index: int):
        """用户切换目标窗口 → 恢复窗口（如已最小化）并重新识别"""
        self._tutorial = None
        self._step_index = 0
        self._elements = []
        hwnd = self._selected_hwnd()
        if hwnd:
            for w in list_windows():
                if w.hwnd == hwnd and w.minimized:
                    restore_and_focus(hwnd)
                    break
        self.statusBar().showMessage("已切换目标窗口，正在重新识别...")
        QTimer.singleShot(400, self._refresh_once)

    # ================= 实验模式（导入的实验） =================
    def _load_experiments(self, *_args):
        """从后端拉取老师导入的实验列表"""
        if self._experiment is not None:
            return

        def _run():
            self._experiments_loaded.emit(self._client.list_experiments())

        threading.Thread(target=_run, daemon=True).start()

    def _on_experiments_loaded(self, items: list):
        prev = self.cmb_experiment.currentData()
        self.cmb_experiment.blockSignals(True)
        self.cmb_experiment.clear()
        self.cmb_experiment.addItem("（不使用实验，跟随窗口）", 0)
        for e in items:
            self.cmb_experiment.addItem(
                f"{e.get('title', '未命名')}（{e.get('total_steps', 0)} 步）", e.get("id")
            )
        idx = self.cmb_experiment.findData(prev) if prev else 0
        self.cmb_experiment.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_experiment.blockSignals(False)
        if items:
            self.statusBar().showMessage(f"已加载 {len(items)} 个实验，可在下拉框中选择")
        else:
            self.statusBar().showMessage("后端还没有实验，请先在网页端导入")

    def _on_experiment_changed(self, _index: int):
        exp_id = self.cmb_experiment.currentData()
        if not exp_id:
            self._stop_experiment()
            return
        self.statusBar().showMessage("正在加载实验步骤...")

        def _run():
            data = self._client.get_experiment(int(exp_id))
            if data:
                self._client.start_experiment(int(exp_id))
            self._experiment_ready.emit(data or {})

        threading.Thread(target=_run, daemon=True).start()

    def _on_experiment_ready(self, data: dict):
        if not data:
            QMessageBox.warning(
                self, "提示",
                "实验加载失败，可能已被删除或重新导入。\n请点实验下拉框旁的 ⟳ 刷新后重试。",
            )
            self.cmb_experiment.setCurrentIndex(0)
            return
        steps = sorted(data.get("steps") or [], key=lambda s: s.get("order_index", 0))
        if not steps:
            QMessageBox.warning(
                self, "提示",
                "这个实验没有步骤。请先在网页端「实验管理」里导入带步骤的实验包。",
            )
            self.cmb_experiment.setCurrentIndex(0)
            return
        self._experiment = data
        self._exp_steps = steps
        self._exp_step = 0
        self._tutorial = None
        self.lbl_exp_title.setText(f"实验：{data.get('title', '')}")
        self.lbl_tut_name.setText("实验模式")
        self._render_experiment_step()
        self._refresh_once()

    def _stop_experiment(self):
        self._experiment = None
        self._exp_steps = []
        self._exp_step = 0
        self.lbl_exp_title.setText("通用屏幕指导（跟随窗口）")
        self.lbl_exp_step.setText("等待识别...")
        self.lbl_tut_name.setText("")
        self.btn_prev_step.setEnabled(False)
        self.btn_next_step.setEnabled(False)
        self.btn_next_step.setText("下一步 ▶")
        self._overlay.clear_target()

    @staticmethod
    def _adapter_app_name(adapter: dict) -> str:
        """目标软件名称（adapter 里可能是字符串或候选列表）"""
        for key in ("window_title", "target_app"):
            value = adapter.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, (list, tuple)) and value:
                return str(value[0])
        return ""

    def _resolve_step_window(self, adapter: dict) -> WindowInfo | None:
        """按步骤的 adapter 提示找到目标窗口（支持多个候选进程/标题）"""
        wins = list_windows()

        def _as_list(value) -> list[str]:
            if not value:
                return []
            if isinstance(value, str):
                return [value]
            return [str(v) for v in value if v]

        apps = [a.lower() for a in _as_list(adapter.get("target_app"))]
        titles = [t.lower() for t in _as_list(adapter.get("window_title"))]

        for app in apps:
            for w in wins:
                if app in w.exe.lower():
                    return w
        for kw in titles:
            for w in wins:
                if kw in w.title.lower():
                    return w
        if apps or titles:
            return None          # 指定了目标窗口但没打开 → 提示用户去打开
        return pick_target_window(self._last_external_hwnd)

    def _analyze_experiment_step(self, force_vision: bool = False):
        """按当前实验步骤定位窗口并匹配控件"""
        if not self._experiment or not self._exp_steps:
            return
        step = self._exp_steps[self._exp_step]
        adapter = step.get("adapter_hint") or {}
        app_name = self._adapter_app_name(adapter)

        win = self._resolve_step_window(adapter)
        if not win:
            self.statusBar().showMessage(f"等待打开「{app_name}」...")
            self._render_experiment_step(
                target_el=None, note=f"⚠️ 请先打开「{app_name}」窗口，助手会自动跟随并标注。"
            )
            return

        if win.minimized:
            restore_and_focus(win.hwnd)
            time.sleep(0.2)
            left, top, width, height = window_rect(win.hwnd)
            win.left, win.top, win.width, win.height = left, top, width, height
            win.minimized = False

        self.lbl_software.setText(win.exe or "—")
        self.lbl_window.setText(win.title or "—")

        elements = collect_elements(win.hwnd)
        self.lbl_elements.setText(f"{len(elements)}（UIA {len(elements)}）")
        self.statusBar().showMessage(
            f"实验第 {self._exp_step + 1}/{len(self._exp_steps)} 步 · 已锁定 {win.exe or win.title}"
        )

        match_step = {
            "keywords": adapter.get("keywords") or [],
            "type_hint": adapter.get("type_hint") or "",
        }
        target_el = self._match_step_target_local(elements, match_step)
        self._render_experiment_step(target_el=target_el)

    def _render_experiment_step(self, target_el: dict | None = None, note: str = ""):
        if not self._experiment or not self._exp_steps:
            return
        step = self._exp_steps[self._exp_step]
        adapter = step.get("adapter_hint") or {}
        total = len(self._exp_steps)
        app_name = self._adapter_app_name(adapter)

        lines = [
            f"🧪 {self._experiment.get('title', '')}",
            f"第 {self._exp_step + 1}/{total} 步：{step['title']}",
            step.get("instruction") or "",
        ]
        if step.get("expected_result"):
            lines += ["", f"期望结果：{step['expected_result']}"]
        errors = step.get("common_errors") or []
        if errors:
            lines += ["常见错误：" + "；".join(str(e) for e in errors)]
        if app_name:
            lines += ["", f"目标软件：{app_name}"]
        if note:
            lines += ["", note]

        self.txt_guide.setPlainText("\n".join(lines))
        self.lbl_exp_step.setText(f"第 {self._exp_step + 1}/{total} 步 · {step['title']}")
        self.lbl_tut_name.setText(
            f"{self._experiment.get('title', '')[:14]}  {self._exp_step + 1}/{total}"
        )
        self.btn_prev_step.setEnabled(self._exp_step > 0)
        self.btn_next_step.setEnabled(True)
        self.btn_next_step.setText(
            "提交实验 ✓" if self._exp_step == total - 1 else "完成本步 ▶"
        )

        target = (self._target_from_el(target_el, step.get("title", ""))
                  if target_el else
                  {"x": None, "y": None, "width": 0, "height": 0, "label": step.get("title", "")})
        bubble = (f"实验 {self._exp_step + 1}/{total}\n{step.get('title', '')}\n"
                  f"{(step.get('instruction') or '')[:70]}")
        self.guide_updated.emit(bubble, target)

    def _exp_step_next(self):
        exp_id = (self._experiment or {}).get("id")
        if not exp_id:
            return
        # 上报本步完成
        threading.Thread(
            target=self._client.report_step, args=(exp_id, self._exp_step), daemon=True
        ).start()

        if self._exp_step >= len(self._exp_steps) - 1:
            def _submit():
                ok = self._client.submit_experiment(exp_id)
                self._experiment_done.emit(bool(ok))
            threading.Thread(target=_submit, daemon=True).start()
            return

        self._exp_step += 1
        self._render_experiment_step()
        self._refresh_once()

    def _exp_step_prev(self):
        if self._exp_step > 0:
            self._exp_step -= 1
            self._render_experiment_step()
            self._refresh_once()

    def _on_experiment_done(self, ok: bool):
        QMessageBox.information(
            self, "实验完成",
            "实验已提交！" if ok else "已到最后一个步骤，但提交失败，请检查后端连接。",
        )
        self._stop_experiment()
        self.cmb_experiment.blockSignals(True)
        self.cmb_experiment.setCurrentIndex(0)
        self.cmb_experiment.blockSignals(False)

    def _on_overlay_toggled(self, state):
        self._settings.overlay_enabled = bool(state)
        if bool(state):
            self._overlay.show()
        else:
            self._overlay.hide()

    def _on_annotation_toggled(self, state):
        self._settings.annotation_enabled = bool(state)
        if not bool(state):
            self._overlay.clear_target()
        elif self._tutorial:
            self._render_tutorial()

    # ================= 文字气泡 =================
    def _apply_bubble_settings(self):
        self._overlay.set_bubble_enabled(self._settings.bubble_enabled)
        self._overlay.set_bubble_opacity(self._settings.bubble_opacity)
        self._overlay.set_bubble_corner(self._settings.bubble_corner)

    def _on_bubble_toggled(self, state):
        self._settings.bubble_enabled = bool(state)
        save_settings(self._settings)
        self._apply_bubble_settings()

    def _on_bubble_corner_changed(self, _index):
        self._settings.bubble_corner = self.cmb_corner.currentData() or "top-right"
        save_settings(self._settings)
        self._apply_bubble_settings()

    def _on_bubble_opacity_changed(self, value):
        self._settings.bubble_opacity = int(value)
        self.lbl_opacity.setText(f"{value}%")
        save_settings(self._settings)
        self._apply_bubble_settings()

    def _toggle_observing(self):
        if self._timer.isActive():
            self._timer.stop()
            self.btn_start.setText("▶ 开始观察")
            self.statusBar().showMessage("已暂停")
        else:
            self._timer.start()
            self.btn_start.setText("⏸ 暂停观察")
            self.statusBar().showMessage("观察中...")

    # ================= 定时轮询 =================
    def _connect_timer(self):
        self._timer = QTimer(self)
        self._timer.setInterval(self._settings.poll_interval_ms)
        self._timer.timeout.connect(self._on_tick)
        # 默认启动（但先不请求 AI）
        self._timer.start()

    def _on_tick(self):
        self._refresh_once()

    def _refresh_once(self, force_vision: bool = False):
        # 防并发
        if self._requesting:
            return

        # 窗口列表随桌面变化自动更新（保留用户已选窗口）
        self._refresh_window_list()

        # 实验模式：按导入的实验步骤指导，不再走通用教程
        if self._experiment:
            self._analyze_experiment_step(force_vision)
            return

        explicit_hwnd = self._selected_hwnd()

        # 记住「用户最后使用的外部窗口」：点助手面板时前台会变成我们自己，
        # 此时不要跳到别的窗口，继续指导刚才那一个
        fg = foreground_window()
        if fg:
            self._last_external_hwnd = fg.hwnd
        win: WindowInfo | None = pick_target_window(explicit_hwnd or self._last_external_hwnd)
        if not win:
            self.lbl_software.setText("—")
            self.lbl_window.setText("未找到可指导的窗口")
            self.lbl_elements.setText("0")
            self.statusBar().showMessage("未找到可指导的窗口，请打开需要学习的软件")
            self.guide_updated.emit(
                "请先打开需要学习的软件窗口（如豆包、浏览器、VS Code、系统设置），\n"
                "再在「目标窗口」里选择它。",
                {"x": None},
            )
            return

        # 用户明确指定且窗口最小化 → 先恢复，否则 UIA 只能拿到窗口框架
        if explicit_hwnd and win.minimized:
            restore_and_focus(win.hwnd)
            time.sleep(0.25)
            left, top, width, height = window_rect(win.hwnd)
            win.left, win.top, win.width, win.height = left, top, width, height
            win.minimized = False

        self.lbl_software.setText(win.exe or "—")
        self.lbl_window.setText(win.title or "—")

        # UIA 控件抓取（毫秒级），有它就能走精确标注、完全不用视觉模型
        try:
            elements = collect_elements(win.hwnd)
        except Exception:
            elements = []

        # 没有可访问控件（如部分 Electron 应用）：每个窗口只自动尝试一次视觉识别，
        # 之后需要用户点「立即刷新」，避免每轮轮询都阻塞几十秒
        if not elements:
            if not force_vision and win.hwnd in self._vision_tried:
                self.statusBar().showMessage(
                    "该窗口无法读取控件，可点击「立即刷新」做视觉识别"
                )
                return
            self._vision_tried.add(win.hwnd)

        self._requesting = True
        self.statusBar().showMessage(f"🔍 正在识别「{win.title[:20]}」...")

        hint = " ".join(x for x in (win.title, win.exe) if x)
        step_index = self._step_index
        stub_text = self._waiting_text(win.exe)

        def _do_request():
            """抓图 + 后端请求放后台，避免阻塞界面"""
            cap = self._capturer.capture_window(win)
            image_b64 = ""
            if cap.image:
                try:
                    buf = io.BytesIO()
                    cap.image.convert("RGB").save(buf, "JPEG", quality=88)
                    image_b64 = base64.b64encode(buf.getvalue()).decode()
                except Exception:
                    image_b64 = ""

            try:
                resp = self._client.request_screen_guide(
                    image_b64,
                    software_hint=hint,
                    step_index=step_index,
                    region=(cap.left, cap.top),
                    image_size=(cap.width, cap.height),
                    uia_elements=elements,
                    force_vision=force_vision,
                )
                self._request_done.emit({
                    "ok": resp is not None,
                    "resp": resp,
                    "window_title": win.title,
                    "process_name": win.exe,
                    "uia_count": len(elements),
                    "waiting_text": stub_text,
                })
            except Exception as e:
                self._request_done.emit({
                    "ok": False, "error": str(e),
                    "window_title": win.title,
                    "process_name": win.exe,
                    "uia_count": len(elements),
                    "waiting_text": stub_text,
                })

        threading.Thread(target=_do_request, daemon=True).start()

    def _apply_request_result(self, data: dict):
        """后台线程完成后，在主线程更新 UI"""
        self._requesting = False
        if self._experiment:
            return  # 已切换到实验模式，丢弃旧的通用识别结果
        resp = data.get("resp") or {}

        if not (data.get("ok") and resp.get("available")):
            guide_text = data.get("waiting_text") or "AI 正在观察你的屏幕..."
            reason = ""
            if resp and not resp.get("available"):
                reason = f"（{resp.get('reason', '视觉模型不可用')}）"
            self.txt_guide.setPlainText(guide_text)
            self.statusBar().showMessage(f"⚠️ 未能获取识别结果{reason}")
            self.guide_updated.emit(guide_text, {"x": None})
            return

        # 控件池：UIA 精确坐标优先
        self._elements = resp.get("elements") or []
        self.lbl_elements.setText(
            f"{len(self._elements)}（UIA {data.get('uia_count', 0)}）"
        )
        if resp.get("software"):
            self.lbl_software.setText(resp["software"])

        tutorial = resp.get("tutorial")
        if tutorial:
            self._tutorial = tutorial
            steps = tutorial.get("steps", [])
            idx = int(resp.get("step_index", 0) or 0)
            self._step_index = max(0, min(idx, len(steps) - 1)) if steps else 0
            self._render_tutorial(backend_target=resp.get("target"))
            self.statusBar().showMessage(
                f"✅ {tutorial['display_name']} · 第 {self._step_index + 1}/{len(steps)} 步 · "
                f"{SOURCE_TEXT.get(resp.get('target_source') or '', '未定位到控件')}"
            )
        else:
            self._tutorial = None
            self._step_index = 0
            self.btn_prev_step.setEnabled(False)
            self.btn_next_step.setEnabled(False)
            self.lbl_tut_name.setText("通用建议（未收录该软件教程）")
            guide_text = resp.get("instruction") or data.get("waiting_text", "")
            target = self._target_from_el(resp.get("target"), "目标控件")
            self.txt_guide.setPlainText(guide_text)
            self.lbl_exp_step.setText(f"识别 {len(self._elements)} 个控件")
            self.statusBar().showMessage(
                f"✅ 已识别「{resp.get('software') or '当前软件'}」 · "
                f"{SOURCE_TEXT.get(resp.get('target_source') or '', '未定位到控件')}"
            )
            self.guide_updated.emit(
                guide_text if len(guide_text) <= 180 else guide_text[:180] + "…", target
            )

    # ================= 教程翻页 =================
    def _tutorial_prev(self):
        if self._experiment:
            self._exp_step_prev()
            return
        if self._tutorial and self._step_index > 0:
            self._step_index -= 1
            self._render_tutorial()

    def _tutorial_next(self):
        if self._experiment:
            self._exp_step_next()
            return
        steps = (self._tutorial or {}).get("steps", [])
        if self._tutorial and self._step_index < len(steps) - 1:
            self._step_index += 1
            self._render_tutorial()

    def _target_from_el(self, el: dict | None, fallback_label: str) -> dict:
        """控件已是屏幕物理像素坐标，直接用于悬浮标注（不再做比例换算）"""
        if el and el.get("x") is not None:
            return {
                "x": int(el["x"]),
                "y": int(el["y"]),
                "width": max(int(el.get("width", 0)), 12),
                "height": max(int(el.get("height", 0)), 10),
                "label": el.get("name") or fallback_label,
            }
        return {"x": None, "y": None, "width": 0, "height": 0, "label": fallback_label}

    @staticmethod
    def _match_step_target_local(elements: list[dict], step: dict) -> dict | None:
        """本地按教程步骤关键词匹配控件（翻页用，不重新调用视觉接口）"""
        if not elements:
            return None
        keywords = [k.lower() for k in step.get("keywords", []) if k]
        hits = []
        for el in elements:
            name = (el.get("name") or "").lower()
            if not name:
                continue
            for kw in keywords:
                if kw in name or name in kw:
                    hits.append((len(kw), el))
                    break
        if hits:
            hits.sort(key=lambda x: (x[0], float(x[1].get("confidence", 0))), reverse=True)
            return hits[0][1]
        # 只接受关键词命中：按控件类型猜出来的目标经常是标题栏按钮，宁可不出框
        return None

    def _render_tutorial(self, backend_target: dict | None = None):
        """渲染当前教程步骤 + 更新悬浮标注"""
        tutorial = self._tutorial
        if not tutorial:
            return
        steps = tutorial.get("steps", [])
        if not steps:
            return

        idx = max(0, min(self._step_index, len(steps) - 1))
        self._step_index = idx
        step = steps[idx]

        lines = [
            f"📘 {tutorial['display_name']} · 使用教程",
            tutorial.get("intro", ""),
            "",
            f"第 {idx + 1}/{len(steps)} 步：{step['title']}",
            step.get("detail", ""),
            "",
            "—— 完整步骤 ——",
        ]
        for i, s in enumerate(steps):
            mark = "▶" if i == idx else "·"
            lines.append(f"{mark} {i + 1}. {s['title']}")
        text = "\n".join(lines)

        # 本地用已抓到的控件重新匹配（翻页即时生效，无需再调后端）
        el = self._match_step_target_local(self._elements, step)
        if el:
            target = self._target_from_el(el, step["title"])
        elif backend_target:
            # 后端兜底目标（例如按控件类型挑的主控件）
            target = self._target_from_el(backend_target, step["title"])
        else:
            # 没有对应控件 → 不画框，只显示教程文字，避免框错位置
            target = {"x": None, "y": None, "width": 0, "height": 0, "label": step["title"]}

        self.txt_guide.setPlainText(text)
        self.lbl_tut_name.setText(f"{tutorial['display_name']} 教程 {idx + 1}/{len(steps)}")
        self.lbl_exp_step.setText(f"识别 {len(self._elements)} 个控件")
        self.btn_prev_step.setEnabled(idx > 0)
        self.btn_next_step.setEnabled(idx < len(steps) - 1)
        self.statusBar().showMessage(
            f"✅ {tutorial['display_name']} · 第 {idx + 1} 步：{step['title']}"
        )
        # 悬浮气泡只放当前步骤（完整步骤列表留在主窗口，避免遮挡屏幕）
        bubble = f"{tutorial['display_name']}  {idx + 1}/{len(steps)}\n{step['title']}\n{step.get('detail', '')}"
        self.guide_updated.emit(bubble, target)

    def _waiting_text(self, process_name: str) -> str:
        """识别过程中的真实状态提示（不预置任何软件内容）"""
        if process_name and process_name != "unknown":
            return f"当前窗口进程：{process_name}\n正在识别界面控件，请稍候…"
        return "正在识别当前窗口，请稍候…"
