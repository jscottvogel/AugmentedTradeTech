import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Fallback defaults for local docker-compose setup
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "augmentedtradetech")

# Attempt to load from SST Linked Resources if they exist
try:
    from sst import Resource  # type: ignore
    if hasattr(Resource, "Database"):
        db_res = Resource.Database
        DB_USER = getattr(db_res, "username", DB_USER)
        DB_PASSWORD = getattr(db_res, "password", DB_PASSWORD)
        DB_HOST = getattr(db_res, "host", DB_HOST)
        DB_PORT = str(getattr(db_res, "port", DB_PORT))
        DB_NAME = getattr(db_res, "database", DB_NAME)
except ImportError:
    pass

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

from sqlalchemy.pool import NullPool

# SQLAlchemy engine config
import sys
IS_TESTING = (
    "pytest" in sys.modules 
    or any("pytest" in arg for arg in sys.argv) 
    or "PYTEST_CURRENT_TEST" in os.environ 
    or os.environ.get("TESTING", "") == "1"
)

engine_kwargs = {
    "pool_pre_ping": True
}
if IS_TESTING:
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def set_rls_context(conn, company_id: str | None, user_id: str | None, role: str | None):
    """
    Helper function that runs SET LOCAL for app.current_company_id, app.current_user_id, app.current_role
    via set_config(..., true) (the safe, parameterizable SQL equivalent of SET LOCAL).
    """
    company_val = company_id if company_id else ""
    user_val = user_id if user_id else ""
    role_val = role if role else ""
    
    conn.execute(
        text("SELECT set_config('app.current_company_id', :company_id, true)"),
        {"company_id": company_val}
    )
    conn.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": user_val}
    )
    conn.execute(
        text("SELECT set_config('app.current_role', :role, true)"),
        {"role": role_val}
    )

def get_db_session():
    """Simple generator to get session without FastAPI dependency context (e.g. for scripts)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db(request = None):
    """
    FastAPI dependency that returns a session-managed DB connection.
    If request is provided, automatically injects company, user, and role context 
    into Postgres session variables to satisfy Row-Level Security (RLS) policies.
    """
    db = SessionLocal()
    try:
        if request and hasattr(request, "state"):
            company_id = getattr(request.state, "company_id", None)
            user_id = getattr(request.state, "user_id", None)
            role = getattr(request.state, "role", None)
            set_rls_context(db, company_id, user_id, role)
        yield db
    finally:
        db.close()
