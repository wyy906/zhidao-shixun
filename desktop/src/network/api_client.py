"""后端 AI 指导接口客户端"""
from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


class AIBackendClient:
    def __init__(self, settings):
        self.base_url = settings.backend_url.rstrip("/")
        self.token = settings.token
        self._client = httpx.Client(timeout=180.0) if httpx else None

    def _api_base(self) -> str:
        """统一拼接后端 API 前缀，兼容用户是否填写 /api 后缀。

        无论用户填 http://localhost:8000 还是 http://localhost:8000/api，
        最终都拼成 http://localhost:8000/api/v1
        """
        url = self.base_url
        if url.endswith("/api"):
            return url + "/v1"
        # 用户可能填了 /api/v1 或更深路径，先剥离已有版本前缀
        for suffix in ("/api/v1", "/v1"):
            if url.endswith(suffix):
                return url
        return url + "/api/v1"

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    # ========== 自动登录 ==========
    def auto_login(self, username: str = "admin", password: str = "demo123") -> bool:
        """自动登录获取 JWT token。"""
        if not self._client:
            return False
        url = f"{self._api_base()}/auth/login"
        try:
            resp = self._client.post(url, json={"username": username, "password": password})
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token", "")
                return bool(self.token)
        except Exception:
            pass
        return False

    # ========== 实验（导入的实验步骤驱动指导） ==========
    def list_experiments(self) -> list[dict]:
        if not self._client or not self.token:
            return []
        try:
            resp = self._client.get(f"{self._api_base()}/experiments", headers=self._headers())
            if resp.status_code == 200:
                return resp.json() or []
        except Exception:
            pass
        return []

    def get_experiment(self, exp_id: int) -> dict | None:
        if not self._client or not self.token:
            return None
        try:
            resp = self._client.get(
                f"{self._api_base()}/experiments/{exp_id}", headers=self._headers()
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def start_experiment(self, exp_id: int) -> bool:
        if not self._client or not self.token:
            return False
        try:
            resp = self._client.post(
                f"{self._api_base()}/experiments/{exp_id}/start", headers=self._headers()
            )
            return resp.status_code == 200
        except Exception:
            return False

    def report_step(self, exp_id: int, step_index: int, completed: bool = True) -> bool:
        if not self._client or not self.token:
            return False
        try:
            resp = self._client.post(
                f"{self._api_base()}/experiments/{exp_id}/step",
                headers=self._headers(),
                json={"step_index": step_index, "completed": completed},
            )
            return resp.status_code == 200
        except Exception:
            return False

    def submit_experiment(self, exp_id: int) -> bool:
        if not self._client or not self.token:
            return False
        try:
            resp = self._client.post(
                f"{self._api_base()}/experiments/{exp_id}/submit", headers=self._headers()
            )
            return resp.status_code == 200
        except Exception:
            return False

    def request_screen_guide(
        self,
        image_b64: str,
        software_hint: str = "",
        step_index: int = 0,
        region: tuple[int, int] = (0, 0),
        image_size: tuple[int, int] = (0, 0),
        uia_elements: list[dict] | None = None,
        force_vision: bool = False,
    ) -> dict | None:
        """通用屏幕指导：上传窗口截图 + UIA 控件 → 后端匹配教程并返回屏幕坐标"""
        if not self._client or not image_b64:
            return None
        import base64 as _b64
        import json as _json

        url = f"{self._api_base()}/ai/screen-guide"
        try:
            raw = _b64.b64decode(image_b64)
            resp = self._client.post(
                url,
                files={"file": ("screen.jpg", raw, "image/jpeg")},
                data={
                    "software_hint": software_hint,
                    "step_index": str(step_index),
                    "region_left": str(int(region[0])),
                    "region_top": str(int(region[1])),
                    "image_width": str(int(image_size[0])),
                    "image_height": str(int(image_size[1])),
                    "uia_elements": _json.dumps(uia_elements or [], ensure_ascii=False),
                    "force_vision": "true" if force_vision else "false",
                },
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            return None
        return None

    def request_guide(
        self,
        experiment_id: int,
        current_step: int,
        screen_state: dict | None = None,
        context: dict | None = None,
    ) -> dict | None:
        """请求 AI 指导。失败返回 None（由调用方提示真实错误）"""
        if not self._client:
            return None
        url = f"{self._api_base()}/ai/guide"
        body = {
            "experiment_id": experiment_id,
            "current_step": current_step,
            "screen_state": screen_state,
            "context": context,
        }
        try:
            resp = self._client.post(url, json=body, headers=self._headers())
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                # token 过期 → 自动重新登录再试一次
                if self.auto_login():
                    resp2 = self._client.post(url, json=body, headers=self._headers())
                    if resp2.status_code == 200:
                        return resp2.json()
        except Exception:
            return None
        return None

    def close(self):
        if self._client:
            self._client.close()
