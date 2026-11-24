"""Bill calculation engine.

Consumption is charged using tiered (slab) tariffs, which differ by utility and
connection type. A fixed monthly charge and tax are added on top; bills paid
after their due date attract a late fee.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")

# Each slab is (upper limit of units, rate per unit). None = no upper limit.
TARIFFS = {
    "electricity": {  # units = kWh
        "residential": {
            "slabs": [(100, "3.50"), (300, "5.00"), (500, "6.50"), (None, "8.00")],
            "fixed_charge": "50.00",
        },
        "commercial": {
            "slabs": [(200, "7.00"), (1000, "8.50"), (None, "10.00")],
            "fixed_charge": "150.00",
        },
    },
    "water": {  # units = kilolitres
        "residential": {
            "slabs": [(10, "8.00"), (25, "12.00"), (None, "18.00")],
            "fixed_charge": "30.00",
        },
        "commercial": {
            "slabs": [(50, "20.00"), (None, "28.00")],
            "fixed_charge": "100.00",
        },
    },
}

TAX_RATE = Decimal("0.05")        # 5% tax on consumption + fixed charge
LATE_FEE_RATE = Decimal("0.02")   # 2% of total if paid after the due date
MIN_LATE_FEE = Decimal("25.00")
DUE_DAYS = 15


def _q(value):
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def slab_charge(units, slabs):
    """Return (charge, breakdown) for `units` across tiered slabs."""
    units = Decimal(units)
    remaining = units
    lower = Decimal(0)
    charge = Decimal(0)
    breakdown = []
    for upper, rate in slabs:
        if remaining <= 0:
            break
        rate = Decimal(rate)
        band = remaining if upper is None else min(remaining, Decimal(upper) - lower)
        amount = band * rate
        breakdown.append(
            {
                "from": float(lower),
                "to": None if upper is None else float(upper),
                "units": float(band),
                "rate": float(rate),
                "amount": float(_q(amount)),
            }
        )
        charge += amount
        remaining -= band
        if upper is not None:
            lower = Decimal(upper)
    return _q(charge), breakdown


def calculate_bill(utility_type, connection_type, previous_reading, current_reading):
    """Compute all monetary components of a bill from meter readings."""
    if utility_type not in TARIFFS:
        raise ValueError(f"Unknown utility type '{utility_type}'")
    if connection_type not in TARIFFS[utility_type]:
        raise ValueError(f"Unknown connection type '{connection_type}'")

    previous_reading = Decimal(str(previous_reading))
    current_reading = Decimal(str(current_reading))
    if current_reading < previous_reading:
        raise ValueError("current_reading cannot be lower than previous_reading")

    tariff = TARIFFS[utility_type][connection_type]
    units = current_reading - previous_reading
    consumption_charge, breakdown = slab_charge(units, tariff["slabs"])
    fixed_charge = _q(tariff["fixed_charge"])
    tax = _q((consumption_charge + fixed_charge) * TAX_RATE)
    total = _q(consumption_charge + fixed_charge + tax)

    return {
        "previous_reading": _q(previous_reading),
        "current_reading": _q(current_reading),
        "units_consumed": _q(units),
        "consumption_charge": consumption_charge,
        "fixed_charge": fixed_charge,
        "tax_amount": tax,
        "total_amount": total,
        "breakdown": breakdown,
    }


def compute_late_fee(base_total):
    return max(_q(Decimal(base_total) * LATE_FEE_RATE), MIN_LATE_FEE)


def default_due_date(issue_date=None):
    return (issue_date or date.today()) + timedelta(days=DUE_DAYS)
