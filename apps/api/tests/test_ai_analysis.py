import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.ai import AIRequest
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer
from apps.api.app.models.job import Job, JobPhoto
from apps.api.app.models.user import User, TechProfile
from apps.api.app.routers.auth import create_access_token
from apps.api.app.routers.ai import CONCURRENT_REQUESTS

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    db.execute(text(
        "TRUNCATE refresh_tokens, magic_link_tokens, invoices, availability_status_logs, "
        "job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, "
        "users, companies, ai_requests, equipment_customers, equipment, job_photos CASCADE;"
    ))
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
    db.add_all([admin, tech])
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


def test_ai_photo_analyses(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    # Create Job
    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }
    job_id = client.post("/jobs", json=job_data, headers=admin_headers).json()["id"]

    # Add Equipment to Job
    equipment = Equipment(
        id="eq_test",
        company_id="comp_test",
        trade="hvac",
        equipment_type="split_ac",
        make="Old Make",
        model="Old Model",
        serial_number="Old Serial"
    )
    test_db.add(equipment)
    test_db.commit()

    job_row = test_db.scalar(select(Job).where(Job.id == job_id))
    job_row.equipment_id = "eq_test"
    test_db.commit()

    # Register Photos
    photo1 = JobPhoto(
        id="jph_nameplate",
        company_id="comp_test",
        job_id=job_id,
        tech_id="usr_tech",
        photo_type="nameplate",
        s3_key="comp_test/job_id/nameplate/jph_nameplate.jpg",
        cdn_url="https://media.augmentedtradetech.com/comp_test/job_id/nameplate/jph_nameplate.jpg"
    )
    photo2 = JobPhoto(
        id="jph_fault",
        company_id="comp_test",
        job_id=job_id,
        tech_id="usr_tech",
        photo_type="fault",
        s3_key="comp_test/job_id/fault/jph_fault.jpg",
        cdn_url="https://media.augmentedtradetech.com/comp_test/job_id/fault/jph_fault.jpg"
    )
    test_db.add_all([photo1, photo2])
    test_db.commit()

    # 1. Test Nameplate Scan Analysis
    payload = {
        "photo_id": "jph_nameplate",
        "analysis_type": "nameplate_scan",
        "job_id": job_id
    }
    response = client.post("/ai/analyze-photo", json=payload, headers=tech_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["make"]["value"] == "Carrier"
    assert res_data["model"]["value"] == "58SB0A045E14--12"
    assert res_data["serial_number"]["value"] == "1218A12345"
    assert res_data["prompt_retake"] is False

    # Check JobPhoto.ai_analysis stored successfully
    test_db.refresh(photo1)
    assert photo1.ai_analysis is not None
    assert photo1.ai_analysis["make"]["value"] == "Carrier"

    # Check Equipment fields got auto-populated
    test_db.refresh(equipment)
    assert equipment.make == "Carrier"
    assert equipment.model == "58SB0A045E14--12"
    assert equipment.serial_number == "1218A12345"

    # Check AIRequest log
    ai_req = test_db.scalar(select(AIRequest).where(AIRequest.job_id == job_id))
    assert ai_req is not None
    assert ai_req.request_type == "nameplate_scan"
    assert ai_req.status == "success"
    assert ai_req.input_tokens > 0
    assert ai_req.output_tokens > 0
    assert ai_req.cost_usd_micro > 0

    # 2. Test Fault/Damage Analysis
    payload_fault = {
        "photo_id": "jph_fault",
        "analysis_type": "fault_analysis",
        "job_id": job_id
    }
    response_fault = client.post("/ai/analyze-photo", json=payload_fault, headers=tech_headers)
    assert response_fault.status_code == 200
    res_fault = response_fault.json()
    assert res_fault["component_type"] == "capacitor"
    assert res_fault["severity"] == "critical"
    assert "safety_concerns" in res_fault


def test_blurry_photo_handling(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    job_data = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }
    job_id = client.post("/jobs", json=job_data, headers=admin_headers).json()["id"]

    # Blurry Photo
    photo_blurry = JobPhoto(
        id="jph_blurry",
        company_id="comp_test",
        job_id=job_id,
        tech_id="usr_tech",
        photo_type="nameplate",
        s3_key="comp_test/job_id/nameplate/blurry.jpg",
        cdn_url="https://media.augmentedtradetech.com/comp_test/job_id/nameplate/blurry.jpg",
        caption="very blurry close up"
    )
    test_db.add(photo_blurry)
    test_db.commit()

    payload = {
        "photo_id": "jph_blurry",
        "analysis_type": "nameplate_scan",
        "job_id": job_id
    }
    response = client.post("/ai/analyze-photo", json=payload, headers=tech_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["prompt_retake"] is True
    assert "blurry" in res_data["message"].lower()
    assert res_data["make"]["value"] is None
    assert res_data["make"]["confidence"] == 0.0


def test_rate_limit(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    job_id = client.post("/jobs", json={
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }, headers=admin_headers).json()["id"]

    photo = JobPhoto(
        id="jph_rate_limit",
        company_id="comp_test",
        job_id=job_id,
        tech_id="usr_tech",
        photo_type="nameplate",
        s3_key="comp_test/job_id/nameplate/rate_limit.jpg",
        cdn_url="https://media.augmentedtradetech.com/comp_test/job_id/nameplate/rate_limit.jpg"
    )
    test_db.add(photo)
    test_db.commit()

    # Add 10 mock entries in ai_requests for this job
    for i in range(10):
        req = AIRequest(
            id=f"ai_mock_{i}",
            company_id="comp_test",
            user_id="usr_tech",
            job_id=job_id,
            request_type="nameplate_scan",
            model="claude-3-5-sonnet",
            feature_tag="photo_analysis",
            status="success"
        )
        test_db.add(req)
    test_db.commit()

    # 11th request should exceed rate limit (429)
    payload = {
        "photo_id": "jph_rate_limit",
        "analysis_type": "nameplate_scan",
        "job_id": job_id
    }
    response = client.post("/ai/analyze-photo", json=payload, headers=tech_headers)
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]


def test_concurrency_queue(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    job_id = client.post("/jobs", json={
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }, headers=admin_headers).json()["id"]

    photo = JobPhoto(
        id="jph_concur",
        company_id="comp_test",
        job_id=job_id,
        tech_id="usr_tech",
        photo_type="nameplate",
        s3_key="comp_test/job_id/nameplate/concur.jpg",
        cdn_url="https://media.augmentedtradetech.com/comp_test/job_id/nameplate/concur.jpg"
    )
    test_db.add(photo)
    test_db.commit()

    # Modify concurrent requests count to 5
    import apps.api.app.routers.ai as ai_router
    ai_router.CONCURRENT_REQUESTS = 5

    payload = {
        "photo_id": "jph_concur",
        "analysis_type": "nameplate_scan",
        "job_id": job_id
    }
    response = client.post("/ai/analyze-photo", json=payload, headers=tech_headers)
    
    # Reset concurrency counter
    ai_router.CONCURRENT_REQUESTS = 0

    assert response.status_code == 202
    res_data = response.json()
    assert res_data["status"] == "queued"
    assert "ai-queue" in res_data["message"]


def test_analyze_nameplate_convenience(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    job_id = client.post("/jobs", json={
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "tech_id": "usr_tech"
    }, headers=admin_headers).json()["id"]

    equipment = Equipment(
        id="eq_conv",
        company_id="comp_test",
        trade="hvac",
        equipment_type="split_ac",
        make="Old Make",
        model="Old Model",
        serial_number="Old Serial"
    )
    test_db.add(equipment)

    photo = JobPhoto(
        id="jph_conv",
        company_id="comp_test",
        job_id=job_id,
        tech_id="usr_tech",
        photo_type="nameplate",
        s3_key="comp_test/job_id/nameplate/conv.jpg",
        cdn_url="https://media.augmentedtradetech.com/comp_test/job_id/nameplate/conv.jpg"
    )
    test_db.add(photo)
    test_db.commit()

    # Call convenience endpoint
    payload = {
        "photo_id": "jph_conv",
        "job_id": job_id,
        "equipment_id": "eq_conv"
    }
    response = client.post("/ai/analyze-nameplate", json=payload, headers=tech_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["make"]["value"] == "Carrier"

    # Verify equipment patched
    test_db.refresh(equipment)
    assert equipment.make == "Carrier"
    assert equipment.model == "58SB0A045E14--12"
    assert equipment.serial_number == "1218A12345"


def test_patch_equipment(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")

    equipment = Equipment(
        id="eq_patch",
        company_id="comp_test",
        trade="hvac",
        equipment_type="split_ac",
        make="Brand X",
        model="Model Y",
        serial_number="Serial Z"
    )
    test_db.add(equipment)
    test_db.commit()

    payload = {
        "make": "Brand New Make",
        "model": "Brand New Model",
        "ai_extracted_data": {"extracted_at": "2026-05-20"}
    }
    response = client.patch("/equipment/eq_patch", json=payload, headers=tech_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["make"] == "Brand New Make"
    assert res_data["model"] == "Brand New Model"
    assert res_data["serial_number"] == "Serial Z"  # remained unchanged
    assert res_data["ai_extracted_data"]["extracted_at"] == "2026-05-20"
