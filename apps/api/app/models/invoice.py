from sqlalchemy import Column, String, Boolean, Integer, Date, DateTime, Numeric, ForeignKey, CheckConstraint, UniqueConstraint, Computed, Index, text
from sqlalchemy.orm import relationship
from apps.api.app.models.base import Base, TenantAuditMixin

class Invoice(Base, TenantAuditMixin):
    __tablename__ = "invoices"

    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    customer_id = Column(String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")
    subtotal_cents = Column(Integer, nullable=False, default=0)
    tax_cents = Column(Integer, nullable=False, default=0)
    discount_cents = Column(Integer, nullable=False, default=0)
    total_cents = Column(Integer, nullable=False, default=0)
    amount_paid_cents = Column(Integer, nullable=False, default=0)
    
    # Generated computed column
    balance_cents = Column(Integer, Computed("total_cents - amount_paid_cents", persisted=True))
    
    tax_rate_bps = Column(Integer, nullable=False, default=0)
    due_date = Column(Date, nullable=True)
    payment_terms = Column(String, nullable=False, default="due_on_receipt")
    notes = Column(String, nullable=True)
    customer_signature_url = Column(String, nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    stripe_invoice_id = Column(String, nullable=True, index=True)
    qbo_invoice_id = Column(String, nullable=True)

    # Relationships
    line_items = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice")

    __table_args__ = (
        UniqueConstraint("company_id", "invoice_number", name="uq_invoices_number"),
        CheckConstraint(
            status.in_(["draft", "sent", "viewed", "paid", "void", "refunded"]),
            name="chk_invoice_status"
        ),
        Index("ix_invoices_company_id_status", "company_id", "status", postgresql_where=text("deleted_at IS NULL")),
    )

class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    invoice_id = Column(String, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    line_type = Column(String, nullable=False) # labor | part | fee
    description = Column(String, nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False, default=1)
    unit_price_cents = Column(Integer, nullable=False, default=0)
    
    # Generated computed column
    total_cents = Column(Integer, Computed("round(quantity * unit_price_cents)::integer", persisted=True))
    
    is_taxable = Column(Boolean, nullable=False, default=True)
    discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    discount_reason = Column(String, nullable=True) # member_discount | promo | manual
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")

    __table_args__ = (
        CheckConstraint(
            line_type.in_(["labor", "part", "fee"]),
            name="chk_line_type"
        ),
    )

class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    invoice_id = Column(String, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    payment_method = Column(String, nullable=False) # card_present | card_manual | payment_link | check | cash | net_terms | points_redemption
    status = Column(String, nullable=False, default="pending") # pending | succeeded | failed | refunded
    stripe_payment_intent_id = Column(String, nullable=True, index=True)
    stripe_charge_id = Column(String, nullable=True)
    collected_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    collected_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")

    __table_args__ = (
        CheckConstraint(
            payment_method.in_(["card_present", "card_manual", "payment_link", "check", "cash", "net_terms", "points_redemption"]),
            name="chk_payment_method"
        ),
        CheckConstraint(
            status.in_(["pending", "succeeded", "failed", "refunded"]),
            name="chk_payment_status"
        ),
    )
