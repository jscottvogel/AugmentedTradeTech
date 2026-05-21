"""add_deleted_at_to_job_photos

Revision ID: 47047f3b5ca0
Revises: 691d63caf0a0
Create Date: 2026-05-20 17:03:36.988587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47047f3b5ca0'
down_revision: Union[str, Sequence[str], None] = '691d63caf0a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('job_photos', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('job_photos', 'deleted_at')
