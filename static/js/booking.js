const flightResults = document.getElementById("flightResults");
const flightCount = document.getElementById("flightCount");
const bookingCard = document.getElementById("bookingCard");
const successCard = document.getElementById("successCard");
const bookingResult = document.getElementById("bookingResult");
const passengerSelect = document.getElementById("passengerId");

let selectedFlight = null;
let currentFlights = [];

async function getJSON(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || "Request failed");
    }
    return data;
}

function formatDateTime(value) {
    if (!value) return "—";
    const d = new Date(value.replace(" ", "T"));
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short"
    });
}

function renderFlights(rows) {
    flightResults.innerHTML = "";

    if (!rows.length) {
        flightCount.textContent = "No matching flights found.";
        flightResults.innerHTML =
            '<tr><td colspan="7" class="empty-state">No flights match your search.</td></tr>';
        return;
    }

    currentFlights = rows;
    flightCount.textContent = `${rows.length} flight(s) found`;

    rows.forEach((flight, index) => {
        const tr = document.createElement("tr");
        const disabled = Number(flight.available_seats) <= 0 ? "disabled" : "";
        tr.innerHTML = `
            <td><strong>${escapeHTML(flight.flight_number)}</strong><br>
                <small>ID: ${flight.flight_id}</small></td>
            <td>${escapeHTML(flight.airline)}</td>
            <td>${escapeHTML(flight.source)} → ${escapeHTML(flight.destination)}</td>
            <td>${formatDateTime(flight.departure_time)}</td>
            <td>${formatDateTime(flight.arrival_time)}</td>
            <td><strong>${flight.available_seats}</strong></td>
            <td>
                <button class="small primary" ${disabled}
                    onclick="selectFlight(currentFlights[${index}])">
                    ${disabled ? "Full" : "Select"}
                </button>
            </td>
        `;
        flightResults.appendChild(tr);
    });
}

const escapeHTML = escapeHtml;

async function loadBookingSeatMap(flightId) {
    const map = document.getElementById("bookingSeatMap");
    map.innerHTML = '<span class="muted">Loading seats...</span>';
    try {
        const data = await getJSON(`/api/seat-map/${flightId}`);
        map.innerHTML = "";
        data.seats.forEach(s => {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "seat " + (s.occupied ? "occupied" : "available");
            b.textContent = s.seat_number;
            b.disabled = s.occupied;
            b.title = s.occupied ? "Taken" : "Available";
            b.addEventListener("click", () => {
                document.getElementById("seatNumber").value = s.seat_number;
                map.querySelectorAll(".seat.selected").forEach(x => x.classList.remove("selected"));
                b.classList.add("selected");
            });
            map.appendChild(b);
        });
    } catch (error) {
        map.innerHTML = `<span class="error-cell">${escapeHTML(error.message)}</span>`;
    }
}

window.selectFlight = async function(flight) {
    selectedFlight = flight;
    document.getElementById("seatNumber").value = "";
    loadBookingSeatMap(flight.flight_id);
    document.getElementById("bookingFlightId").value = flight.flight_id;

    document.getElementById("selectedFlightText").textContent =
        `${flight.flight_number} · ${flight.source} → ${flight.destination}`;

    document.getElementById("selectedFlightSummary").innerHTML = `
        <div><span>Flight</span><strong>${escapeHTML(flight.flight_number)}</strong></div>
        <div><span>Airline</span><strong>${escapeHTML(flight.airline)}</strong></div>
        <div><span>Departure</span><strong>${formatDateTime(flight.departure_time)}</strong></div>
        <div><span>Available</span><strong>${flight.available_seats} seats</strong></div>
    `;

    bookingCard.classList.remove("hidden");
    successCard.classList.add("hidden");
    bookingCard.scrollIntoView({ behavior: "smooth", block: "start" });
};

async function loadOptions() {
    try {
        const [flightOptions, passengers] = await Promise.all([
            getJSON("/api/flight-options"),
            getJSON("/api/booking-passengers")
        ]);

        const source = document.getElementById("source");
        const destination = document.getElementById("destination");

        flightOptions.sources.forEach(value => {
            source.insertAdjacentHTML("beforeend",
                `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`);
        });

        flightOptions.destinations.forEach(value => {
            destination.insertAdjacentHTML("beforeend",
                `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`);
        });

        passengerSelect.innerHTML = '<option value="">Select passenger</option>';
        passengers.forEach(p => {
            passengerSelect.insertAdjacentHTML("beforeend", `
                <option value="${p.passenger_id}">
                    ${escapeHTML(`${p.first_name} ${p.last_name}`)} — ID ${p.passenger_id}
                </option>
            `);
        });
    } catch (error) {
        passengerSelect.innerHTML = '<option value="">Unable to load passengers</option>';
        showToast(error.message, true);
    }
}

async function searchFlights() {
    const params = new URLSearchParams();
    const source = document.getElementById("source").value;
    const destination = document.getElementById("destination").value;
    const date = document.getElementById("travelDate").value;

    if (source) params.set("source", source);
    if (destination) params.set("destination", destination);
    if (date) params.set("date", date);

    try {
        flightCount.textContent = "Searching...";
        const rows = await getJSON(`/api/search-flights?${params.toString()}`);
        renderFlights(rows);
    } catch (error) {
        flightCount.textContent = "Search failed";
        flightResults.innerHTML =
            `<tr><td colspan="7" class="error-cell">${escapeHTML(error.message)}</td></tr>`;
        showToast(error.message, true);
    }
}

document.getElementById("flightSearchForm").addEventListener("submit", event => {
    event.preventDefault();
    searchFlights();
});

document.getElementById("clearSearch").addEventListener("click", () => {
    document.getElementById("flightSearchForm").reset();
    flightCount.textContent = "Search results will appear here.";
    flightResults.innerHTML =
        '<tr><td colspan="7" class="empty-state">Use the search form to find flights.</td></tr>';
    bookingCard.classList.add("hidden");
    successCard.classList.add("hidden");
});

document.getElementById("cancelBooking").addEventListener("click", () => {
    bookingCard.classList.add("hidden");
    selectedFlight = null;
});

document.getElementById("bookingForm").addEventListener("submit", async event => {
    event.preventDefault();

    const payload = {
        passenger_id: passengerSelect.value,
        flight_id: document.getElementById("bookingFlightId").value,
        seat_number: document.getElementById("seatNumber").value.trim().toUpperCase()
    };

    if (!payload.passenger_id || !payload.flight_id || !payload.seat_number) {
        showToast("Please complete all booking fields.", true);
        return;
    }

    try {
        const result = await getJSON("/api/book", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        bookingResult.innerHTML = `
            <div class="booking-success-grid">
                <div><span>Reservation ID</span><strong>#${result.reservation_id}</strong></div>
                <div><span>Passenger</span><strong>${escapeHTML(result.passenger_name)}</strong></div>
                <div><span>Flight</span><strong>${escapeHTML(result.flight_number)}</strong></div>
                <div><span>Route</span><strong>${escapeHTML(result.route)}</strong></div>
                <div><span>Seat</span><strong>${escapeHTML(result.seat_number)}</strong></div>
                <div><span>Status</span><strong>${escapeHTML(result.reservation_status)}</strong></div>
            </div>
        `;

        bookingCard.classList.add("hidden");
        successCard.classList.remove("hidden");
        document.getElementById("bookingForm").reset();
        showToast("Booking created successfully.");

        // Refresh the selected search so the available-seat count changes.
        await searchFlights();
        successCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
        showToast(error.message, true);
    }
});

document.addEventListener("DOMContentLoaded", async () => {
    await loadOptions();
    await searchFlights();
});
