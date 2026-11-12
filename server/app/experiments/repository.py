"""实验文件仓库：扫描目录、汇总加载、按 ID 取用。

V2-03 不引入数据库（按 §7 要求，文件仓库已满足当前需求）；
实验文件由用户放入 experiments/ 目录，仓库不内置任何演示实验。
"""

from collections.abc import Iterator
from pathlib import Path

from app.experiments.errors import ExperimentIssue, ExperimentValidationError
from app.experiments.loader import load_experiment_file
from app.experiments.models import ExperimentDefinition


def default_experiments_dir() -> Path:
    """仓库默认实验目录：<repo>/experiments/（server/app/experiments/repository.py 向上三层）。"""
    return Path(__file__).resolve().parents[3] / "experiments"


class ExperimentsRepository:
    """只读文件仓库。加载是整体式的：任何文件非法都会进入 errors，绝不返回不完整实验。"""

    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory else default_experiments_dir()

    def iter_definition_files(self) -> Iterator[Path]:
        """顶层 *.json 文件（schema/ 子目录自动排除）。"""
        if not self.directory.exists():
            return
        for path in sorted(self.directory.glob("*.json")):
            yield path

    def load_all(self) -> tuple[dict[str, ExperimentDefinition], list[ExperimentIssue]]:
        """加载目录下全部实验定义。返回（按 ID 索引的定义, 全部问题列表）。"""
        loaded: dict[str, ExperimentDefinition] = {}
        issues: list[ExperimentIssue] = []

        if not self.directory.exists():
            issues.append(
                ExperimentIssue(
                    path="<root>",
                    message=f"实验目录不存在：{self.directory}",
                    category="file",
                    file=str(self.directory),
                )
            )
            return loaded, issues

        for path in self.iter_definition_files():
            try:
                definition = load_experiment_file(path)
            except ExperimentValidationError as exc:
                issues.extend(exc.issues)
                continue
            if definition.experiment_id in loaded:
                issues.append(
                    ExperimentIssue(
                        path="experiment_id",
                        message=(
                            f"实验 ID {definition.experiment_id} 重复："
                            f"{loaded[definition.experiment_id]} 与 {path}"
                        ),
                        category="semantic",
                        file=str(path),
                    )
                )
                continue
            loaded[definition.experiment_id] = definition
        return loaded, issues

    def load_or_raise(self) -> dict[str, ExperimentDefinition]:
        """加载全部定义；存在任何问题时整体失败（fail-closed）。"""
        loaded, issues = self.load_all()
        if issues:
            raise ExperimentValidationError(issues)
        return loaded

    def get(self, experiment_id: str) -> ExperimentDefinition | None:
        """按 ID 加载单个实验（重新扫描目录）。"""
        loaded, _ = self.load_all()
        return loaded.get(experiment_id)

    def __repr__(self) -> str:
        return f"ExperimentsRepository({self.directory})"
