const API = "http://127.0.0.1:8000";

const connection = document.getElementById("connection");
const statusPill = document.getElementById("statusPill");
const result = document.getElementById("result");
const unitsInput = document.getElementById("units");

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
    } catch (error) {
        setStatus("down", "Server unavailable. Check its terminal.");
    }
}

document.getElementById("checkButton").addEventListener("click", checkBackend);
checkBackend();

function changeUnits(delta) {
    const next = Number(unitsInput.value || 1) + delta;
    unitsInput.value = Math.min(10, Math.max(1, next));
}
document.getElementById("minus").addEventListener("click", () => changeUnits(-1));
document.getElementById("plus").addEventListener("click", () => changeUnits(1));

document.getElementById("requestForm").addEventListener("submit", (event) => {
    event.preventDefault();

    const group = document.querySelector('input[name="bloodGroup"]:checked');
    const hospital = document.getElementById("hospital").value.trim();
    const units = Number(unitsInput.value);

    result.classList.remove("error");

    if (!group) {
        result.classList.add("error");
        result.textContent = "Choose a blood group to continue.";
        return;
    }
    if (!hospital) {
        result.classList.add("error");
        result.textContent = "Enter the hospital name to continue.";
        return;
    }

    const request = { blood_group: group.value, units, hospital };
    result.textContent =
        `Checked: ${units} unit(s) of ${group.value} at ${hospital}. ` +
        "Not sent yet. The database is not connected.";
    console.log("Test request:", request);
});
