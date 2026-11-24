from flask import Blueprint, abort, jsonify, request
from sqlalchemy import or_, select

from ..extensions import db
from ..models import CONNECTION_TYPES, Bill, Complaint, Customer
from .utils import get_json, get_or_404, paginate, require_fields, validate_choice

bp = Blueprint("customers", __name__)

EDITABLE_FIELDS = ("name", "email", "phone", "address", "connection_type", "is_active")


def _email_taken(email, exclude_id=None):
    stmt = select(Customer.id).where(Customer.email == email)
    if exclude_id:
        stmt = stmt.where(Customer.id != exclude_id)
    return db.session.scalar(stmt) is not None


@bp.get("")
def list_customers():
    stmt = select(Customer).order_by(Customer.id.desc())
    if q := request.args.get("q", "").strip():
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(like),
                Customer.account_no.ilike(like),
                Customer.email.ilike(like),
                Customer.phone.ilike(like),
            )
        )
    if ctype := request.args.get("connection_type"):
        stmt = stmt.where(Customer.connection_type == ctype)
    if (active := request.args.get("is_active")) is not None:
        stmt = stmt.where(Customer.is_active == (active.lower() in ("1", "true", "yes")))
    return jsonify(paginate(stmt, lambda c: c.to_dict(with_summary=True)))


@bp.post("")
def create_customer():
    data = get_json()
    require_fields(data, "name", "email", "phone", "address")
    ctype = validate_choice(
        data.get("connection_type", "residential"), CONNECTION_TYPES, "connection_type"
    )
    email = data["email"].strip().lower()
    if _email_taken(email):
        abort(409, description="A customer with this email already exists")

    customer = Customer(
        account_no="PENDING",
        name=data["name"].strip(),
        email=email,
        phone=str(data["phone"]).strip(),
        address=data["address"].strip(),
        connection_type=ctype,
    )
    db.session.add(customer)
    db.session.flush()  # obtain id to build the account number
    customer.account_no = f"ACC{100000 + customer.id}"
    db.session.commit()
    return jsonify(customer.to_dict(with_summary=True)), 201


@bp.get("/<int:customer_id>")
def get_customer(customer_id):
    customer = get_or_404(Customer, customer_id)
    data = customer.to_dict(with_summary=True)
    recent_bills = sorted(customer.bills, key=lambda b: b.issue_date, reverse=True)[:5]
    recent_complaints = sorted(customer.complaints, key=lambda c: c.created_at, reverse=True)[:5]
    data["recent_bills"] = [b.to_dict() for b in recent_bills]
    data["recent_complaints"] = [c.to_dict() for c in recent_complaints]
    return jsonify(data)


@bp.route("/<int:customer_id>", methods=["PUT", "PATCH"])
def update_customer(customer_id):
    customer = get_or_404(Customer, customer_id)
    data = get_json()
    if request.method == "PUT":
        require_fields(data, "name", "email", "phone", "address")

    for field in EDITABLE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field == "connection_type":
            validate_choice(value, CONNECTION_TYPES, field)
        elif field == "email":
            value = value.strip().lower()
            if _email_taken(value, exclude_id=customer.id):
                abort(409, description="A customer with this email already exists")
        elif field == "is_active":
            value = bool(value)
        elif isinstance(value, str):
            value = value.strip()
            if not value:
                abort(400, description=f"{field} cannot be empty")
        setattr(customer, field, value)

    db.session.commit()
    return jsonify(customer.to_dict(with_summary=True))


@bp.delete("/<int:customer_id>")
def delete_customer(customer_id):
    customer = get_or_404(Customer, customer_id)
    db.session.delete(customer)
    db.session.commit()
    return "", 204


@bp.get("/<int:customer_id>/bills")
def customer_bills(customer_id):
    get_or_404(Customer, customer_id)
    stmt = select(Bill).where(Bill.customer_id == customer_id).order_by(Bill.issue_date.desc())
    return jsonify(paginate(stmt, lambda b: b.to_dict()))


@bp.get("/<int:customer_id>/complaints")
def customer_complaints(customer_id):
    get_or_404(Customer, customer_id)
    stmt = (
        select(Complaint)
        .where(Complaint.customer_id == customer_id)
        .order_by(Complaint.created_at.desc())
    )
    return jsonify(paginate(stmt, lambda c: c.to_dict()))
