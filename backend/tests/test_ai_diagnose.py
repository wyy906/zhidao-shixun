"""AI 路由：验证器与诊断接口接线"""
from app.api.v1.routers import ai as ai_router
from app.models import ExperimentStep
from app.schemas import DiagnoseResponse


def _fake_diagnoser(result):
    class FakeDiagnoser:
        def __init__(self, *args, **kwargs):
            pass

        def diagnose(self, **kwargs):
            return result

    return FakeDiagnoser


def test_verify_endpoint_uses_python_adapter(client, imported_experiment):
    exp_id = imported_experiment["id"]
    step_id = imported_experiment["steps"][0]["id"]
    resp = client.post(
        f"/api/v1/ai/verify/{exp_id}/{step_id}",
        json={"actual_result": {"code_output": "hello"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["passed"] is True
    assert body["confidence"] >= 0.5


def test_verify_endpoint_missing_step_returns_404(client, imported_experiment):
    resp = client.post(
        f"/api/v1/ai/verify/{imported_experiment['id']}/999999",
        json={"actual_result": {"code_output": "hello"}},
    )
    assert resp.status_code == 404


def test_diagnose_endpoint_returns_model_result(
    client, student_headers, imported_experiment, db_session, monkeypatch
):
    exp_id = imported_experiment["id"]
    step = db_session.query(ExperimentStep).filter_by(experiment_id=exp_id).first()
    monkeypatch.setattr(
        ai_router,
        "ErrorDiagnoser",
        _fake_diagnoser(DiagnoseResponse(
            error_type="缩进错误",
            suggestion="把 print 缩进 4 个空格",
            possible_causes=["缩进不一致"],
        )),
    )
    resp = client.post(
        f"/api/v1/ai/diagnose/{exp_id}",
        json={"step_id": step.id, "error": "IndentationError"},
        headers=student_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error_type"] == "缩进错误"
    assert body["suggestion"] == "把 print 缩进 4 个空格"


def test_diagnose_endpoint_falls_back_to_step_info(
    client, student_headers, imported_experiment, db_session, monkeypatch
):
    exp_id = imported_experiment["id"]
    step = db_session.query(ExperimentStep).filter_by(experiment_id=exp_id).first()
    monkeypatch.setattr(ai_router, "ErrorDiagnoser", _fake_diagnoser(None))
    resp = client.post(
        f"/api/v1/ai/diagnose/{exp_id}",
        json={"step_id": step.id, "error": "没有反应"},
        headers=student_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert step.expected_result in body["suggestion"]
    assert body["possible_causes"]


def test_diagnose_endpoint_unknown_experiment_returns_404(
    client, student_headers, monkeypatch
):
    monkeypatch.setattr(ai_router, "ErrorDiagnoser", _fake_diagnoser(None))
    resp = client.post(
        "/api/v1/ai/diagnose/999999",
        json={"error": "x"},
        headers=student_headers,
    )
    assert resp.status_code == 404
