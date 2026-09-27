"""Подписант договора, реквизиты вуза и типовые шаблоны договоров.

* У договора появляется подписант со стороны вуза: ФИО, должность
  и основание полномочий. Подписывает не обязательно ответственный
  за взаимодействие контакт, поэтому это отдельные поля.
* У вуза - реквизиты для договора одним текстом (адрес, КПП, ОГРН, банк).
* Типовые шаблоны договоров: текст с полями, которые заполняются при
  формировании документа. Шаблон по умолчанию заводит само приложение
  при первом обращении (app/services/contract_documents.py), поэтому
  данных миграция не добавляет.

Revision ID: 9705cd6dbba5
Revises: a41601aac6b1
Create Date: 2026-09-27 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9705cd6dbba5"
down_revision: str | None = "a41601aac6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("signatory_name", sa.String(length=255), nullable=True))
    op.add_column(
        "contracts", sa.Column("signatory_position", sa.String(length=255), nullable=True)
    )
    op.add_column("contracts", sa.Column("signatory_basis", sa.String(length=255), nullable=True))
    op.add_column("universities", sa.Column("requisites", sa.Text(), nullable=True))
    op.create_table(
        "contract_templates",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_contract_templates_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contract_templates")),
    )


def downgrade() -> None:
    op.drop_table("contract_templates")
    op.drop_column("universities", "requisites")
    op.drop_column("contracts", "signatory_basis")
    op.drop_column("contracts", "signatory_position")
    op.drop_column("contracts", "signatory_name")
