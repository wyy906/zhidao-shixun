"""V2-02 最小主窗口：后端连接状态、暂停/恢复、停止入口。

感知与标注能力在 V2-05 / V2-06 接入；当前「暂停感知」仅切换状态标记，不采集任何内容。
"""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zhidao_desktop.config.settings import load_settings
from zhidao_desktop.network.api_client import get_health


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("智导实训 · Windows 助手")
        self.resize(460, 240)
        self._paused = False

        central = QWidget(self)
        layout = QVBoxLayout(central)

        self._status_label = QLabel("状态：运行中（感知能力 V2-05 接入）")
        self._server_label = QLabel("后端：未检测")
        layout.addWidget(self._status_label)
        layout.addWidget(self._server_label)

        buttons = QHBoxLayout()
        self._pause_btn = QPushButton("暂停感知")
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._refresh_btn = QPushButton("检查后端连接")
        self._refresh_btn.clicked.connect(self._check_server)
        self._stop_btn = QPushButton("停止助手")
        self._stop_btn.clicked.connect(self._stop)
        buttons.addWidget(self._pause_btn)
        buttons.addWidget(self._refresh_btn)
        buttons.addWidget(self._stop_btn)
        layout.addLayout(buttons)
        layout.addStretch(1)
        self.setCentralWidget(central)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._status_label.setText("状态：已暂停（不采集、不标注）")
            self._pause_btn.setText("恢复感知")
        else:
            self._status_label.setText("状态：运行中（感知能力 V2-05 接入）")
            self._pause_btn.setText("暂停感知")

    def _check_server(self) -> None:
        try:
            data = get_health(load_settings().api_base_url)
            contract_version = data.get("contract_version", "未知")
            self._server_label.setText(f"后端：已连接（契约 {contract_version}，环境 {data.get('app_env')}）")
        except Exception as exc:
            self._server_label.setText(f"后端：连接失败（{exc.__class__.__name__}）")

    def _stop(self) -> None:
        answer = QMessageBox.question(self, "停止助手", "确定停止并关闭 Windows 助手？")
        if answer == QMessageBox.StandardButton.Yes:
            self.close()
