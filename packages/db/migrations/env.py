import sys
import os
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

# Add monorepo root to sys.path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

# Import the database URL resolved by database.py
from apps.api.app.core.database import DATABASE_URL

# Import all SQLAlchemy models to register them on Base.metadata
from apps.api.app.models.base import Base
from apps.api.app.models.company import Company
from apps.api.app.models.user import User, TechProfile
from apps.api.app.models.customer import Customer, Equipment, EquipmentCustomer
from apps.api.app.models.job import Job, JobTechnician, JobPhoto, JobNote, JobStatusHistory
from apps.api.app.models.invoice import Invoice, InvoiceLineItem, Payment
from apps.api.app.models.membership import MembershipPlan, Membership
from apps.api.app.models.loyalty import LoyaltyAccount, LoyaltyLedger, LoyaltyBalanceView
from apps.api.app.models.dispatch import JobPool, TechLocationPing
from apps.api.app.models.sync import SyncQueue
from apps.api.app.models.ai import AIRequest, JobEmbedding, AuditLog
from apps.api.app.models.auth import MagicLinkToken, RefreshToken, CustomerMagicLinkToken

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set metadata for autogenerate support
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Use our database engine configuration dynamically
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

