import pytest
from datetime import datetime, date, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal

from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.job import Job, JobTechnician, JobStatusHistory
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger, LoyaltyBalanceView
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.sync import SyncQueue
from apps.api.app.routers.auth import create_access_token

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, loyalty_ledger, loyalty_accounts, memberships, membership_plans, invoices, availability_status_logs, job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, users, companies CASCADE;"))
    db.commit()

    # Seed Company
    comp = Company(
        id="comp_test",
        name="Test Company",
        slug="test-company",
        timezone="America/Chicago",
        job_number_seq=0,
        tax_rate_bps=825  # 8.25%
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
    tech = User(
        id="usr_tech",
        company_id="comp_test",
        email="tech@test.com",
        full_name="Tech User",
        role="tech",
        is_active=True
    )
    dispatcher = User(
        id="usr_disp",
        company_id="comp_test",
        email="disp@test.com",
        full_name="Dispatcher User",
        role="dispatcher",
        is_active=True
    )
    db.add_all([admin, tech, dispatcher])
    db.commit()

    # Tech Profile
    tprf = TechProfile(
        id="tprf_tech",
        user_id="usr_tech",
        company_id="comp_test",
        availability_status="available"
    )
    db.add(tprf)
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

def test_invoice_autodraft_on_job_completion(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # 1. Create a Job with diagnosis info
    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech",
        "reported_problem": "AC blowing hot air"
    }
    response = client.post("/jobs", json=job_data, headers=admin_headers)
    assert response.status_code == 201
    job_id = response.json()["id"]

    # Assign diagnosis data
    job = test_db.scalar(select(Job).where(Job.id == job_id))
    job.ai_diagnosis = {
        "draft_line_items": [
            {"description": "HVAC Labor Charges", "quantity": 2.5, "unit_price_cents": 8000},
            {"description": "Compressor Part", "quantity": 1, "unit_price_cents": 35000},
            {"description": "Environmental Fee", "quantity": 1, "unit_price_cents": 5000}
        ]
    }
    test_db.add(job)
    test_db.commit()

    # Go through transitions to in_progress
    client.post(f"/jobs/{job_id}/status", json={"status": "confirmed"}, headers=tech_headers)
    client.post(f"/jobs/{job_id}/status", json={"status": "en_route"}, headers=tech_headers)
    client.post(f"/jobs/{job_id}/status", json={"status": "on_site"}, headers=tech_headers)
    client.post(f"/jobs/{job_id}/status", json={"status": "in_progress"}, headers=tech_headers)

    # 2. Trigger job completion status transition
    resp = client.post(f"/jobs/{job_id}/status", json={"status": "completed", "note": "All done"}, headers=tech_headers)
    assert resp.status_code == 200

    # 3. Check that draft invoice was automatically generated
    inv = test_db.scalar(select(Invoice).where(Invoice.job_id == job_id))
    assert inv is not None
    assert inv.status == "draft"
    assert len(inv.line_items) == 3

    # Without membership, total cents should be:
    # subtotal = 20000 + 35000 + 5000 = 60000 cents ($600.00)
    # tax = round(60000 * 825 / 10000) = 4950 cents ($49.50)
    # total = 64950 cents ($649.50)
    assert inv.subtotal_cents == 60000
    assert inv.tax_cents == 4950
    assert inv.discount_cents == 0
    assert inv.total_cents == 64950

def test_invoice_autodraft_with_membership_discounts(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # 1. Create a Membership Plan and active Membership for the customer
    plan = MembershipPlan(
        id="plan_gold",
        company_id="comp_test",
        name="Gold Plan",
        trade="both",
        labor_discount_pct=15.0,  # 15% labor
        parts_discount_pct=10.0,   # 10% parts
        monthly_price_cents=4900,
        is_active=True,
        created_by="usr_admin"
    )
    test_db.add(plan)
    test_db.flush()

    membership = Membership(
        id="mem_cust",
        company_id="comp_test",
        customer_id="cust_test",
        plan_id=plan.id,
        status="active",
        billing_cadence="monthly",
        current_period_start=datetime.now(timezone.utc) - timedelta(days=5),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=25),
        enrolled_by="admin",
        created_by="usr_admin"
    )
    test_db.add(membership)
    test_db.commit()

    # 2. Create Job and set diagnosis data
    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }
    job_id = client.post("/jobs", json=job_data, headers=admin_headers).json()["id"]

    job = test_db.scalar(select(Job).where(Job.id == job_id))
    job.ai_diagnosis = {
        "draft_line_items": [
            {"description": "HVAC Labor Charges", "quantity": 2.5, "unit_price_cents": 8000}, # labor (15% off) -> 3000 cents disc
            {"description": "Compressor Part", "quantity": 1, "unit_price_cents": 35000},   # part (10% off) -> 3500 cents disc
            {"description": "Environmental Fee", "quantity": 1, "unit_price_cents": 5000}     # fee (0% off)
        ]
    }
    test_db.add(job)
    test_db.commit()

    # Transitions
    client.post(f"/jobs/{job_id}/status", json={"status": "confirmed"}, headers=tech_headers)
    client.post(f"/jobs/{job_id}/status", json={"status": "en_route"}, headers=tech_headers)
    client.post(f"/jobs/{job_id}/status", json={"status": "on_site"}, headers=tech_headers)
    client.post(f"/jobs/{job_id}/status", json={"status": "in_progress"}, headers=tech_headers)
    client.post(f"/jobs/{job_id}/status", json={"status": "completed"}, headers=tech_headers)

    # 3. Get invoice
    inv = test_db.scalar(select(Invoice).where(Invoice.job_id == job_id))
    assert inv is not None
    # subtotal: 60000
    # tax: 4950
    # discount: 3000 + 3500 = 6500
    # total: 60000 + 4950 - 6500 = 58450
    assert inv.subtotal_cents == 60000
    assert inv.tax_cents == 4950
    assert inv.discount_cents == 6500
    assert inv.total_cents == 58450

def test_invoice_crud_line_items(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # Seed a job since job_id is NOT NULL
    job = Job(
        id="job_test",
        company_id="comp_test",
        customer_id="cust_test",
        job_number="JOB-2026-00001",
        status="scheduled",
        trade="hvac",
        job_type="service",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.flush()

    # 1. Setup minimal invoice
    invoice = Invoice(
        id="inv_test",
        company_id="comp_test",
        job_id="job_test",
        customer_id="cust_test",
        invoice_number="INV-2026-00001",
        status="draft",
        tax_rate_bps=825,
        subtotal_cents=0,
        tax_cents=0,
        discount_cents=0,
        total_cents=0,
        created_by="usr_admin"
    )
    test_db.add(invoice)
    test_db.commit()

    # 2. Add a line item via POST /invoices/:id/line-items
    line_data = {
        "line_type": "labor",
        "description": "Standard Labor",
        "quantity": 2.0,
        "unit_price_cents": 10000,
        "is_taxable": True
    }
    resp = client.post(f"/invoices/inv_test/line-items", json=line_data, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["line_items"]) == 1
    assert data["subtotal_cents"] == 20000
    assert data["tax_cents"] == 1650 # round(20000 * 825 / 10000)
    assert data["total_cents"] == 21650

    line_item_id = data["line_items"][0]["id"]

    # 3. Update the line item via PUT /invoices/:id/line-items/:lid
    update_data = {
        "quantity": 3.0,
        "unit_price_cents": 12000
    }
    resp = client.put(f"/invoices/inv_test/line-items/{line_item_id}", json=update_data, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["subtotal_cents"] == 36000 # 3.0 * 12000
    assert data["tax_cents"] == 2970 # round(36000 * 825 / 10000)
    assert data["total_cents"] == 38970

    # 4. Remove the line item via DELETE /invoices/:id/line-items/:lid
    resp = client.delete(f"/invoices/inv_test/line-items/{line_item_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["line_items"]) == 0
    assert data["subtotal_cents"] == 0
    assert data["tax_cents"] == 0
    assert data["total_cents"] == 0

def test_loyalty_point_redemption(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # Seed a job since job_id is NOT NULL
    job = Job(
        id="job_test",
        company_id="comp_test",
        customer_id="cust_test",
        job_number="JOB-2026-00001",
        status="scheduled",
        trade="hvac",
        job_type="service",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.flush()

    # 1. Setup invoice
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

    # Seed a line item for $100 standard part so recalculate math works
    line_item = InvoiceLineItem(
        id="ili_test",
        company_id="comp_test",
        invoice_id="inv_test",
        line_type="part",
        description="Standard Part",
        quantity=1.0,
        unit_price_cents=10000,
        is_taxable=True,
        discount_pct=0.0,
        sort_order=0,
        created_by="usr_admin"
    )
    test_db.add(line_item)
    test_db.flush()
    
    # 2. Setup Loyalty account and balance
    loy_acc = LoyaltyAccount(
        id="loy_test",
        company_id="comp_test",
        customer_id="cust_test",
        is_active=True,
        created_by="usr_admin"
    )
    test_db.add(loy_acc)
    test_db.flush()

    # Credit points to account
    credit = LoyaltyLedger(
        id="tx_credit",
        company_id="comp_test",
        account_id="loy_test",
        entry_type="earn",
        points=5000, # 5000 points = $50
        description="Welcome bonus",
        created_by="usr_admin"
    )
    test_db.add(credit)
    test_db.commit()

    # 3. Attempt to redeem 6000 points (insufficient balance)
    resp = client.put(f"/invoices/inv_test", json={"redeem_points": 6000}, headers=admin_headers)
    assert resp.status_code == 400
    assert "Insufficient loyalty points balance" in resp.json()["detail"]

    # 4. Redeem 3000 points (valid balance)
    resp = client.put(f"/invoices/inv_test", json={"redeem_points": 3000}, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["loyalty"]["redeemed_points"] == 3000
    assert data["discount_cents"] == 3000
    assert data["total_cents"] == 7825  # 10000 + 825 - 3000 = 7825

    # 5. Check ledger entry
    ledger_entries = test_db.scalars(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == "inv_test")
        .where(LoyaltyLedger.entry_type == "redeem")
    ).all()
    assert len(ledger_entries) == 1
    assert ledger_entries[0].points == 3000
    assert ledger_entries[0].voided_at is None

    # 6. Change points to 1000
    resp = client.put(f"/invoices/inv_test", json={"redeem_points": 1000}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["loyalty"]["redeemed_points"] == 1000
    assert resp.json()["discount_cents"] == 1000

    # Verify old entries deleted
    ledger_entries = test_db.scalars(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == "inv_test")
        .where(LoyaltyLedger.entry_type == "redeem")
    ).all()
    assert len(ledger_entries) == 1
    assert ledger_entries[0].points == 1000

def test_invoice_sending_and_voiding(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # 1. Create a Job
    job = Job(
        id="job_test",
        company_id="comp_test",
        customer_id="cust_test",
        job_number="JOB-2026-00001",
        status="completed",
        trade="hvac",
        job_type="service",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.flush()
    
    # 2. Create invoice
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
        discount_pct=0.0,
        sort_order=0,
        created_by="usr_admin"
    )
    test_db.add(line_item)
    test_db.commit()

    # 3. Send invoice via POST /invoices/:id/send
    resp = client.post(f"/invoices/inv_test/send", headers=tech_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    assert resp.json()["sent_at"] is not None

    # Job status should have transitioned to "invoiced"
    test_db.refresh(job)
    assert job.status == "invoiced"

    # 4. Voiding permissions: tech should fail
    resp = client.post(f"/invoices/inv_test/void", headers=tech_headers)
    assert resp.status_code == 403

    # Admin voids
    resp = client.post(f"/invoices/inv_test/void", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "void"
    assert resp.json()["voided_at"] is not None

def test_invoice_collect_payment(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # 1. Setup Job (invoiced state)
    job = Job(
        id="job_test",
        company_id="comp_test",
        customer_id="cust_test",
        job_number="JOB-2026-00001",
        status="invoiced",
        trade="hvac",
        job_type="service",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.flush()

    # 2. Setup Invoice (sent state)
    invoice = Invoice(
        id="inv_test",
        company_id="comp_test",
        job_id="job_test",
        customer_id="cust_test",
        invoice_number="INV-2026-00001",
        status="sent",
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
        discount_pct=0.0,
        sort_order=0,
        created_by="usr_admin"
    )
    test_db.add(line_item)
    test_db.commit()

    # 3. Call PUT /invoices/:id to mark as paid
    update_data = {
        "status": "paid",
        "payment_method": "check"
    }
    resp = client.put(f"/invoices/inv_test", json=update_data, headers=tech_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paid"
    assert resp.json()["paid_at"] is not None
    assert resp.json()["amount_paid_cents"] == 10825
    assert resp.json()["balance_cents"] == 0

    # Job status should have transitioned to "paid"
    test_db.refresh(job)
    assert job.status == "paid"

    # Verify Payment record created in DB
    pay = test_db.scalar(select(Payment).where(Payment.invoice_id == "inv_test"))
    assert pay is not None
    assert pay.amount_cents == 10825
    assert pay.payment_method == "check"
    assert pay.status == "succeeded"

def test_invoice_new_payment_and_signature_flows(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # Setup Job (completed state)
    job = Job(
        id="job_test_flow",
        company_id="comp_test",
        customer_id="cust_test",
        job_number="JOB-2026-00002",
        status="completed",
        trade="hvac",
        job_type="service",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.flush()

    # Setup Invoice (draft state)
    invoice = Invoice(
        id="inv_test_flow",
        company_id="comp_test",
        job_id="job_test_flow",
        customer_id="cust_test",
        invoice_number="INV-2026-00002",
        status="draft",
        tax_rate_bps=825,
        subtotal_cents=10000,
        tax_cents=825,
        discount_cents=0,
        total_cents=10825,
        created_by="usr_admin"
    )
    test_db.add(invoice)
    
    line_item = InvoiceLineItem(
        id="ili_test_flow",
        company_id="comp_test",
        invoice_id="inv_test_flow",
        line_type="part",
        description="Standard Part",
        quantity=1.0,
        unit_price_cents=10000,
        is_taxable=True,
        discount_pct=0.0,
        sort_order=0,
        created_by="usr_admin"
    )
    test_db.add(line_item)
    test_db.commit()

    # 1. Test POST /invoices/{id}/signature
    dummy_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    resp = client.post(
        f"/invoices/inv_test_flow/signature",
        json={"signature_base64": dummy_b64},
        headers=tech_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["customer_signature_url"] is not None
    assert "/mock-s3-upload/signatures/inv_test_flow_" in data["customer_signature_url"]

    # 2. Test POST /invoices/{id}/pay/intent (connect mock fallback)
    resp = client.post(
        f"/invoices/inv_test_flow/pay/intent",
        headers=tech_headers
    )
    assert resp.status_code == 200
    intent_data = resp.json()
    assert intent_data["client_secret"] is not None
    assert intent_data["payment_intent_id"].startswith("pi_mock_")
    assert intent_data["status"] == "requires_payment_method"

    # 3. Test POST /invoices/{id}/pay/link (connect mock fallback)
    resp = client.post(
        f"/invoices/inv_test_flow/pay/link",
        headers=tech_headers
    )
    assert resp.status_code == 200
    link_data = resp.json()
    assert "mock_payment_link=true" in link_data["url"]
    assert "invoice_id=inv_test_flow" in link_data["url"]

    # 4. Test Stripe Webhook: payment_intent.succeeded
    webhook_payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": intent_data["payment_intent_id"],
                "amount": 10825,
                "latest_charge": "ch_mock_test_charge",
                "metadata": {
                    "invoice_id": "inv_test_flow",
                    "company_id": "comp_test"
                }
            }
        }
    }
    resp = client.post(
        "/webhooks/stripe",
        json=webhook_payload
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Verify database updates
    test_db.expire_all()
    inv = test_db.scalar(select(Invoice).where(Invoice.id == "inv_test_flow"))
    assert inv.status == "paid"
    assert inv.amount_paid_cents == 10825
    assert inv.paid_at is not None

    job = test_db.scalar(select(Job).where(Job.id == "job_test_flow"))
    assert job.status == "paid"

    pay = test_db.scalar(select(Payment).where(Payment.invoice_id == "inv_test_flow"))
    assert pay is not None
    assert pay.status == "succeeded"
    assert pay.amount_cents == 10825
    assert pay.payment_method == "card_present"

    # Verify loyalty account earned points
    loy = test_db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == "cust_test"))
    assert loy is not None
    
    earn = test_db.scalar(
        select(LoyaltyLedger)
        .where(LoyaltyLedger.invoice_id == "inv_test_flow")
        .where(LoyaltyLedger.entry_type == "earn")
    )
    assert earn is not None
    assert earn.points == 108

    # Verify QuickBooks sync enqueued
    qbo = test_db.scalar(
        select(SyncQueue)
        .where(SyncQueue.entity_id == "inv_test_flow")
    )
    assert qbo is not None
    assert qbo.entity_type == "invoice"
    assert qbo.status == "pending"

def test_invoice_manual_payment(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # Setup Job (completed state)
    job = Job(
        id="job_manual_pay",
        company_id="comp_test",
        customer_id="cust_test",
        job_number="JOB-2026-00003",
        status="completed",
        trade="hvac",
        job_type="service",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.flush()

    # Setup Invoice (draft state)
    invoice = Invoice(
        id="inv_manual_pay",
        company_id="comp_test",
        job_id="job_manual_pay",
        customer_id="cust_test",
        invoice_number="INV-2026-00003",
        status="draft",
        tax_rate_bps=825,
        subtotal_cents=10000,
        tax_cents=825,
        discount_cents=0,
        total_cents=10825,
        created_by="usr_admin"
    )
    test_db.add(invoice)
    
    line_item = InvoiceLineItem(
        id="ili_manual_pay",
        company_id="comp_test",
        invoice_id="inv_manual_pay",
        line_type="part",
        description="Standard Part",
        quantity=1.0,
        unit_price_cents=10000,
        is_taxable=True,
        discount_pct=0.0,
        sort_order=0,
        created_by="usr_admin"
    )
    test_db.add(line_item)
    test_db.commit()

    # Call POST /invoices/{id}/pay/manual
    resp = client.post(
        f"/invoices/inv_manual_pay/pay/manual",
        json={"payment_method": "cash", "notes": "Received $110 cash"},
        headers=tech_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "paid"

    # Verify db updates
    test_db.expire_all()
    inv = test_db.scalar(select(Invoice).where(Invoice.id == "inv_manual_pay"))
    assert inv.status == "paid"

    pay = test_db.scalar(select(Payment).where(Payment.invoice_id == "inv_manual_pay"))
    assert pay is not None
    assert pay.payment_method == "cash"
    assert pay.status == "succeeded"
