"""add_availability_tracking

Revision ID: 9def635f50c1
Revises: 21aecdabec28
Create Date: 2026-05-20 10:47:23.164658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9def635f50c1'
down_revision: Union[str, Sequence[str], None] = '21aecdabec28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create availability_status_logs table
    op.create_table('availability_status_logs',
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('created_by', sa.String(), nullable=True),
    sa.Column('updated_by', sa.String(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_availability_status_logs_user_id'), 'availability_status_logs', ['user_id'], unique=False)
    
    # Add heartbeat and status changed fields to tech_profiles
    op.add_column('tech_profiles', sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tech_profiles', sa.Column('status_changed_at', sa.DateTime(timezone=True), server_default='now()', nullable=False))

    # Enable Row-Level Security (RLS)
    op.execute("ALTER TABLE availability_status_logs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE availability_status_logs FORCE ROW LEVEL SECURITY;")
    op.execute("""
    CREATE POLICY tenant_isolation_policy ON availability_status_logs
    FOR ALL
    USING (
        company_id = NULLIF(current_setting('app.current_company_id', true), '')::text
        OR current_setting('app.current_role', true) = 'platform_admin'
    );
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON availability_status_logs;")
    
    # Drop availability fields and table
    op.drop_column('tech_profiles', 'status_changed_at')
    op.drop_column('tech_profiles', 'last_heartbeat_at')
    op.drop_index(op.f('ix_availability_status_logs_user_id'), table_name='availability_status_logs')
    op.drop_table('availability_status_logs')
