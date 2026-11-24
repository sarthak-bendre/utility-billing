from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import or_, select

from ..extensions import db
from ..models import (
    COMPLAINT_CATEGORIES,
    COMPLAINT_PRIORITIES,
    COMPLAINT_STATUSES,
    Complaint,
    ComplaintUpdate,
    Customer,
    utcnow,
)
from .utils import get_json, get_or_404, paginate, require_fields, validate_choice

bp = Blueprint("complaints", __name__)

# Allowed status transitions for the complaint workflow.
TRANSITIONS = {
    "open": {"in_progress", "resolved", "closed"},
    "in_progress": {"open", "resolved", "closed"},
    "resolved": {"in_progress", "closed"},  # reopen if the fix didn't hold
    "closed": set(),                         # final
}


@bp.get("")
def list_complaints():
    stmt = select(Complaint).join(Customer)
    if status := request.args.get("status"):
        stmt = stmt.where(Complaint.status == status)
    if priority := request.args.get("priority"):
        stmt = stmt.where(Complaint.priority == priority)
    if category := request.args.get("category"):
        stmt = stmt.where(Complaint.category == category)
    if customer_id := request.args.get("customer_id", type=int):
        stmt = stmt.where(Complaint.customer_id == customer_id)
    if q := request.args.get("q", "").strip():
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Complaint.ticket_no.ilike(like),
                Complaint.subject.ilike(like),
                Customer.name.ilike(like),
                Customer.account_no.ilike(like),
            )
        )
    stmt = stmt.order_by(Complaint.created_at.desc(), Complaint.id.desc())
    return jsonify(paginate(stmt, lambda c: c.to_dict()))


@bp.post("")
def register_complaint():
    data = get_json()
    require_fields(data, "customer_id", "category", "subject", "description")
    customer = get_or_404(Customer, data["customer_id"])
    category = validate_choice(data["category"], COMPLAINT_CATEGORIES, "category")
    priority = validate_choice(data.get("priority", "medium"), COMPLAINT_PRIORITIES, "priority")

    complaint = Complaint(
        ticket_no="PENDING",
        customer_id=customer.id,
        category=category,
        subject=data["subject"].strip(),
        description=data["description"].strip(),
        priority=priority,
    )
    db.session.add(complaint)
    db.session.flush()
    complaint.ticket_no = f"TKT{utcnow():%y%m}-{complaint.id:05d}"
    complaint.updates.append(
        ComplaintUpdate(status="open", note="Complaint registered", updated_by=customer.name)
    )
    db.session.commit()
    return jsonify(complaint.to_dict(with_history=True)), 201


@bp.get("/<int:complaint_id>")
def get_complaint(complaint_id):
    return jsonify(get_or_404(Complaint, complaint_id).to_dict(with_history=True))


@bp.route("/<int:complaint_id>", methods=["PUT", "PATCH"])
def update_complaint(complaint_id):
    """Administrative update: change status, priority, assignee and/or add a note."""
    complaint = get_or_404(Complaint, complaint_id)
    data = get_json()
    updated_by = (data.get("updated_by") or "admin").strip()
    changes = []

    if "status" in data and data["status"] != complaint.status:
        new_status = validate_choice(data["status"], COMPLAINT_STATUSES, "status")
        if new_status not in TRANSITIONS[complaint.status]:
            abort(400, description=f"Cannot move complaint from {complaint.status} to {new_status}")
        changes.append(f"Status: {complaint.status} → {new_status}")
        complaint.status = new_status
        if new_status in ("resolved", "closed"):
            complaint.resolved_at = complaint.resolved_at or utcnow()
        else:
            complaint.resolved_at = None

    if "priority" in data and data["priority"] != complaint.priority:
        validate_choice(data["priority"], COMPLAINT_PRIORITIES, "priority")
        changes.append(f"Priority: {complaint.priority} → {data['priority']}")
        complaint.priority = data["priority"]

    if "assigned_to" in data and (data["assigned_to"] or None) != complaint.assigned_to:
        complaint.assigned_to = (data["assigned_to"] or "").strip() or None
        changes.append(f"Assigned to: {complaint.assigned_to or 'nobody'}")

    for field in ("subject", "description"):
        if field in data and data[field] and data[field].strip() != getattr(complaint, field):
            setattr(complaint, field, data[field].strip())
            changes.append(f"{field.capitalize()} edited")

    note = (data.get("note") or "").strip()
    if not changes and not note:
        abort(400, description="Nothing to update")

    complaint.updated_at = utcnow()
    complaint.updates.append(
        ComplaintUpdate(
            status=complaint.status,
            note="; ".join(filter(None, ["; ".join(changes), note])),
            updated_by=updated_by,
        )
    )
    db.session.commit()
    return jsonify(complaint.to_dict(with_history=True))


@bp.delete("/<int:complaint_id>")
def delete_complaint(complaint_id):
    complaint = get_or_404(Complaint, complaint_id)
    db.session.delete(complaint)
    db.session.commit()
    return "", 204
