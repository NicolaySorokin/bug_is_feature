"""Все модели импортируются здесь, чтобы Alembic видел полную метадату."""

from app.db import guards  # noqa: F401 - триггеры неизменности опубликованных версий
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
from app.models.contract import Contract, ContractTemplate, License
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
from app.models.learning import Enrollment, Learner, LearningApplication, LearningStream
from app.models.system import AlertMark, AppSetting, DataVersion
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import (
    Interaction,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTransition,
    WorkflowVersion,
)

__all__ = [
    "AlertMark",
    "AppSetting",
    "Attachment",
    "AuditLog",
    "Base",
    "Comment",
    "Contract",
    "ContractTemplate",
    "DataVersion",
    "Enrollment",
    "ExternalLink",
    "ImportRowError",
    "ImportRun",
    "IntegrationMapping",
    "IntegrationRun",
    "IntegrationRunError",
    "IntegrationSource",
    "Interaction",
    "InteractionContact",
    "InteractionProduct",
    "InteractionProgram",
    "InteractionProgramProduct",
    "ItDirection",
    "ItProduct",
    "ItProgram",
    "Learner",
    "LearningApplication",
    "LearningStream",
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
