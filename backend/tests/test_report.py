"""实验报告：保存、更新、查询、提交、隔离与清理

注意：报告接口实际位于 app/api/v1/routers/experiments.py（不存在独立的 report.py）。
"""
from app.models import ExperimentReport


def _save(client, headers, exp_id, **fields):
    return client.put(f"/api/v1/experiments/{exp_id}/report", json=fields, headers=headers)


def test_student_save_report(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    resp = _save(client, student_headers, exp_id, purpose="实验目的", result="实验结果")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purpose"] == "实验目的"
    assert body["result"] == "实验结果"
    assert body["submitted"] is False


def test_student_update_report(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    first = _save(client, student_headers, exp_id, purpose="初稿")
    assert first.status_code == 200

    second = _save(client, student_headers, exp_id, purpose="修订稿", summary="总结")
    assert second.status_code == 200
    assert second.json()["purpose"] == "修订稿"
    assert second.json()["summary"] == "总结"
    assert second.json()["id"] == first.json()["id"], "更新报告不应新建第二条记录"


def test_student_get_report(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    _save(client, student_headers, exp_id, purpose="目的")
    resp = client.get(f"/api/v1/experiments/{exp_id}/report", headers=student_headers)
    assert resp.status_code == 200
    assert resp.json()["purpose"] == "目的"


def test_get_report_without_any_report_returns_404(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    assert client.get(f"/api/v1/experiments/{exp_id}/report", headers=student_headers).status_code == 404


def test_student_submit_report(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    _save(client, student_headers, exp_id, purpose="目的", result="结果")
    resp = client.post(f"/api/v1/experiments/{exp_id}/report/submit", headers=student_headers)
    assert resp.status_code == 200
    assert resp.json()["submitted"] is True

    got = client.get(f"/api/v1/experiments/{exp_id}/report", headers=student_headers).json()
    assert got["submitted"] is True


def test_submit_report_without_content_returns_400(client, users, student_headers, imported_experiment):
    exp_id = imported_experiment["id"]
    resp = client.post(f"/api/v1/experiments/{exp_id}/report/submit", headers=student_headers)
    assert resp.status_code == 400


def test_report_isolated_between_students(client, users, student_headers, student2_headers,
                                          imported_experiment, db_session):
    exp_id = imported_experiment["id"]
    _save(client, student_headers, exp_id, purpose="甲的报告")
    _save(client, student2_headers, exp_id, purpose="乙的报告")

    first = client.get(f"/api/v1/experiments/{exp_id}/report", headers=student_headers).json()
    second = client.get(f"/api/v1/experiments/{exp_id}/report", headers=student2_headers).json()
    assert first["purpose"] == "甲的报告"
    assert second["purpose"] == "乙的报告"
    assert first["id"] != second["id"]

    db_session.expire_all()
    assert db_session.query(ExperimentReport).count() == 2


def test_teacher_has_no_endpoint_to_read_student_report(client, users, teacher_headers,
                                                        student_headers, imported_experiment):
    """现状：报告接口只返回「当前登录用户自己的」报告，没有教师查看/批阅学生报告的接口"""
    exp_id = imported_experiment["id"]
    _save(client, student_headers, exp_id, purpose="学生报告")
    resp = client.get(f"/api/v1/experiments/{exp_id}/report", headers=teacher_headers)
    assert resp.status_code == 404, "若此断言失败，说明已新增教师查看报告的接口，请同步更新用例"


def test_report_deleted_with_experiment(client, users, teacher_headers, student_headers,
                                        imported_experiment, db_session):
    exp_id = imported_experiment["id"]
    _save(client, student_headers, exp_id, purpose="待清理报告")
    db_session.expire_all()
    assert db_session.query(ExperimentReport).count() == 1

    assert client.delete(f"/api/v1/experiments/{exp_id}", headers=teacher_headers).status_code == 200

    db_session.expire_all()
    assert db_session.query(ExperimentReport).count() == 0


def test_report_on_unknown_experiment_returns_404(client, users, student_headers):
    resp = _save(client, student_headers, 999999, purpose="不存在")
    assert resp.status_code == 404
