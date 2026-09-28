"""Сброс расположения этапов в старом формате.

Прототип хранил в layout_y номер ряда, а не координаты. Такие раскладки
сбрасываются, клиент разложит схему по порядку этапов сам.

Revision ID: 8c4e2d91b7a3
Revises: 5a1f3c2b7d90
Create Date: 2026-09-25 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8c4e2d91b7a3"
down_revision: str | None = "5a1f3c2b7d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE workflow_stages
        SET layout_x = NULL, layout_y = NULL
        WHERE workflow_version_id IN (
            SELECT workflow_version_id
            FROM workflow_stages
            GROUP BY workflow_version_id
            HAVING max(coalesce(layout_y, 0)) <= 20
        )
        """
    )


def downgrade() -> None:
    # Старые координаты не нужны: без них клиент раскладывает схему сам.
    pass
