import pytest
import secrets
import jwt
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.user import User
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer
from apps.api.app.models.job import Job
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.auth import CustomerMagicLinkToken
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger
from apps.api.app.routers.auth import hash_token, JWT_SECRET, ALGORITHM

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    # Clean up before testing
    db.execute(text("TRUNCATE customer_magic_link_tokens, payments, invoice_line_items, invoices, job_status_history, job_photos, jobs, equipment_customers, equipment, loyalty_ledger, loyalty_accounts, memberships, membership_plans, customers, users, companies CASCADE;"))
    db.commit()

    # 1. Seed Company
    comp = Company(id="comp_test", name="Test Company", slug="test-company", primary_color="#ff5500")
    comp_other = Company(id="comp_other", name="Other Company", slug="other-company")
    db.add_all([comp, comp_other])
    db.commit()

    # 2. Seed System User (needed for audit logs or FK references if any)
    sys_user = User(
        id="system",
        company_id="comp_test",
        email="system@test.com",
        full_name="System",
        role="platform_admin",
        is_active=True
    )
    db.add(sys_user)
    db.commit()

    # 3. Seed Customers
    cust_a = Customer(
        id="cust_a",
        company_id="comp_test",
        first_name="Alice",
        last_name="Alpha",
        email="alice@alpha.com",
        phone="5550000001",
        portal_enabled=True,
        created_by="system",
        updated_by="system"
    )
    cust_b = Customer(
        id="cust_b",
        company_id="comp_test",
        first_name="Bob",
        last_name="Beta",
        email="bob@beta.com",
        phone="5550000002",
        portal_enabled=True,
        created_by="system",
        updated_by="system"
    )
    cust_disabled = Customer(
        id="cust_disabled",
        company_id="comp_test",
        first_name="Charlie",
        last_name="Disabled",
        email="charlie@disabled.com",
        phone="5550000003",
        portal_enabled=False,
        created_by="system",
        updated_by="system"
    )
    db.add_all([cust_a, cust_b, cust_disabled])
    db.commit()

    # 4. Seed Jobs
    job_a = Job(
        id="job_a",
        company_id="comp_test",
        customer_id="cust_a",
        trade="hvac",
        job_type="service",
        status="completed",
        reported_problem="AC not cooling",
        completed_at=datetime.now(timezone.utc),
        created_by="system",
        updated_by="system"
    )
    job_b = Job(
        id="job_b",
        company_id="comp_test",
        customer_id="cust_b",
        trade="garage_door",
        job_type="service",
        status="completed",
        reported_problem="Garage door stuck",
        completed_at=datetime.now(timezone.utc),
        created_by="system",
        updated_by="system"
    )
    db.add_all([job_a, job_b])
    db.commit()

    # 5. Seed Invoices
    inv_a = Invoice(
        id="inv_a",
        company_id="comp_test",
        customer_id="cust_a",
        job_id="job_a",
        invoice_number="INV-A",
        status="sent",
        subtotal_cents=10000,
        tax_cents=825,
        discount_cents=0,
        total_cents=10825,
        amount_paid_cents=0,
        created_by="system",
        updated_by="system"
    )
    inv_b = Invoice(
        id="inv_b",
        company_id="comp_test",
        customer_id="cust_b",
        job_id="job_b",
        invoice_number="INV-B",
        status="sent",
        subtotal_cents=20000,
        tax_cents=1650,
        discount_cents=0,
        total_cents=21650,
        amount_paid_cents=0,
        created_by="system",
        updated_by="system"
    )
    db.add_all([inv_a, inv_b])
    db.commit()

    # Seed Line Item for Invoice A
    li_a = InvoiceLineItem(
        id="li_a",
        company_id="comp_test",
        invoice_id="inv_a",
        line_type="labor",
        description="Standard Labor",
        quantity=1.0,
        unit_price_cents=10000,
        created_by="system"
    )
    db.add(li_a)
    db.commit()

    # 6. Seed Equipment
    eq_a = Equipment(
        id="eq_a",
        company_id="comp_test",
        trade="hvac",
        equipment_type="furnace",
        make="Carrier",
        model="59TP6",
        serial_number="CR-12345",
        created_by="system",
        updated_by="system"
    )
    db.add(eq_a)
    db.commit()

    # Associate Equipment with Customer A
    assoc_a = EquipmentCustomer(
        id="assoc_a",
        company_id="comp_test",
        equipment_id="eq_a",
        customer_id="cust_a",
        is_primary=True,
        created_by="system"
    )
    db.add(assoc_a)
    db.commit()

    # 7. Seed Membership Plan
    mplan = MembershipPlan(
        id="plan_test",
        company_id="comp_test",
        name="Silver Membership",
        description="10% off Labor and Parts",
        trade="hvac",
        monthly_price_cents=1500,
        annual_price_cents=15000,
        labor_discount_pct=10.0,
        parts_discount_pct=10.0,
        priority_scheduling=True,
        is_active=True,
        created_by="system",
        updated_by="system"
    )
    db.add(mplan)
    db.commit()

    # 8. Seed Loyalty Account & Ledger
    l_acct = LoyaltyAccount(
        id="l_acct_a",
        company_id="comp_test",
        customer_id="cust_a",
        created_by="system"
    )
    db.add(l_acct)
    db.commit()

    l_entry = LoyaltyLedger(
        id="l_entry_1",
        company_id="comp_test",
        account_id="l_acct_a",
        entry_type="earn",
        points=500,
        description="Seeded points",
        created_by="system"
    )
    db.add(l_entry)
    db.commit()

    yield db
    db.close()

def get_customer_headers(customer_id: str, company_id: str = "comp_test"):
    # Generate Customer JWT token
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {
        "sub": customer_id,
        "customer_id": customer_id,
        "company_id": company_id,
        "role": "customer",
        "exp": expire
    }
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {token}"}

# Tests
def test_get_company_config(test_db):
    # Retrieve by slug
    res = client.get("/portal/company-config?slug=test-company")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Test Company"
    assert data["primary_color"] == "#ff5500"
    assert data["slug"] == "test-company"

    # Retrieve invalid slug
    res = client.get("/portal/company-config?slug=invalid-slug")
    assert res.status_code == 404

def test_portal_magic_link_trigger(test_db):
    # 1. Trigger magic link for valid customer
    res = client.post("/portal/auth/magic-link", json={"contact": "alice@alpha.com"})
    assert res.status_code == 200
    assert "login link has been sent" in res.json()["message"]

    # Verify token added in db
    db_token = test_db.scalar(select(CustomerMagicLinkToken).where(CustomerMagicLinkToken.customer_id == "cust_a"))
    assert db_token is not None
    assert db_token.used_at is None

    # 2. Trigger magic link for disabled customer
    res = client.post("/portal/auth/magic-link", json={"contact": "charlie@disabled.com"})
    assert res.status_code == 400
    assert "access is disabled" in res.json()["detail"]

    # 3. Trigger magic link for invalid email (returns dummy message to prevent enumeration)
    res = client.post("/portal/auth/magic-link", json={"contact": "nonexistent@test.com"})
    assert res.status_code == 200
    assert "login link has been sent" in res.json()["message"]

def test_portal_magic_link_verify(test_db):
    raw_token = "b" * 64
    hashed = hash_token(raw_token)
    token_record = CustomerMagicLinkToken(
        id="cml_test_verify",
        customer_id="cust_a",
        token_hash=hashed,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        created_by="system",
        updated_by="system"
    )
    test_db.add(token_record)
    test_db.commit()

    # Verify magic link token
    res = client.post("/portal/auth/verify", json={"token": raw_token})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["customer"]["id"] == "cust_a"
    assert data["customer"]["email"] == "alice@alpha.com"

    # Check token was marked used
    test_db.refresh(token_record)
    assert token_record.used_at is not None

    # Verify again should fail
    res = client.post("/portal/auth/verify", json={"token": raw_token})
    assert res.status_code == 400

def test_portal_profile_and_isolation(test_db):
    headers_a = get_customer_headers("cust_a")
    headers_b = get_customer_headers("cust_b")

    # 1. Fetch profile
    res = client.get("/portal/me", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["first_name"] == "Alice"

    # 2. Fetch jobs list - Alice should only see job A
    res = client.get("/portal/jobs", headers=headers_a)
    assert res.status_code == 200
    jobs_a = res.json()
    assert len(jobs_a) == 1
    assert jobs_a[0]["id"] == "job_a"

    # Bob should only see job B
    res = client.get("/portal/jobs", headers=headers_b)
    assert res.status_code == 200
    jobs_b = res.json()
    assert len(jobs_b) == 1
    assert jobs_b[0]["id"] == "job_b"

    # Alice tries to read Bob's job detail
    res = client.get("/portal/jobs/job_b", headers=headers_a)
    assert res.status_code == 404

    # Alice reads her own job detail
    res = client.get("/portal/jobs/job_a", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["reported_problem"] == "AC not cooling"

def test_portal_invoices_and_payment(test_db):
    headers_a = get_customer_headers("cust_a")
    headers_b = get_customer_headers("cust_b")

    # 1. Fetch invoices list
    res = client.get("/portal/invoices", headers=headers_a)
    assert res.status_code == 200
    invoices_a = res.json()
    assert len(invoices_a) == 1
    assert invoices_a[0]["id"] == "inv_a"

    # 2. Fetch details
    res = client.get("/portal/invoices/inv_a", headers=headers_a)
    assert res.status_code == 200
    detail = res.json()
    assert detail["invoice_number"] == "INV-A"
    assert len(detail["line_items"]) == 1
    assert detail["line_items"][0]["description"] == "Standard Labor"

    # Cross-customer check
    res = client.get("/portal/invoices/inv_b", headers=headers_a)
    assert res.status_code == 404

    # 3. Pay invoice mock
    res = client.post("/portal/invoices/inv_a/pay", json={"confirm_mock": True}, headers=headers_a)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Verify invoice status is paid
    res = client.get("/portal/invoices/inv_a", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["status"] == "paid"
    assert res.json()["balance_cents"] == 0

def test_portal_equipment_and_requests(test_db):
    headers_a = get_customer_headers("cust_a")

    # 1. Get equipment list
    res = client.get("/portal/equipment", headers=headers_a)
    assert res.status_code == 200
    eq = res.json()
    assert len(eq) == 1
    assert eq[0]["id"] == "eq_a"
    assert eq[0]["make"] == "Carrier"

    # 2. Submit service request
    req_data = {
        "trade": "hvac",
        "reported_problem": "Need furnace inspection before winter",
        "equipment_id": "eq_a",
        "priority": "routine"
      }
    res = client.post("/portal/requests", json=req_data, headers=headers_a)
    assert res.status_code == 201
    job = res.json()
    assert job["trade"] == "hvac"
    assert job["status"] == "scheduled"
    assert job["reported_problem"] == "Need furnace inspection before winter"

def test_portal_membership_enrollment(test_db):
    headers_a = get_customer_headers("cust_a")

    # 1. Get membership details (currently none)
    res = client.get("/portal/membership", headers=headers_a)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "none"
    assert len(data["available_plans"]) == 1
    assert data["available_plans"][0]["id"] == "plan_test"

    # 2. Enroll
    enroll_data = {
        "plan_id": "plan_test",
        "billing_cadence": "monthly"
    }
    res = client.post("/portal/membership/enroll", json=enroll_data, headers=headers_a)
    assert res.status_code == 200
    assert res.json()["status"] == "active"
    assert res.json()["plan_name"] == "Silver Membership"

    # 3. Check status is now active
    res = client.get("/portal/membership", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["status"] == "active"
    assert res.json()["plan"]["name"] == "Silver Membership"

def test_portal_loyalty_balance(test_db):
    headers_a = get_customer_headers("cust_a")

    res = client.get("/portal/loyalty", headers=headers_a)
    assert res.status_code == 200
    data = res.json()
    assert data["balance"] == 500
    assert len(data["history"]) == 1
    assert data["history"][0]["points"] == 500
    assert data["history"][0]["description"] == "Seeded points"
