"""enable_rls_policies

Revision ID: f4d69055536d
Revises: 8a123ad92009
Create Date: 2026-05-19 18:11:12.177291

"""
from typing import Sequence, Union

from alembic import op  # type: ignore
import sqlalchemy as sa  # type: ignore


# revision identifiers, used by Alembic.
revision: str = 'f4d69055536d'
down_revision: Union[str, Sequence[str], None] = '8a123ad92009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

rls_tables = [
    'companies', 'users', 'tech_profiles', 'customers', 'equipment', 'equipment_customers',
    'jobs', 'job_technicians', 'job_photos', 'job_notes', 'job_status_history',
    'invoices', 'invoice_line_items', 'payments', 'membership_plans', 'memberships',
    'loyalty_accounts', 'loyalty_ledger', 'job_pool', 'tech_location_pings',
    'sync_queue', 'ai_requests', 'audit_log', 'job_embeddings'
]

soft_delete_tables = [
    'companies', 'users', 'tech_profiles', 'customers', 'equipment', 'membership_plans',
    'memberships', 'jobs', 'invoices'
]


def upgrade() -> None:
    # 1. Enable RLS and Force RLS on all tenant tables (ensuring they are active)
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

    # 2. Re-create tenant isolation policies to align definitions
    for table in rls_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        if table == 'companies':
            op.execute("""
            CREATE POLICY tenant_isolation_policy ON companies
            FOR ALL
            USING (
                id = NULLIF(current_setting('app.current_company_id', true), '')::text
                OR current_setting('app.current_role', true) = 'platform_admin'
            );
            """)
        else:
            op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            FOR ALL
            USING (
                company_id = NULLIF(current_setting('app.current_company_id', true), '')::text
                OR current_setting('app.current_role', true) = 'platform_admin'
            );
            """)

    # 3. Create no_deleted (RESTRICTIVE) policies on tables with soft delete columns
    for table in soft_delete_tables:
        op.execute(f"DROP POLICY IF EXISTS no_deleted ON {table};")
        op.execute(f"""
        CREATE POLICY no_deleted ON {table}
        AS RESTRICTIVE
        FOR ALL
        USING (
            deleted_at IS NULL
            OR current_setting('app.current_role', true) IN ('company_admin', 'platform_admin')
        );
        """)

    # 4. Create tech_job_scope (RESTRICTIVE) policy on jobs table
    op.execute("DROP POLICY IF EXISTS tech_job_scope ON jobs;")
    op.execute("""
    CREATE POLICY tech_job_scope ON jobs
    AS RESTRICTIVE
    FOR ALL
    USING (
        current_setting('app.current_role', true) IN ('company_admin', 'platform_admin', 'dispatcher')
        OR (
            current_setting('app.current_role', true) = 'tech'
            AND EXISTS (
                SELECT 1 FROM job_technicians jt
                WHERE jt.job_id = jobs.id
                AND jt.tech_id = NULLIF(current_setting('app.current_user_id', true), '')::text
            )
        )
    );
    """)


def downgrade() -> None:
    # 1. Drop restrictive policies
    op.execute("DROP POLICY IF EXISTS tech_job_scope ON jobs;")
    
    for table in soft_delete_tables:
        op.execute(f"DROP POLICY IF EXISTS no_deleted ON {table};")

    # 2. Re-create default tenant_isolation_policies
    for table in rls_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        if table == 'companies':
            op.execute("""
            CREATE POLICY tenant_isolation_policy ON companies
            FOR ALL
            USING (
                id = NULLIF(current_setting('app.current_company_id', true), '')::text
                OR current_setting('app.current_role', true) = 'platform_admin'
            );
            """)
        else:
            op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            FOR ALL
            USING (
                company_id = NULLIF(current_setting('app.current_company_id', true), '')::text
                OR current_setting('app.current_role', true) = 'platform_admin'
            );
            """)
