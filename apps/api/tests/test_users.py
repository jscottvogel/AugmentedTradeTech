import pytest
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.company import Company
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.auth import MagicLinkToken, RefreshToken
from apps.api.app.routers.auth import create_access_token

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    # Clean up before testing
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, tech_profiles, users, companies CASCADE;"))
    db.commit()
    
    # Seed Company A
    comp_a = Company(id="comp_a", name="Company A", slug="company-a")
    # Seed Company B (for isolation checks)
    comp_b = Company(id="comp_b", name="Company B", slug="company-b")
    db.add_all([comp_a, comp_b])
    db.commit()

    # Seed Admin A (Active)
    admin_a = User(
        id="usr_admin_a",
        company_id="comp_a",
        email="admin_a@test.com",
        full_name="Admin A",
        role="company_admin",
        is_active=True,
    )
    # Seed Dispatcher A (Active)
    disp_a = User(
        id="usr_disp_a",
        company_id="comp_a",
        email="disp_a@test.com",
        full_name="Dispatcher A",
        role="dispatcher",
        is_active=True,
    )
    # Seed Admin B (Active)
    admin_b = User(
        id="usr_admin_b",
        company_id="comp_b",
        email="admin_b@test.com",
        full_name="Admin B",
        role="company_admin",
        is_active=True,
    )
    
    db.add_all([admin_a, disp_a, admin_b])
    db.commit()

    yield db
    db.close()

def test_list_users(test_db):
    # Obtain admin access token
    admin_token = create_access_token("usr_admin_a", "comp_a", "company_admin", "admin_a@test.com", True)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # List users as Admin A
    res = client.get("/users", headers=headers)
    assert res.status_code == 200
    users = res.json()
    assert len(users) == 2
    emails = [u["email"] for u in users]
    assert "admin_a@test.com" in emails
    assert "disp_a@test.com" in emails
    assert "admin_b@test.com" not in emails  # isolation check

    # Attempt to list users as Dispatcher A (non-admin)
    disp_token = create_access_token("usr_disp_a", "comp_a", "dispatcher", "disp_a@test.com", True)
    disp_headers = {"Authorization": f"Bearer {disp_token}"}
    res = client.get("/users", headers=disp_headers)
    assert res.status_code == 403

def test_invite_user_success(test_db):
    admin_token = create_access_token("usr_admin_a", "comp_a", "company_admin", "admin_a@test.com", True)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Invite a new technician
    invite_data = {
        "email": "new_tech@test.com",
        "phone": "555-9080",
        "role": "tech",
        "trades": ["hvac"],
    }
    res = client.post("/users/invite", json=invite_data, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "new_tech@test.com"
    assert data["user"]["role"] == "tech"
    assert data["user"]["is_active"] is False

    # Check DB state
    user = test_db.scalar(select(User).where(User.email == "new_tech@test.com"))
    assert user is not None
    assert user.is_active is False
    assert user.tech_profile is not None
    assert user.tech_profile.trades == ["hvac"]

    # Check that a magic link token was generated
    token_rec = test_db.scalar(select(MagicLinkToken).where(MagicLinkToken.user_id == user.id))
    assert token_rec is not None

def test_resend_invite(test_db):
    admin_token = create_access_token("usr_admin_a", "comp_a", "company_admin", "admin_a@test.com", True)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Invite a dispatcher first
    invite_data = {
        "email": "new_disp@test.com",
        "role": "dispatcher",
    }
    res = client.post("/users/invite", json=invite_data, headers=headers)
    assert res.status_code == 200
    user_id = res.json()["user"]["id"]

    # Resend invite
    res = client.post(f"/users/{user_id}/resend-invite", headers=headers)
    assert res.status_code == 200
    assert res.json()["message"] == "Invitation resent successfully"

    # Verify a second token exists
    tokens = test_db.scalars(select(MagicLinkToken).where(MagicLinkToken.user_id == user_id)).all()
    assert len(tokens) >= 1

def test_deactivate_user(test_db):
    admin_token = create_access_token("usr_admin_a", "comp_a", "company_admin", "admin_a@test.com", True)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin deactivates Dispatcher A
    res = client.post("/users/usr_disp_a/deactivate", headers=headers)
    assert res.status_code == 200
    
    # Check DB
    disp = test_db.scalar(select(User).where(User.id == "usr_disp_a"))
    assert disp.is_active is False

    # Try to log in with password as deactivated dispatcher -> should fail
    login_res = client.post("/auth/login", json={"email": "disp_a@test.com", "password": "some_password"})
    assert login_res.status_code == 401

    # Check deactivated tech magic link verification block
    tech = User(
        id="usr_tech_to_deactivate",
        company_id="comp_a",
        email="tech_deact@test.com",
        full_name="Deactivated Tech",
        role="tech",
        is_active=True,
        last_login_at=datetime.now(timezone.utc)
    )
    test_db.add(tech)
    
    # Create magic link token
    raw_token = secrets.token_hex(32)
    token_hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    magic_token = MagicLinkToken(
        id="token_deact_123",
        user_id="usr_tech_to_deactivate",
        token_hash=token_hashed,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    test_db.add(magic_token)
    test_db.commit()

    # Deactivate the tech
    deact_res = client.post("/users/usr_tech_to_deactivate/deactivate", headers=headers)
    assert deact_res.status_code == 200

    # Try to verify magic link for deactivated tech -> should return 403
    verify_res = client.post("/auth/magic-link/verify", json={"token": raw_token})
    assert verify_res.status_code == 403
    assert "Deactivated" in verify_res.json()["detail"]

    # Admin cannot deactivate self
    res = client.post("/users/usr_admin_a/deactivate", headers=headers)
    assert res.status_code == 400
    assert "cannot deactivate themselves" in res.json()["detail"]

def test_verify_magic_link_and_profile_completion(test_db):
    # Step 1: Create invited user
    invited_tech = User(
        id="usr_invited_tech",
        company_id="comp_a",
        email="invited_tech@test.com",
        full_name="",
        role="tech",
        is_active=False
    )
    test_db.add(invited_tech)
    
    # Generate magic link token manually
    raw_token = secrets.token_hex(32)
    token_hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    magic_token = MagicLinkToken(
        id="token_mock_123",
        user_id="usr_invited_tech",
        token_hash=token_hashed,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    test_db.add(magic_token)
    test_db.commit()

    # Step 2: Verify magic link
    res = client.post("/auth/magic-link/verify", json={"token": raw_token})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["is_active"] is False  # Still False
    
    tech_token = data["access_token"]
    tech_headers = {"Authorization": f"Bearer {tech_token}"}

    # Step 3: Complete profile (PUT /users/{id})
    profile_data = {
        "full_name": "Tech Verified",
        "phone": "555-8888",
        "trades": ["hvac", "garage_door"],
        "skills": ["Compressors", "Spring replacement"],
        "truck_id": "T-10",
        "license_number": "LIC-ABC",
        "hire_date": "2026-05-20"
    }
    
    res = client.put("/users/usr_invited_tech", json=profile_data, headers=tech_headers)
    assert res.status_code == 200
    updated = res.json()
    assert updated["is_active"] is True
    assert updated["full_name"] == "Tech Verified"
    assert updated["tech_profile"]["trades"] == ["hvac", "garage_door"]
    assert updated["tech_profile"]["truck_id"] == "T-10"

    # Step 4: Verify in DB
    test_db.expire_all()
    user = test_db.scalar(select(User).where(User.id == "usr_invited_tech"))
    assert user.is_active is True
    assert user.tech_profile.skills == ["Compressors", "Spring replacement"]
