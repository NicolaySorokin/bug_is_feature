"""Правила целостности, которые держит сама база.

Опубликованную версию шаблона структурно менять нельзя: по ней идут
процессы, и их история должна оставаться верной (раздел 3.1 концепции).
Сервис это проверяет, но гарантия нужна и от записи в обход API - поэтому
триггер: этапы и переходы версии не в статусе draft не добавляются,
не удаляются и не меняются. Исключение - название, описание и координаты
этапа: на ход процесса они не влияют (корректировка названий статусов -
функциональное требование 2 ТЗ).

Одна действующая версия на шаблон - частичный уникальный индекс
(см. app.models.workflow).
"""

from sqlalchemy import DDL, event

from app.models.workflow import WorkflowStage, WorkflowTransition

GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION workflow_structure_guard() RETURNS trigger AS $$
DECLARE
    target_version uuid;
    version_status varchar;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_version := OLD.workflow_version_id;
    ELSE
        target_version := NEW.workflow_version_id;
    END IF;
    SELECT status INTO version_status FROM workflow_versions WHERE id = target_version;
    -- Версии уже нет (удаляется черновик целиком) или это черновик - можно.
    IF version_status IS NULL OR version_status = 'draft' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    IF TG_TABLE_NAME = 'workflow_stages' AND TG_OP = 'UPDATE'
       AND NEW.workflow_version_id = OLD.workflow_version_id
       AND NEW.code = OLD.code
       AND NEW.sort_order IS NOT DISTINCT FROM OLD.sort_order
       AND NEW.is_initial = OLD.is_initial
       AND NEW.is_optional = OLD.is_optional
       AND NEW.is_final = OLD.is_final
       AND NEW.outcome IS NOT DISTINCT FROM OLD.outcome
       AND NEW.sla_days IS NOT DISTINCT FROM OLD.sla_days
       AND NEW.required_documents IS NOT DISTINCT FROM OLD.required_documents
       AND NEW.program_status_on_enter IS NOT DISTINCT FROM OLD.program_status_on_enter
       AND NEW.product_status_on_enter IS NOT DISTINCT FROM OLD.product_status_on_enter THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Версия шаблона опубликована: этапы и переходы в ней не меняются'
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql
"""

STAGES_TRIGGER = """
CREATE TRIGGER workflow_stages_guard
BEFORE INSERT OR UPDATE OR DELETE ON workflow_stages
FOR EACH ROW EXECUTE FUNCTION workflow_structure_guard()
"""

TRANSITIONS_TRIGGER = """
CREATE TRIGGER workflow_transitions_guard
BEFORE INSERT OR UPDATE OR DELETE ON workflow_transitions
FOR EACH ROW EXECUTE FUNCTION workflow_structure_guard()
"""

# Схема, созданная по моделям (тесты, create_all), получает те же триггеры,
# что и база после миграций.
event.listen(WorkflowStage.__table__, "after_create", DDL(GUARD_FUNCTION))
event.listen(WorkflowStage.__table__, "after_create", DDL(STAGES_TRIGGER))
event.listen(WorkflowTransition.__table__, "after_create", DDL(GUARD_FUNCTION))
event.listen(WorkflowTransition.__table__, "after_create", DDL(TRANSITIONS_TRIGGER))
