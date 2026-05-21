"""add_company_loyalty_fields

Revision ID: 9baa7328e971
Revises: dbc28536fce0
Create Date: 2026-05-21 11:14:33.712340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9baa7328e971'
down_revision: Union[str, Sequence[str], None] = 'dbc28536fce0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('companies', sa.Column('loyalty_earn_rate', sa.Integer(), server_default='1', nullable=False))
    op.add_column('companies', sa.Column('loyalty_membership_multiplier', sa.Numeric(precision=4, scale=2), server_default='1.00', nullable=False))
    op.add_column('companies', sa.Column('loyalty_expiry_days', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('companies', 'loyalty_expiry_days')
    op.drop_column('companies', 'loyalty_membership_multiplier')
    op.drop_column('companies', 'loyalty_earn_rate')
