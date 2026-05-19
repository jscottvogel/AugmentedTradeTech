"""initial_schema

Revision ID: 8a123ad92009
Revises: 
Create Date: 2026-05-19 17:31:17.722391

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector

# revision identifiers, used by Alembic.
revision: str = '8a123ad92009'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create triggers / utility functions
    op.execute("""
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION generate_job_number(p_company_id TEXT) RETURNS TEXT AS $$
    DECLARE
        v_seq INTEGER;
        v_year TEXT;
    BEGIN
        v_year := to_char(now(), 'YYYY');
        UPDATE companies
           SET job_number_seq = job_number_seq + 1
         WHERE id = p_company_id
        RETURNING job_number_seq INTO v_seq;
        RETURN 'JOB-' || v_year || '-' || LPAD(v_seq::TEXT, 5, '0');
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION trigger_set_job_number() RETURNS TRIGGER AS $$
    BEGIN
        NEW.job_number := generate_job_number(NEW.company_id);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION reset_membership_period(p_membership_id TEXT) RETURNS VOID AS $$
    DECLARE
        v_mem   RECORD;
        v_carry INTEGER;
    BEGIN
        SELECT m.*, p.carryover_visits, p.included_visits_count
          INTO v_mem
          FROM memberships m
          JOIN membership_plans p ON p.id = m.plan_id
         WHERE m.id = p_membership_id
           FOR UPDATE;

        v_carry := CASE
            WHEN v_mem.carryover_visits
            THEN GREATEST(0,
                v_mem.visits_carried_over +
                v_mem.included_visits_count - v_mem.visits_used_this_period
            )
            ELSE 0
        END;

        UPDATE memberships SET
            visits_used_this_period = 0,
            visits_carried_over     = v_carry,
            current_period_start    = current_period_end,
            current_period_end      = CASE
                WHEN billing_cadence = 'monthly'
                THEN current_period_end + INTERVAL '1 month'
                ELSE current_period_end + INTERVAL '1 year'
            END,
            updated_at = now()
        WHERE id = p_membership_id;
    END;
    $$ LANGUAGE plpgsql;
    """)


    # 3. Create Tables (solving cycles by postponing foreign keys)
    op.create_table('companies',
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('job_number_seq', sa.Integer(), server_default='0', nullable=False),
        sa.Column('logo_url', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('address_line1', sa.String(), nullable=True),
        sa.Column('address_line2', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('zip', sa.String(), nullable=True),
        sa.Column('timezone', sa.String(), server_default='America/Chicago', nullable=False),
        sa.Column('trades', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('dispatch_mode', sa.String(), server_default='dispatcher', nullable=False),
        sa.Column('workflow_config', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('notification_config', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('tax_rate_bps', sa.Integer(), server_default='0', nullable=False),
        sa.Column('labor_rate_cents', sa.Integer(), server_default='0', nullable=False),
        sa.Column('stripe_account_id', sa.String(), nullable=True),
        sa.Column('qbo_realm_id', sa.String(), nullable=True),
        sa.Column('qbo_access_token', sa.String(), nullable=True),
        sa.Column('qbo_refresh_token', sa.String(), nullable=True),
        sa.Column('qbo_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sns_spend_limit_usd', sa.Integer(), server_default='100', nullable=False),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('subscription_status', sa.String(), server_default='trial', nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_companies_slug'), 'companies', ['slug'], unique=True)

    op.create_table('users',
        sa.Column('company_id', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('platform_admin', 'company_admin', 'dispatcher', 'tech')", name='chk_role'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_company_id'), 'users', ['company_id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # Postpone companies references to users table
    op.create_foreign_key('fk_companies_created_by_users', 'companies', 'users', ['created_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_companies_updated_by_users', 'companies', 'users', ['updated_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_users_created_by_users', 'users', 'users', ['created_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_users_updated_by_users', 'users', 'users', ['updated_by'], ['id'], ondelete='SET NULL')

    op.create_table('audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=True),
        sa.Column('actor_id', sa.String(), nullable=True),
        sa.Column('actor_role', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('before_state', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('after_state', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('customers',
        sa.Column('first_name', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('address_line1', sa.String(), nullable=True),
        sa.Column('address_line2', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('zip', sa.String(), nullable=True),
        sa.Column('customer_type', sa.String(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('portal_enabled', sa.Boolean(), nullable=False),
        sa.Column('portal_last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customers_email'), 'customers', ['email'], unique=False)
    op.create_index(op.f('ix_customers_phone'), 'customers', ['phone'], unique=False)
    op.execute(
        "CREATE INDEX idx_customers_name_search ON customers USING gin ("
        "to_tsvector('english', coalesce(first_name, '') || ' ' || coalesce(last_name, ''))"
        ");"
    )

    op.create_table('equipment',
        sa.Column('trade', sa.String(), nullable=False),
        sa.Column('equipment_type', sa.String(), nullable=False),
        sa.Column('make', sa.String(), nullable=True),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('serial_number', sa.String(), nullable=True),
        sa.Column('install_date', sa.Date(), nullable=True),
        sa.Column('warranty_expires', sa.Date(), nullable=True),
        sa.Column('location_notes', sa.String(), nullable=True),
        sa.Column('nameplate_photo_url', sa.String(), nullable=True),
        sa.Column('ai_extracted_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_equipment_company_id_serial_number', 'equipment', ['company_id', 'serial_number'], unique=False)

    op.create_table('membership_plans',
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('trade', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('monthly_price_cents', sa.Integer(), nullable=True),
        sa.Column('annual_price_cents', sa.Integer(), nullable=True),
        sa.Column('included_visits_count', sa.Integer(), nullable=False),
        sa.Column('visit_reset_period', sa.String(), nullable=False),
        sa.Column('carryover_visits', sa.Boolean(), nullable=False),
        sa.Column('labor_discount_pct', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('parts_discount_pct', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('priority_scheduling', sa.Boolean(), nullable=False),
        sa.Column('loyalty_multiplier', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('stripe_monthly_price_id', sa.String(), nullable=True),
        sa.Column('stripe_annual_price_id', sa.String(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("trade IN ('hvac', 'garage_door', 'both')", name='chk_plan_trade'),
        sa.CheckConstraint('monthly_price_cents IS NOT NULL OR annual_price_cents IS NOT NULL', name='chk_has_price'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('sync_queue',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('operation', sa.String(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('client_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('conflict_detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('server_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_attempted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_sync_queue_company_id_user_id_status', 'sync_queue', ['company_id', 'user_id', 'status'], unique=False)

    op.create_table('tech_location_pings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('tech_id', sa.String(), nullable=False),
        sa.Column('lat', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('lng', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('accuracy_m', sa.Integer(), nullable=True),
        sa.Column('pinged_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tech_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('tech_profiles',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('availability_status', sa.String(), nullable=False),
        sa.Column('trades', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('certifications', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('skills', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('truck_id', sa.String(), nullable=True),
        sa.Column('license_number', sa.String(), nullable=True),
        sa.Column('hire_date', sa.Date(), nullable=True),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("availability_status IN ('available', 'on_job', 'driving', 'break', 'off_duty', 'offline')", name='chk_availability'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    op.create_table('equipment_customers',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('equipment_id', sa.String(), nullable=False),
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('equipment_id', 'customer_id', name='uq_equipment_customer')
    )
    # Unique partial index: Only one primary customer per equipment unit
    op.execute("CREATE UNIQUE INDEX idx_equipment_primary_customer ON equipment_customers(equipment_id) WHERE is_primary = true;")

    op.create_table('loyalty_accounts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'customer_id', name='uq_loyalty_account')
    )

    op.create_table('memberships',
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('plan_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('billing_cadence', sa.String(), nullable=False),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('visits_used_this_period', sa.Integer(), nullable=False),
        sa.Column('visits_carried_over', sa.Integer(), nullable=False),
        sa.Column('enrolled_by', sa.String(), nullable=False),
        sa.Column('enrolled_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.String(), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('next_renewal_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('grace_period_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("billing_cadence IN ('monthly', 'annual')", name='chk_billing_cadence'),
        sa.CheckConstraint("status IN ('active', 'paused', 'suspended', 'cancelled', 'expired')", name='chk_membership_status'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['membership_plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_subscription_id')
    )
    op.create_index(op.f('ix_memberships_customer_id'), 'memberships', ['customer_id'], unique=False)
    op.create_index('ix_memberships_next_renewal_at', 'memberships', ['next_renewal_at'], unique=False, postgresql_where=sa.text("status = 'active'"))

    op.create_table('jobs',
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('equipment_id', sa.String(), nullable=True),
        sa.Column('job_number', sa.String(), nullable=False),
        sa.Column('trade', sa.String(), nullable=False),
        sa.Column('job_type', sa.String(), nullable=False),
        sa.Column('priority', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reported_problem', sa.String(), nullable=True),
        sa.Column('dispatcher_notes', sa.String(), nullable=True),
        sa.Column('scheduled_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scheduled_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('arrived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('inspection_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('ai_diagnosis', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('voice_transcript', sa.String(), nullable=True),
        sa.Column('membership_id', sa.String(), nullable=True),
        sa.Column('is_included_visit', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("job_type IN ('service', 'maintenance', 'install', 'warranty', 'followup')", name='chk_job_type'),
        sa.CheckConstraint("priority IN ('routine', 'urgent', 'emergency')", name='chk_job_priority'),
        sa.CheckConstraint("status IN ('scheduled', 'confirmed', 'en_route', 'on_site', 'in_progress', 'parts_needed', 'paused', 'completed', 'invoiced', 'paid', 'follow_up_required', 'cancelled')", name='chk_job_status'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['membership_id'], ['memberships.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'job_number', name='uq_jobs_number')
    )
    op.create_index(op.f('ix_jobs_customer_id'), 'jobs', ['customer_id'], unique=False)
    op.create_index(op.f('ix_jobs_equipment_id'), 'jobs', ['equipment_id'], unique=False)
    op.create_index(op.f('ix_jobs_membership_id'), 'jobs', ['membership_id'], unique=False)
    op.create_index('ix_jobs_company_id_scheduled_start', 'jobs', ['company_id', 'scheduled_start'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('ix_jobs_company_id_status', 'jobs', ['company_id', 'status'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))

    # Attach generator trigger to jobs
    op.execute("CREATE TRIGGER trigger_generate_job_number BEFORE INSERT ON jobs FOR EACH ROW EXECUTE FUNCTION trigger_set_job_number();")

    op.create_table('ai_requests',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=True),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('job_id', sa.String(), nullable=True),
        sa.Column('request_type', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd_micro', sa.Integer(), nullable=True),
        sa.Column('feature_tag', sa.String(), nullable=False),
        sa.Column('cache_hit', sa.Boolean(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_detail', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('invoices',
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('invoice_number', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('subtotal_cents', sa.Integer(), nullable=False),
        sa.Column('tax_cents', sa.Integer(), nullable=False),
        sa.Column('discount_cents', sa.Integer(), nullable=False),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('amount_paid_cents', sa.Integer(), nullable=False),
        sa.Column('balance_cents', sa.Integer(), sa.Computed('total_cents - amount_paid_cents', persisted=True), nullable=True),
        sa.Column('tax_rate_bps', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('payment_terms', sa.String(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('customer_signature_url', sa.String(), nullable=True),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_invoice_id', sa.String(), nullable=True),
        sa.Column('qbo_invoice_id', sa.String(), nullable=True),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'sent', 'viewed', 'paid', 'void', 'refunded')", name='chk_invoice_status'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'invoice_number', name='uq_invoices_number'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index(op.f('ix_invoices_customer_id'), 'invoices', ['customer_id'], unique=False)
    op.create_index(op.f('ix_invoices_stripe_invoice_id'), 'invoices', ['stripe_invoice_id'], unique=False)
    op.create_index('ix_invoices_company_id_status', 'invoices', ['company_id', 'status'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))

    op.create_table('job_embeddings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(1536), nullable=False),
        sa.Column('embed_text', sa.String(), nullable=False),
        sa.Column('model_version', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.execute(
        "CREATE INDEX idx_job_embeddings_hnsw ON job_embeddings USING hnsw ("
        "embedding vector_cosine_ops"
        ");"
    )

    op.create_table('job_notes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('author_id', sa.String(), nullable=False),
        sa.Column('note_type', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('is_internal', sa.Boolean(), nullable=False),
        sa.Column('voice_s3_key', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('job_photos',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('tech_id', sa.String(), nullable=False),
        sa.Column('step_key', sa.String(), nullable=True),
        sa.Column('photo_type', sa.String(), nullable=False),
        sa.Column('s3_key', sa.String(), nullable=False),
        sa.Column('cdn_url', sa.String(), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('ai_analysis', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('caption', sa.String(), nullable=True),
        sa.Column('taken_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.CheckConstraint("photo_type IN ('nameplate', 'fault', 'before', 'after', 'general')", name='chk_photo_type'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tech_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('job_pool',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('posted_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claimed_by', sa.String(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('required_trades', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('required_skills', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['claimed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )

    op.create_table('job_status_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('from_status', sa.String(), nullable=True),
        sa.Column('to_status', sa.String(), nullable=False),
        sa.Column('changed_by', sa.String(), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('note', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('job_technicians',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('tech_id', sa.String(), nullable=False),
        sa.Column('is_lead', sa.Boolean(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tech_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'tech_id', name='uq_job_tech')
    )
    op.create_index('ix_job_technicians_company_id_tech_id', 'job_technicians', ['company_id', 'tech_id'], unique=False)
    op.execute(
        "CREATE UNIQUE INDEX idx_job_technicians_single_lead ON job_technicians (job_id) "
        "WHERE is_lead = true;"
    )

    op.create_table('invoice_line_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('invoice_id', sa.String(), nullable=False),
        sa.Column('line_type', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('unit_price_cents', sa.Integer(), nullable=False),
        sa.Column('total_cents', sa.Integer(), sa.Computed('round(quantity * unit_price_cents)::integer', persisted=True), nullable=True),
        sa.Column('is_taxable', sa.Boolean(), nullable=False),
        sa.Column('discount_pct', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('discount_reason', sa.String(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.CheckConstraint("line_type IN ('labor', 'part', 'fee')", name='chk_line_type'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('loyalty_ledger',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('entry_type', sa.String(), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=True),
        sa.Column('invoice_id', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voided_by', sa.String(), nullable=True),
        sa.Column('idempotency_key', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.CheckConstraint("entry_type IN ('earn', 'redeem', 'expire', 'adjustment_credit', 'adjustment_debit')", name='chk_entry_type'),
        sa.CheckConstraint('points > 0', name='chk_points_positive'),
        sa.ForeignKeyConstraint(['account_id'], ['loyalty_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['voided_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_loyalty_ledger_account_id_created_at', 'loyalty_ledger', ['account_id', 'created_at'], unique=False)

    op.create_table('payments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_id', sa.String(), nullable=False),
        sa.Column('invoice_id', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('payment_method', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=True),
        sa.Column('stripe_charge_id', sa.String(), nullable=True),
        sa.Column('collected_by', sa.String(), nullable=True),
        sa.Column('collected_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.CheckConstraint("payment_method IN ('card_present', 'card_manual', 'payment_link', 'check', 'cash', 'net_terms', 'points_redemption')", name='chk_payment_method'),
        sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed', 'refunded')", name='chk_payment_status'),
        sa.ForeignKeyConstraint(['collected_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payments_stripe_payment_intent_id'), 'payments', ['stripe_payment_intent_id'], unique=False)

    # 4. Create loyalty_balances view dynamically
    op.execute("""
    CREATE OR REPLACE VIEW loyalty_balances AS
    SELECT 
        la.id AS account_id,
        la.company_id,
        la.customer_id,
        COALESCE(SUM(CASE WHEN ll.entry_type IN ('earn', 'adjustment_credit') AND (ll.expires_at IS NULL OR ll.expires_at > now()) AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) -
        COALESCE(SUM(CASE WHEN ll.entry_type IN ('redeem', 'expire', 'adjustment_debit') AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) AS balance,
        COALESCE(SUM(CASE WHEN ll.entry_type = 'earn' AND ll.voided_at IS NULL THEN ll.points ELSE 0 END), 0) AS lifetime_earned
    FROM loyalty_accounts la
    LEFT JOIN loyalty_ledger ll ON la.id = ll.account_id
    GROUP BY la.id, la.company_id, la.customer_id;
    """)

    # 5. Bind BEFORE UPDATE triggers to maintain updated_at automatically
    tables_with_updated_at = [
        'companies', 'users', 'customers', 'equipment', 'membership_plans',
        'tech_profiles', 'memberships', 'jobs', 'invoices', 'job_embeddings',
        'job_notes', 'payments', 'loyalty_accounts'
    ]
    for table in tables_with_updated_at:
        op.execute(f"CREATE TRIGGER trigger_update_timestamp BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();")

    # 6. Apply Row-Level Security (RLS) policies to tenant-scoped tables
    # Enable RLS and force it for the owner/superuser during local dev/tests
    rls_tables = [
        'companies', 'users', 'tech_profiles', 'customers', 'equipment', 'equipment_customers',
        'jobs', 'job_technicians', 'job_photos', 'job_notes', 'job_status_history',
        'invoices', 'invoice_line_items', 'payments', 'membership_plans', 'memberships',
        'loyalty_accounts', 'loyalty_ledger', 'job_pool', 'tech_location_pings',
        'sync_queue', 'ai_requests', 'audit_log', 'job_embeddings'
    ]
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

    # Apply policy for companies (matched by id)
    op.execute("""
    CREATE POLICY tenant_isolation_policy ON companies
    FOR ALL
    USING (
        id = NULLIF(current_setting('app.current_company_id', true), '')::text
        OR current_setting('app.current_role', true) = 'platform_admin'
    );
    """)

    # Apply policy for other tables (matched by company_id)
    # RLS tenant scope + platform admin bypass
    for table in rls_tables:
        if table == 'companies':
            continue
        op.execute(f"""
        CREATE POLICY tenant_isolation_policy ON {table}
        FOR ALL
        USING (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::text
            OR current_setting('app.current_role', true) = 'platform_admin'
        );
        """)

def downgrade() -> None:
    # 1. Disable RLS policies
    rls_tables = [
        'companies', 'users', 'tech_profiles', 'customers', 'equipment', 'equipment_customers',
        'jobs', 'job_technicians', 'job_photos', 'job_notes', 'job_status_history',
        'invoices', 'invoice_line_items', 'payments', 'membership_plans', 'memberships',
        'loyalty_accounts', 'loyalty_ledger', 'job_pool', 'tech_location_pings',
        'sync_queue', 'ai_requests', 'audit_log', 'job_embeddings'
    ]
    for table in rls_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # 2. Drop View
    op.execute("DROP VIEW IF EXISTS loyalty_balances;")

    # 3. Drop Tables (in reverse dependency order)
    op.drop_index(op.f('ix_payments_stripe_payment_intent_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index('ix_loyalty_ledger_account_id_created_at', table_name='loyalty_ledger')
    op.drop_table('loyalty_ledger')
    op.drop_table('invoice_line_items')
    op.execute("DROP INDEX IF EXISTS idx_job_technicians_single_lead;")
    op.drop_index('ix_job_technicians_company_id_tech_id', table_name='job_technicians')
    op.drop_table('job_technicians')
    op.drop_table('job_status_history')
    op.drop_table('job_pool')
    op.drop_table('job_photos')
    op.drop_table('job_notes')
    op.execute("DROP INDEX IF EXISTS idx_job_embeddings_hnsw;")
    op.drop_table('job_embeddings')
    op.drop_index('ix_invoices_company_id_status', table_name='invoices')
    op.drop_index(op.f('ix_invoices_stripe_invoice_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_customer_id'), table_name='invoices')
    op.drop_table('invoices')
    op.drop_table('ai_requests')
    op.drop_index('ix_jobs_company_id_status', table_name='jobs')
    op.drop_index('ix_jobs_company_id_scheduled_start', table_name='jobs')
    op.drop_index(op.f('ix_jobs_membership_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_equipment_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_customer_id'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index('ix_memberships_next_renewal_at', table_name='memberships')
    op.drop_index(op.f('ix_memberships_customer_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_table('loyalty_accounts')
    op.execute("DROP INDEX IF EXISTS idx_equipment_primary_customer;")
    op.drop_table('equipment_customers')
    op.drop_table('tech_profiles')
    op.drop_table('tech_location_pings')
    op.drop_index('ix_sync_queue_company_id_user_id_status', table_name='sync_queue')
    op.drop_table('sync_queue')
    op.drop_table('membership_plans')
    op.drop_index('ix_equipment_company_id_serial_number', table_name='equipment')
    op.drop_table('equipment')
    op.execute("DROP INDEX IF EXISTS idx_customers_name_search;")
    op.drop_index(op.f('ix_customers_phone'), table_name='customers')
    op.drop_index(op.f('ix_customers_email'), table_name='customers')
    op.drop_table('customers')
    op.drop_table('audit_log')

    # Remove companies constraints
    op.drop_constraint('fk_companies_created_by_users', 'companies', type_='foreignkey')
    op.drop_constraint('fk_companies_updated_by_users', 'companies', type_='foreignkey')
    op.drop_constraint('fk_users_created_by_users', 'users', type_='foreignkey')
    op.drop_constraint('fk_users_updated_by_users', 'users', type_='foreignkey')

    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_company_id'), table_name='users')
    op.drop_table('users')
    
    op.drop_index(op.f('ix_companies_slug'), table_name='companies')
    op.drop_table('companies')

    # 4. Drop trigger functions
    op.execute("DROP FUNCTION IF EXISTS reset_membership_period(TEXT);")
    op.execute("DROP FUNCTION IF EXISTS trigger_set_job_number();")
    op.execute("DROP FUNCTION IF EXISTS generate_job_number(TEXT);")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    
    # 5. Disable pgvector extension
    op.execute("DROP EXTENSION IF EXISTS vector;")
