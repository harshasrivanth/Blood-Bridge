const API = "https://blood-bridge-e84w.onrender.com";
const connection = document.getElementById("connection");
const statusPill = document.getElementById("statusPill");
const result = document.getElementById("result");
const unitsInput = document.getElementById("units");
const requestForm = document.getElementById("requestForm");
const donorForm = document.getElementById("donorForm");
const donorResult = document.getElementById("donorResult");
const citySelect = document.getElementById("city");
const hospitalSelect = document.getElementById("hospital");

// Local prototype list matching the three demo rows in the local hospitals table.
const hospitalsByCity = {
    "Visakhapatnam": ["My hospital"],
    "Vijayawada": ["My hospital"],
    "Hyderabad": ["My hospital"]
};

citySelect.addEventListener("change", () => {
    const city = citySelect.value;
    hospitalSelect.innerHTML = "";

    if (!city || !hospitalsByCity[city]) {
        hospitalSelect.add(new Option("Select an area first", ""));
        hospitalSelect.disabled = true;
        return;
    }

    hospitalSelect.add(new Option("Select hospital", ""));
    hospitalsByCity[city].forEach(name => hospitalSelect.add(new Option(`${name} (demo)`, name)));
    hospitalSelect.disabled = false;
});

function setStatus(state, text) {
    statusPill.dataset.state = state;
    connection.textContent = text;
}

async function checkBackend() {
    setStatus("checking", "Connecting…");
    try {
        const response = await fetch(`${API}/health`);
        if (!response.ok) throw new Error("Backend returned an error");
        const data = await response.json();
        setStatus("ok", `Server: ${data.status}`);
    } catch {
        setStatus("down", "Server unavailable. Check its terminal.");
    }
}

document.getElementById("checkButton").addEventListener("click", checkBackend);
checkBackend();

function changeUnits(delta) {
    const current = Number(unitsInput.value || 1);
    unitsInput.value = Math.min(10, Math.max(1, current + delta));
}
document.getElementById("minus").addEventListener("click", () => changeUnits(-1));
document.getElementById("plus").addEventListener("click", () => changeUnits(1));

function getErrorMessage(data, fallback) {
    if (Array.isArray(data.detail)) return data.detail.map(item => item.msg).join(", ");
    return data.detail || fallback;
}

requestForm.addEventListener("submit", async event => {
    event.preventDefault();
    result.classList.remove("error", "success");

    const group = document.querySelector('input[name="bloodGroup"]:checked');
    const patientName = document.getElementById("patientName").value.trim();
    const patientEmail = document.getElementById("patientEmail").value.trim();
    const hospital = document.getElementById("hospital").value;
    const city = document.getElementById("city").value.trim();
    const hospitalDocument = document.getElementById("hospitalDocument").files[0];
    const units = Number(unitsInput.value);

    if (!group) {
        result.classList.add("error");
        result.textContent = "Please select the required blood group.";
        return;
    }
    if (!patientName || !patientEmail || !hospital || !city || !hospitalDocument) {
        result.classList.add("error");
        result.textContent = "Please complete all required fields and upload the My Hospital demo PDF.";
        return;
    }
    if (hospitalDocument.type !== "application/pdf" || hospitalDocument.size > 5 * 1024 * 1024) {
        result.classList.add("error");
        result.textContent = "Upload a PDF file of 5 MB or smaller.";
        return;
    }
    if (!Number.isInteger(units) || units < 1 || units > 10) {
        result.classList.add("error");
        result.textContent = "Units must be a whole number from 1 to 10.";
        return;
    }

    const requestData = new FormData();
    requestData.append("patient_name", patientName);
    requestData.append("patient_email", patientEmail);
    requestData.append("blood_group", group.value);
    requestData.append("units_required", String(units));
    requestData.append("hospital_name", hospital);
    requestData.append("city", city);
    requestData.append("urgency", "high");
    requestData.append("hospital_document", hospitalDocument);

    const submitButton = document.getElementById("requestSubmit");
    submitButton.disabled = true;
    result.textContent = "Submitting request…";

    try {
        const response = await fetch(`${API}/requests`, {
            method: "POST",
            body: requestData
        });
        const data = await response.json();
        if (!response.ok) throw new Error(getErrorMessage(data, "Request could not be processed."));

        result.classList.add(data.message.toLowerCase().includes("emailed") ? "success" : "notice-result");
        result.textContent = data.message;
        requestForm.reset();
        unitsInput.value = 1;
        hospitalSelect.innerHTML = '<option value="">Select an area first</option>';
        hospitalSelect.disabled = true;
    } catch (error) {
        result.classList.add("error");
        result.textContent = error.message === "Failed to fetch"
            ? "We couldn't process the request right now. Please try again later or contact the hospital blood bank."
            : error.message;
    } finally {
        submitButton.disabled = false;
    }
});

donorForm.addEventListener("submit", async event => {
    event.preventDefault();
    donorResult.classList.remove("error", "success");

    const fullName = document.getElementById("donorName").value.trim();
    const bloodGroup = document.getElementById("donorBloodGroup").value;
    const phone = document.getElementById("donorPhone").value.trim();
    const city = document.getElementById("donorCity").value.trim();
    const isAvailable = document.getElementById("donorAvailable").checked;
    const consent = document.getElementById("donorConsent").checked;

    if (!/^[6-9]\d{9}$/.test(phone)) {
        donorResult.classList.add("error");
        donorResult.textContent = "Enter a valid 10-digit Indian mobile number.";
        return;
    }
    if (!fullName || !bloodGroup || !city) {
        donorResult.classList.add("error");
        donorResult.textContent = "Please complete all required donor fields.";
        return;
    }
    if (!consent) {
        donorResult.classList.add("error");
        donorResult.textContent = "Consent is required before contact details can be shared with a matched requester.";
        return;
    }

    const donorData = {
        full_name: fullName,
        blood_group: bloodGroup,
        phone,
        city,
        is_available: isAvailable,
        consent_to_share_contact: consent
    };
    const submitButton = document.getElementById("donorSubmit");
    submitButton.disabled = true;
    donorResult.textContent = "Registering donor…";

    try {
        const response = await fetch(`${API}/donors`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(donorData)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(getErrorMessage(data, "Donor registration failed."));
        donorResult.classList.add("success");
        donorResult.textContent = "Donor registration completed.";
        donorForm.reset();
        document.getElementById("donorAvailable").checked = true;
    } catch (error) {
        donorResult.classList.add("error");
        donorResult.textContent = error.message === "Failed to fetch"
            ? "Cannot connect to the backend. Check that the server is running."
            : error.message;
    } finally {
        submitButton.disabled = false;
    }
});
