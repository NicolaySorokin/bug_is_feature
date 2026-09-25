"""Все модели импортируются здесь, чтобы Alembic видел полную метадату."""

from app.db.base import Base
from app.models.access import UserUniversityAccess
from app.models.audit import AuditLog
from app.models.catalog import (
    ItDirection,
    ItProduct,
    ItProgram,
    ProgramProduct,
    Vendor,
    VendorContact,
)
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
from app.models.learning import Learner, LearningApplication
from app.models.system import AppSetting, DataVersion
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
    "AppSetting",
    "Attachment",
    "AuditLog",
    "Base",
    "Comment",
    "Contract",
    "ContractContact",
    "ContractProduct",
    "ContractProgram",
    "DataVersion",
    "ExternalLink",
    "ImportRowError",
    "ImportRun",
    "IntegrationRun",
    "IntegrationSource",
    "ItDirection",
    "ItProduct",
    "ItProgram",
    "Learner",
    "LearningApplication",
    "License",
    "ProgramProduct",
    "University",
    "UniversityContact",
    "User",
    "UserUniversityAccess",
    "Vendor",
    "VendorContact",
    "WorkflowEvent",
    "WorkflowInstance",
    "WorkflowStage",
    "WorkflowTemplate",
    "WorkflowTransition",
    "WorkflowVersion",
]
