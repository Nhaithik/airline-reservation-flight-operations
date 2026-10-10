async function api(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Request failed");
    return data;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showToast(message, error = false) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.className = "toast show " + (error ? "error" : "");
    setTimeout(() => toast.className = "toast", 2800);
}

async function testConnection() {
    const badge = document.getElementById("connectionBadge");
    const message = document.getElementById("dbMessage");
    try {
        const result = await api("/api/health");
        if (badge) {
            badge.textContent = "● MySQL Connected";
            badge.className = "status-badge connected";
        }
        if (message) message.innerHTML = `● Connected to <strong>${escapeHtml(result.database)}</strong>`;
        showToast("MySQL connection successful");
    } catch (e) {
        if (badge) {
            badge.textContent = "● MySQL Disconnected";
            badge.className = "status-badge disconnected";
        }
        if (message) message.textContent = e.message;
        showToast(e.message, true);
    }
}

async function loadDashboard() {
    testConnection();
    try {
        const s = await api("/api/dashboard");
        document.getElementById("statFlights").textContent = s.flights ?? 0;
        document.getElementById("statPassengers").textContent = s.passengers ?? 0;
        document.getElementById("statReservations").textContent = s.reservations ?? 0;
        document.getElementById("statSeats").textContent = s.available_seats ?? 0;
        document.getElementById("statRevenue").textContent = "₹" + Number(s.revenue ?? 0).toFixed(2);
        document.getElementById("statCancellations").textContent = s.cancellations ?? 0;
    } catch (e) {
        showToast("Could not load dashboard: " + e.message, true);
    }
}
