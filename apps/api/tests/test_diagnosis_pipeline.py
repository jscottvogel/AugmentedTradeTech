import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal, set_rls_context
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer, Equipment
from apps.api.app.models.job import Job, JobPhoto
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.ai import JobEmbedding, AIRequest
from apps.api.app.routers.auth import create_access_token
from apps.api.app.services.diagnosis_pipeline import run_diagnosis_pipeline

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


@pytest.mark.anyio
async def test_ai_diagnosis_pipeline_e2e(test_db):
    tech_headers = get_auth_headers("usr_tech", "tech@test.com", "tech")
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")

    job_payload = {
        "customer_id": "cust_test",
        "trade": "hvac",
        "job_type": "service",
        "priority": "routine",
        "reported_problem": "System runs but blow warm air. Inspect condenser and coils.",
        "status": "scheduled"
    }
    
    # Enable bypass of RLS for test setups
    set_rls_context(test_db, "comp_test", "usr_admin", "company_admin")
    
    job_res = client.post("/jobs", json=job_payload, headers=admin_headers)
    assert job_res.status_code == 201
    job_id = job_res.json()["id"]

    # Seed Equipment
    eq = Equipment(
        id="eq_test",
        company_id="comp_test",
        trade="hvac",
        equipment_type="AC Unit",
        make="Carrier",
        model="38CKC036",
        serial_number="123456789"
    )
    test_db.add(eq)
    test_db.commit()
    
    # Associate Equipment to Job
    job_obj = test_db.scalar(select(Job).where(Job.id == job_id))
    job_obj.equipment_id = "eq_test"
    
    # Seed out-of-range temperatures delta-T and low suction pressure
    job_obj.inspection_data = {
        "refrigerant_pressures": {
            "inputs": {
                "suction_pressure": 95.0,
                "discharge_pressure": 320.0
            },
            "skipped": False,
            "completed_at": "2026-05-20T12:00:00Z"
        },
        "temperature_readings": {
            "inputs": {
                "supply_temp": 64.0,
                "return_temp": 72.0
            },
            "skipped": False,
            "completed_at": "2026-05-20T12:05:00Z"
        }
    }
    test_db.commit()

    # Seed Photo with a critical capacitor failure ai_analysis
    photo = JobPhoto(
        id="photo_test",
        company_id="comp_test",
        job_id=job_id,
        tech_id="usr_tech",
        s3_key="comp_test/job_test/electrical/cap.jpg",
        cdn_url="https://media.augmentedtradetech.com/comp_test/job_test/electrical/cap.jpg",
        photo_type="fault",
        file_size_bytes=1000,
        mime_type="image/jpeg",
        ai_analysis={
            "component_type": "capacitor",
            "severity": "critical",
            "visible_damage": "Bulged top with oil residue leaking."
        }
    )
    test_db.add(photo)
    test_db.commit()

    # 2. Trigger AI Diagnosis Endpoint
    diag_res = client.post(f"/ai/diagnose/{job_id}", headers=tech_headers)
    assert diag_res.status_code == 200
    assert diag_res.json()["job_id"] == job_id
    assert diag_res.json()["status"] == "queued"

    # 3. Execute LangGraph Diagnosis pipeline directly for synchronous verification
    diagnosis_data = await run_diagnosis_pipeline(job_id, test_db)
    
    # 4. Verify Final Diagnosis Data Structure
    assert "summary" in diagnosis_data
    assert "root_causes" in diagnosis_data
    assert "recommendations" in diagnosis_data
    assert "safety_concerns" in diagnosis_data
    assert "work_performed" in diagnosis_data
    assert "draft_invoice" in diagnosis_data

    # Check anomalies evaluation logic
    assert diagnosis_data["escalation_needed"] is False
    assert len(diagnosis_data["root_causes"]) > 0
    assert diagnosis_data["root_causes"][0]["confidence"] >= 0.8
    
    # Check Invoice line items (Labor + likely parts)
    draft_invoice = diagnosis_data["draft_invoice"]
    assert len(draft_invoice["line_items"]) >= 2
    labor_item = next(item for item in draft_invoice["line_items"] if "Labor" in item["description"])
    assert labor_item["unit_price_cents"] == 18000
    
    capacitor_item = next(item for item in draft_invoice["line_items"] if "Capacitor" in item["description"])
    assert capacitor_item["unit_price_cents"] == 6500

    # 5. Verify pgvector Embedding Row Creation
    embedding_row = test_db.scalar(select(JobEmbedding).where(JobEmbedding.job_id == job_id))
    assert embedding_row is not None
    assert len(embedding_row.embedding) == 1536
    assert "capacitor" in embedding_row.embed_text.lower()

    # 6. Verify GET /jobs/:id returns the parsed diagnosis successfully
    get_job_res = client.get(f"/jobs/{job_id}", headers=admin_headers)
    assert get_job_res.status_code == 200
    get_job_data = get_job_res.json()
    assert "ai_diagnosis" in get_job_data
    assert get_job_data["ai_diagnosis"]["summary"] == diagnosis_data["summary"]
    assert "draft_invoice" in get_job_data["ai_diagnosis"]
