import os
import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request
import mysql.connector
from mysql.connector import Error

load_dotenv()

app = Flask(__name__)
app.json.sort_keys = False
app.secret_key = os.getenv("FLASK_SECRET_KEY", "airline-final-project")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "airline_reservation"),
}

# How flight seat inventory (flights.available_seats) is maintained:
#   auto    - detect existing DB triggers on the relevant table/event (default)
#   app     - the Flask app always updates the count (use if you have NO triggers)
#   trigger - the database always updates the count (the app never touches it)
SEAT_MODE = os.getenv("SEAT_INVENTORY_MODE", "auto").strip().lower()

# Reservations that stay Pending longer than this many days can be released.
PENDING_HOLD_DAYS = int(os.getenv("PENDING_HOLD_DAYS", "1"))

# Only these tables can be accessed through the generic module API.
ALLOWED_TABLES = {
    "aircraft", "airports", "baggage", "cancellations", "check_ins",
    "fares", "flights", "passengers", "payments", "reservation_details",
    "reservations", "routes", "seats", "tickets",
}

# Tables that are changed by the booking workflow. The generic Add/Edit/Delete
# API is read-only for them by default, because editing them directly bypasses
# the workflow rules and can corrupt seat counts / payments.
# Set ALLOW_WORKFLOW_TABLE_EDITS=1 in .env to enable raw editing (demo only).
WORKFLOW_TABLES = {
    "reservations", "payments", "tickets", "check_ins", "baggage",
    "cancellations", "reservation_details",
}
ALLOW_WORKFLOW_EDITS = os.getenv("ALLOW_WORKFLOW_TABLE_EDITS", "0").strip() == "1"

MODULES = {
    "flights": "flights",
    "passengers": "passengers",
    "reservations": "reservations",
    "seats": "seats",
    "tickets": "tickets",
    "check-in": "check_ins",
    "baggage": "baggage",
    "payments": "payments",
    "cancellations": "cancellations",
    "airports": "airports",
    "routes": "routes",
    "aircraft": "aircraft",
    "fares": "fares",
}

# Refund policy: (minimum hours before departure, percent of the paid amount).
# Checked from top to bottom; a flight that has already departed refunds 0%.
REFUND_POLICY = [(72, 90), (24, 50), (0, 25)]

SEAT_PATTERN = re.compile(r"([1-9]|[12][0-9]|30)[A-F]")  # rows 1-30, seats A-F
PAYMENT_METHODS = {"UPI", "Credit Card", "Debit Card", "Cash"}


class WorkflowError(Exception):
    """A business-rule failure that maps to an HTTP error response."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def json_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return value


def serializable_rows(rows):
    return [{k: json_value(v) for k, v in row.items()} for row in rows]


def execute_query(sql, params=(), fetch=True):
    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        if fetch:
            return cursor.fetchall()
        conn.commit()
        return {"affected_rows": cursor.rowcount, "lastrowid": cursor.lastrowid}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


_trigger_cache = {}


def db_trigger_updates_seats(table, event):
    """
    True when an existing DB trigger on `table` for `event` (INSERT/UPDATE/
    DELETE) already changes flights.available_seats, so the app must not
    change it a second time. Honors SEAT_INVENTORY_MODE. Only successful
    lookups are cached.
    """
    if SEAT_MODE == "app":
        return False
    if SEAT_MODE == "trigger":
        return True

    key = (table, event)
    if key in _trigger_cache:
        return _trigger_cache[key]

    conn = cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT ACTION_STATEMENT
            FROM INFORMATION_SCHEMA.TRIGGERS
            WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE=%s
              AND EVENT_MANIPULATION=%s
        """, (DB_CONFIG["database"], table, event))
        pattern = re.compile(
            r"update\s+`?flights`?\b.{0,300}?available_seats\s*=", re.S | re.I
        )
        found = any(pattern.search(str(r["ACTION_STATEMENT"] or "")) for r in cur.fetchall())
        _trigger_cache[key] = found
        return found
    except Error:
        return False  # lookup failed: do not cache, assume the app owns it
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


_columns_cache = {}


def safe_table(table):
    return table in ALLOWED_TABLES


def is_read_only(table):
    return table in WORKFLOW_TABLES and not ALLOW_WORKFLOW_EDITS


def table_columns(table):
    if not safe_table(table):
        return []
    if table in _columns_cache:
        return _columns_cache[table]
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY,
                   COLUMN_DEFAULT, EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            ORDER BY ORDINAL_POSITION
        """, (DB_CONFIG["database"], table))
        cols = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    # Normalise key case: some MySQL versions return upper/lower case keys.
    cols = [{k.upper(): v for k, v in c.items()} for c in cols]
    _columns_cache[table] = cols
    return cols


def primary_key(table):
    for c in table_columns(table):
        if c["COLUMN_KEY"] == "PRI":
            return c["COLUMN_NAME"]
    return None


def next_number(cur, table, id_col):
    cur.execute(f"SELECT COALESCE(MAX(`{id_col}`),0)+1 AS n FROM `{table}`")
    return int(cur.fetchone()["n"])


def insert_with_number(cur, table, id_col, prefix, insert_sql, params_fn):
    """
    Insert a row that carries a human-readable unique number (TKT001, BP001).
    If the number collides (duplicate key, e.g. two simultaneous requests),
    the next number is tried instead of failing.
    """
    n = next_number(cur, table, id_col)
    for _ in range(10):
        number = f"{prefix}{n:03d}"
        try:
            cur.execute(insert_sql, params_fn(number))
            return cur.lastrowid, number
        except Error as e:
            if e.errno != 1062:
                raise
            n += 1
    raise WorkflowError("Could not allocate a unique number. Please try again.", 503)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/module/<module>")
def module_page(module):
    if module not in MODULES:
        abort(404)
    return render_template("module.html", module=module, table=MODULES[module])


@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.get("/booking")
def booking_page():
    return render_template("booking.html")


@app.route("/operations")
def operations_page():
    return render_template("operations.html")


# ---------------------------------------------------------------------------
# Health + dashboard
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    try:
        conn = get_db()
        conn.close()
        return jsonify({"database": DB_CONFIG["database"], "status": "OK"})
    except Error as e:
        return jsonify({"database": "Disconnected", "status": "ERROR", "message": str(e)}), 500


@app.get("/api/dashboard")
def dashboard_stats():
    queries = {
        "flights": "SELECT COUNT(*) AS value FROM flights",
        "passengers": "SELECT COUNT(*) AS value FROM passengers",
        "reservations": "SELECT COUNT(*) AS value FROM reservations",
        "available_seats": "SELECT COALESCE(SUM(available_seats),0) AS value FROM flights",
        "revenue": "SELECT COALESCE(SUM(payment_amount),0) AS value FROM payments WHERE payment_status='Paid'",
        "cancellations": "SELECT COUNT(*) AS value FROM cancellations",
    }
    conn = cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        stats = {}
        for key, sql in queries.items():
            try:
                cur.execute(sql)
                stats[key] = json_value(cur.fetchone()["value"])
            except Error:
                stats[key] = 0
        return jsonify(stats)
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Generic module API
# ---------------------------------------------------------------------------

READ_ONLY_MESSAGE = (
    "This table is changed through the booking workflow (Operations Center). "
    "Direct editing is disabled."
)


@app.get("/api/table/<table>")
def get_table(table):
    if not safe_table(table):
        return jsonify({"error": "Table not allowed"}), 404

    try:
        cols = table_columns(table)
        pk = primary_key(table)
        search = request.args.get("search", "").strip()
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)

        sql = f"SELECT * FROM `{table}`"
        params = []

        if search and cols:
            conditions = []
            for c in cols:
                conditions.append(f"CAST(`{c['COLUMN_NAME']}` AS CHAR) LIKE %s")
                params.append(f"%{search}%")
            sql += " WHERE " + " OR ".join(conditions)

        if pk:
            sql += f" ORDER BY `{pk}` DESC"
        sql += " LIMIT %s"
        params.append(limit)

        rows = serializable_rows(execute_query(sql, tuple(params)))
        return jsonify({
            "table": table,
            "primary_key": pk,
            "read_only": is_read_only(table),
            "columns": cols,
            "rows": rows,
        })
    except (Error, ValueError) as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/table/<table>/meta")
def table_meta(table):
    if not safe_table(table):
        return jsonify({"error": "Table not allowed"}), 404
    try:
        return jsonify({
            "table": table,
            "primary_key": primary_key(table),
            "read_only": is_read_only(table),
            "columns": table_columns(table),
        })
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/table/<table>")
def insert_table(table):
    if not safe_table(table):
        return jsonify({"error": "Table not allowed"}), 404
    if is_read_only(table):
        return jsonify({"error": READ_ONLY_MESSAGE}), 403

    data = request.get_json(silent=True) or {}
    allowed = {c["COLUMN_NAME"] for c in table_columns(table)}
    clean = {k: v for k, v in data.items() if k in allowed and v not in ("", None)}

    if not clean:
        return jsonify({"error": "No values supplied"}), 400

    names = ", ".join(f"`{k}`" for k in clean)
    marks = ", ".join(["%s"] * len(clean))
    sql = f"INSERT INTO `{table}` ({names}) VALUES ({marks})"

    try:
        result = execute_query(sql, tuple(clean.values()), fetch=False)
        return jsonify({"message": "Record added", **result}), 201
    except Error as e:
        return jsonify({"error": str(e)}), 400


@app.put("/api/table/<table>/<pk_value>")
def update_table(table, pk_value):
    if not safe_table(table):
        return jsonify({"error": "Table not allowed"}), 404
    if is_read_only(table):
        return jsonify({"error": READ_ONLY_MESSAGE}), 403
    pk = primary_key(table)
    if not pk:
        return jsonify({"error": "No primary key found"}), 400

    data = request.get_json(silent=True) or {}
    allowed = {c["COLUMN_NAME"] for c in table_columns(table)}
    clean = {k: v for k, v in data.items() if k in allowed and k != pk}

    if not clean:
        return jsonify({"error": "No editable values supplied"}), 400

    assignments = ", ".join(f"`{k}`=%s" for k in clean)
    sql = f"UPDATE `{table}` SET {assignments} WHERE `{pk}`=%s"

    try:
        exists = execute_query(f"SELECT 1 AS x FROM `{table}` WHERE `{pk}`=%s", (pk_value,))
        if not exists:
            return jsonify({"error": "Record not found"}), 404
        result = execute_query(sql, tuple(clean.values()) + (pk_value,), fetch=False)
        return jsonify({"message": "Record updated", **result})
    except Error as e:
        return jsonify({"error": str(e)}), 400


@app.delete("/api/table/<table>/<pk_value>")
def delete_table(table, pk_value):
    if not safe_table(table):
        return jsonify({"error": "Table not allowed"}), 404
    if is_read_only(table):
        return jsonify({"error": READ_ONLY_MESSAGE}), 403
    pk = primary_key(table)
    if not pk:
        return jsonify({"error": "No primary key found"}), 400

    try:
        result = execute_query(
            f"DELETE FROM `{table}` WHERE `{pk}`=%s", (pk_value,), fetch=False
        )
        if result["affected_rows"] == 0:
            return jsonify({"error": "Record not found"}), 404
        return jsonify({"message": "Record deleted", **result})
    except Error as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# Flight search + booking
# ---------------------------------------------------------------------------

@app.get("/api/flight-options")
def flight_options():
    """Return distinct source/destination values for the booking form."""
    try:
        sources = execute_query(
            "SELECT DISTINCT source FROM flights WHERE source IS NOT NULL ORDER BY source"
        )
        destinations = execute_query(
            "SELECT DISTINCT destination FROM flights WHERE destination IS NOT NULL ORDER BY destination"
        )
        return jsonify({
            "sources": [r["source"] for r in sources],
            "destinations": [r["destination"] for r in destinations],
        })
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/search-flights")
def search_flights():
    """Search live flights using source, destination and departure date."""
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()
    travel_date = request.args.get("date", "").strip()

    conditions = []
    params = []

    if source:
        conditions.append("f.source = %s")
        params.append(source)
    if destination:
        conditions.append("f.destination = %s")
        params.append(destination)
    if travel_date:
        try:
            datetime.strptime(travel_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Date must be in YYYY-MM-DD format"}), 400
        conditions.append("DATE(f.departure_time) = %s")
        params.append(travel_date)

    sql = """
        SELECT f.flight_id, f.flight_number, f.airline, f.source, f.destination,
               f.departure_time, f.arrival_time, f.available_seats
        FROM flights f
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY f.departure_time ASC"

    try:
        return jsonify(serializable_rows(execute_query(sql, tuple(params))))
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/booking-passengers")
def booking_passengers():
    try:
        rows = execute_query("""
            SELECT passenger_id, first_name, last_name, phone, email
            FROM passengers
            ORDER BY passenger_id DESC
        """)
        return jsonify(serializable_rows(rows))
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/book")
def create_booking():
    """Create a Pending reservation and reserve one seat atomically."""
    data = request.get_json(silent=True) or {}

    try:
        passenger_id = int(data.get("passenger_id"))
        flight_id = int(data.get("flight_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Passenger and flight are required"}), 400

    seat_number = str(data.get("seat_number", "")).strip().upper()
    if not SEAT_PATTERN.fullmatch(seat_number):
        return jsonify({
            "error": "Invalid seat number. Use rows 1-30 and seats A-F, e.g. 12A."
        }), 400

    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        # Lock the flight row so simultaneous bookings cannot take the same seat count.
        cur.execute("""
            SELECT flight_id, flight_number, airline, source, destination,
                   departure_time, arrival_time, available_seats
            FROM flights
            WHERE flight_id = %s
            FOR UPDATE
        """, (flight_id,))
        flight = cur.fetchone()
        if not flight:
            raise WorkflowError("Selected flight does not exist", 404)

        cur.execute(
            "SELECT passenger_id, first_name, last_name FROM passengers WHERE passenger_id=%s",
            (passenger_id,),
        )
        passenger = cur.fetchone()
        if not passenger:
            raise WorkflowError("Selected passenger does not exist", 404)

        if int(flight["available_seats"]) <= 0:
            raise WorkflowError("No seats are available on this flight", 400)

        cur.execute("""
            SELECT reservation_id FROM reservations
            WHERE flight_id=%s AND UPPER(seat_number)=%s
              AND reservation_status IN ('Pending','Confirmed')
            LIMIT 1
        """, (flight_id, seat_number))
        if cur.fetchone():
            raise WorkflowError(f"Seat {seat_number} is already reserved on this flight", 409)

        cur.execute("""
            SELECT reservation_id FROM reservations
            WHERE passenger_id=%s AND flight_id=%s
              AND reservation_status IN ('Pending','Confirmed')
            LIMIT 1
        """, (passenger_id, flight_id))
        if cur.fetchone():
            raise WorkflowError("This passenger already has an active reservation for this flight", 409)

        cur.execute("""
            INSERT INTO reservations
                (passenger_id, flight_id, booking_date, seat_number, reservation_status)
            VALUES (%s, %s, CURDATE(), %s, 'Pending')
        """, (passenger_id, flight_id, seat_number))
        reservation_id = cur.lastrowid

        # Reserve one seat unless a DB trigger on reservations INSERT already does.
        if not db_trigger_updates_seats("reservations", "INSERT"):
            cur.execute("""
                UPDATE flights SET available_seats = available_seats - 1
                WHERE flight_id=%s AND available_seats > 0
            """, (flight_id,))
            if cur.rowcount != 1:
                raise WorkflowError("Unable to reserve the selected seat", 409)

        conn.commit()
        return jsonify({
            "message": "Booking created successfully",
            "reservation_id": reservation_id,
            "reservation_status": "Pending",
            "passenger_name": f"{passenger['first_name']} {passenger['last_name']}",
            "flight_number": flight["flight_number"],
            "route": f"{flight['source']} → {flight['destination']}",
            "seat_number": seat_number,
            "next_step": "Complete payment to confirm the reservation.",
        }), 201

    except WorkflowError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": e.message}), e.status
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Operations workflow: seat map, payment, ticket, check-in, baggage, cancel
# ---------------------------------------------------------------------------

@app.get("/api/reservation-options")
def reservation_options():
    try:
        rows = execute_query("""
            SELECT r.reservation_id, r.passenger_id, r.flight_id, r.seat_number,
                   r.reservation_status,
                   CONCAT(p.first_name,' ',p.last_name) AS passenger_name,
                   f.flight_number, f.source, f.destination
            FROM reservations r
            JOIN passengers p ON p.passenger_id=r.passenger_id
            JOIN flights f ON f.flight_id=r.flight_id
            WHERE r.reservation_status IN ('Pending','Confirmed')
            ORDER BY r.reservation_id DESC
        """)
        return jsonify(serializable_rows(rows))
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/seat-map/<int:flight_id>")
def seat_map(flight_id):
    try:
        flights = execute_query(
            "SELECT flight_id, flight_number, available_seats FROM flights WHERE flight_id=%s",
            (flight_id,),
        )
        if not flights:
            return jsonify({"error": "Flight not found"}), 404
        rows = execute_query("""
            SELECT seat_number FROM reservations
            WHERE flight_id=%s AND reservation_status IN ('Pending','Confirmed')
        """, (flight_id,))
        occupied = {str(r["seat_number"]).upper() for r in rows if r.get("seat_number")}
        seats = []
        for row in range(1, 31):
            for letter in "ABCDEF":
                code = f"{row}{letter}"
                seats.append({"seat_number": code, "occupied": code in occupied})
        return jsonify({"flight": serializable_rows(flights)[0], "seats": seats})
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/reservation/<int:reservation_id>")
def reservation_detail(reservation_id):
    try:
        rows = execute_query("""
            SELECT r.*, CONCAT(p.first_name,' ',p.last_name) AS passenger_name,
                   p.phone, p.email, f.flight_number, f.airline, f.source,
                   f.destination, f.departure_time, f.arrival_time
            FROM reservations r
            JOIN passengers p ON p.passenger_id=r.passenger_id
            JOIN flights f ON f.flight_id=r.flight_id
            WHERE r.reservation_id=%s
        """, (reservation_id,))
        if not rows:
            return jsonify({"error": "Reservation not found"}), 404
        return jsonify(serializable_rows(rows)[0])
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/payment")
def make_payment():
    data = request.get_json(silent=True) or {}
    try:
        rid = int(data.get("reservation_id"))
        amount = Decimal(str(data.get("amount")))
        if not amount.is_finite():
            raise InvalidOperation
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"error": "Reservation and valid payment amount are required"}), 400

    method = str(data.get("method", "")).strip()
    reference = str(data.get("reference", "")).strip()

    if amount <= 0:
        return jsonify({"error": "Payment amount must be greater than zero"}), 400
    if amount >= Decimal("100000000"):
        return jsonify({"error": "Payment amount is too large"}), 400
    if method not in PAYMENT_METHODS:
        return jsonify({"error": "Choose a valid payment method"}), 400
    if not reference or len(reference) > 50:
        return jsonify({"error": "Transaction reference is required (max 50 characters)"}), 400

    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT reservation_id, reservation_status
            FROM reservations WHERE reservation_id=%s FOR UPDATE
        """, (rid,))
        reservation = cur.fetchone()
        if not reservation:
            raise WorkflowError("Reservation not found", 404)
        if reservation["reservation_status"] not in ("Pending", "Confirmed"):
            raise WorkflowError(
                f"A {reservation['reservation_status']} reservation cannot be paid", 400
            )

        cur.execute("""
            SELECT payment_id FROM payments
            WHERE reservation_id=%s AND payment_status='Paid'
            LIMIT 1 FOR UPDATE
        """, (rid,))
        if cur.fetchone():
            raise WorkflowError("Reservation is already paid", 409)

        cur.execute("""
            INSERT INTO payments
                (reservation_id, payment_amount, payment_date, payment_method,
                 payment_status, transaction_reference)
            VALUES (%s, %s, NOW(), %s, 'Paid', %s)
        """, (rid, amount, method, reference))
        payment_id = cur.lastrowid

        cur.execute(
            "UPDATE reservations SET reservation_status='Confirmed' WHERE reservation_id=%s",
            (rid,),
        )
        conn.commit()
        return jsonify({
            "message": "Payment successful",
            "payment_id": payment_id,
            "reservation_id": rid,
            "status": "Confirmed",
        }), 201

    except WorkflowError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": e.message}), e.status
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.post("/api/ticket")
def issue_ticket():
    data = request.get_json(silent=True) or {}
    try:
        rid = int(data.get("reservation_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Reservation is required"}), 400

    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT reservation_id, reservation_status
            FROM reservations WHERE reservation_id=%s FOR UPDATE
        """, (rid,))
        r = cur.fetchone()
        if not r:
            raise WorkflowError("Reservation not found", 404)
        if r["reservation_status"] != "Confirmed":
            raise WorkflowError("Only confirmed reservations can receive tickets", 400)

        cur.execute(
            "SELECT ticket_id, ticket_number, ticket_status FROM tickets "
            "WHERE reservation_id=%s LIMIT 1 FOR UPDATE", (rid,),
        )
        existing = cur.fetchone()
        if existing:
            conn.commit()
            return jsonify({"message": "Ticket already exists", **existing})

        cur.execute(
            "SELECT payment_id FROM payments "
            "WHERE reservation_id=%s AND payment_status='Paid' LIMIT 1", (rid,),
        )
        if not cur.fetchone():
            raise WorkflowError("Complete payment before ticket issue", 400)

        ticket_id, ticket_number = insert_with_number(
            cur, "tickets", "ticket_id", "TKT",
            "INSERT INTO tickets (reservation_id, ticket_number, issue_date, ticket_status) "
            "VALUES (%s, %s, NOW(), 'Issued')",
            lambda number: (rid, number),
        )
        conn.commit()
        return jsonify({
            "message": "Ticket issued",
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "reservation_id": rid,
        }), 201

    except WorkflowError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": e.message}), e.status
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.post("/api/checkin")
def checkin():
    data = request.get_json(silent=True) or {}
    try:
        rid = int(data.get("reservation_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Reservation is required"}), 400

    gate = str(data.get("gate", "")).strip().upper()
    if not re.fullmatch(r"[A-Z][0-9]{1,3}", gate):
        return jsonify({"error": "Gate must look like A1 or B12"}), 400

    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT r.reservation_id, r.reservation_status, t.ticket_status
            FROM reservations r
            LEFT JOIN tickets t ON t.reservation_id=r.reservation_id
            WHERE r.reservation_id=%s
            FOR UPDATE
        """, (rid,))
        r = cur.fetchone()
        if not r:
            raise WorkflowError("Reservation not found", 404)
        if r["reservation_status"] != "Confirmed":
            raise WorkflowError("Only confirmed reservations can check in", 400)
        if r["ticket_status"] != "Issued":
            raise WorkflowError("Issue the ticket before check-in", 400)

        cur.execute(
            "SELECT checkin_id, boarding_pass_number, gate_number FROM check_ins "
            "WHERE reservation_id=%s LIMIT 1 FOR UPDATE", (rid,),
        )
        existing = cur.fetchone()
        if existing:
            conn.commit()
            return jsonify({"message": "Already checked in", **existing})

        checkin_id, boarding_pass = insert_with_number(
            cur, "check_ins", "checkin_id", "BP",
            "INSERT INTO check_ins "
            "(reservation_id, checkin_time, boarding_pass_number, gate_number, boarding_status) "
            "VALUES (%s, NOW(), %s, %s, 'Checked-In')",
            lambda number: (rid, number, gate),
        )
        conn.commit()
        return jsonify({
            "message": "Check-in successful",
            "checkin_id": checkin_id,
            "boarding_pass_number": boarding_pass,
            "gate_number": gate,
        }), 201

    except WorkflowError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": e.message}), e.status
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.post("/api/baggage")
def add_baggage():
    data = request.get_json(silent=True) or {}
    try:
        rid = int(data.get("reservation_id"))
        weight = Decimal(str(data.get("weight")))
        if not weight.is_finite():
            raise InvalidOperation
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"error": "Reservation and valid baggage weight are required"}), 400

    if weight <= 0 or weight > 100:
        return jsonify({"error": "Baggage weight must be between 0 and 100 kg"}), 400

    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT r.reservation_id
            FROM reservations r
            JOIN check_ins c ON c.reservation_id=r.reservation_id
            WHERE r.reservation_id=%s AND r.reservation_status='Confirmed'
            LIMIT 1 FOR UPDATE
        """, (rid,))
        if not cur.fetchone():
            raise WorkflowError(
                "Passenger must have a confirmed reservation and completed check-in", 400
            )

        cur.execute("""
            INSERT INTO baggage (reservation_id, baggage_weight, baggage_status)
            VALUES (%s, %s, 'Checked-In')
        """, (rid, weight))
        baggage_id = cur.lastrowid
        conn.commit()
        return jsonify({"message": "Baggage recorded", "baggage_id": baggage_id}), 201

    except WorkflowError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": e.message}), e.status
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def refund_percent(departure_time, now=None):
    """Refund percentage for a cancellation made `now`, based on REFUND_POLICY."""
    if not isinstance(departure_time, datetime):
        return 0
    now = now or datetime.now()
    hours = (departure_time - now).total_seconds() / 3600
    for min_hours, percent in REFUND_POLICY:
        if hours >= min_hours:
            return percent
    return 0


def compute_refund(paid, departure_time, now=None):
    percent = refund_percent(departure_time, now)
    amount = (Decimal(str(paid)) * percent / 100).quantize(Decimal("0.01"))
    return percent, amount


@app.get("/api/refund-policy")
def refund_policy():
    rules = [{"min_hours": h, "percent": p} for h, p in REFUND_POLICY]
    return jsonify({"rules": rules, "after_departure_percent": 0})


@app.get("/api/refund-preview/<int:reservation_id>")
def refund_preview(reservation_id):
    try:
        rows = execute_query("""
            SELECT r.reservation_status, f.departure_time,
                   COALESCE((SELECT SUM(p.payment_amount) FROM payments p
                             WHERE p.reservation_id=r.reservation_id
                               AND p.payment_status='Paid'), 0) AS paid
            FROM reservations r JOIN flights f ON f.flight_id=r.flight_id
            WHERE r.reservation_id=%s
        """, (reservation_id,))
        if not rows:
            return jsonify({"error": "Reservation not found"}), 404
        r = rows[0]
        percent, amount = compute_refund(r["paid"], r["departure_time"])
        return jsonify({
            "paid_amount": float(r["paid"]),
            "refund_percent": percent,
            "refund_amount": float(amount),
            "departure_time": json_value(r["departure_time"]),
        })
    except Error as e:
        return jsonify({"error": str(e)}), 500


def cancel_reservation_tx(cur, rid, reason):
    """
    Cancel one reservation inside the caller's open transaction: record the
    cancellation + refund, mark the reservation Cancelled, cancel its ticket
    and release the seat (unless a DB trigger already does).
    Raises WorkflowError for business-rule failures.
    """
    cur.execute("""
        SELECT r.reservation_id, r.reservation_status, r.flight_id,
               COALESCE((
                 SELECT SUM(p.payment_amount) FROM payments p
                 WHERE p.reservation_id=r.reservation_id AND p.payment_status='Paid'
               ), 0) AS paid
        FROM reservations r
        WHERE r.reservation_id=%s
        FOR UPDATE
    """, (rid,))
    r = cur.fetchone()
    if not r:
        raise WorkflowError("Reservation not found", 404)
    if r["reservation_status"] == "Cancelled":
        raise WorkflowError("Reservation is already cancelled", 409)

    cur.execute("SELECT checkin_id FROM check_ins WHERE reservation_id=%s LIMIT 1", (rid,))
    if cur.fetchone():
        raise WorkflowError("A checked-in reservation cannot be cancelled", 400)

    cur.execute("SELECT departure_time FROM flights WHERE flight_id=%s", (r["flight_id"],))
    flight = cur.fetchone()
    percent, refund = compute_refund(r["paid"], flight["departure_time"] if flight else None)
    cur.execute("""
        INSERT INTO cancellations
            (reservation_id, cancellation_date, cancellation_reason, refund_amount)
        VALUES (%s, NOW(), %s, %s)
    """, (rid, reason, refund))
    cancellation_id = cur.lastrowid

    cur.execute(
        "UPDATE reservations SET reservation_status='Cancelled' WHERE reservation_id=%s",
        (rid,),
    )

    # Keep the ticket consistent. If the ticket_status column does not accept
    # 'Cancelled', that single statement is skipped and the cancellation stands.
    try:
        cur.execute(
            "UPDATE tickets SET ticket_status='Cancelled' WHERE reservation_id=%s", (rid,)
        )
    except Error:
        pass

    # Release the seat unless a trigger on reservations UPDATE or
    # cancellations INSERT already does it.
    if not (db_trigger_updates_seats("reservations", "UPDATE")
            or db_trigger_updates_seats("cancellations", "INSERT")):
        cur.execute(
            "UPDATE flights SET available_seats = available_seats + 1 WHERE flight_id=%s",
            (r["flight_id"],),
        )

    return cancellation_id, refund, percent, Decimal(str(r["paid"]))


@app.post("/api/cancel")
def cancel_reservation():
    data = request.get_json(silent=True) or {}
    try:
        rid = int(data.get("reservation_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Reservation is required"}), 400

    reason = str(data.get("reason", "")).strip()
    if len(reason) < 3:
        return jsonify({"error": "Cancellation reason is required"}), 400

    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        cancellation_id, refund, percent, paid = cancel_reservation_tx(cur, rid, reason)
        conn.commit()
        return jsonify({
            "message": "Reservation cancelled",
            "cancellation_id": cancellation_id,
            "paid_amount": float(paid),
            "refund_percent": percent,
            "refund_amount": float(refund),
        }), 201

    except WorkflowError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": e.message}), e.status
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.post("/api/change-seat")
def change_seat():
    """Move an active reservation to another free seat on the same flight."""
    data = request.get_json(silent=True) or {}
    try:
        rid = int(data.get("reservation_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Reservation is required"}), 400
    new_seat = str(data.get("seat_number", "")).strip().upper()
    if not SEAT_PATTERN.fullmatch(new_seat):
        return jsonify({"error": "Invalid seat number. Use rows 1-30 and seats A-F."}), 400

    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        # Lock order matches booking: flight first, then reservation.
        cur.execute("SELECT flight_id FROM reservations WHERE reservation_id=%s", (rid,))
        first = cur.fetchone()
        if not first:
            raise WorkflowError("Reservation not found", 404)
        cur.execute("SELECT flight_id FROM flights WHERE flight_id=%s FOR UPDATE",
                    (first["flight_id"],))
        cur.execute("""
            SELECT reservation_id, flight_id, seat_number, reservation_status
            FROM reservations WHERE reservation_id=%s FOR UPDATE
        """, (rid,))
        r = cur.fetchone()
        if r["reservation_status"] not in ("Pending", "Confirmed"):
            raise WorkflowError("Only active reservations can change seats", 400)
        if str(r["seat_number"]).upper() == new_seat:
            raise WorkflowError(f"Reservation already has seat {new_seat}", 400)

        cur.execute("SELECT checkin_id FROM check_ins WHERE reservation_id=%s LIMIT 1", (rid,))
        if cur.fetchone():
            raise WorkflowError("Seat cannot be changed after check-in", 400)

        cur.execute("""
            SELECT reservation_id FROM reservations
            WHERE flight_id=%s AND UPPER(seat_number)=%s AND reservation_id<>%s
              AND reservation_status IN ('Pending','Confirmed') LIMIT 1
        """, (r["flight_id"], new_seat, rid))
        if cur.fetchone():
            raise WorkflowError(f"Seat {new_seat} is already reserved on this flight", 409)

        cur.execute("UPDATE reservations SET seat_number=%s WHERE reservation_id=%s",
                    (new_seat, rid))
        conn.commit()
        return jsonify({"message": f"Seat changed to {new_seat}",
                        "reservation_id": rid, "seat_number": new_seat})

    except WorkflowError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": e.message}), e.status
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.post("/api/expire-pending")
def expire_pending():
    """
    Release seats held by Pending reservations that were never paid and are
    older than PENDING_HOLD_DAYS. Call it from a scheduler, or manually
    (e.g. curl -X POST http://127.0.0.1:5000/api/expire-pending).
    """
    conn = cur = None
    try:
        conn = get_db()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT reservation_id FROM reservations
            WHERE reservation_status='Pending'
              AND booking_date < DATE_SUB(CURDATE(), INTERVAL %s DAY)
        """, (PENDING_HOLD_DAYS,))
        ids = [row["reservation_id"] for row in cur.fetchall()]

        released = []
        for rid in ids:
            try:
                cancel_reservation_tx(cur, rid, "Auto-cancelled: payment not received")
                released.append(rid)
            except WorkflowError:
                continue
        conn.commit()
        return jsonify({"message": f"{len(released)} pending reservation(s) released",
                        "released": released})
    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.get("/api/reports/route-demand")
def route_demand():
    sql = """
        SELECT f.source, f.destination, COUNT(*) AS total_reservations
        FROM reservations r
        JOIN flights f ON f.flight_id = r.flight_id
        GROUP BY f.source, f.destination
        ORDER BY total_reservations DESC
    """
    try:
        return jsonify(serializable_rows(execute_query(sql)))
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/reports/revenue")
def revenue_report():
    sql = """
        SELECT COUNT(*) AS total_paid_transactions,
               COALESCE(SUM(payment_amount),0) AS total_revenue,
               COALESCE(AVG(payment_amount),0) AS average_revenue
        FROM payments
        WHERE payment_status='Paid'
    """
    try:
        return jsonify(serializable_rows(execute_query(sql))[0])
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/reports/occupancy")
def occupancy_report():
    try:
        # Pending seats are already deducted from inventory, so they count as booked.
        rows = execute_query("""
            SELECT f.flight_number, f.source, f.destination, f.available_seats,
                   COUNT(CASE WHEN r.reservation_status IN ('Pending','Confirmed')
                              THEN 1 END) AS booked_seats
            FROM flights f
            LEFT JOIN reservations r ON r.flight_id=f.flight_id
            GROUP BY f.flight_id, f.flight_number, f.source, f.destination, f.available_seats
            ORDER BY f.flight_id
        """)
        return jsonify(serializable_rows(rows))
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/reports/manifest")
def manifest_report():
    try:
        rows = execute_query("""
            SELECT r.reservation_id, f.flight_number,
                   CONCAT(p.first_name,' ',p.last_name) AS passenger,
                   r.seat_number, r.reservation_status
            FROM reservations r
            JOIN passengers p ON p.passenger_id=r.passenger_id
            JOIN flights f ON f.flight_id=r.flight_id
            ORDER BY f.flight_id, r.seat_number
        """)
        return jsonify(serializable_rows(rows))
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/reports/baggage")
def baggage_report():
    try:
        rows = execute_query("""
            SELECT f.flight_number, f.source, f.destination,
                   COUNT(b.baggage_id) AS total_bags,
                   COALESCE(SUM(b.baggage_weight),0) AS total_weight,
                   COALESCE(AVG(b.baggage_weight),0) AS average_weight,
                   COALESCE(MAX(b.baggage_weight),0) AS heaviest_bag
            FROM flights f
            JOIN reservations r ON r.flight_id=f.flight_id
            JOIN baggage b ON b.reservation_id=r.reservation_id
            GROUP BY f.flight_id, f.flight_number, f.source, f.destination
            ORDER BY total_weight DESC
        """)
        return jsonify(serializable_rows(rows))
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/reports/cancellations")
def cancellation_report():
    try:
        rows = serializable_rows(execute_query("""
            SELECT c.cancellation_id, c.reservation_id,
                   CONCAT(p.first_name,' ',p.last_name) AS passenger,
                   f.flight_number, c.cancellation_date,
                   c.cancellation_reason, c.refund_amount
            FROM cancellations c
            JOIN reservations r ON r.reservation_id=c.reservation_id
            JOIN passengers p ON p.passenger_id=r.passenger_id
            JOIN flights f ON f.flight_id=r.flight_id
            ORDER BY c.cancellation_id DESC
        """))
        total_refund = sum(float(r["refund_amount"] or 0) for r in rows)
        return jsonify({
            "summary": {"total_cancellations": len(rows),
                        "total_refunded": round(total_refund, 2)},
            "rows": rows,
        })
    except Error as e:
        return jsonify({"error": str(e)}), 500


ON_TIME_GRACE_MINUTES = 15
ON_TIME_HINT = (
    "The flights table has no actual-departure or status column. Run "
    "schema_additions.sql (adds actual_departure_time and flight_status) "
    "and reload this page."
)


@app.get("/api/reports/on-time")
def on_time_report():
    """
    On-time status. Uses flights.actual_departure_time when present (delay vs
    schedule, on time = within 15 minutes); otherwise falls back to a
    flights.flight_status / status column; otherwise explains what to add.
    """
    try:
        names = {c["COLUMN_NAME"].lower(): c["COLUMN_NAME"] for c in table_columns("flights")}
        actual = next((names[n] for n in
                       ("actual_departure_time", "actual_departure") if n in names), None)
        status = next((names[n] for n in ("flight_status", "status") if n in names), None)

        if actual:
            rows = serializable_rows(execute_query(f"""
                SELECT flight_number, source, destination, departure_time,
                       `{actual}` AS actual_departure,
                       CASE WHEN `{actual}` IS NULL THEN NULL
                            ELSE TIMESTAMPDIFF(MINUTE, departure_time, `{actual}`) END AS delay_minutes,
                       CASE WHEN `{actual}` IS NULL THEN 'Not departed'
                            WHEN TIMESTAMPDIFF(MINUTE, departure_time, `{actual}`) <= {ON_TIME_GRACE_MINUTES}
                                 THEN 'On Time'
                            ELSE 'Delayed' END AS on_time_status
                FROM flights ORDER BY departure_time
            """))
            mode = "actual"
        elif status:
            rows = serializable_rows(execute_query(f"""
                SELECT flight_number, source, destination, departure_time,
                       `{status}` AS on_time_status
                FROM flights ORDER BY departure_time
            """))
            mode = "status"
        else:
            return jsonify({"mode": "unavailable", "hint": ON_TIME_HINT,
                            "summary": {}, "rows": []})

        summary = {}
        for r in rows:
            key = r["on_time_status"] or "Unknown"
            summary[key] = summary.get(key, 0) + 1
        return jsonify({"mode": mode, "summary": summary, "rows": rows})
    except Error as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Starting Airline Reservation & Flight Operations Management System")
    print(f"Database: {DB_CONFIG['database']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    debug = os.getenv("FLASK_DEBUG", "0").strip() == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)
