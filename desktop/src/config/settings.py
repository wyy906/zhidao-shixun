"""桌面助手配置"""
from dataclasses import dataclass, asdict
from pathlib import Path
import json


CONFIG_PATH = Path.home() / ".zd_shixun" / "desktop_config.json"


@dataclass
class DesktopSettings:
    backend_url: str = "http://localhost:8000/api"
    token: str = ""
    poll_interval_ms: int = 5000           # 轮询间隔：UIA 链路毫秒级返回，可高频跟随窗口切换
    overlay_enabled: bool = True            # 悬浮层总开关
    annotation_enabled: bool = True         # 标注显示开关
    bubble_enabled: bool = True             # 文字气泡开关（担心遮挡可以关掉）
    bubble_opacity: int = 70                # 气泡不透明度 30-100
    bubble_corner: str = "bottom-right"     # 默认放右下角，避免挡住右上角的内容
    capture_interval_ms: int = 5000         # 截图间隔
    # OCR
    ocr_enabled: bool = False
    # 视觉模型（预留）
    vision_api_url: str = ""
    vision_api_key: str = ""


def load_settings() -> DesktopSettings:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return DesktopSettings(**data)
        except Exception:
            pass
    s = DesktopSettings()
    save_settings(s)
    return s


def save_settings(s: DesktopSettings) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8"
    )
