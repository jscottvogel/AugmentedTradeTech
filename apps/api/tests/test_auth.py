import pytest
import time
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.user import User
from apps.api.app.models.company import Company
from apps.api.app.models.auth import MagicLinkToken, RefreshToken
from apps.api.app.routers.auth import get_password_hash, hash_token, JWT_SECRET, ALGORITHM

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    # Clean up before testing
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, users, companies CASCADE;"))
    db.commit()

    # Seed Company
    comp = Company(id="comp_test", name="Test Company", slug="test-company")
    db.add(comp)
    db.commit()

    # Seed Users
    tech = User(
        id="usr_tech_test",
        company_id="comp_test",
        email="tech_test@test.com",
        full_name="Tech Test",
        role="tech",
        is_active=True
    )
    admin = User(
        id="usr_admin_test",
        company_id="comp_test",
        email="admin_test@test.com",
        full_name="Admin Test",
        role="company_admin",
        password_hash=get_password_hash("secure_password_123"),
        is_active=True
    )
    db.add_all([tech, admin])
    db.commit()

    yield db

    # Clean up after testing
    db.close()

def test_lookup_endpoint(test_db):
    # Test tech user lookup
    res = client.post("/auth/lookup", json={"email": "tech_test@test.com"})
    assert res.status_code == 200
    data = res.json()
    assert data["exists"] is True
    assert data["auth_method"] == "magic_link"
    assert data["role"] == "tech"
    assert data["mfa_enabled"] is False

    # Test admin user lookup
    res = client.post("/auth/lookup", json={"email": "admin_test@test.com"})
    assert res.status_code == 200
    data = res.json()
    assert data["exists"] is True
    assert data["auth_method"] == "password"
    assert data["role"] == "company_admin"

    # Test non-existing email
    res = client.post("/auth/lookup", json={"email": "non_existing@test.com"})
    assert res.status_code == 200
    assert res.json()["exists"] is False

def test_magic_link_flow(test_db):
    # 1. Request magic link
    res = client.post("/auth/magic-link", json={"email": "tech_test@test.com"})
    assert res.status_code == 200
    assert "magic link has been sent" in res.json()["message"]

    # Retrieve the token from database (since we cannot intercept the email in unit tests)
    db_token = test_db.scalar(select(MagicLinkToken).where(MagicLinkToken.user_id == "usr_tech_test"))
    assert db_token is not None
    assert db_token.used_at is None
    
    # 2. Verify with invalid token
    res = client.post("/auth/magic-link/verify", json={"token": "invalid_token_value"})
    assert res.status_code == 400
    assert "Invalid or already used" in res.json()["detail"]

    # We need to simulate the raw token by finding what token maps to the hash.
    # Because we generated a random 32-byte hex, we can't easily guess it.
    # Let's bypass and manually insert a known raw token for testing.
    raw_token = "a" * 64
    hashed = hash_token(raw_token)
    known_token = MagicLinkToken(
        id="token_test_1",
        user_id="usr_tech_test",
        token_hash=hashed,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    test_db.add(known_token)
    test_db.commit()

    # Verify with valid token
    res = client.post("/auth/magic-link/verify", json={"token": raw_token})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "tech_test@test.com"
    assert "refresh_token" in res.cookies

    # Verify again (should fail because it's single-use)
    res = client.post("/auth/magic-link/verify", json={"token": raw_token})
    assert res.status_code == 400
    assert "already used" in res.json()["detail"]

def test_password_login_flow(test_db):
    # Correct login
    res = client.post("/auth/login", json={"email": "admin_test@test.com", "password": "secure_password_123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "admin_test@test.com"
    assert "refresh_token" in res.cookies

    # Incorrect login
    res = client.post("/auth/login", json={"email": "admin_test@test.com", "password": "wrong_password"})
    assert res.status_code == 401
    assert "Invalid credentials" in res.json()["detail"]

    # Tech login via password endpoint (should fail)
    res = client.post("/auth/login", json={"email": "tech_test@test.com", "password": "some_password"})
    assert res.status_code == 401

def test_refresh_token_flow(test_db):
    # Perform initial login to get cookie
    res = client.post("/auth/login", json={"email": "admin_test@test.com", "password": "secure_password_123"})
    assert res.status_code == 200
    refresh_cookie = res.cookies.get("refresh_token")
    assert refresh_cookie is not None

    # Call refresh endpoint
    client.cookies.clear()
    client.cookies.set("refresh_token", refresh_cookie)
    res = client.post("/auth/refresh")
    assert res.status_code == 200
    assert "access_token" in res.json()
    new_cookie = res.cookies.get("refresh_token")
    assert new_cookie is not None
    assert new_cookie != refresh_cookie  # Verify token rotation

def test_logout_flow(test_db):
    res = client.post("/auth/login", json={"email": "admin_test@test.com", "password": "secure_password_123"})
    refresh_cookie = res.cookies.get("refresh_token")
    
    # Logout
    client.cookies.set("refresh_token", refresh_cookie)
    res = client.post("/auth/logout")
    assert res.status_code == 200
    
    # Check refresh token deleted from DB
    hashed = hash_token(refresh_cookie)
    db_token = test_db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hashed))
    assert db_token is None

def test_protected_routes_middleware(test_db):
    # Try to access protected endpoint without token (should fail)
    res = client.post("/auth/mfa/setup")
    assert res.status_code == 401

    # Login to get valid JWT token
    res = client.post("/auth/login", json={"email": "admin_test@test.com", "password": "secure_password_123"})
    access_token = res.json()["access_token"]

    # Access with valid token
    headers = {"Authorization": f"Bearer {access_token}"}
    res = client.post("/auth/mfa/setup", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "secret" in data
    assert "provisioning_uri" in data
