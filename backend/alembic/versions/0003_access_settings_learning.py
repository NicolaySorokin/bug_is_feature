"""user access and roles snapshot, settings, data version, learning data, vendor contacts

Revision ID: 5a1f3c2b7d90
Revises: efbb83baf31b
Create Date: 2026-09-25 16:22:59.976145
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '5a1f3c2b7d90'
down_revision: str | None = 'efbb83baf31b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('data_version',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_data_version'))
    )
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_app_settings_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings'))
    )
    op.create_table('learners',
    sa.Column('source_id', sa.Uuid(), nullable=True),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('middle_name', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('gender', sa.String(length=1), nullable=True),
    sa.Column('education', sa.String(length=255), nullable=True),
    sa.Column('region', sa.String(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['integration_sources.id'], name=op.f('fk_learners_source_id_integration_sources'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_learners'))
    )
    op.create_index(op.f('ix_learners_email'), 'learners', ['email'], unique=True)
    op.create_index(op.f('ix_learners_phone'), 'learners', ['phone'], unique=False)
    op.create_table('vendor_contacts',
    sa.Column('vendor_id', sa.Uuid(), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('contact_channel', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], name=op.f('fk_vendor_contacts_vendor_id_vendors'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vendor_contacts'))
    )
    op.create_index(op.f('ix_vendor_contacts_vendor_id'), 'vendor_contacts', ['vendor_id'], unique=False)
    op.create_table('user_university_access',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('university_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_user_university_access_university_id_universities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_university_access_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'university_id', name=op.f('pk_user_university_access'))
    )
    op.create_index(op.f('ix_user_university_access_university_id'), 'user_university_access', ['university_id'], unique=False)
    op.create_table('learning_applications',
    sa.Column('source_id', sa.Uuid(), nullable=True),
    sa.Column('external_id', sa.String(length=100), nullable=False),
    sa.Column('program_id', sa.Uuid(), nullable=True),
    sa.Column('course_name', sa.String(length=500), nullable=False),
    sa.Column('stream_number', sa.Integer(), nullable=True),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('middle_name', sa.String(length=100), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('university_id', sa.Uuid(), nullable=True),
    sa.Column('contract_id', sa.Uuid(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('fk_learning_applications_contract_id_contracts'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['program_id'], ['it_programs.id'], name=op.f('fk_learning_applications_program_id_it_programs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['integration_sources.id'], name=op.f('fk_learning_applications_source_id_integration_sources'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('fk_learning_applications_university_id_universities'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_learning_applications')),
    sa.UniqueConstraint('source_id', 'external_id', name=op.f('uq_learning_applications_source_id'))
    )
    op.create_index(op.f('ix_learning_applications_contract_id'), 'learning_applications', ['contract_id'], unique=False)
    op.create_index(op.f('ix_learning_applications_email'), 'learning_applications', ['email'], unique=False)
    op.create_index(op.f('ix_learning_applications_phone'), 'learning_applications', ['phone'], unique=False)
    op.create_index(op.f('ix_learning_applications_program_id'), 'learning_applications', ['program_id'], unique=False)
    op.create_index(op.f('ix_learning_applications_submitted_at'), 'learning_applications', ['submitted_at'], unique=False)
    op.create_index(op.f('ix_learning_applications_university_id'), 'learning_applications', ['university_id'], unique=False)
    op.add_column('it_products', sa.Column('contact_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_it_products_contact_id_vendor_contacts'), 'it_products', 'vendor_contacts', ['contact_id'], ['id'], ondelete='SET NULL')
    op.add_column('integration_runs', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('roles', postgresql.ARRAY(sa.String(length=32)), server_default='{}', nullable=False))
    op.add_column('users', sa.Column('data_scope', sa.String(length=16), server_default='default', nullable=False))
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    # Единственная строка счётчика изменений: кэш читает её по первичному ключу.
    op.execute("INSERT INTO data_version (id, version) VALUES (1, 0) ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.drop_column('users', 'last_seen_at')
    op.drop_column('integration_runs', 'notes')
    op.drop_column('users', 'data_scope')
    op.drop_column('users', 'roles')
    op.drop_constraint(op.f('fk_it_products_contact_id_vendor_contacts'), 'it_products', type_='foreignkey')
    op.drop_column('it_products', 'contact_id')
    op.drop_index(op.f('ix_learning_applications_university_id'), table_name='learning_applications')
    op.drop_index(op.f('ix_learning_applications_submitted_at'), table_name='learning_applications')
    op.drop_index(op.f('ix_learning_applications_program_id'), table_name='learning_applications')
    op.drop_index(op.f('ix_learning_applications_phone'), table_name='learning_applications')
    op.drop_index(op.f('ix_learning_applications_email'), table_name='learning_applications')
    op.drop_index(op.f('ix_learning_applications_contract_id'), table_name='learning_applications')
    op.drop_table('learning_applications')
    op.drop_index(op.f('ix_user_university_access_university_id'), table_name='user_university_access')
    op.drop_table('user_university_access')
    op.drop_index(op.f('ix_vendor_contacts_vendor_id'), table_name='vendor_contacts')
    op.drop_table('vendor_contacts')
    op.drop_index(op.f('ix_learners_phone'), table_name='learners')
    op.drop_index(op.f('ix_learners_email'), table_name='learners')
    op.drop_table('learners')
    op.drop_table('app_settings')
    op.drop_table('data_version')
