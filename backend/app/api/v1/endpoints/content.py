"""Комментарии и файлы взаимодействия.

Функциональные требования 2 и 3 ТЗ: комментарий при переходе от статуса
к статусу и файлы в статусах. И комментарий, и файл можно привязать
к событию процесса - тогда они видны в карточке этапа. У файла есть тип
документа: по нему проверяется комплектность этапа (пункт 21 перечня
исправлений).
"""

import uuid

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserDep,
    InteractionDep,
    PrincipalDep,
    SessionDep,
    WritableInteractionDep,
)
from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError
from app.enums import DocumentType
from app.models.content import Attachment, Comment
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.schemas.content import AttachmentRead, CommentCreate, CommentRead
from app.services import access, storage
from app.services.access import Action

router = APIRouter(prefix="/interactions", tags=["comments & files"])
files_router = APIRouter(prefix="/attachments", tags=["comments & files"])


async def _check_event(
    session: SessionDep, interaction_id: uuid.UUID, event_id: uuid.UUID | None
) -> None:
    """Событие процесса должно принадлежать этому же взаимодействию."""
    if event_id is None:
        return
    found = await session.scalar(
        select(WorkflowEvent.id).where(
            WorkflowEvent.id == event_id, WorkflowEvent.workflow_instance_id == interaction_id
        )
    )
    if found is None:
        raise NotFoundError("Событие процесса не найдено в этом взаимодействии")


# --- Комментарии --------------------------------------------------------------


@router.get(
    "/{interaction_id}/comments",
    response_model=list[CommentRead],
    summary="Комментарии взаимодействия",
)
async def list_comments(
    interaction: InteractionDep,
    session: SessionDep,
    workflow_event_id: uuid.UUID | None = None,
) -> list[CommentRead]:
    statement = (
        select(Comment)
        .where(Comment.workflow_instance_id == interaction.id)
        .options(selectinload(Comment.author))
        .order_by(Comment.created_at)
    )
    if workflow_event_id is not None:
        statement = statement.where(Comment.workflow_event_id == workflow_event_id)
    result = await session.execute(statement)
    return [CommentRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/{interaction_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить комментарий",
)
async def create_comment(
    interaction: WritableInteractionDep,
    payload: CommentCreate,
    session: SessionDep,
    user: CurrentUserDep,
) -> CommentRead:
    await _check_event(session, interaction.id, payload.workflow_event_id)
    comment = Comment(
        workflow_instance_id=interaction.id,
        workflow_event_id=payload.workflow_event_id,
        author_id=user.id,
        text=payload.text,
    )
    session.add(comment)
    await session.flush()
    await session.refresh(comment, ["author"])
    return CommentRead.model_validate(comment)


# --- Вложения -----------------------------------------------------------------


@router.get(
    "/{interaction_id}/attachments",
    response_model=list[AttachmentRead],
    summary="Файлы взаимодействия",
)
async def list_attachments(
    interaction: InteractionDep,
    session: SessionDep,
    workflow_event_id: uuid.UUID | None = None,
) -> list[AttachmentRead]:
    statement = (
        select(Attachment)
        .where(Attachment.workflow_instance_id == interaction.id)
        .options(selectinload(Attachment.uploader))
        .order_by(Attachment.created_at)
    )
    if workflow_event_id is not None:
        statement = statement.where(Attachment.workflow_event_id == workflow_event_id)
    result = await session.execute(statement)
    return [AttachmentRead.from_model(row, settings.api_v1_prefix) for row in result.scalars()]


@router.post(
    "/{interaction_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл",
    description=(
        "Допустимые форматы: png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx. "
        "Тип документа (document_type) нужен для обязательных документов этапа. "
        "Файл можно привязать к событию процесса - тогда он появится в карточке этапа."
    ),
)
async def upload_attachment(
    interaction: WritableInteractionDep,
    session: SessionDep,
    user: CurrentUserDep,
    file: UploadFile = File(description="Файл документа"),
    workflow_event_id: uuid.UUID | None = Form(default=None),
    document_type: DocumentType | None = Form(default=None),
) -> AttachmentRead:
    await _check_event(session, interaction.id, workflow_event_id)
    stored = await storage.save_upload(file, f"interactions/{interaction.id}")

    attachment = Attachment(
        workflow_instance_id=interaction.id,
        workflow_event_id=workflow_event_id,
        uploaded_by=user.id,
        document_type=document_type or DocumentType.OTHER,
        original_name=stored.original_name,
        storage_path=stored.storage_path,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
    )
    session.add(attachment)
    await session.flush()
    await session.refresh(attachment, ["uploader"])
    return AttachmentRead.from_model(attachment, settings.api_v1_prefix)


async def _get_attachment(
    session: SessionDep,
    attachment_id: uuid.UUID,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> Attachment:
    statement = (
        select(Attachment)
        .where(Attachment.id == attachment_id)
        .options(
            selectinload(Attachment.uploader),
            selectinload(Attachment.interaction).selectinload(WorkflowInstance.university),
        )
    )
    attachment = (await session.execute(statement)).scalar_one_or_none()
    if attachment is None:
        raise NotFoundError("Файл не найден")
    await access.ensure_interaction_read(session, attachment.interaction, principal, user)
    return attachment


@files_router.get("/{attachment_id}/download", summary="Скачать файл")
async def download_attachment(
    attachment_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> FileResponse:
    attachment = await _get_attachment(session, attachment_id, principal, user)
    path = storage.absolute_path(attachment.storage_path)
    if not path.is_file():
        raise NotFoundError("Файл не найден в хранилище")
    # FileResponse отдаёт файл потоком и сам проставляет имя в Content-Disposition.
    return FileResponse(
        path,
        media_type=attachment.mime_type or "application/octet-stream",
        filename=attachment.original_name,
    )


@files_router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить файл",
)
async def delete_attachment(
    attachment_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> None:
    attachment = await _get_attachment(session, attachment_id, principal, user)
    await access.ensure_interaction_write(session, attachment.interaction, principal, user)
    # Свой файл удаляет автор, чужой - только руководитель.
    if attachment.uploaded_by != user.id and not access.can(
        principal, user, Action.ASSIGN_RESPONSIBLE
    ):
        raise ForbiddenError("Удалять чужие файлы может только руководитель")
    storage.delete(attachment.storage_path)
    await session.delete(attachment)
