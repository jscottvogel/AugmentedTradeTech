import os
import secrets
import ulid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select, text

from apps.api.app.core.database import get_db
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.auth import MagicLinkToken
from apps.api.app.routers.auth import send_ses_email, hash_token, get_password_hash

router = APIRouter(prefix="/users", tags=["users"])

# Pydantic Request Schemas

class UserInviteRequest(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    role: str  # 'company_admin', 'dispatcher', 'tech'
    trades: Optional[List[str]] = None

class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    # Tech profile fields
    trades: Optional[List[str]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
    skills: Optional[List[str]] = None
    truck_id: Optional[str] = None
    license_number: Optional[str] = None
    hire_date: Optional[str] = None  # format YYYY-MM-DD

# Helper to serialize user + tech_profile
def serialize_user(user: User) -> Dict[str, Any]:
    payload = {
        "id": user.id,
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "company_id": user.company_id,
        "tech_profile": None,
    }
    if user.tech_profile:
        payload["tech_profile"] = {
            "id": user.tech_profile.id,
            "availability_status": user.tech_profile.availability_status,
            "trades": user.tech_profile.trades,
            "certifications": user.tech_profile.certifications,
            "skills": user.tech_profile.skills,
            "truck_id": user.tech_profile.truck_id,
            "license_number": user.tech_profile.license_number,
            "hire_date": user.tech_profile.hire_date.isoformat() if user.tech_profile.hire_date else None,
        }
    return payload

# Endpoints

@router.get("")
def list_users(request: Request, db: Session = Depends(get_db)):
    """List all users for the company (Protected, Admin-only)"""
    role = getattr(request.state, "role", None)
    if role != "company_admin":
        raise HTTPException(status_code=403, detail="Only company admins can view the team roster")

    company_id = getattr(request.state, "company_id", None)
    users = db.scalars(select(User).where(User.company_id == company_id)).all()
    return [serialize_user(u) for u in users]

@router.post("/invite")
def invite_user(req: UserInviteRequest, request: Request, db: Session = Depends(get_db)):
    """Invite a new technician or dispatcher by email (Protected, Admin-only)"""
    role = getattr(request.state, "role", None)
    if role != "company_admin":
        raise HTTPException(status_code=403, detail="Only company admins can invite team members")

    company_id = getattr(request.state, "company_id", None)

    # Validate invited role
    if req.role not in ["company_admin", "dispatcher", "tech"]:
        raise HTTPException(status_code=400, detail="Invalid team member role")

    # Check if email is already in use
    existing_user = db.scalar(select(User).where(User.email == req.email.lower()))
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered")

    # 1. Create inactive User record
    user_id = f"usr_{ulid.new()}"
    user = User(
        id=user_id,
        company_id=company_id,
        email=req.email.lower(),
        phone=req.phone,
        full_name="",  # to be completed on profile setup
        role=req.role,
        is_active=False,  # inactive until profile completed
    )
    db.add(user)

    # 2. Setup Tech Profile if role is tech
    if req.role == "tech":
        tech_prof = TechProfile(
            id=f"tp_{ulid.new()}",
            company_id=company_id,
            user_id=user_id,
            trades=req.trades or [],
            availability_status="offline",
        )
        db.add(tech_prof)

    # 3. Generate magic link token for invite
    raw_token = secrets.token_hex(32)
    token_hashed = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    magic_token = MagicLinkToken(
        id=f"token_{ulid.new()}",
        user_id=user_id,
        token_hash=token_hashed,
        expires_at=expires_at,
        created_by=getattr(request.state, "user_id", None),
        updated_by=getattr(request.state, "user_id", None),
    )
    db.add(magic_token)
    db.commit()

    # Send SES Invitation email
    send_ses_email(user.email, raw_token)

    return {
        "message": "Team member successfully invited",
        "user": serialize_user(user)
    }

@router.get("/{id}")
def get_user_profile(id: str, request: Request, db: Session = Depends(get_db)):
    """Get a team member profile details (Protected, Admin or Self)"""
    request_user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)

    if role != "company_admin" and request_user_id != id:
        raise HTTPException(status_code=403, detail="Unauthorized to view this profile")

    user = db.scalar(select(User).where(User.id == id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return serialize_user(user)

@router.put("/{id}")
def update_user_profile(id: str, req: UserUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Update a user's details / Profile completion flow (Protected, Admin or Self)"""
    request_user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)

    if role != "company_admin" and request_user_id != id:
        raise HTTPException(status_code=403, detail="Unauthorized to update this profile")

    user = db.scalar(select(User).where(User.id == id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update Core User Details
    if req.full_name is not None:
        user.full_name = req.full_name
    if req.phone is not None:
        user.phone = req.phone
    if req.password is not None:
        # Hashing password
        user.password_hash = get_password_hash(req.password)

    # Admin only modifications
    if role == "company_admin":
        if req.role is not None and req.role in ["company_admin", "dispatcher", "tech"]:
            user.role = req.role

    # Update Tech Profile
    is_tech = user.role == "tech"
    if is_tech:
        tech_prof = db.scalar(select(TechProfile).where(TechProfile.user_id == id))
        if not tech_prof:
            tech_prof = TechProfile(
                id=f"tp_{ulid.new()}",
                company_id=user.company_id,
                user_id=id,
                availability_status="offline",
            )
            db.add(tech_prof)

        if req.trades is not None:
            tech_prof.trades = req.trades
        if req.certifications is not None:
            tech_prof.certifications = req.certifications
        if req.skills is not None:
            tech_prof.skills = req.skills
        if req.truck_id is not None:
            tech_prof.truck_id = req.truck_id
        if req.license_number is not None:
            tech_prof.license_number = req.license_number
        if req.hire_date is not None:
            try:
                tech_prof.hire_date = datetime.strptime(req.hire_date, "%Y-%m-%d").date() if req.hire_date else None
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid hire_date, must be YYYY-MM-DD")

    # Profile Completion Logic: Set is_active = True if first login completion criteria met
    if not user.is_active:
        # Require full_name for all roles
        if user.full_name and len(user.full_name.strip()) > 0:
            # Dispatchers / Admins also require password
            if user.role in ["company_admin", "dispatcher"]:
                if user.password_hash:
                    user.is_active = True
            else:
                # Techs do not require passwords
                user.is_active = True

    db.commit()
    return serialize_user(user)

@router.post("/{id}/deactivate")
def deactivate_user(id: str, request: Request, db: Session = Depends(get_db)):
    """Soft-deactivate a team member (Protected, Admin-only)"""
    role = getattr(request.state, "role", None)
    if role != "company_admin":
        raise HTTPException(status_code=403, detail="Only company admins can deactivate team members")

    request_user_id = getattr(request.state, "user_id", None)
    if request_user_id == id:
        raise HTTPException(status_code=400, detail="Admins cannot deactivate themselves")

    user = db.scalar(select(User).where(User.id == id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.commit()

    return {"message": "User soft-deactivated successfully", "user": serialize_user(user)}

@router.post("/{id}/resend-invite")
def resend_invite(id: str, request: Request, db: Session = Depends(get_db)):
    """Resend magic link invitation (Protected, Admin-only)"""
    role = getattr(request.state, "role", None)
    if role != "company_admin":
        raise HTTPException(status_code=403, detail="Only company admins can manage invitations")

    user = db.scalar(select(User).where(User.id == id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active:
        raise HTTPException(status_code=400, detail="User is already active")

    # Resend token
    raw_token = secrets.token_hex(32)
    token_hashed = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    magic_token = MagicLinkToken(
        id=f"token_{ulid.new()}",
        user_id=id,
        token_hash=token_hashed,
        expires_at=expires_at,
        created_by=getattr(request.state, "user_id", None),
        updated_by=getattr(request.state, "user_id", None),
    )
    db.add(magic_token)
    db.commit()

    send_ses_email(user.email, raw_token)

    return {"message": "Invitation resent successfully"}
