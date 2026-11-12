"""契约枚举：三端共享的语义常量。"""

from enum import Enum, IntEnum


class GuideLevel(IntEnum):
    """指导颗粒度四级（AI_COLLABORATION.md §3）。"""

    CONCISE = 1    # 一级：简洁提示
    ANNOTATE = 2   # 二级：屏幕标注
    DETAILED = 3   # 三级：详细解释
    DEMO = 4       # 四级：局部示范


class StepStatus(str, Enum):
    """实验步骤状态机（V2-03 起由引擎驱动）。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class VerifyOutcome(str, Enum):
    """验证三态：成功 / 失败 / 不确定（不允许只凭大模型口头判断标记成功）。"""

    PASSED = "passed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class ContractSource(str, Enum):
    """状态来源端。"""

    SERVER = "server"
    WEB = "web"
    DESKTOP = "desktop"
