"""add_qbo_item_mappings

Revision ID: 05f8492d9931
Revises: 47047f3b5ca0
Create Date: 2026-05-21 10:12:10.198683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '05f8492d9931'
down_revision: Union[str, Sequence[str], None] = '47047f3b5ca0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('companies', sa.Column('qbo_item_mappings', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('companies', 'qbo_item_mappings')
