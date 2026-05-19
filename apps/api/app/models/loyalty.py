from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index
from apps.api.app.models.base import Base

class LoyaltyAccount(Base):
    __tablename__ = "loyalty_accounts"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "customer_id", name="uq_loyalty_account"),
    )

class LoyaltyLedger(Base):
    __tablename__ = "loyalty_ledger"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(String, ForeignKey("loyalty_accounts.id", ondelete="CASCADE"), nullable=False)
    entry_type = Column(String, nullable=False) # earn | redeem | expire | adjustment_credit | adjustment_debit
    points = Column(Integer, nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    invoice_id = Column(String, ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    description = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    voided_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            entry_type.in_(["earn", "redeem", "expire", "adjustment_credit", "adjustment_debit"]),
            name="chk_entry_type"
        ),
        CheckConstraint(
            "points > 0",
            name="chk_points_positive"
        ),
        Index("ix_loyalty_ledger_account_id_created_at", "account_id", "created_at"),
    )

class LoyaltyBalanceView(Base):
    """
    Read-only view mapping for database loyalty_balances view.
    """
    __tablename__ = "loyalty_balances"

    account_id = Column(String, primary_key=True)
    company_id = Column(String)
    customer_id = Column(String)
    balance = Column(Integer)
    lifetime_earned = Column(Integer)
