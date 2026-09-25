"""Комментарии и вложения по договору.

Функциональные требования 2 и 3 ТЗ: комментарий при переходе от статуса
к статусу и файлы в статусах. И комментарий, и файл можно привязать
к событию процесса - тогда они видны в карточке этапа.
"""

import uuid

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import ContractDep, CurrentUserDep, PrincipalDep, SessionDep
from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError
from app.enums import Role
from app.models.content import Attachment, Comment
from app.models.contract import Contract
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.schemas.content import AttachmentRead, CommentCreate, CommentRead
from app.services import access, storage

router = APIRouter(prefix="/contracts", tags=["comments & files"])
files_router = APIRouter(prefix="/attachments", tags=["comments & files"])


async def _check_event_belongs_to_contract(
    session: SessionDep, contract_id: uuid.UUID, event_id: uuid.UUID | None
) -> None:
    """Событие процесса должно принадлежать этому же договору."""
    if event_id is None:
        return
    statement = (
        select(WorkflowEvent.id)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowEvent.workflow_instance_id)
        .where(WorkflowEvent.id == event_id, WorkflowInstance.contract_id == contract_id)
    )
    if (await session.execute(statement)).scalar_one_or_none() is None:
        raise NotFoundError("Событие процесса не найдено в этом договоре")


# --- Комментарии --------------------------------------------------------------


@router.get(
    "/{contract_id}/comments",
    response_model=list[CommentRead],
    summary="Комментарии по договору",
)
async def list_comments(
    contract: ContractDep,
    session: SessionDep,
    workflow_event_id: uuid.UUID | None = None,
) -> list[CommentRead]:
    statement = (
        select(Comment)
        .where(Comment.contract_id == contract.id)
        .options(selectinload(Comment.author))
        .order_by(Comment.created_at)
    )
    if workflow_event_id is not None:
        statement = statement.where(Comment.workflow_event_id == workflow_event_id)
    result = await session.execute(statement)
    return [CommentRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/{contract_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить комментарий",
)
async def create_comment(
    contract: ContractDep,
    payload: CommentCreate,
    session: SessionDep,
    user: CurrentUserDep,
) -> CommentRead:
    await _check_event_belongs_to_contract(session, contract.id, payload.workflow_event_id)
    comment = Comment(
        contract_id=contract.id,
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
    "/{contract_id}/attachments",
    response_model=list[AttachmentRead],
    summary="Файлы по договору",
)
async def list_attachments(
    contract: ContractDep,
    session: SessionDep,
    workflow_event_id: uuid.UUID | None = None,
) -> list[AttachmentRead]:
    statement = (
        select(Attachment)
        .where(Attachment.contract_id == contract.id)
        .options(selectinload(Attachment.uploader))
        .order_by(Attachment.created_at)
    )
    if workflow_event_id is not None:
        statement = statement.where(Attachment.workflow_event_id == workflow_event_id)
    result = await session.execute(statement)
    return [
        AttachmentRead.from_model(row, settings.api_v1_prefix) for row in result.scalars()
    ]


@router.post(
    "/{contract_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл",
    description=(
        "Допустимые форматы: png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx. "
        "Файл можно привязать к событию процесса - тогда он появится в карточке этапа."
    ),
)
async def upload_attachment(
    contract: ContractDep,
    session: SessionDep,
    user: CurrentUserDep,
    file: UploadFile = File(description="Файл документа"),
    workflow_event_id: uuid.UUID | None = Form(default=None),
) -> AttachmentRead:
    await _check_event_belongs_to_contract(session, contract.id, workflow_event_id)
    stored = await storage.save_upload(file, f"contracts/{contract.id}")

    attachment = Attachment(
        contract_id=contract.id,
        workflow_event_id=workflow_event_id,
        uploaded_by=user.id,
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
            # Вуз нужен для проверки прав: менеджер видит файлы своих договоров.
            selectinload(Attachment.contract).selectinload(Contract.university),
        )
    )
    attachment = (await session.execute(statement)).scalar_one_or_none()
    if attachment is None:
        raise NotFoundError("Файл не найден")
    await access.ensure_contract_access(session, attachment.contract, principal, user)
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
    # Свой файл удаляет автор, чужой - только руководитель или администратор.
    if attachment.uploaded_by != user.id and not principal.has_role(Role.HEAD, Role.ADMIN):
        raise ForbiddenError("Удалять чужие файлы может только руководитель")
    storage.delete(attachment.storage_path)
    await session.delete(attachment)
