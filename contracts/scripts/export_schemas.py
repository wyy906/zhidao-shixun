"""导出契约 JSON Schema 到 contracts/schemas/。

- 用途：web 端类型对齐 / 代码生成的基线，以及根级 tests/contracts/test_schema_export.py 的漂移检测。
- 用法：python contracts/scripts/export_schemas.py
- 契约模型或版本变化后必须重新运行并提交产物。
"""

import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

sys.path.insert(0, str(SRC_DIR))

from zhidao_contracts import CONTRACT_MODELS, CONTRACT_VERSION  # noqa: E402


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for model in CONTRACT_MODELS:
        doc = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "contract_version": CONTRACT_VERSION,
            **model.model_json_schema(),
        }
        out_path = SCHEMA_DIR / f"{model.__name__}.schema.json"
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.relative_to(SCHEMA_DIR.parents[2])}")


if __name__ == "__main__":
    main()
