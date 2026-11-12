"""数据库初始化（可选）

在 backend 目录下运行：
    python -m backend.scripts.init_db   或在项目根执行 python scripts/init_db.py

只做两件事：
- 建表（若不存在）
- 数据库里没有任何用户时创建管理员账号（账号见 backend/.env 的 ADMIN_USERNAME / ADMIN_PASSWORD）

不再插入任何演示实验、演示学生 —— 实验内容由老师后期导入。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models import User


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password),
                real_name="管理员",
                role="teacher",
            ))
            db.commit()
            print(f"已创建管理员账号：{settings.admin_username}")
        else:
            print("已存在用户，跳过管理员创建")
    finally:
        db.close()
    print("数据库初始化完成（未写入任何演示实验）")


if __name__ == "__main__":
    main()
