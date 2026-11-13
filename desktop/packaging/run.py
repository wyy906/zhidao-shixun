"""便携分发启动器：使用随包的 Python 运行时启动桌面助手。"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "app"))

from main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
