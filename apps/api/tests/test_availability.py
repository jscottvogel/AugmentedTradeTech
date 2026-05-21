import pytest
import ulid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.company import Company
from apps.api.app.models.user import User, TechProfile, AvailabilityStatusLog
from apps.api.app.routers.auth import create_access_token
from apps.api.app.cron.heartbeat import handler as heartbeat_cron_handler

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    # Clean up before testing
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, availability_status_logs, tech_profiles, users, companies CASCADE;"))
    db.commit()
    
    # Seed Company A & B
    comp_a = Company(id="comp_a", name="Company A", slug="company-a")
    comp_b = Company(id="comp_b", name="Company B", slug="company-b")
    db.add_all([comp_a, comp_b])
    db.commit()

    # Seed Admin A (Active, Comp A)
    admin_a = User(
        id="usr_admin_a",
        company_id="comp_a",
        email="admin_a@test.com",
        full_name="Admin A",
        role="company_admin",
        is_active=True,
    )
    # Seed Dispatcher A (Active, Comp A)
    disp_a = User(
        id="usr_disp_a",
        company_id="comp_a",
        email="disp_a@test.com",
        full_name="Dispatcher A",
        role="dispatcher",
        is_active=True,
    )
    # Seed Tech A (Inactive, Comp A)
    tech_a = User(
        id="usr_tech_a",
        company_id="comp_a",
        email="tech_a@test.com",
        full_name="Tech A",
        role="tech",
        is_active=False,
    )
    # Seed Tech B (Active, Comp B)
    tech_b = User(
        id="usr_tech_b",
        company_id="comp_b",
        email="tech_b@test.com",
        full_name="Tech B",
        role="tech",
        is_active=True,
    )
    
    db.add_all([admin_a, disp_a, tech_a, tech_b])
    db.commit()

    # Create active tech profile for Tech B
    tech_b_profile = TechProfile(
        id="tprf_b",
        user_id="usr_tech_b",
        company_id="comp_b",
        availability_status="available",
        trades=["Garage Door"],
        certifications=[{"name": "Master Installer"}],
        skills=["Spring Replacement"],
        last_heartbeat_at=datetime.now(timezone.utc)
    )
    db.add(tech_b_profile)
    db.commit()

    yield db
    db.close()

def test_get_profile(test_db):
    tech_token = create_access_token("usr_tech_a", "comp_a", "tech", "tech_a@test.com", False)
    headers = {"Authorization": f"Bearer {tech_token}"}

    res = client.get("/me/profile", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "tech_a@test.com"
    assert data["is_active"] is False
    assert data["tech_profile"] is None

def test_complete_tech_profile_activation(test_db):
    tech_token = create_access_token("usr_tech_a", "comp_a", "tech", "tech_a@test.com", False)
    headers = {"Authorization": f"Bearer {tech_token}"}

    # Incomplete update (no trades/skills) -> should keep is_active = False
    update_data = {
        "full_name": "Tech A Updated",
        "phone": "555-0199",
        "avatar_url": "https://mockurl.com/photo.jpg",
        "trades": [],
        "certifications": [{"name": "EPA 608"}],
        "skills": []
    }
    res = client.put("/me/profile", json=update_data, headers=headers)
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # Complete update -> should set is_active = True
    complete_data = {
        "full_name": "Tech A Active",
        "phone": "555-0199",
        "avatar_url": "https://mockurl.com/photo.jpg",
        "trades": ["HVAC"],
        "certifications": [{"name": "EPA 608"}],
        "skills": ["Electrical Troubleshooting"]
    }
    res = client.put("/me/profile", json=complete_data, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["is_active"] is True
    assert data["full_name"] == "Tech A Active"
    assert data["tech_profile"]["trades"] == ["HVAC"]
    assert data["tech_profile"]["skills"] == ["Electrical Troubleshooting"]

def test_update_availability(test_db):
    tech_token = create_access_token("usr_tech_a", "comp_a", "tech", "tech_a@test.com", True)
    headers = {"Authorization": f"Bearer {tech_token}"}

    # Verify transition to available
    res = client.put("/me/availability", json={"status": "available"}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["tech_profile"]["availability_status"] == "available"

    # Verify history log created
    res_history = test_db.scalars(
        select(AvailabilityStatusLog)
        .where(AvailabilityStatusLog.user_id == "usr_tech_a")
        .order_by(AvailabilityStatusLog.started_at.desc())
    ).all()
    assert len(res_history) == 1
    assert res_history[0].status == "available"
    assert res_history[0].ended_at is None

    # Transition to driving
    res = client.put("/me/availability", json={"status": "driving"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["tech_profile"]["availability_status"] == "driving"

    # Verify previous log closed and new log created
    test_db.expire_all()
    logs = test_db.scalars(
        select(AvailabilityStatusLog)
        .where(AvailabilityStatusLog.user_id == "usr_tech_a")
        .order_by(AvailabilityStatusLog.started_at.asc())
    ).all()
    assert len(logs) == 2
    assert logs[0].status == "available"
    assert logs[0].ended_at is not None
    assert logs[1].status == "driving"
    assert logs[1].ended_at is None

def test_heartbeat_and_cron_handler(test_db):
    # Setup Tech A active and available
    tech_token = create_access_token("usr_tech_a", "comp_a", "tech", "tech_a@test.com", True)
    headers = {"Authorization": f"Bearer {tech_token}"}
    client.put("/me/availability", json={"status": "available"}, headers=headers)

    # Ping heartbeat
    res = client.post("/me/heartbeat", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # Verify last_heartbeat_at updated
    test_db.expire_all()
    tech_profile = test_db.scalar(select(TechProfile).where(TechProfile.user_id == "usr_tech_a"))
    assert tech_profile.last_heartbeat_at is not None

    # Run heartbeat cron handler - since heartbeat was just sent, tech_a should NOT be stale
    cron_res = heartbeat_cron_handler(None, None)
    assert cron_res["marked_offline_count"] == 0

    # Backdate heartbeat and check stale detection
    tech_profile.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    test_db.commit()

    cron_res_stale = heartbeat_cron_handler(None, None)
    assert cron_res_stale["marked_offline_count"] == 1
    
    test_db.expire_all()
    tech_profile_after = test_db.scalar(select(TechProfile).where(TechProfile.user_id == "usr_tech_a"))
    assert tech_profile_after.availability_status == "offline"

def test_dispatcher_list_techs_and_history(test_db):
    # Dispatcher A token
    disp_token = create_access_token("usr_disp_a", "comp_a", "dispatcher", "disp_a@test.com", True)
    headers = {"Authorization": f"Bearer {disp_token}"}

    # Tech A sets status to 'on_job'
    tech_token = create_access_token("usr_tech_a", "comp_a", "tech", "tech_a@test.com", True)
    client.put("/me/availability", json={"status": "on_job"}, headers={"Authorization": f"Bearer {tech_token}"})

    # Dispatcher lists techs
    res = client.get("/techs", headers=headers)
    assert res.status_code == 200
    techs = res.json()
    # Should only see Tech A from Company A, not Tech B from Company B
    assert len(techs) == 1
    assert techs[0]["id"] == "usr_tech_a"
    assert techs[0]["tech_profile"]["availability_status"] == "on_job"

    # Get history log for Tech A
    res_logs = client.get(f"/techs/usr_tech_a/availability", headers=headers)
    assert res_logs.status_code == 200
    logs = res_logs.json()
    assert len(logs) > 0
    assert logs[0]["status"] == "on_job"

    # Verify RLS/Isolation: Dispatcher A trying to view Tech B (Comp B) history -> should return 404
    res_isolated = client.get(f"/techs/usr_tech_b/availability", headers=headers)
    assert res_isolated.status_code == 404
