"""Все модели импортируются здесь, чтобы Alembic видел полную метадату."""

from app.db.base import Base
from app.models.catalog import ItDirection, ItProduct, ItProgram, ProgramProduct, Vendor
from app.models.content import Attachment, Comment
from app.models.contract import (
    Contract,
    ContractContact,
    ContractProduct,
    ContractProgram,
    License,
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

__all__ = [
    "Attachment",
    "Base",
    "Comment",
    "Contract",
    "ContractContact",
    "ContractProduct",
    "ContractProgram",
    "ItDirection",
    "ItProduct",
    "ItProgram",
    "License",
    "ProgramProduct",
    "University",
    "UniversityContact",
    "User",
    "Vendor",
    "WorkflowEvent",
    "WorkflowInstance",
    "WorkflowStage",
    "WorkflowTemplate",
    "WorkflowTransition",
    "WorkflowVersion",
]
