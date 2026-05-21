import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal

# Import all models to register them in Base.metadata
from apps.api.app.models.ai import JobEmbedding, AIRequest
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer, EquipmentCustomer, Equipment
from apps.api.app.models.dispatch import JobPool, TechLocationPing
from apps.api.app.models.invoice import Invoice, InvoiceLineItem
from apps.api.app.models.job import Job, JobTechnician, JobPhoto, JobNote, JobStatusHistory, JobPart
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.sync import SyncQueue
from apps.api.app.models.user import User, TechProfile, AvailabilityStatusLog

from apps.api.app.routers.auth import create_access_token
from apps.api.app.core.workflows import DEFAULT_WORKFLOW_CONFIG

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, invoices, availability_status_logs, job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, users, companies, ai_requests, equipment_customers, equipment, memberships, membership_plans CASCADE;"))
    db.commit()

    # Seed Company
    comp = Company(
        id="comp_test",
        name="Test Company",
        slug="test-company",
        timezone="America/Chicago",
        job_number_seq=0,
        workflow_config=DEFAULT_WORKFLOW_CONFIG
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
    unassigned_tech = User(
        id="usr_tech_unassigned",
        company_id="comp_test",
        email="tech_unassigned@test.com",
        full_name="Unassigned Tech User",
        role="tech",
        is_active=True
    )
    db.add_all([admin, tech, unassigned_tech])
    db.commit()

    # Seed Customer
    cust = Customer(
        id="cust_test",
        company_id="comp_test",
        first_name="Alice",
        last_name="Smith",
        email="alice@smith.com",
        phone="555-0199",
        customer_type="residential"
    )
    db.add(cust)
    db.commit()

    # Seed Job
    job = Job(
        id="job_test",
        company_id="comp_test",
        customer_id="cust_test",
        trade="hvac",
        job_type="service",
        priority="routine",
        status="scheduled",
        source="phone"
    )
    db.add(job)
    db.commit()

    # Assign tech to job
    jt = JobTechnician(
        id="jt_test",
        company_id="comp_test",
        job_id="job_test",
        tech_id="usr_tech",
        is_lead=True
    )
    db.add(jt)
    db.commit()

    yield db
    db.close()


def test_get_workflow_unauthorized(test_db):
    response = client.get("/jobs/job_test/workflow")
    assert response.status_code == 401


def test_get_workflow_not_assigned_tech(test_db):
    token = create_access_token("usr_tech_unassigned", "comp_test", "tech", "tech_unassigned@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/jobs/job_test/workflow", headers=headers)
    assert response.status_code == 403


def test_get_workflow_success_admin(test_db):
    token = create_access_token("usr_admin", "comp_test", "company_admin", "admin@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/jobs/job_test/workflow", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["trade"] == "hvac"
    assert len(data["steps"]) == 12
    assert data["progress"] == {}


def test_put_workflow_step_validation(test_db):
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Put with invalid step key
    response = client.put(
        "/jobs/job_test/workflow/invalid_step_key",
        headers=headers,
        json={"inputs": {}, "idempotency_key": "ik_1"}
    )
    assert response.status_code == 400
    assert "Invalid step key" in response.json()["detail"]


def test_put_workflow_step_idempotent(test_db):
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "inputs": {"symptoms_confirmed": True, "access_notes": "Gate code #1234"},
        "idempotency_key": "ik_idempotent_test"
    }

    # First Put
    response1 = client.put(
        "/jobs/job_test/workflow/arrive_on_site",
        headers=headers,
        json=payload
    )
    assert response1.status_code == 200
    res_data1 = response1.json()
    assert res_data1["status"] == "success"
    assert res_data1["step_data"]["inputs"]["access_notes"] == "Gate code #1234"
    completed_at = res_data1["step_data"]["completed_at"]
    assert completed_at is not None

    # Second Put (Idempotent Retry)
    response2 = client.put(
        "/jobs/job_test/workflow/arrive_on_site",
        headers=headers,
        json=payload
    )
    assert response2.status_code == 200
    res_data2 = response2.json()
    assert "Idempotent request" in res_data2["message"]
    # Ensure completed_at is exactly the same timestamp (no update occurred)
    assert res_data2["step_data"]["completed_at"] == completed_at


def test_post_workflow_ai_equipment_id(test_db):
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}

    # Put step inputs first
    client.put(
        "/jobs/job_test/workflow/equipment_id",
        headers=headers,
        json={
            "inputs": {"nameplate_photo_url": "https://cdn.example.com/nameplate.jpg"},
            "idempotency_key": "ik_equip"
        }
    )

    # Post to AI
    response = client.post("/jobs/job_test/workflow/equipment_id/ai", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["step_data"]["ai_result"]["make"] == "Carrier"
    assert data["step_data"]["ai_result"]["serial_number"] == "1819A12345"

    # Verify database: Equipment should be auto-created and linked
    job = test_db.scalar(select(Job).where(Job.id == "job_test"))
    assert job.equipment_id is not None
    
    equipment = test_db.scalar(select(Equipment).where(Equipment.id == job.equipment_id))
    assert equipment.make == "Carrier"
    assert equipment.serial_number == "1819A12345"

    # Verify EquipmentCustomer link
    link = test_db.scalar(select(EquipmentCustomer).where(EquipmentCustomer.equipment_id == equipment.id))
    assert link is not None
    assert link.customer_id == "cust_test"

    # Verify AI Request log exists
    ai_req = test_db.scalar(select(AIRequest).where(AIRequest.job_id == "job_test"))
    assert ai_req is not None
    assert ai_req.request_type == "nameplate_scan"


def test_post_workflow_ai_pressures_and_temperatures(test_db):
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Refrigerant Pressures
    client.put(
        "/jobs/job_test/workflow/refrigerant_pressures",
        headers=headers,
        json={
            "inputs": {"suction_pressure": 130.0, "discharge_pressure": 340.0},
            "idempotency_key": "ik_press"
        }
    )
    response_p = client.post("/jobs/job_test/workflow/refrigerant_pressures/ai", headers=headers)
    assert response_p.status_code == 200
    assert response_p.json()["step_data"]["ai_result"]["calculated_superheat_f"] == 12.0

    # 2. Temperature Readings
    client.put(
        "/jobs/job_test/workflow/temperature_readings",
        headers=headers,
        json={
            "inputs": {"supply_temp": 54.0, "return_temp": 74.0},
            "idempotency_key": "ik_temps"
        }
    )
    response_t = client.post("/jobs/job_test/workflow/temperature_readings/ai", headers=headers)
    assert response_t.status_code == 200
    ai_t_res = response_t.json()["step_data"]["ai_result"]
    assert ai_t_res["calculated_delta_t"] == 20.0
    assert ai_t_res["status"] == "normal"


def test_post_workflow_ai_diagnosis(test_db):
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}

    # AI Diagnosis step is of type "ai_trigger" which doesn't require separate inputs
    response = client.post("/jobs/job_test/workflow/ai_diagnosis/ai", headers=headers)
    assert response.status_code == 200
    ai_diag = response.json()["step_data"]["ai_result"]
    assert "diagnostic_summary" in ai_diag
    assert len(ai_diag["recommended_actions"]) > 0


def test_put_workflow_retains_existing_ai_result(test_db):
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}

    # Save inputs
    client.put(
        "/jobs/job_test/workflow/arrive_on_site",
        headers=headers,
        json={"inputs": {"symptoms_confirmed": True}, "idempotency_key": "ik_diag_1"}
    )
    # Trigger AI
    response_ai = client.post("/jobs/job_test/workflow/arrive_on_site/ai", headers=headers)
    assert response_ai.status_code == 200
    ai_res = response_ai.json()["step_data"]["ai_result"]
    assert ai_res is not None

    # Update inputs with new idempotency key
    response_update = client.put(
        "/jobs/job_test/workflow/arrive_on_site",
        headers=headers,
        json={"inputs": {"symptoms_confirmed": True, "notes": "Updated notes"}, "idempotency_key": "ik_diag_2"}
    )
    assert response_update.status_code == 200
    updated_data = response_update.json()["step_data"]
    assert updated_data["inputs"]["notes"] == "Updated notes"
    # Ensure ai_result is retained!
    assert updated_data["ai_result"] == ai_res
