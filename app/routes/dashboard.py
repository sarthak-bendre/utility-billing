from datetime import date

from flask import Blueprint, jsonify
from sqlalchemy import func, select

from ..extensions import db
from ..models import COMPLAINT_STATUSES, Bill, Complaint, Customer
from .bills import refresh_overdue_bills

bp = Blueprint("dashboard", __name__)


def _month_keys(n=6):
    today = date.today()
    keys = []
    y, m = today.year, today.month
    for _ in range(n):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(keys))


@bp.get("/summary")
def summary():
    refresh_overdue_bills()
    scalar = db.session.scalar

    total_customers = scalar(select(func.count(Customer.id)))
    active_customers = scalar(select(func.count(Customer.id)).where(Customer.is_active.is_(True)))

    billed = scalar(select(func.coalesce(func.sum(Bill.total_amount), 0)))
    collected = scalar(
        select(func.coalesce(func.sum(Bill.total_amount), 0)).where(Bill.status == "paid")
    )
    bill_counts = dict(db.session.execute(select(Bill.status, func.count()).group_by(Bill.status)).all())

    complaint_counts = dict(
        db.session.execute(select(Complaint.status, func.count()).group_by(Complaint.status)).all()
    )
    by_category = dict(
        db.session.execute(
            select(Complaint.category, func.count()).group_by(Complaint.category)
        ).all()
    )
    avg_resolution_hours = None
    resolved = db.session.execute(
        select(Complaint.created_at, Complaint.resolved_at).where(Complaint.resolved_at.is_not(None))
    ).all()
    if resolved:
        hours = [(r.resolved_at - r.created_at).total_seconds() / 3600 for r in resolved]
        avg_resolution_hours = round(sum(hours) / len(hours), 1)

    # Monthly billed vs collected, split by utility (done in Python to stay DB-agnostic).
    months = _month_keys()
    monthly = {
        k: {"month": k, "electricity": 0.0, "water": 0.0, "collected": 0.0} for k in months
    }
    for issue_date, utility, amount, status in db.session.execute(
        select(Bill.issue_date, Bill.utility_type, Bill.total_amount, Bill.status)
    ).all():
        key = f"{issue_date:%Y-%m}"
        if key in monthly:
            monthly[key][utility] += float(amount)
            if status == "paid":
                monthly[key]["collected"] += float(amount)

    recent_complaints = db.session.scalars(
        select(Complaint).order_by(Complaint.created_at.desc()).limit(5)
    ).all()
    overdue_bills = db.session.scalars(
        select(Bill).where(Bill.status == "overdue").order_by(Bill.due_date).limit(5)
    ).all()

    return jsonify(
        {
            "customers": {"total": total_customers, "active": active_customers},
            "billing": {
                "total_billed": round(float(billed), 2),
                "collected": round(float(collected), 2),
                "outstanding": round(float(billed) - float(collected), 2),
                "unpaid": bill_counts.get("unpaid", 0),
                "paid": bill_counts.get("paid", 0),
                "overdue": bill_counts.get("overdue", 0),
            },
            "complaints": {
                "total": sum(complaint_counts.values()),
                "by_status": {s: complaint_counts.get(s, 0) for s in COMPLAINT_STATUSES},
                "by_category": by_category,
                "avg_resolution_hours": avg_resolution_hours,
            },
            "monthly": [
                {k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()}
                for row in monthly.values()
            ],
            "recent_complaints": [c.to_dict() for c in recent_complaints],
            "overdue_bills": [b.to_dict() for b in overdue_bills],
        }
    )
