"""智导实训 V2 跨端统一数据契约。

- Python 端（server、desktop）安装本包后直接导入模型；
- Web 端使用 contracts/schemas/ 下的 JSON Schema（运行 contracts/scripts/export_schemas.py 重新导出）；
- 本包不依赖 server / desktop / web 任何内部模块。

schema_version 语义见 version.py。
"""

from pydantic import BaseModel

from .enums import ContractSource, GuideLevel, StepStatus, VerifyOutcome
from .models import (
    GuideMessage,
    ScreenState,
    StepState,
    UiTarget,
    VerifyRequest,
    VerifyResult,
)
from .version import CONTRACT_VERSION

# 参与跨端契约的核心消息模型清单（导出 JSON Schema 与漂移检测均以此为准）
CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    ScreenState,
    StepState,
    VerifyRequest,
    VerifyResult,
    GuideMessage,
)

__all__ = [
    "CONTRACT_VERSION",
    "CONTRACT_MODELS",
    "ContractSource",
    "GuideLevel",
    "GuideMessage",
    "ScreenState",
    "StepState",
    "StepStatus",
    "UiTarget",
    "VerifyOutcome",
    "VerifyRequest",
    "VerifyResult",
]
