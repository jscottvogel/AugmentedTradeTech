"""add_auth_tables_and_columns

Revision ID: c3488aba99ab
Revises: f4d69055536d
Create Date: 2026-05-20 10:16:53.428073

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3488aba99ab'
down_revision: Union[str, Sequence[str], None] = 'f4d69055536d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create magic_link_tokens table
    op.create_table('magic_link_tokens',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('created_by', sa.String(), nullable=True),
    sa.Column('updated_by', sa.String(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_magic_link_tokens_token_hash'), 'magic_link_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_magic_link_tokens_user_id'), 'magic_link_tokens', ['user_id'], unique=False)
    
    # Create refresh_tokens table
    op.create_table('refresh_tokens',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('created_by', sa.String(), nullable=True),
    sa.Column('updated_by', sa.String(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    
    # Add new auth columns to users table
    op.add_column('users', sa.Column('password_hash', sa.String(), nullable=True))
    sa_mfa_enabled = sa.Column('mfa_enabled', sa.Boolean(), nullable=True) # First create as nullable
    op.add_column('users', sa_mfa_enabled)
    op.add_column('users', sa.Column('mfa_secret', sa.String(), nullable=True))
    
    # Update existing users to have mfa_enabled=False, then make it non-nullable
    op.execute("UPDATE users SET mfa_enabled = FALSE WHERE mfa_enabled IS NULL")
    op.alter_column('users', 'mfa_enabled', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'mfa_enabled')
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'password_hash')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_magic_link_tokens_user_id'), table_name='magic_link_tokens')
    op.drop_index(op.f('ix_magic_link_tokens_token_hash'), table_name='magic_link_tokens')
    op.drop_table('magic_link_tokens')
