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
        if not actual_result:
            return {"passed": False, "feedback": "尚未检测到运行结果。", "confidence": 0.4}
        # 桌面端 UIA / 视觉链路会直接给出显式信号，优先采信
        if isinstance(actual_result.get("passed"), bool):
            passed = actual_result["passed"]
            return {
                "passed": passed,
                "feedback": actual_result.get("feedback") or (
                    "代码已成功运行。" if passed else "代码运行未通过，请检查输出。"
                ),
                "confidence": 0.9,
            }
        if actual_result.get("failed") is True:
            return {
                "passed": False,
                "feedback": actual_result.get("feedback") or "代码运行失败，请查看错误信息。",
                "confidence": 0.8,
            }
        # 网页端实验：以是否有代码输出作为最小判据
        if "code_output" in actual_result:
            output = actual_result.get("code_output")
            passed = bool(str(output or "").strip())
            return {
                "passed": passed,
                "feedback": "代码已运行。" if passed else "代码似乎没有输出。",
                "confidence": 0.8 if passed else 0.5,
            }
        return {"passed": False, "feedback": "尚未检测到运行结果。", "confidence": 0.4}
