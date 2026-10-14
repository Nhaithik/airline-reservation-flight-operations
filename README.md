# Airline Reservation & Flight Operations Management System


## 1. Project Overview

This project is a web-based airline reservation and flight operations management system developed using Python Flask, MySQL, HTML, CSS, and JavaScript.

It manages flight information, passenger records, reservations, seat allocation, ticketing, check-in, baggage, payments, cancellations, and reports.

## 2. Technologies Used

- Python and Flask
- MySQL
- HTML, CSS, and JavaScript
- Git and GitHub

## 3. Main Modules

- Dashboard
- Flights and flight search
- Passengers
- Reservations and booking
- Seat allocation
- Tickets
- Check-in
- Baggage
- Payments
- Cancellations and refunds
- Reports

## 4. Requirements

- Python 3.10 or later
- MySQL Server
- Visual Studio Code
- The existing database named `airline_reservation`

## 5. Setup Instructions

Open the project folder in VS Code and open its terminal.

Create and activate a virtual environment on macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Configure your local `.env` file with the correct MySQL connection details. Never upload database passwords or API keys to GitHub.

## 6. Run the Application

Start the Flask application:

```bash
python app.py
```

Open this address in your browser:

http://127.0.0.1:5000

The Flask backend and MySQL server must be running for database functionality.

## 7. Booking Workflow

The intended operational workflow is:

**Flight Search → Booking → Seat Allocation → Payment → Ticket Issue → Check-In → Baggage → Cancellation/Refund → Reports**

The application uses the existing MySQL database. Do not drop or recreate existing tables when running the project.

## 8. Database and Testing

The project includes SQL scripts, a schema verification script, and a test plan. Review the SQL files before execution and use the existing database configuration.

## 9. Security

- Keep `.env` private.
- Do not commit passwords, API keys, or other secrets.
- Use `.gitignore` to exclude environment files and virtual environments.

## 10. Repository

GitHub: https://github.com/Nhaithik/airline-reservation-flight-operations
