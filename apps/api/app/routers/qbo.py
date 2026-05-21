import os
import logging
import jwt
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from apps.api.app.core.database import get_db, set_rls_context
from apps.api.app.models.company import Company
from apps.api.app.models.invoice import Invoice
from apps.api.app.models.sync import SyncQueue
from apps.api.app.services.qbo import QBOClient
from apps.api.app.routers.auth import JWT_SECRET, ALGORITHM
from apps.api.app.routers.invoices import trigger_quickbooks_sync

logger = logging.getLogger("qbo_router")

router = APIRouter(prefix="/integrations/qbo", tags=["QuickBooks Online Integration"])

class MappingsUpdateRequest(BaseModel):
    labor: str
    part_fallback: str
    fee: str

@router.post("/connect")
def connect_qbo(request: Request, db: Session = Depends(get_db)):
    """
    Generate QBO OAuth URL and redirect.
    Binds the company_id and user_id in the signed state token.
    """
    company_id = getattr(request.state, "company_id", None)
    user_id = getattr(request.state, "user_id", None)
    if not company_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Sign state token valid for 15 minutes
    state_payload = {
        "company_id": company_id,
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    state_token = jwt.encode(state_payload, JWT_SECRET, algorithm=ALGORITHM)
    
    client = QBOClient(db, company_id)
    auth_url = client.get_auth_url(state_token)
    return {"url": auth_url}

@router.get("/callback")
def callback_qbo(
    code: str,
    realmId: str,
    state: str,
    db: Session = Depends(get_db)
):
    """
    OAuth callback. Exchanges code for credentials, saves to Company, and redirects to frontend.
    """
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    try:
        # Decode state token
        state_payload = jwt.decode(state, JWT_SECRET, algorithms=[ALGORITHM])
        company_id = state_payload.get("company_id")
        user_id = state_payload.get("user_id")
    except jwt.ExpiredSignatureError:
        logger.error("QBO OAuth callback failed: State token expired")
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?status=error&error=session_expired")
    except jwt.InvalidTokenError:
        logger.error("QBO OAuth callback failed: Invalid state token")
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?status=error&error=invalid_session")
        
    if not company_id:
        logger.error("QBO OAuth callback failed: Missing company ID in state")
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?status=error&error=missing_company")
        
    try:
        # Set RLS context for database modifications in the callback
        set_rls_context(db, company_id, user_id, "company_admin")
        
        # Instantiate client (which checks for mock callback / tokens)
        client = QBOClient(db, company_id)
        
        # Save realm_id first so exchange_code has access to it if needed
        client.company.qbo_realm_id = realmId
        db.add(client.company)
        db.flush()
        
        token_data = client.exchange_code(code)
        
        # Save access and refresh tokens
        client.company.qbo_access_token = token_data.get("access_token")
        client.company.qbo_refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        client.company.qbo_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        db.add(client.company)
        db.commit()
        
        logger.info(f"Successfully connected QuickBooks Online for company {company_id}")
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?status=success")
        
    except Exception as e:
        db.rollback()
        logger.error(f"QBO OAuth callback token exchange failed: {e}")
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?status=error&error=token_exchange_failed")

@router.get("/status")
def get_qbo_status(request: Request, db: Session = Depends(get_db)):
    """
    Get QBO connection status, last sync, mapping config, and failed syncs.
    """
    company_id = getattr(request.state, "company_id", None)
    if not company_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    company = db.scalar(
        select(Company).where(Company.id == company_id)
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    connected = bool(company.qbo_realm_id)
    
    # Get last successful sync time
    last_sync_entry = db.scalar(
        select(SyncQueue)
        .where(SyncQueue.company_id == company_id)
        .where(SyncQueue.entity_type == "invoice")
        .where(SyncQueue.status == "applied")
        .order_by(desc(SyncQueue.applied_at))
        .limit(1)
    )
    last_sync_time = last_sync_entry.applied_at if last_sync_entry else None
    
    # Get recent failed syncs
    failed_syncs = db.scalars(
        select(SyncQueue)
        .where(SyncQueue.company_id == company_id)
        .where(SyncQueue.entity_type == "invoice")
        .where(SyncQueue.status == "failed")
        .order_by(desc(SyncQueue.last_attempted_at))
        .limit(20)
    ).all()
    
    errors_list = []
    for entry in failed_syncs:
        # Load invoice details
        invoice_number = entry.payload.get("invoice_number", f"INV-{entry.entity_id[-6:]}") if entry.payload else "Unknown"
        errors_list.append({
            "id": entry.id,
            "invoice_id": entry.entity_id,
            "invoice_number": invoice_number,
            "failed_at": entry.last_attempted_at or entry.created_at,
            "error_message": entry.conflict_detail.get("error") if entry.conflict_detail else "Unknown sync failure",
            "attempts": entry.attempts
        })
        
    # Get mappings
    mappings = company.qbo_item_mappings or {}
    
    return {
        "connected": connected,
        "realm_id": company.qbo_realm_id,
        "last_sync_at": last_sync_time,
        "item_mappings": {
            "labor": mappings.get("labor", "Labor"),
            "part_fallback": mappings.get("part_fallback", "Parts"),
            "fee": mappings.get("fee", "Fee")
        },
        "errors": errors_list
    }

@router.post("/disconnect")
def disconnect_qbo(request: Request, db: Session = Depends(get_db)):
    """
    Revoke QuickBooks tokens and disconnect the account.
    """
    company_id = getattr(request.state, "company_id", None)
    if not company_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    try:
        client = QBOClient(db, company_id)
        client.disconnect()
        db.commit()
        return {"status": "success", "message": "QuickBooks Online disconnected successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to disconnect QBO: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/mappings")
def update_mappings(
    payload: MappingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update item mapping configuration for the company.
    """
    company_id = getattr(request.state, "company_id", None)
    if not company_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    company = db.scalar(
        select(Company).where(Company.id == company_id)
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    company.qbo_item_mappings = {
        "labor": payload.labor.strip(),
        "part_fallback": payload.part_fallback.strip(),
        "fee": payload.fee.strip()
    }
    
    try:
        db.add(company)
        db.commit()
        return {"status": "success", "item_mappings": company.qbo_item_mappings}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update QBO mappings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync/{invoice_id}")
def sync_invoice_manual(
    invoice_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Manually trigger QuickBooks Online sync for a specific paid invoice.
    """
    company_id = getattr(request.state, "company_id", None)
    user_id = getattr(request.state, "user_id", None)
    if not company_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.company_id == company_id)
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Verify invoice is paid
    if invoice.status != "paid":
        raise HTTPException(status_code=400, detail="Only paid invoices can be synchronized to QuickBooks Online.")
        
    try:
        # If there's an existing failed SyncQueue entry, reset its status to pending and reset attempts
        idempotency_key = f"qbo_sync_{invoice.id}"
        existing = db.scalar(select(SyncQueue).where(SyncQueue.idempotency_key == idempotency_key))
        if existing:
            existing.status = "pending"
            existing.attempts = 0
            existing.last_attempted_at = None
            db.add(existing)
            db.flush()
            
        trigger_quickbooks_sync(db, invoice, user_id)
        db.commit()
        return {"status": "success", "message": "QuickBooks Online sync task enqueued successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to trigger QBO sync manually: {e}")
        raise HTTPException(status_code=500, detail=str(e))
