# Smart Utility Billing and Complaint Management System

A web-based utility management system built with **Python, Flask, MySQL and REST APIs**. It manages
customer records, generates electricity and water bills automatically from meter readings, and tracks
service complaints from registration through to resolution, all from one admin dashboard.

## Features

- **Customer management**: create, search, edit, deactivate and delete customer accounts (residential or commercial). Each account gets an auto-generated account number.
- **Automated billing**: enter a meter reading and the bill is calculated using tiered (slab) tariffs per utility and connection type, plus a fixed charge and 5% tax. The previous reading is filled in automatically from the customer's last bill. A live preview shows the slab-by-slab breakdown before you save.
- **Payments and overdue handling**: mark bills paid. Unpaid bills past their due date are marked *overdue* automatically and get a one-time late fee (2%, minimum ₹25).
- **Complaint management**: customers' complaints get a ticket number, category and priority. Admins assign technicians, move tickets through `open → in_progress → resolved → closed` (with enforced transitions) and add notes. Every change is written to an audit history.
- **Dashboard**: KPIs (billed, collected, outstanding, open complaints, resolution rate, average resolution time), a 6-month billing vs. collection chart, complaints-by-status chart, recent complaints and overdue bills.

## Tech stack

| Layer     | Technology |
|-----------|-----------|
| Backend   | Flask 3 (blueprints, app factory) |
| ORM / DB  | Flask-SQLAlchemy + PyMySQL → MySQL 8 (SQLite fallback for local dev) |
| API       | JSON REST endpoints with validation and consistent error responses |
| Frontend  | HTML, CSS, vanilla JavaScript, Chart.js |
| Tests     | pytest (API and billing-engine tests) |

## Project structure

```
utility-billing/
├── app/
│   ├── __init__.py          # app factory, blueprint registration, error handler
│   ├── config.py            # DATABASE_URL / SECRET_KEY from .env
│   ├── extensions.py        # SQLAlchemy instance
│   ├── models.py            # Customer, Bill, Complaint, ComplaintUpdate
│   ├── services/billing.py  # tariff slabs + bill calculation engine
│   ├── routes/              # customers, bills, complaints, dashboard APIs
│   ├── templates/index.html # dashboard UI
│   └── static/              # app.js, style.css
├── tests/test_api.py
├── schema.sql               # MySQL DDL
├── seed.py                  # sample data
└── run.py
```

## Getting started

```bash
pip install -r requirements.txt
```

### Option A: MySQL (production setup)

1. Create the database and user (or run `schema.sql`):
   ```sql
   CREATE DATABASE utility_billing;
   CREATE USER 'utility_user'@'localhost' IDENTIFIED BY 'change_me';
   GRANT ALL PRIVILEGES ON utility_billing.* TO 'utility_user'@'localhost';
   ```
2. Copy `.env.example` to `.env` and set `DATABASE_URL`:
   ```
   DATABASE_URL=mysql+pymysql://utility_user:change_me@localhost:3306/utility_billing
   ```

### Option B: SQLite (zero setup)

Leave `DATABASE_URL` unset and the app uses `utility_billing.db` in the project folder.

### Run

```bash
python seed.py --reset   # optional: load sample customers, bills, complaints
python run.py            # http://localhost:5000
python -m pytest -q      # run tests
```

## REST API

All endpoints return JSON. List endpoints accept `page` and `per_page` and return
`{items, total, page, per_page, pages}`. Errors return `{error, message}` with a 4xx status.

### Customers
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/customers?q=&connection_type=&is_active=` | List / search customers |
| POST | `/api/customers` | Create (`name`, `email`, `phone`, `address`, `connection_type`) |
| GET | `/api/customers/<id>` | Details + outstanding amount, recent bills & complaints |
| PUT/PATCH | `/api/customers/<id>` | Update |
| DELETE | `/api/customers/<id>` | Delete (cascades bills & complaints) |
| GET | `/api/customers/<id>/bills` | Customer's bills |
| GET | `/api/customers/<id>/complaints` | Customer's complaints |

### Bills
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/bills?customer_id=&utility_type=&status=&q=` | List bills |
| POST | `/api/bills` | Generate (`customer_id`, `utility_type`, `current_reading`, optional `previous_reading`, `period_start`, `period_end`, `issue_date`, `due_date`) |
| POST | `/api/bills/preview` | Calculate without saving |
| GET | `/api/bills/<id>` | Bill + slab breakdown |
| PUT/PATCH | `/api/bills/<id>` | Correct readings/dates on an unpaid bill (recalculates) |
| POST | `/api/bills/<id>/pay` | Record payment |
| DELETE | `/api/bills/<id>` | Delete |
| GET | `/api/bills/tariffs` | Current tariff table |

### Complaints
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/complaints?status=&priority=&category=&customer_id=&q=` | List complaints |
| POST | `/api/complaints` | Register (`customer_id`, `category`, `subject`, `description`, `priority`) |
| GET | `/api/complaints/<id>` | Details + status history |
| PUT/PATCH | `/api/complaints/<id>` | Admin update (`status`, `priority`, `assigned_to`, `note`, `updated_by`) |
| DELETE | `/api/complaints/<id>` | Delete |

### Dashboard
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/dashboard/summary` | KPIs, monthly billing series, complaint stats |

### Example

```bash
curl -X POST http://localhost:5000/api/bills \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "utility_type": "electricity", "current_reading": 1250, "previous_reading": 1000}'
```

## Tariffs (configurable in `app/services/billing.py`)

| Utility | Connection | Slabs (₹/unit) | Fixed |
|---|---|---|---|
| Electricity (kWh) | Residential | 0–100: 3.50 · 101–300: 5.00 · 301–500: 6.50 · 500+: 8.00 | ₹50 |
| Electricity (kWh) | Commercial | 0–200: 7.00 · 201–1000: 8.50 · 1000+: 10.00 | ₹150 |
| Water (kL) | Residential | 0–10: 8 · 11–25: 12 · 25+: 18 | ₹30 |
| Water (kL) | Commercial | 0–50: 20 · 50+: 28 | ₹100 |

Tax: 5% on (consumption + fixed). Late fee: 2% of total (min ₹25), applied once when a bill becomes overdue.
