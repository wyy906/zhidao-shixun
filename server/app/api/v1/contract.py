"""跨端契约版本查询：desktop / web 启动时校验兼容性用。"""

from fastapi import APIRouter

from zhidao_contracts import CONTRACT_MODELS, CONTRACT_VERSION

router = APIRouter(tags=["contract"])


@router.get("/contract/version")
def contract_version() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "models": [model.__name__ for model in CONTRACT_MODELS],
        "note": "JSON Schema 基线见仓库 contracts/schemas/ 目录",
    }
