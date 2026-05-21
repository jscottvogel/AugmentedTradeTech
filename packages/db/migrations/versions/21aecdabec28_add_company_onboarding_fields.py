"""add_company_onboarding_fields

Revision ID: 21aecdabec28
Revises: c3488aba99ab
Create Date: 2026-05-20 10:25:24.301445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '21aecdabec28'
down_revision: Union[str, Sequence[str], None] = 'c3488aba99ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('companies', sa.Column('onboarding_step', sa.Integer(), server_default='1', nullable=False))
    op.add_column('companies', sa.Column('service_area_zips', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False))
    op.add_column('companies', sa.Column('business_hours', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('companies', 'business_hours')
    op.drop_column('companies', 'service_area_zips')
    op.drop_column('companies', 'onboarding_step')
