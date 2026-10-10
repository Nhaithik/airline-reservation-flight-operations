-- =====================================================================
-- OPTIONAL additions. Read each block; skip anything your schema already has
-- (check with DESCRIBE flights; and SHOW INDEX FROM <table>;).
-- =====================================================================
USE airline_reservation;

-- 1) On-time status support (needed by the On-Time report) -------------
ALTER TABLE flights
    ADD COLUMN actual_departure_time DATETIME NULL,
    ADD COLUMN flight_status VARCHAR(20) NOT NULL DEFAULT 'Scheduled';

ALTER TABLE flights
    ADD CONSTRAINT chk_flight_status
    CHECK (flight_status IN ('Scheduled','Departed','Delayed','Cancelled'));

-- Sample data so the report has something to show
UPDATE flights SET actual_departure_time = departure_time + INTERVAL 5  MINUTE,
                   flight_status = 'Departed' WHERE MOD(flight_id,3) = 1;
UPDATE flights SET actual_departure_time = departure_time + INTERVAL 50 MINUTE,
                   flight_status = 'Delayed'  WHERE MOD(flight_id,3) = 2;

-- On-time query (on time = departed within 15 minutes of schedule)
SELECT flight_number, departure_time, actual_departure_time,
       TIMESTAMPDIFF(MINUTE, departure_time, actual_departure_time) AS delay_minutes,
       CASE WHEN actual_departure_time IS NULL THEN 'Not departed'
            WHEN TIMESTAMPDIFF(MINUTE, departure_time, actual_departure_time) <= 15 THEN 'On Time'
            ELSE 'Delayed' END AS on_time_status
FROM flights;

-- 2) Indexes for frequently searched columns ----------------------------
CREATE INDEX idx_flights_route_date  ON flights (source, destination, departure_time);
CREATE INDEX idx_res_flight_status   ON reservations (flight_id, reservation_status);
CREATE INDEX idx_res_passenger       ON reservations (passenger_id);
CREATE INDEX idx_payments_reservation ON payments (reservation_id, payment_status);
