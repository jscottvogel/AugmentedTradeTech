import pytest
from datetime import datetime, date, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal

from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.user import User
from apps.api.app.models.job import Job
from apps.api.app.routers.auth import create_access_token
from apps.api.app.cron import membership_reminder

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    # TRUNCATE tables to avoid primary key constraints
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, loyalty_ledger, loyalty_accounts, memberships, membership_plans, invoices, availability_status_logs, job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, users, companies CASCADE;"))
    db.commit()

    # Seed Company with Connect details
    comp = Company(
        id="comp_test",
        name="Test Company",
        slug="test-company",
        timezone="America/Chicago",
        job_number_seq=0,
        tax_rate_bps=825,
        stripe_account_id="acct_mock_test123" # Mock Connect ID
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
    db.add_all([admin, tech])
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

def test_membership_plan_crud(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # 1. Create a Plan
    plan_data = {
        "name": "Gold Maintenance Plan",
        "description": "Bi-annual inspections and 15% discount",
        "trade": "both",
        "monthly_price_cents": 2900,
        "annual_price_cents": 29900,
        "included_visits_count": 2,
        "visit_reset_period": "annual",
        "carryover_visits": True,
        "labor_discount_pct": 15.0,
        "parts_discount_pct": 10.0,
        "priority_scheduling": True,
        "loyalty_multiplier": 1.5,
        "sort_order": 1
    }
    resp = client.post("/membership-plans", json=plan_data, headers=admin_headers)
    assert resp.status_code == 201
    plan_id = resp.json()["id"]
    assert resp.json()["stripe_monthly_price_id"].startswith("price_mock_monthly_")
    assert resp.json()["stripe_annual_price_id"].startswith("price_mock_annual_")

    # 2. Get list of active plans
    list_resp = client.get("/membership-plans", headers=admin_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["id"] == plan_id

    # 3. Update Plan (price changes generate new price IDs)
    old_monthly_price_id = resp.json()["stripe_monthly_price_id"]
    update_data = {
        "monthly_price_cents": 3500
    }
    up_resp = client.put(f"/membership-plans/{plan_id}", json=update_data, headers=admin_headers)
    assert up_resp.status_code == 200
    assert up_resp.json()["monthly_price_cents"] == 3500
    assert up_resp.json()["stripe_monthly_price_id"] != old_monthly_price_id
    assert up_resp.json()["stripe_monthly_price_id"].startswith("price_mock_monthly_")

    # 4. Soft Delete Plan
    del_resp = client.delete(f"/membership-plans/{plan_id}", headers=admin_headers)
    assert del_resp.status_code == 200
    
    # Query to verify list is empty (since is_active=False)
    list_resp = client.get("/membership-plans", headers=admin_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0

def test_membership_enrollment_lifecycle(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # Seed plan
    plan = MembershipPlan(
        id="plan_gold",
        company_id="comp_test",
        name="Gold Plan",
        trade="both",
        monthly_price_cents=2900,
        annual_price_cents=29900,
        stripe_monthly_price_id="price_mock_monthly_gold",
        stripe_annual_price_id="price_mock_annual_gold",
        is_active=True,
        created_by="usr_admin"
    )
    test_db.add(plan)
    test_db.commit()

    # Enroll step 1: Request SetupIntent
    enroll_data = {
        "customer_id": "cust_test",
        "plan_id": "plan_gold",
        "billing_cadence": "monthly"
    }
    resp1 = client.post("/memberships", json=enroll_data, headers=admin_headers)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "requires_payment_method"
    assert "client_secret" in resp1.json()
    assert "stripe_customer_id" in resp1.json()

    # Enroll step 2: Complete with payment method
    enroll_data_with_pm = {
        "customer_id": "cust_test",
        "plan_id": "plan_gold",
        "billing_cadence": "monthly",
        "payment_method_id": "pm_mock_test_pm"
    }
    resp2 = client.post("/memberships", json=enroll_data_with_pm, headers=admin_headers)
    assert resp2.status_code == 200
    membership_id = resp2.json()["id"]
    assert resp2.json()["status"] == "active"
    assert resp2.json()["stripe_subscription_id"].startswith("sub_mock_")

    # Get details
    detail_resp = client.get(f"/memberships/{membership_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "active"

    # List memberships
    list_resp = client.get("/memberships", headers=admin_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Pause membership
    pause_resp = client.post(f"/memberships/{membership_id}/pause", headers=admin_headers)
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # Resume membership
    resume_resp = client.post(f"/memberships/{membership_id}/resume", headers=admin_headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"

    # Cancel membership
    cancel_resp = client.post(
        f"/memberships/{membership_id}/cancel", 
        json={"cancellation_reason": "Moving out"},
        headers=admin_headers
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
    assert cancel_resp.json()["cancellation_reason"] == "Moving out"

def test_stripe_webhook_scenarios(test_db):
    # Setup active membership and subscription
    plan = MembershipPlan(
        id="plan_silver",
        company_id="comp_test",
        name="Silver Plan",
        trade="hvac",
        monthly_price_cents=1900,
        stripe_monthly_price_id="price_mock_monthly_silver",
        included_visits_count=1,
        is_active=True,
        created_by="usr_admin"
    )
    test_db.add(plan)
    test_db.flush()

    membership = Membership(
        id="mem_webhook_test",
        company_id="comp_test",
        customer_id="cust_test",
        plan_id="plan_silver",
        status="active",
        billing_cadence="monthly",
        current_period_start=datetime.now(timezone.utc) - timedelta(days=10),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=20),
        enrolled_by="admin",
        stripe_subscription_id="sub_webhook_test123",
        stripe_customer_id="cus_webhook_test123"
    )
    test_db.add(membership)
    test_db.commit()

    # 1. Simulate customer.subscription.updated (e.g. status becomes past_due -> suspended)
    sub_updated_payload = {
        "id": "evt_test1",
        "type": "customer.subscription.updated",
        "account": "acct_mock_test123",
        "data": {
            "object": {
                "id": "sub_webhook_test123",
                "status": "past_due",
                "current_period_start": int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp()),
                "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=29)).timestamp())
            }
        }
    }
    webhook_resp = client.post("/webhooks/stripe", json=sub_updated_payload)
    assert webhook_resp.status_code == 200
    
    test_db.expire_all()
    mem_check = test_db.scalar(select(Membership).where(Membership.id == "mem_webhook_test"))
    assert mem_check.status == "suspended"

    # 2. Simulate invoice.payment_failed (grace period initiated)
    payment_failed_payload = {
        "id": "evt_test2",
        "type": "invoice.payment_failed",
        "account": "acct_mock_test123",
        "data": {
            "object": {
                "subscription": "sub_webhook_test123"
            }
        }
    }
    webhook_resp = client.post("/webhooks/stripe", json=payment_failed_payload)
    assert webhook_resp.status_code == 200
    
    test_db.expire_all()
    mem_check = test_db.scalar(select(Membership).where(Membership.id == "mem_webhook_test"))
    assert mem_check.grace_period_ends_at is not None
    assert (mem_check.grace_period_ends_at - datetime.now(timezone.utc)).days == 13

    # 3. Simulate invoice.paid (active restored, next renewal set, job scheduled, notifications sent)
    invoice_paid_payload = {
        "id": "evt_test3",
        "type": "invoice.paid",
        "account": "acct_mock_test123",
        "data": {
            "object": {
                "subscription": "sub_webhook_test123"
            }
        }
    }
    webhook_resp = client.post("/webhooks/stripe", json=invoice_paid_payload)
    assert webhook_resp.status_code == 200

    test_db.expire_all()
    mem_check = test_db.scalar(select(Membership).where(Membership.id == "mem_webhook_test"))
    assert mem_check.status == "active"
    assert mem_check.grace_period_ends_at is None
    
    # Check that a Job was auto-created for maintenance
    job = test_db.scalar(select(Job).where(Job.membership_id == "mem_webhook_test"))
    assert job is not None
    assert job.is_included_visit is True
    assert job.status == "scheduled"
    assert job.job_type == "maintenance"

    # 4. Simulate customer.subscription.deleted
    sub_deleted_payload = {
        "id": "evt_test4",
        "type": "customer.subscription.deleted",
        "account": "acct_mock_test123",
        "data": {
            "object": {
                "id": "sub_webhook_test123"
            }
        }
    }
    webhook_resp = client.post("/webhooks/stripe", json=sub_deleted_payload)
    assert webhook_resp.status_code == 200

    test_db.expire_all()
    mem_check = test_db.scalar(select(Membership).where(Membership.id == "mem_webhook_test"))
    assert mem_check.status == "cancelled"
    assert mem_check.cancelled_at is not None

def test_daily_cron_notifications(test_db):
    # Setup test memberships for reminders:
    plan = MembershipPlan(
        id="plan_reminders",
        company_id="comp_test",
        name="Inspection Plan",
        trade="both",
        monthly_price_cents=1900,
        stripe_monthly_price_id="price_mock_monthly_rem",
        is_active=True,
        created_by="usr_admin"
    )
    test_db.add(plan)
    test_db.flush()

    now = datetime.now(timezone.utc)
    
    # 30-day target membership
    mem_30 = Membership(
        id="mem_30_days",
        company_id="comp_test",
        customer_id="cust_test",
        plan_id="plan_reminders",
        status="active",
        billing_cadence="monthly",
        current_period_start=now - timedelta(days=5),
        current_period_end=now + timedelta(days=30),
        next_renewal_at=now + timedelta(days=30),
        enrolled_by="admin",
        stripe_subscription_id="sub_30_days"
    )
    
    # 7-day target membership
    mem_7 = Membership(
        id="mem_7_days",
        company_id="comp_test",
        customer_id="cust_test",
        plan_id="plan_reminders",
        status="active",
        billing_cadence="monthly",
        current_period_start=now - timedelta(days=23),
        current_period_end=now + timedelta(days=7),
        next_renewal_at=now + timedelta(days=7),
        enrolled_by="admin",
        stripe_subscription_id="sub_7_days"
    )
    
    # grace period target membership
    mem_grace = Membership(
        id="mem_grace_period",
        company_id="comp_test",
        customer_id="cust_test",
        plan_id="plan_reminders",
        status="suspended",
        billing_cadence="monthly",
        current_period_start=now - timedelta(days=30),
        current_period_end=now,
        enrolled_by="admin",
        stripe_subscription_id="sub_grace",
        grace_period_ends_at=now + timedelta(days=10)
    )
    
    # irrelevant membership
    mem_ok = Membership(
        id="mem_ok",
        company_id="comp_test",
        customer_id="cust_test",
        plan_id="plan_reminders",
        status="active",
        billing_cadence="monthly",
        current_period_start=now - timedelta(days=15),
        current_period_end=now + timedelta(days=15),
        next_renewal_at=now + timedelta(days=15),
        enrolled_by="admin",
        stripe_subscription_id="sub_ok"
    )

    test_db.add_all([mem_30, mem_7, mem_grace, mem_ok])
    test_db.commit()

    # Invoke daily cron handler directly
    result = membership_reminder.handler(event={}, context=None)
    assert result["status"] == "success"
    assert result["notifications_sent"] == 3
