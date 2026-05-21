import pytest
import json
import jwt
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer
from apps.api.app.models.invoice import Invoice, InvoiceLineItem
from apps.api.app.models.job import Job
from apps.api.app.models.sync import SyncQueue
from apps.api.app.models.ai import AuditLog
from apps.api.app.routers.auth import JWT_SECRET, ALGORITHM
from apps.api.tests.test_invoices import test_db, get_auth_headers
from apps.api.app.cron.qbo_sync_worker import handler as qbo_worker_handler

client = TestClient(app)

def test_qbo_connect_redirect(test_db):
    headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    resp = client.post("/integrations/qbo/connect", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    # In mock mode / sandbox mode, connect should return a redirect URL pointing back to the frontend with mock parameters
    assert "mock_callback=true" in data["url"]

def test_qbo_callback_and_disconnect(test_db):
    # Set mock_realm_id on company first to trigger mock client
    comp = test_db.scalar(select(Company).where(Company.id == "comp_test"))
    comp.qbo_realm_id = "mock_realm_123"
    test_db.add(comp)
    test_db.commit()

    # Generate valid state JWT token
    state_payload = {
        "company_id": "comp_test",
        "user_id": "usr_admin",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    state_token = jwt.encode(state_payload, JWT_SECRET, algorithm=ALGORITHM)

    # Call callback endpoint (public path)
    resp = client.get(
        f"/integrations/qbo/callback?code=mock_code&realmId=mock_realm_123&state={state_token}",
        follow_redirects=False
    )
    assert resp.status_code == 307  # RedirectResponse
    assert "/settings/integrations?status=success" in resp.headers["location"]

    # Check tokens saved in db
    test_db.expire_all()
    comp = test_db.scalar(select(Company).where(Company.id == "comp_test"))
    assert comp.qbo_access_token == "mock_access_token_xyz"
    assert comp.qbo_refresh_token == "mock_refresh_token_123"

    # Now call status
    headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    status_resp = client.get("/integrations/qbo/status", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["connected"] is True
    assert status_data["realm_id"] == "mock_realm_123"

    # Call disconnect
    disc_resp = client.post("/integrations/qbo/disconnect", headers=headers)
    assert disc_resp.status_code == 200
    assert disc_resp.json()["status"] == "success"

    # Check status again
    status_resp = client.get("/integrations/qbo/status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["connected"] is False
    assert status_resp.json()["realm_id"] is None

def test_qbo_mappings_update(test_db):
    headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    
    mapping_payload = {
        "labor": "My Labor Item",
        "part_fallback": "My Parts Fallback",
        "fee": "My Fee Item"
    }
    resp = client.put("/integrations/qbo/mappings", json=mapping_payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Check DB
    test_db.expire_all()
    comp = test_db.scalar(select(Company).where(Company.id == "comp_test"))
    assert comp.qbo_item_mappings["labor"] == "My Labor Item"
    assert comp.qbo_item_mappings["part_fallback"] == "My Parts Fallback"
    assert comp.qbo_item_mappings["fee"] == "My Fee Item"

    # Get status and verify
    status_resp = client.get("/integrations/qbo/status", headers=headers)
    assert status_resp.json()["item_mappings"]["labor"] == "My Labor Item"

def test_qbo_sync_pipeline(test_db):
    headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # Connect company in mock mode
    comp = test_db.scalar(select(Company).where(Company.id == "comp_test"))
    comp.qbo_realm_id = "mock_realm_abc"
    comp.qbo_access_token = "mock_access_token_xyz"
    comp.qbo_refresh_token = "mock_refresh_token_123"
    comp.qbo_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    test_db.add(comp)

    # Seed Job
    job = Job(
        id="job_test_qbo",
        company_id="comp_test",
        customer_id="cust_test",
        trade="hvac",
        job_type="service",
        reported_problem="AC Issue",
        status="completed"
    )
    test_db.add(job)
    test_db.flush()

    # Seed Paid Invoice
    invoice = Invoice(
        id="inv_test_qbo",
        company_id="comp_test",
        job_id="job_test_qbo",
        customer_id="cust_test",
        invoice_number="INV-2001",
        status="paid",
        subtotal_cents=15000,
        tax_cents=1237,
        total_cents=16237,
        amount_paid_cents=16237,
        due_date=datetime.now(timezone.utc).date()
    )
    test_db.add(invoice)
    test_db.flush()

    # Add line items
    item1 = InvoiceLineItem(
        id="ili_1",
        company_id="comp_test",
        invoice_id="inv_test_qbo",
        line_type="labor",
        description="Fixing AC Units",
        quantity=1.5,
        unit_price_cents=10000,
        is_taxable=True
    )
    test_db.add(item1)
    test_db.commit()

    # Trigger manual resync
    sync_resp = client.post("/integrations/qbo/sync/inv_test_qbo", headers=headers)
    assert sync_resp.status_code == 200
    assert sync_resp.json()["status"] == "success"

    # Verify SyncQueue entry is present and pending
    sync_entry = test_db.scalar(select(SyncQueue).where(SyncQueue.entity_id == "inv_test_qbo"))
    assert sync_entry is not None
    assert sync_entry.status == "pending"

    # Execute Lambda sync worker manually
    event = {
        "Records": [
            {
                "body": json.dumps({
                    "action": "quickbooks_sync",
                    "invoice_id": "inv_test_qbo",
                    "company_id": "comp_test"
                })
            }
        ]
    }
    worker_res = qbo_worker_handler(event, None)
    assert worker_res["status"] == "success"

    # Verify Invoice was updated with mock QBO ID and SyncQueue entry succeeded
    test_db.expire_all()
    updated_inv = test_db.scalar(select(Invoice).where(Invoice.id == "inv_test_qbo"))
    assert updated_inv.qbo_invoice_id == "mock_qbo_inv_inv_test_qbo"

    updated_sync = test_db.scalar(select(SyncQueue).where(SyncQueue.entity_id == "inv_test_qbo"))
    assert updated_sync.status == "applied"
    assert updated_sync.server_response["qbo_invoice_id"] == "mock_qbo_inv_inv_test_qbo"
    assert updated_sync.server_response["qbo_customer_id"] == "mock_qbo_cust_cust_test"

def test_qbo_sync_failure_handling(test_db):
    headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # Connect company in mock mode
    comp = test_db.scalar(select(Company).where(Company.id == "comp_test"))
    comp.qbo_realm_id = "mock_realm_abc"
    comp.qbo_access_token = "mock_access_token_xyz"
    comp.qbo_refresh_token = "mock_refresh_token_123"
    comp.qbo_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    test_db.add(comp)

    # Seed Job
    job = Job(
        id="job_test_qbo_fail",
        company_id="comp_test",
        customer_id="cust_test",
        trade="hvac",
        job_type="service",
        reported_problem="AC Issue",
        status="completed"
    )
    test_db.add(job)
    test_db.flush()

    # Seed Draft Invoice (status not paid, which will cause worker validation failure)
    invoice = Invoice(
        id="inv_test_qbo_fail",
        company_id="comp_test",
        job_id="job_test_qbo_fail",
        customer_id="cust_test",
        invoice_number="INV-2002",
        status="draft",
        subtotal_cents=10000,
        tax_cents=825,
        total_cents=10825,
        amount_paid_cents=0,
    )
    test_db.add(invoice)
    test_db.commit()

    # Trigger manual resync via POST should reject it since invoice is not paid
    sync_resp = client.post("/integrations/qbo/sync/inv_test_qbo_fail", headers=headers)
    assert sync_resp.status_code == 400
    assert "Only paid invoices" in sync_resp.json()["detail"]

    # Let's manually create a SyncQueue entry and run worker to simulate validation failure
    # (e.g. if status changes after enqueuing)
    sync_entry = SyncQueue(
        id="sy_fail_test",
        company_id="comp_test",
        user_id="usr_admin",
        entity_type="invoice",
        entity_id="inv_test_qbo_fail",
        operation="create",
        payload={"invoice_id": "inv_test_qbo_fail"},
        client_timestamp=datetime.now(timezone.utc),
        idempotency_key="qbo_sync_inv_test_qbo_fail",
        status="pending"
    )
    test_db.add(sync_entry)
    test_db.commit()

    # Execute Lambda sync worker
    event = {
        "Records": [
            {
                "body": json.dumps({
                    "action": "quickbooks_sync",
                    "invoice_id": "inv_test_qbo_fail",
                    "company_id": "comp_test"
                })
            }
        ]
    }
    worker_res = qbo_worker_handler(event, None)
    assert worker_res["status"] == "success"

    # Verify SyncQueue status updated to "failed" and details saved
    test_db.expire_all()
    updated_sync = test_db.scalar(select(SyncQueue).where(SyncQueue.entity_id == "inv_test_qbo_fail"))
    assert updated_sync.status == "failed"
    assert "QBO sync requires status 'paid'" in updated_sync.conflict_detail["error"]

    # Verify AuditLog created
    audit = test_db.scalar(
        select(AuditLog)
        .where(AuditLog.entity_id == "inv_test_qbo_fail")
        .where(AuditLog.action == "quickbooks.sync_failed")
    )
    assert audit is not None
    assert "QBO sync requires status 'paid'" in audit.after_state["error"]
