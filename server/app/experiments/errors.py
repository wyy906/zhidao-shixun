"""实验定义校验错误：所有失败都以可定位的 ExperimentIssue 列表返回。"""

from dataclasses import dataclass, field
from typing import Literal

IssueCategory = Literal["file", "schema", "semantic"]


@dataclass(frozen=True)
class ExperimentIssue:
    """一条可定位的校验问题。

    path 为问题在实验 JSON 中的定位（如 experiment_id、steps[2].verifier.type）；
    file 仅在从文件加载时提供；category 区分文件级 / Schema 级 / 语义级问题。
    """

    path: str
    message: str
    category: IssueCategory
    file: str | None = None

    def __str__(self) -> str:
        location = self.file or "<memory>"
        return f"[{self.category}] {location} :: {self.path} :: {self.message}"


@dataclass
class ExperimentValidationError(Exception):
    """实验定义校验失败。绝不静默跳过错误后返回不完整实验。"""

    issues: list[ExperimentIssue] = field(default_factory=list)

    def __str__(self) -> str:
        joined = "\n  ".join(str(issue) for issue in self.issues)
        return f"实验定义校验失败（{len(self.issues)} 个问题）：\n  {joined}"
