from datetime import datetime, timezone
import zoneinfo
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, text, and_

from apps.api.app.core.database import get_db
from apps.api.app.models.job import Job, JobTechnician
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.company import Company
from apps.api.app.routers.jobs import serialize_job

router = APIRouter(prefix="/dispatch", tags=["dispatch"])

class SuggestTechRequest(BaseModel):
    job_id: str

@router.get("/board")
def get_dispatch_board(request: Request, date: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all jobs for a specific day grouped by status columns (unassigned, scheduled, en_route, on_site, in_progress, completed)"""
    company_id = request.state.company_id
    
    # Resolve timezone
    company = db.scalar(select(Company).where(Company.id == company_id))
    tz_name = company.timezone if (company and company.timezone) else "America/Chicago"
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")

    # Parse date or default to today
    if date:
        try:
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")
    else:
        parsed_date = datetime.now(tz).date()

    # Determine timezone boundaries
    start_dt = datetime.combine(parsed_date, datetime.min.time()).replace(tzinfo=tz)
    end_dt = datetime.combine(parsed_date, datetime.max.time()).replace(tzinfo=tz)

    # Fetch jobs scheduled for this date range
    stmt = (
        select(Job)
        .where(Job.company_id == company_id)
        .where(Job.deleted_at.is_(None))
        .where(Job.scheduled_start >= start_dt)
        .where(Job.scheduled_start <= end_dt)
        .order_by(Job.scheduled_start.asc().nulls_last())
    )
    jobs = db.scalars(stmt).all()

    # Columns: Unassigned | Scheduled | En Route | On Site | In Progress | Completed
    board = {
        "unassigned": [],
        "scheduled": [],
        "en_route": [],
        "on_site": [],
        "in_progress": [],
        "completed": []
    }

    for j in jobs:
        # Check if job is unassigned (no technicians list)
        is_unassigned = len(j.technicians) == 0
        serialized = serialize_job(j)

        # Enrich technician full names
        tech_ids = [t["tech_id"] for t in serialized["technicians"]]
        if tech_ids:
            users = db.scalars(select(User).where(User.id.in_(tech_ids))).all()
            user_map = {u.id: u.full_name for u in users}
            for t in serialized["technicians"]:
                t["full_name"] = user_map.get(t["tech_id"], "Unknown Technician")

        if is_unassigned:
            board["unassigned"].append(serialized)
        else:
            status_val = j.status
            if status_val in ["scheduled", "confirmed", "follow_up_required"]:
                board["scheduled"].append(serialized)
            elif status_val == "en_route":
                board["en_route"].append(serialized)
            elif status_val == "on_site":
                board["on_site"].append(serialized)
            elif status_val in ["in_progress", "parts_needed", "paused"]:
                board["in_progress"].append(serialized)
            elif status_val in ["completed", "invoiced", "paid"]:
                board["completed"].append(serialized)
            else:
                # Fallback for unexpected states
                board["scheduled"].append(serialized)

    return board

@router.get("/techs")
def get_dispatch_techs(request: Request, db: Session = Depends(get_db)):
    """List all active techs with availability status and current active job"""
    company_id = request.state.company_id

    techs = db.scalars(
        select(User)
        .where(User.company_id == company_id)
        .where(User.role == "tech")
        .where(User.is_active == True)
        .order_by(User.full_name.asc())
    ).all()

    response = []
    for t in techs:
        avail_status = "offline"
        trades_list = []
        skills_list = []
        if t.tech_profile:
            avail_status = t.tech_profile.availability_status
            trades_list = t.tech_profile.trades or []
            skills_list = t.tech_profile.skills or []

        # Find active job
        active_jt = db.scalar(
            select(JobTechnician)
            .join(Job, Job.id == JobTechnician.job_id)
            .where(JobTechnician.tech_id == t.id)
            .where(Job.deleted_at.is_(None))
            .where(Job.status.notin_(["completed", "cancelled", "invoiced", "paid"]))
            .order_by(Job.scheduled_start.asc().nulls_last())
            .limit(1)
        )

        active_job = None
        if active_jt and active_jt.job:
            active_job = {
                "id": active_jt.job.id,
                "job_number": active_jt.job.job_number,
                "status": active_jt.job.status,
                "priority": active_jt.job.priority,
                "trade": active_jt.job.trade,
                "customer_name": f"{active_jt.job.customer.first_name} {active_jt.job.customer.last_name}" if active_jt.job.customer else "Unknown Client"
            }

        response.append({
            "id": t.id,
            "full_name": t.full_name,
            "email": t.email,
            "phone": t.phone,
            "avatar_url": t.avatar_url,
            "availability_status": avail_status,
            "trades": trades_list,
            "skills": skills_list,
            "active_job": active_job
        })

    return response

@router.get("/unassigned")
def get_dispatch_unassigned(request: Request, db: Session = Depends(get_db)):
    """Get all unassigned jobs that are not completed/cancelled"""
    company_id = request.state.company_id

    stmt = (
        select(Job)
        .outerjoin(JobTechnician, JobTechnician.job_id == Job.id)
        .where(Job.company_id == company_id)
        .where(Job.deleted_at.is_(None))
        .where(JobTechnician.id.is_(None))
        .where(Job.status.notin_(["completed", "cancelled", "invoiced", "paid"]))
        .order_by(Job.scheduled_start.asc().nulls_last())
    )
    jobs = db.scalars(stmt).all()
    
    payloads = []
    for j in jobs:
        payloads.append(serialize_job(j))
    return payloads

@router.post("/suggest-tech")
def suggest_best_tech(req: SuggestTechRequest, request: Request, db: Session = Depends(get_db)):
    """Suggest best technician for a job based on trade specialties, status, and workload"""
    company_id = request.state.company_id

    job = db.scalar(
        select(Job)
        .where(Job.id == req.job_id)
        .where(Job.company_id == company_id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    techs = db.scalars(
        select(User)
        .where(User.company_id == company_id)
        .where(User.role == "tech")
        .where(User.is_active == True)
    ).all()

    if not techs:
        return {
            "suggested_tech_id": None,
            "reasoning": "No active technicians are registered for this company."
        }

    scored_techs = []
    for t in techs:
        score = 0
        reasons = []

        status_val = "offline"
        trades_list = []
        if t.tech_profile:
            status_val = t.tech_profile.availability_status
            trades_list = t.tech_profile.trades or []

        # Trade Match
        if job.trade in trades_list:
            score += 50
            reasons.append(f"matches trade specialty ({job.trade})")
        else:
            reasons.append("specialty does not match trade")

        # Availability Score
        if status_val == "available":
            score += 40
            reasons.append("is currently available")
        elif status_val in ["driving", "break"]:
            score += 25
            reasons.append(f"is currently {status_val}")
        elif status_val == "on_job":
            score += 10
            reasons.append("is on a job")
        else:
            score -= 10
            reasons.append("is offline/off-duty")

        # Today's workload check (UTC or general local date start/end)
        today_start = datetime.combine(datetime.now().date(), datetime.min.time())
        today_end = datetime.combine(datetime.now().date(), datetime.max.time())
        workload = db.scalar(
            select(text("count(*)"))
            .select_from(text("job_technicians jt"))
            .join(text("jobs j"), text("j.id = jt.job_id"))
            .where(text("jt.tech_id = :tech_id"))
            .where(text("j.scheduled_start >= :t_start"))
            .where(text("j.scheduled_start <= :t_end"))
            .where(text("j.deleted_at is null")),
            {"tech_id": t.id, "t_start": today_start, "t_end": today_end}
        ) or 0

        if workload == 0:
            score += 15
            reasons.append("has 0 jobs scheduled today")
        elif workload == 1:
            score += 10
            reasons.append("has 1 job scheduled today")
        else:
            score -= (workload * 5)
            reasons.append(f"has {workload} jobs today")

        scored_techs.append({
            "tech_id": t.id,
            "full_name": t.full_name,
            "score": score,
            "reasons": reasons
        })

    # Sort descending by score
    scored_techs.sort(key=lambda x: x["score"], reverse=True)
    suggestion = scored_techs[0]

    reasons_str = ", ".join(suggestion["reasons"])
    reasoning = f"{suggestion['full_name']} is selected because they {reasons_str}."

    return {
        "suggested_tech_id": suggestion["tech_id"],
        "reasoning": reasoning
    }
