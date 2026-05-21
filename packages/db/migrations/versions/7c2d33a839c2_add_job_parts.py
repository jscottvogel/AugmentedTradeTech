"""add_job_parts

Revision ID: 7c2d33a839c2
Revises: 9def635f50c1
Create Date: 2026-05-20 13:30:03.216734

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2d33a839c2'
down_revision: Union[str, Sequence[str], None] = '9def635f50c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create job_parts table
    op.create_table(
        'job_parts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('company_id', sa.String(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.String(), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('price_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('serial_number', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Create indexes
    op.create_index('ix_job_parts_job_id', 'job_parts', ['job_id'])
    op.create_index('ix_job_parts_company_id', 'job_parts', ['company_id'])

    # 2. Enable RLS and Force RLS
    op.execute("ALTER TABLE job_parts ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE job_parts FORCE ROW LEVEL SECURITY;")

    # 3. Create tenant isolation policy
    op.execute("""
    CREATE POLICY tenant_isolation_policy ON job_parts
    FOR ALL
    USING (
        company_id = NULLIF(current_setting('app.current_company_id', true), '')::text
        OR current_setting('app.current_role', true) = 'platform_admin'
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_parts CASCADE;")
