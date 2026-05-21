import sys
import os
import datetime

# Add monorepo root to sys.path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from sqlalchemy.orm import Session
from sqlalchemy import text, select

from apps.api.app.core.database import SessionLocal
from apps.api.app.models.company import Company
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer
from apps.api.app.models.job import Job, JobTechnician
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.ai import JobEmbedding
from apps.api.app.core.workflows import DEFAULT_WORKFLOW_CONFIG

def seed_demo_data():
    print("Seeding demo data for E2E tests...")
    db: Session = SessionLocal()
    try:
        # Delete any existing demo rows to allow re-running
        db.execute(text("DELETE FROM job_technicians WHERE company_id = 'comp_demo';"))
        db.execute(text("DELETE FROM jobs WHERE company_id = 'comp_demo';"))
        db.execute(text("DELETE FROM customers WHERE company_id = 'comp_demo';"))
        db.execute(text("DELETE FROM tech_profiles WHERE id IN (SELECT id FROM users WHERE company_id = 'comp_demo');"))
        db.execute(text("DELETE FROM users WHERE company_id = 'comp_demo';"))
        db.execute(text("DELETE FROM companies WHERE id = 'comp_demo';"))
        db.commit()

        # 1. Company
        comp = Company(
            id="comp_demo",
            name="Demo Company",
            slug="demo-company",
            timezone="America/Chicago",
            job_number_seq=0,
            workflow_config=DEFAULT_WORKFLOW_CONFIG
        )
        db.add(comp)
        db.flush()

        # 2. Users
        tech = User(
            id="usr_tech_demo",
            company_id="comp_demo",
            email="tech@demo.com",
            full_name="John Technician",
            role="tech",
            is_active=True
        )
        admin = User(
            id="usr_admin_demo",
            company_id="comp_demo",
            email="admin@demo.com",
            full_name="Sarah Admin",
            role="company_admin",
            is_active=True
        )
        db.add_all([tech, admin])
        db.flush()

        # 3. TechProfile
        tp = TechProfile(
            id="usr_tech_demo",
            user_id="usr_tech_demo",
            company_id="comp_demo",
            availability_status="available"
        )
        db.add(tp)
        db.flush()

        # 4. Customer
        cust = Customer(
            id="cust_demo",
            company_id="comp_demo",
            first_name="Sarah",
            last_name="Connor",
            email="sarah@connor.com",
            phone="555-0101",
            customer_type="residential"
        )
        db.add(cust)
        db.flush()

        # 5. Job
        now = datetime.datetime.now(datetime.timezone.utc)
        job = Job(
            id="job_demo_1",
            company_id="comp_demo",
            customer_id="cust_demo",
            trade="hvac",
            job_type="service",
            priority="routine",
            status="scheduled",
            source="phone",
            scheduled_start=now,
            scheduled_end=now + datetime.timedelta(hours=2)
        )
        db.add(job)
        db.flush()

        # 6. JobTechnician
        jt = JobTechnician(
            id="jt_demo_1",
            company_id="comp_demo",
            job_id="job_demo_1",
            tech_id="usr_tech_demo",
            is_lead=True
        )
        db.add(jt)
        
        db.commit()
        print("Demo data seeded successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding demo data: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Re-enable triggers
        db.execute(text("ALTER TABLE companies ENABLE TRIGGER ALL;"))
        db.execute(text("ALTER TABLE users ENABLE TRIGGER ALL;"))
        db.execute(text("ALTER TABLE customers ENABLE TRIGGER ALL;"))
        db.execute(text("ALTER TABLE tech_profiles ENABLE TRIGGER ALL;"))
        db.execute(text("ALTER TABLE jobs ENABLE TRIGGER ALL;"))
        db.execute(text("ALTER TABLE job_technicians ENABLE TRIGGER ALL;"))
        db.commit()
        db.close()

if __name__ == "__main__":
    seed_demo_data()
