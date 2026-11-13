"""执行记录（V2-04B 阶段 B2）。

每次执行落一条 JSONL 记录，关联用户/实验/任务；执行记录只描述"容器执行发生了什么"，
绝不包含实验验证结论（验证结果由验证器另行判定，两者严格分离）。
"""

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.executor.models import ExecutionOutcome


@dataclass(frozen=True)
class ExecutionRecord:
    """一条容器执行记录（面向审计与学习记录，非验证结论）。"""

    record_id: str
    user_id: str
    experiment_id: str
    task_id: str
    status: str            # completed / timeout / error
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    failure_kind: str | None
    failure_detail: str
    container_id: str | None
    duration_ms: int | None
    created_at: str        # ISO8601 UTC

    @classmethod
    def from_outcome(cls, outcome: ExecutionOutcome, record_id: str, created_at: str) -> "ExecutionRecord":
        result = outcome.result
        return cls(
            record_id=record_id,
            user_id=outcome.task.user_id,
            experiment_id=outcome.task.experiment_id,
            task_id=outcome.task.task_id,
            status=outcome.status,
            exit_code=result.exit_code if result else None,
            stdout=result.stdout if result else "",
            stderr=result.stderr if result else "",
            timed_out=result.timed_out if result else False,
            truncated=result.truncated if result else False,
            failure_kind=outcome.failure_kind.value if outcome.failure_kind else None,
            failure_detail=outcome.failure_detail,
            container_id=outcome.container_id,
            duration_ms=outcome.duration_ms,
            created_at=created_at,
        )


class JsonlRecordStore:
    """JSONL 追加式执行记录存储（append-only）。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: ExecutionRecord) -> None:
        line = json.dumps(asdict(record), ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read_all(self) -> list[ExecutionRecord]:
        if not self._path.exists():
            return []
        records: list[ExecutionRecord] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(ExecutionRecord(**json.loads(line)))
        return records
