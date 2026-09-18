"""Проверка правил процесса без обращения к базе.

Разбор переходов и вычисление состояний этапов - чистые функции, поэтому
здесь достаточно объектов моделей в памяти и сессии-заглушки.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import Principal
from app.enums import Role, StageState, WorkflowEventType, WorkflowInstanceStatus
from app.models.user import User
from app.models.workflow import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStage,
    WorkflowTransition,
    WorkflowVersion,
)
from app.services import workflow as service


class FakeSession:
    """Минимальная замена AsyncSession: собирает добавленные объекты."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def make_stage(code: str, order: int, *, optional: bool = False, final: bool = False):
    return WorkflowStage(
        id=uuid.uuid4(),
        code=code,
        name=code,
        sort_order=order,
        is_optional=optional,
        is_final=final,
    )


@pytest.fixture
def version() -> WorkflowVersion:
    contact = make_stage("contact", 10)
    meeting = make_stage("meeting", 20)
    documents = make_stage("documents", 30, optional=True)
    approval = make_stage("approval", 40)
    signing = make_stage("signing", 50, final=True)

    version = WorkflowVersion(id=uuid.uuid4(), version_number=1)
    version.stages = [contact, meeting, documents, approval, signing]
    version.transitions = [
        WorkflowTransition(
            id=uuid.uuid4(),
            workflow_version_id=version.id,
            from_stage_id=contact.id,
            to_stage_id=meeting.id,
            is_backward=False,
            requires_comment=False,
        ),
        WorkflowTransition(
            id=uuid.uuid4(),
            workflow_version_id=version.id,
            from_stage_id=meeting.id,
            to_stage_id=documents.id,
            is_backward=False,
            requires_comment=False,
        ),
        WorkflowTransition(
            id=uuid.uuid4(),
            workflow_version_id=version.id,
            from_stage_id=documents.id,
            to_stage_id=approval.id,
            is_backward=False,
            requires_comment=False,
        ),
        WorkflowTransition(
            id=uuid.uuid4(),
            workflow_version_id=version.id,
            from_stage_id=approval.id,
            to_stage_id=meeting.id,
            is_backward=True,
            requires_comment=True,
        ),
        WorkflowTransition(
            id=uuid.uuid4(),
            workflow_version_id=version.id,
            from_stage_id=approval.id,
            to_stage_id=signing.id,
            is_backward=False,
            requires_comment=False,
        ),
    ]
    return version


def stage(version: WorkflowVersion, code: str) -> WorkflowStage:
    return next(s for s in version.stages if s.code == code)


@pytest.fixture
def instance(version: WorkflowVersion) -> WorkflowInstance:
    return WorkflowInstance(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        workflow_version_id=version.id,
        current_stage_id=stage(version, "contact").id,
        status=WorkflowInstanceStatus.IN_PROGRESS,
        started_at=datetime.now(UTC),
    )


@pytest.fixture
def user() -> User:
    return User(id=uuid.uuid4(), keycloak_id="k", username="u", full_name="U")


@pytest.fixture
def manager() -> Principal:
    return Principal(subject="k", username="u", full_name="U", roles=frozenset({Role.MANAGER}))


@pytest.fixture
def head() -> Principal:
    return Principal(subject="h", username="h", full_name="H", roles=frozenset({Role.HEAD}))


def test_initial_stage_is_lowest_sort_order(version: WorkflowVersion) -> None:
    assert service.initial_stage(version).code == "contact"


def test_available_transitions_limited_to_current_stage(version, instance) -> None:
    available = service.available_transitions(version, instance.current_stage_id)
    assert [t.to_stage_id for t in available] == [stage(version, "meeting").id]


async def test_forward_transition_records_event(version, instance, user, manager) -> None:
    session = FakeSession()
    event = await service.move(
        session, instance, version, stage(version, "meeting").id, user, manager
    )

    assert event.event_type == WorkflowEventType.FORWARD
    assert instance.current_stage_id == stage(version, "meeting").id
    assert event in session.added


async def test_transition_not_in_template_is_rejected(
    version, instance, user, manager
) -> None:
    session = FakeSession()
    with pytest.raises(service.WorkflowError):
        await service.move(
            session, instance, version, stage(version, "signing").id, user, manager
        )
    assert instance.current_stage_id == stage(version, "contact").id


async def test_backward_transition_requires_comment(version, instance, user, manager) -> None:
    instance.current_stage_id = stage(version, "approval").id
    session = FakeSession()

    with pytest.raises(service.WorkflowError):
        await service.move(
            session, instance, version, stage(version, "meeting").id, user, manager
        )

    event = await service.move(
        session,
        instance,
        version,
        stage(version, "meeting").id,
        user,
        manager,
        comment="Не хватает документов",
    )
    assert event.event_type == WorkflowEventType.BACKWARD


async def test_manager_skips_only_optional_stage(
    version, instance, user, manager, head
) -> None:
    instance.current_stage_id = stage(version, "meeting").id
    session = FakeSession()

    # «Встреча» обязательна - менеджеру пропуск недоступен.
    with pytest.raises(service.WorkflowError):
        await service.move(
            session,
            instance,
            version,
            stage(version, "documents").id,
            user,
            manager,
            comment="Не нужна",
            skip=True,
        )

    # Руководителю - доступен.
    event = await service.move(
        session,
        instance,
        version,
        stage(version, "documents").id,
        user,
        head,
        comment="Встреча уже была вне системы",
        skip=True,
    )
    assert event.event_type == WorkflowEventType.SKIPPED


async def test_final_stage_completes_instance(version, instance, user, manager) -> None:
    instance.current_stage_id = stage(version, "approval").id
    session = FakeSession()

    await service.move(
        session, instance, version, stage(version, "signing").id, user, manager
    )
    assert instance.status == WorkflowInstanceStatus.COMPLETED
    assert instance.completed_at is not None


def test_stage_states_derived_from_history(version, instance) -> None:
    base = datetime.now(UTC)
    instance.current_stage_id = stage(version, "approval").id
    events = [
        WorkflowEvent(
            workflow_instance_id=instance.id,
            from_stage_id=None,
            to_stage_id=stage(version, "contact").id,
            event_type=WorkflowEventType.STARTED,
            created_at=base,
        ),
        WorkflowEvent(
            workflow_instance_id=instance.id,
            from_stage_id=stage(version, "contact").id,
            to_stage_id=stage(version, "meeting").id,
            event_type=WorkflowEventType.FORWARD,
            created_at=base + timedelta(minutes=1),
        ),
        WorkflowEvent(
            workflow_instance_id=instance.id,
            from_stage_id=stage(version, "meeting").id,
            to_stage_id=stage(version, "documents").id,
            event_type=WorkflowEventType.FORWARD,
            created_at=base + timedelta(minutes=2),
        ),
        WorkflowEvent(
            workflow_instance_id=instance.id,
            from_stage_id=stage(version, "documents").id,
            to_stage_id=stage(version, "approval").id,
            event_type=WorkflowEventType.SKIPPED,
            created_at=base + timedelta(minutes=3),
        ),
    ]

    states = service.compute_stage_states(version, instance, events)

    assert states[stage(version, "contact").id] == StageState.COMPLETED
    assert states[stage(version, "meeting").id] == StageState.COMPLETED
    assert states[stage(version, "documents").id] == StageState.SKIPPED
    assert states[stage(version, "approval").id] == StageState.ACTIVE
    assert states[stage(version, "signing").id] == StageState.NOT_STARTED


def test_blocked_instance_marks_current_stage(version, instance) -> None:
    instance.status = WorkflowInstanceStatus.BLOCKED
    states = service.compute_stage_states(version, instance, [])
    assert states[instance.current_stage_id] == StageState.BLOCKED
