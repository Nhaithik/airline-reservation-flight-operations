# Airline Reservation & Flight Operations Management System

Final Review 2 + Review 3 Flask + MySQL project.

## 1. Requirements

- Python 3.10+
- MySQL Server
- Existing database named `airline_reservation`
- VS Code

## 2. Setup

Open this folder in VS Code.

Create and activate a virtual environment:

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

Install packages:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and put your real MySQL password in `.env`.

Example:

```text
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=airline_reservation
FLASK_SECRET_KEY=airline-final-project
```

## 3. Start the backend

```bash
python app.py
```

Open:

http://127.0.0.1:5000

## 4. Modules

The same Flask application provides:

- Dashboard
- Flights
- Passengers
- Reservations
- Seats
- Tickets
- Check-In
- Baggage
- Payments
- Cancellations
- Reports

Every module reads the corresponding MySQL table.

The module screens also support generic Add/Edit/Delete operations based on the actual columns and primary key discovered from MySQL.

## 5. Important

Do not commit `.env` to GitHub.

The GitHub repository should contain `.env.example`, not the real `.env`.

## 6. GitHub

Example commands:

```bash
git init
git add .
git commit -m "Final airline reservation management system"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

The Flask backend requires a machine/server with access to MySQL. GitHub Pages alone cannot run this Flask backend or connect directly to your local MySQL server.

For the college demonstration, run the Flask backend in VS Code and show the website at `127.0.0.1:5000`.


## Review 3 Workflow Added

The project now includes a dedicated **Flight Search & Booking** workflow at `/booking`.

Flow:
1. Search live flights by source, destination and date.
2. Select a passenger from the existing `passengers` table.
3. Select a flight and enter a seat number.
4. The server validates the passenger, flight, available seats, duplicate passenger booking and duplicate active seat.
5. A `Pending` reservation is created and one seat is reserved atomically.
6. Payment confirmation will be the next Review 3 workflow step.

The existing database tables are reused; the application does not drop or recreate them.


## FINAL Review 2 + Review 3 Application

This final version includes the complete application workflow in one project folder:

**Flight Search & Booking → Seat Allocation → Payment → Ticket Issue → Check-In → Baggage → Cancellation/Refund → Reports**

### Workflow rules
- Booking validates passenger, flight, seat format, duplicate active passenger/flight booking and duplicate active seat.
- Payment confirms a pending reservation.
- Ticket issue requires a confirmed and paid reservation.
- Check-in requires an issued ticket.
- Baggage requires a confirmed reservation and completed check-in.
- Cancellation records a refund and releases inventory; existing database triggers are respected so seat inventory is not updated twice.
- Reports include route demand, revenue, occupancy and passenger manifest.
- Existing MySQL tables are reused. The application does not drop or recreate the database.

### Final run
```bash
source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

No additional application files are required after extracting this final project. Only the local `.env` must contain the correct MySQL password/settings.

## Changes in the fixed version
- Seat inventory no longer double-counts: trigger detection checks the right table/event, and `SEAT_INVENTORY_MODE` (auto/app/trigger) overrides it.
- Ticket and boarding-pass numbers retry on duplicate keys instead of failing.
- Occupancy report counts Pending + Confirmed seats.
- Payment only for Pending/Confirmed reservations; stricter validation.
- Cancelling is blocked after check-in; ticket is marked Cancelled.
- `POST /api/expire-pending` releases unpaid holds older than `PENDING_HOLD_DAYS`.
- Workflow tables are read-only in the generic module screens (set `ALLOW_WORKFLOW_TABLE_EDITS=1` to re-enable).
- Seat numbers limited to rows 1-30, A-F (matches the seat map).
- Edit form no longer overwrites required fields with NULL; update/delete return 404 for missing rows.
- Duplicate `__main__` block removed; debug is off unless `FLASK_DEBUG=1`.
- Frontend: duplicate helpers removed, safe flight-select button, safer JSON error handling.

## Added for the project brief
- Reports: baggage, cancellations & refunds, on-time status (needs `sql/schema_additions.sql` once).
- Refund rules: 90% if 72h+ before departure, 50% if 24-72h, 25% under 24h, 0% after departure (edit `REFUND_POLICY` in `app.py`).
- Seat allocation: click a seat on the booking page; change seats from the Operations page.
- Modules for airports, routes, aircraft and fares.
- `sql/queries_and_views.sql`: 6 views plus joins, aggregates, subqueries.
- `sql/schema_additions.sql`: on-time columns and indexes (optional).
- `TEST_PLAN.md` and `tests/` (run `python -m unittest discover -s tests -v`).
