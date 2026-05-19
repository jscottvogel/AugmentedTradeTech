from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from apps.api.app.models.base import Base, TenantAuditMixin

class Customer(Base, TenantAuditMixin):
    __tablename__ = "customers"

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True, index=True)
    address_line1 = Column(String, nullable=True)
    address_line2 = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    zip = Column(String, nullable=True)
    customer_type = Column(String, nullable=False, default="residential") # residential | commercial
    notes = Column(String, nullable=True)
    portal_enabled = Column(Boolean, nullable=False, default=True)
    portal_last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    equipment_associations = relationship("EquipmentCustomer", back_populates="customer")

    __table_args__ = (
        Index(
            "idx_customers_name_search",
            text("to_tsvector('english', coalesce(first_name, '') || ' ' || coalesce(last_name, ''))"),
            postgresql_using="gin",
        ),
    )

class Equipment(Base, TenantAuditMixin):
    __tablename__ = "equipment"

    trade = Column(String, nullable=False) # hvac | garage_door
    equipment_type = Column(String, nullable=False) # split_ac, heat_pump, etc.
    make = Column(String, nullable=True)
    model = Column(String, nullable=True)
    serial_number = Column(String, nullable=True)
    install_date = Column(Date, nullable=True)
    warranty_expires = Column(Date, nullable=True)
    location_notes = Column(String, nullable=True)
    nameplate_photo_url = Column(String, nullable=True)
    ai_extracted_data = Column(JSONB, nullable=False, server_default="{}")

    # Relationships
    customer_associations = relationship("EquipmentCustomer", back_populates="equipment")

    __table_args__ = (
        Index("ix_equipment_company_id_serial_number", "company_id", "serial_number"),
    )

class EquipmentCustomer(Base):
    __tablename__ = "equipment_customers"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    equipment_id = Column(String, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="equipment_associations")
    equipment = relationship("Equipment", back_populates="customer_associations")

    __table_args__ = (
        UniqueConstraint("equipment_id", "customer_id", name="uq_equipment_customer"),
    )
