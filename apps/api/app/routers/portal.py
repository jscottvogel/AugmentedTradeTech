import os
import secrets
import hashlib
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import jwt
import boto3
import ulid
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, text

from apps.api.app.core.database import get_db, set_rls_context
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer
from apps.api.app.models.job import Job, JobPhoto, JobStatusHistory
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger, LoyaltyBalanceView
from apps.api.app.models.company import Company
from apps.api.app.models.auth import CustomerMagicLinkToken
from apps.api.app.models.user import User
from apps.api.app.routers.auth import JWT_SECRET, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, hash_token
from apps.api.app.routers.invoices import process_successful_payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])

# Schemas
class CustomerMagicLinkRequest(BaseModel):
    contact: str  # Email or phone number

class CustomerVerifyRequest(BaseModel):
    token: str

class ServiceRequestCreate(BaseModel):
    trade: str  # hvac | garage_door
    reported_problem: str
    equipment_id: Optional[str] = None
    priority: Optional[str] = "routine"

class PhotoPresignRequest(BaseModel):
    photo_type: str  # nameplate | fault | before | after | general

class PhotoRegisterRequest(BaseModel):
    photo_type: str
    s3_key: str
    cdn_url: str
    caption: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = "image/jpeg"

class MembershipEnrollRequest(BaseModel):
    plan_id: str
    billing_cadence: str  # monthly | annual

class PortalPayRequest(BaseModel):
    confirm_mock: Optional[bool] = False

# Helper Dependency to elevate RLS context to platform_admin
# so we can query customer-specific data across companies (if token validates it)
# and enforce strict application-layer filtering by customer_id
def get_portal_db(db: Session = Depends(get_db)):
    set_rls_context(db, None, None, "platform_admin")
    return db

def check_customer_auth(request: Request):
    """Dependency to check if the current user is a customer"""
    role = getattr(request.state, "role", None)
    customer_id = getattr(request.state, "customer_id", None)
    if role != "customer" or not customer_id:
        raise HTTPException(status_code=401, detail="Customer authentication required")
    return customer_id

# Public Configuration Config
@router.get("/company-config")
def get_company_config(
    slug: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_portal_db)
):
    """Retrieve company name, logo_url, and primary_color by slug or from JWT state"""
    company = None
    if slug:
        company = db.scalar(select(Company).where(Company.slug == slug))
    elif request and hasattr(request, "state") and getattr(request.state, "company_id", None):
        company_id = request.state.company_id
        company = db.scalar(select(Company).where(Company.id == company_id))
    
    if not company:
        raise HTTPException(status_code=404, detail="Company configuration not found")
        
    return {
        "name": company.name,
        "logo_url": company.logo_url,
        "primary_color": company.primary_color or "#3b82f6",  # Default theme color
        "slug": company.slug
    }

# Auth Routes
@router.post("/auth/magic-link")
def send_customer_magic_link(req: CustomerMagicLinkRequest, db: Session = Depends(get_portal_db)):
    """Generate a magic link for a customer using email or phone"""
    contact_cleaned = req.contact.strip().lower()
    
    # Check if a customer matches this email or phone
    customer = db.scalar(
        select(Customer).where(
            or_(
                Customer.email.ilike(contact_cleaned),
                Customer.phone == req.contact.strip()
            )
        )
    )
    
    if not customer:
        # Prevent contact enumeration
        return {"message": "If the contact details are registered, a login link has been sent."}
        
    if not customer.portal_enabled:
        raise HTTPException(status_code=400, detail="Portal access is disabled for this account")
        
    raw_token = secrets.token_hex(32)
    token_hashed = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    magic_token = CustomerMagicLinkToken(
        id=f"cml_{ulid.new()}",
        customer_id=customer.id,
        token_hash=token_hashed,
        expires_at=expires_at,
        created_by="system",
        updated_by="system"
    )
    db.add(magic_token)
    db.commit()
    
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    # Fetch company slug for correct redirect
    company = db.scalar(select(Company).where(Company.id == customer.company_id))
    slug_param = f"&slug={company.slug}" if company else ""
    verify_url = f"{frontend_url}/portal/verify?token={raw_token}{slug_param}"
    
    # Print to console in local development
    print(f"\n[LOCAL DEV] Customer Magic Link for {customer.first_name} ({req.contact}):\n{verify_url}\n")
    
    # Also attempt sending via SES (for email)
    if customer.email and "@" in contact_cleaned:
        try:
            ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
            sender = os.getenv("SES_SENDER_EMAIL", "noreply@augmentedtradetech.com")
            subject = f"{company.name} - Portal Login Link" if company else "Customer Portal - Login Link"
            
            body_text = f"Hello {customer.first_name},\n\nClick the link below to log in to your customer portal:\n\n{verify_url}\n\nThis link is valid for 15 minutes."
            body_html = f"""<html>
            <body>
              <h3>{company.name if company else 'Customer Portal'}</h3>
              <p>Hello {customer.first_name},</p>
              <p>Click the link below to log in to your portal account:</p>
              <p><a href="{verify_url}"><strong>Log In to Portal</strong></a></p>
              <p>Or copy/paste this URL into your browser:</p>
              <p>{verify_url}</p>
              <br/>
              <p>This link is valid for 15 minutes and can only be used once.</p>
            </body>
            </html>"""
            
            ses.send_email(
                Source=sender,
                Destination={"ToAddresses": [customer.email]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {
                        "Text": {"Data": body_text},
                        "Html": {"Data": body_html}
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Failed to send SES email: {e}")
            
    return {"message": "If the contact details are registered, a login link has been sent."}

@router.post("/auth/verify")
def verify_customer_magic_link(req: CustomerVerifyRequest, db: Session = Depends(get_portal_db)):
    """Verify magic link token, activate session, and return JWT"""
    token_hashed = hash_token(req.token)
    token_record = db.scalar(
        select(CustomerMagicLinkToken).where(
            CustomerMagicLinkToken.token_hash == token_hashed,
            CustomerMagicLinkToken.used_at.is_(None)
        )
    )
    
    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or already used magic link")
        
    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Expired magic link")
        
    # Mark token used
    token_record.used_at = datetime.now(timezone.utc)
    
    customer = token_record.customer
    if not customer.portal_enabled:
        raise HTTPException(status_code=400, detail="Portal access is disabled for this account")
        
    customer.portal_last_login_at = datetime.now(timezone.utc)
    db.commit()
    
    # Generate Customer JWT
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": customer.id,
        "customer_id": customer.id,
        "company_id": customer.company_id,
        "role": "customer",
        "email": customer.email,
        "phone": customer.phone,
        "exp": expire
    }
    access_token = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "customer": {
            "id": customer.id,
            "email": customer.email,
            "phone": customer.phone,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "company_id": customer.company_id
        }
    }

# Authenticated Portal Routes
@router.get("/me")
def get_customer_profile(
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Retrieve logged-in customer's profile"""
    customer = db.scalar(select(Customer).where(Customer.id == customer_id))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {
        "id": customer.id,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone,
        "address_line1": customer.address_line1,
        "address_line2": customer.address_line2,
        "city": customer.city,
        "state": customer.state,
        "zip": customer.zip,
        "customer_type": customer.customer_type,
        "notes": customer.notes,
        "portal_last_login_at": customer.portal_last_login_at.isoformat() if customer.portal_last_login_at else None
    }

@router.get("/jobs")
def get_customer_jobs(
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Get completed job history for the customer"""
    stmt = (
        select(Job)
        .where(Job.customer_id == customer_id)
        .where(Job.status.in_(["completed", "invoiced", "paid"]))
        .where(Job.deleted_at.is_(None))
        .order_by(Job.completed_at.desc().nulls_last())
    )
    jobs = db.scalars(stmt).all()
    
    return [{
        "id": j.id,
        "job_number": j.job_number,
        "trade": j.trade,
        "job_type": j.job_type,
        "priority": j.priority,
        "status": j.status,
        "reported_problem": j.reported_problem,
        "scheduled_start": j.scheduled_start.isoformat() if j.scheduled_start else None,
        "scheduled_end": j.scheduled_end.isoformat() if j.scheduled_end else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None
    } for j in jobs]

@router.get("/jobs/{id}")
def get_customer_job_detail(
    id: str,
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Get specific job detail, scoped to this customer"""
    job = db.scalar(
        select(Job)
        .where(Job.id == id)
        .where(Job.customer_id == customer_id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    photos = db.scalars(
        select(JobPhoto)
        .where(JobPhoto.job_id == id)
        .where(JobPhoto.deleted_at.is_(None))
    ).all()
    
    return {
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
        "arrived_at": job.arrived_at.isoformat() if job.arrived_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "photos": [{
            "id": p.id,
            "photo_type": p.photo_type,
            "cdn_url": p.cdn_url,
            "caption": p.caption,
            "taken_at": p.taken_at.isoformat()
        } for p in photos]
    }

@router.get("/invoices")
def get_customer_invoices(
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Retrieve non-draft invoices for this customer"""
    stmt = (
        select(Invoice)
        .where(Invoice.customer_id == customer_id)
        .where(Invoice.status != "draft")
        .where(Invoice.deleted_at.is_(None))
        .order_by(Invoice.created_at.desc())
    )
    invoices = db.scalars(stmt).all()
    
    return [{
        "id": i.id,
        "invoice_number": i.invoice_number,
        "status": i.status,
        "subtotal_cents": i.subtotal_cents,
        "tax_cents": i.tax_cents,
        "discount_cents": i.discount_cents,
        "total_cents": i.total_cents,
        "amount_paid_cents": i.amount_paid_cents,
        "balance_cents": i.balance_cents,
        "due_date": i.due_date.isoformat() if i.due_date else None,
        "payment_terms": i.payment_terms,
        "paid_at": i.paid_at.isoformat() if i.paid_at else None
    } for i in invoices]

@router.get("/invoices/{id}")
def get_customer_invoice_detail(
    id: str,
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Retrieve detailed invoice and line items, scoped to customer"""
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == id)
        .where(Invoice.customer_id == customer_id)
        .where(Invoice.deleted_at.is_(None))
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    line_items = db.scalars(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == id)
        .order_by(InvoiceLineItem.sort_order.asc())
    ).all()
    
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "subtotal_cents": invoice.subtotal_cents,
        "tax_cents": invoice.tax_cents,
        "discount_cents": invoice.discount_cents,
        "total_cents": invoice.total_cents,
        "amount_paid_cents": invoice.amount_paid_cents,
        "balance_cents": invoice.balance_cents,
        "tax_rate_bps": invoice.tax_rate_bps,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "payment_terms": invoice.payment_terms,
        "notes": invoice.notes,
        "customer_signature_url": invoice.customer_signature_url,
        "signed_at": invoice.signed_at.isoformat() if invoice.signed_at else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "line_items": [{
            "id": item.id,
            "line_type": item.line_type,
            "description": item.description,
            "quantity": float(item.quantity),
            "unit_price_cents": item.unit_price_cents,
            "total_cents": item.total_cents,
            "is_taxable": item.is_taxable,
            "discount_pct": float(item.discount_pct),
            "discount_reason": item.discount_reason
        } for item in line_items]
    }

@router.post("/invoices/{id}/pay")
def pay_customer_invoice(
    id: str,
    req: PortalPayRequest,
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Initiate Stripe PaymentIntent for invoice or confirm mock payment"""
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == id)
        .where(Invoice.customer_id == customer_id)
        .where(Invoice.deleted_at.is_(None))
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="Invoice is already paid")
        
    company = db.scalar(select(Company).where(Company.id == invoice.company_id))
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    
    is_mock = (
        req.confirm_mock or
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )
    
    if is_mock:
        # Create a payment record and process direct success
        process_successful_payment(
            db=db,
            invoice=invoice,
            payment_method="payment_link",
            amount_cents=invoice.total_cents,
            stripe_payment_intent_id=f"pi_mock_{secrets.token_hex(8)}",
            stripe_charge_id=f"ch_mock_{secrets.token_hex(8)}",
            user_id="customer"
        )
        db.commit()
        return {"status": "success", "message": "Mock payment processed successfully"}
        
    # Real Stripe integration
    import stripe
    try:
        stripe.api_key = stripe_key
        intent = stripe.PaymentIntent.create(
            amount=invoice.total_cents,
            currency="usd",
            stripe_account=stripe_account_id,
            metadata={
                "invoice_id": invoice.id,
                "company_id": invoice.company_id,
                "customer_id": customer_id
            }
        )
        
        # Save a pending payment
        payment = Payment(
            id=f"pay_{ulid.new()}",
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            amount_cents=invoice.total_cents,
            payment_method="payment_link",
            status="pending",
            stripe_payment_intent_id=intent.id
        )
        db.add(payment)
        db.commit()
        
        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "status": intent.status
        }
    except Exception as e:
        logger.error(f"Stripe PaymentIntent creation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Stripe PaymentIntent creation failed: {str(e)}")

@router.get("/equipment")
def get_customer_equipment(
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Retrieve equipment associated with the customer, with its service history"""
    associations = db.scalars(
        select(EquipmentCustomer)
        .where(EquipmentCustomer.customer_id == customer_id)
    ).all()
    
    equipment_list = []
    for assoc in associations:
        eq = assoc.equipment
        
        # Fetch service history (jobs completed on this equipment)
        jobs = db.scalars(
            select(Job)
            .where(Job.equipment_id == eq.id)
            .where(Job.status == "completed")
            .where(Job.deleted_at.is_(None))
            .order_by(Job.completed_at.desc())
        ).all()
        
        equipment_list.append({
            "id": eq.id,
            "trade": eq.trade,
            "equipment_type": eq.equipment_type,
            "make": eq.make,
            "model": eq.model,
            "serial_number": eq.serial_number,
            "install_date": eq.install_date.isoformat() if eq.install_date else None,
            "warranty_expires": eq.warranty_expires.isoformat() if eq.warranty_expires else None,
            "location_notes": eq.location_notes,
            "nameplate_photo_url": eq.nameplate_photo_url,
            "is_primary": assoc.is_primary,
            "service_history": [{
                "id": j.id,
                "job_number": j.job_number,
                "job_type": j.job_type,
                "completed_at": j.completed_at.isoformat()
            } for j in jobs]
        })
        
    return equipment_list

@router.post("/requests", status_code=status.HTTP_201_CREATED)
def submit_service_request(
    req: ServiceRequestCreate,
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Submit a new service request (creates a Job)"""
    customer = db.scalar(select(Customer).where(Customer.id == customer_id))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    db_user_id = db.scalar(
        select(User.id)
        .where(User.company_id == customer.company_id)
        .limit(1)
    )
    if not db_user_id:
        db_user_id = "system"
        
    job_id = f"job_{ulid.new()}"
    job = Job(
        id=job_id,
        company_id=customer.company_id,
        customer_id=customer_id,
        equipment_id=req.equipment_id,
        job_number="PENDING",  # Auto-replaced by Postgres trigger
        trade=req.trade,
        job_type="service",
        priority=req.priority or "routine",
        status="scheduled",
        reported_problem=req.reported_problem,
        source="portal"
    )
    db.add(job)
    db.flush()
    
    # Create initial job status history
    hist = JobStatusHistory(
        id=f"jsh_{ulid.new()}",
        company_id=customer.company_id,
        job_id=job_id,
        from_status=None,
        to_status="scheduled",
        changed_by=db_user_id,
        note="Customer service request submitted via self-service portal"
    )
    db.add(hist)
    db.commit()
    db.refresh(job)
    
    return {
        "id": job.id,
        "job_number": job.job_number,
        "trade": job.trade,
        "status": job.status,
        "reported_problem": job.reported_problem,
        "created_at": job.created_at.isoformat()
    }

@router.post("/requests/{job_id}/photos/presign")
def presign_request_photo(
    job_id: str,
    req: PhotoPresignRequest,
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Generate S3 presigned URL for customer photo upload, scoped to customer's own job request"""
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .where(Job.customer_id == customer_id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job request not found")
        
    photo_ulid = ulid.new()
    s3_key = f"{job.company_id}/{job_id}/{req.photo_type}/{photo_ulid}.jpg"
    
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
            tags = f"Environment={env}&company_id={job.company_id}&job_id={job_id}&photo_type={req.photo_type}"
            
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
            logger.warning(f"Error generating customer presigned URL: {e}")
            
    # Mock upload URL in local environments
    api_url = os.getenv("API_URL", "http://localhost:8000")
    upload_url = f"{api_url}/mock-s3-upload/{s3_key}"
    return {
        "upload_url": upload_url,
        "s3_key": s3_key,
        "headers": {"Content-Type": "image/jpeg"}
    }

@router.post("/requests/{job_id}/photos", status_code=status.HTTP_201_CREATED)
def register_request_photo(
    job_id: str,
    req: PhotoRegisterRequest,
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Register customer photo metadata after S3 upload, scoped to customer's own job request"""
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .where(Job.customer_id == customer_id)
        .where(Job.deleted_at.is_(None))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job request not found")
        
    photo = JobPhoto(
        id=f"photo_{ulid.new()}",
        company_id=job.company_id,
        job_id=job_id,
        tech_id="system",  # System-registered or customer-registered
        photo_type=req.photo_type,
        s3_key=req.s3_key,
        cdn_url=req.cdn_url,
        caption=req.caption,
        file_size_bytes=req.file_size_bytes,
        mime_type=req.mime_type
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    
    return {
        "id": photo.id,
        "photo_type": photo.photo_type,
        "cdn_url": photo.cdn_url,
        "caption": photo.caption,
        "taken_at": photo.taken_at.isoformat()
    }

@router.get("/membership")
def get_customer_membership(
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Get active or inactive membership details for this customer"""
    membership = db.scalar(
        select(Membership)
        .where(Membership.customer_id == customer_id)
        .where(Membership.status == "active")
        .order_by(Membership.enrolled_at.desc())
        .limit(1)
    )
    
    if not membership:
        # Check if there are active plans available for enrollment
        customer = db.scalar(select(Customer).where(Customer.id == customer_id))
        plans = db.scalars(
            select(MembershipPlan)
            .where(MembershipPlan.company_id == customer.company_id)
            .where(MembershipPlan.is_active == True)
        ).all()
        
        return {
            "status": "none",
            "available_plans": [{
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "monthly_price_cents": p.monthly_price_cents,
                "annual_price_cents": p.annual_price_cents,
                "labor_discount_pct": float(p.labor_discount_pct),
                "parts_discount_pct": float(p.parts_discount_pct),
                "priority_scheduling": p.priority_scheduling
            } for p in plans]
        }
        
    plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == membership.plan_id))
    return {
        "status": "active",
        "membership_id": membership.id,
        "billing_cadence": membership.billing_cadence,
        "current_period_start": membership.current_period_start.isoformat(),
        "current_period_end": membership.current_period_end.isoformat(),
        "enrolled_at": membership.enrolled_at.isoformat(),
        "next_renewal_at": membership.next_renewal_at.isoformat() if membership.next_renewal_at else None,
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "description": plan.description,
            "labor_discount_pct": float(plan.labor_discount_pct),
            "parts_discount_pct": float(plan.parts_discount_pct),
            "priority_scheduling": plan.priority_scheduling
        }
    }

@router.post("/membership/enroll")
def enroll_customer_membership(
    req: MembershipEnrollRequest,
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Enroll the customer in a membership plan (simulated mock subscription)"""
    customer = db.scalar(select(Customer).where(Customer.id == customer_id))
    plan = db.scalar(
        select(MembershipPlan)
        .where(MembershipPlan.id == req.plan_id)
        .where(MembershipPlan.company_id == customer.company_id)
    )
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Membership plan not found or inactive")
        
    # Check if already has active membership
    existing = db.scalar(
        select(Membership)
        .where(Membership.customer_id == customer_id)
        .where(Membership.status == "active")
    )
    if existing:
        raise HTTPException(status_code=400, detail="Customer already has an active membership")
        
    now = datetime.now(timezone.utc)
    next_renewal = now + (timedelta(days=365) if req.billing_cadence == "annual" else timedelta(days=30))
    
    membership = Membership(
        id=f"mem_{ulid.new()}",
        company_id=customer.company_id,
        customer_id=customer_id,
        plan_id=req.plan_id,
        status="active",
        billing_cadence=req.billing_cadence,
        current_period_start=now,
        current_period_end=next_renewal,
        enrolled_by="customer",
        enrolled_at=now,
        next_renewal_at=next_renewal,
        stripe_subscription_id=f"sub_mock_{secrets.token_hex(8)}",
        stripe_customer_id=f"cus_mock_{secrets.token_hex(8)}"
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    
    return {
        "status": "active",
        "membership_id": membership.id,
        "billing_cadence": membership.billing_cadence,
        "plan_name": plan.name
    }

@router.get("/loyalty")
def get_customer_loyalty(
    customer_id: str = Depends(check_customer_auth),
    db: Session = Depends(get_portal_db)
):
    """Retrieve loyalty points balance and transaction history"""
    balance_view = db.scalar(
        select(LoyaltyBalanceView)
        .where(LoyaltyBalanceView.customer_id == customer_id)
    )
    
    balance = balance_view.balance if balance_view else 0
    lifetime_earned = balance_view.lifetime_earned if balance_view else 0
    
    # Get transaction history
    account = db.scalar(
        select(LoyaltyAccount)
        .where(LoyaltyAccount.customer_id == customer_id)
    )
    ledger_entries = []
    if account:
        ledger_entries = db.scalars(
            select(LoyaltyLedger)
            .where(LoyaltyLedger.account_id == account.id)
            .order_by(LoyaltyLedger.created_at.desc())
        ).all()
        
    return {
        "balance": balance,
        "lifetime_earned": lifetime_earned,
        "history": [{
            "id": entry.id,
            "entry_type": entry.entry_type,
            "points": entry.points,
            "description": entry.description,
            "created_at": entry.created_at.isoformat()
        } for entry in ledger_entries]
    }
