from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from apps.api.app.core.database import get_db
from apps.api.app.models.user import User, TechProfile, AvailabilityStatusLog

router = APIRouter(prefix="/techs", tags=["techs"])

# Helper to serialize tech users
def serialize_tech(user: User) -> Dict[str, Any]:
    payload = {
        "id": user.id,
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "is_active": user.is_active,
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
            "last_heartbeat_at": user.tech_profile.last_heartbeat_at.isoformat() if user.tech_profile.last_heartbeat_at else None,
            "status_changed_at": user.tech_profile.status_changed_at.isoformat() if user.tech_profile.status_changed_at else None,
        }
    return payload


@router.get("")
def list_technicians(request: Request, db: Session = Depends(get_db)):
    """List all technicians with availability status (Protected, Admin/Dispatcher only)"""
    role = getattr(request.state, "role", None)
    if role not in ["company_admin", "dispatcher"]:
        raise HTTPException(status_code=403, detail="Only admins and dispatchers can view technician availability")

    company_id = getattr(request.state, "company_id", None)
    techs = db.scalars(
        select(User)
        .where(User.company_id == company_id)
        .where(User.role == "tech")
    ).all()
    
    return [serialize_tech(t) for t in techs]


@router.get("/{tech_id}/availability")
def get_tech_availability_history(tech_id: str, request: Request, db: Session = Depends(get_db)):
    """Get chronological availability history logs for a specific technician (Protected, Admin/Dispatcher only)"""
    role = getattr(request.state, "role", None)
    if role not in ["company_admin", "dispatcher"]:
        raise HTTPException(status_code=403, detail="Only admins and dispatchers can view availability logs")

    company_id = getattr(request.state, "company_id", None)
    
    # Verify the tech exists and belongs to the same company
    tech = db.scalar(
        select(User)
        .where(User.id == tech_id)
        .where(User.company_id == company_id)
        .where(User.role == "tech")
    )
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found or not in company")

    logs = db.scalars(
        select(AvailabilityStatusLog)
        .where(AvailabilityStatusLog.user_id == tech_id)
        .order_by(AvailabilityStatusLog.started_at.desc())
    ).all()

    return [
        {
            "id": log.id,
            "status": log.status,
            "started_at": log.started_at.isoformat(),
            "ended_at": log.ended_at.isoformat() if log.ended_at else None,
            "duration_seconds": int((log.ended_at - log.started_at).total_seconds()) if log.ended_at else None
        }
        for log in logs
    ]
