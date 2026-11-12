"""智导实训 Windows 桌面助手 —— 入口"""
import sys
from pathlib import Path

# 确保能 import 同包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import load_settings
from ui.main_window import MainWindow
from ui.tray import SystemTray


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("智导实训助手")
    app.setQuitOnLastWindowClosed(False)  # 关闭主窗口后保留托盘

    settings = load_settings()

    # 主窗口
    window = MainWindow(settings)
    window.show()

    # 系统托盘
    tray = SystemTray(window, app)
    tray.show()

    # 首次启动提示
    if settings.backend_url:
        pass  # 后续可以尝试连接后端
    else:
        QMessageBox.information(
            window,
            "欢迎使用",
            "智导实训桌面助手已启动。\n请先在『设置』中配置后端 API 地址。",
        )

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
