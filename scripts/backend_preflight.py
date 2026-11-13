"""业务后端生产配置预检（只读，不打印任何密钥）

用途：上线前在业务服务器上检查 `.env` 是否满足生产要求，避免把开发配置带上线。

用法：
    python scripts/backend_preflight.py [--env-file PATH]

退出码：0=全部 PASS；1=存在 FAIL；2=无 FAIL 但有 WARN。
脚本只输出“检查项结论 / 长度 / 文件路径”，不回显令牌、密码或密钥内容。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

_WEAK_ADMIN_PASSWORDS = {
    "demo123",
    "admin",
    "admin123",
    "password",
    "123456",
    "change-me-please",
    "changeme",
}
_WEAK_JWT_MARKERS = ("change-me", "changeme", "secret", "please")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


@dataclass(frozen=True)
class Result:
    level: str
    message: str


def load_env(path: Path) -> dict[str, str]:
    """极简 .env 解析：KEY=VALUE，去掉注释/空行/成对引号，不做变量展开"""
    env: dict[str, str] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            env[key] = value
    return env


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_cors(raw: str) -> list[str]:
    """CORS_ORIGINS 支持 JSON 数组或逗号分隔；解析失败按空处理"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower()
    return host in _LOOPBACK_HOSTS


def evaluate(env: dict[str, str], base_dir: Path | None = None) -> list[Result]:
    """根据环境变量内容生成检查结论（纯函数，便于测试）"""
    base = base_dir or Path.cwd()
    results: list[Result] = []

    def add(level: str, message: str) -> None:
        results.append(Result(level, message))

    app_env = (env.get("APP_ENV") or "").strip()
    if app_env and app_env != "development":
        add(PASS, f"APP_ENV={app_env}")
    else:
        add(FAIL, "APP_ENV 必须为非 development 的生产值（如 production）")

    if _is_true(env.get("DEBUG")):
        add(FAIL, "DEBUG 必须为 false（生产会泄露堆栈信息）")
    else:
        add(PASS, "DEBUG 已关闭")

    jwt = (env.get("JWT_SECRET_KEY") or "").strip()
    lowered = jwt.lower()
    if len(jwt) < 32:
        add(FAIL, "JWT_SECRET_KEY 缺失或长度不足 32 字符")
    elif any(marker in lowered for marker in _WEAK_JWT_MARKERS):
        add(FAIL, "JWT_SECRET_KEY 含默认/占位标记，必须替换为随机值")
    else:
        add(PASS, f"JWT_SECRET_KEY 长度 {len(jwt)}，无占位标记")

    admin_pwd = (env.get("ADMIN_PASSWORD") or "").strip()
    if not admin_pwd:
        add(FAIL, "ADMIN_PASSWORD 未设置（首次启动会创建弱口令管理员）")
    elif admin_pwd.lower() in _WEAK_ADMIN_PASSWORDS:
        add(FAIL, "ADMIN_PASSWORD 仍为默认/弱口令")
    elif len(admin_pwd) < 12:
        add(FAIL, f"ADMIN_PASSWORD 长度 {len(admin_pwd)}，建议至少 12 字符")
    else:
        add(PASS, f"ADMIN_PASSWORD 长度 {len(admin_pwd)}")

    if _is_true(env.get("ALLOW_PUBLIC_REGISTER")):
        add(WARN, "ALLOW_PUBLIC_REGISTER=true：生产默认应关闭公开注册")
    else:
        add(PASS, "公开注册已关闭")

    database_url = (env.get("DATABASE_URL") or "").strip()
    if not database_url:
        add(FAIL, "DATABASE_URL 未设置")
    elif database_url.startswith("sqlite"):
        add(WARN, "DATABASE_URL 使用 SQLite：单机演示可用，多实例/生产建议 PostgreSQL")
    else:
        add(PASS, "DATABASE_URL 非 SQLite")

    if _is_true(env.get("DB_AUTO_CREATE")):
        add(FAIL, "DB_AUTO_CREATE=true：生产必须先 alembic upgrade head，禁止自动建表")
    else:
        add(PASS, "未启用自动建表（需先执行 alembic upgrade head）")

    cors = _parse_cors(env.get("CORS_ORIGINS") or "")
    if not cors:
        add(FAIL, "CORS_ORIGINS 为空（前端将无法访问 API）")
    elif any(origin == "*" for origin in cors):
        add(FAIL, "CORS_ORIGINS 含通配符 *，生产必须写明确域名")
    else:
        add(PASS, f"CORS_ORIGINS 已限定 {len(cors)} 个来源")

    # 未显式关闭时按应用默认值 true 处理，避免漏检沙箱配置
    if _is_true(env.get("CODE_EXECUTION_ENABLED", "true")):
        sandbox_url = (env.get("SANDBOX_MANAGER_URL") or "").strip()
        token = (env.get("SANDBOX_MANAGER_TOKEN") or "").strip()
        if not sandbox_url:
            add(FAIL, "CODE_EXECUTION_ENABLED=true 但未配置 SANDBOX_MANAGER_URL")
        else:
            parsed = urlparse(sandbox_url)
            if parsed.scheme == "https":
                add(PASS, "沙箱管理器使用 HTTPS")
            elif parsed.scheme == "http" and _is_loopback_url(sandbox_url):
                if _is_true(env.get("SANDBOX_ALLOW_INSECURE_HTTP")):
                    add(WARN, "沙箱管理器为回环明文 HTTP（仅限本机开发）")
                else:
                    add(FAIL, "回环明文 HTTP 未显式开启 SANDBOX_ALLOW_INSECURE_HTTP")
            else:
                add(FAIL, "沙箱管理器必须使用 HTTPS（非回环地址禁止明文）")
        if len(token) < 32:
            add(FAIL, "SANDBOX_MANAGER_TOKEN 缺失或长度不足 32 字符")
        else:
            add(PASS, f"SANDBOX_MANAGER_TOKEN 长度 {len(token)}")

        ca_file = (env.get("SANDBOX_MANAGER_CA_FILE") or "").strip()
        if ca_file:
            ca_path = Path(ca_file)
            if not ca_path.is_absolute():
                ca_path = base / ca_path
            if ca_path.is_file():
                add(PASS, "沙箱 CA 文件存在")
            else:
                add(FAIL, "沙箱 CA 文件不存在或不是文件")
        else:
            add(WARN, "未配置 SANDBOX_MANAGER_CA_FILE（生产建议固定 CA）")

        cert = (env.get("SANDBOX_MANAGER_CLIENT_CERT") or "").strip()
        key = (env.get("SANDBOX_MANAGER_CLIENT_KEY") or "").strip()
        if bool(cert) != bool(key):
            add(FAIL, "客户端证书与私钥必须同时配置")
        elif cert:
            cert_path = Path(cert)
            key_path = Path(key)
            if not cert_path.is_absolute():
                cert_path = base / cert_path
            if not key_path.is_absolute():
                key_path = base / key_path
            if cert_path.is_file() and key_path.is_file():
                add(PASS, "双向 TLS 客户端证书与私钥存在")
            else:
                add(FAIL, "双向 TLS 客户端证书或私钥文件不存在")
        else:
            add(WARN, "未配置双向 TLS 客户端证书（生产建议启用 mTLS）")
    else:
        add(PASS, "代码执行已关闭（/code/run 将返回 503）")

    ai_values = [
        env.get("AI_API_BASE_URL") or "",
        env.get("AI_API_KEY") or "",
        env.get("AI_VISION_MODEL") or "",
    ]
    filled = sum(1 for value in ai_values if value.strip())
    if 0 < filled < 3:
        add(WARN, "AI_* 配置不完整（三项需同时填写，否则整组不生效）")
    elif filled == 3:
        add(PASS, "AI_* 三项齐全")
    else:
        add(PASS, "未配置 AI_*（仅使用教程关键词路径）")

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="业务后端生产配置预检（只读）")
    parser.add_argument(
        "--env-file",
        default=str(Path(__file__).resolve().parents[1] / "backend" / ".env"),
        help="生产环境变量文件路径",
    )
    args = parser.parse_args(argv)

    env_path = Path(args.env_file)
    print(f"== 预检 {env_path} ==")
    if not env_path.is_file():
        print(f"FAIL   环境变量文件不存在：{env_path}")
        print("\n结果：PASS=0 FAIL=1 WARN=0")
        return 1

    results = evaluate(load_env(env_path), env_path.parent)
    for item in results:
        print(f"{item.level:<6} {item.message}")

    passed = sum(1 for item in results if item.level == PASS)
    failed = sum(1 for item in results if item.level == FAIL)
    warned = sum(1 for item in results if item.level == WARN)
    print(f"\n结果：PASS={passed} FAIL={failed} WARN={warned}")
    if failed:
        return 1
    if warned:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
