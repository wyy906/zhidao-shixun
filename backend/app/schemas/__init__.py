"""Pydantic Schemas — 请求 / 响应契约"""
from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, ConfigDict, EmailStr


# ========== 用户 / 鉴权 ==========
class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str
    real_name: Optional[str] = None
    role: str = "student"
    class_name: Optional[str] = None


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: Optional[str] = None
    role: str
    class_name: Optional[str] = None


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserInfo


# ========== 实验 ==========
class ExperimentBase(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[str] = None
    software: Optional[str] = None
    prerequisites: Optional[List[str]] = None
    criteria: Optional[List[str]] = None
    status: str = "draft"
    deadline: Optional[datetime] = None


class ExperimentCreate(ExperimentBase):
    pass


class ExperimentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    software: Optional[str] = None
    prerequisites: Optional[List[str]] = None
    criteria: Optional[List[str]] = None
    status: Optional[str] = None
    deadline: Optional[datetime] = None


class ExperimentStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_index: int
    title: str
    instruction: Optional[str] = None
    expected_result: Optional[str] = None
    common_errors: Optional[List[str]] = None
    # 桌面助手定位该步骤目标窗口/控件所需的信息
    adapter_hint: Optional[dict] = None


class ExperimentStepImport(BaseModel):
    """导入用的步骤定义"""
    title: str
    instruction: Optional[str] = None
    expected_result: Optional[str] = None
    common_errors: Optional[List[str]] = None
    adapter: Optional[dict] = None


class ExperimentImportIn(BaseModel):
    """导入实验（JSON）"""
    version: int = 1
    overwrite: bool = False          # 同标题实验存在时是否覆盖
    experiment: ExperimentCreate
    steps: List[ExperimentStepImport] = []


class StepProgressIn(BaseModel):
    step_index: int
    completed: bool = True


class ExperimentOut(ExperimentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    steps: List[ExperimentStepOut] = []


class ExperimentListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    type: Optional[str] = None
    software: Optional[str] = None
    status: str
    deadline: Optional[datetime] = None
    created_at: Optional[datetime] = None
    total_steps: int = 0
    completed_steps: int = 0
    progress: float = 0.0


class ExperimentReportIn(BaseModel):
    """实验报告内容（六个固定段落）"""
    purpose: Optional[str] = None
    environment: Optional[str] = None
    process: Optional[str] = None
    result: Optional[str] = None
    problems: Optional[str] = None
    summary: Optional[str] = None


class ExperimentReportOut(ExperimentReportIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    submitted: bool = False
    updated_at: Optional[datetime] = None


# ========== AI 指导 ==========
class AIGuideRequest(BaseModel):
    experiment_id: int
    current_step: int
    context: Optional[dict] = None
    screen_state: Optional[dict] = None


class GuideTarget(BaseModel):
    x: int
    y: int
    width: int
    height: int
    label: str


class AIGuideResponse(BaseModel):
    level: str   # brief / annotate / detailed / demo
    instruction: str
    target: Optional[GuideTarget] = None
    expected_result: Optional[str] = None
    common_errors: Optional[List[str]] = None
    next_action: Optional[str] = None


class VerifyRequest(BaseModel):
    actual_result: Optional[dict] = None
    operation_context: Optional[dict] = None


class VerifyResponse(BaseModel):
    passed: bool
    feedback: str
    confidence: float = 0.0


class DiagnoseResponse(BaseModel):
    error_type: str
    suggestion: str
    possible_causes: Optional[List[str]] = None


# ========== 进度 ==========
class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    experiment_id: int
    current_step: int
    completed_steps: int
    status: str
    started_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
