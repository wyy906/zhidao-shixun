"""业务进程侧的执行服务客户端（V2-04B 阶段 B2）。

- 业务进程只通过本客户端调用独立执行服务，绝不直接访问 Docker daemon/socket；
- 服务不可达 / 非法响应 → 结构化错误，fail-closed，绝不回退宿主机执行；
- 不把执行服务异常伪装成 Python 运行结果。
"""

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.services.executor.base import DockerUnavailableError, ExecutorError


class ExecutorServiceError(ExecutorError):
    """执行服务调用失败（网络/协议/鉴权）。调用方必须显式处理。"""


@dataclass(frozen=True)
class ExecutionSubmission:
    user_id: str
    experiment_id: str
    task_id: str
    language: str = "python"
    code: str = ""
    timeout_seconds: int = 10


class ExecutorServiceClient:
    """指向独立执行服务的最小 HTTP 客户端（标准库实现，无额外依赖）。"""

    def __init__(self, base_url: str, token: str, timeout_seconds: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        if not token:
            raise ExecutorServiceError("执行服务令牌未配置；业务进程拒绝提交执行（fail-closed）。")
        self._token = token
        self._timeout = timeout_seconds

    def health(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(
                f"{self._base_url}/healthz", timeout=self._timeout
            ) as resp:
                import json

                return dict(json.loads(resp.read().decode("utf-8")))
        except (urllib.error.URLError, OSError) as exc:
            raise DockerUnavailableError(f"执行服务不可达：{exc}") from exc

    def submit(self, submission: ExecutionSubmission) -> dict[str, Any]:
        import json

        payload = json.dumps(
            {
                "user_id": submission.user_id,
                "experiment_id": submission.experiment_id,
                "task_id": submission.task_id,
                "language": submission.language,
                "code": submission.code,
                "timeout_seconds": submission.timeout_seconds,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/v1/executions",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Execution-Token": self._token,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return dict(json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            raise ExecutorServiceError(
                f"执行服务返回 HTTP {exc.code}：{body}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DockerUnavailableError(f"执行服务不可达：{exc}") from exc
