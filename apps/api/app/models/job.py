from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Integer, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from apps.api.app.models.base import Base, TenantAuditMixin

class Job(Base, TenantAuditMixin):
    __tablename__ = "jobs"

    customer_id = Column(String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    equipment_id = Column(String, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True)
    job_number = Column(String, nullable=False)
    trade = Column(String, nullable=False) # hvac | garage_door
    job_type = Column(String, nullable=False) # service | maintenance | install | warranty | followup
    priority = Column(String, nullable=False, default="routine") # routine | urgent | emergency
    status = Column(String, nullable=False, default="scheduled")
    reported_problem = Column(String, nullable=True)
    dispatcher_notes = Column(String, nullable=True)
    scheduled_start = Column(DateTime(timezone=True), nullable=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=True)
    arrived_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    inspection_data = Column(JSONB, nullable=False, server_default="{}")
    ai_diagnosis = Column(JSONB, nullable=True)
    voice_transcript = Column(String, nullable=True)
    
    membership_id = Column(String, ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True)
    is_included_visit = Column(Boolean, nullable=False, default=False)
    source = Column(String, nullable=False, default="dispatcher") # dispatcher | pool | website | agentic | portal

    # Relationships
    technicians = relationship("JobTechnician", back_populates="job")
    photos = relationship("JobPhoto", back_populates="job")
    notes = relationship("JobNote", back_populates="job")
    status_history = relationship("JobStatusHistory", back_populates="job")
    customer = relationship("Customer")
    equipment = relationship("Equipment")
    parts = relationship("JobPart", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "job_number", name="uq_jobs_number"),
        CheckConstraint(
            status.in_(["scheduled", "confirmed", "en_route", "on_site", "in_progress", "parts_needed", "paused", "completed", "invoiced", "paid", "follow_up_required", "cancelled"]),
            name="chk_job_status"
        ),
        CheckConstraint(
            priority.in_(["routine", "urgent", "emergency"]),
            name="chk_job_priority"
        ),
        CheckConstraint(
            job_type.in_(["service", "maintenance", "install", "warranty", "followup"]),
            name="chk_job_type"
        ),
        Index("ix_jobs_company_id_status", "company_id", "status", postgresql_where=text("deleted_at IS NULL")),
        Index("ix_jobs_company_id_scheduled_start", "company_id", "scheduled_start", postgresql_where=text("deleted_at IS NULL")),
    )

class JobTechnician(Base):
    __tablename__ = "job_technicians"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    tech_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_lead = Column(Boolean, nullable=False, default=False)
    assigned_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    job = relationship("Job", back_populates="technicians")

    __table_args__ = (
        UniqueConstraint("job_id", "tech_id", name="uq_job_tech"),
        Index("ix_job_technicians_company_id_tech_id", "company_id", "tech_id"),
        Index("idx_job_technicians_single_lead", "job_id", unique=True, postgresql_where=text("is_lead = true")),
    )

class JobPhoto(Base):
    __tablename__ = "job_photos"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    tech_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    step_key = Column(String, nullable=True)
    photo_type = Column(String, nullable=False) # nameplate | fault | before | after | general
    s3_key = Column(String, nullable=False)
    cdn_url = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=False, default="image/jpeg")
    ai_analysis = Column(JSONB, nullable=True)
    caption = Column(String, nullable=True)
    taken_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    job = relationship("Job", back_populates="photos")

    __table_args__ = (
        CheckConstraint(
            photo_type.in_(["nameplate", "fault", "before", "after", "general"]),
            name="chk_photo_type"
        ),
    )

class JobNote(Base):
    __tablename__ = "job_notes"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    note_type = Column(String, nullable=False, default="general") # general | dispatch | ai_summary | voice_transcript
    body = Column(String, nullable=False)
    is_internal = Column(Boolean, nullable=False, default=True)
    voice_s3_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    job = relationship("Job", back_populates="notes")

class JobStatusHistory(Base):
    __tablename__ = "job_status_history"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    changed_by = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    note = Column(String, nullable=True)

    # Relationships
    job = relationship("Job", back_populates="status_history")

class JobPart(Base, TenantAuditMixin):
    __tablename__ = "job_parts"

    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price_cents = Column(Integer, nullable=False, default=0)
    serial_number = Column(String, nullable=True)

    # Relationships
    job = relationship("Job", back_populates="parts")
