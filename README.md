Airline Reservation & Flight Operations Management System
Student: Nhaithik Reddy Siddenki
Roll Number: 25WU0102185
Programme: B.Tech Artificial Intelligence & Machine Learning
Faculty: Dr. C. Nagaraju
Institution: School of Technology
Project Type: DBMS Project-Based Learning (PBL)
Academic Year: 2026--2027
1. Project Overview
The Airline Reservation & Flight Operations Management System is a
database-driven project designed to manage airline operations through a
MySQL database and a Python Flask web application.
The system covers flight search, reservations, seat allocation,
payments, ticketing, check-in, baggage, cancellations, and reporting.
2. Problem Statement
The project addresses three main problems:
- Seat conflicts: preventing two passengers from reserving the
  same seat on a flight.
- Incomplete manifests: keeping reservation, ticket, and check-in
  information organised and connected.
- Invalid refunds: preventing cancellations after check-in and
  refunds that exceed the amount paid.
3. Objectives
- Model airports, routes, aircraft, seats, flights, passengers,
  reservations, and payments using a relational database design.
- Organise the schema around First, Second, and Third Normal Forms
  (1NF, 2NF, and 3NF).
- Use keys and integrity constraints, including CHECK, DEFAULT,
  and UNIQUE rules where applicable.
- Enforce booking, check-in, cancellation, and refund rules with SQL
  triggers.
- Develop a Flask web application for flight search, booking, payment,
  ticketing, check-in, baggage, cancellation, and reports.
4. Technologies Used
- Database: MySQL 8
- Backend: Python with Flask
- Frontend: HTML, CSS, and JavaScript
- Database connectivity: MySQL Connector/Python
- Development tools: Visual Studio Code and MySQL Workbench
5. System Architecture
The system has three main layers:
1. Browser: displays the dashboard, booking pages, operations
   modules, and reports.
2. Flask application: handles application routes, input validation,
   transactions, and parameterised SQL queries.
3. MySQL database: stores project data and implements relational
   constraints, triggers, and views.
Database summary
- 13 tables
- 5 triggers
- 7 reporting views
- 8 main workflow steps
6. Database Tables
The database contains the following 13 tables:
1. aircraft
2. airports
3. baggage
4. cancellations
5. check_ins
6. fares
7. flights
8. passengers
9. payments
10. reservations
11. routes
12. seats
13. tickets
The reservation is the central transaction entity, connecting a
passenger with a flight, seat, and reservation status. Reservations are
associated with related payment, ticket, check-in, baggage, and
cancellation records.
7. Normalisation
The presentation describes the database as designed around Third
Normal Form (3NF):
- 1NF: columns contain atomic values and repeating groups are
  avoided.
- 2NF: non-key attributes depend on the whole candidate key; the
  design uses single-column surrogate keys.
- 3NF: passenger and flight details are maintained in their own
  tables rather than duplicated in reservation records.
The presentation identifies alternate keys declared as UNIQUE,
including flight number, email, ticket number, boarding-pass number, and
transaction reference.
8. Integrity Constraints and Business Rules
- A flight seat should not be assigned to multiple passengers:
  UNIQUE (flight_id, seat_number).
- One reservation per passenger per flight:
  UNIQUE (passenger_id, flight_id).
- Available seats must not be negative; confirmation is blocked when
  no seats remain.
- Baggage weight must be non-negative; the application accepts a range
  of 0--100 kg.
- Check-in is allowed only when a reservation is Confirmed.
- A reservation cannot be cancelled after check-in.
- Refunds cannot exceed the amount paid.
9. SQL Triggers
The presentation describes five triggers:
- before_reservation_update
- after_reservation_update
- before_checkin_insert
- prevent_cancellation_after_checkin
- before_cancellation_insert
Their intended roles include checking seat availability when confirming
reservations, updating available-seat counts after status changes,
allowing check-in only for confirmed reservations, preventing
cancellation after check-in, and validating refund amounts.
Trigger names in this README follow the project presentation. Check
the actual trigger names in MySQL if they differ.

10. Reporting Views
The project contains seven reporting views:
- flight_manifest_view
- flight_occupancy_view
- route_demand_view
- baggage_report_view
- cancellation_report_view
- revenue_report_view
- reservation_details
These views support operational summaries and reporting for
reservations, flights, baggage, cancellations, revenue, and route
demand.
11. Application Workflow
1. Search: filter flights by source, destination, and date.
2. Book: create a pending reservation with passenger and seat
   details.
3. Seat allocation: select an available seat.
4. Pay: record a valid payment and confirm the reservation.
5. Ticket: issue a ticket after payment.
6. Check-in: generate boarding-pass and gate details for a
   confirmed reservation.
7. Baggage: record baggage weight after check-in.
8. Cancel: process cancellation and calculate a refund according to
   the time before departure.
12. Testing and Results
The presentation documents an end-to-end positive workflow for
reservation #17:
- Payment of ₹5,000 by UPI
- Ticket TKT006 issued
- Boarding pass BP005 with gate A1
- Baggage record #9 saved with a weight of 40 kg
The presentation also documents negative tests for:
- Check-in on a pending reservation
- Cancellation after check-in
- Refund greater than the payment amount
- A second cancellation for the same reservation
The presentation reports that these invalid actions were rejected by the
implemented rules. Re-run the tests against the submitted database if
independent verification is required.
13. Outcomes
- A 13-table MySQL relational design with keys and integrity rules
- SQL triggers for check-in, cancellation, refund, and seat-related
  rules
- A Python Flask application covering the search-to-cancellation
  workflow
- Reporting views and sample data for demonstrating the system
14. Future Enhancements
- Login and role-based access for staff and passengers
- Additional foreign-key relationships between flights, aircraft, and
  routes
- Integration with a real payment gateway
- Automatic release of unpaid bookings
- Flight-delay tracking and on-time status reporting
15. Project Files
This repository folder is intended to contain:
- Airline_Reservation_Project_Presentation.pdf --- project
  presentation
- Final DBMS PBL report PDF
- Python/Flask source code or source ZIP
- SQL scripts and SQL documentation
- Supporting database and application screenshots
Upload each file to this repository and update filenames here if they
differ. Do not upload database passwords, API keys, or other secrets.
16. How to Run Locally
1. Install Python and MySQL.
2. Open the project folder in Visual Studio Code.
3. Create and activate a Python virtual environment.
4. Install dependencies from requirements.txt if provided.
5. Configure the database connection using local environment settings.
6. Start the Flask application:
   python app.py
7. If the application starts successfully, open http://127.0.0.1:5000
   in a browser.
The exact setup depends on the submitted source files and local MySQL
configuration.
17. Repository
GitHub repository:
https://github.com/Nhaithik/airline-reservation-flight-operations
