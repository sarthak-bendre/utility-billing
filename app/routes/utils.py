from datetime import date

from flask import abort, request

from ..extensions import db


def get_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object")
    return data


def require_fields(data, *fields):
    missing = [f for f in fields if data.get(f) in (None, "")]
    if missing:
        abort(400, description=f"Missing required field(s): {', '.join(missing)}")


def validate_choice(value, choices, field):
    if value not in choices:
        abort(400, description=f"Invalid {field} '{value}'. Allowed: {', '.join(choices)}")
    return value


def parse_date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        abort(400, description=f"{field} must be an ISO date (YYYY-MM-DD)")


def parse_number(value, field):
    try:
        number = float(value)
    except (TypeError, ValueError):
        abort(400, description=f"{field} must be a number")
    if number < 0:
        abort(400, description=f"{field} cannot be negative")
    return number


def get_or_404(model, obj_id):
    obj = db.session.get(model, obj_id)
    if obj is None:
        abort(404, description=f"{model.__name__} {obj_id} not found")
    return obj


def paginate(query, serializer):
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 20, type=int), 1), 100)
    result = db.paginate(query, page=page, per_page=per_page, error_out=False)
    return {
        "items": [serializer(item) for item in result.items],
        "total": result.total,
        "page": result.page,
        "per_page": result.per_page,
        "pages": result.pages,
    }
