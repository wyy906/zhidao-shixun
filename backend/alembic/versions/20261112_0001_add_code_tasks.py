"""add code_tasks

Revision ID: 20261112_0001
Revises:
Create Date: 2026-11-12

注意：应用启动仍使用 Base.metadata.create_all；本迁移用于把 code_tasks
纳入正式迁移链。若目标库已由 create_all 建过该表，upgrade 会跳过建表。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261112_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "code_tasks" in inspector.get_table_names():
        return

    op.create_table(
        "code_tasks",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("code_length", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_code_tasks_user_id", "code_tasks", ["user_id"])
    op.create_index("ix_code_tasks_status", "code_tasks", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "code_tasks" not in inspector.get_table_names():
        return
    op.drop_index("ix_code_tasks_status", table_name="code_tasks")
    op.drop_index("ix_code_tasks_user_id", table_name="code_tasks")
    op.drop_table("code_tasks")
