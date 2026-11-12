"""实验定义 Pydantic 模型。

约束与 experiments/schema/experiment_definition.schema.json 一一对应（第三轮复审后逐字段镜像）：
- 全部模型 extra="forbid"（未知字段拒绝）；
- 字符串长度、数组数量、元素长度、唯一性、正则表达式与 Schema 相同；
- 验证器类型与适配器标识是白名单枚举；
- Schema 结构校验之外的字段级约束（如依赖存在、无环、参数合法性）在 loader 语义校验层完成。
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_ENVIRONMENTS: tuple[str, ...] = ("python_web", "mysql_workbench")

_STEP_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _validate_bounded_text_list(value: list[str], *, max_item_length: int) -> list[str]:
    """条件/能力描述列表逐项校验：字符串且长度 1..max_item_length（镜像 Schema item minLength/maxLength）。"""
    for index, item in enumerate(value):
        if not isinstance(item, str) or not (1 <= len(item) <= max_item_length):
            raise ValueError(f"第 {index} 项必须是 1..{max_item_length} 字符的字符串")
    return value


def _validate_unique_bounded_text_list(value: list[str], *, max_item_length: int) -> list[str]:
    """在逐项长度校验基础上追加唯一性（镜像 Schema uniqueItems）。"""
    _validate_bounded_text_list(value, max_item_length=max_item_length)
    if len(set(value)) != len(value):
        raise ValueError("列表项不允许重复")
    return value


def _validate_step_id_list(value: list[str]) -> list[str]:
    """依赖列表校验：逐项符合步骤 ID 格式且不重复（镜像 Schema item pattern + uniqueItems）。"""
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _STEP_ID_PATTERN.fullmatch(item):
            raise ValueError(f"第 {index} 项 {item!r} 不符合步骤 ID 格式（小写字母/数字/下划线/连字符）")
    if len(set(value)) != len(value):
        raise ValueError("depends_on 不允许重复步骤 ID")
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

    @field_validator("artifacts")
    @classmethod
    def _check_artifacts(cls, value: list[str]) -> list[str]:
        return _validate_bounded_text_list(value, max_item_length=200)


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

    @field_validator("depends_on")
    @classmethod
    def _check_depends_on(cls, value: list[str]) -> list[str]:
        return _validate_step_id_list(value)

    @field_validator("preconditions", "common_errors", "recovery_hints")
    @classmethod
    def _check_text_items(cls, value: list[str]) -> list[str]:
        return _validate_bounded_text_list(value, max_item_length=300)


class AdapterSpec(BaseModel):
    """适配器标识与能力要求。adapter_id 必须与实验 environment 一致（语义校验）。"""

    model_config = ConfigDict(extra="forbid")

    adapter_id: Literal["python_web", "mysql_workbench"]
    capabilities: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("capabilities")
    @classmethod
    def _check_capabilities(cls, value: list[str]) -> list[str]:
        return _validate_unique_bounded_text_list(value, max_item_length=40)


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

    @field_validator("prerequisites")
    @classmethod
    def _check_prerequisites(cls, value: list[str]) -> list[str]:
        return _validate_bounded_text_list(value, max_item_length=200)

    @property
    def step_map(self) -> dict[str, StepDefinition]:
        return {step.step_id: step for step in self.steps}

    def get_step(self, step_id: str) -> StepDefinition:
        try:
            return self.step_map[step_id]
        except KeyError:
            raise KeyError(f"实验 {self.experiment_id} 中不存在步骤 {step_id}") from None
