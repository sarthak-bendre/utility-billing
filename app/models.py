from datetime import date, datetime, timezone

from .extensions import db

UTILITY_TYPES = ("electricity", "water")
CONNECTION_TYPES = ("residential", "commercial")
BILL_STATUSES = ("unpaid", "paid", "overdue")
COMPLAINT_CATEGORIES = ("electricity", "water", "billing", "meter", "other")
COMPLAINT_PRIORITIES = ("low", "medium", "high", "critical")
COMPLAINT_STATUSES = ("open", "in_progress", "resolved", "closed")


def utcnow():
    """Naive UTC timestamp (stored without tz info for MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _money(value):
    return float(value) if value is not None else None


def _iso(value):
    return value.isoformat() if value else None


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    account_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    connection_type = db.Column(db.String(20), nullable=False, default="residential")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    bills = db.relationship("Bill", back_populates="customer", cascade="all, delete-orphan")
    complaints = db.relationship(
        "Complaint", back_populates="customer", cascade="all, delete-orphan"
    )

    def to_dict(self, with_summary=False):
        data = {
            "id": self.id,
            "account_no": self.account_no,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "connection_type": self.connection_type,
            "is_active": self.is_active,
            "created_at": _iso(self.created_at),
        }
        if with_summary:
            outstanding = sum(float(b.total_amount) for b in self.bills if b.status != "paid")
            data["outstanding_amount"] = round(outstanding, 2)
            data["bill_count"] = len(self.bills)
            data["open_complaints"] = sum(
                1 for c in self.complaints if c.status in ("open", "in_progress")
            )
        return data


class Bill(db.Model):
    __tablename__ = "bills"

    id = db.Column(db.Integer, primary_key=True)
    bill_no = db.Column(db.String(30), unique=True, nullable=False, index=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    utility_type = db.Column(db.String(20), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    previous_reading = db.Column(db.Numeric(12, 2), nullable=False)
    current_reading = db.Column(db.Numeric(12, 2), nullable=False)
    units_consumed = db.Column(db.Numeric(12, 2), nullable=False)
    consumption_charge = db.Column(db.Numeric(12, 2), nullable=False)
    fixed_charge = db.Column(db.Numeric(12, 2), nullable=False)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False)
    late_fee = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="unpaid", index=True)
    issue_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=False)
    paid_date = db.Column(db.Date)

    customer = db.relationship("Customer", back_populates="bills")

    def to_dict(self):
        return {
            "id": self.id,
            "bill_no": self.bill_no,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else None,
            "account_no": self.customer.account_no if self.customer else None,
            "utility_type": self.utility_type,
            "period_start": _iso(self.period_start),
            "period_end": _iso(self.period_end),
            "previous_reading": _money(self.previous_reading),
            "current_reading": _money(self.current_reading),
            "units_consumed": _money(self.units_consumed),
            "consumption_charge": _money(self.consumption_charge),
            "fixed_charge": _money(self.fixed_charge),
            "tax_amount": _money(self.tax_amount),
            "late_fee": _money(self.late_fee),
            "total_amount": _money(self.total_amount),
            "status": self.status,
            "issue_date": _iso(self.issue_date),
            "due_date": _iso(self.due_date),
            "paid_date": _iso(self.paid_date),
        }


class Complaint(db.Model):
    __tablename__ = "complaints"

    id = db.Column(db.Integer, primary_key=True)
    ticket_no = db.Column(db.String(30), unique=True, nullable=False, index=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="medium")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    assigned_to = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    resolved_at = db.Column(db.DateTime)

    customer = db.relationship("Customer", back_populates="complaints")
    updates = db.relationship(
        "ComplaintUpdate",
        back_populates="complaint",
        cascade="all, delete-orphan",
        order_by="ComplaintUpdate.created_at",
    )

    def to_dict(self, with_history=False):
        data = {
            "id": self.id,
            "ticket_no": self.ticket_no,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else None,
            "account_no": self.customer.account_no if self.customer else None,
            "category": self.category,
            "subject": self.subject,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "resolved_at": _iso(self.resolved_at),
        }
        if with_history:
            data["history"] = [u.to_dict() for u in self.updates]
        return data


class ComplaintUpdate(db.Model):
    """Audit trail of every status change / note on a complaint."""

    __tablename__ = "complaint_updates"

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(
        db.Integer, db.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = db.Column(db.String(20), nullable=False)
    note = db.Column(db.Text)
    updated_by = db.Column(db.String(120), nullable=False, default="system")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    complaint = db.relationship("Complaint", back_populates="updates")

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "note": self.note,
            "updated_by": self.updated_by,
            "created_at": _iso(self.created_at),
        }
