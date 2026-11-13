"""实验列表/详情接口测试（V2-04D1）。

全部 Mock/依赖注入测试：验证只读 API 的加载语义与错误处理，
不构成真实 Docker 验证。
"""

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.v1.executions import get_experiments_repository
from app.experiments.repository import ExperimentsRepository
from app.main import create_app

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import make_valid_experiment  # noqa: E402

EXPERIMENT_ID = "py-web-demo"


def make_client(repo: ExperimentsRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_experiments_repository] = lambda: repo
    return TestClient(app)


def make_repo(tmp_path, *, valid: bool = True, broken: bool = False) -> ExperimentsRepository:
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir()
    if valid:
        data = make_valid_experiment()
        data["experiment_id"] = EXPERIMENT_ID
        (exp_dir / "demo.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    if broken:
        (exp_dir / "broken.json").write_text('{"schema_version": "oops"}', encoding="utf-8")
    return ExperimentsRepository(directory=exp_dir)


def test_empty_directory_returns_empty_list(tmp_path):
    http = make_client(make_repo(tmp_path, valid=False))
    resp = http.get("/api/v1/experiments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["experiments"] == []
    assert body["issues_count"] == 0


def test_list_returns_experiment_summary(tmp_path):
    http = make_client(make_repo(tmp_path))
    resp = http.get("/api/v1/experiments")
    assert resp.status_code == 200
    items = resp.json()["experiments"]
    assert len(items) == 1
    item = items[0]
    assert item["experiment_id"] == EXPERIMENT_ID
    assert item["title"]
    assert item["environment"] == "python_web"
    assert item["step_count"] == 2
    assert item["difficulty"] == "beginner"


def test_list_reports_issue_count_for_broken_files(tmp_path):
    """fail-closed 加载语义：非法文件不进入列表，问题数如实返回。"""
    http = make_client(make_repo(tmp_path, broken=True))
    resp = http.get("/api/v1/experiments")
    body = resp.json()
    assert body["issues_count"] >= 1
    assert all(item["experiment_id"] != "broken" for item in body["experiments"])


def test_detail_returns_full_definition(tmp_path):
    http = make_client(make_repo(tmp_path))
    resp = http.get(f"/api/v1/experiments/{EXPERIMENT_ID}")
    assert resp.status_code == 200
    detail = resp.json()["experiment"]
    assert detail["experiment_id"] == EXPERIMENT_ID
    assert [s["step_id"] for s in detail["steps"]] == ["s1", "s2"]
    assert detail["steps"][1]["depends_on"] == ["s1"]
    assert detail["steps"][0]["verifier"]["type"] == "python_exit_code_zero"


def test_detail_unknown_experiment_is_404(tmp_path):
    http = make_client(make_repo(tmp_path))
    resp = http.get("/api/v1/experiments/no-such-exp")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "experiment_not_found"
