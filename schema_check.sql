USE airline_reservation;

-- Confirm all project tables
SHOW TABLES;

-- Confirm the main Flights structure
DESCRIBE flights;

-- Confirm reservations and passengers
DESCRIBE reservations;
DESCRIBE passengers;

-- Confirm transaction tables
DESCRIBE payments;
DESCRIBE cancellations;

-- Confirm check-in and baggage
DESCRIBE check_ins;
DESCRIBE baggage;

-- Confirm views/triggers if required for the final demonstration
SHOW FULL TABLES WHERE Table_type = 'VIEW';
SHOW TRIGGERS;
