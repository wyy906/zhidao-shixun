"""实验定义 Pydantic 模型。

约束与 experiments/schema/experiment_definition.schema.json 一一对应：
- 全部模型 extra="forbid"（未知字段拒绝）；
- 长度/数量上限与 Schema 相同；
- 验证器类型与适配器标识是白名单枚举；
- Schema 结构校验之外的字段级约束（如依赖存在、无环、参数合法性）在 loader 语义校验层完成。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_ENVIRONMENTS: tuple[str, ...] = ("python_web", "mysql_workbench")


def _validate_conditional_text_list(value: list[str]) -> list[str]:
    """条件描述列表逐项校验：1..300 字符（与 Schema 的 item minLength/maxLength 镜像）。"""
    for index, item in enumerate(value):
        if not isinstance(item, str) or not (1 <= len(item) <= 300):
            raise ValueError(f"第 {index} 项必须是 1..300 字符的字符串")
    return value


class VerifierDef(BaseModel):
    """验证器定义。type 只能取 registry 白名单中的值（Schema 层已限定枚举）。"""

    model_config = ConfigDict(extra="forbid")

    type: str
    params: dict[str, Any] = Field(default_factory=dict, max_length=16)

    @property
    def supported(self) -> bool:
        """该验证器是否已实现（reserved 类型可被结构化表达，但执行必须拒绝）。"""
        from app.experiments.verifiers.registry import get_spec

        spec = get_spec(self.type)
        return spec is not None and spec.implementation.value == "implemented"


class ExpectedState(BaseModel):
    """预期状态：description 给人读，artifacts 描述可复核产物；机器条件由 verifier 表达。"""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    artifacts: list[str] = Field(default_factory=list, max_length=10)


class StepDefinition(BaseModel):
    """单个实验步骤。三类信息显式分离：student_action（给学生）、verifier+expected_state（机器）、learning_goal（AI 参考）。"""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=120)
    learning_goal: str = Field(min_length=1, max_length=500)
    student_action: str = Field(min_length=1, max_length=1000)
    expected_state: ExpectedState
    verifier: VerifierDef
    depends_on: list[str] = Field(default_factory=list, max_length=10)
    preconditions: list[str] = Field(
        max_length=10,
        description="操作前置条件（本步骤自身的条件，显式必填；空数组表示无额外前置条件），与 depends_on（步骤间依赖）相互独立",
    )
    common_errors: list[str] = Field(default_factory=list, max_length=10)
    recovery_hints: list[str] = Field(default_factory=list, max_length=10)
    guide_hint: int = Field(ge=1, le=4)

    @field_validator("preconditions", "common_errors", "recovery_hints")
    @classmethod
    def _check_text_items(cls, value: list[str]) -> list[str]:
        return _validate_conditional_text_list(value)


class AdapterSpec(BaseModel):
    """适配器标识与能力要求。adapter_id 必须与实验 environment 一致（语义校验）。"""

    model_config = ConfigDict(extra="forbid")

    adapter_id: Literal["python_web", "mysql_workbench"]
    capabilities: list[str] = Field(default_factory=list, max_length=16)


class ExperimentMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_minutes: int = Field(ge=1, le=600)
    difficulty: Literal["beginner", "intermediate", "advanced"]


class ExperimentDefinition(BaseModel):
    """完整实验定义。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    experiment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1, max_length=40)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    environment: Literal["python_web", "mysql_workbench"]
    adapter: AdapterSpec
    prerequisites: list[str] = Field(default_factory=list, max_length=20)
    steps: list[StepDefinition] = Field(min_length=1, max_length=100)
    meta: ExperimentMeta

    @property
    def step_map(self) -> dict[str, StepDefinition]:
        return {step.step_id: step for step in self.steps}

    def get_step(self, step_id: str) -> StepDefinition:
        try:
            return self.step_map[step_id]
        except KeyError:
            raise KeyError(f"实验 {self.experiment_id} 中不存在步骤 {step_id}") from None
