"""实验进度：开始、推进、完成、提交与隔离"""
from app.models import ExperimentProgress


def test_start_experiment(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    resp = client.post(f"/api/v1/experiments/{exp_id}/start", headers=student_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "in_progress"


def test_get_progress_after_start(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    client.post(f"/api/v1/experiments/{exp_id}/start", headers=student_headers)

    resp = client.get(f"/api/v1/progress/{exp_id}", headers=student_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["experiment_id"] == exp_id
    assert body["status"] == "in_progress"
    assert body["completed_steps"] == 0
    assert body["started_at"]


def test_progress_before_start_returns_404(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    assert client.get(f"/api/v1/progress/{exp_id}", headers=student_headers).status_code == 404


def test_advance_steps(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    client.post(f"/api/v1/experiments/{exp_id}/start", headers=student_headers)

    first = client.post(f"/api/v1/experiments/{exp_id}/step",
                        json={"step_index": 0, "completed": True}, headers=student_headers)
    assert first.status_code == 200
    assert first.json()["completed_steps"] == 1

    second = client.post(f"/api/v1/experiments/{exp_id}/step",
                         json={"step_index": 1, "completed": True}, headers=student_headers)
    assert second.status_code == 200
    assert second.json()["current_step"] == 1
    assert second.json()["completed_steps"] == 2


def test_complete_last_step(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    client.post(f"/api/v1/experiments/{exp_id}/start", headers=student_headers)
    total = len(imported_experiment["steps"])

    resp = client.post(f"/api/v1/experiments/{exp_id}/step",
                       json={"step_index": total - 1, "completed": True}, headers=student_headers)
    assert resp.status_code == 200
    assert resp.json()["completed_steps"] == total


def test_submit_experiment_sets_completed(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    client.post(f"/api/v1/experiments/{exp_id}/start", headers=student_headers)
    total = len(imported_experiment["steps"])

    resp = client.post(f"/api/v1/experiments/{exp_id}/submit", headers=student_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    progress = client.get(f"/api/v1/progress/{exp_id}", headers=student_headers).json()
    assert progress["status"] == "completed"
    assert progress["completed_steps"] == total
    assert progress["completed_at"] is not None


def test_submit_without_start_returns_400(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    assert client.post(f"/api/v1/experiments/{exp_id}/submit", headers=student_headers).status_code == 400


def test_progress_isolated_between_students(client, users, student_headers, student2_headers,
                                            imported_experiment, db_session):
    exp_id = imported_experiment["id"]
    client.post(f"/api/v1/experiments/{exp_id}/start", headers=student_headers)
    client.post(f"/api/v1/experiments/{exp_id}/step",
                json={"step_index": 0, "completed": True}, headers=student_headers)

    # 学生乙没有开始该实验
    assert client.get(f"/api/v1/progress/{exp_id}", headers=student2_headers).status_code == 404

    client.post(f"/api/v1/experiments/{exp_id}/start", headers=student2_headers)
    second = client.get(f"/api/v1/progress/{exp_id}", headers=student2_headers).json()
    assert second["completed_steps"] == 0

    db_session.expire_all()
    rows = db_session.query(ExperimentProgress).filter_by(experiment_id=exp_id).all()
    assert len(rows) == 2
    assert {r.user_id for r in rows} == {users["student"]["id"], users["student2"]["id"]}


def test_step_index_out_of_range_returns_400(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    client.post(f"/api/v1/experiments/{exp_id}/start", headers=student_headers)
    total = len(imported_experiment["steps"])

    too_large = client.post(f"/api/v1/experiments/{exp_id}/step",
                            json={"step_index": total, "completed": True}, headers=student_headers)
    assert too_large.status_code == 400

    negative = client.post(f"/api/v1/experiments/{exp_id}/step",
                           json={"step_index": -1, "completed": True}, headers=student_headers)
    assert negative.status_code == 400


def test_step_on_unknown_experiment_returns_404(client, users, student_headers):
    resp = client.post("/api/v1/experiments/999999/step",
                       json={"step_index": 0, "completed": True}, headers=student_headers)
    assert resp.status_code == 404


def test_start_unknown_experiment_returns_404(client, users, student_headers):
    assert client.post("/api/v1/experiments/999999/start", headers=student_headers).status_code == 404
