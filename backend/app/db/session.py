"""Асинхронное подключение к PostgreSQL."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)

SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Ключ в session.info: в сессии сохранялись предметные данные
# (выставляет обработчик before_flush в app.services.audit).
DATA_CHANGED = "data_changed"


def mark_changed(session: AsyncSession) -> None:
    """Для записи мимо ORM (UPDATE/DELETE выражением): обработчик before_flush её не видит."""
    session.info[DATA_CHANGED] = True


async def commit(session: AsyncSession) -> None:
    """Фиксирует транзакцию, отмечая изменение данных для кэша выборок."""
    if session.info.pop(DATA_CHANGED, False):
        # Импорт здесь: сервис кэша сам зависит от моделей.
        from app.services import cache

        await cache.bump_version(session)
    await session.commit()


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: сессия на время обработки запроса.

    Подключается с ``scope="function"`` (см. app.api.deps): транзакция
    фиксируется до отправки ответа. Иначе клиент получил бы «успех» раньше,
    чем данные сохранены, - и сбой фиксации, и чтение сразу после записи
    прошли бы мимо него.
    """
    async with SessionFactory() as session:
        try:
            yield session
            await commit(session)
        except Exception:
            await session.rollback()
            raise
