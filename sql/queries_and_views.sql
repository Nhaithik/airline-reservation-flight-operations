-- =====================================================================
-- Airline Reservation & Flight Operations - views and demonstration queries
-- Uses only columns the application already relies on.
-- Run with:  mysql -u root -p airline_reservation < sql/queries_and_views.sql
-- NOTE: CREATE OR REPLACE VIEW overwrites a view of the same name. The names
-- below start with v_report_ to avoid clashing with your existing views.
-- =====================================================================
USE airline_reservation;

-- ---------------------------- VIEWS ----------------------------------

-- Flight manifest (join of 3 tables)
CREATE OR REPLACE VIEW v_report_flight_manifest AS
SELECT f.flight_number, f.source, f.destination, f.departure_time,
       r.reservation_id, CONCAT(p.first_name,' ',p.last_name) AS passenger,
       r.seat_number, r.reservation_status
FROM reservations r
JOIN passengers p ON p.passenger_id = r.passenger_id
JOIN flights f    ON f.flight_id    = r.flight_id;

-- Occupancy per flight (aggregate + conditional count)
CREATE OR REPLACE VIEW v_report_occupancy AS
SELECT f.flight_id, f.flight_number, f.source, f.destination, f.available_seats,
       COUNT(CASE WHEN r.reservation_status IN ('Pending','Confirmed') THEN 1 END) AS booked_seats
FROM flights f
LEFT JOIN reservations r ON r.flight_id = f.flight_id
GROUP BY f.flight_id, f.flight_number, f.source, f.destination, f.available_seats;

-- Route demand
CREATE OR REPLACE VIEW v_report_route_demand AS
SELECT f.source, f.destination, COUNT(*) AS total_reservations
FROM reservations r JOIN flights f ON f.flight_id = r.flight_id
GROUP BY f.source, f.destination;

-- Baggage per flight
CREATE OR REPLACE VIEW v_report_baggage AS
SELECT f.flight_number, COUNT(b.baggage_id) AS total_bags,
       SUM(b.baggage_weight) AS total_weight, AVG(b.baggage_weight) AS avg_weight
FROM baggage b
JOIN reservations r ON r.reservation_id = b.reservation_id
JOIN flights f      ON f.flight_id      = r.flight_id
GROUP BY f.flight_id, f.flight_number;

-- Cancellations with refunds
CREATE OR REPLACE VIEW v_report_cancellations AS
SELECT c.cancellation_id, c.reservation_id, CONCAT(p.first_name,' ',p.last_name) AS passenger,
       f.flight_number, c.cancellation_date, c.cancellation_reason, c.refund_amount
FROM cancellations c
JOIN reservations r ON r.reservation_id = c.reservation_id
JOIN passengers p   ON p.passenger_id   = r.passenger_id
JOIN flights f      ON f.flight_id      = r.flight_id;

-- Revenue per flight
CREATE OR REPLACE VIEW v_report_revenue AS
SELECT f.flight_number, COUNT(pay.payment_id) AS paid_transactions,
       SUM(pay.payment_amount) AS revenue
FROM payments pay
JOIN reservations r ON r.reservation_id = pay.reservation_id
JOIN flights f      ON f.flight_id      = r.flight_id
WHERE pay.payment_status = 'Paid'
GROUP BY f.flight_id, f.flight_number;

-- ------------------------ DEMONSTRATION QUERIES -----------------------

-- Q1 JOIN: confirmed passengers with ticket numbers
SELECT r.reservation_id, CONCAT(p.first_name,' ',p.last_name) AS passenger,
       f.flight_number, r.seat_number, t.ticket_number
FROM reservations r
JOIN passengers p ON p.passenger_id = r.passenger_id
JOIN flights f    ON f.flight_id    = r.flight_id
LEFT JOIN tickets t ON t.reservation_id = r.reservation_id
WHERE r.reservation_status = 'Confirmed';

-- Q2 AGGREGATE + HAVING: routes with more than one reservation
SELECT source, destination, total_reservations
FROM v_report_route_demand
WHERE total_reservations > 1
ORDER BY total_reservations DESC;

-- Q3 SUBQUERY: flights busier than the average flight
SELECT flight_number, booked_seats
FROM v_report_occupancy
WHERE booked_seats > (SELECT AVG(booked_seats) FROM v_report_occupancy);

-- Q4 NESTED (NOT EXISTS): confirmed reservations that have not checked in
SELECT r.reservation_id, r.seat_number
FROM reservations r
WHERE r.reservation_status = 'Confirmed'
  AND NOT EXISTS (SELECT 1 FROM check_ins c WHERE c.reservation_id = r.reservation_id);

-- Q5 NESTED (IN): passengers who cancelled at least once
SELECT passenger_id, first_name, last_name
FROM passengers
WHERE passenger_id IN (
    SELECT r.passenger_id FROM reservations r
    JOIN cancellations c ON c.reservation_id = r.reservation_id);

-- Q6 AGGREGATE: total refunds vs total revenue
SELECT (SELECT COALESCE(SUM(payment_amount),0) FROM payments WHERE payment_status='Paid') AS revenue,
       (SELECT COALESCE(SUM(refund_amount),0)  FROM cancellations)                           AS refunded;

-- Q7 Heaviest baggage per flight (correlated subquery)
SELECT f.flight_number, b.baggage_id, b.baggage_weight
FROM baggage b
JOIN reservations r ON r.reservation_id = b.reservation_id
JOIN flights f      ON f.flight_id      = r.flight_id
WHERE b.baggage_weight = (
    SELECT MAX(b2.baggage_weight) FROM baggage b2
    JOIN reservations r2 ON r2.reservation_id = b2.reservation_id
    WHERE r2.flight_id = r.flight_id);

-- Q8 Integrity check: seats booked twice on one flight (should return 0 rows)
SELECT flight_id, seat_number, COUNT(*) AS times_booked
FROM reservations
WHERE reservation_status IN ('Pending','Confirmed')
GROUP BY flight_id, seat_number
HAVING COUNT(*) > 1;

-- Q9 Using the views
SELECT * FROM v_report_flight_manifest ORDER BY flight_number, seat_number;
SELECT * FROM v_report_baggage;
SELECT * FROM v_report_cancellations;
SELECT * FROM v_report_revenue ORDER BY revenue DESC;
