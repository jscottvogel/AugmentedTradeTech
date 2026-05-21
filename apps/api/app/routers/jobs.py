import os
import logging
import zoneinfo
import ulid
import boto3
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, update, and_, text

from apps.api.app.core.database import get_db
from apps.api.app.models.job import Job, JobTechnician, JobPhoto, JobNote, JobStatusHistory, JobPart
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer
from apps.api.app.models.membership import Membership, MembershipPlan
from apps.api.app.models.company import Company
from apps.api.app.models.user import User, TechProfile, AvailabilityStatusLog
from apps.api.app.models.ai import AIRequest
from apps.api.app.core.workflows import DEFAULT_WORKFLOW_CONFIG
import copy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

# --- Request Schemas ---

class PresignRequest(BaseModel):
    photo_type: str = "general"
    client_filename: Optional[str] = None

class JobCreateRequest(BaseModel):
    customer_id: str
    equipment_id: Optional[str] = None
    trade: str  # hvac | garage_door
    job_type: str  # service | maintenance | install | warranty | followup
    priority: Optional[str] = "routine"  # routine | urgent | emergency
    status: Optional[str] = "scheduled"
    reported_problem: Optional[str] = None
    dispatcher_notes: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    tech_id: Optional[str] = None  # Immediate assignment

class JobUpdateRequest(BaseModel):
    trade: Optional[str] = None
    job_type: Optional[str] = None
    priority: Optional[str] = None
    reported_problem: Optional[str] = None
    dispatcher_notes: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    status: Optional[str] = None

class JobStatusTransitionRequest(BaseModel):
    status: str
    note: Optional[str] = None

class JobAssignRequest(BaseModel):
    tech_id: str

class JobPartRequest(BaseModel):
    name: str
    quantity: Optional[int] = 1
    price_cents: Optional[int] = 0
    serial_number: Optional[str] = None

class JobNoteRequest(BaseModel):
    body: str
    note_type: Optional[str] = "general"
    is_internal: Optional[bool] = True

class WorkflowStepUpdate(BaseModel):
    inputs: Dict[str, Any]
    skipped: Optional[bool] = False
    idempotency_key: str

# --- Helpers ---

VALID_TRANSITIONS = {
    "scheduled": ["confirmed", "follow_up_required", "cancelled"],
    "confirmed": ["en_route", "follow_up_required", "cancelled"],
    "en_route": ["on_site", "follow_up_required", "cancelled"],
    "on_site": ["in_progress", "follow_up_required", "cancelled"],
    "in_progress": ["parts_needed", "paused", "completed", "follow_up_required", "cancelled"],
    "parts_needed": ["in_progress", "follow_up_required", "cancelled"],
    "paused": ["in_progress", "follow_up_required", "cancelled"],
    "completed": ["invoiced", "follow_up_required", "cancelled"],
    "invoiced": ["paid", "follow_up_required", "cancelled"],
    "paid": ["follow_up_required", "cancelled"],
    "follow_up_required": [
        "scheduled", "confirmed", "en_route", "on_site", "in_progress",
        "parts_needed", "paused", "completed", "invoiced", "paid", "cancelled"
    ],
    "cancelled": [
        "scheduled", "confirmed", "en_route", "on_site", "in_progress",
        "parts_needed", "paused", "completed", "invoiced", "paid", "follow_up_required"
    ],
}

def check_permission(request: Request, allowed_roles: List[str]):
    role = getattr(request.state, "role", None)
    if not role or role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. Required roles: {allowed_roles}"
        )

def publish_sns_notification(customer_phone: str | None, message: str):
    if not customer_phone:
        logger.warning("No customer phone number available for SNS notification")
        return
    try:
        sns = boto3.client("sns", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sns.publish(
            PhoneNumber=customer_phone,
            Message=message
        )
        logger.info(f"Published SNS message to {customer_phone}: '{message}'")
    except Exception as e:
        logger.warning(f"Skipped SNS notification: {e} (AWS credentials likely not set up locally)")

def update_tech_availability(db: Session, company_id: str, tech_id: str, new_availability: str):
    tech = db.scalar(select(User).where(User.id == tech_id))
    if not tech:
        return
    
    if not tech.tech_profile:
        tech.tech_profile = TechProfile(
            id=f"tprf_{ulid.new()}",
            user_id=tech.id,
            company_id=company_id,
            availability_status="offline"
        )
        db.add(tech.tech_profile)
        db.flush()

    current_time = datetime.now(timezone.utc)
    old_status = tech.tech_profile.availability_status

    if old_status != new_availability:
        tech.tech_profile.availability_status = new_availability
        tech.tech_profile.status_changed_at = current_time

        # Close active log
        prev_log = db.scalar(
            select(AvailabilityStatusLog)
            .where(AvailabilityStatusLog.user_id == tech_id)
            .where(AvailabilityStatusLog.ended_at.is_(None))
        )
        if prev_log:
            prev_log.ended_at = current_time

        # Create new log
        new_log = AvailabilityStatusLog(
            id=f"asl_{ulid.new()}",
            user_id=tech_id,
            company_id=company_id,
            status=new_availability,
            started_at=current_time
        )
        db.add(new_log)
        db.flush()

def serialize_job(job: Job) -> Dict[str, Any]:
    payload = {
        "id": job.id,
        "company_id": job.company_id,
        "job_number": job.job_number,
        "trade": job.trade,
        "job_type": job.job_type,
        "priority": job.priority,
        "status": job.status,
        "reported_problem": job.reported_problem,
        "dispatcher_notes": job.dispatcher_notes,
        "scheduled_start": job.scheduled_start.isoformat() if job.scheduled_start else None,
        "scheduled_end": job.scheduled_end.isoformat() if job.scheduled_end else None,
        "arrived_at": job.arrived_at.isoformat() if job.arrived_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "is_included_visit": job.is_included_visit,
        "source": job.source,
        "created_at": job.created_at.isoformat(),
        "customer": None,
        "equipment": None,
        "technicians": [],
        "photos": [],
        "notes": [],
        "parts": [],
        "status_history": [],
        "inspection_data": job.inspection_data or {},
        "ai_diagnosis": job.ai_diagnosis
    }
    
    if job.customer:
        payload["customer"] = {
            "id": job.customer.id,
            "first_name": job.customer.first_name,
            "last_name": job.customer.last_name,
            "email": job.customer.email,
            "phone": job.customer.phone,
            "address_line1": job.customer.address_line1,
            "address_line2": job.customer.address_line2,
            "city": job.customer.city,
            "state": job.customer.state,
            "zip": job.customer.zip,
        }
    
    if job.equipment:
        payload["equipment"] = {
            "id": job.equipment.id,
            "name": job.equipment.equipment_type,
            "make": job.equipment.make,
            "model": job.equipment.model,
            "serial_number": job.equipment.serial_number,
            "location": job.equipment.location_notes,
        }

    for jt in job.technicians:
        payload["technicians"].append({
            "id": jt.id,
            "tech_id": jt.tech_id,
            "is_lead": jt.is_lead,
            "full_name": jt.job.customer.first_name if not jt.job else "" # Fallback
        })
        # Let's enrich the tech's actual full name if we can load it.
        # But wait! We will handle full name resolution inline during details loading.

    cdn_domain = os.getenv("CDN_DOMAIN")
    if not cdn_domain:
        try:
            from sst import Resource
            if hasattr(Resource, "MediaBucket"):
                cdn_domain = getattr(Resource.MediaBucket, "domain", None)
        except Exception:
            pass
    if not cdn_domain:
        cdn_domain = "media.augmentedtradetech.com"

    for jp in job.photos:
        if jp.deleted_at is not None:
            continue
        # Construct CDN URL at read time: {cdn_domain}/{s3_key}
        final_cdn_url = f"https://{cdn_domain}/{jp.s3_key}" if jp.s3_key else jp.cdn_url
        payload["photos"].append({
            "id": jp.id,
            "photo_type": jp.photo_type,
            "cdn_url": final_cdn_url,
            "caption": jp.caption,
            "taken_at": jp.taken_at.isoformat() if jp.taken_at else None
        })

    for jn in job.notes:
        payload["notes"].append({
            "id": jn.id,
            "author_id": jn.author_id,
            "note_type": jn.note_type,
            "body": jn.body,
            "is_internal": jn.is_internal,
            "created_at": jn.created_at.isoformat()
        })

    for part in job.parts:
        payload["parts"].append({
            "id": part.id,
            "name": part.name,
            "quantity": part.quantity,
            "price_cents": part.price_cents,
            "serial_number": part.serial_number,
            "created_at": part.created_at.isoformat()
        })

    for sh in job.status_history:
        payload["status_history"].append({
            "id": sh.id,
            "from_status": sh.from_status,
            "to_status": sh.to_status,
            "changed_by": sh.changed_by,
            "changed_at": sh.changed_at.isoformat(),
            "note": sh.note
        })
        
    return payload

# --- Endpoints ---

@router.post("", status_code=status.HTTP_201_CREATED)
def create_job(req: JobCreateRequest, request: Request, db: Session = Depends(get_db)):
    """Create a new job and generate sequential job number (dispatcher/admin)"""
    check_permission(request, ["company_admin", "dispatcher"])
    company_id = request.state.company_id
    user_id = request.state.user_id

    job_id = f"job_{ulid.new()}"
    job = Job(
        id=job_id,
        company_id=company_id,
        customer_id=req.customer_id,
        equipment_id=req.equipment_id,
        job_number="PENDING",
        trade=req.trade,
        job_type=req.job_type,
        priority=req.priority,
        status=req.status or "scheduled",
        reported_problem=req.reported_problem,
        dispatcher_notes=req.dispatcher_notes,
        scheduled_start=req.scheduled_start,
        scheduled_end=req.scheduled_end,
        created_by=user_id,
        updated_by=user_id
    )
    db.add(job)
    db.flush()

    # Create initial status history entry
    hist = JobStatusHistory(
        id=f"jsh_{ulid.new()}",
        company_id=company_id,
        job_id=job_id,
        from_status=None,
        to_status=job.status,
        changed_by=user_id,
        note="Initial job creation"
    )
    db.add(hist)

    # Assign technician if specified
    if req.tech_id:
        jt_id = f"jt_{ulid.new()}"
        job_tech = JobTechnician(
            id=jt_id,
            company_id=company_id,
            job_id=job_id,
            tech_id=req.tech_id,
            is_lead=True,
            created_by=user_id
        )
        db.add(job_tech)

    db.commit()
    db.refresh(job)
    return serialize_job(job)


@router.get("")
def list_jobs(
    request: Request,
    status: Optional[str] = None,
    trade: Optional[str] = None,
    tech_id: Optional[str] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """List jobs filtered by status, date bounds, tech, trade (RLS scoped)"""
    company_id = request.state.company_id
    role = request.state.role
    user_id = request.state.user_id

    stmt = select(Job).where(Job.deleted_at.is_(None))

    if status:
        stmt = stmt.where(Job.status == status)
    if trade:
        stmt = stmt.where(Job.trade == trade)
    if date_start:
        stmt = stmt.where(Job.scheduled_start >= date_start)
    if date_end:
        stmt = stmt.where(Job.scheduled_start <= date_end)

    if tech_id:
        stmt = stmt.join(JobTechnician, JobTechnician.job_id == Job.id).where(JobTechnician.tech_id == tech_id)
    elif role == "tech":
        # Technicians can only see jobs they are assigned to
        stmt = stmt.join(JobTechnician, JobTechnician.job_id == Job.id).where(JobTechnician.tech_id == user_id)

    stmt = stmt.order_by(Job.scheduled_start.asc().nulls_last())
    jobs = db.scalars(stmt).all()
    return [serialize_job(j) for j in jobs]


@router.get("/{id}")
def get_job_detail(id: str, request: Request, db: Session = Depends(get_db)):
    """Get full job details including sub-resources"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(
        select(Job)
        .where(Job.id == id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If technician, verify they are assigned to this job
    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied. You are not assigned to this job.")

    payload = serialize_job(job)

    # Enrich tech full names
    tech_ids = [t["tech_id"] for t in payload["technicians"]]
    if tech_ids:
        users = db.scalars(select(User).where(User.id.in_(tech_ids))).all()
        user_map = {u.id: u.full_name for u in users}
        for t in payload["technicians"]:
            t["full_name"] = user_map.get(t["tech_id"], "Unknown Technician")

    # Enrich history changer names
    changer_ids = [sh["changed_by"] for sh in payload["status_history"]]
    if changer_ids:
        changers = db.scalars(select(User).where(User.id.in_(changer_ids))).all()
        changer_map = {u.id: u.full_name for u in changers}
        for sh in payload["status_history"]:
            sh["changed_by_name"] = changer_map.get(sh["changed_by"], "System")

    return payload


@router.put("/{id}")
def update_job(id: str, req: JobUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Update job general fields (dispatcher/admin or assigned tech)"""
    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    job = db.scalar(
        select(Job)
        .where(Job.id == id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Validate permission
    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied. You are not assigned to this job.")

    # Update fields
    update_data = req.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(job, field, val)

    job.updated_by = user_id
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return serialize_job(job)


@router.delete("/{id}")
def delete_job(id: str, request: Request, db: Session = Depends(get_db)):
    """Soft delete a job (admin only)"""
    check_permission(request, ["company_admin"])
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.deleted_at = datetime.now(timezone.utc)
    job.updated_by = user_id
    db.commit()
    return {"status": "success", "detail": f"Job {id} soft deleted"}


@router.post("/{id}/assign")
def assign_technician(id: str, req: JobAssignRequest, request: Request, db: Session = Depends(get_db)):
    """Assign or reassign a lead technician (dispatcher/admin)"""
    check_permission(request, ["company_admin", "dispatcher"])
    company_id = request.state.company_id
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify technician user exists in company
    tech_user = db.scalar(
        select(User)
        .where(User.id == req.tech_id)
        .where(User.company_id == company_id)
        .where(User.role == "tech")
    )
    if not tech_user:
        raise HTTPException(status_code=400, detail="Invalid technician ID for this company")

    # Remove existing lead technician if assigning as lead
    db.execute(
        update(JobTechnician)
        .where(JobTechnician.job_id == id)
        .where(JobTechnician.is_lead == True)
        .values(is_lead=False)
    )

    # Check if this tech is already assigned
    existing = db.scalar(
        select(JobTechnician)
        .where(JobTechnician.job_id == id)
        .where(JobTechnician.tech_id == req.tech_id)
    )
    if existing:
        existing.is_lead = True
    else:
        new_assign = JobTechnician(
            id=f"jt_{ulid.new()}",
            company_id=company_id,
            job_id=id,
            tech_id=req.tech_id,
            is_lead=True,
            created_by=user_id
        )
        db.add(new_assign)

    db.commit()
    db.refresh(job)
    return serialize_job(job)


@router.post("/{id}/status")
def transition_job_status(id: str, req: JobStatusTransitionRequest, request: Request, db: Session = Depends(get_db)):
    """Perform a status transition with state validation, logs, and notification"""
    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    job = db.scalar(
        select(Job)
        .where(Job.id == id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Validate tech permission
    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied. You are not assigned to this job.")

    old_status = job.status
    new_status = req.status

    if old_status == new_status:
        return serialize_job(job)

    # Validate state transition rules
    allowed = VALID_TRANSITIONS.get(old_status, [])
    if new_status not in allowed and new_status not in ["follow_up_required", "cancelled"]:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition from '{old_status}' to '{new_status}'."
        )

    # Apply updates
    current_time = datetime.now(timezone.utc)
    job.status = new_status
    job.updated_at = current_time
    job.updated_by = user_id

    if new_status == "on_site" and not job.arrived_at:
        job.arrived_at = current_time
    elif new_status == "completed" and not job.completed_at:
        job.completed_at = current_time

    # Insert status history entry
    hist = JobStatusHistory(
        id=f"jsh_{ulid.new()}",
        company_id=company_id,
        job_id=id,
        from_status=old_status,
        to_status=new_status,
        changed_by=user_id,
        note=req.note
    )
    db.add(hist)

    # Update technician availability based on status change
    lead_tech = db.scalar(
        select(JobTechnician)
        .where(JobTechnician.job_id == id)
        .where(JobTechnician.is_lead == True)
    )
    if lead_tech:
        if new_status == "on_site":
            update_tech_availability(db, company_id, lead_tech.tech_id, "on_job")
        elif new_status == "completed":
            update_tech_availability(db, company_id, lead_tech.tech_id, "available")

    # Commit state changes
    db.commit()
    db.refresh(job)

    # Send SNS notification to customer on key transitions
    customer = db.scalar(select(Customer).where(Customer.id == job.customer_id))
    if customer:
        message = None
        if new_status == "en_route":
            message = "Your tech is on the way"
        elif new_status == "on_site":
            message = "Your tech has arrived"
        elif new_status == "completed":
            message = "Job complete — invoice on its way"

        if message:
            publish_sns_notification(customer.phone, message)

    return serialize_job(job)

# --- Parts Management Endpoints ---

@router.post("/{id}/parts", status_code=status.HTTP_201_CREATED)
def add_job_part(id: str, req: JobPartRequest, request: Request, db: Session = Depends(get_db)):
    """Add a part used on a job (dispatcher/admin or assigned tech)"""
    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    part_id = f"jp_{ulid.new()}"
    part = JobPart(
        id=part_id,
        company_id=company_id,
        job_id=id,
        name=req.name,
        quantity=req.quantity,
        price_cents=req.price_cents,
        serial_number=req.serial_number,
        created_by=user_id,
        updated_by=user_id
    )
    db.add(part)
    db.commit()
    db.refresh(job)
    return serialize_job(job)


@router.put("/{id}/parts/{part_id}")
def update_job_part(id: str, part_id: str, req: JobPartRequest, request: Request, db: Session = Depends(get_db)):
    """Update a part used on a job (dispatcher/admin or assigned tech)"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    part = db.scalar(
        select(JobPart)
        .where(JobPart.id == part_id)
        .where(JobPart.job_id == id)
    )
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    part.name = req.name
    part.quantity = req.quantity
    part.price_cents = req.price_cents
    part.serial_number = req.serial_number
    part.updated_by = user_id
    part.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(job)
    return serialize_job(job)


@router.delete("/{id}/parts/{part_id}")
def remove_job_part(id: str, part_id: str, request: Request, db: Session = Depends(get_db)):
    """Remove a part used from a job (dispatcher/admin or assigned tech)"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    part = db.scalar(
        select(JobPart)
        .where(JobPart.id == part_id)
        .where(JobPart.job_id == id)
    )
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    db.delete(part)
    db.commit()
    db.refresh(job)
    return serialize_job(job)


# --- Notes Management Endpoints ---

@router.post("/{id}/notes", status_code=status.HTTP_201_CREATED)
def add_job_note(id: str, req: JobNoteRequest, request: Request, db: Session = Depends(get_db)):
    """Add a note to a job (dispatcher/admin or assigned tech)"""
    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    note_id = f"jnt_{ulid.new()}"
    note = JobNote(
        id=note_id,
        company_id=company_id,
        job_id=id,
        author_id=user_id,
        note_type=req.note_type or "general",
        body=req.body,
        is_internal=req.is_internal,
        created_by=user_id,
        updated_by=user_id
    )
    db.add(note)
    db.commit()
    db.refresh(job)
    return serialize_job(job)


# --- Photos Management Endpoints ---

@router.post("/{id}/photos/presign")
def generate_photo_presign_url(
    id: str,
    req: PresignRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Generate an S3 presigned PUT URL for uploading a job photo (assigned tech or dispatcher/admin)"""
    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    photo_type = req.photo_type
    if photo_type not in ["nameplate", "fault", "before", "after", "general"]:
        raise HTTPException(status_code=400, detail="Invalid photo type")

    photo_ulid = ulid.new()
    s3_key = f"{company_id}/{id}/{photo_type}/{photo_ulid}.jpg"

    bucket_name = None
    try:
        from sst import Resource
        if hasattr(Resource, "MediaBucket"):
            bucket_name = Resource.MediaBucket.name
    except Exception:
        pass

    if bucket_name:
        try:
            s3_client = boto3.client("s3")
            env = os.getenv("STAGE", "dev")
            tags = f"Environment={env}&company_id={company_id}&job_id={id}&photo_type={photo_type}"
            
            presigned_url = s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": bucket_name,
                    "Key": s3_key,
                    "ContentType": "image/jpeg",
                    "Tagging": tags
                },
                ExpiresIn=300
            )
            return {
                "upload_url": presigned_url,
                "s3_key": s3_key,
                "headers": {
                    "Content-Type": "image/jpeg",
                    "x-amz-tagging": tags
                }
            }
        except Exception as e:
            logger.warning(f"Failed to generate real presigned URL: {e}")

    # Fallback to local dev mock endpoint
    api_url = os.getenv("API_URL", "http://localhost:8000")
    mock_upload_url = f"{api_url}/mock-s3-upload/{s3_key}"
    return {
        "upload_url": mock_upload_url,
        "s3_key": s3_key,
        "headers": {
            "Content-Type": "image/jpeg"
        }
    }


@router.post("/{id}/photos", status_code=status.HTTP_201_CREATED)
async def add_job_photo(
    id: str,
    request: Request,
    file: Optional[UploadFile] = File(None),
    photo_type: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Register a photo.
    Supports BOTH:
    1. JSON registration (after S3 upload): {"s3_key": "...", "photo_type": "...", ...}
    2. Multipart file upload (legacy fallback)
    """
    import json
    role = request.state.role
    user_id = request.state.user_id
    company_id = request.state.company_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            body_bytes = await request.body()
            body_data = json.loads(body_bytes)
            s3_key = body_data.get("s3_key")
            if not s3_key:
                raise HTTPException(status_code=400, detail="Missing s3_key in JSON request")
            
            p_type = body_data.get("photo_type", "general")
            if p_type not in ["nameplate", "fault", "before", "after", "general"]:
                raise HTTPException(status_code=400, detail="Invalid photo type")

            caption_val = body_data.get("caption")
            size_bytes = body_data.get("file_size_bytes")
            mime = body_data.get("mime_type", "image/jpeg")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    else:
        # Fallback to Multipart Upload (legacy)
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded or invalid JSON body")
        
        p_type = photo_type or "general"
        if p_type not in ["nameplate", "fault", "before", "after", "general"]:
            raise HTTPException(status_code=400, detail="Invalid photo type")

        file_ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
        s3_key = f"job-photos/{id}/{ulid.new()}{file_ext}"

        bucket_name = None
        media_domain = None
        try:
            from sst import Resource
            if hasattr(Resource, "MediaBucket"):
                bucket_name = Resource.MediaBucket.name
                media_domain = getattr(Resource.MediaBucket, "domain", None)
        except Exception:
            pass

        upload_url = None
        if bucket_name:
            try:
                s3 = boto3.client("s3")
                s3.upload_fileobj(
                    file.file,
                    bucket_name,
                    s3_key,
                    ExtraArgs={"ContentType": file.content_type or "image/jpeg"}
                )
                if media_domain:
                    upload_url = f"https://{media_domain}/{s3_key}"
                else:
                    upload_url = f"/media/{s3_key}"
            except Exception as e:
                logger.warning(f"Failed S3 upload fallback: {e}")

        if not upload_url:
            upload_url = f"https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&q=80&w=400&mock={ulid.new()}"

        caption_val = caption
        size_bytes = None
        mime = file.content_type or "image/jpeg"

    cdn_domain = os.getenv("CDN_DOMAIN")
    if not cdn_domain:
        try:
            from sst import Resource
            if hasattr(Resource, "MediaBucket"):
                cdn_domain = getattr(Resource.MediaBucket, "domain", None)
        except Exception:
            pass
    if not cdn_domain:
        cdn_domain = "media.augmentedtradetech.com"

    db_cdn_url = f"https://{cdn_domain}/{s3_key}"

    photo_id = f"jph_{ulid.new()}"
    new_photo = JobPhoto(
        id=photo_id,
        company_id=company_id,
        job_id=id,
        tech_id=user_id,
        photo_type=p_type,
        s3_key=s3_key,
        cdn_url=db_cdn_url,
        caption=caption_val,
        file_size_bytes=size_bytes,
        mime_type=mime,
        created_by=user_id
    )
    db.add(new_photo)
    db.commit()
    db.refresh(job)
    return serialize_job(job)


@router.get("/{id}/photos")
def list_job_photos(
    id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """List all photos for a job (assigned tech or dispatcher/admin)"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    photos = db.scalars(
        select(JobPhoto)
        .where(JobPhoto.job_id == id)
        .where(JobPhoto.deleted_at.is_(None))
        .order_by(JobPhoto.taken_at.desc())
    ).all()

    cdn_domain = os.getenv("CDN_DOMAIN")
    if not cdn_domain:
        try:
            from sst import Resource
            if hasattr(Resource, "MediaBucket"):
                cdn_domain = getattr(Resource.MediaBucket, "domain", None)
        except Exception:
            pass
    if not cdn_domain:
        cdn_domain = "media.augmentedtradetech.com"

    result = []
    for p in photos:
        final_cdn_url = f"https://{cdn_domain}/{p.s3_key}" if p.s3_key else p.cdn_url
        result.append({
            "id": p.id,
            "photo_type": p.photo_type,
            "s3_key": p.s3_key,
            "cdn_url": final_cdn_url,
            "caption": p.caption,
            "file_size_bytes": p.file_size_bytes,
            "mime_type": p.mime_type,
            "taken_at": p.taken_at.isoformat() if p.taken_at else None,
            "created_by": p.created_by
        })
    return result


@router.delete("/{id}/photos/{photo_id}")
def delete_job_photo(
    id: str,
    photo_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Soft delete a photo from a job"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    photo = db.scalar(
        select(JobPhoto)
        .where(JobPhoto.id == photo_id)
        .where(JobPhoto.job_id == id)
        .where(JobPhoto.deleted_at.is_(None))
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    photo.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "success", "message": "Photo soft-deleted successfully"}


# --- Inspection Workflow Engine Endpoints ---

@router.get("/{id}/workflow")
def get_job_workflow(
    id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Retrieve the inspection workflow template and current progress for a job"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    company = db.scalar(select(Company).where(Company.id == job.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Retrieve trade workflow config
    trade_config = None
    if company.workflow_config and job.trade in company.workflow_config:
        trade_config = company.workflow_config[job.trade]
    else:
        trade_config = DEFAULT_WORKFLOW_CONFIG.get(job.trade)

    if not trade_config:
        raise HTTPException(
            status_code=404, 
            detail=f"No workflow configuration found for trade '{job.trade}'"
        )

    return {
        "trade": job.trade,
        "steps": trade_config.get("steps", []),
        "progress": job.inspection_data or {}
    }


@router.put("/{id}/workflow/{step}")
def update_job_workflow_step(
    id: str,
    step: str,
    req: WorkflowStepUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Save step progress data (idempotent, sync-queue safe)"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    company = db.scalar(select(Company).where(Company.id == job.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Validate step exists in workflow config
    trade_config = None
    if company.workflow_config and job.trade in company.workflow_config:
        trade_config = company.workflow_config[job.trade]
    else:
        trade_config = DEFAULT_WORKFLOW_CONFIG.get(job.trade)

    if not trade_config:
        raise HTTPException(status_code=404, detail=f"No workflow config found for trade '{job.trade}'")

    steps_list = trade_config.get("steps", [])
    valid_step_keys = {s["key"] for s in steps_list}
    if step not in valid_step_keys:
        raise HTTPException(status_code=400, detail=f"Invalid step key '{step}' for trade '{job.trade}'")

    current_data = job.inspection_data or {}

    # Enforce idempotency: if idempotency key matches, return existing record without modification
    existing_step = current_data.get(step, {})
    if existing_step and existing_step.get("idempotency_key") == req.idempotency_key:
        return {
            "status": "success",
            "message": "Idempotent request; no updates made.",
            "step_data": existing_step
        }

    # Otherwise update in place
    new_data = copy.deepcopy(current_data)
    
    # Retain existing AI results if any (or initialize as None)
    existing_ai_result = existing_step.get("ai_result") if existing_step else None

    new_data[step] = {
        "inputs": req.inputs,
        "ai_result": existing_ai_result,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "skipped": req.skipped,
        "idempotency_key": req.idempotency_key
    }

    job.inspection_data = new_data
    db.add(job)
    db.commit()
    db.refresh(job)

    return {
        "status": "success",
        "step_data": job.inspection_data[step]
    }


@router.post("/{id}/workflow/{step}/ai")
def trigger_ai_analysis(
    id: str,
    step: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Trigger AI analysis/diagnostics on the accumulated step data"""
    role = request.state.role
    user_id = request.state.user_id

    job = db.scalar(select(Job).where(Job.id == id).where(Job.deleted_at.is_(None)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if role == "tech":
        is_assigned = db.scalar(
            select(JobTechnician)
            .where(JobTechnician.job_id == id)
            .where(JobTechnician.tech_id == user_id)
        )
        if not is_assigned:
            raise HTTPException(status_code=403, detail="Access denied")

    company = db.scalar(select(Company).where(Company.id == job.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Validate step exists in workflow config
    trade_config = None
    if company.workflow_config and job.trade in company.workflow_config:
        trade_config = company.workflow_config[job.trade]
    else:
        trade_config = DEFAULT_WORKFLOW_CONFIG.get(job.trade)

    if not trade_config:
        raise HTTPException(status_code=404, detail=f"No workflow config found for trade '{job.trade}'")

    steps_list = trade_config.get("steps", [])
    step_def = next((s for s in steps_list if s["key"] == step), None)
    if not step_def:
        raise HTTPException(status_code=400, detail=f"Invalid step key '{step}' for trade '{job.trade}'")

    current_data = job.inspection_data or {}
    step_data = current_data.get(step, {})

    # For AI trigger steps, we don't strictly require prior step inputs (since it evaluates all previous steps).
    # But for other steps, we must have saved inputs first before triggering AI on it.
    if step_def["type"] != "ai_trigger" and not step_data:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot run AI analysis on step '{step}' because inputs have not been submitted."
        )

    inputs = step_data.get("inputs", {})

    # Simulate AI analysis based on step key and type
    ai_result = {}
    request_type = "readings_analysis"

    if step == "equipment_id":
        request_type = "nameplate_scan"
        ai_result = {
            "make": "Carrier",
            "model": "58SB0A070E1412",
            "serial_number": "1819A12345",
            "tonnage": 3.0,
            "age_years": 5,
            "status": "success",
            "confidence": 0.95
        }
        # Auto-populate job record / equipment
        equipment = None
        if job.equipment_id:
            equipment = db.scalar(select(Equipment).where(Equipment.id == job.equipment_id))

        if not equipment:
            equipment = Equipment(
                id=f"eqp_{ulid.new()}",
                company_id=job.company_id,
                trade="hvac",
                equipment_type="split_ac"
            )
            db.add(equipment)
            db.flush()
            job.equipment_id = equipment.id

        equipment.make = ai_result["make"]
        equipment.model = ai_result["model"]
        equipment.serial_number = ai_result["serial_number"]
        equipment.ai_extracted_data = ai_result

        # Auto-create EquipmentCustomer link
        if job.customer_id:
            assoc = db.scalar(
                select(EquipmentCustomer)
                .where(EquipmentCustomer.equipment_id == equipment.id)
                .where(EquipmentCustomer.customer_id == job.customer_id)
            )
            if not assoc:
                assoc = EquipmentCustomer(
                    id=f"eqc_{ulid.new()}",
                    company_id=job.company_id,
                    equipment_id=equipment.id,
                    customer_id=job.customer_id
                )
                db.add(assoc)

    elif step == "refrigerant_pressures":
        suction = inputs.get("suction_pressure", 120)
        discharge = inputs.get("discharge_pressure", 320)
        superheat = 12.0
        subcooling = 10.0
        ai_result = {
            "calculated_superheat_f": superheat,
            "calculated_subcooling_f": subcooling,
            "status": "normal",
            "anomalies_detected": False,
            "recommendation": "Pressures and calculated values are within manufacturer specifications."
        }

    elif step == "temperature_readings":
        supply = inputs.get("supply_temp", 55.0)
        return_t = inputs.get("return_temp", 75.0)
        try:
            delta_t = float(return_t) - float(supply)
        except (ValueError, TypeError):
            delta_t = 20.0

        status_val = "normal" if 16.0 <= delta_t <= 22.0 else "anomalous"
        ai_result = {
            "calculated_delta_t": delta_t,
            "status": status_val,
            "recommendation": "Delta-T is optimal." if status_val == "normal" else "Delta-T is out of specification. Potential airflow or refrigerant issue."
        }

    elif step == "ai_diagnosis":
        request_type = "diagnosis"
        if job.trade == "hvac":
            ai_result = {
                "diagnostic_summary": "Based on the dirty/restricted filter and normal pressures, the system is currently performing within normal parameters but airflow is reduced.",
                "likely_causes": [
                    {"cause": "Restricted airflow due to dirty filter", "confidence": 0.85},
                    {"cause": "Minor blower motor speed discrepancy", "confidence": 0.20}
                ],
                "recommended_actions": [
                    "Replace the return air filter with a new MERV 11 filter.",
                    "Clean debris from the evaporator coil surface."
                ]
            }
        else:
            ai_result = {
                "diagnostic_summary": "Safety sensors and auto-reverse test passed. Springs are properly wound and balanced.",
                "likely_causes": [],
                "recommended_actions": [
                    "Perform standard quarterly lubrication of tracks, rollers, and hinges.",
                    "Verify limit switch alignment."
                ]
            }

    elif step == "diagnosis_repair":
        request_type = "auto_document"
        work_notes = inputs.get("notes") or inputs.get("work_performed") or "Standard maintenance performed."
        ai_result = {
            "drafted_summary": f"Technician completed inspection and service. Action summary: {work_notes}",
            "suggested_invoice_notes": "All safety checks passed. System left in good working order."
        }

    elif step == "spring_system":
        ai_result = {
            "wear_level": "low",
            "imbalance_risk": "low",
            "status": "normal",
            "recommendation": "Spring tension is within spec. No immediate replacement needed."
        }

    else:
        ai_result = {
            "status": "analyzed",
            "summary": f"AI analysis completed for step '{step}'. No anomalies detected."
        }

    # Log to ai_requests table
    ai_req = AIRequest(
        id=f"ai_{ulid.new()}",
        company_id=job.company_id,
        user_id=user_id,
        job_id=job.id,
        request_type=request_type,
        model="claude-3-5-sonnet",
        input_tokens=450,
        output_tokens=180,
        cost_usd_micro=1900,
        feature_tag="inspection_workflow",
        cache_hit=False,
        latency_ms=250,
        status="success"
    )
    db.add(ai_req)

    # Save to jobs.inspection_data
    new_data = copy.deepcopy(current_data)
    if step not in new_data:
        new_data[step] = {
            "inputs": {},
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "skipped": False,
            "idempotency_key": f"ai_gen_{ulid.new()}"
        }
    new_data[step]["ai_result"] = ai_result

    job.inspection_data = new_data
    db.add(job)
    db.commit()
    db.refresh(job)

    return {
        "status": "success",
        "step_data": job.inspection_data[step]
    }
