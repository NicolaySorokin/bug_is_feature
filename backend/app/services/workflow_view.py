"""Представление процесса для вкладки «Процесс»: схема, состояния, история."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.schemas.workflow import (
    EventRead,
    InstanceView,
    StageInstanceState,
    TransitionRead,
    VersionGraph,
)
from app.services import workflow as workflow_service


async def build_view(session: AsyncSession, instance: WorkflowInstance) -> InstanceView:
    """Схема из версии шаблона, состояния этапов из истории."""
    version = await workflow_service.load_version(session, instance.workflow_version_id)
    events = list(
        (
            await session.execute(
                select(WorkflowEvent)
                .where(WorkflowEvent.workflow_instance_id == instance.id)
                .options(selectinload(WorkflowEvent.user))
                .order_by(WorkflowEvent.created_at)
            )
        ).scalars()
    )
    states = workflow_service.compute_stage_states(version, instance, events)
    transitions = (
        workflow_service.available_transitions(version, instance.current_stage_id)
        if instance.status in workflow_service.OPEN
        else []
    )
    return InstanceView(
        id=instance.id,
        university_id=instance.university_id,
        manager_id=instance.manager_id,
        workflow_version_id=instance.workflow_version_id,
        current_stage_id=instance.current_stage_id,
        status=instance.status,
        outcome=instance.outcome,
        closure_reason=instance.closure_reason,
        blocked_reason=instance.blocked_reason,
        current_stage_started_at=instance.current_stage_started_at,
        started_at=instance.started_at,
        closed_at=instance.closed_at,
        version=VersionGraph.model_validate(version),
        stage_states=[
            StageInstanceState(stage_id=stage_id, state=state)
            for stage_id, state in states.items()
        ],
        available_transitions=[TransitionRead.model_validate(t) for t in transitions],
        events=[EventRead.model_validate(event) for event in events],
    )
