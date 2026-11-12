"""Windows 助手启动入口。

用法（cwd = desktop/）：
    python -m zhidao_desktop.main            # 正常启动窗口
    python -m zhidao_desktop.main --smoke    # 启动窗口 1.5 秒后自动退出（自动化验证）
    python -m zhidao_desktop.main --check    # 仅检测后端 /health，不打开窗口
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zhidao-desktop", description="智导实训 Windows 助手")
    parser.add_argument("--smoke", action="store_true", help="启动窗口 1.5 秒后自动退出（自动化验证）")
    parser.add_argument("--check", action="store_true", help="仅检测后端连接，不打开窗口")
    args = parser.parse_args(argv)

    from zhidao_desktop.config.settings import load_settings
    from zhidao_desktop.network.api_client import get_health

    settings = load_settings()

    if args.check:
        try:
            data = get_health(settings.api_base_url, settings.request_timeout_seconds)
            print(f"[check] 后端已连接：{data}")
            return 0
        except Exception as exc:
            print(f"[check] 后端连接失败：{exc.__class__.__name__}: {exc}")
            return 1

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from zhidao_desktop.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    window = MainWindow()
    window.show()
    if args.smoke:
        QTimer.singleShot(1500, app.quit)
        print("[smoke] 窗口已启动，1.5 秒后自动退出")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
