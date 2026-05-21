import pytest
import zoneinfo
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from apps.api.app.main import app
from apps.api.app.core.database import SessionLocal
from apps.api.app.models.company import Company
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.customer import Customer
from apps.api.app.models.job import Job, JobTechnician
from apps.api.app.models.invoice import Invoice
from apps.api.app.models.membership import Membership
from apps.api.app.routers.auth import create_access_token

client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    db = SessionLocal()
    db.execute(text("TRUNCATE refresh_tokens, magic_link_tokens, invoices, availability_status_logs, job_technicians, jobs, customers, tech_profiles, users, companies CASCADE;"))
    db.commit()

    # Seed Company with Central Timezone
    comp = Company(
        id="comp_test",
        name="Augmented Tech LLC",
        slug="augmented-tech",
        timezone="America/Chicago",
        workflow_config={"show_tech_earnings": True}
    )
    db.add(comp)
    db.commit()

    # Seed Technicians
    tech_a = User(
        id="usr_tech_a",
        company_id="comp_test",
        email="tech_a@test.com",
        full_name="Tech Alpha",
        role="tech",
        is_active=True,
    )
    tech_b = User(
        id="usr_tech_b",
        company_id="comp_test",
        email="tech_b@test.com",
        full_name="Tech Beta",
        role="tech",
        is_active=True,
    )
    db.add_all([tech_a, tech_b])
    db.commit()

    # Tech Profile for Tech A
    tech_a_profile = TechProfile(
        id="tprf_a",
        user_id="usr_tech_a",
        company_id="comp_test",
        availability_status="available"
    )
    db.add(tech_a_profile)
    db.commit()

    # Seed Customers
    cust1 = Customer(
        id="cust_1",
        company_id="comp_test",
        first_name="John",
        last_name="Doe",
        address_line1="123 Main St",
        city="Dallas",
        state="TX",
        zip="75201"
    )
    cust2 = Customer(
        id="cust_2",
        company_id="comp_test",
        first_name="Jane",
        last_name="Smith",
        address_line1="456 Oak Ave",
        city="Dallas",
        state="TX",
        zip="75202"
    )
    db.add_all([cust1, cust2])
    db.commit()

    yield db
    db.close()

def test_get_jobs_today_and_upcoming(test_db):
    tz = zoneinfo.ZoneInfo("America/Chicago")
    now_local = datetime.now(tz)
    
    # Calculate times relative to today local
    today_10am = datetime(now_local.year, now_local.month, now_local.day, 10, 0, 0, tzinfo=tz)
    today_2pm = datetime(now_local.year, now_local.month, now_local.day, 14, 0, 0, tzinfo=tz)
    tomorrow_9am = today_10am + timedelta(days=1)
    yesterday_3pm = today_10am - timedelta(days=1)
    eight_days_later = today_10am + timedelta(days=8)

    # Job 1: Today 10 AM (Tech A)
    job1 = Job(id="job_1", company_id="comp_test", customer_id="cust_1", job_number="J-101", trade="hvac", job_type="service", priority="urgent", status="scheduled", scheduled_start=today_10am, scheduled_end=today_10am + timedelta(hours=2))
    # Job 2: Today 2 PM (Tech A)
    job2 = Job(id="job_2", company_id="comp_test", customer_id="cust_2", job_number="J-102", trade="garage_door", job_type="maintenance", priority="routine", status="confirmed", scheduled_start=today_2pm, scheduled_end=today_2pm + timedelta(hours=1))
    # Job 3: Tomorrow 9 AM (Tech A) - Upcoming
    job3 = Job(id="job_3", company_id="comp_test", customer_id="cust_1", job_number="J-103", trade="hvac", job_type="install", priority="emergency", status="scheduled", scheduled_start=tomorrow_9am, scheduled_end=tomorrow_9am + timedelta(hours=4))
    # Job 4: Yesterday 3 PM (Tech A) - Past
    job4 = Job(id="job_4", company_id="comp_test", customer_id="cust_2", job_number="J-104", trade="hvac", job_type="service", priority="routine", status="completed", scheduled_start=yesterday_3pm, scheduled_end=yesterday_3pm + timedelta(hours=2), completed_at=yesterday_3pm + timedelta(hours=1.5))
    # Job 5: Today 10 AM (Tech B - different tech)
    job5 = Job(id="job_5", company_id="comp_test", customer_id="cust_1", job_number="J-105", trade="garage_door", job_type="service", priority="routine", status="scheduled", scheduled_start=today_10am, scheduled_end=today_10am + timedelta(hours=2))
    # Job 6: 8 Days Later (Tech A) - Out of upcoming bounds (7 days limit)
    job6 = Job(id="job_6", company_id="comp_test", customer_id="cust_2", job_number="J-106", trade="hvac", job_type="service", priority="routine", status="scheduled", scheduled_start=eight_days_later, scheduled_end=eight_days_later + timedelta(hours=2))
    
    test_db.add_all([job1, job2, job3, job4, job5, job6])
    test_db.commit()

    # Assign technicians
    jt1 = JobTechnician(id="jt_1", company_id="comp_test", job_id="job_1", tech_id="usr_tech_a", is_lead=True)
    jt2 = JobTechnician(id="jt_2", company_id="comp_test", job_id="job_2", tech_id="usr_tech_a", is_lead=True)
    jt3 = JobTechnician(id="jt_3", company_id="comp_test", job_id="job_3", tech_id="usr_tech_a", is_lead=True)
    jt4 = JobTechnician(id="jt_4", company_id="comp_test", job_id="job_4", tech_id="usr_tech_a", is_lead=True)
    jt5 = JobTechnician(id="jt_5", company_id="comp_test", job_id="job_5", tech_id="usr_tech_b", is_lead=True)
    jt6 = JobTechnician(id="jt_6", company_id="comp_test", job_id="job_6", tech_id="usr_tech_a", is_lead=True)

    test_db.add_all([jt1, jt2, jt3, jt4, jt5, jt6])
    test_db.commit()

    # Get Token for Tech A
    token = create_access_token("usr_tech_a", "comp_test", "tech", "tech_a@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}

    # Test Today's Jobs
    res_today = client.get("/me/jobs/today", headers=headers)
    assert res_today.status_code == 200
    today_jobs = res_today.json()
    # Should only return Job 1 and Job 2 (sorted by scheduled_start)
    assert len(today_jobs) == 2
    assert today_jobs[0]["id"] == "job_1"
    assert today_jobs[1]["id"] == "job_2"
    assert today_jobs[0]["customer"]["first_name"] == "John"
    assert today_jobs[0]["customer"]["address_line1"] == "123 Main St"

    # Test Upcoming Jobs
    res_upcoming = client.get("/me/jobs/upcoming", headers=headers)
    assert res_upcoming.status_code == 200
    upcoming_jobs = res_upcoming.json()
    # Should return Job 3 (tomorrow), but not Job 6 (8 days later)
    assert len(upcoming_jobs) == 1
    assert upcoming_jobs[0]["id"] == "job_3"

def test_get_stats_today(test_db):
    tz = zoneinfo.ZoneInfo("America/Chicago")
    now_local = datetime.now(tz)
    today_11am = datetime(now_local.year, now_local.month, now_local.day, 11, 0, 0, tzinfo=tz)

    # Job: Completed today
    job = Job(
        id="job_comp",
        company_id="comp_test",
        customer_id="cust_1",
        job_number="J-999",
        trade="hvac",
        job_type="service",
        priority="routine",
        status="completed",
        scheduled_start=today_11am,
        scheduled_end=today_11am + timedelta(hours=1),
        completed_at=today_11am + timedelta(minutes=45)
    )
    test_db.add(job)
    test_db.commit()

    jt = JobTechnician(id="jt_comp", company_id="comp_test", job_id="job_comp", tech_id="usr_tech_a", is_lead=True)
    test_db.add(jt)
    test_db.commit()

    # Invoice for this job
    invoice = Invoice(
        id="inv_comp",
        company_id="comp_test",
        job_id="job_comp",
        customer_id="cust_1",
        invoice_number="INV-999",
        status="paid",
        total_cents=32550  # $325.50
    )
    test_db.add(invoice)
    test_db.commit()

    # Get Token for Tech A
    token = create_access_token("usr_tech_a", "comp_test", "tech", "tech_a@test.com", True)
    headers = {"Authorization": f"Bearer {token}"}

    # Test with Earnings Enabled
    res_stats = client.get("/me/stats/today", headers=headers)
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["jobs_completed"] == 1
    assert stats["earnings_today"] == 32550
    assert stats["earnings_enabled"] is True

    # Disable earnings in workflow_config
    comp = test_db.scalar(select(Company).where(Company.id == "comp_test"))
    comp.workflow_config = {"show_tech_earnings": False}
    test_db.commit()

    # Test with Earnings Disabled
    res_stats_disabled = client.get("/me/stats/today", headers=headers)
    assert res_stats_disabled.status_code == 200
    stats_disabled = res_stats_disabled.json()
    assert stats_disabled["jobs_completed"] == 1
    assert stats_disabled["earnings_today"] is None
    assert stats_disabled["earnings_enabled"] is False
