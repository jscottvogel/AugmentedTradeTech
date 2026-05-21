"""add_portal_tables

Revision ID: dbc28536fce0
Revises: 05f8492d9931
Create Date: 2026-05-21 10:45:47.511574

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dbc28536fce0'
down_revision: Union[str, Sequence[str], None] = '05f8492d9931'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create customer_magic_link_tokens table
    op.create_table('customer_magic_link_tokens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_magic_link_tokens_customer_id'), 'customer_magic_link_tokens', ['customer_id'], unique=False)
    op.create_index(op.f('ix_customer_magic_link_tokens_token_hash'), 'customer_magic_link_tokens', ['token_hash'], unique=True)
    
    # Add primary_color column to companies table
    op.add_column('companies', sa.Column('primary_color', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('companies', 'primary_color')
    op.drop_index(op.f('ix_customer_magic_link_tokens_token_hash'), table_name='customer_magic_link_tokens')
    op.drop_index(op.f('ix_customer_magic_link_tokens_customer_id'), table_name='customer_magic_link_tokens')
    op.drop_table('customer_magic_link_tokens')
