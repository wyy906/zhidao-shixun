"""认证路由"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, require_roles
from app.core.config import settings
from app.core.security import hash_password, verify_password, create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas import UserLogin, UserRegister, TokenResponse, UserInfo

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """账号密码登录（账号不存在直接报错，不再自动创建）"""
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在")
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "密码错误")

    token = create_access_token(user.id, user.role)
    return TokenResponse(token=token, user=UserInfo.model_validate(user))


@router.post("/register", response_model=UserInfo)
def register(
    data: UserRegister,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """注册账号

    - 生产/默认配置（allow_public_register=False）：仅管理员可创建账号
    - 开发环境可开启公开注册（allow_public_register=True）
    """
    if not settings.allow_public_register:
        # 非公开注册：必须登录且为管理员/教师
        if not current_user or current_user.role not in ("teacher", "admin"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "公开注册已关闭，请联系管理员创建账号",
            )

    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已存在")
    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        real_name=data.real_name,
        role=data.role if data.role in ("student", "teacher") else "student",
        class_name=data.class_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserInfo.model_validate(user)


@router.get("/me", response_model=UserInfo)
def me(current_user: User = Depends(get_current_user)):
    return UserInfo.model_validate(current_user)
