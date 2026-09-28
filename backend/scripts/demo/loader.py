"""Запись демонстрационных данных в базу.

История каждого взаимодействия строится от сегодняшнего дня назад, поэтому
сроки и просрочки выглядят так, как задумано в сюжете, в любой день.
Переходы проверяются по схеме шаблона, как в рабочем процессе. Случайность
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
    ClosureReason,
    ContractClosureReason,
    ContractStatus,
    DataScope,
    ImportRunStatus,
    ImportType,
    IntegrationRunStatus,
    InteractionOutcome,
    InteractionStatus,
    LicenseStatus,
    MappingStatus,
    Permission,
    ProductTransferStatus,
    ProgramImplementationStatus,
    UniversityStatus,
    WorkflowEventType,
    WorkflowVersionStatus,
)
from app.models.access import UserUniversityAccess
from app.models.catalog import ItDirection, ItProduct, ItProgram, ProgramProduct, Vendor
from app.models.content import Attachment, Comment
from app.models.contract import Contract, License
from app.models.importing import ImportRowError, ImportRun
from app.models.integration import (
    ExternalLink,
    IntegrationMapping,
    IntegrationRun,
    IntegrationRunError,
    IntegrationSource,
)
from app.models.interaction import (
    InteractionContact,
    InteractionProduct,
    InteractionProgram,
    InteractionProgramProduct,
)
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
from app.services.integrations.base import UNAVAILABLE_MESSAGE, load_fixture
from app.services.integrations.lms import LmsAdapter
from app.services.integrations.site import SiteAdapter
from scripts.demo import files, sheets
from scripts.demo.catalog import (
    CONTACTS_PER_UNIVERSITY,
    DIRECTIONS,
    PRODUCTS,
    PROGRAM_BY_NAME,
    PROGRAMS,
    UNIVERSITIES,
    VENDORS,
)
from scripts.demo.people import (
    EMPLOYEES,
    HEAD_OF,
    Employee,
    university_contacts,
    university_signatory,
)
from scripts.demo.plans import CONTRACT_FROM, STORIES, InteractionPlan, Move, generate
from scripts.demo.processes import (
    BACKWARD_REASONS,
    SKIP_REASONS,
    TEMPLATE_BY_KEY,
    TEMPLATES,
    TEXTS,
    StageTexts,
)

SEED = 20260924
# Сколько «здоровых» взаимодействий добавить к сюжетным: вместе около 90.
GENERATED = 66

_REMARKS = (
    "Ключевой партнёр в регионе",
    "Вуз планирует второй поток",
    "Занятия ведут два преподавателя кафедры",
    "Интерес к расширению на магистратуру",
)

# Неудачный обмен описан той же фразой, что видит сотрудник при сбое.
_SYNC_ERROR = UNAVAILABLE_MESSAGE
_UNKNOWN_UNIVERSITY = "Вуз «site-99» не сопоставлен со справочником"

# Вуз с сайта, который обмен не сопоставил сам: такое название уже есть,
# решает администратор в очереди сопоставления.
_MAPPING_SITE_ID = "site-10"

# Вуз, который менеджер завёл сам: он ждёт проверки руководителем.
_PROPOSED_UNIVERSITY = {
    "name": "Национальный исследовательский Томский политехнический университет",
    "short_name": "ТПУ",
    "city": "Томск",
    "website": "https://tpu.ru",
    "description": "Вуз написал на общую почту ИТ Школы - завёл Петров, ждёт проверки",
}

# Статус продукта, соответствующий статусу программы в сюжете.
_PRODUCT_BY_PROGRAM = {
    ProgramImplementationStatus.NOT_STARTED: ProductTransferStatus.NOT_STARTED,
    ProgramImplementationStatus.IN_PROGRESS: ProductTransferStatus.IN_PROGRESS,
    ProgramImplementationStatus.IMPLEMENTED: ProductTransferStatus.TRANSFERRED,
    ProgramImplementationStatus.SUSPENDED: ProductTransferStatus.SUSPENDED,
}


@dataclass
class Summary:
    users: int = 0
    universities: int = 0
    interactions: int = 0
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
        return next(stage for stage in self.stages.values() if stage.is_initial)


@dataclass
class Visit:
    """Пребывание на этапе: событие входа и момент выхода."""

    code: str
    event: WorkflowEvent
    start: datetime
    end: datetime | None = None  # None значит, что взаимодействие и сейчас здесь
    done: bool = False  # этап пройден, а не брошен возвратом назад


@dataclass
class Timeline:
    version: LoadedVersion
    created: datetime
    events: list[WorkflowEvent] = field(default_factory=list)
    visits: list[Visit] = field(default_factory=list)
    status: InteractionStatus = InteractionStatus.IN_PROGRESS
    outcome: InteractionOutcome | None = None
    closed_at: datetime | None = None
    blocked_at: datetime | None = None

    @property
    def started(self) -> datetime:
        return next(
            event.created_at
            for event in self.events
            if event.event_type == WorkflowEventType.STARTED
        )

    @property
    def current(self) -> Visit:
        return self.visits[-1]

    def left_at(self, code: str) -> datetime | None:
        """Когда этап впервые пройден вперёд, например подписание."""
        return next(
            (visit.end for visit in self.visits if visit.code == code and visit.done), None
        )

    def entered_at(self, code: str) -> datetime | None:
        return next((visit.start for visit in self.visits if visit.code == code), None)


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

    # Общее

    def _ago(self, days: float, minutes: int = 0) -> datetime:
        return self.now - timedelta(days=days, minutes=minutes)

    def _jitter(self) -> timedelta:
        """Разброс по времени суток, чтобы события не выстраивались по часам."""
        return timedelta(minutes=self.rng.randint(30, 420))

    @staticmethod
    def _subject(employee: Employee) -> str:
        """Как пользователь представится API, так его и заводим.

        Под Keycloak это id из реалма, под заглушкой dev:<логин>.
        """
        if settings.auth_backend == "keycloak":
            return employee.keycloak_id
        return f"dev:{employee.username}"

    async def is_empty(self) -> bool:
        interactions = await self.session.scalar(
            select(func.count()).select_from(WorkflowInstance)
        )
        templates = await self.session.scalar(
            select(func.count()).select_from(WorkflowTemplate)
        )
        return not interactions and not templates

    # Основной набор

    async def load(self, generated: int = GENERATED) -> Summary:
        await self._users()
        await self._catalog()
        await self._universities()
        await self._templates()
        self.sources = {
            source.code: source for source in await sync.ensure_sources(self.session)
        }

        for plan in (*STORIES, *generate(generated, self.rng)):
            await self._interaction(plan)
        await self.session.flush()
        await self._retire_versions()

        await self._access()
        await self._external_links()
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
        for username, head in HEAD_OF.items():
            self.users[username].head_id = self.users[head].id
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
        confirmer = self.users["orlova"]
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
                status=UniversityStatus.CONFIRMED,
                confirmed_by_id=confirmer.id,
                confirmed_at=since,
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
        proposed = self._ago(2, minutes=self.rng.randint(0, 600))
        self.session.add(
            University(
                id=uuid.uuid4(),
                **_PROPOSED_UNIVERSITY,
                status=UniversityStatus.PENDING,
                origin="manual",
                created_at=proposed,
                updated_at=proposed,
            )
        )
        self.session.add_all(self.universities.values())
        await self.session.flush()
        self.session.add_all(contact for items in self.contacts.values() for contact in items)
        await self.session.flush()
        self.summary.universities = len(self.universities) + 1

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
                # Этапы и переходы добавляются в черновик: опубликованную версию база
                # менять не даст.
                version = WorkflowVersion(
                    id=uuid.uuid4(),
                    template_id=template.id,
                    version_number=version_spec.number,
                    status=WorkflowVersionStatus.DRAFT,
                    created_at=published - timedelta(days=4),
                )
                stages = {
                    stage.code: WorkflowStage(
                        id=uuid.uuid4(),
                        workflow_version_id=version.id,
                        code=stage.code,
                        name=stage.name,
                        description=stage.description,
                        sort_order=(index + 1) * 10,
                        is_initial=index == 0,
                        is_optional=stage.optional,
                        is_final=stage.final,
                        outcome=stage.outcome,
                        sla_days=stage.sla_days,
                        required_documents=[str(item) for item in stage.required],
                        program_status_on_enter=stage.program_status,
                        product_status_on_enter=stage.product_status,
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

            # Публикация: последняя версия действует, прежние устарели, начатые по ним
            # процессы идут по своей схеме.
            for index, item in enumerate(loaded):
                item.model.published_at = self._ago(spec.versions[index].published_days_ago)
                if index == len(loaded) - 1:
                    item.model.status = WorkflowVersionStatus.ACTIVE
                else:
                    item.model.status = WorkflowVersionStatus.DEPRECATED
                    item.model.deprecated_at = loaded[index + 1].model.published_at
            await self.session.flush()
            self.versions[spec.key] = loaded

    async def _retire_versions(self) -> None:
        """Устаревшая версия без открытых взаимодействий выводится из использования."""
        replaced = (WorkflowVersionStatus.DEPRECATED, WorkflowVersionStatus.RETIRED)
        for loaded in self.versions.values():
            for item in loaded:
                if item.model.status not in replaced:
                    continue
                last_open = await self.session.scalar(
                    select(func.count())
                    .select_from(WorkflowInstance)
                    .where(
                        WorkflowInstance.workflow_version_id == item.model.id,
                        WorkflowInstance.status.in_(
                            (
                                InteractionStatus.DRAFT,
                                InteractionStatus.IN_PROGRESS,
                                InteractionStatus.BLOCKED,
                            )
                        ),
                    )
                )
                if last_open:
                    item.model.status = WorkflowVersionStatus.DEPRECATED
                    item.model.retired_at = None
                elif item.model.status != WorkflowVersionStatus.RETIRED:
                    item.model.status = WorkflowVersionStatus.RETIRED
                    item.model.retired_at = self._ago(self.rng.randint(5, 40))
        await self.session.flush()

    # Взаимодействие

    def _version_at(self, template_key: str, moment: datetime) -> LoadedVersion:
        """Последняя версия, опубликованная к моменту запуска процесса."""
        versions = self.versions[template_key]
        published = [item for item in versions if item.model.published_at <= moment]
        return published[-1] if published else versions[0]

    def _active_version(self, template_key: str) -> LoadedVersion:
        return next(
            item
            for item in self.versions[template_key]
            if item.model.status == WorkflowVersionStatus.ACTIVE
        )

    def _duration(self, stage: WorkflowStage) -> timedelta:
        norm = stage.sla_days or 7
        days = max(1.0, self.rng.uniform(0.35, 0.9) * norm)
        return timedelta(days=days) + self._jitter()

    def _timeline(self, plan: InteractionPlan) -> Timeline:
        """История процесса: от последнего перехода назад к запуску."""
        moves = [step if isinstance(step, Move) else Move(step) for step in plan.route]
        latest = self.versions[plan.template][-1]

        # Сначала моменты переходов по нормам последней версии, затем выбор версии
        # по дате запуска: нормы версий различаются мало.
        moments: list[datetime] = []
        moment = self._ago(plan.days_on_stage) - self._jitter()
        codes = [latest.initial.code, *(move.stage for move in moves)]
        for index in range(len(moves) - 1, -1, -1):
            moments.insert(0, moment)
            stage = latest.stages.get(codes[index]) or latest.initial
            moment -= self._duration(stage)
        version = self._version_at(plan.template, moment)

        manager = self._responsible(plan)
        created = moment - timedelta(hours=self.rng.randint(2, 60))
        timeline = Timeline(version=version, created=created)
        timeline.events.append(
            WorkflowEvent(
                id=uuid.uuid4(),
                user_id=manager.id,
                event_type=WorkflowEventType.CREATED,
                created_at=created,
            )
        )
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
                    break  # шаблон поменяли руками, дальше путь не пройти
                raise ValueError(
                    f"{plan.label}: переход «{source} -> {move.stage}» "
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
                if transition.requires_comment and not comment:
                    comment = transition.name

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

        current = version.stages[timeline.current.code]
        if current.is_final:
            timeline.status = InteractionStatus.COMPLETED
            timeline.outcome = InteractionOutcome(current.outcome or "successful")
            timeline.closed_at = timeline.current.start
            timeline.current.done = True
        elif plan.cancelled or plan.blocked:
            since = timeline.current.start
            when = since + (self.now - since) * self.rng.uniform(0.3, 0.7)
            kind = WorkflowEventType.CANCELLED if plan.cancelled else WorkflowEventType.BLOCKED
            timeline.events.append(
                WorkflowEvent(
                    id=uuid.uuid4(),
                    from_stage_id=current.id,
                    to_stage_id=current.id,
                    user_id=manager.id,
                    event_type=kind,
                    comment=plan.cancelled or plan.blocked,
                    created_at=when,
                )
            )
            if plan.cancelled:
                timeline.status = InteractionStatus.CANCELLED
                timeline.outcome = InteractionOutcome.UNSUCCESSFUL
                timeline.closed_at = when
            else:
                timeline.status = InteractionStatus.BLOCKED
                timeline.blocked_at = when
        return timeline

    def _responsible(self, plan: InteractionPlan) -> User:
        """Кто ведёт взаимодействие. Без ответственного действия выполняет руководитель."""
        return self.users[plan.manager] if plan.manager else self.users["orlova"]

    def _number(self, plan: InteractionPlan, created: datetime) -> str:
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

    def _valid_to(self, plan: InteractionPlan, signed: date) -> date:
        if plan.valid_days_left is not None:
            return self.today + timedelta(days=plan.valid_days_left)
        # Договор заключают на целое число лет, берём первый срок с запасом.
        for years in range(1, 6):
            candidate = _add_years(signed, years) - timedelta(days=1)
            if candidate >= self.today + timedelta(days=75):
                return candidate
        return self.today + timedelta(days=365)

    def _statuses(
        self, plan: InteractionPlan, timeline: Timeline | None
    ) -> tuple[ProgramImplementationStatus, ProductTransferStatus]:
        """Статусы программ и продуктов: их ставят этапы при входе, как в процессе."""
        if plan.implementation is not None:
            return plan.implementation, _PRODUCT_BY_PROGRAM[plan.implementation]
        program = ProgramImplementationStatus.NOT_STARTED
        product = ProductTransferStatus.NOT_STARTED
        if timeline is None:
            return program, product
        entering = (
            WorkflowEventType.STARTED,
            WorkflowEventType.FORWARD,
            WorkflowEventType.SKIPPED,
        )
        for visit in timeline.visits:
            if visit.event.event_type not in entering:
                continue  # возврат назад статусы не откатывает
            stage = timeline.version.stages[visit.code]
            if stage.program_status_on_enter:
                program = ProgramImplementationStatus(stage.program_status_on_enter)
            if stage.product_status_on_enter:
                product = ProductTransferStatus(stage.product_status_on_enter)
        return program, product

    async def _interaction(self, plan: InteractionPlan) -> None:
        university = self.universities[plan.university]
        contacts = self.contacts.get(plan.university, [])
        manager = self.users[plan.manager] if plan.manager else None
        author = self._responsible(plan)
        timeline = self._timeline(plan) if plan.template else None

        if timeline is not None:
            created = timeline.created
            last_activity = max(event.created_at for event in timeline.events)
            version = timeline.version
        else:
            created = self._ago(plan.days_on_stage) - self._jitter()
            last_activity = created
            version = self._active_version("main")

        remark = plan.notes[0] if plan.notes else None
        if remark is None and not plan.light and self.rng.random() < 0.25:
            remark = self.rng.choice(_REMARKS)

        instance = WorkflowInstance(
            id=uuid.uuid4(),
            university_id=university.id,
            manager_id=manager.id if manager else None,
            title=plan.title,
            source=plan.source,
            comment=remark,
            created_by_id=author.id,
            workflow_version_id=version.model.id,
            status=InteractionStatus.DRAFT,
            created_at=created,
            updated_at=last_activity,
        )
        if timeline is not None:
            current = timeline.current
            instance.current_stage_id = version.stages[current.code].id
            instance.current_stage_started_at = current.start
            instance.started_at = timeline.started
            instance.status = timeline.status
            instance.outcome = timeline.outcome
            if timeline.status == InteractionStatus.BLOCKED:
                instance.blocked_reason = plan.blocked
                instance.blocked_at = timeline.blocked_at
            if timeline.closed_at is not None:
                instance.closed_at = timeline.closed_at
                instance.closed_by_id = author.id
                if timeline.outcome != InteractionOutcome.SUCCESSFUL:
                    instance.closure_reason = plan.closure or ClosureReason.OTHER
                    instance.closure_comment = plan.cancelled or current.event.comment
        self.session.add(instance)
        await self.session.flush()

        _, product_links = self._composition(plan, instance, timeline, created)
        self._contacts(instance, contacts)
        contract = self._contract(plan, instance, timeline, last_activity)
        if contract is not None and plan.licenses:
            handover = timeline.left_at("signing") if timeline else None
            handover = handover or (
                datetime.combine(contract.signed_at, datetime.min.time(), UTC)
                if contract.signed_at
                else None
            )
            if handover is not None:
                self._licenses(plan, contract, product_links, handover)

        context = self._context(plan, contract, university, contacts, manager)
        if timeline is not None:
            if not plan.light:
                self._entry_comments(timeline, context)
            for event in timeline.events:
                event.workflow_instance_id = instance.id
            self.session.add_all(timeline.events)
            self.summary.events += len(timeline.events)
        else:
            self.session.add(
                WorkflowEvent(
                    id=uuid.uuid4(),
                    workflow_instance_id=instance.id,
                    user_id=author.id,
                    event_type=WorkflowEventType.CREATED,
                    created_at=created,
                )
            )
            self.summary.events += 1
        # Комментарии и файлы ссылаются на события процесса без relationship,
        # поэтому сначала события должны попасть в базу.
        await self.session.flush()

        if timeline is not None and not plan.light:
            self._stage_extras(plan, instance, timeline, context)
        if plan.notes:
            for text in plan.notes:
                self._comment(instance, author, text, self._between(created, self.now), None)
        if plan.request:
            self.session.add(
                ExternalLink(
                    id=uuid.uuid4(),
                    source_id=self.sources["site"].id,
                    entity_type=sync.INTERACTION,
                    entity_id=instance.id,
                    external_id=plan.request,
                )
            )
        self.summary.interactions += 1

    def _composition(
        self,
        plan: InteractionPlan,
        instance: WorkflowInstance,
        timeline: Timeline | None,
        created: datetime,
    ) -> tuple[list[InteractionProgram], list[InteractionProduct]]:
        """Программы, продукты и связи «продукт используется в программе»."""
        program_status, product_status = self._statuses(plan, timeline)
        programs = [
            InteractionProgram(
                id=uuid.uuid4(),
                workflow_instance_id=instance.id,
                program_id=self.programs[name].id,
                implementation_status=program_status,
                created_at=created,
            )
            for name in plan.programs
        ]
        products = [
            InteractionProduct(
                id=uuid.uuid4(),
                workflow_instance_id=instance.id,
                product_id=self.products[name].id,
                transfer_status=product_status,
                created_at=created,
            )
            for name in plan.products
        ]
        self.session.add_all([*programs, *products])

        head = self.users[HEAD_OF.get(plan.manager or "", "orlova")]
        by_name = dict(zip(plan.programs, programs, strict=True))
        for name, product in zip(plan.products, products, strict=True):
            if name in plan.unlinked:
                continue
            users = [
                program
                for program_name, program in by_name.items()
                if name in PROGRAM_BY_NAME[program_name].products
            ]
            if users:
                self.session.add_all(
                    InteractionProgramProduct(
                        interaction_program_id=program.id,
                        interaction_product_id=product.id,
                        created_at=created,
                    )
                    for program in users
                )
            elif programs:
                # Связи нет в справочнике: осознанное исключение руководителя.
                self.session.add(
                    InteractionProgramProduct(
                        interaction_program_id=programs[0].id,
                        interaction_product_id=product.id,
                        is_exception=True,
                        exception_comment=(
                            "Продукт нужен вузу для практикума этой программы - "
                            "согласовано руководителем"
                        ),
                        created_by_id=head.id,
                        created_at=created,
                    )
                )
        return programs, products

    def _contacts(self, instance: WorkflowInstance, contacts: list[UniversityContact]) -> None:
        if not contacts:
            return
        self.session.add(
            InteractionContact(
                workflow_instance_id=instance.id,
                contact_id=contacts[0].id,
                role="Ответственный от вуза",
                is_primary=True,
            )
        )
        if len(contacts) > 1 and self.rng.random() < 0.5:
            self.session.add(
                InteractionContact(
                    workflow_instance_id=instance.id,
                    contact_id=contacts[1].id,
                    role="Куратор программ",
                    is_primary=False,
                )
            )

    def _contract(
        self,
        plan: InteractionPlan,
        instance: WorkflowInstance,
        timeline: Timeline | None,
        last_activity: datetime,
    ) -> Contract | None:
        """Договор появляется на обмене документами, до подписания он черновик."""
        if timeline is None or not plan.has_contract:
            return None
        drafted = timeline.entered_at(CONTRACT_FROM) or timeline.started
        if timeline.version.template_key == "short":
            signed_at = timeline.left_at("signing") or (
                timeline.current.start
                if timeline.status == InteractionStatus.COMPLETED
                and timeline.outcome == InteractionOutcome.SUCCESSFUL
                else None
            )
        else:
            signed_at = timeline.left_at("signing")
        signed = signed_at.date() if signed_at else None

        status = plan.contract_status or (
            ContractStatus.ACTIVE if signed else ContractStatus.DRAFT
        )
        if not signed and timeline.outcome == InteractionOutcome.UNSUCCESSFUL:
            status = ContractStatus.CANCELLED  # не подписан, а переговоры закрыты
        valid_to = self._valid_to(plan, signed) if signed else None
        closure = None
        if status == ContractStatus.CLOSED:
            closure = (
                ContractClosureReason.EXPIRED
                if valid_to and valid_to < self.today
                else ContractClosureReason.FULFILLED
            )

        # Подписывает не ответственный от вуза, а ректор или первый проректор.
        signatory = university_signatory(plan.university, drafted.year)
        contract = Contract(
            id=uuid.uuid4(),
            workflow_instance_id=instance.id,
            number=self._number(plan, drafted),
            title=plan.title,
            signed_at=signed,
            valid_from=signed,
            valid_to=valid_to,
            status=status,
            closure_reason=closure,
            signatory_name=signatory.full_name,
            signatory_position=signatory.position,
            signatory_basis=signatory.basis,
            created_at=drafted,
            updated_at=max(drafted, signed_at or drafted, last_activity),
        )
        self.session.add(contract)
        self.summary.contracts += 1
        return contract

    def _licenses(
        self,
        plan: InteractionPlan,
        contract: Contract,
        links: list[InteractionProduct],
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
                    contract_id=contract.id,
                    interaction_product_id=link.id,
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

    # Комментарии и файлы этапов

    def _context(
        self,
        plan: InteractionPlan,
        contract: Contract | None,
        university: University,
        contacts: list[UniversityContact],
        manager: User | None,
    ) -> dict[str, object]:
        template = TEMPLATE_BY_KEY[plan.template or "main"]
        return {
            "number": contract.number if contract else "б/н",
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
        """Комментарии к переходам вперёд, если сюжет не задал свои."""
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
        plan: InteractionPlan,
        instance: WorkflowInstance,
        timeline: Timeline,
        context: dict[str, object],
    ) -> None:
        """Заметки менеджера и файлы, пока взаимодействие стояло на этапе."""
        texts = TEXTS[timeline.version.template_key]
        author = self._responsible(plan)
        for visit in timeline.visits:
            stage_texts = texts.get(visit.code, StageTexts())
            context["date"] = visit.start.strftime("%d.%m.%Y")

            if stage_texts.notes and self.rng.random() < 0.45:
                text = self.rng.choice(stage_texts.notes).format_map(context)
                when = self._between(visit.start, visit.end)
                self._comment(instance, author, text, when, visit.event.id)

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
                    instance,
                    author,
                    visit.event.id,
                    upload.kind,
                    str(upload.document),
                    name,
                    stage,
                    when,
                    context,
                )

    def _comment(
        self,
        instance: WorkflowInstance,
        author: User,
        text: str,
        when: datetime,
        event_id: uuid.UUID | None,
    ) -> None:
        self.session.add(
            Comment(
                id=uuid.uuid4(),
                workflow_instance_id=instance.id,
                workflow_event_id=event_id,
                author_id=author.id,
                text=text,
                created_at=when,
            )
        )
        self.summary.comments += 1

    def _attachment(
        self,
        instance: WorkflowInstance,
        author: User,
        event_id: uuid.UUID,
        kind: str,
        document_type: str,
        name: str,
        stage: WorkflowStage,
        when: datetime,
        context: dict[str, object],
    ) -> None:
        title = PurePosixPath(name).stem.removesuffix(".log")
        lines = [
            f"Вуз: {context['university_name']}",
            f"Договор: {context['number']}",
            f"Этап: {stage.name}",
            f"Программы: {context['programs']}",
            f"Ответственный ИТ Школы: {context['manager']}",
            f"Представитель вуза: {context['contact']}",
            f"Дата: {when:%d.%m.%Y}",
        ]
        data = files.document(kind, title, lines, _table_for(name, context, self.rng))

        file_id = uuid.uuid4()
        relative = f"interactions/{instance.id}/{file_id}.{kind}"
        target = storage.absolute_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        self.session.add(
            Attachment(
                id=file_id,
                workflow_instance_id=instance.id,
                workflow_event_id=event_id,
                uploaded_by=author.id,
                document_type=document_type,
                original_name=name,
                storage_path=relative,
                mime_type=storage.ALLOWED_TYPES[kind],
                size_bytes=len(data),
                created_at=when,
            )
        )
        self.summary.attachments += 1

    # Права и доступ

    async def _access(self) -> None:
        """Что видно в «Пользователи и права» сразу после загрузки.

        Иванова замещает Петрова в отпуске: у неё точечный доступ к его вузу. Фёдорову
        временно открыта вся организация, Орлова видит персональные данные студентов
        и журнал обмена. У администратора бизнес-данных нет.
        """
        orlova, fedorov = self.users["orlova"], self.users["fedorov"]
        self.session.add(
            UserUniversityAccess(
                user_id=self.users["ivanova"].id,
                university_id=self.universities["mirea"].id,
                reason="Замещает Петрова на время отпуска",
                granted_by_id=self.users["admin"].id,
                expires_at=self.now + timedelta(days=12),
                created_at=self._ago(2),
            )
        )
        fedorov.data_scope = DataScope.ALL
        fedorov.data_scope_reason = "Подготовка годового отчёта по всем вузам"
        fedorov.data_scope_expires_at = self.now + timedelta(days=14)
        orlova.permissions = [
            str(Permission.VIEW_PERSONAL_DATA),
            str(Permission.VIEW_INTEGRATION_LOG),
        ]
        await self.session.flush()

    # Журналы обмена и загрузок

    async def _external_links(self) -> None:
        """Связи с объектами LMS и сайта: повторный обмен обновит те же записи.

        Одна запись сайта оставлена без связи, её решает администратор в очереди
        сопоставления.
        """
        payloads = {
            "lms": LmsAdapter.parse(load_fixture("lms")),
            "site": SiteAdapter.parse(load_fixture("site")),
        }
        universities = {
            university.name: university for university in self.universities.values()
        }
        links: list[tuple[str, str, uuid.UUID, str]] = []
        lms = payloads["lms"]
        for item in lms.programs:
            if item.name in self.programs:
                links.append(
                    ("lms", sync.PROGRAM, self.programs[item.name].id, item.external_id)
                )
        for item in lms.products:
            if item.name in self.products:
                links.append(
                    ("lms", sync.PRODUCT, self.products[item.name].id, item.external_id)
                )
        for item in payloads["site"].universities:
            university = universities.get(item.name)
            if university is None:
                continue
            if item.external_id == _MAPPING_SITE_ID:
                self.session.add(
                    IntegrationMapping(
                        id=uuid.uuid4(),
                        source_id=self.sources["site"].id,
                        entity_type=sync.UNIVERSITY,
                        external_id=item.external_id,
                        external_name=item.name,
                        payload={
                            "name": item.name,
                            "short_name": item.short_name,
                            "city": item.city,
                            "website": item.website,
                        },
                        suggested_entity_id=university.id,
                        status=MappingStatus.PENDING,
                        created_at=self._ago(2),
                    )
                )
                continue
            links.append(("site", sync.UNIVERSITY, university.id, item.external_id))
        self.session.add_all(
            ExternalLink(
                id=uuid.uuid4(),
                source_id=self.sources[code].id,
                entity_type=entity_type,
                entity_id=entity_id,
                external_id=external_id,
            )
            for code, entity_type, entity_id, external_id in links
        )
        await self.session.flush()

    async def _integration_history(self) -> None:
        """Прошлые запуски синхронизации. Последний обмен с сайтом упал, поэтому
        на главной висит тревога, её снимает ручной запуск обмена.
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
                manual = self.rng.random() < 0.5
                if failed:
                    status = IntegrationRunStatus.FAILED
                elif broken:
                    status = IntegrationRunStatus.PARTIAL
                else:
                    status = IntegrationRunStatus.SUCCESS
                run = IntegrationRun(
                    id=uuid.uuid4(),
                    source_id=self.sources[code].id,
                    triggered_by=admin.id if manual else None,
                    trigger="manual" if manual else "schedule",
                    status=status,
                    started_at=started,
                    finished_at=started + timedelta(seconds=self.rng.randint(2, 40)),
                    attempts=3 if failed else 1,
                    records_received=0 if failed else size,
                    records_created=created,
                    records_updated=0 if failed else size - created - broken,
                    records_failed=broken,
                    error_message=_SYNC_ERROR if failed else None,
                )
                self.session.add(run)
                if broken:
                    self.session.add(
                        IntegrationRunError(
                            id=uuid.uuid4(),
                            run_id=run.id,
                            entity_type=sync.INTERACTION,
                            external_id="req-2026-026",
                            message=_UNKNOWN_UNIVERSITY,
                        )
                    )
        await self.session.flush()

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

    # Добавка для нагрузки

    async def load_extra(self, count: int, batch: int = 200) -> int:
        """Ещё ``count`` взаимодействий поверх того, что уже в базе."""
        await self._attach_existing()
        self.rng = random.Random(SEED + len(self.numbers))
        plans = generate(count, self.rng, light=True)
        for index, plan in enumerate(plans, start=1):
            await self._interaction(plan)
            if index % batch == 0:
                await self.session.flush()
                # Сессия не должна копить десятки тысяч объектов.
                self.session.expunge_all()
                print(f"  добавлено взаимодействий: {index} из {count}")
        await self.session.flush()
        await self._attach_versions()
        await self._retire_versions()
        return len(plans)

    async def _attach_existing(self) -> None:
        """Справочники и шаблоны берём из базы в текущем виде."""
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

        await self._attach_versions()

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

    async def _attach_versions(self) -> None:
        """Опубликованные версии шаблонов из базы с этапами и переходами."""
        self.versions = {}
        template_keys = {spec.name: spec.key for spec in TEMPLATES}
        versions = (
            await self.session.execute(
                select(WorkflowVersion, WorkflowTemplate.name)
                .join(WorkflowTemplate)
                .where(WorkflowVersion.status != WorkflowVersionStatus.DRAFT)
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
