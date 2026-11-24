from datetime import date, timedelta

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import select

from ..extensions import db
from ..models import UTILITY_TYPES, Bill, Customer
from ..services.billing import TARIFFS, calculate_bill, compute_late_fee, default_due_date
from .utils import (
    get_json,
    get_or_404,
    paginate,
    parse_date,
    parse_number,
    require_fields,
    validate_choice,
)

bp = Blueprint("bills", __name__)


def refresh_overdue_bills():
    """Mark unpaid bills past their due date as overdue and apply the late fee once."""
    overdue = db.session.scalars(
        select(Bill).where(Bill.status == "unpaid", Bill.due_date < date.today())
    ).all()
    for bill in overdue:
        fee = compute_late_fee(bill.total_amount)
        bill.late_fee = fee
        bill.total_amount = bill.total_amount + fee
        bill.status = "overdue"
    if overdue:
        db.session.commit()
    return len(overdue)


def _last_reading(customer_id, utility_type, exclude_id=None):
    stmt = (
        select(Bill.current_reading)
        .where(Bill.customer_id == customer_id, Bill.utility_type == utility_type)
        .order_by(Bill.period_end.desc(), Bill.id.desc())
        .limit(1)
    )
    if exclude_id:
        stmt = stmt.where(Bill.id != exclude_id)
    value = db.session.scalar(stmt)
    return float(value) if value is not None else 0.0


def _calc_or_400(*args):
    try:
        return calculate_bill(*args)
    except ValueError as exc:
        abort(400, description=str(exc))


def _resolve_inputs(data, customer):
    utility_type = validate_choice(data.get("utility_type"), UTILITY_TYPES, "utility_type")
    current = parse_number(data.get("current_reading"), "current_reading")
    if data.get("previous_reading") not in (None, ""):
        previous = parse_number(data["previous_reading"], "previous_reading")
    else:
        previous = _last_reading(customer.id, utility_type)
    return utility_type, previous, current


@bp.get("/tariffs")
def tariffs():
    return jsonify(TARIFFS)


@bp.post("/preview")
def preview_bill():
    """Calculate a bill without saving it."""
    data = get_json()
    require_fields(data, "customer_id", "utility_type", "current_reading")
    customer = get_or_404(Customer, data["customer_id"])
    utility_type, previous, current = _resolve_inputs(data, customer)
    calc = _calc_or_400(utility_type, customer.connection_type, previous, current)
    return jsonify({k: (float(v) if k != "breakdown" else v) for k, v in calc.items()})


@bp.get("")
def list_bills():
    refresh_overdue_bills()
    stmt = select(Bill).order_by(Bill.issue_date.desc(), Bill.id.desc())
    if customer_id := request.args.get("customer_id", type=int):
        stmt = stmt.where(Bill.customer_id == customer_id)
    if utility := request.args.get("utility_type"):
        stmt = stmt.where(Bill.utility_type == utility)
    if status := request.args.get("status"):
        stmt = stmt.where(Bill.status == status)
    if q := request.args.get("q", "").strip():
        like = f"%{q}%"
        stmt = stmt.join(Customer).where(
            Bill.bill_no.ilike(like) | Customer.name.ilike(like) | Customer.account_no.ilike(like)
        )
    return jsonify(paginate(stmt, lambda b: b.to_dict()))


@bp.post("")
def create_bill():
    data = get_json()
    require_fields(data, "customer_id", "utility_type", "current_reading")
    customer = get_or_404(Customer, data["customer_id"])
    if not customer.is_active:
        abort(400, description="Cannot bill an inactive customer")

    utility_type, previous, current = _resolve_inputs(data, customer)
    calc = _calc_or_400(utility_type, customer.connection_type, previous, current)

    today = date.today()
    period_end = parse_date(data.get("period_end"), "period_end") or today
    period_start = parse_date(data.get("period_start"), "period_start") or (
        period_end - timedelta(days=30)
    )
    if period_start > period_end:
        abort(400, description="period_start must be before period_end")
    issue_date = parse_date(data.get("issue_date"), "issue_date") or today
    due_date = parse_date(data.get("due_date"), "due_date") or default_due_date(issue_date)

    bill = Bill(
        bill_no="PENDING",
        customer_id=customer.id,
        utility_type=utility_type,
        period_start=period_start,
        period_end=period_end,
        previous_reading=calc["previous_reading"],
        current_reading=calc["current_reading"],
        units_consumed=calc["units_consumed"],
        consumption_charge=calc["consumption_charge"],
        fixed_charge=calc["fixed_charge"],
        tax_amount=calc["tax_amount"],
        late_fee=0,
        total_amount=calc["total_amount"],
        issue_date=issue_date,
        due_date=due_date,
    )
    db.session.add(bill)
    db.session.flush()
    prefix = "EB" if utility_type == "electricity" else "WB"
    bill.bill_no = f"{prefix}{issue_date:%Y%m}-{bill.id:05d}"
    db.session.commit()

    result = bill.to_dict()
    result["breakdown"] = calc["breakdown"]
    return jsonify(result), 201


@bp.get("/<int:bill_id>")
def get_bill(bill_id):
    bill = get_or_404(Bill, bill_id)
    data = bill.to_dict()
    data["breakdown"] = calculate_bill(
        bill.utility_type, bill.customer.connection_type, bill.previous_reading, bill.current_reading
    )["breakdown"]
    return jsonify(data)


@bp.route("/<int:bill_id>", methods=["PUT", "PATCH"])
def update_bill(bill_id):
    """Correct readings / dates on a bill that has not been paid yet; recalculates charges."""
    bill = get_or_404(Bill, bill_id)
    if bill.status == "paid":
        abort(400, description="Paid bills cannot be modified")
    data = get_json()

    previous = (
        parse_number(data["previous_reading"], "previous_reading")
        if "previous_reading" in data
        else bill.previous_reading
    )
    current = (
        parse_number(data["current_reading"], "current_reading")
        if "current_reading" in data
        else bill.current_reading
    )
    calc = _calc_or_400(bill.utility_type, bill.customer.connection_type, previous, current)

    for field in ("period_start", "period_end", "due_date"):
        if field in data:
            setattr(bill, field, parse_date(data[field], field))

    bill.previous_reading = calc["previous_reading"]
    bill.current_reading = calc["current_reading"]
    bill.units_consumed = calc["units_consumed"]
    bill.consumption_charge = calc["consumption_charge"]
    bill.fixed_charge = calc["fixed_charge"]
    bill.tax_amount = calc["tax_amount"]
    # Re-evaluate overdue status against the (possibly new) due date.
    bill.late_fee = 0
    bill.status = "unpaid"
    bill.total_amount = calc["total_amount"]
    db.session.commit()
    refresh_overdue_bills()
    return jsonify(bill.to_dict())


@bp.post("/<int:bill_id>/pay")
def pay_bill(bill_id):
    refresh_overdue_bills()
    bill = get_or_404(Bill, bill_id)
    if bill.status == "paid":
        abort(400, description="Bill is already paid")
    data = request.get_json(silent=True) or {}
    paid_date = parse_date(data.get("paid_date"), "paid_date") or date.today()
    bill.status = "paid"
    bill.paid_date = paid_date
    db.session.commit()
    return jsonify(bill.to_dict())


@bp.delete("/<int:bill_id>")
def delete_bill(bill_id):
    bill = get_or_404(Bill, bill_id)
    db.session.delete(bill)
    db.session.commit()
    return "", 204
