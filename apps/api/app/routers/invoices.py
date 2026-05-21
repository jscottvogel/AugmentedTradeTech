import os
import logging
import ulid
import boto3
import math
import stripe
import json
import secrets
import base64
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete, and_, text, func

from apps.api.app.core.database import get_db, set_rls_context
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.job import Job, JobStatusHistory
from apps.api.app.models.customer import Customer
from apps.api.app.models.membership import Membership, MembershipPlan
from apps.api.app.models.company import Company
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger, LoyaltyBalanceView
from apps.api.app.models.user import User
from apps.api.app.models.sync import SyncQueue
from apps.api.app.routers.auth import send_ses_email
from apps.api.app.services.loyalty import earn_loyalty_points

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoices", tags=["invoices"])
webhook_router = APIRouter(tags=["webhooks"])

# --- Request Schemas ---

class SignatureSaveRequest(BaseModel):
    signature_base64: str

class ManualPaymentRequest(BaseModel):
    payment_method: str
    notes: Optional[str] = None

class DraftInvoiceRequest(BaseModel):
    redeem_points: Optional[int] = 0


class InvoiceUpdateRequest(BaseModel):
    due_date: Optional[date] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    customer_signature_url: Optional[str] = None
    signed_at: Optional[datetime] = None
    tax_rate_bps: Optional[int] = None
    redeem_points: Optional[int] = None
    status: Optional[str] = None
    payment_method: Optional[str] = "card_present"

class LineItemCreateRequest(BaseModel):
    line_type: str  # labor | part | fee
    description: str
    quantity: float
    unit_price_cents: int
    is_taxable: Optional[bool] = True
    discount_pct: Optional[float] = 0.0
    discount_reason: Optional[str] = None

class LineItemUpdateRequest(BaseModel):
    line_type: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price_cents: Optional[int] = None
    is_taxable: Optional[bool] = None
    discount_pct: Optional[float] = None
    discount_reason: Optional[str] = None

# --- Helper Functions ---

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

def send_invoice_email(email: str, invoice_number: str, invoice_url: str, total_dollars: float) -> bool:
    subject = f"Invoice {invoice_number} from Augmented Trade Tech"
    body_text = f"Hello,\n\nYour invoice {invoice_number} is ready. Total amount: ${total_dollars:.2f}.\n\nYou can view and pay it here:\n\n{invoice_url}\n\nThank you for your business!"
    body_html = f"""<html>
    <body>
      <h3>Augmented Trade Tech</h3>
      <p>Your invoice <strong>{invoice_number}</strong> is ready.</p>
      <p>Total amount: <strong>${total_dollars:.2f}</strong></p>
      <p><a href="{invoice_url}"><strong>View & Pay Invoice</strong></a></p>
      <br/>
      <p>Thank you for your business!</p>
    </body>
    </html>"""
    
    if os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID"):
        print(f"\n[LOCAL DEV] Sending Invoice Email to {email}:\n{invoice_url}\n")
        return True
        
    try:
        ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sender = os.getenv("SES_SENDER_EMAIL", "noreply@augmentedtradetech.com")
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body_text},
                    "Html": {"Data": body_html}
                }
            }
        )
        return True
    except Exception as e:
        print(f"Error sending invoice email via SES: {e}")
        return False

def send_renewal_email(email: str, customer_name: str, plan_name: str, renewal_date: str, company_name: str) -> bool:
    subject = f"Your Membership has Renewed! - {company_name}"
    body_text = f"Hello {customer_name},\n\nYour membership '{plan_name}' has successfully renewed! Your next renewal date is {renewal_date}.\n\nThank you for your business!"
    body_html = f"""<html>
    <body>
      <h3>{company_name}</h3>
      <p>Hello <strong>{customer_name}</strong>,</p>
      <p>Your membership <strong>{plan_name}</strong> has successfully renewed!</p>
      <p>Your next renewal date is: <strong>{renewal_date}</strong></p>
      <br/>
      <p>Thank you for your business!</p>
    </body>
    </html>"""
    
    if os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID"):
        print(f"\n[LOCAL DEV] Sending Renewal Confirmation Email to {email}:\n{plan_name} renewed.\n")
        return True
        
    try:
        ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sender = os.getenv("SES_SENDER_EMAIL", "noreply@augmentedtradetech.com")
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body_text},
                    "Html": {"Data": body_html}
                }
            }
        )
        return True
    except Exception as e:
        logger.error(f"Error sending renewal email via SES: {e}")
        return False

def recalculate_invoice(db: Session, invoice: Invoice):
    subtotal_cents = 0
    discount_cents = 0
    
    # Query LoyaltyLedger for any redeem points on this invoice
    redeem_entry = db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == invoice.id)
        .where(LoyaltyLedger.entry_type == "redeem")
        .where(LoyaltyLedger.voided_at.is_(None))
    )
    redeem_points = redeem_entry.points if redeem_entry else 0
    points_discount_cents = redeem_points  # 1 point = 1 cent
    
    # Keep the loyalty points redemption line item price in sync with the ledger
    for item in invoice.line_items:
        if item.line_type == "fee" and item.description == "Loyalty Points Redemption":
            if item.unit_price_cents != -points_discount_cents:
                item.unit_price_cents = -points_discount_cents

    for item in invoice.line_items:
        # Exclude Loyalty Points Redemption line item from subtotal_cents to prevent double-discounting or tax reduction
        if item.line_type == "fee" and item.description == "Loyalty Points Redemption":
            continue
        # total_cents computed column on DB
        item_total = int(round(float(item.quantity) * item.unit_price_cents))
        item_discount = int(round(item_total * float(item.discount_pct or 0) / 100))
        
        subtotal_cents += item_total
        discount_cents += item_discount
        
    discount_cents += points_discount_cents
    
    tax_rate_bps = invoice.tax_rate_bps or 0
    tax_cents = int(round(subtotal_cents * tax_rate_bps / 10000))
    
    invoice.subtotal_cents = subtotal_cents
    invoice.tax_cents = tax_cents
    invoice.discount_cents = discount_cents
    invoice.total_cents = max(0, subtotal_cents + tax_cents - discount_cents)

def serialize_invoice(invoice: Invoice, db: Session) -> Dict[str, Any]:
    items = []
    for item in invoice.line_items:
        items.append({
            "id": item.id,
            "line_type": item.line_type,
            "description": item.description,
            "quantity": float(item.quantity),
            "unit_price_cents": item.unit_price_cents,
            "total_cents": item.total_cents,
            "is_taxable": item.is_taxable,
            "discount_pct": float(item.discount_pct),
            "discount_reason": item.discount_reason
        })
        
    loyalty_account = db.scalar(
        select(LoyaltyAccount)
        .where(LoyaltyAccount.customer_id == invoice.customer_id)
    )
    
    available_balance = 0
    if loyalty_account:
        balance_view = db.scalar(
            select(LoyaltyBalanceView)
            .where(LoyaltyBalanceView.account_id == loyalty_account.id)
        )
        if balance_view:
            available_balance = balance_view.balance or 0
            
    redeemed_points = db.scalar(
        select(func.sum(LoyaltyLedger.points))
        .where(LoyaltyLedger.invoice_id == invoice.id)
        .where(LoyaltyLedger.entry_type == "redeem")
        .where(LoyaltyLedger.voided_at.is_(None))
    ) or 0
    
    active_membership = db.scalar(
        select(Membership)
        .where(Membership.customer_id == invoice.customer_id)
        .where(Membership.status == "active")
    )
    
    member_discount_applied = False
    labor_discount_pct = 0
    parts_discount_pct = 0
    if active_membership:
        plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == active_membership.plan_id))
        if plan:
            member_discount_applied = True
            labor_discount_pct = float(plan.labor_discount_pct or 0)
            parts_discount_pct = float(plan.parts_discount_pct or 0)
            
    return {
        "id": invoice.id,
        "job_id": invoice.job_id,
        "customer_id": invoice.customer_id,
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
        "sent_at": invoice.sent_at.isoformat() if invoice.sent_at else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "voided_at": invoice.voided_at.isoformat() if invoice.voided_at else None,
        "line_items": items,
        "loyalty": {
            "available_balance": available_balance,
            "redeemed_points": int(redeemed_points),
            "redeemed_cents": int(redeemed_points) * 1
        },
        "membership": {
            "applied": member_discount_applied,
            "labor_discount_pct": labor_discount_pct,
            "parts_discount_pct": parts_discount_pct
        }
    }

def create_draft_invoice_from_job(db: Session, job: Job, user_id: str) -> Invoice:
    existing = db.scalar(select(Invoice).where(Invoice.job_id == job.id))
    if existing:
        return existing

    company = db.scalar(select(Company).where(Company.id == job.company_id))
    tax_rate_bps = company.tax_rate_bps if company else 0

    active_membership = db.scalar(
        select(Membership)
        .where(Membership.customer_id == job.customer_id)
        .where(Membership.status == "active")
    )
    labor_discount_pct = 0
    parts_discount_pct = 0
    membership_id = None
    if active_membership:
        membership_id = active_membership.id
        plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == active_membership.plan_id))
        if plan:
            labor_discount_pct = float(plan.labor_discount_pct or 0)
            parts_discount_pct = float(plan.parts_discount_pct or 0)

    invoice_id = f"inv_{ulid.new()}"
    invoice = Invoice(
        id=invoice_id,
        company_id=job.company_id,
        job_id=job.id,
        customer_id=job.customer_id,
        invoice_number="PENDING",
        status="draft",
        tax_rate_bps=tax_rate_bps,
        subtotal_cents=0,
        tax_cents=0,
        discount_cents=0,
        total_cents=0,
        amount_paid_cents=0,
        due_date=date.today() + timedelta(days=30),
        payment_terms="due_on_receipt",
        created_by=user_id,
        updated_by=user_id
    )

    year = datetime.now().year
    count = db.scalar(select(func.count(Invoice.id)).where(Invoice.company_id == job.company_id))
    while True:
        inv_num = f"INV-{year}-{count + 1:05d}"
        exists = db.scalar(select(Invoice.id).where(Invoice.company_id == job.company_id, Invoice.invoice_number == inv_num))
        if not exists:
            invoice.invoice_number = inv_num
            break
        count += 1

    db.add(invoice)
    db.flush()

    draft_items = []
    if job.ai_diagnosis:
        if "draft_line_items" in job.ai_diagnosis:
            draft_items = job.ai_diagnosis["draft_line_items"]
        elif "draft_invoice" in job.ai_diagnosis and "line_items" in job.ai_diagnosis["draft_invoice"]:
            draft_items = job.ai_diagnosis["draft_invoice"]["line_items"]

    for idx, item in enumerate(draft_items):
        desc = item.get("description", "")
        qty = item.get("quantity", 1)
        price_cents = item.get("unit_price_cents", 0)

        desc_lower = desc.lower()
        if "labor" in desc_lower:
            ltype = "labor"
            discount_pct = labor_discount_pct
        elif "fee" in desc_lower:
            ltype = "fee"
            discount_pct = 0
        else:
            ltype = "part"
            discount_pct = parts_discount_pct

        reason = "member_discount" if discount_pct > 0 else None

        line_item = InvoiceLineItem(
            id=f"ili_{ulid.new()}",
            company_id=job.company_id,
            invoice_id=invoice.id,
            line_type=ltype,
            description=desc,
            quantity=qty,
            unit_price_cents=price_cents,
            is_taxable=True,
            discount_pct=discount_pct,
            discount_reason=reason,
            sort_order=idx,
            created_by=user_id
        )
        db.add(line_item)

    db.flush()

    if membership_id and not job.membership_id:
        job.membership_id = membership_id
        db.add(job)

    recalculate_invoice(db, invoice)
    db.flush()
    return invoice

def trigger_quickbooks_sync(db: Session, invoice: Invoice, user_id: str | None = None):
    if user_id == "system":
        user_id = None
    if not user_id:
        user_id = invoice.created_by or invoice.updated_by
    if not user_id:
        user_id = db.scalar(
            select(User.id)
            .where(User.company_id == invoice.company_id)
            .limit(1)
        )
    if user_id:
        idempotency_key = f"qbo_sync_{invoice.id}"
        existing = db.scalar(select(SyncQueue).where(SyncQueue.idempotency_key == idempotency_key))
        if not existing:
            sync_entry = SyncQueue(
                id=f"sy_{ulid.new()}",
                company_id=invoice.company_id,
                user_id=user_id,
                entity_type="invoice",
                entity_id=invoice.id,
                operation="create",
                payload={"invoice_id": invoice.id, "invoice_number": invoice.invoice_number},
                client_timestamp=datetime.now(timezone.utc),
                idempotency_key=idempotency_key,
                status="pending"
            )
            db.add(sync_entry)
            db.flush()

    queue_url = None
    try:
        from sst import Resource
        if hasattr(Resource, "NotificationQueue"):
            queue_url = Resource.NotificationQueue.url
        elif hasattr(Resource, "notification-queue"):
            queue_url = Resource["notification-queue"].url
        elif "NotificationQueue" in Resource:
            queue_url = Resource["NotificationQueue"].url
        elif "notification-queue" in Resource:
            queue_url = Resource["notification-queue"].url
    except Exception:
        pass

    payload = {
        "action": "quickbooks_sync",
        "invoice_id": invoice.id,
        "company_id": invoice.company_id
    }
    if queue_url:
        try:
            sqs = boto3.client("sqs")
            sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
            logger.info(f"QuickBooks sync request for invoice {invoice.id} enqueued to SQS successfully.")
        except Exception as sqs_err:
            logger.error(f"Failed to queue QBO sync via SQS: {sqs_err}")
    else:
        logger.info(f"[LOCAL] Simulated QBO sync SQS message: {payload}")

def send_payment_receipt_notifications(db: Session, invoice: Invoice, amount_cents: int):
    customer = db.scalar(select(Customer).where(Customer.id == invoice.customer_id))
    if not customer:
        return
    amount_dollars = amount_cents / 100.0
    subject = f"Receipt for Invoice {invoice.invoice_number}"
    body_text = f"Hello {customer.first_name},\n\nThank you for your payment of ${amount_dollars:.2f} for Invoice {invoice.invoice_number}.\n\nYour payment has been successfully processed.\n\nThank you for your business!"
    body_html = f"""<html>
    <body>
      <h3>Augmented Trade Tech</h3>
      <p>Hello {customer.first_name},</p>
      <p>Thank you for your payment of <strong>${amount_dollars:.2f}</strong> for Invoice <strong>{invoice.invoice_number}</strong>.</p>
      <p>Your payment has been successfully processed.</p>
      <br/>
      <p>Thank you for your business!</p>
    </body>
    </html>"""

    # Send SMS
    sms_message = f"Augmented Trade Tech: Thank you for your payment of ${amount_dollars:.2f} for Invoice {invoice.invoice_number}. Your receipt has been sent to your email."
    publish_sns_notification(customer.phone, sms_message)

    # Send Email
    if customer.email:
        if os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID"):
            print(f"\n[LOCAL DEV] Sending Receipt Email to {customer.email}:\n{body_text}\n")
            return
        try:
            ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
            sender = os.getenv("SES_SENDER_EMAIL", "noreply@augmentedtradetech.com")
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
            logger.warning(f"Error sending receipt email via SES: {e}")

def process_successful_payment(
    db: Session,
    invoice: Invoice,
    payment_method: str,
    amount_cents: int,
    stripe_payment_intent_id: str | None = None,
    stripe_charge_id: str | None = None,
    user_id: str | None = None
):
    # Avoid duplicate processing if already paid
    if invoice.status == "paid":
        logger.info(f"Invoice {invoice.id} is already paid. Skipping payment processing.")
        return

    db_user_id = user_id if (user_id and user_id not in ["system", "customer"]) else None
    if not db_user_id:
        db_user_id = db.scalar(
            select(User.id)
            .where(User.company_id == invoice.company_id)
            .limit(1)
        )

    # Update Invoice Status
    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    invoice.amount_paid_cents = invoice.total_cents

    # Record or Update Payment
    payment = None
    if stripe_payment_intent_id:
        payment = db.scalar(
            select(Payment)
            .where(Payment.stripe_payment_intent_id == stripe_payment_intent_id)
        )
    if payment:
        payment.status = "succeeded"
        payment.stripe_charge_id = stripe_charge_id
        payment.amount_cents = amount_cents
        payment.updated_at = datetime.now(timezone.utc)
        if db_user_id:
            payment.updated_by = db_user_id
    else:
        payment = Payment(
            id=f"pay_{ulid.new()}",
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            amount_cents=amount_cents,
            payment_method=payment_method,
            status="succeeded",
            stripe_payment_intent_id=stripe_payment_intent_id,
            stripe_charge_id=stripe_charge_id,
            collected_by=db_user_id,
            collected_at=datetime.now(timezone.utc),
            created_by=db_user_id,
            updated_by=db_user_id
        )
        db.add(payment)

    # Transition Job to paid
    job = db.scalar(select(Job).where(Job.id == invoice.job_id))
    if job and job.status in ["invoiced", "completed"]:
        job.status = "paid"
        hist = JobStatusHistory(
            id=f"jsh_{ulid.new()}",
            company_id=invoice.company_id,
            job_id=job.id,
            from_status=job.status,
            to_status="paid",
            changed_by=db_user_id,
            note="Payment successfully processed, job status changed to paid"
        )
        db.add(hist)

    # Credit loyalty points to customer
    earn_loyalty_points(
        db=db,
        customer_id=invoice.customer_id,
        job_id=invoice.job_id,
        invoice_id=invoice.id,
        amount_cents=amount_cents
    )
    db.flush()

    # Trigger QuickBooks Sync
    trigger_quickbooks_sync(db, invoice, db_user_id)

    # Send SES Email & SNS SMS Receipts
    send_payment_receipt_notifications(db, invoice, amount_cents)

# --- Router Endpoints ---

@router.post("/jobs/{job_id}/invoice/draft", status_code=status.HTTP_201_CREATED)
def draft_invoice_endpoint(job_id: str, req: DraftInvoiceRequest, request: Request, db: Session = Depends(get_db)):
    """Generate a draft invoice from a job's diagnostic info"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    job = db.scalar(select(Job).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    invoice = create_draft_invoice_from_job(db, job, request.state.user_id)
    
    # Handle points redemption if requested
    if req.redeem_points and req.redeem_points > 0:
        loyalty_account = db.scalar(
            select(LoyaltyAccount)
            .where(LoyaltyAccount.customer_id == invoice.customer_id)
        )
        if not loyalty_account:
            loyalty_account = LoyaltyAccount(
                id=f"loy_{ulid.new()}",
                company_id=invoice.company_id,
                customer_id=invoice.customer_id,
                is_active=True,
                created_by=request.state.user_id
            )
            db.add(loyalty_account)
            db.flush()
            
        balance_view = db.scalar(
            select(LoyaltyBalanceView)
            .where(LoyaltyBalanceView.account_id == loyalty_account.id)
        )
        available = balance_view.balance if balance_view else 0
        if req.redeem_points > available:
            raise HTTPException(status_code=400, detail="Insufficient loyalty points balance")
            
        # Write ledger entry
        ledger_entry = LoyaltyLedger(
            id=f"tx_{ulid.new()}",
            company_id=invoice.company_id,
            account_id=loyalty_account.id,
            entry_type="redeem",
            points=req.redeem_points,
            job_id=invoice.job_id,
            invoice_id=invoice.id,
            description=f"Redeemed {req.redeem_points} loyalty points on invoice {invoice.invoice_number}",
            created_by=request.state.user_id
        )
        db.add(ledger_entry)
        db.flush()
        recalculate_invoice(db, invoice)
        
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.get("/{id}")
def get_invoice_endpoint(id: str, request: Request, db: Session = Depends(get_db)):
    """Retrieve an invoice by ID"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    return serialize_invoice(invoice, db)

@router.put("/{id}")
def update_invoice_endpoint(id: str, req: InvoiceUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Update fields on an invoice, including loyalty points or marking as paid"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Apply updates
    if req.due_date is not None:
        invoice.due_date = req.due_date
    if req.payment_terms is not None:
        invoice.payment_terms = req.payment_terms
    if req.notes is not None:
        invoice.notes = req.notes
    if req.customer_signature_url is not None:
        invoice.customer_signature_url = req.customer_signature_url
    if req.signed_at is not None:
        invoice.signed_at = req.signed_at
    if req.tax_rate_bps is not None:
        invoice.tax_rate_bps = req.tax_rate_bps
        
    # Handle loyalty points redemption updates
    if req.redeem_points is not None:
        loyalty_account = db.scalar(
            select(LoyaltyAccount)
            .where(LoyaltyAccount.customer_id == invoice.customer_id)
        )
        if not loyalty_account:
            loyalty_account = LoyaltyAccount(
                id=f"loy_{ulid.new()}",
                company_id=invoice.company_id,
                customer_id=invoice.customer_id,
                is_active=True,
                created_by=request.state.user_id
            )
            db.add(loyalty_account)
            db.flush()
            
        balance_view = db.scalar(
            select(LoyaltyBalanceView)
            .where(LoyaltyBalanceView.account_id == loyalty_account.id)
        )
        
        # Calculate available points excluding any current redemptions on this invoice
        current_redeemed = db.scalar(
            select(func.sum(LoyaltyLedger.points))
            .where(LoyaltyLedger.invoice_id == invoice.id)
            .where(LoyaltyLedger.entry_type == "redeem")
            .where(LoyaltyLedger.voided_at.is_(None))
        ) or 0
        
        available = (balance_view.balance if balance_view else 0) + current_redeemed
        if req.redeem_points > available:
            raise HTTPException(status_code=400, detail="Insufficient loyalty points balance")
            
        # Delete previous redeem ledger entry
        db.execute(
            delete(LoyaltyLedger)
            .where(LoyaltyLedger.invoice_id == invoice.id)
            .where(LoyaltyLedger.entry_type == "redeem")
        )
        db.flush()
        
        if req.redeem_points > 0:
            ledger_entry = LoyaltyLedger(
                id=f"tx_{ulid.new()}",
                company_id=invoice.company_id,
                account_id=loyalty_account.id,
                entry_type="redeem",
                points=req.redeem_points,
                job_id=invoice.job_id,
                invoice_id=invoice.id,
                description=f"Redeemed {req.redeem_points} loyalty points on invoice {invoice.invoice_number}",
                idempotency_key=f"redeem-{invoice.id}",
                created_by=request.state.user_id
            )
            db.add(ledger_entry)
            db.flush()

        # Update or insert or delete the Loyalty Points Redemption line item
        redeem_item = db.scalar(
            select(InvoiceLineItem)
            .where(InvoiceLineItem.invoice_id == invoice.id)
            .where(InvoiceLineItem.line_type == "fee")
            .where(InvoiceLineItem.description == "Loyalty Points Redemption")
        )
        if req.redeem_points > 0:
            if redeem_item:
                redeem_item.unit_price_cents = -req.redeem_points
            else:
                sort_order = db.scalar(
                    select(func.count(InvoiceLineItem.id)).where(InvoiceLineItem.invoice_id == invoice.id)
                ) or 0
                redeem_item = InvoiceLineItem(
                    id=f"ili_{ulid.new()}",
                    company_id=invoice.company_id,
                    invoice_id=invoice.id,
                    line_type="fee",
                    description="Loyalty Points Redemption",
                    quantity=1.00,
                    unit_price_cents=-req.redeem_points,
                    is_taxable=False,
                    sort_order=sort_order,
                    created_by=request.state.user_id
                )
                db.add(redeem_item)
        else:
            if redeem_item:
                db.delete(redeem_item)
        db.flush()
            
    # Handle status transition (specifically for marking invoice as paid)
    if req.status is not None:
        if req.status == "paid" and invoice.status != "paid":
            invoice.status = "paid"
            invoice.paid_at = datetime.now(timezone.utc)
            invoice.amount_paid_cents = invoice.total_cents
            
            # Record Payment entry
            payment = Payment(
                id=f"pay_{ulid.new()}",
                company_id=invoice.company_id,
                invoice_id=invoice.id,
                amount_cents=invoice.total_cents,
                payment_method=req.payment_method or "card_present",
                status="succeeded",
                collected_by=request.state.user_id,
                collected_at=datetime.now(timezone.utc),
                created_by=request.state.user_id,
                updated_by=request.state.user_id
            )
            db.add(payment)

            # Credit loyalty points to customer
            earn_loyalty_points(
                db=db,
                customer_id=invoice.customer_id,
                job_id=invoice.job_id,
                invoice_id=invoice.id,
                amount_cents=invoice.total_cents
            )
            
            # Transition Job to paid
            job = db.scalar(select(Job).where(Job.id == invoice.job_id))
            if job and job.status == "invoiced":
                job.status = "paid"
                hist = JobStatusHistory(
                    id=f"jsh_{ulid.new()}",
                    company_id=invoice.company_id,
                    job_id=job.id,
                    from_status="invoiced",
                    to_status="paid",
                    changed_by=request.state.user_id,
                    note="Payment collected, job marked paid"
                )
                db.add(hist)
        elif req.status == "void":
            check_permission(request, ["company_admin"])
            invoice.status = "void"
            invoice.voided_at = datetime.now(timezone.utc)
            
            # Void any redeemed points
            db.execute(
                update(LoyaltyLedger)
                .where(LoyaltyLedger.invoice_id == invoice.id)
                .where(LoyaltyLedger.entry_type == "redeem")
                .values(voided_at=datetime.now(timezone.utc), voided_by=request.state.user_id)
            )
        else:
            invoice.status = req.status

    recalculate_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.post("/{id}/line-items", status_code=status.HTTP_201_CREATED)
def add_line_item_endpoint(id: str, req: LineItemCreateRequest, request: Request, db: Session = Depends(get_db)):
    """Add a line item to the invoice"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    sort_order = db.scalar(
        select(func.count(InvoiceLineItem.id)).where(InvoiceLineItem.invoice_id == invoice.id)
    ) or 0
    
    line_item = InvoiceLineItem(
        id=f"ili_{ulid.new()}",
        company_id=invoice.company_id,
        invoice_id=invoice.id,
        line_type=req.line_type,
        description=req.description,
        quantity=req.quantity,
        unit_price_cents=req.unit_price_cents,
        is_taxable=req.is_taxable,
        discount_pct=req.discount_pct or 0.0,
        discount_reason=req.discount_reason,
        sort_order=sort_order,
        created_by=request.state.user_id
    )
    db.add(line_item)
    db.flush()
    
    recalculate_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.put("/{id}/line-items/{lid}")
def update_line_item_endpoint(id: str, lid: str, req: LineItemUpdateRequest, request: Request, db: Session = Depends(get_db)):
    """Update a specific line item on an invoice"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    line_item = db.scalar(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == id)
        .where(InvoiceLineItem.id == lid)
    )
    if not line_item:
        raise HTTPException(status_code=404, detail="Line item not found")
        
    if req.line_type is not None:
        line_item.line_type = req.line_type
    if req.description is not None:
        line_item.description = req.description
    if req.quantity is not None:
        line_item.quantity = req.quantity
    if req.unit_price_cents is not None:
        line_item.unit_price_cents = req.unit_price_cents
    if req.is_taxable is not None:
        line_item.is_taxable = req.is_taxable
    if req.discount_pct is not None:
        line_item.discount_pct = req.discount_pct
    if req.discount_reason is not None:
        line_item.discount_reason = req.discount_reason
        
    db.flush()
    recalculate_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.delete("/{id}/line-items/{lid}")
def remove_line_item_endpoint(id: str, lid: str, request: Request, db: Session = Depends(get_db)):
    """Remove a line item from the invoice"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    line_item = db.scalar(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == id)
        .where(InvoiceLineItem.id == lid)
    )
    if not line_item:
        raise HTTPException(status_code=404, detail="Line item not found")
        
    db.delete(line_item)
    db.flush()
    
    recalculate_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.post("/{id}/send")
def send_invoice_endpoint(id: str, request: Request, db: Session = Depends(get_db)):
    """Send the invoice to the customer via Email & SMS"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    invoice.status = "sent"
    invoice.sent_at = datetime.now(timezone.utc)
    
    job = db.scalar(select(Job).where(Job.id == invoice.job_id))
    if job and job.status == "completed":
        job.status = "invoiced"
        hist = JobStatusHistory(
            id=f"jsh_{ulid.new()}",
            company_id=invoice.company_id,
            job_id=job.id,
            from_status="completed",
            to_status="invoiced",
            changed_by=request.state.user_id,
            note=f"Invoice {invoice.invoice_number} sent to customer"
        )
        db.add(hist)
        
    customer = db.scalar(select(Customer).where(Customer.id == invoice.customer_id))
    if customer:
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        invoice_url = f"{frontend_url}/app/jobs/{job.id}/invoice" if job else f"{frontend_url}/invoices/{invoice.id}"
        total_dollars = invoice.total_cents / 100.0
        
        # SMS Notification
        message = f"Augmented Trade Tech: Your invoice {invoice.invoice_number} is ready. Total: ${total_dollars:.2f}. View here: {invoice_url}"
        publish_sns_notification(customer.phone, message)
        
        # Email Notification
        if customer.email:
            send_invoice_email(customer.email, invoice.invoice_number, invoice_url, total_dollars)
            
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.post("/{id}/void")
def void_invoice_endpoint(id: str, request: Request, db: Session = Depends(get_db)):
    """Void the invoice (admin only)"""
    check_permission(request, ["company_admin"])
    
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    invoice.status = "void"
    invoice.voided_at = datetime.now(timezone.utc)
    
    # Void points redeemed
    db.execute(
        update(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == invoice.id)
        .where(LoyaltyLedger.entry_type == "redeem")
        .values(voided_at=datetime.now(timezone.utc), voided_by=request.state.user_id)
    )
    
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.post("/{id}/signature")
def save_signature_endpoint(id: str, req: SignatureSaveRequest, request: Request, db: Session = Depends(get_db)):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Decode signature base64
    b64_data = req.signature_base64
    if "," in b64_data:
        b64_data = b64_data.split(",")[1]
    try:
        image_data = base64.b64decode(b64_data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 signature data")

    # S3 Upload
    s3_key = f"signatures/{invoice.id}_{ulid.new()}.png"
    bucket_name = None
    media_domain = None
    try:
        from sst import Resource
        if hasattr(Resource, "MediaBucket"):
            bucket_name = Resource.MediaBucket.name
            media_domain = getattr(Resource.MediaBucket, "domain", None)
    except Exception:
        pass

    if bucket_name:
        try:
            s3 = boto3.client("s3")
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=image_data,
                ContentType="image/png"
            )
            if media_domain:
                upload_url = f"https://{media_domain}/{s3_key}"
            else:
                upload_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
        except Exception as e:
            logger.warning(f"S3 signature upload failed: {e}")
            api_url = os.getenv("API_URL", "http://localhost:8000")
            upload_url = f"{api_url}/mock-s3-upload/{s3_key}"
    else:
        api_url = os.getenv("API_URL", "http://localhost:8000")
        upload_url = f"{api_url}/mock-s3-upload/{s3_key}"

    invoice.customer_signature_url = upload_url
    invoice.signed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@router.post("/{id}/pay/intent")
def create_payment_intent_endpoint(id: str, request: Request, db: Session = Depends(get_db)):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    company = db.scalar(select(Company).where(Company.id == invoice.company_id))
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    is_mock = (
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )

    if is_mock:
        mock_intent_id = f"pi_mock_{secrets.token_hex(8)}"
        payment = Payment(
            id=f"pay_{ulid.new()}",
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            amount_cents=invoice.total_cents,
            payment_method="card_present",
            status="pending",
            stripe_payment_intent_id=mock_intent_id,
            created_by=request.state.user_id,
            updated_by=request.state.user_id
        )
        db.add(payment)
        db.commit()

        return {
            "client_secret": f"{mock_intent_id}_secret_{secrets.token_hex(4)}",
            "payment_intent_id": mock_intent_id,
            "status": "requires_payment_method"
        }

    try:
        stripe.api_key = stripe_key
        intent = stripe.PaymentIntent.create(
            amount=invoice.total_cents,
            currency="usd",
            stripe_account=stripe_account_id,
            metadata={
                "invoice_id": invoice.id,
                "company_id": invoice.company_id
            }
        )
        payment = Payment(
            id=f"pay_{ulid.new()}",
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            amount_cents=invoice.total_cents,
            payment_method="card_present",
            status="pending",
            stripe_payment_intent_id=intent.id,
            created_by=request.state.user_id,
            updated_by=request.state.user_id
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

@router.post("/{id}/pay/link")
def create_payment_link_endpoint(id: str, request: Request, db: Session = Depends(get_db)):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    company = db.scalar(select(Company).where(Company.id == invoice.company_id))
    stripe_account_id = company.stripe_account_id if company else None
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    is_mock = (
        not stripe_key or 
        not stripe_account_id or 
        stripe_account_id.startswith("acct_mock_")
    )

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    if is_mock:
        mock_link = f"{frontend_url}/app/jobs/{invoice.job_id}/invoice/pay?mock_payment_link=true&invoice_id={invoice.id}"
        customer = db.scalar(select(Customer).where(Customer.id == invoice.customer_id))
        if customer:
            sms_message = f"Augmented Trade Tech: Invoice {invoice.invoice_number} payment link: {mock_link}"
            publish_sns_notification(customer.phone, sms_message)
            if customer.email:
                send_invoice_email(customer.email, invoice.invoice_number, mock_link, invoice.total_cents / 100.0)

        return {"url": mock_link}

    try:
        stripe.api_key = stripe_key
        price = stripe.Price.create(
            unit_amount=invoice.total_cents,
            currency="usd",
            product_data={
                "name": f"Invoice {invoice.invoice_number}"
            },
            stripe_account=stripe_account_id
        )
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            metadata={
                "invoice_id": invoice.id,
                "company_id": invoice.company_id
            },
            stripe_account=stripe_account_id
        )

        customer = db.scalar(select(Customer).where(Customer.id == invoice.customer_id))
        if customer:
            sms_message = f"Augmented Trade Tech: Invoice {invoice.invoice_number} payment link: {payment_link.url}"
            publish_sns_notification(customer.phone, sms_message)
            if customer.email:
                send_invoice_email(customer.email, invoice.invoice_number, payment_link.url, invoice.total_cents / 100.0)

        return {"url": payment_link.url}
    except Exception as e:
        logger.error(f"Stripe PaymentLink creation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Stripe PaymentLink creation failed: {str(e)}")

@router.post("/{id}/pay/manual")
def record_manual_payment_endpoint(id: str, req: ManualPaymentRequest, request: Request, db: Session = Depends(get_db)):
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    invoice = db.scalar(select(Invoice).where(Invoice.id == id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if req.payment_method not in ["cash", "check"]:
        raise HTTPException(status_code=400, detail="Invalid manual payment method")

    process_successful_payment(
        db=db,
        invoice=invoice,
        payment_method=req.payment_method,
        amount_cents=invoice.total_cents,
        user_id=request.state.user_id
    )

    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice, db)

@webhook_router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    event = None
    if webhook_secret and sig_header:
        try:
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {e}")
    else:
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type")
    data_obj = event.get("data", {}).get("object", {})
    
    company_id = None
    metadata = data_obj.get("metadata", {})
    if metadata and "company_id" in metadata:
        company_id = metadata["company_id"]
    else:
        stripe_account = event.get("account")
        if stripe_account:
            company = db.scalar(select(Company).where(Company.stripe_account_id == stripe_account))
            if company:
                company_id = company.id

    if not company_id:
        company_id = event.get("company_id") or metadata.get("company_id")

    if not company_id:
        logger.error("Could not resolve company ID for Stripe webhook")
        return {"status": "un-routable", "message": "Company context could not be resolved"}

    set_rls_context(db, company_id, None, "system")

    if event_type == "payment_intent.succeeded":
        invoice_id = metadata.get("invoice_id")
        if not invoice_id:
            logger.warning(f"payment_intent.succeeded missed invoice_id in metadata: {data_obj.get('id')}")
            return {"status": "ignored"}
        
        invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id))
        if not invoice:
            logger.error(f"Invoice {invoice_id} not found in database for payment_intent.succeeded")
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        process_successful_payment(
            db=db,
            invoice=invoice,
            payment_method="payment_link",
            amount_cents=data_obj.get("amount", invoice.total_cents),
            stripe_payment_intent_id=data_obj.get("id"),
            stripe_charge_id=data_obj.get("latest_charge"),
            user_id="system"
        )
        db.commit()

    elif event_type == "payment_intent.payment_failed":
        pi_id = data_obj.get("id")
        payment = db.scalar(select(Payment).where(Payment.stripe_payment_intent_id == pi_id))
        if payment:
            payment.status = "failed"
            payment.updated_at = datetime.now(timezone.utc)
            db.commit()

    elif event_type == "customer.subscription.updated":
        subscription_id = data_obj.get("id")
        if subscription_id:
            membership = db.scalar(
                select(Membership)
                .where(Membership.stripe_subscription_id == subscription_id)
            )
            if membership:
                stripe_status = data_obj.get("status")
                pause_collection = data_obj.get("pause_collection")
                
                if pause_collection:
                    membership.status = "paused"
                elif stripe_status in ["active", "trialing"]:
                    membership.status = "active"
                elif stripe_status in ["past_due", "unpaid"]:
                    membership.status = "suspended"
                elif stripe_status == "canceled":
                    membership.status = "cancelled"
                    if not membership.cancelled_at:
                        membership.cancelled_at = datetime.now(timezone.utc)
                    membership.next_renewal_at = None
                
                period_start = data_obj.get("current_period_start")
                period_end = data_obj.get("current_period_end")
                if period_start:
                    membership.current_period_start = datetime.fromtimestamp(period_start, tz=timezone.utc)
                if period_end:
                    membership.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
                    if membership.status == "active":
                        membership.next_renewal_at = membership.current_period_end
                
                membership.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"Membership {membership.id} updated via customer.subscription.updated to status={membership.status}.")

    elif event_type == "customer.subscription.deleted":
        subscription_id = data_obj.get("id")
        if subscription_id:
            membership = db.scalar(
                select(Membership)
                .where(Membership.stripe_subscription_id == subscription_id)
            )
            if membership:
                membership.status = "cancelled"
                membership.cancelled_at = datetime.now(timezone.utc)
                membership.next_renewal_at = None
                membership.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"Membership {membership.id} cancelled via customer.subscription.deleted.")

    elif event_type == "invoice.payment_failed":
        subscription_id = data_obj.get("subscription")
        if subscription_id:
            membership = db.scalar(
                select(Membership)
                .where(Membership.stripe_subscription_id == subscription_id)
            )
            if membership:
                membership.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=14)
                membership.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"Membership {membership.id} set to grace period via invoice.payment_failed.")

    elif event_type == "invoice.paid":
        subscription_id = data_obj.get("subscription")
        if subscription_id:
            membership = db.scalar(
                select(Membership)
                .where(Membership.stripe_subscription_id == subscription_id)
            )
            if membership:
                db.execute(
                    text("SELECT reset_membership_period(:mem_id);"),
                    {"mem_id": membership.id}
                )
                db.commit()
                db.refresh(membership)
                
                membership.next_renewal_at = membership.current_period_end
                membership.grace_period_ends_at = None
                membership.status = "active"
                db.commit()
                
                # Fetch plan, customer and company
                plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == membership.plan_id))
                customer = db.scalar(select(Customer).where(Customer.id == membership.customer_id))
                company = db.scalar(select(Company).where(Company.id == membership.company_id))
                
                # Schedule next included visit if applicable
                if plan and plan.included_visits_count > 0:
                    db_user_id = db.scalar(
                        select(User.id)
                        .where(User.company_id == membership.company_id)
                        .limit(1)
                    )
                    job_id = f"job_{ulid.new()}"
                    trade = plan.trade if plan.trade != "both" else "hvac"
                    job = Job(
                        id=job_id,
                        company_id=membership.company_id,
                        customer_id=membership.customer_id,
                        equipment_id=None,
                        job_number="PENDING",
                        trade=trade,
                        job_type="maintenance",
                        priority="routine",
                        status="scheduled",
                        reported_problem="Membership included preventative maintenance visit",
                        dispatcher_notes=f"Auto-created from membership renewal: {plan.name}",
                        scheduled_start=None,
                        scheduled_end=None,
                        created_by=db_user_id,
                        updated_by=db_user_id,
                        membership_id=membership.id,
                        is_included_visit=True,
                        source="dispatcher"
                    )
                    db.add(job)
                    
                    hist = JobStatusHistory(
                        id=f"jsh_{ulid.new()}",
                        company_id=membership.company_id,
                        job_id=job_id,
                        from_status=None,
                        to_status="scheduled",
                        changed_by=db_user_id,
                        note="Initial auto-creation of included membership visit"
                    )
                    db.add(hist)
                    db.commit()
                    logger.info(f"Auto-created preventative maintenance visit job {job_id} for membership {membership.id}")
                
                # Send confirmation via SES and SNS
                if customer:
                    customer_name = f"{customer.first_name} {customer.last_name}"
                    plan_name = plan.name if plan else "Membership"
                    renewal_date_str = membership.next_renewal_at.strftime("%Y-%m-%d") if membership.next_renewal_at else ""
                    company_name = company.name if company else "Company"
                    
                    if customer.email:
                        send_renewal_email(customer.email, customer_name, plan_name, renewal_date_str, company_name)
                    
                    sms_message = f"{company_name}: Your membership {plan_name} has successfully renewed! Next renewal: {renewal_date_str}"
                    publish_sns_notification(customer.phone, sms_message)

                logger.info(f"Membership {membership.id} period reset successfully on invoice.paid webhook.")

    return {"status": "success"}

