from datetime import date, timedelta

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.services.billing import calculate_bill


@pytest.fixture
def client():
    app = create_app(TestConfig)
    with app.test_client() as client, app.app_context():
        yield client
        db.session.remove()
        db.drop_all()


def make_customer(client, **overrides):
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "phone": "9876543210",
        "address": "1 Test Street",
        "connection_type": "residential",
    }
    payload.update(overrides)
    res = client.post("/api/customers", json=payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()


# ---------- billing engine ----------

def test_slab_calculation_residential_electricity():
    # 100*3.5 + 150*5.0 = 350 + 750 = 1100; fixed 50; tax 5% of 1150 = 57.50
    calc = calculate_bill("electricity", "residential", 1000, 1250)
    assert float(calc["units_consumed"]) == 250
    assert float(calc["consumption_charge"]) == 1100.00
    assert float(calc["fixed_charge"]) == 50.00
    assert float(calc["tax_amount"]) == 57.50
    assert float(calc["total_amount"]) == 1207.50


def test_slab_calculation_water_top_slab():
    # 10*8 + 15*12 + 5*18 = 80 + 180 + 90 = 350; fixed 30; tax 19 => 399
    calc = calculate_bill("water", "residential", 0, 30)
    assert float(calc["total_amount"]) == 399.00
    assert len(calc["breakdown"]) == 3


def test_reading_cannot_decrease():
    with pytest.raises(ValueError):
        calculate_bill("water", "residential", 50, 40)


# ---------- customers ----------

def test_customer_crud(client):
    c = make_customer(client)
    assert c["account_no"].startswith("ACC")

    assert client.post("/api/customers", json={"name": "x"}).status_code == 400
    dup = client.post(
        "/api/customers",
        json={"name": "B", "email": "TEST@example.com", "phone": "1", "address": "a"},
    )
    assert dup.status_code == 409

    res = client.patch(f"/api/customers/{c['id']}", json={"phone": "1112223333"})
    assert res.get_json()["phone"] == "1112223333"

    listing = client.get("/api/customers?q=Test").get_json()
    assert listing["total"] == 1

    assert client.delete(f"/api/customers/{c['id']}").status_code == 204
    assert client.get(f"/api/customers/{c['id']}").status_code == 404


# ---------- bills ----------

def test_bill_generation_uses_previous_reading(client):
    c = make_customer(client)
    first = client.post(
        "/api/bills",
        json={"customer_id": c["id"], "utility_type": "electricity", "current_reading": 1250, "previous_reading": 1000},
    ).get_json()
    assert first["total_amount"] == 1207.50
    assert first["bill_no"].startswith("EB")

    second = client.post(
        "/api/bills", json={"customer_id": c["id"], "utility_type": "electricity", "current_reading": 1300}
    ).get_json()
    assert second["previous_reading"] == 1250
    assert second["units_consumed"] == 50

    paid = client.post(f"/api/bills/{first['id']}/pay").get_json()
    assert paid["status"] == "paid"
    assert client.post(f"/api/bills/{first['id']}/pay").status_code == 400
    assert client.patch(f"/api/bills/{first['id']}", json={"current_reading": 2000}).status_code == 400

    customer = client.get(f"/api/customers/{c['id']}").get_json()
    assert customer["outstanding_amount"] == second["total_amount"]


def test_overdue_bill_gets_late_fee(client):
    c = make_customer(client)
    past = (date.today() - timedelta(days=40)).isoformat()
    bill = client.post(
        "/api/bills",
        json={
            "customer_id": c["id"], "utility_type": "water", "current_reading": 30,
            "previous_reading": 0, "issue_date": past,
        },
    ).get_json()
    assert bill["status"] == "unpaid"

    refreshed = client.get(f"/api/bills/{bill['id']}")
    listing = client.get("/api/bills?status=overdue").get_json()
    assert listing["total"] == 1
    overdue = listing["items"][0]
    assert overdue["late_fee"] == 25.00  # 2% of 399 < minimum 25
    assert overdue["total_amount"] == 424.00
    # Late fee applied only once.
    client.get("/api/bills")
    assert client.get(f"/api/bills/{bill['id']}").get_json()["total_amount"] == 424.00
    assert refreshed.status_code == 200


def test_bill_validation(client):
    c = make_customer(client)
    bad = client.post(
        "/api/bills", json={"customer_id": c["id"], "utility_type": "gas", "current_reading": 10}
    )
    assert bad.status_code == 400
    lower = client.post(
        "/api/bills",
        json={"customer_id": c["id"], "utility_type": "water", "current_reading": 5, "previous_reading": 10},
    )
    assert lower.status_code == 400
    preview = client.post(
        "/api/bills/preview", json={"customer_id": c["id"], "utility_type": "water", "current_reading": 30}
    ).get_json()
    assert preview["total_amount"] == 399.00
    assert client.get("/api/bills").get_json()["total"] == 0  # preview doesn't save


# ---------- complaints ----------

def test_complaint_workflow(client):
    c = make_customer(client)
    comp = client.post(
        "/api/complaints",
        json={"customer_id": c["id"], "category": "water", "subject": "No water", "description": "Dry taps", "priority": "high"},
    ).get_json()
    assert comp["status"] == "open"
    assert comp["ticket_no"].startswith("TKT")
    assert len(comp["history"]) == 1

    upd = client.patch(
        f"/api/complaints/{comp['id']}",
        json={"status": "in_progress", "assigned_to": "Water Dept", "note": "Team dispatched"},
    ).get_json()
    assert upd["status"] == "in_progress"
    assert upd["assigned_to"] == "Water Dept"
    assert len(upd["history"]) == 2

    done = client.patch(f"/api/complaints/{comp['id']}", json={"status": "closed"}).get_json()
    assert done["resolved_at"] is not None

    reopen = client.patch(f"/api/complaints/{comp['id']}", json={"status": "open"})
    assert reopen.status_code == 400
    assert client.get("/api/complaints?status=closed").get_json()["total"] == 1


def test_dashboard_summary(client):
    c = make_customer(client)
    client.post("/api/bills", json={"customer_id": c["id"], "utility_type": "water", "current_reading": 30})
    client.post(
        "/api/complaints",
        json={"customer_id": c["id"], "category": "billing", "subject": "s", "description": "d"},
    )
    d = client.get("/api/dashboard/summary").get_json()
    assert d["customers"]["total"] == 1
    assert d["billing"]["total_billed"] == 399.00
    assert d["billing"]["outstanding"] == 399.00
    assert d["complaints"]["by_status"]["open"] == 1
    assert len(d["monthly"]) == 6


def test_index_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"UtilityDesk" in res.data
