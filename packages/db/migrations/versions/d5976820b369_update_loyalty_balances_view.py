"""update_loyalty_balances_view

Revision ID: d5976820b369
Revises: 9baa7328e971
Create Date: 2026-05-21 11:17:15.015508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5976820b369'
down_revision: Union[str, Sequence[str], None] = '9baa7328e971'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE VIEW loyalty_balances AS
    SELECT 
        la.id AS account_id,
        la.company_id,
        la.customer_id,
        COALESCE(SUM(CASE WHEN ll.entry_type IN ('earn', 'adjustment_credit') AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) -
        COALESCE(SUM(CASE WHEN ll.entry_type IN ('redeem', 'expire', 'adjustment_debit') AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) AS balance,
        COALESCE(SUM(CASE WHEN ll.entry_type = 'earn' AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) AS lifetime_earned
    FROM loyalty_accounts la
    LEFT JOIN loyalty_ledger ll ON la.id = ll.account_id
    GROUP BY la.id, la.company_id, la.customer_id;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
    CREATE OR REPLACE VIEW loyalty_balances AS
    SELECT 
        la.id AS account_id,
        la.company_id,
        la.customer_id,
        COALESCE(SUM(CASE WHEN ll.entry_type IN ('earn', 'adjustment_credit') AND (ll.expires_at IS NULL OR ll.expires_at > now()) AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) -
        COALESCE(SUM(CASE WHEN ll.entry_type IN ('redeem', 'expire', 'adjustment_debit') AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) AS balance,
        COALESCE(SUM(CASE WHEN ll.entry_type = 'earn' AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) AS lifetime_earned
    FROM loyalty_accounts la
    LEFT JOIN loyalty_ledger ll ON la.id = ll.account_id
    GROUP BY la.id, la.company_id, la.customer_id;
    """)
