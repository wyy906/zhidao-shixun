"""验证测试运行时不读取真实 backend/.env"""
import os
from pathlib import Path

from app.core.config import Settings, settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
REAL_ENV_FILE = BACKEND_DIR / ".env"


def test_env_file_is_not_real_dotenv():
    """当前配置使用的 env 文件必须是不存在的临时文件，而不是 backend/.env"""
    env_file = Path(str(settings.model_config["env_file"]))
    print(f"\n[env 隔离检查] 实际 env 文件: {env_file}")
    assert env_file != REAL_ENV_FILE
    assert env_file.name == "no-such-test.env"
    assert not env_file.exists()


def test_env_file_override_is_honored(tmp_path):
    """ZD_ENV_FILE 指定的文件会被读取（证明机制生效）"""
    sentinel = tmp_path / "sentinel.env"
    sentinel.write_text("APP_NAME=sentinel-app\nAI_API_KEY=sentinel-key\n", encoding="utf-8")

    loaded = Settings(_env_file=str(sentinel))
    assert loaded.app_name == "sentinel-app"
    assert loaded.ai_api_key == "sentinel-key"


def test_missing_env_file_does_not_fall_back_to_real_dotenv(tmp_path):
    """指向不存在的文件时使用代码默认值，不会回退到 backend/.env"""
    missing = tmp_path / "definitely-missing.env"
    assert not missing.exists()

    loaded = Settings(_env_file=str(missing))
    assert loaded.app_name == "智导实训"
    assert loaded.ai_api_key == ""
    # DATABASE_URL 来自测试设置的环境变量，且指向临时库，而不是 .env 里的真实库
    assert loaded.database_url == os.environ["DATABASE_URL"]
    assert "zd_shixun.db" not in loaded.database_url


def test_real_dotenv_untouched():
    """本用例只做存在性检查，绝不读取或改写用户本地 .env"""
    if REAL_ENV_FILE.exists():
        # 只取大小与修改时间，不读取内容
        st = REAL_ENV_FILE.stat()
        print(f"[env 隔离检查] 真实 .env 存在但未被读取，size={st.st_size}")
    assert os.environ.get("ZD_ENV_FILE", "").endswith("no-such-test.env")
