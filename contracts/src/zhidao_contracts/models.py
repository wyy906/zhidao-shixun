"""跨端统一数据契约模型（V2-02 首批五个核心模型）。

规则：
- desktop 只依赖本包，禁止 import server 内部模块；
- 每个消息模型携带 schema_version，默认取当前 CONTRACT_VERSION；
- Web 端通过 contracts/schemas/ 下的 JSON Schema 对齐（由 export_schemas.py 导出）。
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import ContractSource, GuideLevel, StepStatus, VerifyOutcome
from .version import CONTRACT_VERSION


def _current_contract_version() -> str:
    return CONTRACT_VERSION


class UiTarget(BaseModel):
    """屏幕目标 / 控件定位。坐标为屏幕像素，标注层（V2-06）可直接使用。

    confidence 低于阈值（由消费端定义）时不得做精确标注，只能降级为文字指导。
    """

    x: int
    y: int
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    label: str = Field(description="人类可读名称，如「新建查询按钮」")
    control_type: str | None = Field(default=None, description="控件类型提示，如 Button / MenuItem")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ScreenState(BaseModel):
    """一次屏幕 / 页面感知快照。由 desktop 感知适配器或 web 实验端上报。"""

    schema_version: str = Field(default_factory=_current_contract_version)
    captured_at: datetime
    source: ContractSource
    window_title: str | None = None
    process_name: str | None = None
    targets: list[UiTarget] = Field(default_factory=list)
    notes: str | None = Field(default=None, description="状态补充描述；禁止包含敏感信息")


class StepState(BaseModel):
    """实验步骤当前状态（引擎状态机的对外表达）。"""

    schema_version: str = Field(default_factory=_current_contract_version)
    experiment_id: str
    step_id: str
    status: StepStatus
    attempts: int = Field(default=0, ge=0)
    guide_level: GuideLevel = Field(default=GuideLevel.CONCISE)
    last_feedback: str | None = None


class VerifyRequest(BaseModel):
    """验证请求。actual 为验证器约定的实际结果载荷（命令输出、查询结果、文件状态等）。"""

    schema_version: str = Field(default_factory=_current_contract_version)
    experiment_id: str
    step_id: str
    actual: dict[str, object] = Field(default_factory=dict)
    screen: ScreenState | None = None


class VerifyResult(BaseModel):
    """验证结果：三态 + 可复核证据。"""

    schema_version: str = Field(default_factory=_current_contract_version)
    step_id: str
    outcome: VerifyOutcome
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    feedback: str
    evidence: dict[str, object] = Field(default_factory=dict, description="可复核证据：命令输出、查询结果、文件状态等")


class GuideMessage(BaseModel):
    """指导消息：四级颗粒度 + 可选标注目标（二级指导需带 targets）。"""

    schema_version: str = Field(default_factory=_current_contract_version)
    step_id: str
    level: GuideLevel
    title: str
    content: str
    targets: list[UiTarget] = Field(default_factory=list)
    created_at: datetime
