"""baseline: users, experiments, steps, progress, records, reports

Revision ID: 20261113_0000
Revises:
Create Date: 2026-11-13

生产环境的第一个迁移：在干净库上创建除 code_tasks 外的全部核心表。
此后生产部署必须且只能通过 `alembic upgrade head` 建表（DB_AUTO_CREATE 必须为空/false）。
对历史开发库（已由 create_all 建表）幂等：表已存在则跳过。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261113_0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "users" in existing:
        # 历史库已由 create_all 建过全部核心表，本迁移无事可做
        return

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("real_name", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("class_name", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=True),
        sa.Column("software", sa.String(length=128), nullable=True),
        sa.Column("prerequisites", sa.JSON(), nullable=True),
        sa.Column("criteria", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "experiment_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.Integer(), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("expected_result", sa.Text(), nullable=True),
        sa.Column("common_errors", sa.JSON(), nullable=True),
        sa.Column("adapter_hint", sa.JSON(), nullable=True),
    )

    op.create_table(
        "experiment_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("experiment_id", sa.Integer(), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=True),
        sa.Column("completed_steps", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("last_active_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "operation_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "progress_id",
            sa.Integer(),
            sa.ForeignKey("experiment_progress.id"),
            nullable=False,
        ),
        sa.Column("step_id", sa.Integer(), sa.ForeignKey("experiment_steps.id"), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=True),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "experiment_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "progress_id",
            sa.Integer(),
            sa.ForeignKey("experiment_progress.id"),
            nullable=False,
        ),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("environment", sa.Text(), nullable=True),
        sa.Column("process", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("problems", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("screenshots", sa.JSON(), nullable=True),
        sa.Column("submitted", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "users" not in existing:
        return
    for table in (
        "experiment_reports",
        "operation_records",
        "experiment_progress",
        "experiment_steps",
        "experiments",
    ):
        if table in existing:
            op.drop_table(table)
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
