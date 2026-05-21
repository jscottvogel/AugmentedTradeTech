import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal, set_rls_context
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer, Equipment
from apps.api.app.models.job import Job, JobTechnician
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.ai import AIRequest
from apps.api.app.routers.auth import create_access_token

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    db.execute(text(
        "TRUNCATE refresh_tokens, magic_link_tokens, invoices, availability_status_logs, "
        "job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, "
        "users, companies, ai_requests, equipment_customers, equipment, job_photos, job_embeddings CASCADE;"
    ))
    db.commit()

    # Seed Company
    comp = Company(
        id="comp_test",
        name="Test Company",
        slug="test-company",
        timezone="America/Chicago",
        job_number_seq=100
    )
    db.add(comp)
    db.commit()

    # Seed Users
    tech = User(
        id="usr_tech",
        company_id="comp_test",
        email="tech@test.com",
        full_name="Tech User",
        role="tech",
        is_active=True
    )
    tech2 = User(
        id="usr_tech2",
        company_id="comp_test",
        email="tech2@test.com",
        full_name="Other Tech User",
        role="tech",
        is_active=True
    )
    admin = User(
        id="usr_admin",
        company_id="comp_test",
        email="admin@test.com",
        full_name="Admin User",
        role="company_admin",
        is_active=True
    )
    db.add_all([tech, tech2, admin])
    db.commit()

    # Seed Tech Profiles
    tp = TechProfile(
        id="tprf_tech",
        user_id="usr_tech",
        company_id="comp_test",
        availability_status="available",
        trades=["HVAC"]
    )
    tp2 = TechProfile(
        id="tprf_tech2",
        user_id="usr_tech2",
        company_id="comp_test",
        availability_status="available",
        trades=["HVAC"]
    )
    db.add_all([tp, tp2])
    db.commit()

    # Seed Customer & Equipment
    cust = Customer(id="cust_1", company_id="comp_test", first_name="John", last_name="Doe", email="john@test.com")
    equip = Equipment(id="eq_1", company_id="comp_test", make="Carrier", model="58SB0A", serial_number="SN12345", equipment_type="furnace", trade="HVAC")
    db.add_all([cust, equip])
    db.commit()

    # Seed Job
    job = Job(
        id="job_1",
        company_id="comp_test",
        job_number=101,
        reported_problem="AC blowing warm air",
        status="in_progress",
        trade="HVAC",
        job_type="service",
        customer_id="cust_1",
        equipment_id="eq_1",
        inspection_data={
            "refrigerant_pressures": {
                "skipped": False,
                "inputs": {"suction_pressure": 110, "liquid_pressure": 320}
            }
        }
    )
    db.add(job)
    db.commit()

    # Assign tech to Job
    job_tech = JobTechnician(
        id="jt_1",
        company_id="comp_test",
        job_id="job_1",
        tech_id="usr_tech",
        is_lead=True
    )
    db.add(job_tech)
    db.commit()

    yield db
    db.close()


def test_ai_chat_unauthenticated(test_db):
    """Should return 401 Unauthenticated for requests without valid token."""
    response = client.post("/ai/chat", json={
        "job_id": "job_1",
        "messages": [{"role": "user", "content": "Hello"}]
    })
    assert response.status_code == 401


def test_ai_chat_nonexistent_job(test_db):
    """Should return 404 Not Found for non-existent job."""
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    response = client.post(
        "/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "job_id": "nonexistent_job",
            "messages": [{"role": "user", "content": "Hello"}]
        }
    )
    assert response.status_code == 404


def test_ai_chat_unassigned_tech(test_db):
    """Tech not assigned to the job should receive a 403 Forbidden."""
    token = create_access_token("usr_tech2", "comp_test", "tech", "tech2@test.com", True)
    response = client.post(
        "/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "job_id": "job_1",
            "messages": [{"role": "user", "content": "Hello"}]
        }
    )
    assert response.status_code == 403


def test_ai_chat_authorized_streaming_and_logging(test_db):
    """Assigned tech or admin should receive a 200 SSE stream, and an AIRequest should be logged."""
    token = create_access_token("usr_tech", "comp_test", "tech", "tech@test.com", True)
    
    # 1. Trigger the chat request
    response = client.post(
        "/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "job_id": "job_1",
            "messages": [
                {"role": "user", "content": "My suction pressure is 110 PSI."}
            ]
        }
    )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    # 2. Parse stream chunks
    lines = response.content.decode("utf-8").split("\n\n")
    received_text = ""
    for line in lines:
        if line.startswith("data:"):
            payload = json.loads(line[5:])
            if "text" in payload:
                received_text += payload["text"]
            if "error" in payload:
                pytest.fail(f"Stream returned error: {payload['error']}")
                
    assert len(received_text) > 0
    assert "Carrier 58SB0A" in received_text or "suction_pressure" in received_text or "HVAC" in received_text
    
    # 3. Verify request log in AIRequest
    db = SessionLocal()
    set_rls_context(db, "comp_test", None, "system")
    logs = db.scalars(select(AIRequest).where(AIRequest.job_id == "job_1")).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.request_type == "senior_tech_chat"
    assert log.status == "success"
    assert log.user_id == "usr_tech"
    db.close()
