import ulid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from apps.api.app.core.database import get_db
from apps.api.app.models.customer import Customer
from apps.api.app.models.job import Job

router = APIRouter(prefix="/customers", tags=["customers"])

class CustomerCreateRequest(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    customer_type: Optional[str] = "residential"
    notes: Optional[str] = None

def serialize_customer(c: Customer) -> Dict[str, Any]:
    return {
        "id": c.id,
        "company_id": c.company_id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "email": c.email,
        "phone": c.phone,
        "address_line1": c.address_line1,
        "address_line2": c.address_line2,
        "city": c.city,
        "state": c.state,
        "zip": c.zip,
        "customer_type": c.customer_type,
        "notes": c.notes,
        "portal_enabled": c.portal_enabled,
        "created_at": c.created_at.isoformat() if c.created_at else None
    }

@router.get("")
def list_customers(request: Request, q: Optional[str] = None, db: Session = Depends(get_db)):
    """List and search customers by name, phone, email (RLS scoped)"""
    company_id = request.state.company_id
    
    stmt = select(Customer).where(Customer.company_id == company_id)
    if q:
        search = f"%{q}%"
        stmt = stmt.where(
            or_(
                Customer.first_name.ilike(search),
                Customer.last_name.ilike(search),
                Customer.email.ilike(search),
                Customer.phone.ilike(search)
            )
        )
    stmt = stmt.order_by(Customer.last_name.asc(), Customer.first_name.asc())
    customers = db.scalars(stmt).all()
    return [serialize_customer(c) for c in customers]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(req: CustomerCreateRequest, request: Request, db: Session = Depends(get_db)):
    """Create a new customer (dispatcher/admin only)"""
    company_id = request.state.company_id
    user_id = request.state.user_id
    
    # Check permissions
    role = request.state.role
    if role not in ["company_admin", "dispatcher"]:
        raise HTTPException(status_code=403, detail="Only admins and dispatchers can create customers")
        
    cust = Customer(
        id=f"cust_{ulid.new()}",
        company_id=company_id,
        first_name=req.first_name,
        last_name=req.last_name,
        email=req.email,
        phone=req.phone,
        address_line1=req.address_line1,
        address_line2=req.address_line2,
        city=req.city,
        state=req.state,
        zip=req.zip,
        customer_type=req.customer_type or "residential",
        notes=req.notes,
        created_by=user_id,
        updated_by=user_id
    )
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return serialize_customer(cust)

@router.get("/{id}")
def get_customer_detail(id: str, request: Request, db: Session = Depends(get_db)):
    """Get customer details and history of past/present jobs"""
    company_id = request.state.company_id
    
    cust = db.scalar(
        select(Customer)
        .where(Customer.id == id)
        .where(Customer.company_id == company_id)
    )
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    # Get job history
    jobs = db.scalars(
        select(Job)
        .where(Job.customer_id == id)
        .where(Job.company_id == company_id)
        .where(Job.deleted_at.is_(None))
        .order_by(Job.scheduled_start.desc().nulls_last())
    ).all()
    
    jobs_payload = []
    for j in jobs:
        jobs_payload.append({
            "id": j.id,
            "job_number": j.job_number,
            "trade": j.trade,
            "job_type": j.job_type,
            "priority": j.priority,
            "status": j.status,
            "scheduled_start": j.scheduled_start.isoformat() if j.scheduled_start else None,
            "scheduled_end": j.scheduled_end.isoformat() if j.scheduled_end else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None
        })
        
    payload = serialize_customer(cust)
    payload["jobs"] = jobs_payload
    return payload
