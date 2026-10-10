"""
Input-validation and business-rule unit tests.
They run WITHOUT a database: every case below is rejected before any SQL runs.

    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as airline  # noqa: E402


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = airline.app.test_client()

    def post(self, url, payload):
        return self.client.post(url, json=payload)

    # ---- pages -----------------------------------------------------------
    def test_pages_render(self):
        for url in ("/", "/booking", "/operations", "/reports",
                    "/module/flights", "/module/airports", "/module/routes",
                    "/module/aircraft", "/module/fares"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_unknown_module_404(self):
        self.assertEqual(self.client.get("/module/nothing").status_code, 404)

    # ---- generic API protection -----------------------------------------
    def test_table_not_whitelisted(self):
        self.assertEqual(self.client.get("/api/table/users").status_code, 404)
        self.assertEqual(self.post("/api/table/users", {"a": 1}).status_code, 404)

    def test_workflow_tables_read_only(self):
        for table in ("reservations", "payments", "tickets", "check_ins",
                      "baggage", "cancellations"):
            self.assertEqual(self.post(f"/api/table/{table}", {"x": 1}).status_code, 403, table)
            self.assertEqual(self.client.delete(f"/api/table/{table}/1").status_code, 403, table)

    # ---- search ----------------------------------------------------------
    def test_search_bad_date(self):
        self.assertEqual(self.client.get("/api/search-flights?date=13-09-2026").status_code, 400)

    # ---- booking ---------------------------------------------------------
    def test_book_requires_ids(self):
        self.assertEqual(self.post("/api/book", {"seat_number": "12A"}).status_code, 400)

    def test_book_rejects_bad_seats(self):
        for seat in ("", "99Z", "31A", "0A", "12G", "A12", "12", "1 2A"):
            r = self.post("/api/book", {"passenger_id": 1, "flight_id": 1, "seat_number": seat})
            self.assertEqual(r.status_code, 400, seat)

    def test_seat_pattern_accepts_valid(self):
        for seat in ("1A", "9F", "12C", "30F"):
            self.assertTrue(airline.SEAT_PATTERN.fullmatch(seat), seat)

    def test_change_seat_validation(self):
        self.assertEqual(self.post("/api/change-seat", {"reservation_id": 1, "seat_number": "40A"}).status_code, 400)
        self.assertEqual(self.post("/api/change-seat", {"seat_number": "1A"}).status_code, 400)

    # ---- payment ---------------------------------------------------------
    def test_payment_validation(self):
        good = {"reservation_id": 1, "amount": 5000, "method": "UPI", "reference": "TXN1"}
        bad_cases = [
            {**good, "amount": -5}, {**good, "amount": 0}, {**good, "amount": "abc"},
            {**good, "amount": "NaN"}, {**good, "method": "Bitcoin"},
            {**good, "reference": ""}, {**good, "reference": "x" * 51},
            {k: v for k, v in good.items() if k != "reservation_id"},
        ]
        for payload in bad_cases:
            self.assertEqual(self.post("/api/payment", payload).status_code, 400, payload)

    # ---- check-in / baggage / cancel ------------------------------------
    def test_checkin_gate_validation(self):
        for gate in ("", "12", "AA1", "A1234"):
            self.assertEqual(self.post("/api/checkin", {"reservation_id": 1, "gate": gate}).status_code, 400, gate)

    def test_baggage_weight_validation(self):
        for w in (-1, 0, 101, "heavy"):
            self.assertEqual(self.post("/api/baggage", {"reservation_id": 1, "weight": w}).status_code, 400, w)

    def test_cancel_requires_reason(self):
        self.assertEqual(self.post("/api/cancel", {"reservation_id": 1, "reason": "x"}).status_code, 400)
        self.assertEqual(self.post("/api/cancel", {"reason": "Change of plan"}).status_code, 400)


class RefundPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 8, 12, 0)

    def pct(self, hours):
        return airline.refund_percent(self.now + timedelta(hours=hours), self.now)

    def test_tiers(self):
        self.assertEqual(self.pct(100), 90)
        self.assertEqual(self.pct(72), 90)
        self.assertEqual(self.pct(48), 50)
        self.assertEqual(self.pct(24), 50)
        self.assertEqual(self.pct(5), 25)
        self.assertEqual(self.pct(0), 25)
        self.assertEqual(self.pct(-1), 0)

    def test_amount(self):
        _, amount = airline.compute_refund(5000, self.now + timedelta(hours=48), self.now)
        self.assertEqual(float(amount), 2500.00)
        self.assertEqual(airline.compute_refund(0, None, self.now)[1], 0)


if __name__ == "__main__":
    unittest.main()
