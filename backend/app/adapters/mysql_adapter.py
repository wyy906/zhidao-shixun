"""MySQL Workbench 适配器

真实环境下应该通过：
- Windows UI Automation 读取窗口控件树
- 或 OCR + 视觉模型识别屏幕文字
- 或 pywinauto 操作 Window

坐标只能由桌面端的真实 UIA / 视觉识别路径产出，此处不返回任何屏幕坐标。
"""
from app.adapters.base import BaseSoftwareAdapter, register_adapter


@register_adapter
class MySQLWorkbenchAdapter(BaseSoftwareAdapter):
    software_key = "mysql"

    def locate_target(self, step, screen_state):
        """桌面端 MySQL 实验的坐标由真实 UIA / 视觉识别产出，适配器不返回假坐标。"""
        return None

    def validate_result(self, step, actual_result):
        """根据操作结果判断"""
        if not actual_result:
            return {"passed": False, "feedback": "尚未检测到操作结果。"}
        if actual_result.get("grid_rows") or actual_result.get("query_success"):
            return {"passed": True, "feedback": "SQL 执行成功！"}
        return {"passed": False, "feedback": "操作可能未成功完成。请检查错误消息。"}
