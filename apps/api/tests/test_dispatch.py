import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal

# Import all models to register them in Base.metadata
from apps.api.app.models.ai import JobEmbedding, AIRequest  # type: ignore
from apps.api.app.models.company import Company  # type: ignore
from apps.api.app.models.customer import Customer, EquipmentCustomer, Equipment  # type: ignore
from apps.api.app.models.dispatch import JobPool, TechLocationPing  # type: ignore
from apps.api.app.models.invoice import Invoice, InvoiceLineItem  # type: ignore
from apps.api.app.models.job import Job, JobTechnician, JobPhoto, JobNote, JobStatusHistory, JobPart  # type: ignore
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger  # type: ignore
from apps.api.app.models.membership import MembershipPlan, Membership  # type: ignore
from apps.api.app.models.sync import SyncQueue  # type: ignore
from apps.api.app.models.user import User, TechProfile, AvailabilityStatusLog  # type: ignore
from apps.api.app.routers.auth import create_access_token

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    # Clean database tables
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, invoices, availability_status_logs, job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, users, companies CASCADE;"))
    db.commit()

    # Seed Company
    comp = Company(
        id="comp_dispatch_test",
        name="Dispatch Test Company",
        slug="dispatch-test-company",
        timezone="UTC",
        job_number_seq=0
    )
    db.add(comp)
    db.commit()

    # Seed Users
    disp = User(
        id="usr_disp_test",
        company_id="comp_dispatch_test",
        email="dispatcher@test.com",
        full_name="Dispatcher Jack",
        role="dispatcher",
        is_active=True
    )
    tech = User(
        id="usr_tech_test",
        company_id="comp_dispatch_test",
        email="tech_john@test.com",
        full_name="Tech John",
        role="tech",
        is_active=True
    )
    db.add_all([disp, tech])
    db.commit()

    # Tech Profile
    tprf = TechProfile(
        id="tprf_john",
        user_id="usr_tech_test",
        company_id="comp_dispatch_test",
        availability_status="available",
        trades=["hvac"]
    )
    db.add(tprf)
    db.commit()

    # Seed Customers
    cust = Customer(
        id="cust_test_1",
        company_id="comp_dispatch_test",
        first_name="Jane",
        last_name="Doe",
        phone="5551112222",
        email="jane.doe@example.com",
        address_line1="100 Test Blvd",
        city="Dallas",
        state="TX",
        zip="75201"
    )
    db.add(cust)
    db.commit()

    yield db
    db.close()

def get_auth_headers(user_id: str, email: str, role: str, company_id: str = "comp_dispatch_test"):
    token = create_access_token(user_id, company_id, role, email, True)
    return {"Authorization": f"Bearer {token}"}

def test_create_and_search_customers(test_db):
    headers = get_auth_headers("usr_disp_test", "dispatcher@test.com", "dispatcher")

    # 1. Create a customer
    create_payload = {
        "first_name": "Bob",
        "last_name": "Smith",
        "email": "bob.smith@example.com",
        "phone": "5552223333",
        "address_line1": "200 Oak Ave",
        "city": "Plano",
        "state": "TX",
        "zip": "75023",
        "customer_type": "residential",
        "notes": "Gate code is 4432"
    }
    res = client.post("/customers", json=create_payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["first_name"] == "Bob"
    assert data["last_name"] == "Smith"
    assert "id" in data

    # 2. Search customer by query
    res = client.get("/customers?q=Bob", headers=headers)
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["first_name"] == "Bob"

    # Search by partial phone
    res = client.get("/customers?q=555222", headers=headers)
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["last_name"] == "Smith"

def test_customer_detail_and_job_history(test_db):
    headers = get_auth_headers("usr_disp_test", "dispatcher@test.com", "dispatcher")

    # Seed a job for customer cust_test_1
    job = Job(
        id="job_test_hist",
        company_id="comp_dispatch_test",
        customer_id="cust_test_1",
        job_number="JOB-2026-9999",
        trade="hvac",
        job_type="service",
        priority="urgent",
        status="scheduled",
        scheduled_start=datetime.now(timezone.utc)
    )
    test_db.add(job)
    test_db.commit()

    res = client.get("/customers/cust_test_1", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["first_name"] == "Jane"
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_number"].startswith("JOB-")

def test_dispatch_board_grouping(test_db):
    headers = get_auth_headers("usr_disp_test", "dispatcher@test.com", "dispatcher")

    # Create two jobs for today
    today_dt = datetime.now(timezone.utc)
    
    # Job 1: Unassigned scheduled job
    job1 = Job(
        id="job_unassigned_test",
        company_id="comp_dispatch_test",
        customer_id="cust_test_1",
        job_number="JOB-2026-0001",
        trade="hvac",
        job_type="service",
        priority="routine",
        status="scheduled",
        scheduled_start=today_dt
    )
    # Job 2: Assigned in-progress job
    job2 = Job(
        id="job_assigned_test",
        company_id="comp_dispatch_test",
        customer_id="cust_test_1",
        job_number="JOB-2026-0002",
        trade="hvac",
        job_type="service",
        priority="emergency",
        status="in_progress",
        scheduled_start=today_dt
    )
    test_db.add_all([job1, job2])
    test_db.commit()

    # Assign tech to job 2
    jt = JobTechnician(
        id="jt_test_assign",
        company_id="comp_dispatch_test",
        job_id="job_assigned_test",
        tech_id="usr_tech_test",
        is_lead=True
    )
    test_db.add(jt)
    test_db.commit()

    # Get dispatch board
    date_str = today_dt.strftime("%Y-%m-%d")
    res = client.get(f"/dispatch/board?date={date_str}", headers=headers)
    assert res.status_code == 200
    board = res.json()

    assert len(board["unassigned"]) == 1
    assert board["unassigned"][0]["id"] == "job_unassigned_test"
    
    assert len(board["in_progress"]) == 1
    assert board["in_progress"][0]["id"] == "job_assigned_test"
    assert board["in_progress"][0]["technicians"][0]["full_name"] == "Tech John"

def test_dispatch_techs_list(test_db):
    headers = get_auth_headers("usr_disp_test", "dispatcher@test.com", "dispatcher")

    # Seed an active assigned job
    today_dt = datetime.now(timezone.utc)
    job = Job(
        id="job_assigned_active",
        company_id="comp_dispatch_test",
        customer_id="cust_test_1",
        job_number="JOB-2026-1010",
        trade="hvac",
        job_type="service",
        priority="routine",
        status="en_route",
        scheduled_start=today_dt
    )
    jt = JobTechnician(
        id="jt_tech_active",
        company_id="comp_dispatch_test",
        job_id="job_assigned_active",
        tech_id="usr_tech_test",
        is_lead=True
    )
    test_db.add_all([job, jt])
    test_db.commit()

    res = client.get("/dispatch/techs", headers=headers)
    assert res.status_code == 200
    techs = res.json()
    assert len(techs) == 1
    assert techs[0]["id"] == "usr_tech_test"
    assert techs[0]["availability_status"] == "available"
    assert techs[0]["active_job"]["id"] == "job_assigned_active"
    assert techs[0]["active_job"]["customer_name"] == "Jane Doe"

def test_dispatch_unassigned_jobs(test_db):
    headers = get_auth_headers("usr_disp_test", "dispatcher@test.com", "dispatcher")

    # Seed an unassigned job
    job = Job(
        id="job_unassigned_only",
        company_id="comp_dispatch_test",
        customer_id="cust_test_1",
        job_number="JOB-2026-1111",
        trade="garage_door",
        job_type="install",
        priority="routine",
        status="scheduled",
        scheduled_start=datetime.now(timezone.utc)
    )
    test_db.add(job)
    test_db.commit()

    res = client.get("/dispatch/unassigned", headers=headers)
    assert res.status_code == 200
    unassigned = res.json()
    assert len(unassigned) == 1
    assert unassigned[0]["id"] == "job_unassigned_only"
    assert unassigned[0]["trade"] == "garage_door"

def test_dispatch_suggest_tech(test_db):
    headers = get_auth_headers("usr_disp_test", "dispatcher@test.com", "dispatcher")

    job = Job(
        id="job_to_suggest",
        company_id="comp_dispatch_test",
        customer_id="cust_test_1",
        job_number="JOB-2026-3030",
        trade="hvac",
        job_type="service",
        priority="routine",
        status="scheduled",
        scheduled_start=datetime.now(timezone.utc)
    )
    test_db.add(job)
    test_db.commit()

    res = client.post("/dispatch/suggest-tech", json={"job_id": "job_to_suggest"}, headers=headers)
    assert res.status_code == 200
    suggestion = res.json()
    assert suggestion["suggested_tech_id"] == "usr_tech_test"
    assert "Tech John" in suggestion["reasoning"]
