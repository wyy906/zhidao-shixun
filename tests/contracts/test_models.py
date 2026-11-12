"""契约模型校验测试：三端共享契约的最小行为保证。"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from zhidao_contracts import (
    CONTRACT_VERSION,
    ContractSource,
    GuideLevel,
    GuideMessage,
    ScreenState,
    StepState,
    StepStatus,
    UiTarget,
    VerifyOutcome,
    VerifyRequest,
    VerifyResult,
)


def _target() -> UiTarget:
    return UiTarget(x=100, y=80, width=120, height=36, label="新建查询按钮", control_type="Button")


def test_screen_state_roundtrip() -> None:
    state = ScreenState(
        captured_at=datetime.now(timezone.utc),
        source=ContractSource.DESKTOP,
        window_title="MySQL Workbench",
        process_name="MySQLWorkbench.exe",
        targets=[_target()],
    )
    assert state.schema_version == CONTRACT_VERSION
    data = state.model_dump(mode="json")
    assert ScreenState.model_validate(data) == state


def test_step_state_defaults() -> None:
    state = StepState(experiment_id="exp-1", step_id="step-1", status=StepStatus.IN_PROGRESS)
    assert state.attempts == 0
    assert state.guide_level == GuideLevel.CONCISE
    assert state.schema_version == CONTRACT_VERSION


def test_verify_result_three_outcomes() -> None:
    for outcome in (VerifyOutcome.PASSED, VerifyOutcome.FAILED, VerifyOutcome.UNCERTAIN):
        result = VerifyResult(step_id="step-1", outcome=outcome, feedback="ok")
        assert result.outcome == outcome


def test_guide_level_four_levels() -> None:
    assert [int(level) for level in GuideLevel] == [1, 2, 3, 4]


def test_guide_message_with_targets() -> None:
    message = GuideMessage(
        step_id="step-2",
        level=GuideLevel.ANNOTATE,
        title="点击「新建查询」",
        content="在工具栏点击新建查询按钮，开始输入 SQL。",
        targets=[_target()],
        created_at=datetime.now(timezone.utc),
    )
    assert message.level == GuideLevel.ANNOTATE
    assert len(message.targets) == 1


def test_ui_target_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        UiTarget(x=0, y=0, width=10, height=10, label="x", confidence=1.5)
    with pytest.raises(ValidationError):
        UiTarget(x=0, y=0, width=10, height=10, label="x", confidence=-0.1)


def test_verify_request_carries_screen() -> None:
    request = VerifyRequest(
        experiment_id="exp-1",
        step_id="step-1",
        actual={"stdout": "Python 3.13.14"},
        screen=ScreenState(captured_at=datetime.now(timezone.utc), source=ContractSource.DESKTOP),
    )
    assert request.screen is not None
    assert request.screen.source == ContractSource.DESKTOP
