"""契约 JSON Schema 漂移检测：schemas/ 下的提交产物必须与模型一致。

模型或版本变化后，运行 `python contracts/scripts/export_schemas.py` 重新导出并提交。
"""

import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas"
SRC_DIR = REPO_ROOT / "contracts" / "src"

sys.path.insert(0, str(SRC_DIR))

from zhidao_contracts import CONTRACT_MODELS, CONTRACT_VERSION  # noqa: E402


def _regenerated(model) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "contract_version": CONTRACT_VERSION,
        **model.model_json_schema(),
    }


def test_every_contract_model_has_exported_schema() -> None:
    for model in CONTRACT_MODELS:
        path = SCHEMA_DIR / f"{model.__name__}.schema.json"
        assert path.exists(), f"缺少契约 Schema：{path.name}，请运行 python contracts/scripts/export_schemas.py"


def test_exported_schemas_match_models() -> None:
    for model in CONTRACT_MODELS:
        path = SCHEMA_DIR / f"{model.__name__}.schema.json"
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert committed == _regenerated(model), (
            f"{path.name} 与模型不一致：契约发生漂移，请重新运行 python contracts/scripts/export_schemas.py 并提交"
        )


def test_contract_version_matches_package_metadata() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "contracts" / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == CONTRACT_VERSION
