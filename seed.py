"""Populate the database with sample customers, bills and complaints.

Usage:  python seed.py          (adds sample data)
        python seed.py --reset  (drops all tables first)
"""

import random
import sys
from datetime import date, datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import Bill, Complaint, ComplaintUpdate, Customer, utcnow
from app.services.billing import calculate_bill, compute_late_fee

CUSTOMERS = [
    ("Aarav Sharma", "Flat 12, Green Park, Pune", "residential"),
    ("Priya Nair", "22 MG Road, Bengaluru", "residential"),
    ("Rohan Mehta", "7 Lake View Society, Mumbai", "residential"),
    ("Sneha Kulkarni", "B-4 Shivaji Nagar, Pune", "residential"),
    ("Vikram Singh", "45 Civil Lines, Jaipur", "residential"),
    ("Ananya Iyer", "3 Anna Salai, Chennai", "residential"),
    ("FreshMart Groceries", "Shop 5, Market Yard, Pune", "commercial"),
    ("TechNest Co-working", "Floor 3, Cyber Tower, Hyderabad", "commercial"),
    ("Hotel Sunrise", "88 Beach Road, Goa", "commercial"),
    ("Kabir Das", "16 Model Town, Delhi", "residential"),
]

COMPLAINTS = [
    ("electricity", "Frequent power cuts", "Power goes off 3-4 times every evening.", "high"),
    ("water", "Low water pressure", "Water pressure is very low in the mornings.", "medium"),
    ("billing", "Bill amount too high", "This month's bill is double the usual amount.", "medium"),
    ("meter", "Meter not working", "The electricity meter display is blank.", "high"),
    ("water", "Contaminated water", "Tap water is muddy since two days.", "critical"),
    ("electricity", "Voltage fluctuation", "Appliances are tripping due to voltage drops.", "high"),
    ("other", "Change of address", "Need to update my communication address.", "low"),
    ("billing", "Payment not reflected", "Paid online but bill still shows unpaid.", "medium"),
]

STAFF = ["R. Patil (Lineman)", "S. Joshi (Water Dept)", "M. Khan (Billing)", None]


def months_ago(n):
    d = date.today().replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


def seed(reset=False):
    random.seed(42)
    if reset:
        db.drop_all()
        db.create_all()

    customers = []
    for i, (name, address, ctype) in enumerate(CUSTOMERS, start=1):
        email = name.lower().replace(" ", ".").replace("-", "") + "@example.com"
        if db.session.query(Customer).filter_by(email=email).first():
            continue
        c = Customer(
            account_no="PENDING",
            name=name,
            email=email,
            phone=f"98{random.randint(10000000, 99999999)}",
            address=address,
            connection_type=ctype,
        )
        db.session.add(c)
        db.session.flush()
        c.account_no = f"ACC{100000 + c.id}"
        customers.append(c)

    # Six months of bills per customer per utility.
    for c in customers:
        for utility in ("electricity", "water"):
            reading = random.randint(1000, 5000) if utility == "electricity" else random.randint(100, 800)
            for m in range(5, -1, -1):
                start = months_ago(m)
                issue = start + timedelta(days=random.randint(1, 5))
                if utility == "electricity":
                    usage = random.randint(80, 450) * (4 if c.connection_type == "commercial" else 1)
                else:
                    usage = random.randint(6, 30) * (3 if c.connection_type == "commercial" else 1)
                calc = calculate_bill(utility, c.connection_type, reading, reading + usage)
                reading += usage
                due = issue + timedelta(days=15)
                if m >= 2 or (m == 1 and random.random() < 0.7):
                    status, paid = "paid", issue + timedelta(days=random.randint(2, 14))
                else:
                    status, paid = "unpaid", None
                bill = Bill(
                    bill_no="PENDING",
                    customer_id=c.id,
                    utility_type=utility,
                    period_start=start,
                    period_end=issue,
                    previous_reading=calc["previous_reading"],
                    current_reading=calc["current_reading"],
                    units_consumed=calc["units_consumed"],
                    consumption_charge=calc["consumption_charge"],
                    fixed_charge=calc["fixed_charge"],
                    tax_amount=calc["tax_amount"],
                    late_fee=0,
                    total_amount=calc["total_amount"],
                    status=status,
                    issue_date=issue,
                    due_date=due,
                    paid_date=paid,
                )
                if status == "unpaid" and due < date.today():
                    bill.late_fee = compute_late_fee(bill.total_amount)
                    bill.total_amount += bill.late_fee
                    bill.status = "overdue"
                db.session.add(bill)
                db.session.flush()
                prefix = "EB" if utility == "electricity" else "WB"
                bill.bill_no = f"{prefix}{issue:%Y%m}-{bill.id:05d}"

    # Complaints in various stages of resolution.
    for i, (category, subject, desc, priority) in enumerate(COMPLAINTS):
        if not customers:
            break
        c = customers[i % len(customers)]
        created = utcnow() - timedelta(days=random.randint(5, 40), hours=random.randint(0, 23))
        status = ["open", "in_progress", "resolved", "closed"][i % 4]
        comp = Complaint(
            ticket_no="PENDING",
            customer_id=c.id,
            category=category,
            subject=subject,
            description=desc,
            priority=priority,
            status=status,
            assigned_to=STAFF[i % len(STAFF)] if status != "open" else None,
            created_at=created,
            updated_at=created,
        )
        db.session.add(comp)
        db.session.flush()
        comp.ticket_no = f"TKT{created:%y%m}-{comp.id:05d}"
        comp.updates.append(
            ComplaintUpdate(status="open", note="Complaint registered", updated_by=c.name, created_at=created)
        )
        if status != "open":
            t = created + timedelta(hours=random.randint(2, 24))
            comp.updates.append(
                ComplaintUpdate(status="in_progress", note=f"Assigned to {comp.assigned_to}", updated_by="admin", created_at=t)
            )
            comp.updated_at = t
        if status in ("resolved", "closed"):
            t = comp.updated_at + timedelta(hours=random.randint(4, 72))
            comp.updates.append(
                ComplaintUpdate(status=status, note="Issue fixed and verified", updated_by="admin", created_at=t)
            )
            comp.resolved_at = comp.updated_at = t

    db.session.commit()
    print(f"Seeded {len(customers)} customers with bills and complaints.")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        seed(reset="--reset" in sys.argv)
