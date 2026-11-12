"""实验定义加载器：文件/字典 → 严格校验 → ExperimentDefinition。

校验顺序（全部通过才返回模型，任何失败都抛 ExperimentValidationError）：
1. 版本门：schema_version 必须在受支持列表内（给出友好错误，避免 const 报错难懂）；
2. Schema 门：jsonschema 对 experiments/schema/ 的规范文件独立校验（未知字段、类型、
   枚举、长度上限都在这一层拦截）；
3. 模型门：Pydantic 严格模型（与 Schema 镜像，extra=forbid）；
4. 语义门：environment 与 adapter_id 一致、依赖存在且无环、验证器类型在白名单内且
   参数合法、验证器支持当前环境。
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError as PydanticValidationError

from app.experiments.dependency import DependencyError, validate_dependencies
from app.experiments.errors import ExperimentIssue, ExperimentValidationError
from app.experiments.models import VALID_ENVIRONMENTS, ExperimentDefinition
from app.experiments.schema_version import SUPPORTED_SCHEMA_VERSIONS
from app.experiments.verifiers.registry import validate_verifier_def

SCHEMA_FILE = Path(__file__).resolve().parents[3] / "experiments" / "schema" / "experiment_definition.schema.json"


def _json_path(parts: tuple[Any, ...]) -> str:
    """jsonschema 错误路径 → 可读路径：steps[2].verifier.type。"""
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path or "<root>"


def _schema_issues(errors: list[jsonschema.ValidationError], file: str | None) -> list[ExperimentIssue]:
    return [
        ExperimentIssue(
            path=_json_path(tuple(error.absolute_path)),
            message=error.message,
            category="schema",
            file=file,
        )
        for error in errors
    ]


def _validate_against_schema(data: Any, file: str | None) -> None:
    """独立使用 experiments/schema/ 的 JSON Schema 校验（不依赖 Pydantic）。"""
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)
    raw_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if raw_errors:
        raise ExperimentValidationError(_schema_issues(raw_errors, file))


def _semantic_issues(definition: ExperimentDefinition, file: str | None) -> list[ExperimentIssue]:
    issues: list[ExperimentIssue] = []

    if definition.environment != definition.adapter.adapter_id:
        issues.append(
            ExperimentIssue(
                path="adapter.adapter_id",
                message=(
                    f"适配器标识 {definition.adapter.adapter_id} 与实验环境 "
                    f"{definition.environment} 不一致"
                ),
                category="semantic",
                file=file,
            )
        )

    try:
        validate_dependencies(definition.steps)
    except DependencyError as exc:
        issues.append(
            ExperimentIssue(path="steps", message=str(exc), category="semantic", file=file)
        )

    for index, step in enumerate(definition.steps):
        for message in validate_verifier_def(
            step.verifier.type,
            step.verifier.params,
            environment=definition.environment,
        ):
            issues.append(
                ExperimentIssue(
                    path=f"steps[{index}].verifier.type",
                    message=message,
                    category="semantic",
                    file=file,
                )
            )
    return issues


def load_experiment_dict(data: Any, *, source: str | None = None) -> ExperimentDefinition:
    """从已解析的 JSON 数据加载实验定义（严格校验，失败抛 ExperimentValidationError）。"""
    file = source

    if not isinstance(data, dict):
        raise ExperimentValidationError(
            [ExperimentIssue(path="<root>", message="实验定义必须是 JSON 对象", category="schema", file=file)]
        )

    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ExperimentValidationError(
            [
                ExperimentIssue(
                    path="schema_version",
                    message=(
                        f"不支持的实验定义版本 {version!r}；当前支持：{', '.join(SUPPORTED_SCHEMA_VERSIONS)}。"
                        "请升级加载器或改用受支持版本的实验文件"
                    ),
                    category="semantic",
                    file=file,
                )
            ]
        )

    # 1) Schema 独立校验
    _validate_against_schema(data, file)

    # 2) Pydantic 严格模型
    try:
        definition = ExperimentDefinition.model_validate(data)
    except PydanticValidationError as exc:
        issues = [
            ExperimentIssue(
                path=_json_path(tuple(error["loc"])),
                message=error["msg"],
                category="schema",
                file=file,
            )
            for error in exc.errors()
        ]
        raise ExperimentValidationError(issues) from None

    # 3) 语义校验
    semantic = _semantic_issues(definition, file)
    if semantic:
        raise ExperimentValidationError(semantic)

    return definition


def load_experiment_file(path: Path | str) -> ExperimentDefinition:
    """从 JSON 文件加载实验定义；错误信息包含文件路径、字段路径与原因。"""
    file_path = Path(path)
    if not file_path.exists():
        raise ExperimentValidationError(
            [ExperimentIssue(path="<root>", message=f"文件不存在：{file_path}", category="file", file=str(file_path))]
        )
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ExperimentValidationError(
            [
                ExperimentIssue(
                    path="<root>",
                    message=f"不是有效的 UTF-8 JSON 文件：{exc}",
                    category="file",
                    file=str(file_path),
                )
            ]
        ) from None
    return load_experiment_dict(data, source=str(file_path))


def adapter_environments() -> tuple[str, ...]:
    """当前支持的目标环境（供仓库/未来 API 使用）。"""
    return VALID_ENVIRONMENTS
