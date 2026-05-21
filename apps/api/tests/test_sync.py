import pytest
import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.job import Job, JobPhoto, JobStatusHistory
from apps.api.app.models.sync import SyncQueue
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.company import Company
from apps.api.app.models.customer import Customer
from apps.api.app.routers.auth import create_access_token
from apps.api.app.cron.sync_queue_worker import handler as sync_worker_handler

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, invoices, availability_status_logs, job_parts, job_technicians, job_status_history, jobs, customers, tech_profiles, users, companies, sync_queue CASCADE;"))
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

def test_sync_flush_applied(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    
    # 1. Create a job
    job = Job(
        id="job_test_1",
        company_id="comp_test",
        customer_id="cust_test",
        trade="hvac",
        job_type="service",
        status="scheduled",
        reported_problem="Leaking water",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.commit()

    # 2. Send status update mutation via /sync/flush
    payload = {
        "items": [
            {
                "idempotency_key": "ik_1",
                "entity_type": "job",
                "entity_id": "job_test_1",
                "operation": "status",
                "payload": {
                    "status": "confirmed",
                    "note": "Client confirmed offline",
                    "last_known_updated_at": job.updated_at.isoformat()
                },
                "client_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)
            }
        ]
    }
    
    response = client.post("/sync/flush", json=payload, headers=admin_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["results"]) == 1
    assert res_data["results"][0]["idempotency_key"] == "ik_1"
    assert res_data["results"][0]["status"] == "applied"
    
    # Verify job status in DB
    test_db.expire_all()
    db_job = test_db.scalar(select(Job).where(Job.id == "job_test_1"))
    assert db_job.status == "confirmed"

def test_sync_flush_idempotency(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    
    # Create job
    job = Job(
        id="job_test_2",
        company_id="comp_test",
        customer_id="cust_test",
        trade="hvac",
        job_type="service",
        status="scheduled",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.commit()

    # Send mutation first time
    payload = {
        "items": [
            {
                "idempotency_key": "ik_idemp_test",
                "entity_type": "job",
                "entity_id": "job_test_2",
                "operation": "status",
                "payload": {
                    "status": "confirmed",
                    "last_known_updated_at": job.updated_at.isoformat()
                },
                "client_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)
            }
        ]
    }
    res1 = client.post("/sync/flush", json=payload, headers=admin_headers)
    assert res1.status_code == 200
    assert res1.json()["results"][0]["status"] == "applied"

    # Send again - should be returned from idempotency log
    res2 = client.post("/sync/flush", json=payload, headers=admin_headers)
    assert res2.status_code == 200
    assert res2.json()["results"][0]["idempotency_key"] == "ik_idemp_test"
    assert res2.json()["results"][0]["status"] == "applied"

def test_sync_flush_conflict(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    
    # Create job
    job = Job(
        id="job_test_3",
        company_id="comp_test",
        customer_id="cust_test",
        trade="hvac",
        job_type="service",
        status="scheduled",
        created_by="usr_admin",
        updated_at=datetime.now(timezone.utc)
    )
    test_db.add(job)
    test_db.commit()

    # Modify the job on the server to advance updated_at
    server_time = datetime.now(timezone.utc) + timedelta(minutes=5)
    job.status = "confirmed"
    job.updated_at = server_time
    test_db.add(job)
    test_db.commit()

    # Client tries to send an offline status change using an OLD updated_at
    client_last_known = (server_time - timedelta(minutes=10)).isoformat()
    
    payload = {
        "items": [
            {
                "idempotency_key": "ik_conflict_test",
                "entity_type": "job",
                "entity_id": "job_test_3",
                "operation": "status",
                "payload": {
                    "status": "en_route",
                    "last_known_updated_at": client_last_known
                },
                "client_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)
            }
        ]
    }
    
    response = client.post("/sync/flush", json=payload, headers=admin_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["results"]) == 1
    assert res_data["results"][0]["status"] == "conflict"
    assert res_data["results"][0]["server_response"]["status"] == "confirmed"

def test_sync_photos_confirm(test_db):
    admin_headers = get_auth_headers("usr_admin", "admin@test.com", "company_admin")
    
    job = Job(
        id="job_test_4",
        company_id="comp_test",
        customer_id="cust_test",
        trade="hvac",
        job_type="service",
        status="scheduled",
        created_by="usr_admin"
    )
    test_db.add(job)
    test_db.commit()

    payload = {
        "photo_uploads": [
            {
                "idempotency_key": "ik_photo_1",
                "s3_key": "jobs/job_test_4/before.jpg",
                "job_id": "job_test_4",
                "step_key": "step_1",
                "photo_type": "before"
            }
        ]
    }
    
    response = client.post("/sync/photos/confirm", json=payload, headers=admin_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["results"]) == 1
    assert res_data["results"][0]["status"] == "registered"
    
    # Verify in DB
    photo = test_db.scalar(select(JobPhoto).where(JobPhoto.s3_key == "jobs/job_test_4/before.jpg"))
    assert photo is not None
    assert photo.photo_type == "before"
    assert photo.step_key == "step_1"

def test_sync_queue_worker_handler(test_db):
    # Seed SyncQueue entry
    sq_record = SyncQueue(
        id="sq_worker_test",
        company_id="comp_test",
        user_id="usr_admin",
        entity_type="job",
        entity_id="job_test_1",
        operation="status",
        payload={"status": "confirmed"},
        client_timestamp=datetime.now(timezone.utc),
        idempotency_key="ik_worker_1",
        status="processing",
        attempts=1
    )
    test_db.add(sq_record)
    test_db.commit()

    # 1. Successful message processing
    sqs_event = {
        "Records": [
            {
                "messageId": "msg_1",
                "receiptHandle": "receipt_1",
                "body": json.dumps({
                    "sync_queue_id": "sq_worker_test",
                    "company_id": "comp_test",
                    "status": "processing",
                    "payload": {}
                }),
                "attributes": {
                    "ApproximateReceiveCount": "1"
                }
            }
        ]
    }
    
    result = sync_worker_handler(sqs_event, None)
    assert len(result["batchItemFailures"]) == 0
    
    # Record status should be updated to applied
    test_db.refresh(sq_record)
    assert sq_record.status == "applied"

    # 2. Failed message processing (ApproximateReceiveCount <= 3 -> retry / backoff)
    sqs_event_fail = {
        "Records": [
            {
                "messageId": "msg_2",
                "receiptHandle": "receipt_2",
                "body": json.dumps({
                    "sync_queue_id": "sq_worker_test",
                    "company_id": "comp_test",
                    "status": "processing",
                    "payload": {
                        "simulate_worker_error": True
                    }
                }),
                "attributes": {
                    "ApproximateReceiveCount": "2"
                }
            }
        ]
    }
    
    result_fail = sync_worker_handler(sqs_event_fail, None)
    assert len(result_fail["batchItemFailures"]) == 1
    assert result_fail["batchItemFailures"][0]["itemIdentifier"] == "msg_2"

    # 3. Failed message processing (ApproximateReceiveCount > 3 -> route to DLQ)
    sqs_event_dlq = {
        "Records": [
            {
                "messageId": "msg_3",
                "receiptHandle": "receipt_3",
                "body": json.dumps({
                    "sync_queue_id": "sq_worker_test",
                    "company_id": "comp_test",
                    "status": "processing",
                    "payload": {
                        "simulate_worker_error": True
                    }
                }),
                "attributes": {
                    "ApproximateReceiveCount": "4"
                }
            }
        ]
    }
    
    result_dlq = sync_worker_handler(sqs_event_dlq, None)
    assert len(result_dlq["batchItemFailures"]) == 0
