import sys
import os
import json
import logging
import traceback
import ulid
from datetime import datetime, timezone
from sqlalchemy import select

# Add parent directory to sys.path to allow absolute imports in Lambda if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

import boto3
from apps.api.app.core.database import SessionLocal, set_rls_context
from apps.api.app.models.company import Company
from apps.api.app.models.invoice import Invoice
from apps.api.app.models.sync import SyncQueue
from apps.api.app.models.user import User
from apps.api.app.models.ai import AuditLog
from apps.api.app.models.customer import Customer
from apps.api.app.services.qbo import QBOClient

logger = logging.getLogger("qbo_sync_worker")

def send_failure_email(company_id, invoice_id, invoice_number, error_msg, admin_emails):
    if os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID"):
        print(f"\n[LOCAL DEV] Simulated QBO Failure Email to {admin_emails} for invoice {invoice_number}: {error_msg}\n")
        return
        
    try:
        ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sender = os.getenv("SES_SENDER_EMAIL", "noreply@augmentedtradetech.com")
        subject = f"[QuickBooks Sync Failure] Invoice {invoice_number}"
        body_text = f"QuickBooks Online sync failed for invoice {invoice_number} (ID: {invoice_id}).\n\nError:\n{error_msg}\n\nPlease check the integration logs and retry sync manually."
        body_html = f"""<html>
        <body>
          <h2>QuickBooks Online Sync Failed</h2>
          <p>QuickBooks Online sync failed for invoice <strong>{invoice_number}</strong> (ID: {invoice_id}).</p>
          <p><strong>Error Details:</strong></p>
          <pre style="background-color: #f8f9fa; padding: 10px; border: 1px solid #dee2e6; border-radius: 4px;">{error_msg}</pre>
          <p>Please log in to the system, review the integration dashboard, and retry sync manually.</p>
        </body>
        </html>"""
        
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": admin_emails},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body_text},
                    "Html": {"Data": body_html}
                }
            }
        )
    except Exception as e:
        logger.error(f"Failed to send alert email via SES: {e}")

def handler(event, context):
    logger.info(f"Received SQS event: {json.dumps(event)}")
    db = SessionLocal()
    
    try:
        for record in event.get("Records", []):
            body = {}
            try:
                body = json.loads(record.get("body", "{}"))
            except Exception as e:
                logger.error(f"Failed to parse record body: {e}")
                continue
                
            action = body.get("action")
            event_type = body.get("type")
            
            # SQS payload must be for QBO sync
            if action != "quickbooks_sync" and event_type != "qbo_sync":
                logger.info(f"Skipping non-QBO sync action/type: action={action}, type={event_type}")
                continue
                
            invoice_id = body.get("invoice_id")
            company_id = body.get("company_id")
            
            if not invoice_id or not company_id:
                logger.error(f"Missing invoice_id or company_id in payload: {body}")
                continue
                
            # Set RLS context for the specific company
            set_rls_context(db, company_id, None, "system")
            
            # Find the SyncQueue entry
            idempotency_key = f"qbo_sync_{invoice_id}"
            sync_entry = db.scalar(
                select(SyncQueue)
                .where(SyncQueue.company_id == company_id)
                .where(SyncQueue.idempotency_key == idempotency_key)
            )
            
            # Create a SyncQueue entry if missing
            if not sync_entry:
                sync_entry = SyncQueue(
                    id=f"sy_{ulid.new()}",
                    company_id=company_id,
                    user_id="system",
                    entity_type="invoice",
                    entity_id=invoice_id,
                    operation="create",
                    payload={"invoice_id": invoice_id},
                    client_timestamp=datetime.now(timezone.utc),
                    idempotency_key=idempotency_key,
                    status="pending"
                )
                db.add(sync_entry)
                db.flush()
            
            sync_entry.status = "processing"
            sync_entry.attempts += 1
            sync_entry.last_attempted_at = datetime.now(timezone.utc)
            db.flush()
            
            # Find the Company & check connection status
            company = db.scalar(select(Company).where(Company.id == company_id))
            if not company:
                error_msg = f"Company {company_id} not found."
                mark_failed(db, sync_entry, error_msg, company_id, invoice_id, "Unknown Invoice")
                continue
                
            if not company.qbo_realm_id:
                # Company not connected to QBO - skip sync (not an error, just keep pending)
                logger.info(f"Company {company_id} is not connected to QuickBooks Online. Keeping in pending.")
                sync_entry.status = "pending"
                db.commit()
                continue
                
            # Find the Invoice
            invoice = db.scalar(
                select(Invoice)
                .where(Invoice.id == invoice_id)
                .where(Invoice.company_id == company_id)
            )
            if not invoice:
                error_msg = f"Invoice {invoice_id} not found."
                mark_failed(db, sync_entry, error_msg, company_id, invoice_id, "Unknown Invoice")
                continue
                
            # Double check that invoice status is paid
            if invoice.status != "paid":
                error_msg = f"Invoice {invoice_id} has status '{invoice.status}'. QBO sync requires status 'paid'."
                mark_failed(db, sync_entry, error_msg, company_id, invoice_id, invoice.invoice_number)
                continue
                
            try:
                # Initialize QBO client & refresh token
                client = QBOClient(db, company_id)
                client.refresh_token_if_needed()
                
                # Fetch customer details
                customer = db.scalar(
                    select(Customer)
                    .where(Customer.id == invoice.customer_id)
                    .where(Customer.company_id == company_id)
                )
                if not customer:
                    raise ValueError(f"Customer {invoice.customer_id} not found for invoice {invoice_id}")
                    
                # 1. Sync Customer
                qbo_customer_id = client.get_or_create_customer(customer)
                
                # 2. Sync Invoice (Items are resolved dynamically inside)
                qbo_invoice_id = client.create_invoice(invoice, qbo_customer_id)
                
                # 3. Sync Payment
                qbo_payment_id = client.create_payment(invoice, qbo_invoice_id, qbo_customer_id)
                
                # Update Invoice with QBO ID
                invoice.qbo_invoice_id = qbo_invoice_id
                db.add(invoice)
                
                # Update SyncQueue entry
                sync_entry.status = "applied"
                sync_entry.applied_at = datetime.now(timezone.utc)
                sync_entry.server_response = {
                    "qbo_customer_id": qbo_customer_id,
                    "qbo_invoice_id": qbo_invoice_id,
                    "qbo_payment_id": qbo_payment_id
                }
                sync_entry.conflict_detail = None
                
                db.commit()
                logger.info(f"QuickBooks sync succeeded for Invoice {invoice_id}. QBO Inv ID: {qbo_invoice_id}")
                
            except Exception as e:
                db.rollback()
                error_trace = traceback.format_exc()
                error_msg = f"Sync failed: {str(e)}\n\nTraceback:\n{error_trace}"
                logger.error(f"Error syncing invoice {invoice_id} to QBO: {error_msg}")
                
                # Set context again for marking failure (rollback clears session state)
                set_rls_context(db, company_id, None, "system")
                mark_failed(db, sync_entry, error_msg, company_id, invoice_id, invoice.invoice_number)
                
        return {"status": "success"}
    finally:
        db.close()

def mark_failed(db, sync_entry, error_msg, company_id, invoice_id, invoice_number):
    try:
        # Refetch/Re-merge since transaction was rolled back
        sync_entry = db.merge(sync_entry)
        sync_entry.status = "failed"
        sync_entry.conflict_detail = {"error": error_msg[:1000]} # Limit size
        db.add(sync_entry)
        
        # Log to AuditLog
        audit = AuditLog(
            id=f"al_{ulid.new()}",
            company_id=company_id,
            actor_id=None,
            actor_role="system",
            action="quickbooks.sync_failed",
            entity_type="invoice",
            entity_id=invoice_id,
            before_state=None,
            after_state={"error": error_msg}
        )
        db.add(audit)
        db.commit()
        
        # Fetch admins
        admins = db.scalars(
            select(User)
            .where(User.company_id == company_id)
            .where(User.role == "company_admin")
            .where(User.is_active == True)
        ).all()
        admin_emails = [admin.email for admin in admins] if admins else ["admin@augmentedtradetech.com"]
        
        # Send SES email alert
        send_failure_email(company_id, invoice_id, invoice_number, error_msg, admin_emails)
    except Exception as inner_err:
        logger.error(f"Failed to record QBO sync failure: {inner_err}")
        db.rollback()
