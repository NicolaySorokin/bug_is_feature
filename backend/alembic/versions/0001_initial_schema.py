"""initial schema

Revision ID: d63f94e3380a
Revises: 
Create Date: 2026-09-18 17:49:54.316732
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd63f94e3380a'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('it_directions',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_it_directions')),
    sa.UniqueConstraint('name', name=op.f('uq_it_directions_name'))
    )
    op.create_table('users',
    sa.Column('keycloak_id', sa.String(length=64), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_keycloak_id'), 'users', ['keycloak_id'], unique=True)
    op.create_table('vendors',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vendors')),
    sa.UniqueConstraint('name', name=op.f('uq_vendors_name'))
    )
    op.create_table('workflow_templates',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_templates')),
    sa.UniqueConstraint('name', name=op.f('uq_workflow_templates_name'))
    )
    op.create_table('it_products',
    sa.Column('vendor_id', sa.Uuid(), nullable=True),
    sa.Column('name', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], name=op.f('fk_it_products_vendor_id_vendors'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_it_products'))
    )
    op.create_index(op.f('ix_it_products_name'), 'it_products', ['name'], unique=False)
    op.create_index(op.f('ix_it_products_vendor_id'), 'it_products', ['vendor_id'], unique=False)
    op.create_table('it_programs',
    sa.Column('direction_id', sa.Uuid(), nullable=True),
    sa.Column('name', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['direction_id'], ['it_directions.id'], name=op.f('fk_it_programs_direction_id_it_directions'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_it_programs'))
    )
    op.create_index(op.f('ix_it_programs_direction_id'), 'it_programs', ['direction_id'], unique=False)
    op.create_index(op.f('ix_it_programs_name'), 'it_programs', ['name'], unique=False)
    op.create_table('universities',
    sa.Column('name', sa.String(length=500), nullable=False),
    sa.Column('short_name', sa.String(length=100), nullable=True),
    sa.Column('city', sa.String(length=255), nullable=True),
    sa.Column('website', sa.String(length=500), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('manager_id', sa.Uuid(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['manager_id'], ['users.id'], name=op.f('fk_universities_manager_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_universities'))
    )
    op.create_index(op.f('ix_universities_name'), 'universities', ['name'], unique=False)
    op.create_table('workflow_versions',
    sa.Column('template_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['template_id'], ['workflow_templates.id'], name=op.f('fk_workflow_versions_template_id_workflow_templates'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_versions')),
    sa.UniqueConstraint('template_id', 'version_number', name=op.f('uq_workflow_versions_template_id'))
    )
    op.create_index(op.f('ix_workflow_versions_template_id'), 'workflow_versions', ['template_id'], unique=False)
    op.create_table('contracts',
    sa.Column('university_id', sa.Uuid(), nullable=False),
    sa.Column('manager_id', sa.Uuid(), nullable=True),
    sa.Column('number', sa.String(length=100), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=True),
    sa.Column('signed_at', sa.Date(), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=32), server_default='draft', nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['manager_id'], ['users.id'], name=op.f('fk_contracts_manager_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_contracts_university_id_universities'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contracts'))
    )
    op.create_index(op.f('ix_contracts_manager_id'), 'contracts', ['manager_id'], unique=False)
    op.create_index(op.f('ix_contracts_number'), 'contracts', ['number'], unique=False)
    op.create_index(op.f('ix_contracts_university_id'), 'contracts', ['university_id'], unique=False)
    op.create_table('program_products',
    sa.Column('program_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['it_products.id'], name=op.f('fk_program_products_product_id_it_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['program_id'], ['it_programs.id'], name=op.f('fk_program_products_program_id_it_programs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('program_id', 'product_id', name=op.f('pk_program_products'))
    )
    op.create_table('university_contacts',
    sa.Column('university_id', sa.Uuid(), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('position', sa.String(length=255), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_university_contacts_university_id_universities'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_university_contacts'))
    )
    op.create_index(op.f('ix_university_contacts_university_id'), 'university_contacts', ['university_id'], unique=False)
    op.create_table('workflow_stages',
    sa.Column('workflow_version_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_optional', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_final', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('sla_days', sa.Integer(), nullable=True),
    sa.Column('layout_x', sa.Integer(), nullable=True),
    sa.Column('layout_y', sa.Integer(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['workflow_version_id'], ['workflow_versions.id'], name=op.f('fk_workflow_stages_workflow_version_id_workflow_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_stages')),
    sa.UniqueConstraint('workflow_version_id', 'code', name=op.f('uq_workflow_stages_workflow_version_id'))
    )
    op.create_index(op.f('ix_workflow_stages_workflow_version_id'), 'workflow_stages', ['workflow_version_id'], unique=False)
    op.create_table('contract_contacts',
    sa.Column('contract_id', sa.Uuid(), nullable=False),
    sa.Column('contact_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=255), nullable=True),
    sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['contact_id'], ['university_contacts.id'], name=op.f('fk_contract_contacts_contact_id_university_contacts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_contract_contacts_contract_id_contracts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('contract_id', 'contact_id', name=op.f('pk_contract_contacts'))
    )
    op.create_table('contract_products',
    sa.Column('contract_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('transfer_status', sa.String(length=32), server_default='not_started', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_contract_products_contract_id_contracts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['it_products.id'], name=op.f('fk_contract_products_product_id_it_products'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contract_products')),
    sa.UniqueConstraint('contract_id', 'product_id', name=op.f('uq_contract_products_contract_id'))
    )
    op.create_index(op.f('ix_contract_products_contract_id'), 'contract_products', ['contract_id'], unique=False)
    op.create_index(op.f('ix_contract_products_product_id'), 'contract_products', ['product_id'], unique=False)
    op.create_table('contract_programs',
    sa.Column('contract_id', sa.Uuid(), nullable=False),
    sa.Column('program_id', sa.Uuid(), nullable=False),
    sa.Column('implementation_status', sa.String(length=32), server_default='not_started', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_contract_programs_contract_id_contracts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['program_id'], ['it_programs.id'], name=op.f('fk_contract_programs_program_id_it_programs'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contract_programs')),
    sa.UniqueConstraint('contract_id', 'program_id', name=op.f('uq_contract_programs_contract_id'))
    )
    op.create_index(op.f('ix_contract_programs_contract_id'), 'contract_programs', ['contract_id'], unique=False)
    op.create_index(op.f('ix_contract_programs_program_id'), 'contract_programs', ['program_id'], unique=False)
    op.create_table('workflow_instances',
    sa.Column('contract_id', sa.Uuid(), nullable=False),
    sa.Column('workflow_version_id', sa.Uuid(), nullable=False),
    sa.Column('current_stage_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.String(length=32), server_default='in_progress', nullable=False),
    sa.Column('current_stage_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_workflow_instances_contract_id_contracts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['current_stage_id'], ['workflow_stages.id'], name=op.f('fk_workflow_instances_current_stage_id_workflow_stages'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workflow_version_id'], ['workflow_versions.id'], name=op.f('fk_workflow_instances_workflow_version_id_workflow_versions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_instances'))
    )
    op.create_index(op.f('ix_workflow_instances_contract_id'), 'workflow_instances', ['contract_id'], unique=False)
    op.create_index(op.f('ix_workflow_instances_workflow_version_id'), 'workflow_instances', ['workflow_version_id'], unique=False)
    op.create_table('workflow_transitions',
    sa.Column('workflow_version_id', sa.Uuid(), nullable=False),
    sa.Column('from_stage_id', sa.Uuid(), nullable=False),
    sa.Column('to_stage_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('is_backward', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('requires_comment', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['from_stage_id'], ['workflow_stages.id'], name=op.f('fk_workflow_transitions_from_stage_id_workflow_stages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['to_stage_id'], ['workflow_stages.id'], name=op.f('fk_workflow_transitions_to_stage_id_workflow_stages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_version_id'], ['workflow_versions.id'], name=op.f('fk_workflow_transitions_workflow_version_id_workflow_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_transitions')),
    sa.UniqueConstraint('from_stage_id', 'to_stage_id', name=op.f('uq_workflow_transitions_from_stage_id'))
    )
    op.create_index(op.f('ix_workflow_transitions_from_stage_id'), 'workflow_transitions', ['from_stage_id'], unique=False)
    op.create_index(op.f('ix_workflow_transitions_to_stage_id'), 'workflow_transitions', ['to_stage_id'], unique=False)
    op.create_index(op.f('ix_workflow_transitions_workflow_version_id'), 'workflow_transitions', ['workflow_version_id'], unique=False)
    op.create_table('licenses',
    sa.Column('contract_product_id', sa.Uuid(), nullable=False),
    sa.Column('number', sa.String(length=100), nullable=True),
    sa.Column('seats', sa.Integer(), nullable=True),
    sa.Column('signed_at', sa.Date(), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['contract_product_id'], ['contract_products.id'], name=op.f('fk_licenses_contract_product_id_contract_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_licenses'))
    )
    op.create_index(op.f('ix_licenses_contract_product_id'), 'licenses', ['contract_product_id'], unique=False)
    op.create_table('workflow_events',
    sa.Column('workflow_instance_id', sa.Uuid(), nullable=False),
    sa.Column('from_stage_id', sa.Uuid(), nullable=True),
    sa.Column('to_stage_id', sa.Uuid(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['from_stage_id'], ['workflow_stages.id'], name=op.f('fk_workflow_events_from_stage_id_workflow_stages'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['to_stage_id'], ['workflow_stages.id'], name=op.f('fk_workflow_events_to_stage_id_workflow_stages'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_workflow_events_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workflow_instance_id'], ['workflow_instances.id'], name=op.f('fk_workflow_events_workflow_instance_id_workflow_instances'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_events'))
    )
    op.create_index(op.f('ix_workflow_events_workflow_instance_id'), 'workflow_events', ['workflow_instance_id'], unique=False)
    op.create_table('attachments',
    sa.Column('contract_id', sa.Uuid(), nullable=False),
    sa.Column('workflow_event_id', sa.Uuid(), nullable=True),
    sa.Column('uploaded_by', sa.Uuid(), nullable=True),
    sa.Column('original_name', sa.String(length=500), nullable=False),
    sa.Column('storage_path', sa.String(length=1000), nullable=False),
    sa.Column('mime_type', sa.String(length=255), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_attachments_contract_id_contracts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name=op.f('fk_attachments_uploaded_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workflow_event_id'], ['workflow_events.id'], name=op.f('fk_attachments_workflow_event_id_workflow_events'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attachments'))
    )
    op.create_index(op.f('ix_attachments_contract_id'), 'attachments', ['contract_id'], unique=False)
    op.create_index(op.f('ix_attachments_workflow_event_id'), 'attachments', ['workflow_event_id'], unique=False)
    op.create_table('comments',
    sa.Column('contract_id', sa.Uuid(), nullable=False),
    sa.Column('workflow_event_id', sa.Uuid(), nullable=True),
    sa.Column('author_id', sa.Uuid(), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_comments_author_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_comments_contract_id_contracts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_event_id'], ['workflow_events.id'], name=op.f('fk_comments_workflow_event_id_workflow_events'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comments'))
    )
    op.create_index(op.f('ix_comments_contract_id'), 'comments', ['contract_id'], unique=False)
    op.create_index(op.f('ix_comments_workflow_event_id'), 'comments', ['workflow_event_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_comments_workflow_event_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_contract_id'), table_name='comments')
    op.drop_table('comments')
    op.drop_index(op.f('ix_attachments_workflow_event_id'), table_name='attachments')
    op.drop_index(op.f('ix_attachments_contract_id'), table_name='attachments')
    op.drop_table('attachments')
    op.drop_index(op.f('ix_workflow_events_workflow_instance_id'), table_name='workflow_events')
    op.drop_table('workflow_events')
    op.drop_index(op.f('ix_licenses_contract_product_id'), table_name='licenses')
    op.drop_table('licenses')
    op.drop_index(op.f('ix_workflow_transitions_workflow_version_id'), table_name='workflow_transitions')
    op.drop_index(op.f('ix_workflow_transitions_to_stage_id'), table_name='workflow_transitions')
    op.drop_index(op.f('ix_workflow_transitions_from_stage_id'), table_name='workflow_transitions')
    op.drop_table('workflow_transitions')
    op.drop_index(op.f('ix_workflow_instances_workflow_version_id'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_contract_id'), table_name='workflow_instances')
    op.drop_table('workflow_instances')
    op.drop_index(op.f('ix_contract_programs_program_id'), table_name='contract_programs')
    op.drop_index(op.f('ix_contract_programs_contract_id'), table_name='contract_programs')
    op.drop_table('contract_programs')
    op.drop_index(op.f('ix_contract_products_product_id'), table_name='contract_products')
    op.drop_index(op.f('ix_contract_products_contract_id'), table_name='contract_products')
    op.drop_table('contract_products')
    op.drop_table('contract_contacts')
    op.drop_index(op.f('ix_workflow_stages_workflow_version_id'), table_name='workflow_stages')
    op.drop_table('workflow_stages')
    op.drop_index(op.f('ix_university_contacts_university_id'), table_name='university_contacts')
    op.drop_table('university_contacts')
    op.drop_table('program_products')
    op.drop_index(op.f('ix_contracts_university_id'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_number'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_manager_id'), table_name='contracts')
    op.drop_table('contracts')
    op.drop_index(op.f('ix_workflow_versions_template_id'), table_name='workflow_versions')
    op.drop_table('workflow_versions')
    op.drop_index(op.f('ix_universities_name'), table_name='universities')
    op.drop_table('universities')
    op.drop_index(op.f('ix_it_programs_name'), table_name='it_programs')
    op.drop_index(op.f('ix_it_programs_direction_id'), table_name='it_programs')
    op.drop_table('it_programs')
    op.drop_index(op.f('ix_it_products_vendor_id'), table_name='it_products')
    op.drop_index(op.f('ix_it_products_name'), table_name='it_products')
    op.drop_table('it_products')
    op.drop_table('workflow_templates')
    op.drop_table('vendors')
    op.drop_index(op.f('ix_users_keycloak_id'), table_name='users')
    op.drop_table('users')
    op.drop_table('it_directions')
