import os
import re
import secrets
import ulid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select

from apps.api.app.core.database import get_db
from apps.api.app.models.company import Company
from apps.api.app.models.user import User
from apps.api.app.models.auth import RefreshToken
from apps.api.app.core.workflows import DEFAULT_WORKFLOW_CONFIG
import copy
from apps.api.app.routers.auth import (
    get_password_hash,
    create_access_token,
    hash_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Helper to slugify company name
def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text

# Pydantic Schemas
class CompanySignupRequest(BaseModel):
    company_name: str
    owner_name: str
    email: EmailStr
    password: str

class ProfileUpdateRequest(BaseModel):
    trades: List[str]
    service_area_zips: List[str]
    business_hours: Dict[str, Any]
    logo_url: Optional[str] = None

class PlanSelectionRequest(BaseModel):
    plan: str

class QuickBooksConnectRequest(BaseModel):
    connect: bool

class TechInviteRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

# Endpoints

@router.get("/{company_id}")
def get_onboarding_state(company_id: str, request: Request, db: Session = Depends(get_db)):
    """Retrieve current onboarding state for a company (Protected)"""
    user_state = getattr(request.state, "user", None)
    if not user_state or user_state.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "onboarding_step": company.onboarding_step,
        "trades": company.trades,
        "service_area_zips": company.service_area_zips,
        "business_hours": company.business_hours,
        "logo_url": company.logo_url,
        "stripe_account_id": company.stripe_account_id,
        "qbo_realm_id": company.qbo_realm_id,
    }

@router.post("/company")
def signup_company(req: CompanySignupRequest, response: Response, db: Session = Depends(get_db)):
    """Step 1: Create Company + Admin User (Public)"""
    # Check if user already exists
    existing_user = db.scalar(select(User).where(User.email == req.email.lower()))
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered")

    # Generate unique slug
    base_slug = slugify(req.company_name) or "company"
    slug = base_slug
    counter = 1
    while db.scalar(select(Company).where(Company.slug == slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1

    # 1. Create Company
    company_id = f"comp_{ulid.new()}"
    company = Company(
        id=company_id,
        name=req.company_name,
        slug=slug,
        onboarding_step=2,
        workflow_config=copy.deepcopy(DEFAULT_WORKFLOW_CONFIG)
    )
    db.add(company)

    # 2. Create Owner User
    user_id = f"usr_{ulid.new()}"
    user = User(
        id=user_id,
        company_id=company_id,
        email=req.email.lower(),
        full_name=req.owner_name,
        password_hash=get_password_hash(req.password),
        role="company_admin",
        is_active=True,
    )
    db.add(user)
    db.commit()

    # 3. Log user in immediately (Generate JWT & Refresh tokens)
    access_token = create_access_token(user.id, company.id, user.role, user.email, user.is_active)
    
    raw_refresh = secrets.token_hex(32)
    refresh_hashed = hash_token(raw_refresh)
    refresh_expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hashed,
        expires_at=refresh_expire,
        created_by=user.id,
        updated_by=user.id
    )
    db.add(refresh_token_record)
    db.commit()

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        expires=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        secure=True,
        samesite="lax",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name,
            "company_id": company.id,
        },
        "company": {
            "id": company.id,
            "name": company.name,
            "slug": company.slug,
            "onboarding_step": company.onboarding_step,
        }
    }

@router.put("/{company_id}/profile")
def update_profile(company_id: str, req: ProfileUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Step 2: Business Profile update (Protected)"""
    user_state = getattr(request.state, "user", None)
    if not user_state or user_state.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Unauthorized to modify this company")

    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.trades = req.trades
    company.service_area_zips = req.service_area_zips
    company.business_hours = req.business_hours
    if req.logo_url:
        company.logo_url = req.logo_url
    
    # Progress step if current step is 2
    if company.onboarding_step == 2:
        company.onboarding_step = 3

    db.commit()
    return {"message": "Profile updated", "onboarding_step": company.onboarding_step}

@router.put("/{company_id}/plan")
def select_plan(company_id: str, req: PlanSelectionRequest, request: Request, db: Session = Depends(get_db)):
    """Step 3: Plan selection (Protected)"""
    user_state = getattr(request.state, "user", None)
    if not user_state or user_state.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Unauthorized to modify this company")

    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Save plan selection
    company.subscription_status = req.plan.lower()
    
    # Progress step if current step is 3
    if company.onboarding_step == 3:
        company.onboarding_step = 4

    db.commit()
    return {"message": "Plan selected", "onboarding_step": company.onboarding_step}

@router.post("/{company_id}/stripe")
def initiate_stripe(company_id: str, request: Request, db: Session = Depends(get_db)):
    """Step 4: Initiate Stripe Connect OAuth (Protected)"""
    user_state = getattr(request.state, "user", None)
    if not user_state or user_state.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Generate mock callback URL
    api_url = os.getenv("API_URL", "http://localhost:8000")
    redirect_uri = f"{api_url}/onboarding/{company_id}/stripe/callback?code=mock_stripe_code&state=mock_state"

    return {"url": redirect_uri}

@router.get("/{company_id}/stripe/callback")
def stripe_callback(company_id: str, code: str, state: str, db: Session = Depends(get_db)):
    """Handle Stripe OAuth callback redirect (Public callback)"""
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Complete step 4 by seeding mock stripe account
    company.stripe_account_id = f"acct_mock_{secrets.token_hex(8)}"
    if company.onboarding_step == 4:
        company.onboarding_step = 5

    db.commit()

    # Redirect user back to Next.js frontend onboarding page
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}/onboarding")

@router.post("/{company_id}/quickbooks")
def connect_quickbooks(company_id: str, req: QuickBooksConnectRequest, request: Request, db: Session = Depends(get_db)):
    """Step 5: Connect QuickBooks or Skip (Protected)"""
    user_state = getattr(request.state, "user", None)
    if not user_state or user_state.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if req.connect:
        # Seed mock QBO credentials
        company.qbo_realm_id = f"realm_{secrets.token_hex(4)}"
        company.qbo_access_token = f"access_{secrets.token_hex(16)}"
        company.qbo_refresh_token = f"refresh_{secrets.token_hex(16)}"
        company.qbo_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    # Progress step if current step is 5
    if company.onboarding_step == 5:
        company.onboarding_step = 6

    db.commit()
    return {"message": "QuickBooks state updated", "onboarding_step": company.onboarding_step}

@router.post("/{company_id}/invite-tech")
def invite_technician(company_id: str, req: TechInviteRequest, request: Request, db: Session = Depends(get_db)):
    """Step 6: Invite first technician (Protected)"""
    user_state = getattr(request.state, "user", None)
    if not user_state or user_state.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Create technician user in database if email/phone provided
    if req.email:
        # Check if already registered
        existing_user = db.scalar(select(User).where(User.email == req.email.lower()))
        if not existing_user:
            tech_id = f"usr_{ulid.new()}"
            tech = User(
                id=tech_id,
                company_id=company_id,
                email=req.email.lower(),
                phone=req.phone,
                full_name="Technician",
                role="tech",
                is_active=True
            )
            db.add(tech)
            db.commit()
            print(f"[ONBOARDING TECH INVITE] Sent technician invite to {req.email}")

    # Progress step if current step is 6
    if company.onboarding_step == 6:
        company.onboarding_step = 7

    db.commit()
    return {"message": "Technician invited", "onboarding_step": company.onboarding_step}

@router.put("/{company_id}/complete")
def complete_onboarding(company_id: str, request: Request, db: Session = Depends(get_db)):
    """Step 8: Complete onboarding (Protected)"""
    user_state = getattr(request.state, "user", None)
    if not user_state or user_state.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Mark as completely finished
    company.onboarding_step = 8
    db.commit()

    return {"message": "Onboarding completed successfully", "onboarding_step": company.onboarding_step}
