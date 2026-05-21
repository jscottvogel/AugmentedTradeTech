import math
import ulid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.models.customer import Customer
from apps.api.app.models.company import Company
from apps.api.app.models.membership import Membership, MembershipPlan
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger

def earn_loyalty_points(
    db: Session,
    customer_id: str,
    job_id: str | None,
    invoice_id: str,
    amount_cents: int
) -> LoyaltyLedger | None:
    """
    Credits loyalty points to a customer's account for a paid invoice.
    Ensures idempotency using 'earn-{invoice_id}' key.
    """
    # 1. Fetch customer and company_id
    customer = db.scalar(select(Customer).where(Customer.id == customer_id))
    if not customer:
        return None
    company_id = customer.company_id

    # Get or create customer's loyalty_account
    loyalty_account = db.scalar(
        select(LoyaltyAccount)
        .where(LoyaltyAccount.customer_id == customer_id)
    )
    if not loyalty_account:
        loyalty_account = LoyaltyAccount(
            id=f"loy_{ulid.new()}",
            company_id=company_id,
            customer_id=customer_id,
            is_active=True
        )
        db.add(loyalty_account)
        db.flush()

    # 2. Check for existing earn entry (idempotency check)
    idempotency_key = f"earn-{invoice_id}"
    existing_earn = db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.idempotency_key == idempotency_key)
    )
    if existing_earn:
        return existing_earn

    # 3. Get company loyalty config
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        return None

    earn_rate = company.loyalty_earn_rate or 1
    company_multiplier = float(company.loyalty_membership_multiplier or 1.0)

    # 4. Calculate base points
    base_points = int(math.floor((amount_cents / 100.0) * earn_rate))
    if base_points <= 0:
        return None

    # 5. Apply multiplier if customer has active membership
    multiplier = 1.0
    active_membership = db.scalar(
        select(Membership)
        .where(Membership.customer_id == customer_id)
        .where(Membership.status == "active")
    )
    if active_membership:
        # Check plan multiplier first, fall back to company membership multiplier
        plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == active_membership.plan_id))
        if plan and plan.loyalty_multiplier is not None:
            plan_multiplier = float(plan.loyalty_multiplier)
            if plan_multiplier != 1.0:
                multiplier = plan_multiplier
            else:
                multiplier = company_multiplier
        else:
            multiplier = company_multiplier

    points_to_earn = int(math.floor(base_points * multiplier))
    if points_to_earn <= 0:
        return None

    # 6. Expiry date calculation
    expires_at = None
    if company.loyalty_expiry_days is not None and company.loyalty_expiry_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=company.loyalty_expiry_days)

    # 7. Insert new ledger row
    ledger_entry = LoyaltyLedger(
        id=f"tx_{ulid.new()}",
        company_id=company_id,
        account_id=loyalty_account.id,
        entry_type="earn",
        points=points_to_earn,
        job_id=job_id,
        invoice_id=invoice_id,
        description=f"Earned {points_to_earn} points on invoice {invoice_id}",
        expires_at=expires_at,
        idempotency_key=idempotency_key
    )
    db.add(ledger_entry)
    db.flush()

    return ledger_entry
