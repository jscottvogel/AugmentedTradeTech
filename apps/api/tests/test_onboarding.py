import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.company import Company
from apps.api.app.models.user import User

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    # Clean up before testing
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, users, companies CASCADE;"))
    db.commit()
    yield db
    db.close()

def test_full_onboarding_lifecycle(test_db):
    # Step 1: Sign up a new Company and Admin
    signup_data = {
        "company_name": "Apex HVAC Services",
        "owner_name": "Apex Owner",
        "email": "owner@apex.com",
        "password": "apexpassword123"
    }
    
    # Try public signup
    res = client.post("/onboarding/company", json=signup_data)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "user" in data
    assert "company" in data
    
    company_id = data["company"]["id"]
    user_id = data["user"]["id"]
    access_token = data["access_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    
    # Verify DB state after signup
    company = test_db.scalar(select(Company).where(Company.id == company_id))
    assert company is not None
    assert company.onboarding_step == 2
    assert company.name == "Apex HVAC Services"
    
    user = test_db.scalar(select(User).where(User.id == user_id))
    assert user is not None
    assert user.role == "company_admin"
    assert user.email == "owner@apex.com"

    # Verify protected state retrieval (Step 2 check)
    res = client.get(f"/onboarding/{company_id}", headers=auth_headers)
    assert res.status_code == 200
    state = res.json()
    assert state["onboarding_step"] == 2
    assert state["trades"] == []

    # Step 2: Save Profile details
    profile_data = {
        "trades": ["hvac"],
        "service_area_zips": ["75201", "75202"],
        "business_hours": {"start": "08:00", "end": "17:00"},
        "logo_url": "https://apex.com/logo.png"
    }
    res = client.put(f"/onboarding/{company_id}/profile", json=profile_data, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["onboarding_step"] == 3

    # Verify profile DB updates
    test_db.expire_all()
    company = test_db.scalar(select(Company).where(Company.id == company_id))
    assert company.onboarding_step == 3
    assert company.trades == ["hvac"]
    assert company.service_area_zips == ["75201", "75202"]
    assert company.logo_url == "https://apex.com/logo.png"

    # Step 3: Select Plan
    plan_data = {"plan": "professional"}
    res = client.put(f"/onboarding/{company_id}/plan", json=plan_data, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["onboarding_step"] == 4

    test_db.expire_all()
    company = test_db.scalar(select(Company).where(Company.id == company_id))
    assert company.onboarding_step == 4
    assert company.subscription_status == "professional"

    # Step 4: Stripe Connect initiation
    res = client.post(f"/onboarding/{company_id}/stripe", headers=auth_headers)
    assert res.status_code == 200
    assert "stripe/callback" in res.json()["url"]

    # Simulate Stripe redirect callback (Public route check)
    res = client.get(f"/onboarding/{company_id}/stripe/callback?code=mock_code&state=mock_state", follow_redirects=False)
    # Callback returns RedirectResponse back to frontend
    assert res.status_code == 307
    
    test_db.expire_all()
    company = test_db.scalar(select(Company).where(Company.id == company_id))
    assert company.onboarding_step == 5
    assert company.stripe_account_id is not None
    assert company.stripe_account_id.startswith("acct_mock_")

    # Step 5: QuickBooks Connect (optional connect)
    res = client.post(f"/onboarding/{company_id}/quickbooks", json={"connect": True}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["onboarding_step"] == 6

    test_db.expire_all()
    company = test_db.scalar(select(Company).where(Company.id == company_id))
    assert company.onboarding_step == 6
    assert company.qbo_realm_id is not None

    # Step 6: Invite Technician
    invite_data = {"email": "tech1@apex.com", "phone": "555-0199"}
    res = client.post(f"/onboarding/{company_id}/invite-tech", json=invite_data, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["onboarding_step"] == 7

    # Check technician user was generated in DB
    tech = test_db.scalar(select(User).where(User.email == "tech1@apex.com"))
    assert tech is not None
    assert tech.role == "tech"
    assert tech.company_id == company_id

    # Step 8: Mark Onboarding Completed
    res = client.put(f"/onboarding/{company_id}/complete", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["onboarding_step"] == 8

    test_db.expire_all()
    company = test_db.scalar(select(Company).where(Company.id == company_id))
    assert company.onboarding_step == 8
