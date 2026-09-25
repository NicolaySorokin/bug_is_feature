"""Схемы договоров, их состава и лицензий."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.enums import (
    ContractStatus,
    ImplementationStatus,
    WorkflowInstanceStatus,
)
from app.schemas.catalog import ItProductRead, ItProgramRead
from app.schemas.common import ORMModel
from app.schemas.license import LicenseRead
from app.schemas.university import UniversityContactRead, UniversityRead
from app.schemas.user import UserRead


class ContractProgramCreate(BaseModel):
    program_id: uuid.UUID
    implementation_status: ImplementationStatus = ImplementationStatus.NOT_STARTED


class ContractProgramRead(ORMModel):
    id: uuid.UUID
    program_id: uuid.UUID
    implementation_status: ImplementationStatus
    program: ItProgramRead | None = None


class ContractProgramUpdate(BaseModel):
    implementation_status: ImplementationStatus


class ContractProductCreate(BaseModel):
    product_id: uuid.UUID
    transfer_status: ImplementationStatus = ImplementationStatus.NOT_STARTED


class ContractProductUpdate(BaseModel):
    transfer_status: ImplementationStatus


class ContractProductRead(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    transfer_status: ImplementationStatus
    product: ItProductRead | None = None
    licenses: list[LicenseRead] = []


class ContractContactCreate(BaseModel):
    contact_id: uuid.UUID
    role: str | None = Field(default=None, max_length=255)
    is_primary: bool = False


class ContractContactRead(ORMModel):
    """Ответственный от вуза по конкретному договору."""

    contact_id: uuid.UUID
    role: str | None
    is_primary: bool
    contact: UniversityContactRead


class ContractCreate(BaseModel):
    university_id: uuid.UUID
    number: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=500)
    manager_id: uuid.UUID | None = None
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: ContractStatus = ContractStatus.DRAFT
    comment: str | None = None
    program_ids: list[uuid.UUID] = []
    product_ids: list[uuid.UUID] = []
    # Если задано, по договору сразу запускается процесс по этому шаблону.
    workflow_template_id: uuid.UUID | None = None


class ContractUpdate(BaseModel):
    number: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=500)
    manager_id: uuid.UUID | None = None
    signed_at: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: ContractStatus | None = None
    comment: str | None = None


class ContractRead(ORMModel):
    id: uuid.UUID
    university_id: uuid.UUID
    manager_id: uuid.UUID | None
    manager: UserRead | None = None
    number: str
    title: str | None
    signed_at: date | None
    valid_from: date | None
    valid_to: date | None
    status: ContractStatus
    comment: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProcessSummary(BaseModel):
    """Где сейчас процесс по договору - для строки реестра."""

    instance_id: uuid.UUID
    status: WorkflowInstanceStatus
    stage_id: uuid.UUID | None = None
    stage_name: str | None = None
    days_on_stage: int | None = None
    sla_days: int | None = None


class ContractListItem(ContractRead):
    university: UniversityRead | None = None
    process: ProcessSummary | None = None


class ContractDetail(ContractListItem):
    programs: list[ContractProgramRead] = []
    products: list[ContractProductRead] = []
    contacts: list[ContractContactRead] = []
