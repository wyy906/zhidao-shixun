"""鉴权与测试数据库隔离"""
from app.db import session as db_session_module


# ---------------------------------------------------------------------------
# 隔离性：先证明测试没有连接到项目真实数据库
# ---------------------------------------------------------------------------
def test_app_engine_is_not_real_database():
    """全局 engine 必须指向一次性临时库，不能是项目真实库"""
    url = str(db_session_module.engine.url)
    print(f"\n[隔离检查] 全局 engine 实际连接: {url}")
    assert "zd_shixun.db" not in url, f"测试连接到了真实数据库: {url}"
    assert "zd_shixun_test_guard_" in url, f"未使用隔离数据库: {url}"


def test_each_test_uses_isolated_sqlite_file(db_engine, users, client):
    """每个测试的数据库是 tmp_path 下的独立文件，且已有预置用户"""
    url = str(db_engine.url)
    print(f"[隔离检查] 本次测试库连接: {url}")
    assert url.endswith("test.db"), url
    assert "zd_shixun.db" not in url
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401
    # 预置用户确实写进了这个临时库
    assert len(users) == 3


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------
def test_login_success_returns_token(client, users):
    resp = client.post("/api/v1/auth/login",
                       json={"username": users["teacher"]["username"],
                             "password": users["teacher"]["password"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == users["teacher"]["username"]
    assert body["user"]["role"] == "teacher"


def test_login_wrong_password_returns_401(client, users):
    resp = client.post("/api/v1/auth/login",
                       json={"username": users["student"]["username"], "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_unknown_user_returns_401(client, users):
    resp = client.post("/api/v1/auth/login",
                       json={"username": "no-such-user", "password": "whatever"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 受保护接口
# ---------------------------------------------------------------------------
def test_protected_endpoint_without_token_returns_401(client, users):
    resp = client.get("/api/v1/experiments")
    assert resp.status_code == 401


def test_me_without_token_returns_401(client, users):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_token_returns_current_user(client, users, teacher_headers):
    resp = client.get("/api/v1/auth/me", headers=teacher_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == users["teacher"]["username"]


def test_student_cannot_create_experiment(client, users, student_headers):
    resp = client.post("/api/v1/experiments", json={"title": "越权实验"}, headers=student_headers)
    assert resp.status_code == 403


def test_teacher_can_create_experiment(client, users, teacher_headers):
    resp = client.post("/api/v1/experiments", json={"title": "教师创建实验"}, headers=teacher_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "教师创建实验"


# ---------------------------------------------------------------------------
# 响应中不得泄露密码哈希
# ---------------------------------------------------------------------------
def test_login_response_has_no_hashed_password(client, users):
    resp = client.post("/api/v1/auth/login",
                       json={"username": users["student"]["username"],
                             "password": users["student"]["password"]})
    assert "hashed_password" not in resp.text
    assert "$2b$" not in resp.text


def test_user_info_has_no_hashed_password(client, users, student_headers):
    resp = client.get("/api/v1/auth/me", headers=student_headers)
    assert "hashed_password" not in resp.text
