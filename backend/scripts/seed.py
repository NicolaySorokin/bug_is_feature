"""Наполнение базы демонстрационными данными.

Запуск:
    python -m scripts.seed               # демоданные, если база пустая
    python -m scripts.seed --load 3000   # ещё 3000 взаимодействий для нагрузочной проверки

Повторный запуск ничего не портит: если в базе уже есть взаимодействия или
шаблоны процессов, основной набор не загружается. Перезалить с нуля -
``make reset``.

Что получается (подробности - в пакете scripts/demo):

* 23 сотрудника ИТ Школы: 20 менеджеров, два руководителя со своими
  командами и администратор; роли не наследуются;
* 30 вузов с контактными лицами и один вуз на проверке, 16 программ
  по 8 направлениям, 12 продуктов;
* шаблон процесса из 14 шагов ТЗ с этапом «Отказ вуза» в двух версиях
  (первая устарела, вторая действует) и короткий шаблон для
  дополнительных соглашений;
* около 90 взаимодействий с вузами за два года: с историей переходов,
  составом программ и продуктов, договорами (у тех, кто дошёл до обмена
  документами), лицензиями, комментариями и файлами всех форматов из ТЗ,
  кроме xls; есть черновик, отказ вуза и досрочная отмена;
* журналы синхронизаций с LMS и сайтом, связи с их записями и одна запись
  в очереди сопоставления, прошлые загрузки каталогов;
* каталог вендоров с ответственными и около 400 заявок на обучение
  с потоками, анкетами и зачислениями - для статистики востребованности.

На главной руководителя и администратора видна тревога каждого вида
из раздела 7 концепции.

Пользователи заводятся под ту схему входа, что настроена сейчас
(AUTH_BACKEND): под dev-заглушкой - ``X-Dev-User: petrov``, под Keycloak -
учётные записи реалма с тем же логином и паролем. Сменили схему - перезалейте.

Дополнения, появившиеся после первого выпуска (роли сотрудников в карточках,
вендоры, заявки и обучающиеся), подгружаются и в уже заполненную базу -
каждое только если его таблица пуста.
"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory, engine
from app.models.user import User
from app.services import cache
from scripts.demo import learning, vendors
from scripts.demo.loader import DemoLoader
from scripts.demo.people import EMPLOYEE_BY_USERNAME, HEAD_OF


async def sync_demo_roles(session: AsyncSession) -> int:
    """Снимок ролей у демо-сотрудников, которые ещё ни разу не входили."""
    updated = 0
    for user in (await session.execute(select(User))).scalars():
        employee = EMPLOYEE_BY_USERNAME.get(user.username)
        if employee is not None and not user.roles:
            user.roles = sorted(str(role) for role in employee.roles)
            updated += 1
    await session.flush()
    return updated


async def sync_demo_teams(session: AsyncSession) -> int:
    """Команды руководителей: без них область «команда» пуста.

    Нужна и в базе, заполненной до появления команд: связь ставится тем
    демо-сотрудникам, у которых руководитель ещё не указан.
    """
    users = {user.username: user for user in (await session.execute(select(User))).scalars()}
    updated = 0
    for username, head in HEAD_OF.items():
        user, leader = users.get(username), users.get(head)
        if user is not None and leader is not None and user.head_id is None:
            user.head_id = leader.id
            updated += 1
    await session.flush()
    return updated


async def main(load: int) -> None:
    async with SessionFactory() as session:
        loader = DemoLoader(session)
        if await loader.is_empty():
            summary = await loader.load()
            await session.commit()
            print(
                f"Демоданные загружены: сотрудников {summary.users}, "
                f"вузов {summary.universities}, взаимодействий {summary.interactions}, "
                f"договоров {summary.contracts}, "
                f"переходов по процессам {summary.events}, "
                f"комментариев {summary.comments}, файлов {summary.attachments}."
            )
        else:
            print("В базе уже есть данные, демонстрационные не загружаю.")

        if updated := await sync_demo_roles(session):
            print(f"Роли в карточках демо-сотрудников: {updated}.")
        if updated := await sync_demo_teams(session):
            print(f"Демо-сотрудники распределены по командам: {updated}.")
        if await vendors.is_empty(session):
            outcome = await vendors.load(session)
            print(f"Каталог вендоров: создано {outcome.created}, обновлено {outcome.updated}.")
        if await learning.is_empty(session):
            applications, learners = await learning.load(session)
            print(f"Заявки на обучение: {applications}, обучающихся в LMS: {learners}.")
        # Кэш выборок работающего API должен увидеть новые данные сразу.
        await cache.bump_version(session)
        await session.commit()

        if load:
            added = await loader.load_extra(load)
            await cache.bump_version(session)
            await session.commit()
            print(f"Для нагрузочной проверки добавлено взаимодействий: {added}.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Демонстрационные данные")
    parser.add_argument(
        "--load",
        type=int,
        default=0,
        metavar="N",
        help="добавить N взаимодействий для нагрузочной проверки (без файлов и заметок)",
    )
    asyncio.run(main(parser.parse_args().load))
