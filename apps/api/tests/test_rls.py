import pytest
from datetime import datetime, UTC
from sqlalchemy import text
from sqlalchemy.orm import Session
from apps.api.app.core.database import SessionLocal, set_rls_context  # type: ignore

# Import all models to register them in Base.metadata
from apps.api.app.models.ai import JobEmbedding, AIRequest  # type: ignore
from apps.api.app.models.company import Company  # type: ignore
from apps.api.app.models.customer import Customer, EquipmentCustomer  # type: ignore
from apps.api.app.models.dispatch import JobPool, TechLocationPing  # type: ignore
from apps.api.app.models.invoice import Invoice, InvoiceLineItem  # type: ignore
from apps.api.app.models.job import Job, JobTechnician, JobPhoto, JobNote, JobStatusHistory  # type: ignore
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger  # type: ignore
from apps.api.app.models.membership import MembershipPlan, Membership  # type: ignore
from apps.api.app.models.sync import SyncQueue  # type: ignore
from apps.api.app.models.user import User, TechProfile  # type: ignore

@pytest.fixture(scope="function")
def db():
    # 1. Seed as superuser
    su_session = SessionLocal()
    
    # Clean up existing test data
    su_session.execute(text("TRUNCATE job_technicians, jobs, customers, tech_profiles, users, companies CASCADE;"))
    su_session.commit()

    # Ensure test_app_user exists and has privileges
    su_session.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'test_app_user') THEN
                CREATE ROLE test_app_user WITH LOGIN PASSWORD 'test_password';
            END IF;
        END
        $$;
    """))
    su_session.execute(text("GRANT ALL PRIVILEGES ON DATABASE augmentedtradetech TO test_app_user;"))
    su_session.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO test_app_user;"))
    su_session.execute(text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test_app_user;"))
    su_session.execute(text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO test_app_user;"))
    su_session.commit()

    # Seed Companies
    comp_a = Company(id="comp_a", name="Company A", slug="company-a")
    comp_b = Company(id="comp_b", name="Company B", slug="company-b")
    su_session.add_all([comp_a, comp_b])
    su_session.commit()

    # Seed Users
    usr_admin_a = User(id="usr_admin_a", company_id="comp_a", email="admin_a@test.com", full_name="Admin A", role="company_admin", is_active=True)
    usr_tech_a1 = User(id="usr_tech_a1", company_id="comp_a", email="tech_a1@test.com", full_name="Tech A1", role="tech", is_active=True)
    usr_tech_a2 = User(id="usr_tech_a2", company_id="comp_a", email="tech_a2@test.com", full_name="Tech A2", role="tech", is_active=True)
    usr_disp_a = User(id="usr_disp_a", company_id="comp_a", email="disp_a@test.com", full_name="Disp A", role="dispatcher", is_active=True)
    usr_admin_b = User(id="usr_admin_b", company_id="comp_b", email="admin_b@test.com", full_name="Admin B", role="company_admin", is_active=True)
    usr_plat_admin = User(id="usr_plat_admin", company_id=None, email="plat@test.com", full_name="Plat Admin", role="platform_admin", is_active=True)

    su_session.add_all([usr_admin_a, usr_tech_a1, usr_tech_a2, usr_disp_a, usr_admin_b, usr_plat_admin])
    su_session.commit()

    # Seed Tech Profiles
    tech_prof_a1 = TechProfile(id="tp_a1", company_id="comp_a", user_id="usr_tech_a1", availability_status="available")
    tech_prof_a2 = TechProfile(id="tp_a2", company_id="comp_a", user_id="usr_tech_a2", availability_status="available")
    su_session.add_all([tech_prof_a1, tech_prof_a2])
    su_session.commit()

    # Seed Customers
    cust_a = Customer(id="cust_a", company_id="comp_a", first_name="John", last_name="Doe", email="john@comp_a.com", customer_type="residential", portal_enabled=False)
    cust_b = Customer(id="cust_b", company_id="comp_b", first_name="Jane", last_name="Smith", email="jane@comp_b.com", customer_type="residential", portal_enabled=False)
    su_session.add_all([cust_a, cust_b])
    su_session.commit()

    # Seed Jobs
    job_a1 = Job(
        id="job_a1",
        company_id="comp_a",
        customer_id="cust_a",
        job_number="JOB-2026-00001",
        trade="hvac",
        job_type="service",
        priority="routine",
        status="scheduled",
        is_included_visit=False,
        source="phone"
    )
    job_a2 = Job(
        id="job_a2",
        company_id="comp_a",
        customer_id="cust_a",
        job_number="JOB-2026-00002",
        trade="plumbing",
        job_type="maintenance",
        priority="routine",
        status="completed",
        is_included_visit=False,
        source="phone",
        deleted_at=datetime.now(UTC)
    )
    job_b1 = Job(
        id="job_b1",
        company_id="comp_b",
        customer_id="cust_b",
        job_number="JOB-2026-00003",
        trade="electrical",
        job_type="install",
        priority="urgent",
        status="scheduled",
        is_included_visit=False,
        source="web"
    )
    su_session.add_all([job_a1, job_a2, job_b1])
    su_session.commit()

    # Assign Tech A1 to Job A1 and Job A2
    jt1 = JobTechnician(id="jt1", company_id="comp_a", job_id="job_a1", tech_id="usr_tech_a1", is_lead=True)
    jt2 = JobTechnician(id="jt2", company_id="comp_a", job_id="job_a2", tech_id="usr_tech_a1", is_lead=True)
    su_session.add_all([jt1, jt2])
    su_session.commit()
    
    su_session.close()

    # 2. Create non-superuser session for tests
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from apps.api.app.core.database import DB_HOST, DB_PORT, DB_NAME  # type: ignore
    
    test_url = f"postgresql+psycopg://test_app_user:test_password@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    test_engine = create_engine(test_url, pool_pre_ping=True)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    test_session = TestSessionLocal()
    yield test_session
    test_session.close()
    test_engine.dispose()
    
    # 3. Clean up as superuser
    cleanup_session = SessionLocal()
    cleanup_session.execute(text("TRUNCATE job_technicians, jobs, customers, tech_profiles, users, companies CASCADE;"))
    cleanup_session.commit()
    cleanup_session.close()

def test_cross_tenant_isolation(db: Session):
    # Company A Admin should see only Company A records
    set_rls_context(db, company_id="comp_a", user_id="usr_admin_a", role="company_admin")
    jobs_a = db.query(Job).all()
    customers_a = db.query(Customer).all()
    
    # Company A has job_a1 and job_a2 (soft deleted, admin can see it)
    assert len(jobs_a) == 2
    assert any(j.id == "job_a1" for j in jobs_a)
    assert any(j.id == "job_a2" for j in jobs_a)
    assert not any(j.id == "job_b1" for j in jobs_a)
    
    assert len(customers_a) == 1
    assert customers_a[0].id == "cust_a"

    # Company B Admin should see only Company B records
    set_rls_context(db, company_id="comp_b", user_id="usr_admin_b", role="company_admin")
    jobs_b = db.query(Job).all()
    customers_b = db.query(Customer).all()

    assert len(jobs_b) == 1
    assert jobs_b[0].id == "job_b1"
    assert len(customers_b) == 1
    assert customers_b[0].id == "cust_b"

def test_technician_job_scoping(db: Session):
    # Tech A1 is assigned to job_a1, should see only job_a1 (job_a2 is soft-deleted, tech can't see it)
    set_rls_context(db, company_id="comp_a", user_id="usr_tech_a1", role="tech")
    jobs_tech_a1 = db.query(Job).all()
    assert len(jobs_tech_a1) == 1
    assert jobs_tech_a1[0].id == "job_a1"

    # Tech A2 has no assignments, should see 0 jobs
    set_rls_context(db, company_id="comp_a", user_id="usr_tech_a2", role="tech")
    jobs_tech_a2 = db.query(Job).all()
    assert len(jobs_tech_a2) == 0

def test_platform_admin_bypass(db: Session):
    # Platform Admin can see everything bypassing company scopes
    set_rls_context(db, company_id=None, user_id="usr_plat_admin", role="platform_admin")
    jobs_all = db.query(Job).all()
    customers_all = db.query(Customer).all()

    # Platform Admin sees job_a1, job_a2 (soft-deleted), job_b1
    assert len(jobs_all) == 3
    assert any(j.id == "job_a1" for j in jobs_all)
    assert any(j.id == "job_a2" for j in jobs_all)
    assert any(j.id == "job_b1" for j in jobs_all)

    assert len(customers_all) == 2
    assert any(c.id == "cust_a" for c in customers_all)
    assert any(c.id == "cust_b" for c in customers_all)

def test_soft_deleted_visibility(db: Session):
    # 1. Admin can see soft deleted records
    set_rls_context(db, company_id="comp_a", user_id="usr_admin_a", role="company_admin")
    jobs_admin = db.query(Job).all()
    assert len(jobs_admin) == 2
    assert any(j.id == "job_a2" for j in jobs_admin) # soft-deleted

    # 2. Dispatcher cannot see soft deleted records
    set_rls_context(db, company_id="comp_a", user_id="usr_disp_a", role="dispatcher")
    jobs_disp = db.query(Job).all()
    assert len(jobs_disp) == 1
    assert jobs_disp[0].id == "job_a1"

    # 3. Tech cannot see soft deleted records, even if assigned
    set_rls_context(db, company_id="comp_a", user_id="usr_tech_a1", role="tech")
    jobs_tech = db.query(Job).all()
    assert len(jobs_tech) == 1
    assert jobs_tech[0].id == "job_a1"
