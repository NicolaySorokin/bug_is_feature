"""Отметки «прочитано» у уведомлений колокольчика.

Отметка хранит ключ проблемы и важность, при которой её прочитали.

Revision ID: 51bfc7dc611f
Revises: 9705cd6dbba5
Create Date: 2026-09-28 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "51bfc7dc611f"
down_revision: str | None = "9705cd6dbba5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_marks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("alert_key", sa.String(length=300), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_alert_marks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "alert_key", name=op.f("pk_alert_marks")),
    )


def downgrade() -> None:
    op.drop_table("alert_marks")
