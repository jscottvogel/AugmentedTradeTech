from sqlalchemy import Column, String, Integer, DateTime, Numeric
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from apps.api.app.models.base import Base, AuditMixin
from apps.api.app.core.workflows import DEFAULT_WORKFLOW_CONFIG
import copy

class Company(Base, AuditMixin):
    __tablename__ = "companies"

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    job_number_seq = Column(Integer, nullable=False, server_default="0")
    logo_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address_line1 = Column(String, nullable=True)
    address_line2 = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    zip = Column(String, nullable=True)
    timezone = Column(String, nullable=False, server_default="America/Chicago")
    
    # Postgres specific types: GIN indexed or JSON fields
    trades = Column(ARRAY(String), nullable=False, server_default="{}")
    dispatch_mode = Column(String, nullable=False, server_default="dispatcher")
    workflow_config = Column(JSONB, nullable=False, server_default="{}", default=lambda: copy.deepcopy(DEFAULT_WORKFLOW_CONFIG))
    notification_config = Column(JSONB, nullable=False, server_default="{}")
    
    tax_rate_bps = Column(Integer, nullable=False, server_default="0")
    labor_rate_cents = Column(Integer, nullable=False, server_default="0")
    
    stripe_account_id = Column(String, nullable=True)
    
    qbo_realm_id = Column(String, nullable=True)
    qbo_access_token = Column(String, nullable=True)
    qbo_refresh_token = Column(String, nullable=True)
    qbo_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    qbo_item_mappings = Column(JSONB, nullable=False, server_default="{}")
    
    sns_spend_limit_usd = Column(Integer, nullable=False, server_default="100")
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    subscription_status = Column(String, nullable=False, server_default="trial")
    onboarding_step = Column(Integer, nullable=False, server_default="1")
    service_area_zips = Column(ARRAY(String), nullable=False, server_default="{}")
    business_hours = Column(JSONB, nullable=False, server_default="{}")

    # Loyalty Program Configurations
    loyalty_earn_rate = Column(Integer, nullable=False, server_default="1")
    loyalty_membership_multiplier = Column(Numeric(4, 2), nullable=False, server_default="1.00")
    loyalty_expiry_days = Column(Integer, nullable=True)
