import os
import logging
import secrets
import ulid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

import stripe

from apps.api.app.core.database import get_db
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.customer import Customer
from apps.api.app.models.company import Company
from apps.api.app.routers.membership_plans import check_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memberships", tags=["Memberships"])

# Pydantic Schemas
class MembershipEnrollRequest(BaseModel):
    customer_id: str
    plan_id: str
    billing_cadence: str # monthly | annual
    payment_method_id: Optional[str] = None

class CancelRequest(BaseModel):
    cancellation_reason: Optional[str] = None

# Serializer helper
def serialize_membership(db: Session, mem: Membership):
    plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == mem.plan_id))
    customer = db.scalar(select(Customer).where(Customer.id == mem.customer_id))
    return {
        "id": mem.id,
        "company_id": mem.company_id,
        "customer_id": mem.customer_id,
        "plan_id": mem.plan_id,
        "status": mem.status,
        "billing_cadence": mem.billing_cadence,
        "current_period_start": mem.current_period_start.isoformat() if mem.current_period_start else None,
        "current_period_end": mem.current_period_end.isoformat() if mem.current_period_end else None,
        "visits_used_this_period": mem.visits_used_this_period,
        "visits_carried_over": mem.visits_carried_over,
        "enrolled_by": mem.enrolled_by,
        "enrolled_at": mem.enrolled_at.isoformat() if mem.enrolled_at else None,
        "cancelled_at": mem.cancelled_at.isoformat() if mem.cancelled_at else None,
        "cancellation_reason": mem.cancellation_reason,
        "stripe_subscription_id": mem.stripe_subscription_id,
        "stripe_customer_id": mem.stripe_customer_id,
        "next_renewal_at": mem.next_renewal_at.isoformat() if mem.next_renewal_at else None,
        "grace_period_ends_at": mem.grace_period_ends_at.isoformat() if mem.grace_period_ends_at else None,
        "plan_name": plan.name if plan else None,
        "customer_name": f"{customer.first_name} {customer.last_name}" if customer else None,
    }

# Routes
@router.post("")
def enroll_customer(
    req: MembershipEnrollRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    company_id = request.state.company_id
    user_role = request.state.role

    # 1. Retrieve customer and plan
    customer = db.scalar(select(Customer).where(Customer.id == req.customer_id))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == req.plan_id))
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Membership plan not found or inactive")

    if req.billing_cadence not in ["monthly", "annual"]:
        raise HTTPException(status_code=400, detail="Invalid billing cadence. Must be 'monthly' or 'annual'.")

    # 2. Check for active membership
    active_mem = db.scalar(
        select(Membership)
        .where(Membership.customer_id == req.customer_id)
        .where(Membership.status == "active")
    )
    if active_mem:
        raise HTTPException(status_code=400, detail="Customer already has an active membership")

    # 3. Resolve Stripe details
    company = db.scalar(select(Company).where(Company.id == company_id))
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    is_mock = (
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )

    # 4. Find historical Stripe Customer
    stripe_customer_id = None
    past_mem = db.scalar(
        select(Membership)
        .where(Membership.customer_id == req.customer_id)
        .where(Membership.stripe_customer_id.is_not(None))
        .limit(1)
    )
    if past_mem:
        stripe_customer_id = past_mem.stripe_customer_id

    # 5. Enrollment flow
    if is_mock:
        if not stripe_customer_id:
            stripe_customer_id = f"cus_mock_{secrets.token_hex(8)}"

        if not req.payment_method_id:
            # SetupIntent flow start
            return {
                "status": "requires_payment_method",
                "client_secret": f"seti_mock_secret_{secrets.token_hex(12)}",
                "stripe_customer_id": stripe_customer_id
            }
        else:
            # Complete mock subscription creation
            now = datetime.now(timezone.utc)
            period_end = now + (timedelta(days=365) if req.billing_cadence == "annual" else timedelta(days=30))
            sub_id = f"sub_mock_{secrets.token_hex(8)}"

            membership = Membership(
                id=f"mem_{ulid.new()}",
                company_id=company_id,
                customer_id=req.customer_id,
                plan_id=req.plan_id,
                status="active",
                billing_cadence=req.billing_cadence,
                current_period_start=now,
                current_period_end=period_end,
                visits_used_this_period=0,
                visits_carried_over=0,
                enrolled_by=user_role,
                enrolled_at=now,
                stripe_subscription_id=sub_id,
                stripe_customer_id=stripe_customer_id,
                next_renewal_at=period_end
            )
            db.add(membership)
            db.commit()
            db.refresh(membership)
            return serialize_membership(db, membership)

    else:
        # Live Stripe Connect integration
        try:
            stripe.api_key = stripe_key
            if not stripe_customer_id:
                cust_res = stripe.Customer.create(
                    email=customer.email,
                    phone=customer.phone,
                    name=f"{customer.first_name} {customer.last_name}",
                    stripe_account=stripe_account_id
                )
                stripe_customer_id = cust_res.id

            if not req.payment_method_id:
                # Return SetupIntent secret for frontend confirmation
                setup_intent = stripe.SetupIntent.create(
                    customer=stripe_customer_id,
                    payment_method_types=["card"],
                    stripe_account=stripe_account_id
                )
                return {
                    "status": "requires_payment_method",
                    "client_secret": setup_intent.client_secret,
                    "stripe_customer_id": stripe_customer_id
                }
            else:
                # Attach payment method and set as customer default
                stripe.PaymentMethod.attach(
                    req.payment_method_id,
                    customer=stripe_customer_id,
                    stripe_account=stripe_account_id
                )
                stripe.Customer.modify(
                    stripe_customer_id,
                    invoice_settings={"default_payment_method": req.payment_method_id},
                    stripe_account=stripe_account_id
                )

                # Get plan price ID
                price_id = plan.stripe_monthly_price_id if req.billing_cadence == "monthly" else plan.stripe_annual_price_id
                if not price_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Plan does not have Stripe Price ID configured for {req.billing_cadence} cadence."
                    )

                # Create subscription
                subscription = stripe.Subscription.create(
                    customer=stripe_customer_id,
                    items=[{"price": price_id}],
                    default_payment_method=req.payment_method_id,
                    stripe_account=stripe_account_id
                )

                now = datetime.now(timezone.utc)
                period_end = now + (timedelta(days=365) if req.billing_cadence == "annual" else timedelta(days=30))

                membership = Membership(
                    id=f"mem_{ulid.new()}",
                    company_id=company_id,
                    customer_id=req.customer_id,
                    plan_id=req.plan_id,
                    status="active",
                    billing_cadence=req.billing_cadence,
                    current_period_start=now,
                    current_period_end=period_end,
                    visits_used_this_period=0,
                    visits_carried_over=0,
                    enrolled_by=user_role,
                    enrolled_at=now,
                    stripe_subscription_id=subscription.id,
                    stripe_customer_id=stripe_customer_id,
                    next_renewal_at=period_end
                )
                db.add(membership)
                db.commit()
                db.refresh(membership)
                return serialize_membership(db, membership)
        except Exception as e:
            logger.error(f"Stripe enrollment failed: {e}")
            raise HTTPException(status_code=400, detail=f"Stripe enrollment failed: {str(e)}")

@router.get("")
def list_memberships(
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "platform_admin"])
    
    mems = db.scalars(
        select(Membership)
        .order_by(Membership.enrolled_at.desc())
    ).all()
    
    return [serialize_membership(db, m) for m in mems]

@router.get("/{id}")
def get_membership_detail(
    id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    mem = db.scalar(select(Membership).where(Membership.id == id))
    if not mem:
        raise HTTPException(status_code=404, detail="Membership not found")
        
    return serialize_membership(db, mem)

@router.post("/{id}/cancel")
def cancel_membership(
    id: str,
    req: CancelRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    company_id = request.state.company_id
    user_id = request.state.user_id

    mem = db.scalar(select(Membership).where(Membership.id == id))
    if not mem:
        raise HTTPException(status_code=404, detail="Membership not found")

    company = db.scalar(select(Company).where(Company.id == company_id))
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    is_mock = (
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )

    if not is_mock and mem.stripe_subscription_id and not mem.stripe_subscription_id.startswith("sub_mock_"):
        try:
            stripe.api_key = stripe_key
            stripe.Subscription.cancel(
                mem.stripe_subscription_id,
                stripe_account=stripe_account_id
            )
        except Exception as e:
            logger.error(f"Failed to cancel Stripe subscription: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to cancel Stripe subscription: {str(e)}")

    now = datetime.now(timezone.utc)
    mem.status = "cancelled"
    mem.cancelled_at = now
    mem.cancellation_reason = req.cancellation_reason or "Cancelled by operator"
    mem.next_renewal_at = None
    mem.updated_at = now
    mem.updated_by = user_id

    db.commit()
    db.refresh(mem)
    return serialize_membership(db, mem)

@router.post("/{id}/pause")
def pause_membership(
    id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    company_id = request.state.company_id
    user_id = request.state.user_id

    mem = db.scalar(select(Membership).where(Membership.id == id))
    if not mem:
        raise HTTPException(status_code=404, detail="Membership not found")

    company = db.scalar(select(Company).where(Company.id == company_id))
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    is_mock = (
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )

    if not is_mock and mem.stripe_subscription_id and not mem.stripe_subscription_id.startswith("sub_mock_"):
        try:
            stripe.api_key = stripe_key
            stripe.Subscription.modify(
                mem.stripe_subscription_id,
                pause_collection={"behavior": "keep_as_draft"},
                stripe_account=stripe_account_id
            )
        except Exception as e:
            logger.error(f"Failed to pause Stripe subscription: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to pause Stripe subscription: {str(e)}")

    now = datetime.now(timezone.utc)
    mem.status = "paused"
    mem.updated_at = now
    mem.updated_by = user_id

    db.commit()
    db.refresh(mem)
    return serialize_membership(db, mem)

@router.post("/{id}/resume")
def resume_membership(
    id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    company_id = request.state.company_id
    user_id = request.state.user_id

    mem = db.scalar(select(Membership).where(Membership.id == id))
    if not mem:
        raise HTTPException(status_code=404, detail="Membership not found")

    company = db.scalar(select(Company).where(Company.id == company_id))
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    is_mock = (
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )

    if not is_mock and mem.stripe_subscription_id and not mem.stripe_subscription_id.startswith("sub_mock_"):
        try:
            stripe.api_key = stripe_key
            stripe.Subscription.modify(
                mem.stripe_subscription_id,
                pause_collection=None,
                stripe_account=stripe_account_id
            )
        except Exception as e:
            logger.error(f"Failed to resume Stripe subscription: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to resume Stripe subscription: {str(e)}")

    now = datetime.now(timezone.utc)
    mem.status = "active"
    mem.updated_at = now
    mem.updated_by = user_id

    db.commit()
    db.refresh(mem)
    return serialize_membership(db, mem)
