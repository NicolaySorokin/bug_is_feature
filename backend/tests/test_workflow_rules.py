"""Проверка правил процесса без обращения к базе.

Разбор переходов и вычисление состояний этапов - чистые функции, поэтому
здесь достаточно объектов моделей в памяти и сессии-заглушки.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.enums import (
    ClosureReason,
    InteractionOutcome,
    StageState,
    WorkflowEventType,
    WorkflowInstanceStatus,
)
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

    async def get(self, _model: object, _key: object) -> None:
        return None


def make_stage(
    code: str,
    order: int,
    *,
    initial: bool = False,
    optional: bool = False,
    final: bool = False,
    outcome: InteractionOutcome | None = None,
):
    return WorkflowStage(
        id=uuid.uuid4(),
        code=code,
        name=code,
        sort_order=order,
        is_initial=initial,
        is_optional=optional,
        is_final=final,
        outcome=outcome or (InteractionOutcome.SUCCESSFUL if final else None),
        required_documents=[],
    )


@pytest.fixture
def version() -> WorkflowVersion:
    # Стартовый этап отмечен явно - и не первым по сортировке.
    contact = make_stage("contact", 30, initial=True)
    meeting = make_stage("meeting", 20)
    documents = make_stage("documents", 35, optional=True)
    approval = make_stage("approval", 40)
    signing = make_stage("signing", 50, final=True)
    refusal = make_stage("refusal", 60, final=True, outcome=InteractionOutcome.UNSUCCESSFUL)

    version = WorkflowVersion(id=uuid.uuid4(), version_number=1)
    version.stages = [contact, meeting, documents, approval, signing, refusal]
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
        WorkflowTransition(
            id=uuid.uuid4(),
            workflow_version_id=version.id,
            from_stage_id=approval.id,
            to_stage_id=refusal.id,
            is_backward=False,
            requires_comment=True,
        ),
    ]
    return version


def stage(version: WorkflowVersion, code: str) -> WorkflowStage:
    return next(s for s in version.stages if s.code == code)


@pytest.fixture
def instance(version: WorkflowVersion) -> WorkflowInstance:
    return WorkflowInstance(
        id=uuid.uuid4(),
        university_id=uuid.uuid4(),
        workflow_version_id=version.id,
        current_stage_id=stage(version, "contact").id,
        status=WorkflowInstanceStatus.IN_PROGRESS,
        started_at=datetime.now(UTC),
    )


@pytest.fixture
def user() -> User:
    return User(id=uuid.uuid4(), keycloak_id="k", username="u", full_name="U")


def test_initial_stage_is_marked_explicitly(version: WorkflowVersion) -> None:
    assert service.initial_stage(version).code == "contact"
    for item in version.stages:
        item.is_initial = False
    with pytest.raises(service.WorkflowError):
        service.initial_stage(version)


def test_available_transitions_limited_to_current_stage(version, instance) -> None:
    available = service.available_transitions(version, instance.current_stage_id)
    assert [t.to_stage_id for t in available] == [stage(version, "meeting").id]


async def test_forward_transition_records_event(version, instance, user) -> None:
    session = FakeSession()
    event = await service.move(session, instance, version, stage(version, "meeting").id, user)

    assert event.event_type == WorkflowEventType.FORWARD
    assert instance.current_stage_id == stage(version, "meeting").id
    assert event in session.added


async def test_transition_not_in_template_is_rejected(version, instance, user) -> None:
    session = FakeSession()
    with pytest.raises(service.WorkflowError):
        await service.move(session, instance, version, stage(version, "signing").id, user)
    assert instance.current_stage_id == stage(version, "contact").id


async def test_backward_transition_requires_comment(version, instance, user) -> None:
    instance.current_stage_id = stage(version, "approval").id
    session = FakeSession()

    with pytest.raises(service.WorkflowError):
        await service.move(session, instance, version, stage(version, "meeting").id, user)

    event = await service.move(
        session,
        instance,
        version,
        stage(version, "meeting").id,
        user,
        comment="Не хватает документов",
    )
    assert event.event_type == WorkflowEventType.BACKWARD


async def test_manager_skips_only_optional_stage(version, instance, user) -> None:
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
        comment="Встреча уже была вне системы",
        skip=True,
        may_skip_required=True,
    )
    assert event.event_type == WorkflowEventType.SKIPPED


async def test_final_stage_completes_instance(version, instance, user) -> None:
    instance.current_stage_id = stage(version, "approval").id
    session = FakeSession()

    await service.move(session, instance, version, stage(version, "signing").id, user)
    assert instance.status == WorkflowInstanceStatus.COMPLETED
    assert instance.outcome == InteractionOutcome.SUCCESSFUL
    assert instance.closed_at is not None
    assert instance.closed_by_id == user.id


async def test_unsuccessful_final_needs_reason(version, instance, user) -> None:
    instance.current_stage_id = stage(version, "approval").id
    session = FakeSession()
    refusal = stage(version, "refusal").id

    with pytest.raises(service.WorkflowError):
        await service.move(session, instance, version, refusal, user, comment="Отказ")
    await service.move(
        session,
        instance,
        version,
        refusal,
        user,
        comment="Вуз выбрал другого партнёра",
        closure_reason=ClosureReason.UNIVERSITY_REFUSED,
    )
    assert instance.status == WorkflowInstanceStatus.COMPLETED
    assert instance.outcome == InteractionOutcome.UNSUCCESSFUL
    assert instance.closure_reason == ClosureReason.UNIVERSITY_REFUSED


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
