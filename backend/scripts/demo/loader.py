"""Запись демонстрационных данных в базу.

История каждого договора строится от сегодняшнего дня назад: последний
переход был ``days_on_stage`` дней назад, а каждый предыдущий этап занял
от трети до почти полной нормы (``sla_days``). Поэтому «дней на этапе»,
контроль просрочек и фильтр отчёта по движениям процесса совпадают с тем,
что задумано в сюжете, в какой бы день ни запустили сид.

Переходы проверяются по схеме шаблона так же строго, как в рабочем
процессе: сюжет с недопустимым шагом упадёт при загрузке, а не всплывёт
странной историей на показе. Версия шаблона выбирается по дате запуска
процесса - начатые до выхода второй версии идут по первой.

Номера договоров, состав и сюжеты одинаковы при каждом запуске: случайность
идёт от фиксированного зерна, меняются только даты.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.enums import (
    ContractStatus,
    ImplementationStatus,
    ImportRunStatus,
    ImportType,
    IntegrationRunStatus,
    LicenseStatus,
    WorkflowEventType,
    WorkflowInstanceStatus,
)
from app.models.catalog import ItDirection, ItProduct, ItProgram, ProgramProduct, Vendor
from app.models.content import Attachment, Comment
from app.models.contract import (
    Contract,
    ContractContact,
    ContractProduct,
    ContractProgram,
    License,
)
from app.models.importing import ImportRowError, ImportRun
from app.models.integration import ExternalLink, IntegrationRun, IntegrationSource
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTransition,
    WorkflowVersion,
)
from app.services import imports, storage
from app.services.integrations import sync
from app.services.integrations.base import load_fixture
from app.services.integrations.lms import LmsAdapter
from app.services.integrations.site import SiteAdapter
from scripts.demo import files, sheets
from scripts.demo.catalog import (
    CONTACTS_PER_UNIVERSITY,
    DIRECTIONS,
    PRODUCTS,
    PROGRAMS,
    UNIVERSITIES,
    VENDORS,
)
from scripts.demo.people import EMPLOYEES, Employee, university_contacts
from scripts.demo.plans import STORIES, ContractPlan, Move, generate
from scripts.demo.processes import (
    BACKWARD_REASONS,
    SKIP_REASONS,
    TEMPLATE_BY_KEY,
    TEMPLATES,
    TEXTS,
    StageTexts,
)

SEED = 20260924
# Сколько «здоровых» договоров добавить к сюжетным: вместе около 85 договоров.
GENERATED = 66

# Статусы внедрения программ и передачи продуктов по этапу основного процесса.
_IMPLEMENTATION_BY_STAGE: dict[str, tuple[ImplementationStatus, ImplementationStatus]] = {
    "handover": (ImplementationStatus.IN_PROGRESS, ImplementationStatus.IN_PROGRESS),
    "rollout": (ImplementationStatus.IN_PROGRESS, ImplementationStatus.IN_PROGRESS),
    "training": (ImplementationStatus.IN_PROGRESS, ImplementationStatus.IMPLEMENTED),
    "curriculum": (ImplementationStatus.IN_PROGRESS, ImplementationStatus.IMPLEMENTED),
    "classes": (ImplementationStatus.IMPLEMENTED, ImplementationStatus.IMPLEMENTED),
    "docs_update": (ImplementationStatus.IMPLEMENTED, ImplementationStatus.IMPLEMENTED),
    "upskilling": (ImplementationStatus.IMPLEMENTED, ImplementationStatus.IMPLEMENTED),
    "control": (ImplementationStatus.IMPLEMENTED, ImplementationStatus.IMPLEMENTED),
}

_CONTRACT_REMARKS = (
    "Ключевой партнёр в регионе",
    "Вуз планирует второй поток",
    "Занятия ведут два преподавателя кафедры",
    "Интерес к расширению на магистратуру",
)

_SYNC_ERROR = (
    "Внешняя система не ответила: Server error '502 Bad Gateway' "
    "for url 'https://it-school.example/api/partners'"
)


@dataclass
class Summary:
    users: int = 0
    universities: int = 0
    contracts: int = 0
    events: int = 0
    comments: int = 0
    attachments: int = 0


@dataclass
class LoadedVersion:
    """Версия шаблона в том виде, в каком она уже лежит в базе."""

    template_key: str
    model: WorkflowVersion
    stages: dict[str, WorkflowStage]
    transitions: dict[tuple[str, str], WorkflowTransition]

    @property
    def initial(self) -> WorkflowStage:
        return min(self.stages.values(), key=lambda stage: stage.sort_order)


@dataclass
class Visit:
    """Пребывание договора на этапе: событие входа и момент выхода."""

    code: str
    event: WorkflowEvent
    start: datetime
    end: datetime | None = None  # None - договор и сейчас здесь
    done: bool = False  # этап пройден, а не брошен возвратом назад


@dataclass
class Timeline:
    version: LoadedVersion
    events: list[WorkflowEvent] = field(default_factory=list)
    visits: list[Visit] = field(default_factory=list)
    status: WorkflowInstanceStatus = WorkflowInstanceStatus.IN_PROGRESS

    @property
    def started(self) -> datetime:
        return self.events[0].created_at

    @property
    def current(self) -> Visit:
        return self.visits[-1]

    def left_at(self, code: str) -> datetime | None:
        """Когда этап впервые пройден вперёд - например, подписание."""
        return next(
            (visit.end for visit in self.visits if visit.code == code and visit.done), None
        )


class DemoLoader:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.now = datetime.now(UTC)
        self.today = date.today()
        self.rng = random.Random(SEED)
        self.summary = Summary()

        self.users: dict[str, User] = {}
        self.universities: dict[str, University] = {}
        self.contacts: dict[str, list[UniversityContact]] = {}
        self.programs: dict[str, ItProgram] = {}
        self.products: dict[str, ItProduct] = {}
        self.versions: dict[str, list[LoadedVersion]] = {}
        self.sources: dict[str, IntegrationSource] = {}
        self.numbers: set[str] = set()
        self.license_count = 0

    # --- Общее -----------------------------------------------------------------

    def _ago(self, days: float, minutes: int = 0) -> datetime:
        return self.now - timedelta(days=days, minutes=minutes)

    def _jitter(self) -> timedelta:
        """Разброс по времени суток, чтобы события не выстраивались по часам."""
        return timedelta(minutes=self.rng.randint(30, 420))

    @staticmethod
    def _subject(employee: Employee) -> str:
        """Как пользователь представится API: так же его и заводим.

        Под Keycloak это id из реалма, под dev-заглушкой - ``dev:<логин>``.
        """
        if settings.auth_backend == "keycloak":
            return employee.keycloak_id
        return f"dev:{employee.username}"

    async def is_empty(self) -> bool:
        contracts = await self.session.scalar(select(func.count()).select_from(Contract))
        templates = await self.session.scalar(
            select(func.count()).select_from(WorkflowTemplate)
        )
        return not contracts and not templates

    # --- Основной набор --------------------------------------------------------

    async def load(self, generated: int = GENERATED) -> Summary:
        await self._users()
        await self._catalog()
        await self._universities()
        await self._templates()
        self.sources = {
            source.code: source for source in await sync.ensure_sources(self.session)
        }

        for plan in (*STORIES, *generate(generated, self.rng)):
            await self._contract(plan)

        await self._integration_history()
        await self._import_history()
        await self.session.flush()
        return self.summary

    async def _users(self) -> None:
        if settings.auth_backend != "keycloak":
            # Пользователь dev-заглушки для запросов без заголовков, как в Swagger UI.
            self.session.add(
                User(
                    id=uuid.uuid4(),
                    keycloak_id=settings.dev_user_subject,
                    username=settings.dev_user_username,
                    full_name=settings.dev_user_full_name,
                    email=settings.dev_user_email,
                )
            )
        for employee in EMPLOYEES:
            joined = self._ago(self.rng.randint(700, 830))
            user = User(
                id=uuid.uuid4(),
                keycloak_id=self._subject(employee),
                username=employee.username,
                full_name=employee.full_name,
                email=employee.email,
                # Снимок ролей из реалма: карточки видны до первого входа.
                roles=sorted(str(role) for role in employee.roles),
                created_at=joined,
                updated_at=joined,
            )
            self.session.add(user)
            self.users[employee.username] = user
        await self.session.flush()
        self.summary.users = len(self.users)

    async def _catalog(self) -> None:
        directions = {
            name: ItDirection(id=uuid.uuid4(), name=name, description=description)
            for name, description in DIRECTIONS.items()
        }
        vendors = {
            name: Vendor(id=uuid.uuid4(), name=name, description=description)
            for name, description in VENDORS.items()
        }
        self.session.add_all([*directions.values(), *vendors.values()])
        await self.session.flush()

        for info in PRODUCTS:
            self.products[info.name] = ItProduct(
                id=uuid.uuid4(),
                name=info.name,
                vendor_id=vendors[info.vendor].id,
                description=info.description,
            )
        for info in PROGRAMS:
            self.programs[info.name] = ItProgram(
                id=uuid.uuid4(),
                name=info.name,
                direction_id=directions[info.direction].id,
                description=info.description,
            )
        self.session.add_all([*self.products.values(), *self.programs.values()])
        await self.session.flush()

        self.session.add_all(
            ProgramProduct(
                program_id=self.programs[info.name].id, product_id=self.products[name].id
            )
            for info in PROGRAMS
            for name in info.products
        )
        await self.session.flush()

    async def _universities(self) -> None:
        for info in UNIVERSITIES:
            since = self._ago(self.rng.randint(700, 820))
            university = University(
                id=uuid.uuid4(),
                name=info.name,
                short_name=info.short_name,
                city=info.city,
                website=info.website,
                description=(
                    f"Партнёр ИТ Школы с {since.year} года. "
                    f"Направления: {', '.join(info.directions)}."
                ),
                manager_id=self.users[info.manager].id if info.manager else None,
                created_at=since,
                updated_at=since,
            )
            self.universities[info.key] = university
            self.contacts[info.key] = [
                UniversityContact(
                    id=uuid.uuid4(),
                    university_id=university.id,
                    full_name=contact.full_name,
                    position=contact.position,
                    email=contact.email,
                    phone=contact.phone,
                    created_at=since,
                    updated_at=since,
                )
                for contact in university_contacts(info.key, CONTACTS_PER_UNIVERSITY)
            ]
        self.session.add_all(self.universities.values())
        await self.session.flush()
        self.session.add_all(contact for items in self.contacts.values() for contact in items)
        await self.session.flush()
        self.summary.universities = len(self.universities)

    async def _templates(self) -> None:
        # Порядок заведения важен: основным считается шаблон, созданный раньше.
        for spec in TEMPLATES:
            template = WorkflowTemplate(
                id=uuid.uuid4(),
                name=spec.name,
                description=spec.description,
                created_at=self._ago(spec.created_days_ago),
            )
            self.session.add(template)
            await self.session.flush()

            loaded: list[LoadedVersion] = []
            for version_spec in spec.versions:
                published = self._ago(version_spec.published_days_ago)
                version = WorkflowVersion(
                    id=uuid.uuid4(),
                    template_id=template.id,
                    version_number=version_spec.number,
                    created_at=published - timedelta(days=4),
                    published_at=published,
                )
                stages = {
                    stage.code: WorkflowStage(
                        id=uuid.uuid4(),
                        workflow_version_id=version.id,
                        code=stage.code,
                        name=stage.name,
                        description=stage.description,
                        sort_order=(index + 1) * 10,
                        is_optional=stage.optional,
                        is_final=stage.final,
                        sla_days=stage.sla_days,
                    )
                    for index, stage in enumerate(version_spec.stages)
                }
                transitions = {
                    (item.source, item.target): WorkflowTransition(
                        id=uuid.uuid4(),
                        workflow_version_id=version.id,
                        from_stage_id=stages[item.source].id,
                        to_stage_id=stages[item.target].id,
                        name=item.name,
                        is_backward=item.backward,
                        requires_comment=item.needs_comment,
                    )
                    for item in version_spec.transitions
                }
                self.session.add(version)
                await self.session.flush()
                self.session.add_all(stages.values())
                await self.session.flush()
                self.session.add_all(transitions.values())
                await self.session.flush()
                loaded.append(LoadedVersion(spec.key, version, stages, transitions))
            self.versions[spec.key] = loaded

    # --- Договор ---------------------------------------------------------------

    def _version_at(self, template_key: str, moment: datetime) -> LoadedVersion:
        """Последняя версия, опубликованная к моменту запуска процесса."""
        versions = self.versions[template_key]
        published = [item for item in versions if item.model.published_at <= moment]
        return published[-1] if published else versions[0]

    def _duration(self, stage: WorkflowStage) -> timedelta:
        norm = stage.sla_days or 7
        days = max(1.0, self.rng.uniform(0.35, 0.9) * norm)
        return timedelta(days=days) + self._jitter()

    def _timeline(self, plan: ContractPlan) -> Timeline:
        """История процесса: от последнего перехода назад к запуску."""
        moves = [step if isinstance(step, Move) else Move(step) for step in plan.route]
        latest = self.versions[plan.template][-1]

        # Сначала моменты переходов по нормам последней версии, затем выбор
        # версии по дате запуска: разница норм между версиями невелика.
        moments: list[datetime] = []
        moment = self._ago(plan.days_on_stage) - self._jitter()
        codes = [latest.initial.code, *(move.stage for move in moves)]
        for index in range(len(moves) - 1, -1, -1):
            moments.insert(0, moment)
            stage = latest.stages.get(codes[index]) or latest.initial
            moment -= self._duration(stage)
        version = self._version_at(plan.template, moment)

        timeline = Timeline(version=version)
        manager = self._responsible(plan)
        start = WorkflowEvent(
            id=uuid.uuid4(),
            to_stage_id=version.initial.id,
            user_id=manager.id,
            event_type=WorkflowEventType.STARTED,
            created_at=moment,
        )
        timeline.events.append(start)
        timeline.visits.append(Visit(version.initial.code, start, moment))

        for move, when in zip(moves, moments, strict=True):
            source = timeline.current.code
            transition = version.transitions.get((source, move.stage))
            if transition is None:
                if plan.light:
                    break  # шаблон поменяли руками - дальше путь не пройти
                raise ValueError(
                    f"{plan.number or plan.university}: переход «{source} -> {move.stage}» "
                    "не предусмотрен шаблоном"
                )

            skip = move.skip and version.stages[source].is_optional
            if skip:
                kind, comment = (
                    WorkflowEventType.SKIPPED,
                    move.comment or SKIP_REASONS.get(source),
                )
            elif transition.is_backward:
                kind = WorkflowEventType.BACKWARD
                comment = move.comment or BACKWARD_REASONS.get((source, move.stage))
                comment = comment or transition.name
            else:
                kind, comment = WorkflowEventType.FORWARD, move.comment

            event = WorkflowEvent(
                id=uuid.uuid4(),
                from_stage_id=version.stages[source].id,
                to_stage_id=version.stages[move.stage].id,
                user_id=manager.id,
                event_type=kind,
                comment=comment,
                created_at=when,
            )
            timeline.current.end = when
            timeline.current.done = kind != WorkflowEventType.BACKWARD
            timeline.events.append(event)
            timeline.visits.append(Visit(move.stage, event, when))

        if version.stages[timeline.current.code].is_final:
            timeline.status = WorkflowInstanceStatus.COMPLETED
            timeline.current.done = True
        elif plan.blocked:
            since = timeline.current.start
            blocked_at = since + (self.now - since) * self.rng.uniform(0.3, 0.7)
            timeline.events.append(
                WorkflowEvent(
                    id=uuid.uuid4(),
                    from_stage_id=version.stages[timeline.current.code].id,
                    to_stage_id=version.stages[timeline.current.code].id,
                    user_id=manager.id,
                    event_type=WorkflowEventType.BLOCKED,
                    comment=plan.blocked,
                    created_at=blocked_at,
                )
            )
            timeline.status = WorkflowInstanceStatus.BLOCKED
        return timeline

    def _responsible(self, plan: ContractPlan) -> User:
        """Кто ведёт договор. Без ответственного действия выполняет руководитель."""
        return self.users[plan.manager] if plan.manager else self.users["orlova"]

    def _number(self, plan: ContractPlan, created: datetime) -> str:
        if plan.number:
            self.numbers.add(plan.number)
            return plan.number
        prefix = "НТ" if plan.light else ("ДС" if plan.template == "short" else "ДГ")
        sequence = 101
        while f"{prefix}-{created.year}-{sequence:03d}" in self.numbers:
            sequence += 1
        number = f"{prefix}-{created.year}-{sequence:03d}"
        self.numbers.add(number)
        return number

    def _valid_to(self, plan: ContractPlan, signed: date) -> date:
        if plan.valid_days_left is not None:
            return self.today + timedelta(days=plan.valid_days_left)
        # Договор заключают на целое число лет - берём первый срок с запасом.
        for years in range(1, 6):
            candidate = _add_years(signed, years) - timedelta(days=1)
            if candidate >= self.today + timedelta(days=75):
                return candidate
        return self.today + timedelta(days=365)

    def _implementation(
        self, plan: ContractPlan, timeline: Timeline | None
    ) -> tuple[ImplementationStatus, ImplementationStatus]:
        if plan.implementation is not None:
            return plan.implementation, plan.implementation
        if timeline is None:
            return ImplementationStatus.NOT_STARTED, ImplementationStatus.NOT_STARTED
        if timeline.version.template_key == "short":
            if timeline.status != WorkflowInstanceStatus.COMPLETED:
                return ImplementationStatus.NOT_STARTED, ImplementationStatus.NOT_STARTED
            recent = self.now - timeline.current.start < timedelta(days=60)
            status = (
                ImplementationStatus.IN_PROGRESS
                if recent
                else ImplementationStatus.IMPLEMENTED
            )
            return status, status
        return _IMPLEMENTATION_BY_STAGE.get(
            timeline.current.code,
            (ImplementationStatus.NOT_STARTED, ImplementationStatus.NOT_STARTED),
        )

    async def _contract(self, plan: ContractPlan) -> None:
        university = self.universities[plan.university]
        contacts = self.contacts.get(plan.university, [])
        manager = self.users[plan.manager] if plan.manager else None
        timeline = self._timeline(plan) if plan.template else None

        if timeline is not None:
            created = timeline.started - timedelta(hours=self.rng.randint(2, 60))
            if timeline.version.template_key == "short":
                signed_at = timeline.left_at("signing") or (
                    timeline.current.start
                    if timeline.status == WorkflowInstanceStatus.COMPLETED
                    else None
                )
            else:
                signed_at = timeline.left_at("signing")
            handover = timeline.left_at("signing") or signed_at
            last_activity = max(event.created_at for event in timeline.events)
        else:
            created = self._ago(plan.days_on_stage) - self._jitter()
            signed_at = handover = None
            last_activity = created

        number = self._number(plan, created)
        signed = signed_at.date() if signed_at else None
        status = plan.status or (ContractStatus.ACTIVE if signed else ContractStatus.DRAFT)
        remark = plan.notes[0] if plan.notes else None
        if remark is None and not plan.light and self.rng.random() < 0.25:
            remark = self.rng.choice(_CONTRACT_REMARKS)

        contract = Contract(
            id=uuid.uuid4(),
            university_id=university.id,
            manager_id=manager.id if manager else None,
            number=number,
            title=plan.title,
            signed_at=signed,
            valid_from=signed,
            valid_to=self._valid_to(plan, signed) if signed else None,
            status=status,
            comment=remark,
            created_at=created,
            updated_at=last_activity,
        )
        self.session.add(contract)

        program_status, product_status = self._implementation(plan, timeline)
        self.session.add_all(
            ContractProgram(
                id=uuid.uuid4(),
                contract_id=contract.id,
                program_id=self.programs[name].id,
                implementation_status=program_status,
                created_at=created,
            )
            for name in plan.programs
        )
        links = [
            ContractProduct(
                id=uuid.uuid4(),
                contract_id=contract.id,
                product_id=self.products[name].id,
                transfer_status=product_status,
                created_at=created,
            )
            for name in plan.products
        ]
        self.session.add_all(links)

        if contacts:
            self.session.add(
                ContractContact(
                    contract_id=contract.id,
                    contact_id=contacts[0].id,
                    role="Ответственный за договор",
                    is_primary=True,
                )
            )
            if len(contacts) > 1 and self.rng.random() < 0.5:
                self.session.add(
                    ContractContact(
                        contract_id=contract.id,
                        contact_id=contacts[1].id,
                        role="Куратор программ",
                        is_primary=False,
                    )
                )

        if handover is not None and plan.licenses:
            self._licenses(plan, contract, links, handover)

        context = self._context(plan, contract, university, contacts, manager)
        if timeline is not None:
            if not plan.light:
                self._entry_comments(timeline, context)
            self._instance(contract, timeline)
        # Комментарии и файлы ссылаются на события процесса без relationship,
        # поэтому сначала события должны попасть в базу.
        await self.session.flush()

        if timeline is not None and not plan.light:
            self._stage_extras(plan, contract, timeline, context)
        if plan.notes:
            author = self._responsible(plan)
            for text in plan.notes:
                self._comment(contract, author, text, self._between(created, self.now), None)
        if plan.request:
            self.session.add(
                ExternalLink(
                    id=uuid.uuid4(),
                    source_id=self.sources["site"].id,
                    entity_type=sync.CONTRACT,
                    entity_id=contract.id,
                    external_id=plan.request,
                )
            )
        self.summary.contracts += 1

    def _licenses(
        self,
        plan: ContractPlan,
        contract: Contract,
        links: list[ContractProduct],
        handover: datetime,
    ) -> None:
        start = handover.date()
        valid_to = (
            self.today + timedelta(days=plan.license_days_left)
            if plan.license_days_left is not None
            else contract.valid_to
        )
        for link in links:
            self.license_count += 1
            self.session.add(
                License(
                    id=uuid.uuid4(),
                    contract_product_id=link.id,
                    number=f"ЛЦ-{start.year}-{self.license_count:04d}",
                    seats=self.rng.randrange(30, 260, 10),
                    signed_at=start,
                    valid_from=start,
                    valid_to=valid_to,
                    status=(
                        LicenseStatus.EXPIRED
                        if valid_to and valid_to < self.today
                        else LicenseStatus.ACTIVE
                    ),
                    created_at=handover,
                    updated_at=handover,
                )
            )

    def _instance(self, contract: Contract, timeline: Timeline) -> None:
        current = timeline.current
        instance = WorkflowInstance(
            id=uuid.uuid4(),
            contract_id=contract.id,
            workflow_version_id=timeline.version.model.id,
            current_stage_id=timeline.version.stages[current.code].id,
            status=timeline.status,
            current_stage_started_at=current.start,
            started_at=timeline.started,
            completed_at=(
                current.start if timeline.status == WorkflowInstanceStatus.COMPLETED else None
            ),
        )
        self.session.add(instance)
        for event in timeline.events:
            event.workflow_instance_id = instance.id
        self.session.add_all(timeline.events)
        self.summary.events += len(timeline.events)

    # --- Комментарии и файлы этапов --------------------------------------------

    def _context(
        self,
        plan: ContractPlan,
        contract: Contract,
        university: University,
        contacts: list[UniversityContact],
        manager: User | None,
    ) -> dict[str, object]:
        template = TEMPLATE_BY_KEY[plan.template or "main"]
        return {
            "number": contract.number,
            "university": university.short_name or university.name,
            "university_name": university.name,
            "programs": ", ".join(plan.programs) or "—",
            "contact": contacts[0].full_name if contacts else "представитель вуза",
            "manager": manager.full_name if manager else "не назначен",
            "students": self.rng.randrange(18, 96, 2),
            "teachers": self.rng.randint(3, 12),
            "licenses": self.rng.randrange(30, 260, 10),
            "document": template.document,
            "date": "",
        }

    def _between(self, start: datetime, end: datetime | None) -> datetime:
        """Случайный момент внутри окна, не позже текущего."""
        finish = min(end or self.now, self.now) - timedelta(minutes=10)
        if finish <= start:
            return start + timedelta(minutes=1)
        return start + (finish - start) * self.rng.uniform(0.1, 0.9)

    def _entry_comments(self, timeline: Timeline, context: dict[str, object]) -> None:
        """Комментарии к переходам вперёд - если сюжет не задал свои."""
        texts = TEXTS[timeline.version.template_key]
        for visit in timeline.visits:
            entry = texts.get(visit.code, StageTexts()).entry
            if (
                visit.event.event_type == WorkflowEventType.FORWARD
                and not visit.event.comment
                and entry
                and self.rng.random() < 0.6
            ):
                context["date"] = visit.start.strftime("%d.%m.%Y")
                visit.event.comment = self.rng.choice(entry).format_map(context)

    def _stage_extras(
        self,
        plan: ContractPlan,
        contract: Contract,
        timeline: Timeline,
        context: dict[str, object],
    ) -> None:
        """Заметки менеджера и файлы, пока договор стоял на этапе."""
        texts = TEXTS[timeline.version.template_key]
        author = self._responsible(plan)
        for visit in timeline.visits:
            stage_texts = texts.get(visit.code, StageTexts())
            context["date"] = visit.start.strftime("%d.%m.%Y")

            if stage_texts.notes and self.rng.random() < 0.45:
                text = self.rng.choice(stage_texts.notes).format_map(context)
                when = self._between(visit.start, visit.end)
                self._comment(contract, author, text, when, visit.event.id)

            if not plan.documents:
                continue
            stage = timeline.version.stages[visit.code]
            for upload in stage_texts.uploads:
                if upload.when_done and not visit.done:
                    continue
                if upload.chance < 1 and self.rng.random() > upload.chance:
                    continue
                name = upload.name.format_map(context)
                when = self._between(visit.start, visit.end)
                self._attachment(
                    contract, author, visit.event.id, upload.kind, name, stage, when, context
                )

    def _comment(
        self,
        contract: Contract,
        author: User,
        text: str,
        when: datetime,
        event_id: uuid.UUID | None,
    ) -> None:
        self.session.add(
            Comment(
                id=uuid.uuid4(),
                contract_id=contract.id,
                workflow_event_id=event_id,
                author_id=author.id,
                text=text,
                created_at=when,
            )
        )
        self.summary.comments += 1

    def _attachment(
        self,
        contract: Contract,
        author: User,
        event_id: uuid.UUID,
        kind: str,
        name: str,
        stage: WorkflowStage,
        when: datetime,
        context: dict[str, object],
    ) -> None:
        title = PurePosixPath(name).stem.removesuffix(".log")
        lines = [
            f"Вуз: {context['university_name']}",
            f"Договор: {contract.number}",
            f"Этап: {stage.name}",
            f"Программы: {context['programs']}",
            f"Ответственный ИТ Школы: {context['manager']}",
            f"Представитель вуза: {context['contact']}",
            f"Дата: {when:%d.%m.%Y}",
        ]
        data = files.document(kind, title, lines, _table_for(name, context, self.rng))

        file_id = uuid.uuid4()
        relative = f"contracts/{contract.id}/{file_id}.{kind}"
        target = storage.absolute_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        self.session.add(
            Attachment(
                id=file_id,
                contract_id=contract.id,
                workflow_event_id=event_id,
                uploaded_by=author.id,
                original_name=name,
                storage_path=relative,
                mime_type=storage.ALLOWED_TYPES[kind],
                size_bytes=len(data),
                created_at=when,
            )
        )
        self.summary.attachments += 1

    # --- Журналы обмена и загрузок ---------------------------------------------

    async def _integration_history(self) -> None:
        """Прошлые запуски синхронизации. Последний обмен с сайтом упал.

        Из-за этого на главной висит тревога «синхронизация не удалась»:
        на показе её снимает ручной запуск обмена в разделе «Интеграции».
        """
        admin = self.users["admin"]
        payloads = {
            "lms": LmsAdapter.parse(load_fixture("lms")),
            "site": SiteAdapter.parse(load_fixture("site")),
        }
        schedule = {
            "lms": (29, 26, 23, 19, 15, 12, 8, 5, 2),
            "site": (28, 24, 20, 16, 13, 9, 6, 2),
        }
        for code, days_list in schedule.items():
            size = payloads[code].size
            for days in days_list:
                started = self._ago(days, minutes=self.rng.randint(0, 600))
                failed = code == "site" and days == days_list[-1]
                created = 0 if failed else self.rng.choice((0, 0, 1, 2))
                broken = 1 if code == "site" and not failed else 0  # заявка на неизвестный вуз
                self.session.add(
                    IntegrationRun(
                        id=uuid.uuid4(),
                        source_id=self.sources[code].id,
                        triggered_by=admin.id if self.rng.random() < 0.5 else None,
                        status=(
                            IntegrationRunStatus.FAILED
                            if failed
                            else IntegrationRunStatus.SUCCESS
                        ),
                        started_at=started,
                        finished_at=started + timedelta(seconds=self.rng.randint(2, 40)),
                        records_received=0 if failed else size,
                        records_created=created,
                        records_updated=0 if failed else size - created - broken,
                        records_failed=broken,
                        error_message=_SYNC_ERROR if failed else None,
                    )
                )

    async def _import_history(self) -> None:
        """Три прошлые загрузки: удачная, с отклонённой строкой и не прошедшая проверку."""
        admin = self.users["admin"]
        history = (
            (imports.CATALOG_SPEC, sheets.catalog(), "Каталог ИТ Школы 2025.xlsx", 390, None),
            (
                imports.UNIVERSITY_SPEC,
                sheets.universities(),
                "Вузы — дополнение.xlsx",
                150,
                None,
            ),
            (
                imports.CATALOG_SPEC,
                sheets.catalog_errors(),
                "Каталог — сентябрь.xlsx",
                6,
                ImportRunStatus.FAILED,
            ),
        )
        for spec, (headers, rows), filename, days, status in history:
            relative = str(PurePosixPath("imports") / f"{uuid.uuid4()}.xlsx")
            target = storage.absolute_path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files.xlsx(spec.title, headers, rows))

            sheet = imports.SheetData(headers=headers, rows=rows)
            mapping = imports.suggest_mapping(spec, headers)
            errors = imports.validate(spec, sheet, mapping)
            uploaded = self._ago(days, minutes=self.rng.randint(0, 480))
            run = ImportRun(
                id=uuid.uuid4(),
                uploaded_by=admin.id,
                filename=filename,
                storage_path=relative,
                import_type=ImportType(spec.import_type),
                mapping=mapping,
                rows_total=len(rows),
                created_at=uploaded,
            )
            if status == ImportRunStatus.FAILED:
                run.status = ImportRunStatus.FAILED  # проверка не прошла, импорт не делали
            else:
                failed_rows = {error.row_number for error in errors}
                run.status = ImportRunStatus.COMPLETED
                run.rows_failed = len(failed_rows)
                run.rows_updated = min(3, len(rows) - len(failed_rows))
                run.rows_created = len(rows) - len(failed_rows) - run.rows_updated
                run.finished_at = uploaded + timedelta(minutes=4)
            self.session.add(run)
            await self.session.flush()
            self.session.add_all(
                ImportRowError(
                    id=uuid.uuid4(),
                    import_run_id=run.id,
                    row_number=error.row_number,
                    field_name=error.field_name,
                    message=error.message,
                )
                for error in errors
            )

    # --- Добавка для нагрузки --------------------------------------------------

    async def load_extra(self, count: int, batch: int = 200) -> int:
        """Ещё ``count`` договоров поверх того, что уже в базе."""
        await self._attach_existing()
        self.rng = random.Random(SEED + len(self.numbers))
        plans = generate(count, self.rng, light=True)
        for index, plan in enumerate(plans, start=1):
            await self._contract(plan)
            if index % batch == 0:
                await self.session.flush()
                # Сессия не должна копить десятки тысяч объектов.
                self.session.expunge_all()
                print(f"  добавлено договоров: {index} из {count}")
        await self.session.flush()
        return len(plans)

    async def _attach_existing(self) -> None:
        """Справочники и шаблоны берутся из базы - в том виде, в каком они сейчас."""
        users = (await self.session.execute(select(User))).scalars()
        self.users = {user.username: user for user in users}

        by_name = {info.name: info.key for info in UNIVERSITIES}
        universities = (
            await self.session.execute(
                select(University).options(selectinload(University.contacts))
            )
        ).scalars()
        for university in universities:
            key = by_name.get(university.name)
            if key is not None:
                self.universities[key] = university
                self.contacts[key] = list(university.contacts)

        programs = (await self.session.execute(select(ItProgram))).scalars()
        self.programs = {program.name: program for program in programs}
        products = (await self.session.execute(select(ItProduct))).scalars()
        self.products = {product.name: product for product in products}

        template_keys = {spec.name: spec.key for spec in TEMPLATES}
        versions = (
            await self.session.execute(
                select(WorkflowVersion, WorkflowTemplate.name)
                .join(WorkflowTemplate)
                .where(WorkflowVersion.published_at.is_not(None))
                .options(
                    selectinload(WorkflowVersion.stages),
                    selectinload(WorkflowVersion.transitions),
                )
                .order_by(WorkflowVersion.version_number)
            )
        ).all()
        for version, template_name in versions:
            key = template_keys.get(template_name)
            if key is None:
                continue
            stages = {stage.code: stage for stage in version.stages}
            code_by_id = {stage.id: stage.code for stage in version.stages}
            transitions = {
                (code_by_id[item.from_stage_id], code_by_id[item.to_stage_id]): item
                for item in version.transitions
            }
            self.versions.setdefault(key, []).append(
                LoadedVersion(key, version, stages, transitions)
            )

        self.sources = {
            source.code: source for source in await sync.ensure_sources(self.session)
        }
        self.numbers = set((await self.session.execute(select(Contract.number))).scalars())
        self.license_count = await self.session.scalar(
            select(func.count()).select_from(License)
        )
        missing = {"main", "short"} - set(self.versions)
        if missing or not self.universities:
            raise RuntimeError(
                "В базе нет демонстрационных справочников или шаблонов - "
                "сначала загрузите демоданные: python -m scripts.seed"
            )


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:  # 29 февраля
        return value.replace(year=value.year + years, day=28)


def _table_for(
    name: str, context: dict[str, object], rng: random.Random
) -> files.Table | None:
    """Содержимое таблиц-вложений: у каждого вида своё."""
    lowered = name.lower()
    if "преподавател" in lowered:
        people = university_contacts(f"{context['university']}-teachers", 6)
        return (
            ("ФИО", "Должность", "Курс пройден", "Сертификат"),
            [
                (
                    person.full_name,
                    "Преподаватель кафедры",
                    "да",
                    f"С-{rng.randint(1000, 9999)}",
                )
                for person in people
            ],
        )
    if "расписание" in lowered:
        return (
            ("День", "Время", "Группа", "Тема"),
            [
                (day, "10:10–11:40", f"ИТ-{rng.randint(11, 45)}", topic)
                for day, topic in zip(
                    ("Понедельник", "Среда", "Пятница", "Понедельник", "Среда"),
                    ("Введение", "Практикум 1", "Практикум 2", "Контрольная", "Проект"),
                    strict=True,
                )
            ],
        )
    if "учебный план" in lowered:
        return (
            ("Модуль", "Часы", "Форма контроля"),
            [
                ("Основы и инструменты", 36, "Зачёт"),
                ("Практикум на учебном стенде", 72, "Проект"),
                ("Промышленные практики", 36, "Экзамен"),
            ],
        )
    return None
