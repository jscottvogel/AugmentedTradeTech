import ulid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from apps.api.app.core.database import get_db
from apps.api.app.models.customer import Customer
from apps.api.app.models.invoice import Invoice, InvoiceLineItem
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger, LoyaltyBalanceView
from apps.api.app.routers.invoices import check_permission, recalculate_invoice

router = APIRouter(prefix="/loyalty", tags=["loyalty"])

class LoyaltyRedeemRequest(BaseModel):
    invoice_id: str
    points: int

@router.get("/{customer_id}")
def get_customer_loyalty_endpoint(
    customer_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Retrieve a customer's loyalty account info, balance, and transaction history (Staff only)"""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    company_id = request.state.company_id

    # Verify customer exists and belongs to this company
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .where(Customer.company_id == company_id)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Get or create loyalty account
    account = db.scalar(
        select(LoyaltyAccount)
        .where(LoyaltyAccount.customer_id == customer_id)
    )
    if not account:
        account = LoyaltyAccount(
            id=f"loy_{ulid.new()}",
            company_id=company_id,
            customer_id=customer_id,
            is_active=True
        )
        db.add(account)
        db.flush()

    # Get balance and lifetime earned
    balance_view = db.scalar(
        select(LoyaltyBalanceView)
        .where(LoyaltyBalanceView.account_id == account.id)
    )
    balance = balance_view.balance if balance_view else 0
    lifetime_earned = balance_view.lifetime_earned if balance_view else 0

    # Get transaction history
    ledger_entries = db.scalars(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.account_id == account.id)
        .order_by(LoyaltyLedger.created_at.desc())
    ).all()

    return {
        "account": {
            "id": account.id,
            "company_id": account.company_id,
            "customer_id": account.customer_id,
            "is_active": account.is_active,
            "created_at": account.created_at.isoformat() if account.created_at else None
        },
        "balance": balance,
        "lifetime_earned": lifetime_earned,
        "history": [
            {
                "id": entry.id,
                "entry_type": entry.entry_type,
                "points": entry.points,
                "description": entry.description,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "voided_at": entry.voided_at.isoformat() if entry.voided_at else None
            }
            for entry in ledger_entries
        ]
    }

@router.post("/{customer_id}/redeem")
def redeem_loyalty_points_endpoint(
    customer_id: str,
    req: LoyaltyRedeemRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Redeem points on an invoice for a customer. Atomic transaction."""
    check_permission(request, ["company_admin", "dispatcher", "tech"])
    company_id = request.state.company_id
    user_id = request.state.user_id

    # Verify customer and invoice belong to this company
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .where(Customer.company_id == company_id)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == req.invoice_id)
        .where(Invoice.company_id == company_id)
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="Invoice does not belong to this customer")

    if req.points <= 0:
        raise HTTPException(status_code=400, detail="Redemption points must be greater than zero")

    # Get or create loyalty account
    account = db.scalar(
        select(LoyaltyAccount)
        .where(LoyaltyAccount.customer_id == customer_id)
    )
    if not account:
        account = LoyaltyAccount(
            id=f"loy_{ulid.new()}",
            company_id=company_id,
            customer_id=customer_id,
            is_active=True
        )
        db.add(account)
        db.flush()

    # Check for existing redemption on this invoice
    idempotency_key = f"redeem-{invoice.id}"
    existing_redeem = db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.idempotency_key == idempotency_key)
    )
    if existing_redeem:
        raise HTTPException(status_code=400, detail="Points already redeemed for this invoice")

    # 1. Verify sufficient balance (query loyalty_balances view)
    balance_view = db.scalar(
        select(LoyaltyBalanceView)
        .where(LoyaltyBalanceView.account_id == account.id)
    )
    current_balance = balance_view.balance if balance_view else 0
    if current_balance < req.points:
        raise HTTPException(status_code=400, detail="Insufficient loyalty points balance")

    # 2. INSERT loyalty_ledger row
    ledger_entry = LoyaltyLedger(
        id=f"tx_{ulid.new()}",
        company_id=company_id,
        account_id=account.id,
        entry_type="redeem",
        points=req.points,
        job_id=invoice.job_id,
        invoice_id=invoice.id,
        description=f"Redeemed {req.points} loyalty points on invoice {invoice.invoice_number}",
        idempotency_key=idempotency_key,
        created_by=user_id
    )
    db.add(ledger_entry)

    # 3. Add discount line item to invoice
    discount_item = InvoiceLineItem(
        id=f"ili_{ulid.new()}",
        company_id=company_id,
        invoice_id=invoice.id,
        line_type="fee",
        description="Loyalty Points Redemption",
        quantity=1.00,
        unit_price_cents=-req.points,
        is_taxable=False,
        created_by=user_id
    )
    db.add(discount_item)
    db.flush()

    # 4. Recalculate invoice total
    recalculate_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)

    return {
        "success": True,
        "redeemed_points": req.points,
        "invoice_total_cents": invoice.total_cents
    }
