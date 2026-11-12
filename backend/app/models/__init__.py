"""数据库模型"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float, JSON
)
from sqlalchemy.orm import relationship

from app.db.session import Base


# ========== 用户 ==========
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    real_name = Column(String(64))
    role = Column(String(16), nullable=False, default="student")  # student / teacher
    class_name = Column(String(64))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ========== 实验 ==========
class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    type = Column(String(32))       # python / database / excel / simulation
    software = Column(String(128))  # 依赖的软件
    prerequisites = Column(JSON)    # 前置知识列表
    criteria = Column(JSON)         # 完成标准列表
    status = Column(String(16), default="draft")  # draft / published / archived
    deadline = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    steps = relationship("ExperimentStep", back_populates="experiment", cascade="all, delete-orphan")
    # 级联删除：删除实验时连带清理其所有进度、报告、操作记录，避免孤儿数据
    progresses = relationship(
        "ExperimentProgress", cascade="all, delete-orphan",
        back_populates="experiment",
    )


class ExperimentStep(Base):
    __tablename__ = "experiment_steps"

    id = Column(Integer, primary_key=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    order_index = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    instruction = Column(Text)
    expected_result = Column(Text)
    common_errors = Column(JSON)     # 常见错误列表
    adapter_hint = Column(JSON)      # 适配器所需的提示信息

    experiment = relationship("Experiment", back_populates="steps")


# ========== 实验进度 ==========
class ExperimentProgress(Base):
    """记录每个学生每个实验的进度"""
    __tablename__ = "experiment_progress"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    current_step = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)
    status = Column(String(16), default="not_started")  # not_started / in_progress / completed
    started_at = Column(DateTime)
    last_active_at = Column(DateTime)
    completed_at = Column(DateTime)

    __table_args__ = (
        # 同一用户同一实验只有一条记录
    )

    # 反向关系 + 级联：删除进度时连带删除报告和操作记录
    experiment = relationship("Experiment", back_populates="progresses")
    reports = relationship("ExperimentReport", cascade="all, delete-orphan")
    operation_records = relationship("OperationRecord", cascade="all, delete-orphan")


# ========== 操作记录 ==========
class OperationRecord(Base):
    """实验中的关键操作记录"""
    __tablename__ = "operation_records"

    id = Column(Integer, primary_key=True)
    progress_id = Column(Integer, ForeignKey("experiment_progress.id"), nullable=False)
    step_id = Column(Integer, ForeignKey("experiment_steps.id"))
    event_type = Column(String(32))     # action / error / ai_guide / result
    content = Column(JSON)              # 详细内容
    level = Column(String(16))          # brief / annotate / detailed / demo
    created_at = Column(DateTime, default=datetime.utcnow)


# ========== 实验报告 ==========
class ExperimentReport(Base):
    __tablename__ = "experiment_reports"

    id = Column(Integer, primary_key=True)
    progress_id = Column(Integer, ForeignKey("experiment_progress.id"), nullable=False)
    purpose = Column(Text)
    environment = Column(Text)
    process = Column(Text)
    result = Column(Text)
    problems = Column(Text)
    summary = Column(Text)
    screenshots = Column(JSON)
    submitted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ========== 代码执行任务（沙箱） ==========
class CodeTask(Base):
    """学生代码执行任务

    代码本身不落库（只在内存中转发给沙箱管理器），这里只保存任务状态与结果，
    用于按用户隔离查询、以及服务重启后把未完成任务标记为失败。
    """
    __tablename__ = "code_tasks"

    # uuid4().hex：不可猜测，避免通过 task_id 越权访问他人任务
    id = Column(String(32), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # queued / running / succeeded / failed / timeout / resource_exceeded / cancelled
    status = Column(String(24), nullable=False, default="queued", index=True)
    code_length = Column(Integer, default=0)
    timeout_seconds = Column(Integer, default=10)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    exit_code = Column(Integer)
    duration_ms = Column(Integer)
    error_code = Column(String(32))
    error_message = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
