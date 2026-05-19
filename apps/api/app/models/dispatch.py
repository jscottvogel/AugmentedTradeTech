from sqlalchemy import Column, String, DateTime, Numeric, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from apps.api.app.models.base import Base

class JobPool(Base):
    __tablename__ = "job_pool"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    posted_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    claimed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="open") # open | claimed | expired | recalled
    required_trades = Column(ARRAY(String), nullable=False, server_default="{}")
    required_skills = Column(ARRAY(String), nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

class TechLocationPing(Base):
    __tablename__ = "tech_location_pings"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    tech_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lat = Column(Numeric(9, 6), nullable=False)
    lng = Column(Numeric(9, 6), nullable=False)
    accuracy_m = Column(Integer, nullable=True)
    pinged_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
