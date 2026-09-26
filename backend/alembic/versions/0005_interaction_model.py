"""Взаимодействие с вузом вместо договора как главного объекта.

Решения по бизнес-модели (docs/business-model-decisions.md) и перечень
исправлений (docs/required-fixes.md, пункты 1-5, 9-11, 14-16, 18-22):

* экземпляр workflow - это взаимодействие: на нём вуз, ответственный,
  источник, статус draft/in_progress/blocked/completed/cancelled,
  результат и сведения о закрытии; договор - необязательная сущность
  внутри взаимодействия (не больше одного);
* программы, продукты и контакты вуза переезжают с договора на
  взаимодействие, добавляется фактическая связь программа - продукт;
  статус передачи продукта отделён от статуса внедрения программы
  (implemented -> transferred);
* комментарии и файлы принадлежат взаимодействию, у файла есть тип;
* версии шаблона получают жизненный цикл draft/active/deprecated/retired
  с одной действующей версией на шаблон; стартовый этап задаётся явно,
  у финального этапа - результат; опубликованную версию структурно
  менять нельзя (триггеры);
* вуз получает статус, ИНН и ссылку для объединения дублей; точечный
  доступ к вузу - срок, основание и кто выдал; у сотрудника -
  руководитель, дополнительные права и временная область данных;
* потоки обучения и зачисления - отдельные сущности; у запуска обмена -
  частичный успех, ошибки по записям и очередь ручного сопоставления.

Данные переносятся полностью: каждый договор становится взаимодействием
(с процессом или черновиком без процесса), идентификаторы программ
и продуктов состава сохраняются, поэтому лицензии и ссылки не рвутся.

Revision ID: 3f7a9c1e5b20
Revises: 8c4e2d91b7a3
Create Date: 2026-09-26 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3f7a9c1e5b20"
down_revision: str | None = "8c4e2d91b7a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _versions_and_stages() -> None:
    op.add_column(
        "workflow_versions",
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
    )
    op.add_column(
        "workflow_versions",
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_versions", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "workflow_stages",
        sa.Column("is_initial", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("workflow_stages", sa.Column("outcome", sa.String(length=16), nullable=True))
    op.add_column(
        "workflow_stages",
        sa.Column(
            "required_documents",
            postgresql.ARRAY(sa.String(length=32)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "workflow_stages",
        sa.Column("program_status_on_enter", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "workflow_stages",
        sa.Column("product_status_on_enter", sa.String(length=32), nullable=True),
    )

    # Стартовый этап был «первым по сортировке» - теперь это явный признак.
    op.execute(
        """
        UPDATE workflow_stages SET is_initial = true
        WHERE id IN (
            SELECT DISTINCT ON (workflow_version_id) id
            FROM workflow_stages
            ORDER BY workflow_version_id, sort_order, code
        )
        """
    )
    # Финальный этап даёт результат: «Отказ» - неуспех, остальные - успех.
    op.execute(
        """
        UPDATE workflow_stages
        SET outcome = CASE WHEN lower(name) LIKE '%отказ%' THEN 'unsuccessful'
                           ELSE 'successful' END
        WHERE is_final
        """
    )
    # Статусы внедрения, которые раньше ставились руками по ходу процесса,
    # теперь ставит сам этап основного шаблона при входе в него.
    op.execute(
        """
        UPDATE workflow_stages SET
            program_status_on_enter = CASE code
                WHEN 'handover' THEN 'in_progress'
                WHEN 'classes' THEN 'implemented' END,
            product_status_on_enter = CASE code
                WHEN 'handover' THEN 'in_progress'
                WHEN 'training' THEN 'transferred' END
        WHERE code IN ('handover', 'training', 'classes')
        """
    )
    # Последняя опубликованная версия шаблона - действующая.
    op.execute(
        """
        UPDATE workflow_versions v SET status = 'active'
        WHERE v.published_at IS NOT NULL
          AND v.id = (
              SELECT w.id FROM workflow_versions w
              WHERE w.template_id = v.template_id AND w.published_at IS NOT NULL
              ORDER BY w.version_number DESC LIMIT 1
          )
        """
    )


def _fallback_version() -> None:
    """Договоры без процесса станут черновиками взаимодействий - им нужна
    действующая версия. Если шаблонов нет совсем, заводится простейший."""
    op.execute(
        """
        DO $$
        DECLARE
            template_id uuid;
            version_id uuid;
            first_stage uuid;
            last_stage uuid;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM contracts c
                WHERE NOT EXISTS (
                    SELECT 1 FROM workflow_instances i WHERE i.contract_id = c.id
                )
            ) OR EXISTS (SELECT 1 FROM workflow_versions WHERE status = 'active') THEN
                RETURN;
            END IF;
            template_id := gen_random_uuid();
            version_id := gen_random_uuid();
            first_stage := gen_random_uuid();
            last_stage := gen_random_uuid();
            INSERT INTO workflow_templates (id, name, description, is_active)
            VALUES (template_id, 'Процесс по умолчанию',
                    'Заведён при переходе на взаимодействия: у договоров не было процесса',
                    true);
            INSERT INTO workflow_versions (id, template_id, version_number, status, published_at)
            VALUES (version_id, template_id, 1, 'active', now());
            INSERT INTO workflow_stages
                (id, workflow_version_id, code, name, sort_order, is_initial, is_final, outcome)
            VALUES
                (first_stage, version_id, 'work', 'Работа с вузом', 10, true, false, NULL),
                (last_stage, version_id, 'done', 'Завершено', 20, false, true, 'successful');
            INSERT INTO workflow_transitions
                (id, workflow_version_id, from_stage_id, to_stage_id, name)
            VALUES (gen_random_uuid(), version_id, first_stage, last_stage, 'Работа завершена');
        END $$
        """
    )


def _interactions() -> None:
    op.add_column("workflow_instances", sa.Column("university_id", sa.Uuid(), nullable=True))
    op.add_column("workflow_instances", sa.Column("manager_id", sa.Uuid(), nullable=True))
    op.add_column(
        "workflow_instances", sa.Column("title", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "workflow_instances",
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
    )
    op.add_column("workflow_instances", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column("workflow_instances", sa.Column("created_by_id", sa.Uuid(), nullable=True))
    op.add_column("workflow_instances", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column(
        "workflow_instances",
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_instances", sa.Column("outcome", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "workflow_instances", sa.Column("closure_reason", sa.String(length=32), nullable=True)
    )
    op.add_column("workflow_instances", sa.Column("closure_comment", sa.Text(), nullable=True))
    op.add_column("workflow_instances", sa.Column("closed_by_id", sa.Uuid(), nullable=True))
    op.add_column(
        "workflow_instances", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )
    for column in _timestamps():
        op.add_column("workflow_instances", column)
    op.alter_column("workflow_instances", "status", server_default="draft")

    # Процессы договоров получают вуз, ответственного и название договора.
    op.execute(
        """
        UPDATE workflow_instances i
        SET university_id = c.university_id,
            manager_id = c.manager_id,
            title = c.title,
            comment = c.comment,
            source = CASE WHEN c.number LIKE 'ЗАЯВК%' THEN 'site' ELSE 'manual' END,
            created_at = LEAST(c.created_at, coalesce(i.started_at, c.created_at)),
            updated_at = greatest(c.updated_at, coalesce(i.current_stage_started_at, c.updated_at)),
            closed_at = CASE WHEN i.status IN ('completed', 'cancelled')
                             THEN coalesce(i.completed_at, i.current_stage_started_at) END,
            outcome = CASE WHEN i.status = 'completed' THEN coalesce(
                (SELECT s.outcome FROM workflow_stages s WHERE s.id = i.current_stage_id),
                'successful') END,
            closure_reason = CASE WHEN i.status = 'cancelled' THEN 'other' END
        FROM contracts c
        WHERE c.id = i.contract_id
        """
    )
    # Причина блокировки - из последнего события блокировки.
    op.execute(
        """
        UPDATE workflow_instances i
        SET blocked_reason = e.comment, blocked_at = e.created_at
        FROM (
            SELECT DISTINCT ON (workflow_instance_id) workflow_instance_id, comment, created_at
            FROM workflow_events
            WHERE event_type = 'blocked'
            ORDER BY workflow_instance_id, created_at DESC
        ) e
        WHERE e.workflow_instance_id = i.id AND i.status = 'blocked'
        """
    )
    # Автор завершения - тот, кто сделал последний переход.
    op.execute(
        """
        UPDATE workflow_instances i
        SET closed_by_id = e.user_id
        FROM (
            SELECT DISTINCT ON (workflow_instance_id) workflow_instance_id, user_id
            FROM workflow_events
            ORDER BY workflow_instance_id, created_at DESC
        ) e
        WHERE e.workflow_instance_id = i.id AND i.status IN ('completed', 'cancelled')
        """
    )
    # Создатель - кто запустил процесс.
    op.execute(
        """
        UPDATE workflow_instances i
        SET created_by_id = e.user_id
        FROM workflow_events e
        WHERE e.workflow_instance_id = i.id AND e.event_type = 'started'
        """
    )

    _fallback_version()
    # Договор без процесса - черновик взаимодействия по действующей версии
    # основного (самого раннего) шаблона.
    op.execute(
        """
        INSERT INTO workflow_instances
            (id, contract_id, university_id, manager_id, title, comment, source,
             workflow_version_id, status, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, c.university_id, c.manager_id, c.title, c.comment,
               CASE WHEN c.number LIKE 'ЗАЯВК%' THEN 'site' ELSE 'manual' END,
               (SELECT v.id FROM workflow_versions v
                JOIN workflow_templates t ON t.id = v.template_id
                WHERE v.status = 'active'
                ORDER BY t.is_active DESC, t.created_at LIMIT 1),
               'draft', c.created_at, c.updated_at
        FROM contracts c
        WHERE NOT EXISTS (SELECT 1 FROM workflow_instances i WHERE i.contract_id = c.id)
        """
    )
    op.execute(
        """
        INSERT INTO workflow_events
            (id, workflow_instance_id, event_type, comment, created_at)
        SELECT gen_random_uuid(), i.id, 'created',
               'Взаимодействие заведено при переходе с договоров', i.created_at
        FROM workflow_instances i
        WHERE i.status = 'draft'
        """
    )

    # Остальные опубликованные версии: устаревшие, если по ним ещё идут
    # процессы, иначе - выведенные из использования.
    op.execute(
        """
        UPDATE workflow_versions v
        SET status = CASE WHEN EXISTS (
                SELECT 1 FROM workflow_instances i
                WHERE i.workflow_version_id = v.id
                  AND i.status IN ('draft', 'in_progress', 'blocked')
            ) THEN 'deprecated' ELSE 'retired' END,
            deprecated_at = now()
        WHERE v.published_at IS NOT NULL AND v.status = 'draft'
        """
    )
    op.execute("UPDATE workflow_versions SET retired_at = now() WHERE status = 'retired'")

    op.alter_column("workflow_instances", "university_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_workflow_instances_university_id_universities"),
        "workflow_instances",
        "universities",
        ["university_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    for column in ("manager_id", "created_by_id", "closed_by_id"):
        op.create_foreign_key(
            op.f(f"fk_workflow_instances_{column}_users"),
            "workflow_instances",
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        op.f("ix_workflow_instances_university_id"), "workflow_instances", ["university_id"]
    )
    op.create_index(
        op.f("ix_workflow_instances_manager_id"), "workflow_instances", ["manager_id"]
    )
    op.create_index(op.f("ix_workflow_instances_status"), "workflow_instances", ["status"])


def _contracts() -> None:
    op.add_column("contracts", sa.Column("workflow_instance_id", sa.Uuid(), nullable=True))
    op.add_column(
        "contracts", sa.Column("closure_reason", sa.String(length=32), nullable=True)
    )
    # Договор - во взаимодействии своего последнего процесса.
    op.execute(
        """
        UPDATE contracts c SET workflow_instance_id = (
            SELECT i.id FROM workflow_instances i
            WHERE i.contract_id = c.id
            ORDER BY i.started_at DESC NULLS LAST, i.created_at DESC
            LIMIT 1
        )
        """
    )
    op.execute(
        """
        UPDATE contracts
        SET closure_reason = CASE WHEN valid_to IS NOT NULL AND valid_to < current_date
                                  THEN 'expired' ELSE 'fulfilled' END
        WHERE status = 'closed'
        """
    )
    # Даты приводятся к ограничениям: срок не может начаться после окончания.
    op.execute(
        "UPDATE contracts SET valid_from = NULL "
        "WHERE valid_from IS NOT NULL AND valid_to IS NOT NULL AND valid_from > valid_to"
    )
    op.execute(
        "UPDATE contracts SET signed_at = valid_to "
        "WHERE signed_at IS NOT NULL AND valid_to IS NOT NULL AND signed_at > valid_to"
    )
    op.alter_column("contracts", "workflow_instance_id", nullable=False)
    op.create_unique_constraint(
        op.f("uq_contracts_workflow_instance_id"), "contracts", ["workflow_instance_id"]
    )
    op.create_foreign_key(
        op.f("fk_contracts_workflow_instance_id_workflow_instances"),
        "contracts",
        "workflow_instances",
        ["workflow_instance_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_contracts_valid_period"),
        "contracts",
        "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to",
    )
    op.create_check_constraint(
        op.f("ck_contracts_signed_before_end"),
        "contracts",
        "signed_at IS NULL OR valid_to IS NULL OR signed_at <= valid_to",
    )


def _composition() -> None:
    op.create_table(
        "interaction_programs",
        sa.Column("workflow_instance_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column(
            "implementation_status",
            sa.String(length=32),
            server_default="not_started",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["it_programs.id"],
            name=op.f("fk_interaction_programs_program_id_it_programs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_instance_id"],
            ["workflow_instances.id"],
            name=op.f("fk_interaction_programs_workflow_instance_id_workflow_instances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interaction_programs")),
        sa.UniqueConstraint(
            "workflow_instance_id",
            "program_id",
            name=op.f("uq_interaction_programs_workflow_instance_id"),
        ),
    )
    op.create_index(
        op.f("ix_interaction_programs_program_id"), "interaction_programs", ["program_id"]
    )
    op.create_index(
        op.f("ix_interaction_programs_workflow_instance_id"),
        "interaction_programs",
        ["workflow_instance_id"],
    )

    op.create_table(
        "interaction_products",
        sa.Column("workflow_instance_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "transfer_status",
            sa.String(length=32),
            server_default="not_started",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["it_products.id"],
            name=op.f("fk_interaction_products_product_id_it_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_instance_id"],
            ["workflow_instances.id"],
            name=op.f("fk_interaction_products_workflow_instance_id_workflow_instances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interaction_products")),
        sa.UniqueConstraint(
            "workflow_instance_id",
            "product_id",
            name=op.f("uq_interaction_products_workflow_instance_id"),
        ),
    )
    op.create_index(
        op.f("ix_interaction_products_product_id"), "interaction_products", ["product_id"]
    )
    op.create_index(
        op.f("ix_interaction_products_workflow_instance_id"),
        "interaction_products",
        ["workflow_instance_id"],
    )

    op.create_table(
        "interaction_program_products",
        sa.Column("interaction_program_id", sa.Uuid(), nullable=False),
        sa.Column("interaction_product_id", sa.Uuid(), nullable=False),
        sa.Column("is_exception", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("exception_comment", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_interaction_program_products_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["interaction_product_id"],
            ["interaction_products.id"],
            name=op.f(
                "fk_interaction_program_products_interaction_product_id_interaction_products"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interaction_program_id"],
            ["interaction_programs.id"],
            name=op.f(
                "fk_interaction_program_products_interaction_program_id_interaction_programs"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "interaction_program_id",
            "interaction_product_id",
            name=op.f("pk_interaction_program_products"),
        ),
    )

    op.create_table(
        "interaction_contacts",
        sa.Column("workflow_instance_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["university_contacts.id"],
            name=op.f("fk_interaction_contacts_contact_id_university_contacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_instance_id"],
            ["workflow_instances.id"],
            name=op.f("fk_interaction_contacts_workflow_instance_id_workflow_instances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "workflow_instance_id", "contact_id", name=op.f("pk_interaction_contacts")
        ),
    )

    # Состав договора - составу его взаимодействия; идентификаторы строк
    # сохраняются, поэтому лицензии продуктов остаются на месте. Если
    # процессов по договору было несколько, состав получают все.
    op.execute(
        """
        INSERT INTO interaction_programs
            (id, workflow_instance_id, program_id, implementation_status, created_at)
        SELECT CASE WHEN i.id = c.workflow_instance_id THEN cp.id ELSE gen_random_uuid() END,
               i.id, cp.program_id, cp.implementation_status, cp.created_at
        FROM contract_programs cp
        JOIN contracts c ON c.id = cp.contract_id
        JOIN workflow_instances i ON i.contract_id = c.id
        """
    )
    op.execute(
        """
        INSERT INTO interaction_products
            (id, workflow_instance_id, product_id, transfer_status, created_at)
        SELECT CASE WHEN i.id = c.workflow_instance_id THEN cp.id ELSE gen_random_uuid() END,
               i.id, cp.product_id,
               CASE WHEN cp.transfer_status = 'implemented' THEN 'transferred'
                    ELSE cp.transfer_status END,
               cp.created_at
        FROM contract_products cp
        JOIN contracts c ON c.id = cp.contract_id
        JOIN workflow_instances i ON i.contract_id = c.id
        """
    )
    op.execute(
        """
        INSERT INTO interaction_contacts (workflow_instance_id, contact_id, role, is_primary)
        SELECT i.id, cc.contact_id, cc.role, cc.is_primary
        FROM contract_contacts cc
        JOIN workflow_instances i ON i.contract_id = cc.contract_id
        """
    )
    # Связь программа - продукт: сначала по справочнику program_products...
    op.execute(
        """
        INSERT INTO interaction_program_products
            (interaction_program_id, interaction_product_id, is_exception, created_at)
        SELECT ipr.id, ipd.id, false, ipd.created_at
        FROM interaction_products ipd
        JOIN interaction_programs ipr ON ipr.workflow_instance_id = ipd.workflow_instance_id
        JOIN program_products pp
          ON pp.program_id = ipr.program_id AND pp.product_id = ipd.product_id
        """
    )
    # ...а продукт, которому по справочнику не нашлось программы, связывается
    # со всеми программами взаимодействия как исключение: в договоре
    # продукты шли общим списком, и руководитель уточнит связь.
    op.execute(
        """
        INSERT INTO interaction_program_products
            (interaction_program_id, interaction_product_id, is_exception,
             exception_comment, created_at)
        SELECT ipr.id, ipd.id, true,
               'Перенесено из состава договора: в справочнике программ и продуктов '
               'такой связи нет - уточните программу',
               ipd.created_at
        FROM interaction_products ipd
        JOIN interaction_programs ipr ON ipr.workflow_instance_id = ipd.workflow_instance_id
        WHERE NOT EXISTS (
            SELECT 1 FROM interaction_program_products x
            WHERE x.interaction_product_id = ipd.id
        )
        """
    )

    # Лицензии: договор и продукт взаимодействия.
    op.add_column("licenses", sa.Column("contract_id", sa.Uuid(), nullable=True))
    op.add_column("licenses", sa.Column("interaction_product_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE licenses l
        SET contract_id = cp.contract_id, interaction_product_id = cp.id
        FROM contract_products cp
        WHERE cp.id = l.contract_product_id
        """
    )
    op.execute(
        "UPDATE licenses SET valid_from = NULL "
        "WHERE valid_from IS NOT NULL AND valid_to IS NOT NULL AND valid_from > valid_to"
    )
    op.alter_column("licenses", "contract_id", nullable=False)
    op.alter_column("licenses", "interaction_product_id", nullable=False)
    op.drop_index(op.f("ix_licenses_contract_product_id"), table_name="licenses")
    op.drop_constraint(
        op.f("fk_licenses_contract_product_id_contract_products"),
        "licenses",
        type_="foreignkey",
    )
    op.drop_column("licenses", "contract_product_id")
    op.create_foreign_key(
        op.f("fk_licenses_contract_id_contracts"),
        "licenses",
        "contracts",
        ["contract_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_licenses_interaction_product_id_interaction_products"),
        "licenses",
        "interaction_products",
        ["interaction_product_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_licenses_contract_id"), "licenses", ["contract_id"])
    op.create_index(
        op.f("ix_licenses_interaction_product_id"), "licenses", ["interaction_product_id"]
    )
    op.create_check_constraint(
        op.f("ck_licenses_valid_period"),
        "licenses",
        "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to",
    )

    op.drop_table("contract_programs")
    op.drop_table("contract_products")
    op.drop_table("contract_contacts")


def _content() -> None:
    for table in ("comments", "attachments"):
        op.add_column(table, sa.Column("workflow_instance_id", sa.Uuid(), nullable=True))
        # Материал события - во взаимодействии этого события, остальное -
        # во взаимодействии договора.
        op.execute(
            f"""
            UPDATE {table} t
            SET workflow_instance_id = coalesce(
                (SELECT e.workflow_instance_id FROM workflow_events e
                 WHERE e.id = t.workflow_event_id),
                (SELECT c.workflow_instance_id FROM contracts c WHERE c.id = t.contract_id)
            )
            """
        )
        op.alter_column(table, "workflow_instance_id", nullable=False)
        op.drop_index(op.f(f"ix_{table}_contract_id"), table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_contract_id_contracts"), table, type_="foreignkey")
        op.drop_column(table, "contract_id")
        op.create_foreign_key(
            op.f(f"fk_{table}_workflow_instance_id_workflow_instances"),
            table,
            "workflow_instances",
            ["workflow_instance_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(op.f(f"ix_{table}_workflow_instance_id"), table, ["workflow_instance_id"])

    op.add_column(
        "attachments", sa.Column("document_type", sa.String(length=32), nullable=True)
    )
    # Тип документа - по названию файла; остальное - «прочее».
    op.execute(
        """
        UPDATE attachments SET document_type = CASE
            WHEN lower(original_name) LIKE '%доп%соглаш%' THEN 'agreement'
            WHEN lower(original_name) LIKE '%договор%' THEN 'contract'
            WHEN lower(original_name) LIKE '%лиценз%' THEN 'license'
            WHEN lower(original_name) LIKE '%акт%' THEN 'act'
            WHEN lower(original_name) LIKE '%протокол%'
              OR lower(original_name) LIKE '%письм%' THEN 'letter'
            WHEN lower(original_name) LIKE '%учебн%'
              OR lower(original_name) LIKE '%программ%' THEN 'curriculum'
            WHEN lower(original_name) LIKE '%презентац%' THEN 'presentation'
            ELSE 'other' END
        """
    )


def _drop_contract_links() -> None:
    op.drop_index(op.f("ix_workflow_instances_contract_id"), table_name="workflow_instances")
    op.drop_constraint(
        op.f("fk_workflow_instances_contract_id_contracts"),
        "workflow_instances",
        type_="foreignkey",
    )
    op.drop_column("workflow_instances", "contract_id")
    op.drop_column("workflow_instances", "completed_at")

    op.drop_index(op.f("ix_contracts_manager_id"), table_name="contracts")
    op.drop_index(op.f("ix_contracts_university_id"), table_name="contracts")
    op.drop_constraint(op.f("fk_contracts_manager_id_users"), "contracts", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_contracts_university_id_universities"), "contracts", type_="foreignkey"
    )
    op.drop_column("contracts", "manager_id")
    op.drop_column("contracts", "university_id")


def _universities_and_access() -> None:
    op.add_column("universities", sa.Column("inn", sa.String(length=12), nullable=True))
    op.add_column(
        "universities",
        sa.Column("status", sa.String(length=16), server_default="confirmed", nullable=False),
    )
    op.add_column(
        "universities",
        sa.Column("origin", sa.String(length=16), server_default="manual", nullable=False),
    )
    op.add_column("universities", sa.Column("confirmed_by_id", sa.Uuid(), nullable=True))
    op.add_column(
        "universities",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("universities", sa.Column("merged_into_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE universities SET status = CASE WHEN is_active THEN 'confirmed' "
        "ELSE 'archived' END, confirmed_at = created_at"
    )
    op.drop_column("universities", "is_active")
    op.create_unique_constraint(op.f("uq_universities_inn"), "universities", ["inn"])
    op.create_index(op.f("ix_universities_status"), "universities", ["status"])
    op.create_foreign_key(
        op.f("fk_universities_confirmed_by_id_users"),
        "universities",
        "users",
        ["confirmed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_universities_merged_into_id_universities"),
        "universities",
        "universities",
        ["merged_into_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("user_university_access", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column(
        "user_university_access", sa.Column("granted_by_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "user_university_access",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_university_access",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_university_access", sa.Column("revoked_by_id", sa.Uuid(), nullable=True)
    )
    op.execute(
        "UPDATE user_university_access SET reason = 'Выдан до введения оснований доступа'"
    )
    for column in ("granted_by_id", "revoked_by_id"):
        op.create_foreign_key(
            op.f(f"fk_user_university_access_{column}_users"),
            "user_university_access",
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )

    op.add_column(
        "users",
        sa.Column(
            "permissions",
            postgresql.ARRAY(sa.String(length=48)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("head_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("data_scope_reason", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("data_scope_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_users_head_id_users"), "users", "users", ["head_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(op.f("ix_users_head_id"), "users", ["head_id"])


def _integrations() -> None:
    op.add_column(
        "integration_runs",
        sa.Column("trigger", sa.String(length=16), server_default="manual", nullable=False),
    )
    op.add_column(
        "integration_runs",
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "integration_runs",
        sa.Column("records_pending", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        "UPDATE integration_runs SET status = 'partial' "
        "WHERE status = 'success' AND records_failed > 0"
    )
    op.create_table(
        "integration_run_errors",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["integration_runs.id"],
            name=op.f("fk_integration_run_errors_run_id_integration_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_run_errors")),
    )
    op.create_index(
        op.f("ix_integration_run_errors_run_id"), "integration_run_errors", ["run_id"]
    )
    op.create_table(
        "integration_mappings",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_name", sa.String(length=500), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("suggested_entity_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_by_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["users.id"],
            name=op.f("fk_integration_mappings_resolved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["integration_sources.id"],
            name=op.f("fk_integration_mappings_source_id_integration_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_mappings")),
        sa.UniqueConstraint(
            "source_id",
            "entity_type",
            "external_id",
            name=op.f("uq_integration_mappings_source_id"),
        ),
    )
    op.create_index(
        op.f("ix_integration_mappings_source_id"), "integration_mappings", ["source_id"]
    )
    # Связи «заявка сайта -> договор» больше не нужны: заявка вуза теперь
    # ведёт к взаимодействию.
    op.execute(
        """
        UPDATE external_links l
        SET entity_type = 'interaction', entity_id = c.workflow_instance_id
        FROM contracts c
        WHERE l.entity_type = 'contract' AND c.id = l.entity_id
        """
    )


def _learning() -> None:
    op.create_table(
        "learning_streams",
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(length=16), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["it_programs.id"],
            name=op.f("fk_learning_streams_program_id_it_programs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["integration_sources.id"],
            name=op.f("fk_learning_streams_source_id_integration_sources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_streams")),
        sa.UniqueConstraint(
            "source_id", "external_id", name=op.f("uq_learning_streams_source_id")
        ),
    )
    op.create_index(
        op.f("ix_learning_streams_program_id"), "learning_streams", ["program_id"]
    )

    op.add_column("learning_applications", sa.Column("stream_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_learning_applications_stream_id_learning_streams"),
        "learning_applications",
        "learning_streams",
        ["stream_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_learning_applications_stream_id"), "learning_applications", ["stream_id"]
    )
    # Потоки из номеров заявок: номер отдельно от периода не опознаёт поток,
    # поэтому ключ - программа (или курс), номер и полугодие набора.
    op.execute(
        """
        INSERT INTO learning_streams
            (id, source_id, external_id, program_id, number, period, created_at, updated_at)
        SELECT gen_random_uuid(), source_id, key, program_id, stream_number, period, now(), now()
        FROM (
            SELECT DISTINCT ON (source_id, key)
                   source_id, program_id, stream_number, period, key
            FROM (
                SELECT a.source_id, a.program_id, a.stream_number,
                       to_char(a.submitted_at, 'YYYY') || '-' ||
                       CASE WHEN extract(month FROM a.submitted_at) <= 6 THEN 'H1' ELSE 'H2' END
                           AS period,
                       'auto:' || coalesce(a.program_id::text, lower(a.course_name)) || ':' ||
                       a.stream_number || ':' || to_char(a.submitted_at, 'YYYY') ||
                       CASE WHEN extract(month FROM a.submitted_at) <= 6 THEN 'H1' ELSE 'H2' END
                           AS key
                FROM learning_applications a
                WHERE a.stream_number IS NOT NULL
            ) numbered
            ORDER BY source_id, key
        ) streams
        """
    )
    op.execute(
        """
        UPDATE learning_applications a
        SET stream_id = s.id
        FROM learning_streams s
        WHERE a.stream_number IS NOT NULL
          AND s.source_id IS NOT DISTINCT FROM a.source_id
          AND s.external_id = 'auto:' || coalesce(a.program_id::text, lower(a.course_name))
              || ':' || a.stream_number || ':' || to_char(a.submitted_at, 'YYYY') ||
              CASE WHEN extract(month FROM a.submitted_at) <= 6 THEN 'H1' ELSE 'H2' END
        """
    )
    op.drop_index(
        op.f("ix_learning_applications_contract_id"), table_name="learning_applications"
    )
    op.drop_constraint(
        op.f("fk_learning_applications_contract_id_contracts"),
        "learning_applications",
        type_="foreignkey",
    )
    op.drop_column("learning_applications", "contract_id")

    op.add_column("learners", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.create_table(
        "enrollments",
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("stream_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("matched_by", sa.String(length=16), server_default="lms", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["learning_applications.id"],
            name=op.f("fk_enrollments_application_id_learning_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_enrollments_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["it_programs.id"],
            name=op.f("fk_enrollments_program_id_it_programs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stream_id"],
            ["learning_streams.id"],
            name=op.f("fk_enrollments_stream_id_learning_streams"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
        sa.UniqueConstraint(
            "learner_id",
            "program_id",
            "stream_id",
            name=op.f("uq_enrollments_learner_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(op.f("ix_enrollments_learner_id"), "enrollments", ["learner_id"])
    op.create_index(op.f("ix_enrollments_program_id"), "enrollments", ["program_id"])
    op.create_index(op.f("ix_enrollments_stream_id"), "enrollments", ["stream_id"])
    # Зачисления из прежнего правила «анкета нашлась по почте или телефону
    # заявки» - теперь это явная, проверяемая связь с программой и потоком.
    op.execute(
        """
        INSERT INTO enrollments
            (id, learner_id, program_id, stream_id, application_id, matched_by,
             created_at, updated_at)
        SELECT gen_random_uuid(), l.id, a.program_id, a.stream_id, a.id, 'contact', now(), now()
        FROM learning_applications a
        JOIN learners l
          ON (a.email IS NOT NULL AND l.email = a.email)
          OR (a.phone IS NOT NULL AND l.phone = a.phone)
        WHERE a.program_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def upgrade() -> None:
    _versions_and_stages()
    _interactions()
    _contracts()
    _composition()
    _content()
    _drop_contract_links()
    _universities_and_access()
    _integrations()
    _learning()

    op.create_index(
        "uq_workflow_versions_active",
        "workflow_versions",
        ["template_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    # Триггеры - последними: переносу данных выше они бы помешали.
    op.execute(GUARD_FUNCTION)
    op.execute(
        "CREATE TRIGGER workflow_stages_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON workflow_stages "
        "FOR EACH ROW EXECUTE FUNCTION workflow_structure_guard()"
    )
    op.execute(
        "CREATE TRIGGER workflow_transitions_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON workflow_transitions "
        "FOR EACH ROW EXECUTE FUNCTION workflow_structure_guard()"
    )


def downgrade() -> None:
    # Обратный перенос потерял бы данные, которых в старой модели нет
    # (взаимодействия без договора, результаты, связи программ и продуктов,
    # потоки и зачисления). Откат - восстановлением резервной копии,
    # см. cicd/README.md, раздел «Резервные копии».
    raise NotImplementedError(
        "Откат перехода на взаимодействия не поддерживается: восстановите резервную копию"
    )
