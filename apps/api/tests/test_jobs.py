import pytest
from datetime import datetime, timezone
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
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, invoices, availability_status_logs, job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, users, companies CASCADE;"))
    db.commit()

    # Seed Company
    comp = Company(
        id="comp_test",
        name="Test Company",
        slug="test-company",
        timezone="America/Chicago",
        job_number_seq=0
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

def test_create_job_permission_and_sequence(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "priority": "routine",
        "reported_problem": "AC blowing hot air"
    }

    # 1. Tech should not be allowed to create job
    response = client.post("/jobs", json=job_data, headers=tech_headers)
    assert response.status_code == 403

    # 2. Admin creates job - generates JOB-[year]-00001
    response = client.post("/jobs", json=job_data, headers=admin_headers)
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["job_number"].endswith("-00001")
    assert res_data["reported_problem"] == "AC blowing hot air"
    assert res_data["status"] == "scheduled"
    assert res_data["customer"]["first_name"] == "Jane"

    # 3. Create second job - generates JOB-[year]-00002
    response = client.post("/jobs", json=job_data, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["job_number"].endswith("-00002")

def test_list_and_get_job_details(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # Create job assigned to usr_tech
    job_data = {
        "customer_id": "cust_test",
        "trade": "garage_door",
        "job_type": "maintenance",
        "tech_id": "usr_tech"
    }
    response = client.post("/jobs", json=job_data, headers=admin_headers)
    assert response.status_code == 201
    job_id = response.json()["id"]

    # Tech lists their jobs - should see it
    response = client.get("/jobs", headers=tech_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == job_id

    # Tech gets job details
    response = client.get(f"/jobs/{job_id}", headers=tech_headers)
    assert response.status_code == 200
    details = response.json()
    assert details["job_number"].endswith("-00001")
    assert len(details["technicians"]) == 1
    assert details["technicians"][0]["tech_id"] == "usr_tech"

def test_status_transitions_and_tech_availability(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # Create job assigned to tech
    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }
    job_res = client.post("/jobs", json=job_data, headers=admin_headers).json()
    job_id = job_res["id"]

    # 1. Invalid status transition: scheduled -> in_progress (must go via confirmed -> en_route -> on_site)
    trans_response = client.post(f"/jobs/{job_id}/status", json={"status": "in_progress"}, headers=tech_headers)
    assert trans_response.status_code == 422

    # 2. Valid status transition: scheduled -> confirmed
    trans_response = client.post(f"/jobs/{job_id}/status", json={"status": "confirmed", "note": "Confirmed with customer"}, headers=tech_headers)
    assert trans_response.status_code == 200
    assert trans_response.json()["status"] == "confirmed"

    # 3. Verify history entry was written
    history = trans_response.json()["status_history"]
    assert len(history) == 2  # creation + confirmed
    assert history[1]["from_status"] == "scheduled"
    assert history[1]["to_status"] == "confirmed"
    assert history[1]["note"] == "Confirmed with customer"

    # 4. Transition: confirmed -> en_route
    client.post(f"/jobs/{job_id}/status", json={"status": "en_route"}, headers=tech_headers)

    # 5. Transition: en_route -> on_site
    # Should automatically set tech availability status to "on_job"
    trans_response = client.post(f"/jobs/{job_id}/status", json={"status": "on_site"}, headers=tech_headers)
    assert trans_response.status_code == 200
    
    tech_prof = test_db.scalar(select(TechProfile).where(TechProfile.user_id == "usr_tech"))
    assert tech_prof.availability_status == "on_job"

    # 6. Transition: on_site -> in_progress -> completed
    client.post(f"/jobs/{job_id}/status", json={"status": "in_progress"}, headers=tech_headers)
    trans_response = client.post(f"/jobs/{job_id}/status", json={"status": "completed"}, headers=tech_headers)
    assert trans_response.status_code == 200
    
    # Tech availability should revert to "available"
    test_db.refresh(tech_prof)
    assert tech_prof.availability_status == "available"

def test_job_parts_management(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # Create job
    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }
    job_id = client.post("/jobs", json=job_data, headers=admin_headers).json()["id"]

    # 1. Add Part
    part_data = {
        "name": "Capacitor 45uF",
        "quantity": 1,
        "price_cents": 4500,
        "serial_number": "CAP12345"
    }
    response = client.post(f"/jobs/{job_id}/parts", json=part_data, headers=tech_headers)
    assert response.status_code == 201
    parts = response.json()["parts"]
    assert len(parts) == 1
    assert parts[0]["name"] == "Capacitor 45uF"
    part_id = parts[0]["id"]

    # 2. Update Part
    part_update = {
        "name": "Capacitor 45uF Upgraded",
        "quantity": 2,
        "price_cents": 5000,
        "serial_number": "CAP12345B"
    }
    response = client.put(f"/jobs/{job_id}/parts/{part_id}", json=part_update, headers=tech_headers)
    assert response.status_code == 200
    parts = response.json()["parts"]
    assert len(parts) == 1
    assert parts[0]["name"] == "Capacitor 45uF Upgraded"
    assert parts[0]["quantity"] == 2
    assert parts[0]["price_cents"] == 5000

    # 3. Delete Part
    response = client.delete(f"/jobs/{job_id}/parts/{part_id}", headers=tech_headers)
    assert response.status_code == 200
    assert len(response.json()["parts"]) == 0


def test_job_photos_management(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    # Create job
    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }
    job_id = client.post("/jobs", json=job_data, headers=admin_headers).json()["id"]

    # 1. Presign URL generation
    presign_payload = {
        "photo_type": "before"
    }
    presign_res = client.post(f"/jobs/{job_id}/photos/presign", json=presign_payload, headers=tech_headers)
    assert presign_res.status_code == 200
    presign_data = presign_res.json()
    assert "upload_url" in presign_data
    assert "s3_key" in presign_data
    assert "headers" in presign_data
    assert presign_data["headers"]["Content-Type"] == "image/jpeg"

    # 2. Register Photo in DB
    s3_key = presign_data["s3_key"]
    register_payload = {
        "s3_key": s3_key,
        "photo_type": "before",
        "caption": "Arrived at site - HVAC inspection before photo",
        "file_size_bytes": 102400,
        "mime_type": "image/jpeg"
    }
    reg_res = client.post(f"/jobs/{job_id}/photos", json=register_payload, headers=tech_headers)
    assert reg_res.status_code == 201
    job_data = reg_res.json()
    assert len(job_data["photos"]) == 1
    photo = job_data["photos"][0]
    assert photo["photo_type"] == "before"
    assert photo["caption"] == "Arrived at site - HVAC inspection before photo"
    assert "cdn_url" in photo
    photo_id = photo["id"]

    # 3. List photos via GET /jobs/:id/photos
    list_res = client.get(f"/jobs/{job_id}/photos", headers=tech_headers)
    assert list_res.status_code == 200
    photos_list = list_res.json()
    assert len(photos_list) == 1
    assert photos_list[0]["id"] == photo_id
    assert "cdn_url" in photos_list[0]

    # 4. Soft Delete Photo via DELETE /jobs/:id/photos/:photo_id
    del_res = client.delete(f"/jobs/{job_id}/photos/{photo_id}", headers=tech_headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 5. Verify the photo is no longer listed in /jobs/:id/photos
    list_res = client.get(f"/jobs/{job_id}/photos", headers=tech_headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 0

    # 6. Verify the photo is no longer in serialized Job response
    job_res = client.get(f"/jobs/{job_id}", headers=tech_headers)
    assert job_res.status_code == 200
    assert len(job_res.json()["photos"]) == 0

