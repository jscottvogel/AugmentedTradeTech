import os
import logging
import secrets
import ulid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator, model_validator

import stripe

from apps.api.app.core.database import get_db
from apps.api.app.models.membership import MembershipPlan
from apps.api.app.models.company import Company

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/membership-plans", tags=["Membership Plans"])

# Pydantic Schemas
class MembershipPlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trade: str # hvac | garage_door | both
    monthly_price_cents: Optional[int] = None
    annual_price_cents: Optional[int] = None
    included_visits_count: int = 0
    visit_reset_period: str = "annual" # annual | monthly
    carryover_visits: bool = False
    labor_discount_pct: float = 0.0
    parts_discount_pct: float = 0.0
    priority_scheduling: bool = False
    loyalty_multiplier: float = 1.0
    sort_order: int = 0

    @model_validator(mode="after")
    def validate_prices(self):
        if self.monthly_price_cents is None and self.annual_price_cents is None:
            raise ValueError("At least one price (monthly or annual) must be set.")
        return self

    @field_validator("trade")
    def validate_trade(cls, v):
        if v not in ["hvac", "garage_door", "both"]:
            raise ValueError("trade must be one of: hvac, garage_door, both")
        return v

    @field_validator("visit_reset_period")
    def validate_visit_reset_period(cls, v):
        if v not in ["annual", "monthly"]:
            raise ValueError("visit_reset_period must be one of: annual, monthly")
        return v

class MembershipPlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trade: Optional[str] = None
    is_active: Optional[bool] = None
    monthly_price_cents: Optional[int] = None
    annual_price_cents: Optional[int] = None
    included_visits_count: Optional[int] = None
    visit_reset_period: Optional[str] = None
    carryover_visits: Optional[bool] = None
    labor_discount_pct: Optional[float] = None
    parts_discount_pct: Optional[float] = None
    priority_scheduling: Optional[bool] = None
    loyalty_multiplier: Optional[float] = None
    sort_order: Optional[int] = None

    @field_validator("trade")
    def validate_trade(cls, v):
        if v is not None and v not in ["hvac", "garage_door", "both"]:
            raise ValueError("trade must be one of: hvac, garage_door, both")
        return v

    @field_validator("visit_reset_period")
    def validate_visit_reset_period(cls, v):
        if v is not None and v not in ["annual", "monthly"]:
            raise ValueError("visit_reset_period must be one of: annual, monthly")
        return v

# Helper functions
def check_permission(request: Request, allowed_roles: List[str]):
    role = getattr(request.state, "role", None)
    if not role or role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. Required roles: {allowed_roles}"
        )

def serialize_plan(plan: MembershipPlan):
    return {
        "id": plan.id,
        "company_id": plan.company_id,
        "name": plan.name,
        "description": plan.description,
        "trade": plan.trade,
        "is_active": plan.is_active,
        "monthly_price_cents": plan.monthly_price_cents,
        "annual_price_cents": plan.annual_price_cents,
        "included_visits_count": plan.included_visits_count,
        "visit_reset_period": plan.visit_reset_period,
        "carryover_visits": plan.carryover_visits,
        "labor_discount_pct": float(plan.labor_discount_pct) if plan.labor_discount_pct is not None else 0.0,
        "parts_discount_pct": float(plan.parts_discount_pct) if plan.parts_discount_pct is not None else 0.0,
        "priority_scheduling": plan.priority_scheduling,
        "loyalty_multiplier": float(plan.loyalty_multiplier) if plan.loyalty_multiplier is not None else 1.0,
        "stripe_monthly_price_id": plan.stripe_monthly_price_id,
        "stripe_annual_price_id": plan.stripe_annual_price_id,
        "sort_order": plan.sort_order,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }

def create_stripe_price_for_plan(company: Company, plan_name: str, amount_cents: int, cadence: str) -> str:
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    is_mock = (
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )

    if is_mock:
        return f"price_mock_{cadence}_{secrets.token_hex(4)}"

    try:
        stripe.api_key = stripe_key
        price = stripe.Price.create(
            unit_amount=amount_cents,
            currency="usd",
            recurring={"interval": "month" if cadence == "monthly" else "year"},
            product_data={
                "name": f"{plan_name} ({cadence.capitalize()})"
            },
            stripe_account=stripe_account_id
        )
        return price.id
    except Exception as e:
        logger.error(f"Stripe Price creation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Stripe Price creation failed: {str(e)}"
        )

# Routes
@router.get("", response_model=List[dict])
def list_membership_plans(
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "platform_admin", "dispatcher", "tech"])
    
    plans = db.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.is_active == True)
        .order_by(MembershipPlan.sort_order.asc(), MembershipPlan.id.asc())
    ).all()
    
    return [serialize_plan(p) for p in plans]

@router.post("", status_code=201)
def create_membership_plan(
    req: MembershipPlanCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "platform_admin"])
    company_id = request.state.company_id
    user_id = request.state.user_id
    
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Generate Stripe price IDs if price is provided
    stripe_monthly_price_id = None
    if req.monthly_price_cents is not None:
        stripe_monthly_price_id = create_stripe_price_for_plan(company, req.name, req.monthly_price_cents, "monthly")

    stripe_annual_price_id = None
    if req.annual_price_cents is not None:
        stripe_annual_price_id = create_stripe_price_for_plan(company, req.name, req.annual_price_cents, "annual")

    plan = MembershipPlan(
        id=f"plan_{ulid.new()}",
        company_id=company_id,
        name=req.name,
        description=req.description,
        trade=req.trade,
        is_active=True,
        monthly_price_cents=req.monthly_price_cents,
        annual_price_cents=req.annual_price_cents,
        included_visits_count=req.included_visits_count,
        visit_reset_period=req.visit_reset_period,
        carryover_visits=req.carryover_visits,
        labor_discount_pct=req.labor_discount_pct,
        parts_discount_pct=req.parts_discount_pct,
        priority_scheduling=req.priority_scheduling,
        loyalty_multiplier=req.loyalty_multiplier,
        stripe_monthly_price_id=stripe_monthly_price_id,
        stripe_annual_price_id=stripe_annual_price_id,
        sort_order=req.sort_order,
        created_by=user_id,
        updated_by=user_id
    )
    
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return serialize_plan(plan)

@router.put("/{id}")
def update_membership_plan(
    id: str,
    req: MembershipPlanUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "platform_admin"])
    company_id = request.state.company_id
    user_id = request.state.user_id
    
    plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == id))
    if not plan:
        raise HTTPException(status_code=404, detail="Membership plan not found")
        
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Update plan fields
    updates = req.model_dump(exclude_unset=True)
    for field, val in updates.items():
        if field == "monthly_price_cents" and val != plan.monthly_price_cents:
            if val is not None:
                plan.stripe_monthly_price_id = create_stripe_price_for_plan(company, plan.name, val, "monthly")
            else:
                plan.stripe_monthly_price_id = None
            plan.monthly_price_cents = val
        elif field == "annual_price_cents" and val != plan.annual_price_cents:
            if val is not None:
                plan.stripe_annual_price_id = create_stripe_price_for_plan(company, plan.name, val, "annual")
            else:
                plan.stripe_annual_price_id = None
            plan.annual_price_cents = val
        else:
            setattr(plan, field, val)

    plan.updated_at = datetime.now(timezone.utc)
    plan.updated_by = user_id

    db.commit()
    db.refresh(plan)
    return serialize_plan(plan)

@router.delete("/{id}")
def delete_membership_plan(
    id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    check_permission(request, ["company_admin", "platform_admin"])
    user_id = request.state.user_id

    plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == id))
    if not plan:
        raise HTTPException(status_code=404, detail="Membership plan not found")

    plan.is_active = False
    plan.deleted_at = datetime.now(timezone.utc)
    plan.updated_at = datetime.now(timezone.utc)
    plan.updated_by = user_id

    db.commit()
    db.refresh(plan)
    return {"status": "success", "message": f"Membership plan {id} soft-deleted successfully."}
