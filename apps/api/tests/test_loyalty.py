import pytest
import math
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text, select, func

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal

from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.job import Job
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger, LoyaltyBalanceView
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.user import User
from apps.api.app.routers.auth import create_access_token
from apps.api.app.services.loyalty import earn_loyalty_points
from apps.api.app.cron.loyalty_expiry import handler as expiry_cron_handler

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, loyalty_ledger, loyalty_accounts, memberships, membership_plans, invoices, availability_status_logs, job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, users, companies CASCADE;"))
    db.commit()

    # Seed Company with loyalty configurations
    comp = Company(
        id="comp_test",
        name="Test Company",
        slug="test-company",
        timezone="America/Chicago",
        job_number_seq=0,
        tax_rate_bps=825,  # 8.25%
        loyalty_earn_rate=2,  # 2 points per dollar
        loyalty_membership_multiplier=1.5,  # 1.5x for active members
        loyalty_expiry_days=30  # 30 days points validity
    )
    db.add(comp)
    db.commit()

    # Seed Users
    admin = User(
        id="usr_admin",
        company_id="comp_test",
        email="admin@test.com",
        full_name="Admin User",
        role="company_admin",
        is_active=True
    )
    db.add(admin)
    db.commit()

    # Seed Customer
    cust = Customer(
        id="cust_test",
        company_id="comp_test",
        first_name="Jane",
        last_name="Doe",
        phone="5551234567",
        email="jane@doe.com",
        address_line1="123 Main St",
        city="Dallas",
        state="TX",
        zip="75201"
    )
    db.add(cust)
    db.commit()

    yield db
    db.close()

def get_auth_headers(user_id: str, email: str, role: str, company_id: str = "comp_test"):
    token = create_access_token(user_id, company_id, role, email, True)
    return {"Authorization": f"Bearer {token}"}

def seed_job_and_invoice(db, job_id: str, invoice_id: str, company_id: str = "comp_test", customer_id: str = "cust_test", status: str = "draft", subtotal_cents: int = 10000):
    job = Job(
        id=job_id,
        company_id=company_id,
        customer_id=customer_id,
        job_number=f"JOB-{job_id}",
        status="completed",
        trade="plumbing",
        job_type="service",
        created_by="usr_admin"
    )
    db.add(job)
    db.flush()

    invoice = Invoice(
        id=invoice_id,
        company_id=company_id,
        job_id=job_id,
        customer_id=customer_id,
        invoice_number=f"INV-{invoice_id}",
        status=status,
        tax_rate_bps=825,
        subtotal_cents=subtotal_cents,
        tax_cents=round(subtotal_cents * 0.0825),
        discount_cents=0,
        total_cents=subtotal_cents + round(subtotal_cents * 0.0825),
        created_by="usr_admin"
    )
    db.add(invoice)
    db.flush()
    return job, invoice

def test_earn_loyalty_points_service(test_db):
    seed_job_and_invoice(test_db, "job_test_1", "inv_test_1")

    # 1. Earn points on $100.00 amount (10000 cents)
    # Earn rate is 2 points per dollar, so base = 200 points.
    earn_loyalty_points(
        db=test_db,
        customer_id="cust_test",
        job_id=None,
        invoice_id="inv_test_1",
        amount_cents=10000
    )
    test_db.commit()

    account = test_db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == "cust_test"))
    assert account is not None
    assert account.is_active is True

    ledger_entry = test_db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.account_id == account.id)
        .where(LoyaltyLedger.entry_type == "earn")
    )
    assert ledger_entry is not None
    assert ledger_entry.points == 200
    assert ledger_entry.idempotency_key == "earn-inv_test_1"
    assert ledger_entry.expires_at is not None
    
    # Check expiry is roughly 30 days from now
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=30)
    assert abs((ledger_entry.expires_at - expected_expiry).total_seconds()) < 60

    # 2. Test idempotency
    dup_entry = earn_loyalty_points(
        db=test_db,
        customer_id="cust_test",
        job_id=None,
        invoice_id="inv_test_1",
        amount_cents=10000
    )
    test_db.commit()
    assert dup_entry.id == ledger_entry.id

    # 3. Test active membership multiplier (company fallback: 1.5x)
    # Create active membership plan and active membership
    plan = MembershipPlan(
        id="plan_test",
        company_id="comp_test",
        name="Gold Plan",
        trade="both",
        monthly_price_cents=1000,
        is_active=True,
        loyalty_multiplier=None  # Fallback to company multiplier
    )
    test_db.add(plan)
    
    membership = Membership(
        id="mem_test",
        company_id="comp_test",
        customer_id="cust_test",
        plan_id="plan_test",
        status="active",
        billing_cadence="monthly",
        current_period_start=datetime.now(timezone.utc) - timedelta(days=5),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=25),
        enrolled_by="tech"
    )
    test_db.add(membership)
    test_db.commit()

    seed_job_and_invoice(test_db, "job_test_2", "inv_test_2", subtotal_cents=5000)

    # Earn points on $50.00 amount (5000 cents)
    # Base: 50 * 2 = 100. Multiplier: 1.5x -> 150 points.
    earn_loyalty_points(
        db=test_db,
        customer_id="cust_test",
        job_id=None,
        invoice_id="inv_test_2",
        amount_cents=5000
    )
    test_db.commit()

    entry_with_mult = test_db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == "inv_test_2")
    )
    assert entry_with_mult is not None
    assert entry_with_mult.points == 150

    # 4. Test active membership multiplier (plan custom: 2.0x)
    plan.loyalty_multiplier = 2.0
    test_db.commit()

    seed_job_and_invoice(test_db, "job_test_3", "inv_test_3", subtotal_cents=5000)

    # Base: 50 * 2 = 100. Multiplier: 2.0x -> 200 points.
    earn_loyalty_points(
        db=test_db,
        customer_id="cust_test",
        job_id=None,
        invoice_id="inv_test_3",
        amount_cents=5000
    )
    test_db.commit()

    entry_with_plan_mult = test_db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == "inv_test_3")
    )
    assert entry_with_plan_mult is not None
    assert entry_with_plan_mult.points == 200


def test_get_customer_loyalty_endpoint(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    seed_job_and_invoice(test_db, "job_test_1", "inv_test_1")

    # Seed loyalty points
    earn_loyalty_points(
        db=test_db,
        customer_id="cust_test",
        job_id=None,
        invoice_id="inv_test_1",
        amount_cents=10000
    )
    test_db.commit()

    resp = client.get("/loyalty/cust_test", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == 200
    assert data["lifetime_earned"] == 200
    assert len(data["history"]) == 1
    assert data["history"][0]["entry_type"] == "earn"
    assert data["history"][0]["points"] == 200


def test_redeem_loyalty_points_endpoint(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # Seed job and invoice
    job = Job(
        id="job_test",
        company_id="comp_test",
        customer_id="cust_test",
        job_number="JOB-2026-00001",
        status="completed",
        trade="plumbing",
        job_type="service",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.flush()
    
    invoice = Invoice(
        id="inv_test",
        company_id="comp_test",
        job_id="job_test",
        customer_id="cust_test",
        invoice_number="INV-2026-00001",
        status="draft",
        tax_rate_bps=825,
        subtotal_cents=10000,
        tax_cents=825,
        discount_cents=0,
        total_cents=10825,
        created_by="usr_admin"
    )
    test_db.add(invoice)
    test_db.flush()

    line_item = InvoiceLineItem(
        id="ili_test",
        company_id="comp_test",
        invoice_id="inv_test",
        line_type="part",
        description="Standard Part",
        quantity=1.0,
        unit_price_cents=10000,
        is_taxable=True,
        created_by="usr_admin"
    )
    test_db.add(line_item)
    test_db.flush()
    test_db.commit()

    # Seed 5000 points
    seed_job_and_invoice(test_db, "job_prev", "inv_prev", subtotal_cents=250000)
    earn_loyalty_points(
        db=test_db,
        customer_id="cust_test",
        job_id=None,
        invoice_id="inv_prev",
        amount_cents=250000  # 2500 * 2 = 5000 points
    )
    test_db.commit()

    # Redeem 3000 points
    resp = client.post(
        "/loyalty/cust_test/redeem",
        json={"invoice_id": "inv_test", "points": 3000},
        headers=admin_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["redeemed_points"] == 3000
    assert data["invoice_total_cents"] == 7825  # 10000 + 825 - 3000

    # Verify line item added
    test_db.refresh(invoice)
    redemption_item = test_db.scalar(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == "inv_test")
        .where(InvoiceLineItem.description == "Loyalty Points Redemption")
    )
    assert redemption_item is not None
    assert redemption_item.unit_price_cents == -3000

    # Verify ledger entry
    ledger_entry = test_db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == "inv_test")
        .where(LoyaltyLedger.entry_type == "redeem")
    )
    assert ledger_entry is not None
    assert ledger_entry.points == 3000
    assert ledger_entry.idempotency_key == "redeem-inv_test"


def test_loyalty_expiry_cron(test_db):
    # Setup account and ledger entries manually
    account = LoyaltyAccount(
        id="loy_test",
        company_id="comp_test",
        customer_id="cust_test",
        is_active=True
    )
    test_db.add(account)
    test_db.commit()

    # 1. Earn 1: 1000 points, expired 1 day ago
    earn1 = LoyaltyLedger(
        id="tx_earn1",
        company_id="comp_test",
        account_id="loy_test",
        entry_type="earn",
        points=1000,
        description="Earn 1",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        created_at=datetime.now(timezone.utc) - timedelta(days=31)
    )

    # 2. Earn 2: 500 points, expires in 29 days
    earn2 = LoyaltyLedger(
        id="tx_earn2",
        company_id="comp_test",
        account_id="loy_test",
        entry_type="earn",
        points=500,
        description="Earn 2",
        expires_at=datetime.now(timezone.utc) + timedelta(days=29),
        created_at=datetime.now(timezone.utc) - timedelta(days=1)
    )

    # 3. Redeem: 300 points
    redeem = LoyaltyLedger(
        id="tx_redeem",
        company_id="comp_test",
        account_id="loy_test",
        entry_type="redeem",
        points=300,
        description="Redeem 300",
        created_at=datetime.now(timezone.utc) - timedelta(days=15)
    )

    test_db.add_all([earn1, earn2, redeem])
    test_db.commit()

    # Pre-cron balance calculation (using the updated view)
    balance_view = test_db.scalar(
        select(LoyaltyBalanceView).where(LoyaltyBalanceView.account_id == "loy_test")
    )
    # Total earned/credited = 1000 + 500 = 1500. Total deducted = 300.
    # Pre-cron balance should be 1500 - 300 = 1200.
    assert balance_view.balance == 1200

    # Run the cron job
    result = expiry_cron_handler(None, None)
    assert result["status"] == "success"
    assert result["expired_entries_count"] == 1
    # FIFO: the 300 points redeemed were taken from Earn 1 (1000 points).
    # So the remaining points to expire from Earn 1 is 1000 - 300 = 700.
    assert result["expired_points_total"] == 700

    # Verify expire entry is in ledger
    test_db.rollback() # clear session cache
    expire_entry = test_db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.idempotency_key == "expire-tx_earn1")
    )
    assert expire_entry is not None
    assert expire_entry.points == 700

    # Post-cron balance calculation
    balance_view = test_db.scalar(
        select(LoyaltyBalanceView).where(LoyaltyBalanceView.account_id == "loy_test")
    )
    # Total earned/credited = 1500.
    # Total deducted = 300 (redeem) + 700 (expire) = 1000.
    # Balance should be 1500 - 1000 = 500. (Exactly Earn 2's balance)
    assert balance_view.balance == 500

    # Run cron again to verify idempotency (should expire 0 entries)
    result_idem = expiry_cron_handler(None, None)
    assert result_idem["expired_entries_count"] == 0
    assert result_idem["expired_points_total"] == 0
