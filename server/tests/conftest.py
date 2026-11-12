"""pytest 共享配置。同时支持从仓库根目录（推荐）与 server/ 目录运行。"""

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
