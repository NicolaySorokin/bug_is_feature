"""Типовые шаблоны договоров и проект договора по шаблону.

Шаблоны ведёт руководитель. Менеджер получает предпросмотр, файл DOCX
или вложение во взаимодействие с типом «Проект договора».
"""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserDep,
    InteractionDep,
    PrincipalDep,
    SessionDep,
    WritableInteractionDep,
    require_action,
)
from app.api.v1.endpoints.content import check_event
from app.core.config import settings
from app.core.errors import AppError, ErrorCode, ForbiddenError, NotFoundError
from app.enums import DocumentType
from app.models.content import Attachment
from app.models.contract import ContractTemplate
from app.schemas.content import AttachmentRead
from app.schemas.contract import (
    ContractDocumentPreview,
    ContractDocumentRequest,
    ContractTemplateRead,
    ContractTemplateWrite,
    TemplateFieldRead,
)
from app.services import access, contract_documents, storage
from app.services.access import Action

router = APIRouter(prefix="/contract-templates", tags=["contract templates"])
documents_router = APIRouter(prefix="/interactions", tags=["contract templates"])

DOCX_TYPE = storage.ALLOWED_TYPES["docx"]

edit_templates = require_action(
    Action.EDIT_CONTRACT_TEMPLATES, "Шаблоны договоров ведёт руководитель"
)


def _can_use(principal: PrincipalDep, user: CurrentUserDep) -> bool:
    return access.can(principal, user, Action.WORK_INTERACTION) or access.can(
        principal, user, Action.EDIT_CONTRACT_TEMPLATES
    )


def _check_fields(body: str) -> None:
    unknown = contract_documents.unknown_fields(body)
    if unknown:
        names = ", ".join(f"{{{{{key}}}}}" for key in unknown)
        raise AppError(
            f"В шаблоне неизвестные поля: {names}. Список полей - под текстом шаблона",
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            details={"unknown_fields": unknown},
        )


async def _read(session: SessionDep, template_id: uuid.UUID) -> ContractTemplate:
    template = await session.scalar(
        select(ContractTemplate)
        .where(ContractTemplate.id == template_id)
        .options(selectinload(ContractTemplate.updated_by))
        .execution_options(populate_existing=True)
    )
    if template is None:
        raise NotFoundError("Шаблон договора не найден")
    return template


@router.get(
    "",
    response_model=list[ContractTemplateRead],
    summary="Шаблоны договоров",
    description=(
        "Менеджеру - действующие шаблоны, руководителю - все, включая выключенные. "
        "Если шаблонов ещё нет, заводится типовой."
    ),
)
async def list_templates(
    session: SessionDep, principal: PrincipalDep, user: CurrentUserDep
) -> list[ContractTemplateRead]:
    if not _can_use(principal, user):
        raise ForbiddenError("Шаблоны договоров доступны тем, кто ведёт взаимодействия")
    await contract_documents.ensure_default(session)
    statement = (
        select(ContractTemplate)
        .options(selectinload(ContractTemplate.updated_by))
        .order_by(ContractTemplate.is_active.desc(), ContractTemplate.name)
    )
    if not access.can(principal, user, Action.EDIT_CONTRACT_TEMPLATES):
        statement = statement.where(ContractTemplate.is_active.is_(True))
    result = await session.execute(statement)
    return [ContractTemplateRead.model_validate(row) for row in result.scalars()]


@router.get(
    "/fields",
    response_model=list[TemplateFieldRead],
    summary="Поля шаблона договора",
    description="Что можно подставить в текст шаблона: {{ключ}} и откуда берётся значение.",
)
async def list_fields(
    principal: PrincipalDep, user: CurrentUserDep
) -> list[TemplateFieldRead]:
    if not _can_use(principal, user):
        raise ForbiddenError("Шаблоны договоров доступны тем, кто ведёт взаимодействия")
    return [
        TemplateFieldRead(key=field.key, label=field.label, group=field.group)
        for field in contract_documents.FIELDS
    ]


@router.post(
    "",
    response_model=ContractTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Завести шаблон договора",
    dependencies=[edit_templates],
)
async def create_template(
    payload: ContractTemplateWrite, session: SessionDep, user: CurrentUserDep
) -> ContractTemplateRead:
    _check_fields(payload.body)
    template = ContractTemplate(**payload.model_dump(), updated_by_id=user.id)
    session.add(template)
    await session.flush()
    return ContractTemplateRead.model_validate(await _read(session, template.id))


@router.put(
    "/{template_id}",
    response_model=ContractTemplateRead,
    summary="Изменить шаблон договора",
    description="Шаблон не удаляется, а выключается: по нему уже могли сформировать договоры.",
    dependencies=[edit_templates],
)
async def update_template(
    template_id: uuid.UUID,
    payload: ContractTemplateWrite,
    session: SessionDep,
    user: CurrentUserDep,
) -> ContractTemplateRead:
    _check_fields(payload.body)
    template = await _read(session, template_id)
    for field, value in payload.model_dump().items():
        setattr(template, field, value)
    template.updated_by_id = user.id
    await session.flush()
    return ContractTemplateRead.model_validate(await _read(session, template.id))


# Договор по шаблону


def _preview(document: contract_documents.PreparedDocument) -> ContractDocumentPreview:
    return ContractDocumentPreview(
        template_name=document.template.name,
        filename=document.filename,
        text=document.text,
        missing=[
            TemplateFieldRead(key=field.key, label=field.label, group=field.group)
            for field in document.missing
        ],
    )


@documents_router.post(
    "/{interaction_id}/contract/document/preview",
    response_model=ContractDocumentPreview,
    summary="Предпросмотр договора по шаблону",
    description=(
        "Текст с подставленными реквизитами и список полей без значения: их "
        "стоит дописать в карточке вуза или в договоре до формирования файла."
    ),
)
async def preview_document(
    interaction: InteractionDep, payload: ContractDocumentRequest, session: SessionDep
) -> ContractDocumentPreview:
    document = await contract_documents.prepare(session, interaction.id, payload.template_id)
    return _preview(document)


@documents_router.post(
    "/{interaction_id}/contract/document",
    summary="Скачать договор по шаблону (DOCX)",
    response_class=Response,
    responses={200: {"content": {DOCX_TYPE: {}}, "description": "Файл DOCX"}},
)
async def download_document(
    interaction: InteractionDep, payload: ContractDocumentRequest, session: SessionDep
) -> Response:
    document = await contract_documents.prepare(session, interaction.id, payload.template_id)
    content = contract_documents.build_docx(document.text, document.filename[:-5])
    return Response(
        content=content,
        media_type=DOCX_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="contract-draft.docx"; '
                f"filename*=UTF-8''{quote(document.filename)}"
            )
        },
    )


@documents_router.post(
    "/{interaction_id}/contract/document/attach",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Приложить договор по шаблону к взаимодействию",
    description=(
        "Файл DOCX попадает в файлы взаимодействия с типом «Проект договора», "
        "а с workflow_event_id - и в карточку этапа. Проект не закрывает "
        "обязательный документ «Договор»: для подписания нужен подписанный договор."
    ),
)
async def attach_document(
    interaction: WritableInteractionDep,
    payload: ContractDocumentRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> AttachmentRead:
    await check_event(session, interaction.id, payload.workflow_event_id)
    document = await contract_documents.prepare(session, interaction.id, payload.template_id)
    content = contract_documents.build_docx(document.text, document.filename[:-5])
    stored = storage.save_bytes(content, document.filename, f"interactions/{interaction.id}")
    attachment = Attachment(
        workflow_instance_id=interaction.id,
        workflow_event_id=payload.workflow_event_id,
        uploaded_by=user.id,
        document_type=DocumentType.CONTRACT_DRAFT,
        original_name=stored.original_name,
        storage_path=stored.storage_path,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
    )
    session.add(attachment)
    await session.flush()
    await session.refresh(attachment, ["uploader"])
    return AttachmentRead.from_model(attachment, settings.api_v1_prefix)
