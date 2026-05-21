import os
import boto3
import ulid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
import zoneinfo
from datetime import timedelta

from apps.api.app.core.database import get_db
from apps.api.app.models.user import User, TechProfile, AvailabilityStatusLog
from apps.api.app.models.company import Company
from apps.api.app.models.job import Job, JobTechnician
from apps.api.app.models.customer import Customer
from apps.api.app.models.invoice import Invoice

router = APIRouter(prefix="/me", tags=["me"])

# Pydantic Schemas
class MeProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    # Tech profile fields
    trades: Optional[List[str]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
    skills: Optional[List[str]] = None

class MeAvailabilityUpdateRequest(BaseModel):
    status: str # available | on_job | driving | break | off_duty | offline

# Helper to serialize user + tech_profile
def serialize_me_user(user: User) -> Dict[str, Any]:
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
            "last_heartbeat_at": user.tech_profile.last_heartbeat_at.isoformat() if user.tech_profile.last_heartbeat_at else None,
            "status_changed_at": user.tech_profile.status_changed_at.isoformat() if user.tech_profile.status_changed_at else None,
        }
    return payload


@router.get("/profile")
def get_my_profile(request: Request, db: Session = Depends(get_db)):
    """Get the profile of the current authenticated user"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return serialize_me_user(user)


@router.put("/profile")
def update_my_profile(req: MeProfileUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Update current user's profile and auto-activate technician if completing setup"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.full_name is not None:
        user.full_name = req.full_name
    if req.phone is not None:
        user.phone = req.phone
    if req.avatar_url is not None:
        user.avatar_url = req.avatar_url

    # Handle technician specific fields
    if user.role == "tech":
        # Create tech profile if not exists
        if not user.tech_profile:
            tech_prof_id = f"tprf_{ulid.new()}"
            user.tech_profile = TechProfile(
                id=tech_prof_id,
                user_id=user.id,
                company_id=user.company_id,
                availability_status="offline"
            )
            db.add(user.tech_profile)

        if req.trades is not None:
            user.tech_profile.trades = req.trades
        if req.certifications is not None:
            user.tech_profile.certifications = req.certifications
        if req.skills is not None:
            user.tech_profile.skills = req.skills

        # Auto-activate tech: if they were inactive and have now completed the required fields
        if not user.is_active:
            # Check completeness: photo, trades, certifications, and skills must be set
            has_photo = bool(user.avatar_url or req.avatar_url)
            has_trades = bool(user.tech_profile.trades)
            has_certifications = bool(user.tech_profile.certifications)
            has_skills = bool(user.tech_profile.skills)
            
            if has_photo and has_trades and has_certifications and has_skills:
                user.is_active = True

    db.commit()
    db.refresh(user)
    return serialize_me_user(user)


@router.put("/availability")
def update_my_availability(req: MeAvailabilityUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Update technician's availability status and transition history logs"""
    user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)
    company_id = getattr(request.state, "company_id", None)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if role != "tech":
        raise HTTPException(status_code=400, detail="Only technicians can update availability status")

    valid_statuses = ["available", "on_job", "driving", "break", "off_duty", "offline"]
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid availability status. Must be one of {valid_statuses}")

    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.tech_profile:
        tech_prof_id = f"tprf_{ulid.new()}"
        user.tech_profile = TechProfile(
            id=tech_prof_id,
            user_id=user.id,
            company_id=user.company_id,
            availability_status="offline"
        )
        db.add(user.tech_profile)

    current_time = datetime.now(timezone.utc)
    old_status = user.tech_profile.availability_status

    if old_status != req.status:
        # Update tech profile status
        user.tech_profile.availability_status = req.status
        user.tech_profile.status_changed_at = current_time

        # End previous status log if exists
        prev_log = db.scalar(
            select(AvailabilityStatusLog)
            .where(AvailabilityStatusLog.user_id == user_id)
            .where(AvailabilityStatusLog.ended_at.is_(None))
        )
        if prev_log:
            prev_log.ended_at = current_time

        # Create new status log
        new_log = AvailabilityStatusLog(
            id=f"asl_{ulid.new()}",
            user_id=user_id,
            company_id=company_id,
            status=req.status,
            started_at=current_time
        )
        db.add(new_log)
        db.commit()
        db.refresh(user)

    return serialize_me_user(user)


@router.post("/profile/photo")
def upload_profile_photo(file: UploadFile = File(...), request: Request = None, db: Session = Depends(get_db)):
    """Upload technician profile photo to S3 or mock destination and return URL"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Generate unique key for file
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    file_key = f"profile-photos/{user_id}/{ulid.new()}{file_ext}"

    # Try SST linked Resource bucket
    bucket_name = None
    media_domain = None
    try:
        from sst import Resource
        if hasattr(Resource, "MediaBucket"):
            bucket_name = Resource.MediaBucket.name
            # If domain is not resolved, fallback
            media_domain = getattr(Resource.MediaBucket, "domain", None)
    except Exception:
        pass

    if bucket_name:
        try:
            s3 = boto3.client("s3")
            s3.upload_fileobj(
                file.file,
                bucket_name,
                file_key,
                ExtraArgs={"ContentType": file.content_type or "image/jpeg"}
            )
            
            # Formulate upload url
            if media_domain:
                upload_url = f"https://{media_domain}/{file_key}"
            else:
                upload_url = f"/media/{file_key}"
                
            return {"avatar_url": upload_url}
        except Exception as e:
            # Fail silently to mock in case credentials aren't configured
            pass

    # Mock Upload Fallback
    mock_url = f"https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=256&mock={ulid.new()}"
    return {"avatar_url": mock_url}


@router.post("/heartbeat")
def heartbeat_ping(request: Request, db: Session = Depends(get_db)):
    """Heartbeat signal sent by active tech frontend to keep status online"""
    user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if role != "tech":
        raise HTTPException(status_code=400, detail="Only technicians emit heartbeat pings")

    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.tech_profile:
        tech_prof_id = f"tprf_{ulid.new()}"
        user.tech_profile = TechProfile(
            id=tech_prof_id,
            user_id=user.id,
            company_id=user.company_id,
            availability_status="offline"
        )
        db.add(user.tech_profile)

    user.tech_profile.last_heartbeat_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


@router.get("/jobs/today")
def get_my_jobs_today(request: Request, db: Session = Depends(get_db)):
    """Get assigned jobs for today in the company's local timezone"""
    user_id = getattr(request.state, "user_id", None)
    company_id = getattr(request.state, "company_id", None)
    if not user_id or not company_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get company timezone
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    tz_str = company.timezone or "America/Chicago"
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("America/Chicago")

    # Calculate local today bounds
    now_local = datetime.now(tz)
    today_start = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=tz)
    today_end = datetime(now_local.year, now_local.month, now_local.day, 23, 59, 59, 999999, tzinfo=tz)

    # Query lead/assigned jobs for today
    stmt = (
        select(Job, Customer)
        .join(JobTechnician, JobTechnician.job_id == Job.id)
        .join(Customer, Customer.id == Job.customer_id)
        .where(JobTechnician.tech_id == user_id)
        .where(Job.scheduled_start >= today_start)
        .where(Job.scheduled_start <= today_end)
        .order_by(Job.scheduled_start.asc())
    )
    results = db.execute(stmt).all()

    payload = []
    for job, customer in results:
        payload.append({
            "id": job.id,
            "job_number": job.job_number,
            "trade": job.trade,
            "job_type": job.job_type,
            "priority": job.priority,
            "status": job.status,
            "reported_problem": job.reported_problem,
            "dispatcher_notes": job.dispatcher_notes,
            "scheduled_start": job.scheduled_start.isoformat() if job.scheduled_start else None,
            "scheduled_end": job.scheduled_end.isoformat() if job.scheduled_end else None,
            "customer": {
                "id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "address_line1": customer.address_line1,
                "address_line2": customer.address_line2,
                "city": customer.city,
                "state": customer.state,
                "zip": customer.zip,
            }
        })
    return payload


@router.get("/jobs/upcoming")
def get_my_jobs_upcoming(request: Request, db: Session = Depends(get_db)):
    """Get assigned jobs for the next 7 days (excluding today) in the company's local timezone"""
    user_id = getattr(request.state, "user_id", None)
    company_id = getattr(request.state, "company_id", None)
    if not user_id or not company_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get company timezone
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    tz_str = company.timezone or "America/Chicago"
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("America/Chicago")

    # Bounds: tomorrow_start to 7 days from now
    now_local = datetime.now(tz)
    today_end = datetime(now_local.year, now_local.month, now_local.day, 23, 59, 59, 999999, tzinfo=tz)
    tomorrow_start = today_end + timedelta(microseconds=1)
    seven_days_end = today_end + timedelta(days=7)

    stmt = (
        select(Job, Customer)
        .join(JobTechnician, JobTechnician.job_id == Job.id)
        .join(Customer, Customer.id == Job.customer_id)
        .where(JobTechnician.tech_id == user_id)
        .where(Job.scheduled_start >= tomorrow_start)
        .where(Job.scheduled_start <= seven_days_end)
        .order_by(Job.scheduled_start.asc())
    )
    results = db.execute(stmt).all()

    payload = []
    for job, customer in results:
        payload.append({
            "id": job.id,
            "job_number": job.job_number,
            "trade": job.trade,
            "job_type": job.job_type,
            "priority": job.priority,
            "status": job.status,
            "reported_problem": job.reported_problem,
            "dispatcher_notes": job.dispatcher_notes,
            "scheduled_start": job.scheduled_start.isoformat() if job.scheduled_start else None,
            "scheduled_end": job.scheduled_end.isoformat() if job.scheduled_end else None,
            "customer": {
                "id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "address_line1": customer.address_line1,
                "address_line2": customer.address_line2,
                "city": customer.city,
                "state": customer.state,
                "zip": customer.zip,
            }
        })
    return payload


@router.get("/stats/today")
def get_my_stats_today(request: Request, db: Session = Depends(get_db)):
    """Get technician stats for today: jobs completed, earnings today (if enabled)"""
    user_id = getattr(request.state, "user_id", None)
    company_id = getattr(request.state, "company_id", None)
    role = getattr(request.state, "role", None)
    if not user_id or not company_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if role != "tech":
        raise HTTPException(status_code=400, detail="Only technicians have personal stats dashboards")

    # Get company timezone
    company = db.scalar(select(Company).where(Company.id == company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    tz_str = company.timezone or "America/Chicago"
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("America/Chicago")

    # Bounds for today
    now_local = datetime.now(tz)
    today_start = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=tz)
    today_end = datetime(now_local.year, now_local.month, now_local.day, 23, 59, 59, 999999, tzinfo=tz)

    # Query completed jobs today for this tech
    stmt = (
        select(Job)
        .join(JobTechnician, JobTechnician.job_id == Job.id)
        .where(JobTechnician.tech_id == user_id)
        .where(Job.status == "completed")
        .where(Job.completed_at >= today_start)
        .where(Job.completed_at <= today_end)
    )
    completed_jobs = db.scalars(stmt).all()

    # Sum total cents from invoices if enabled
    show_earnings = company.workflow_config.get("show_tech_earnings", True) if company.workflow_config else True
    earnings_today = 0
    if show_earnings:
        for job in completed_jobs:
            invoice = db.scalar(select(Invoice).where(Invoice.job_id == job.id))
            if invoice:
                earnings_today += invoice.total_cents

    return {
        "jobs_completed": len(completed_jobs),
        "earnings_today": earnings_today if show_earnings else None,
        "earnings_enabled": show_earnings
    }

