"""后端托管前端构建产物（mount_frontend）的行为测试"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


@pytest.fixture()
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<html><body>SPA-INDEX</body></html>", encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text("console.log('app');", encoding="utf-8")
    return dist


def _make_app(dist: Path) -> TestClient:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    assert mount_frontend_with(app, dist) is True
    return TestClient(app)


def mount_frontend_with(app: FastAPI, dist: Path) -> bool:
    import app.main as main_mod

    original = main_mod.mount_frontend

    def patched(application: FastAPI) -> bool:
        import os

        old = os.environ.get("ZD_FRONTEND_DIST")
        os.environ["ZD_FRONTEND_DIST"] = str(dist)
        try:
            return original(application)
        finally:
            if old is None:
                os.environ.pop("ZD_FRONTEND_DIST", None)
            else:
                os.environ["ZD_FRONTEND_DIST"] = old

    return patched(app)


def test_serves_index_and_assets(dist_dir: Path):
    client = _make_app(dist_dir)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SPA-INDEX" in resp.text

    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_spa_fallback_returns_index(dist_dir: Path):
    client = _make_app(dist_dir)
    resp = client.get("/student/workbench/1")
    assert resp.status_code == 200
    assert "SPA-INDEX" in resp.text


def test_api_routes_take_priority(dist_dir: Path):
    client = _make_app(dist_dir)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_path_traversal_falls_back_to_index(dist_dir: Path):
    client = _make_app(dist_dir)
    outside = dist_dir.parent / "secret.txt"
    outside.write_text("SECRET", encoding="utf-8")
    resp = client.get("/../secret.txt")
    # 星号路径不会命中外部文件；无论回退还是 404，绝不能返回外部内容
    assert b"SECRET" not in resp.content


def test_returns_false_without_dist(tmp_path: Path):
    app = FastAPI()
    empty = tmp_path / "no-dist"
    empty.mkdir()
    assert mount_frontend_with(app, empty) is False
