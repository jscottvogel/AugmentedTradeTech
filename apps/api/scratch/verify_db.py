import sys
import os
from datetime import datetime, date, timedelta
from decimal import Decimal

# Add monorepo root to sys.path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from sqlalchemy.orm import Session
from sqlalchemy import text, select, create_engine

from apps.api.app.core.database import SessionLocal, engine, DB_HOST, DB_PORT, DB_NAME
from apps.api.app.models.company import Company
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer
from apps.api.app.models.job import Job, JobTechnician
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger, LoyaltyBalanceView
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.ai import JobEmbedding

def run_verification():
    print("==================================================")
    print("STARTING DATABASE AND SYSTEM SCHEMA VERIFICATION")
    print("==================================================")
    
    # 1. Setup a superuser connection to clean up and set up test user
    su_db: Session = SessionLocal()
    
    try:
        # Create non-superuser for testing RLS
        print("Setting up non-superuser database role 'test_app_user'...")
        su_db.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'test_app_user') THEN
                CREATE ROLE test_app_user WITH LOGIN PASSWORD 'test_password';
            END IF;
        END
        $$;
        """))
        su_db.execute(text("GRANT ALL PRIVILEGES ON DATABASE augmentedtradetech TO test_app_user;"))
        su_db.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO test_app_user;"))
        su_db.execute(text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test_app_user;"))
        su_db.execute(text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO test_app_user;"))
        su_db.commit()

        # Clean up database from previous runs
        print("Cleaning up old test data...")
        su_db.execute(text("ALTER TABLE payments DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE loyalty_ledger DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE invoice_line_items DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE invoices DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE job_technicians DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE job_embeddings DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE jobs DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE memberships DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE loyalty_accounts DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE equipment_customers DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE tech_profiles DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE customers DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE users DISABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE companies DISABLE TRIGGER ALL;"))

        # Delete all records
        su_db.execute(text("TRUNCATE TABLE payments, loyalty_ledger, invoice_line_items, invoices, job_technicians, job_embeddings, jobs, memberships, loyalty_accounts, equipment_customers, tech_profiles, customers, audit_log, users, companies RESTART IDENTITY CASCADE;"))
        su_db.execute(text("DROP SEQUENCE IF EXISTS seq_job_number_comp_a;"))
        su_db.execute(text("DROP SEQUENCE IF EXISTS seq_job_number_comp_b;"))
        
        # Re-enable triggers
        su_db.execute(text("ALTER TABLE companies ENABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE users ENABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE customers ENABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE equipment ENABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE jobs ENABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE invoices ENABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE loyalty_ledger ENABLE TRIGGER ALL;"))
        su_db.execute(text("ALTER TABLE payments ENABLE TRIGGER ALL;"))
        su_db.commit()
        print("Clean-up completed.")

        # --- SEEDING PRE-REQUISITES (BYPASS RLS TO SEED GLOBAL) ---
        print("\nSeeding company & user records (bypassing RLS)...")
        
        company_a = Company(id="comp_a", name="Company A", slug="company-a")
        company_b = Company(id="comp_b", name="Company B", slug="company-b")
        su_db.add_all([company_a, company_b])
        su_db.flush()
        
        admin_a = User(id="usr_admin_a", company_id="comp_a", email="admin@comp_a.com", full_name="Admin Company A", role="company_admin", is_active=True)
        tech_a = User(id="usr_tech_a", company_id="comp_a", email="tech@comp_a.com", full_name="Tech Company A", role="tech", is_active=True)
        
        admin_b = User(id="usr_admin_b", company_id="comp_b", email="admin@comp_b.com", full_name="Admin Company B", role="company_admin", is_active=True)
        
        su_db.add_all([admin_a, tech_a, admin_b])
        su_db.flush()
        
        # Update companies to reference created users
        company_a.created_by = admin_a.id
        company_a.updated_by = admin_a.id
        company_b.created_by = admin_b.id
        company_b.updated_by = admin_b.id
        su_db.commit()
        print("Seeded successfully.")
        
        # Grant permissions to newly seeded data for the test user
        su_db.execute(text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test_app_user;"))
        su_db.execute(text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO test_app_user;"))
        su_db.commit()
        su_db.close()

        # Connect as non-superuser to run standard verification and enforce RLS
        print("\nConnecting to database as non-superuser 'test_app_user'...")
        test_url = f"postgresql+psycopg://test_app_user:test_password@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        test_engine = create_engine(test_url, pool_pre_ping=True)
        db = Session(test_engine)

        # ==========================================================
        # 1. VERIFY ROW-LEVEL SECURITY (RLS) FOR MULTI-TENANCY
        # ==========================================================
        print("\n--- 1. Testing Row-Level Security (RLS) ---")
        
        # Act as Admin of Company A
        db.execute(text("SELECT set_config('app.current_role', 'company_admin', true);"))
        db.execute(text("SELECT set_config('app.current_company_id', 'comp_a', true);"))
        
        # Insert Customer under Company A
        customer_a = Customer(
            id="cust_a1",
            company_id="comp_a",
            first_name="John",
            last_name="Doe",
            email="john@doe.com",
            customer_type="residential",
            portal_enabled=False
        )
        db.add(customer_a)
        db.flush()
        
        # Act as Admin of Company B
        db.execute(text("SELECT set_config('app.current_role', 'company_admin', true);"))
        db.execute(text("SELECT set_config('app.current_company_id', 'comp_b', true);"))
        
        # Verify Admin of Company B cannot see Company A's Customer
        customers_seen_by_b = db.scalars(select(Customer)).all()
        print(f"Company B queries customers: {len(customers_seen_by_b)} found (Expected: 0)")
        assert len(customers_seen_by_b) == 0, "Security violation: Company B accessed Company A's customer!"
        
        # Act as Company A again
        db.execute(text("SELECT set_config('app.current_role', 'company_admin', true);"))
        db.execute(text("SELECT set_config('app.current_company_id', 'comp_a', true);"))
        customers_seen_by_a = db.scalars(select(Customer)).all()
        print(f"Company A queries customers: {len(customers_seen_by_a)} found (Expected: 1)")
        assert len(customers_seen_by_a) == 1, "Failed: Company A could not read its own customer!"
        print("RLS tenant isolation verified successfully.")

        # ==========================================================
        # 2. VERIFY JOB NUMBER GENERATOR DB TRIGGER
        # ==========================================================
        print("\n--- 2. Testing Job Number DB Trigger ---")
        
        # Insert jobs for Company A
        job_1 = Job(
            id="job_a1",
            company_id="comp_a",
            customer_id="cust_a1",
            trade="hvac",
            job_type="service",
            priority="routine",
            status="scheduled",
            source="phone"
        )
        job_2 = Job(
            id="job_a2",
            company_id="comp_a",
            customer_id="cust_a1",
            trade="hvac",
            job_type="maintenance",
            priority="urgent",
            status="scheduled",
            source="web"
        )
        db.add_all([job_1, job_2])
        db.flush()
        
        # Refresh and print job numbers
        db.refresh(job_1)
        db.refresh(job_2)
        print(f"Job 1 number: {job_1.job_number} (Expected: JOB-YYYY-00001)")
        print(f"Job 2 number: {job_2.job_number} (Expected: JOB-YYYY-00002)")
        assert job_1.job_number.startswith("JOB-"), "Failed: Job number prefix doesn't match"
        assert job_1.job_number.endswith("-00001"), "Failed: Sequence value not started at 1"
        assert job_2.job_number.endswith("-00002"), "Failed: Sequence not incrementing sequentially"
        print("Job number DB Trigger verified successfully.")

        # ==========================================================
        # 3. VERIFY UPDATED_AT TRIGGER
        # ==========================================================
        print("\n--- 3. Testing updated_at DB Trigger ---")
        old_updated_at = job_1.updated_at
        print(f"Original updated_at: {old_updated_at}")
        
        # Perform modification
        import time
        time.sleep(1) # wait a moment to ensure timestamp diff
        job_1.reported_problem = "Furnace is blowing cold air"
        db.flush()
        db.refresh(job_1)
        print(f"Updated updated_at:  {job_1.updated_at}")
        assert job_1.updated_at > old_updated_at, "Failed: updated_at was not updated by trigger!"
        print("updated_at trigger verified successfully.")

        # ==========================================================
        # 4. VERIFY COMPUTED COLUMNS (INVOICE BALANCE)
        # ==========================================================
        print("\n--- 4. Testing Invoice Computed Column ---")
        invoice = Invoice(
            id="inv_1",
            company_id="comp_a",
            job_id="job_a1",
            customer_id="cust_a1",
            invoice_number="INV-10001",
            status="draft",
            subtotal_cents=15000,
            tax_cents=1200,
            discount_cents=2000,
            total_cents=14200,
            amount_paid_cents=5000,
            tax_rate_bps=800,
            payment_terms="cod"
        )
        db.add(invoice)
        db.flush()
        db.refresh(invoice)
        print(f"Invoice balance_cents computed by DB: {invoice.balance_cents} (Expected: 9200)")
        assert invoice.balance_cents == 9200, f"Failed: Invoice computed balance mismatch, got {invoice.balance_cents}"
        print("Invoice computed column verified successfully.")

        # ==========================================================
        # 5. VERIFY LOYALTY LEDGER VIEW
        # ==========================================================
        print("\n--- 5. Testing Loyalty Balances View ---")
        loyalty_acc = LoyaltyAccount(
            id="loy_1",
            company_id="comp_a",
            customer_id="cust_a1",
            is_active=True
        )
        db.add(loyalty_acc)
        db.flush()

        # Add earning transactions
        txn1 = LoyaltyLedger(
            id="txn_1",
            company_id="comp_a",
            account_id="loy_1",
            entry_type="earn",
            points=100,
            description="Signed up for membership"
        )
        txn2 = LoyaltyLedger(
            id="txn_2",
            company_id="comp_a",
            account_id="loy_1",
            entry_type="earn",
            points=250,
            description="Service job bonus"
        )
        # Add a redemption transaction
        txn3 = LoyaltyLedger(
            id="txn_3",
            company_id="comp_a",
            account_id="loy_1",
            entry_type="redeem",
            points=50,
            description="Redeemed filter discount"
        )
        # Add an expired earn entry
        txn4 = LoyaltyLedger(
            id="txn_4",
            company_id="comp_a",
            account_id="loy_1",
            entry_type="earn",
            points=1000,
            expires_at=datetime.utcnow() - timedelta(days=1), # Expired yesterday
            description="Expired promotional points"
        )
        db.add_all([txn1, txn2, txn3, txn4])
        db.flush()

        # Query the View
        view_result = db.scalars(select(LoyaltyBalanceView).where(LoyaltyBalanceView.account_id == "loy_1")).first()
        print(f"Loyalty aggregate balance: {view_result.balance} (Expected: 300 = 100 + 250 - 50, promo 1000 excluded since expired)")
        print(f"Loyalty aggregate lifetime: {view_result.lifetime_earned} (Expected: 1350 = 100 + 250 + 1000)")
        assert view_result.balance == 300, f"Failed: balance mismatch, got {view_result.balance}"
        assert view_result.lifetime_earned == 1350, f"Failed: lifetime_earned mismatch, got {view_result.lifetime_earned}"
        print("Loyalty DB View verified successfully.")

        # ==========================================================
        # 6. VERIFY PGVECTOR EMBEDDING INTEGRATION
        # ==========================================================
        print("\n--- 6. Testing pgvector Embedding operations ---")
        
        # Define some embeddings of 1536 dimensions
        # Embedding for job A (HVAC repair)
        embedding_a = [0.01] * 1536
        embedding_a[0] = 0.5
        embedding_a[1] = 0.5
        
        # Embedding for job B (HVAC replacement)
        embedding_b = [0.01] * 1536
        embedding_b[0] = 0.49
        embedding_b[1] = 0.51
        
        # Embedding for job C (Garage Door repair - unrelated)
        embedding_c = [0.01] * 1536
        embedding_c[1000] = 0.99
        
        embed_job1 = JobEmbedding(
            id="emb_1",
            company_id="comp_a",
            job_id="job_a1",
            embedding=embedding_a,
            embed_text="Repair HVAC duct leakage and charge refrigerant",
            model_version="text-embedding-3-small"
        )
        embed_job2 = JobEmbedding(
            id="emb_2",
            company_id="comp_a",
            job_id="job_a2",
            embedding=embedding_b,
            embed_text="Replace condenser coil and compressor unit",
            model_version="text-embedding-3-small"
        )
        db.add_all([embed_job1, embed_job2])
        db.flush()

        # Query cosine similarity (distance <-> distance)
        # Using SQLAlchemy vector <-> operator (cosine distance)
        # Let's perform query using direct vector operators or raw text select
        results = db.execute(
            select(
                JobEmbedding.job_id,
                JobEmbedding.embed_text,
                JobEmbedding.embedding.cosine_distance(embedding_a).label("distance")
            ).order_by(text("distance ASC"))
        ).mappings().all()

        print("Similarity search results (ascending distance):")
        for r in results:
            print(f"  Job: {r['job_id']} | Text: '{r['embed_text']}' | Cosine Distance: {r['distance']:.5f}")
        
        assert results[0]['job_id'] == "job_a1", "Failed: The query embedding itself wasn't the closest result!"
        assert results[0]['distance'] < 0.01, "Failed: Cosine distance to exact matching vector should be zero/near-zero"
        assert results[1]['job_id'] == "job_a2", "Failed: Semantic match is not the second closest"
        print("pgvector embeddings verification successful.")

        # ==========================================================
        # 7. VERIFY RESET_MEMBERSHIP_PERIOD DB FUNCTION
        # ==========================================================
        print("\n--- 7. Testing reset_membership_period DB Function ---")
        plan_a = MembershipPlan(
            id="plan_a",
            company_id="comp_a",
            name="HVAC Comfort Plan",
            trade="hvac",
            is_active=True,
            monthly_price_cents=2999,
            included_visits_count=2,
            visit_reset_period="monthly",
            carryover_visits=True,
            labor_discount_pct=10.0,
            parts_discount_pct=10.0,
            priority_scheduling=True,
            loyalty_multiplier=1.5,
            sort_order=1
        )
        db.add(plan_a)
        db.flush()

        membership_a = Membership(
            id="mem_a",
            company_id="comp_a",
            customer_id="cust_a1",
            plan_id="plan_a",
            status="active",
            billing_cadence="monthly",
            current_period_start=datetime.utcnow() - timedelta(days=30),
            current_period_end=datetime.utcnow(),
            visits_used_this_period=1,
            visits_carried_over=0,
            enrolled_by="usr_admin_a"
        )
        db.add(membership_a)
        db.flush()

        # Call the reset function
        db.execute(text("SELECT reset_membership_period(:mem_id);"), {"mem_id": "mem_a"})
        db.flush()
        db.refresh(membership_a)

        print(f"Membership visits_used: {membership_a.visits_used_this_period} (Expected: 0)")
        print(f"Membership visits_carried_over: {membership_a.visits_carried_over} (Expected: 1)")
        
        assert membership_a.visits_used_this_period == 0, "Failed: visits_used_this_period should reset to 0"
        assert membership_a.visits_carried_over == 1, "Failed: visits_carried_over should carry over remaining visits"
        print("reset_membership_period DB function verified successfully.")

        # ==========================================================
        # 8. VERIFY CUSTOMER FULL-TEXT SEARCH
        # ==========================================================
        print("\n--- 8. Testing Customer Full-Text Search ---")
        # Search for Doe
        search_results = db.execute(
            text("SELECT id, first_name, last_name FROM customers WHERE to_tsvector('english', coalesce(first_name, '') || ' ' || coalesce(last_name, '')) @@ to_tsquery('english', :query)"),
            {"query": "Doe"}
        ).fetchall()
        print(f"Customer FTS search for 'Doe': {[r.first_name + ' ' + r.last_name for r in search_results]}")
        assert len(search_results) == 1, "Failed: Customer search did not find John Doe!"
        assert search_results[0].first_name == "John", "Failed: Incorrect customer search result"
        print("Customer Full-Text Search verified successfully.")

        # ==========================================================
        # 9. VERIFY SINGLE LEAD TECHNICIAN CONSTRAINT
        # ==========================================================
        print("\n--- 9. Testing Single Lead Technician Constraint ---")
        # Add a lead technician
        tech1 = JobTechnician(
            id="job_tech_1",
            company_id="comp_a",
            job_id="job_a1",
            tech_id="usr_tech_a",
            is_lead=True
        )
        db.add(tech1)
        db.flush()
        
        # Attempt to add another lead technician to same job - should fail
        from sqlalchemy.exc import IntegrityError
        tech2 = JobTechnician(
            id="job_tech_2",
            company_id="comp_a",
            job_id="job_a1",
            tech_id="usr_admin_a", # different user but also lead
            is_lead=True
        )
        db.add(tech2)
        try:
            db.flush()
            assert False, "Failed: Allowed two lead technicians on the same job!"
        except IntegrityError:
            print("Successfully blocked second lead technician on job (UniqueConstraint/Index violated).")
            db.rollback()
        
        print("Job Technician Single Lead Constraint verified successfully.")

        print("\n==================================================")
        print("VERIFICATION SUCCESSFUL! ALL TESTS PASSED.")
        print("==================================================")

    except Exception as e:
        print("\nVERIFICATION FAILED!")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_verification()
