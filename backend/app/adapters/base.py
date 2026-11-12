"""专业软件适配器基类 + 注册表"""
from abc import ABC, abstractmethod
from typing import Any


class BaseSoftwareAdapter(ABC):
    """所有专业软件适配器的共同接口

    适配器负责：
    1. 识别自己对应的软件类型（software_key）
    2. 从屏幕状态中定位目标控件（locate_target）
    3. 验证某一步操作结果（validate_result）
    4. 返回软件的统一状态描述（get_state）
    """

    software_key: str = "base"   # 子类必须覆盖

    @abstractmethod
    def locate_target(self, step: Any, screen_state: dict | None) -> dict | None:
        """
        从屏幕状态中定位当前步骤的目标控件。
        返回 None 表示无法定位（引擎应降级为纯文字指导）。

        返回格式示例：
        {
            "x": 420, "y": 280,
            "width": 120, "height": 40,
            "label": "Create Schema 按钮"
        }
        """

    @abstractmethod
    def validate_result(self, step: Any, actual_result: dict | None) -> dict:
        """
        验证实际操作结果是否符合步骤预期。
        返回 {"passed": bool, "feedback": str}
        """

    def get_state(self) -> dict:
        """可选：返回适配器能提供的软件状态快照"""
        return {"adapter": self.software_key, "available": True}


# ============ 注册表 ============
_REGISTRY: dict[str, type[BaseSoftwareAdapter]] = {}


def register_adapter(cls: type[BaseSoftwareAdapter]):
    """装饰器：将适配器注册到全局注册表"""
    _REGISTRY[cls.software_key] = cls
    return cls


def get_adapter(key: str) -> BaseSoftwareAdapter | None:
    """根据 software key 获取适配器实例（首期复用单例）"""
    cls = _REGISTRY.get(key) or _REGISTRY.get(key.lower())
    if cls:
        return cls()
    return None


def list_adapters() -> list[str]:
    return list(_REGISTRY.keys())
