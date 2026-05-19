from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship
from apps.api.app.models.base import Base, AuditMixin, TenantAuditMixin

class User(Base, AuditMixin):
    __tablename__ = "users"

    # company_id is Nullable for platform_admin
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    phone = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    role = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tech_profile = relationship("TechProfile", back_populates="user", uselist=False, foreign_keys="[TechProfile.user_id]")

    __table_args__ = (
        CheckConstraint(
            role.in_(["platform_admin", "company_admin", "dispatcher", "tech"]),
            name="chk_role"
        ),
    )

class TechProfile(Base, TenantAuditMixin):
    __tablename__ = "tech_profiles"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    availability_status = Column(String, nullable=False, default="offline")
    trades = Column(ARRAY(String), nullable=False, server_default="{}")
    certifications = Column(JSONB, nullable=False, server_default="[]")
    skills = Column(ARRAY(String), nullable=False, server_default="{}")
    truck_id = Column(String, nullable=True)
    license_number = Column(String, nullable=True)
    hire_date = Column(Date, nullable=True)

    # Relationships
    user = relationship("User", back_populates="tech_profile", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(
            availability_status.in_(["available", "on_job", "driving", "break", "off_duty", "offline"]),
            name="chk_availability"
        ),
    )
