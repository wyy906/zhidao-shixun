"""实验定义域模块（V2-03）。

职责：实验定义的模型、加载校验、验证器白名单、步骤依赖与状态规则。
本模块不依赖 api/engine，反向供它们调用；跨端契约仍以 zhidao_contracts 为准。
"""

from app.experiments.errors import ExperimentIssue, ExperimentValidationError
from app.experiments.models import (
    AdapterSpec,
    ExperimentDefinition,
    ExperimentMeta,
    ExpectedState,
    StepDefinition,
    VerifierDef,
)
from app.experiments.schema_version import EXPERIMENT_SCHEMA_VERSION

__all__ = [
    "EXPERIMENT_SCHEMA_VERSION",
    "AdapterSpec",
    "ExperimentDefinition",
    "ExperimentIssue",
    "ExperimentMeta",
    "ExperimentValidationError",
    "ExpectedState",
    "StepDefinition",
    "VerifierDef",
]
