"""日志初始化：统一格式，级别由配置控制。"""

import logging


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    # 降低 uvicorn 内部日志重复输出
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
