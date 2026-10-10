let meta = null;
let rows = [];
let editingKey = null;
let timer = null;

function debouncedLoadModule() {
    clearTimeout(timer);
    timer = setTimeout(loadModule, 250);
}

async function loadModule() {
    try {
        if (!meta) meta = await api(`/api/table/${TABLE}/meta`);
        const search = document.getElementById("searchInput").value;
        const result = await api(`/api/table/${TABLE}?search=${encodeURIComponent(search)}&limit=200`);
        rows = result.rows;
        const addBtn = document.getElementById("addRecordBtn");
        if (addBtn) addBtn.style.display = result.read_only ? "none" : "";
        renderTable(result);
    } catch (e) {
        document.getElementById("tableBody").innerHTML =
            `<tr><td colspan="99" class="error-cell">${escapeHtml(e.message)}</td></tr>`;
        showToast(e.message, true);
    }
}

function renderTable(result) {
    const head = document.getElementById("tableHead");
    const body = document.getElementById("tableBody");
    head.innerHTML = "";
    body.innerHTML = "";

    result.columns.forEach(c => {
        head.innerHTML += `<th>${escapeHtml(c.COLUMN_NAME)}</th>`;
    });
    const canEdit = !result.read_only && result.primary_key;
    if (canEdit) head.innerHTML += `<th>Actions</th>`;

    result.rows.forEach((row, index) => {
        let html = "";
        result.columns.forEach(c => {
            let value = row[c.COLUMN_NAME];
            if (value === null || value === undefined) value = "NULL";
            html += `<td>${escapeHtml(value)}</td>`;
        });
        if (canEdit) {
            html += `<td class="actions">
                <button class="small" onclick="editRow(${index})">Edit</button>
                <button class="small danger" onclick="deleteRow(${index})">Delete</button>
            </td>`;
        }
        body.innerHTML += `<tr>${html}</tr>`;
    });

    const note = result.read_only ? " — read-only (changed through the booking workflow)" : "";
    document.getElementById("recordCount").textContent = `${result.rows.length} record(s) shown${note}`;
}

function inputForColumn(c, value = "") {
    const typeMap = {
        int: "number", bigint: "number", decimal: "number", float: "number", double: "number",
        date: "date", datetime: "datetime-local", timestamp: "datetime-local"
    };
    const inputType = typeMap[c.DATA_TYPE] || "text";
    const step = ["decimal","float","double"].includes(c.DATA_TYPE) ? "0.01" : "1";
    const required = c.IS_NULLABLE === "NO" && !String(c.EXTRA || "").includes("auto_increment");
    let val = value ?? "";
    if ((inputType === "datetime-local") && typeof val === "string") val = val.replace(" ", "T").slice(0,16);

    return `<label>${escapeHtml(c.COLUMN_NAME)}
        <input name="${escapeHtml(c.COLUMN_NAME)}" type="${inputType}" step="${step}"
               value="${escapeHtml(val)}" ${required ? "required" : ""}>
        <small>${escapeHtml(c.DATA_TYPE)}${required ? " • required" : " • optional"}</small>
    </label>`;
}

function openAddModal() {
    editingKey = null;
    document.getElementById("modalTitle").textContent = "Add Record";
    const form = document.getElementById("formFields");
    form.innerHTML = meta.columns
        .filter(c => !String(c.EXTRA || "").includes("auto_increment"))
        .map(c => inputForColumn(c)).join("");
    document.getElementById("modal").classList.remove("hidden");
}

function editRow(index) {
    const row = rows[index];
    editingKey = String(row[meta.primary_key]);
    document.getElementById("modalTitle").textContent = "Edit Record";
    document.getElementById("formFields").innerHTML = meta.columns
        .filter(c => c.COLUMN_NAME !== meta.primary_key && !String(c.EXTRA || "").includes("auto_increment"))
        .map(c => inputForColumn(c, row[c.COLUMN_NAME])).join("");
    document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
}

async function saveRecord(event) {
    event.preventDefault();
    const form = new FormData(event.target);
    const data = Object.fromEntries(form.entries());

    // Blank values: send null for nullable columns (so they can be cleared on
    // edit); omit blank NOT NULL columns so existing values are kept.
    meta.columns.forEach(c => {
        const name = c.COLUMN_NAME;
        if (data[name] === "") {
            if (editingKey && c.IS_NULLABLE === "YES") data[name] = null;
            else delete data[name];
        }
    });

    try {
        const url = editingKey
            ? `/api/table/${TABLE}/${encodeURIComponent(editingKey)}`
            : `/api/table/${TABLE}`;
        const method = editingKey ? "PUT" : "POST";
        await api(url, {
            method,
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });
        closeModal();
        await loadModule();
        showToast(editingKey ? "Record updated successfully" : "Record added successfully");
    } catch (e) {
        showToast(e.message, true);
    }
}

async function deleteRow(index) {
    const key = String(rows[index][meta.primary_key]);
    if (!confirm("Delete this record? This action cannot be undone.")) return;
    try {
        await api(`/api/table/${TABLE}/${encodeURIComponent(key)}`, {method: "DELETE"});
        await loadModule();
        showToast("Record deleted");
    } catch (e) {
        showToast(e.message, true);
    }
}
