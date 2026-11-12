"""实验仓库测试：目录扫描、非法文件报告、重复 ID、fail-closed。"""

import json
import sys
from pathlib import Path

import pytest

from app.experiments.errors import ExperimentValidationError
from app.experiments.repository import ExperimentsRepository

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers_experiment import deep_copy, make_valid_experiment  # noqa: E402


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_scan_loads_valid_files_and_ignores_non_json(tmp_path) -> None:
    _write(tmp_path / "a.json", make_valid_experiment())
    other = deep_copy(make_valid_experiment())
    other["experiment_id"] = "py-web-demo-2"
    _write(tmp_path / "b.json", other)
    (tmp_path / "not-json.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "schema").mkdir()  # schema/ 子目录下的 json 不属于用户实验

    repo = ExperimentsRepository(tmp_path)
    loaded, issues = repo.load_all()
    assert set(loaded) == {"py-web-demo", "py-web-demo-2"}
    assert issues == []


def test_invalid_file_is_reported_with_path_and_reason(tmp_path) -> None:
    broken = deep_copy(make_valid_experiment())
    broken["experiment_id"] = "broken-exp"
    broken.pop("title")
    _write(tmp_path / "c.json", broken)
    (tmp_path / "bad.json").write_text("{ not json", encoding="utf-8")

    repo = ExperimentsRepository(tmp_path)
    loaded, issues = repo.load_all()
    assert loaded == {}  # 非法文件不进入结果（fail-closed）
    assert any("title" in i.message and i.file and "c.json" in i.file for i in issues)
    assert any(i.category == "file" and "bad.json" in (i.file or "") for i in issues)


def test_duplicate_experiment_id_rejected(tmp_path) -> None:
    _write(tmp_path / "a.json", make_valid_experiment())
    _write(tmp_path / "d.json", deep_copy(make_valid_experiment()))  # 同 ID

    repo = ExperimentsRepository(tmp_path)
    _, issues = repo.load_all()
    assert any("重复" in i.message and i.path == "experiment_id" for i in issues)


def test_load_or_raise_fails_closed_and_get_works(tmp_path) -> None:
    _write(tmp_path / "a.json", make_valid_experiment())
    repo = ExperimentsRepository(tmp_path)

    assert repo.get("py-web-demo").experiment_id == "py-web-demo"
    assert repo.get("not-there") is None
    assert list(repo.load_or_raise()) == ["py-web-demo"]

    _write(tmp_path / "bad.json", {"schema_version": "1.0"})  # 缺全部必填字段
    with pytest.raises(ExperimentValidationError):
        repo.load_or_raise()


def test_missing_directory_reported(tmp_path) -> None:
    repo = ExperimentsRepository(tmp_path / "does-not-exist")
    loaded, issues = repo.load_all()
    assert loaded == {}
    assert any("实验目录不存在" in i.message for i in issues)
