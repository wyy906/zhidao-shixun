"""测试夹具工厂：生成最小合法实验定义字典（仅供测试，不构成仓库内置演示实验）。"""

import copy
from typing import Any


def make_step(step_id: str = "s1", **overrides: Any) -> dict[str, Any]:
    step: dict[str, Any] = {
        "step_id": step_id,
        "title": f"步骤 {step_id}",
        "learning_goal": "掌握本步骤的训练目标",
        "student_action": "在编辑器中完成本步骤操作并运行",
        "expected_state": {
            "description": "操作完成后的预期状态描述",
            "artifacts": ["运行输出"],
        },
        "verifier": {"type": "python_exit_code_zero", "params": {}},
        "depends_on": [],
        "preconditions": ["代码编辑器已打开"],
        "common_errors": ["常见错误示例"],
        "recovery_hints": ["恢复建议示例"],
        "guide_hint": 1,
    }
    step.update(overrides)
    return step


def make_valid_experiment(**overrides: Any) -> dict[str, Any]:
    """两个步骤的 python_web 实验：s1 ← s2（s2 依赖 s1）。"""
    data: dict[str, Any] = {
        "schema_version": "1.1",
        "experiment_id": "py-web-demo",
        "title": "Python 网页实验（测试用）",
        "description": "用于单元测试的最小合法实验定义，不是正式实验内容",
        "category": "测试",
        "version": "1.0",
        "environment": "python_web",
        "adapter": {
            "adapter_id": "python_web",
            "capabilities": ["read_stdout", "read_exit_code"],
        },
        "prerequisites": ["Python 基础语法"],
        "steps": [
            make_step("s1"),
            make_step(
                "s2",
                depends_on=["s1"],
                verifier={"type": "python_stdout_contains", "params": {"text": "hello"}},
            ),
        ],
        "meta": {"estimated_minutes": 30, "difficulty": "beginner"},
    }
    data.update(overrides)
    return data


def deep_copy(data: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(data)
