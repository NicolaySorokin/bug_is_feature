"""Ошибки обмена в журнале - без кодов ответа внешней системы.

Раньше неудачный запуск обмена записывался с техническими подробностями:
«Внешняя система ответила ошибкой 502 (попыток: 3)», «...не ответила
за 15 с» и т. п. Теперь сотрудник видит одну понятную фразу, а причина
сбоя пишется в журнал сервера (app/services/integrations/base.py). Уже
записанные запуски приводятся к той же фразе, чтобы старые коды не
оставались в журнале обмена и в тревогах на главной.

Revision ID: a41601aac6b1
Revises: 3f7a9c1e5b20
Create Date: 2026-09-27 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a41601aac6b1"
down_revision: str | None = "3f7a9c1e5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Текст повторён, а не взят из кода: миграция не должна меняться вместе с ним.
MESSAGE = (
    "Внешняя система сейчас недоступна. Повторите обмен позже, "
    "а если ошибка повторится - обратитесь к разработчику."
)

# Начала прежних текстов сбоя обмена (сеть, тайм-аут, код ответа, не JSON).
OLD_MESSAGES = (
    "Внешняя система ответила ошибкой %",
    "Внешняя система не ответила за %",
    "Не удалось связаться с внешней системой%",
    "Внешняя система прислала ответ не в формате JSON%",
)


def upgrade() -> None:
    runs = sa.table("integration_runs", sa.column("error_message", sa.Text))
    op.execute(
        runs.update()
        .where(sa.or_(*(runs.c.error_message.like(pattern) for pattern in OLD_MESSAGES)))
        .values(error_message=MESSAGE)
    )


def downgrade() -> None:
    # Коды ответа не восстановить, да и не нужно: разработчику они видны
    # в журнале сервера.
    pass
