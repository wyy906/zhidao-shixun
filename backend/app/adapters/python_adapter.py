"""Python 在线实验适配器（Stub）

网页内部实验通过 API / Playwright 获取页面状态，
这里只实现最小接口——真实环境下应对接 Monaco Editor / 执行引擎。
"""
from app.adapters.base import BaseSoftwareAdapter, register_adapter


@register_adapter
class PythonWebAdapter(BaseSoftwareAdapter):
    software_key = "python"

    def locate_target(self, step, screen_state):
        """网页内部实验不使用屏幕悬浮层，不返回任何屏幕坐标。

        坐标只能由桌面端的真实 UIA / 视觉识别路径产出。
        """
        return None

    def validate_result(self, step, actual_result):
        if actual_result and "code_output" in actual_result:
            return {
                "passed": bool(actual_result.get("code_output")),
                "feedback": "代码已运行。" if actual_result.get("code_output") else "代码似乎没有输出。",
            }
        return {"passed": False, "feedback": "尚未检测到运行结果。"}
