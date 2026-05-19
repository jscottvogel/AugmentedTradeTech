from sqlalchemy import Column, String, Boolean, Integer, Numeric, DateTime, ForeignKey, CheckConstraint, Index, text
from apps.api.app.models.base import Base, TenantAuditMixin

class MembershipPlan(Base, TenantAuditMixin):
    __tablename__ = "membership_plans"

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    trade = Column(String, nullable=False) # hvac | garage_door | both
    is_active = Column(Boolean, nullable=False, default=True)
    monthly_price_cents = Column(Integer, nullable=True)
    annual_price_cents = Column(Integer, nullable=True)
    included_visits_count = Column(Integer, nullable=False, default=0)
    visit_reset_period = Column(String, nullable=False, default="annual") # annual | monthly
    carryover_visits = Column(Boolean, nullable=False, default=False)
    labor_discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    parts_discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    priority_scheduling = Column(Boolean, nullable=False, default=False)
    loyalty_multiplier = Column(Numeric(4, 2), nullable=False, default=1.0)
    stripe_monthly_price_id = Column(String, nullable=True)
    stripe_annual_price_id = Column(String, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            trade.in_(["hvac", "garage_door", "both"]),
            name="chk_plan_trade"
        ),
        CheckConstraint(
            "monthly_price_cents IS NOT NULL OR annual_price_cents IS NOT NULL",
            name="chk_has_price"
        ),
    )

class Membership(Base, TenantAuditMixin):
    __tablename__ = "memberships"

    customer_id = Column(String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(String, ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String, nullable=False, default="active") # active | paused | suspended | cancelled | expired
    billing_cadence = Column(String, nullable=False) # monthly | annual
    current_period_start = Column(DateTime(timezone=True), nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=False)
    visits_used_this_period = Column(Integer, nullable=False, default=0)
    visits_carried_over = Column(Integer, nullable=False, default=0)
    enrolled_by = Column(String, nullable=False) # tech | customer | dispatcher
    enrolled_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True, unique=True)
    stripe_customer_id = Column(String, nullable=True)
    next_renewal_at = Column(DateTime(timezone=True), nullable=True)
    grace_period_ends_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            status.in_(["active", "paused", "suspended", "cancelled", "expired"]),
            name="chk_membership_status"
        ),
        CheckConstraint(
            billing_cadence.in_(["monthly", "annual"]),
            name="chk_billing_cadence"
        ),
        Index("ix_memberships_next_renewal_at", "next_renewal_at", postgresql_where=text("status = 'active'")),
    )
