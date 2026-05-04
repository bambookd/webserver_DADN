const API_BASE = "";

const el = {
  temperature: document.getElementById("temperature"),
  humidity: document.getElementById("humidity"),
  soilMoisture: document.getElementById("soil_moisture"),
  light: document.getElementById("light"),
  pumpStatus: document.getElementById("pump-status"),
  autoModeStatus: document.getElementById("auto-mode-status"),
  pumpOnBtn: document.getElementById("pump-on-btn"),
  pumpOffBtn: document.getElementById("pump-off-btn"),
  toggleAutoBtn: document.getElementById("toggle-auto-btn"),
  message: document.getElementById("message"),
  clock: document.getElementById("clock"),
};

let autoMode = true;

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "--";
  }
  return Number(value).toFixed(1);
}

function showMessage(text, isError = false) {
  el.message.textContent = text;
  el.message.style.color = isError ? "#b31942" : "#0e6b4f";
}

async function fetchSensorData() {
  try {
    const response = await fetch(`${API_BASE}/sensor-data`);
    if (!response.ok) {
      throw new Error(`Failed to load sensor data: ${response.status}`);
    }

    const data = await response.json();
    const latest = data.latest || {};

    el.temperature.textContent = formatNumber(latest.temperature);
    el.humidity.textContent = formatNumber(latest.humidity);
    el.soilMoisture.textContent = formatNumber(latest.soil_moisture);
    el.light.textContent = formatNumber(latest.light);

    el.pumpStatus.textContent = (data.pump || "unknown").toUpperCase();
    el.pumpStatus.className = `badge ${(data.pump || "off") === "on" ? "on" : "off"}`;

    autoMode = Boolean(data.auto_mode);
    el.autoModeStatus.textContent = autoMode ? "ENABLED" : "DISABLED";
    el.autoModeStatus.className = `badge ${autoMode ? "auto-on" : "auto-off"}`;
    el.toggleAutoBtn.textContent = autoMode ? "Disable Auto Mode" : "Enable Auto Mode";
  } catch (error) {
    showMessage(error.message, true);
    console.error(error);
  }
}

async function sendControl(state) {
  try {
    const response = await fetch(`${API_BASE}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device: "pump", state }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || err.error || "Control command failed");
    }

    showMessage(`Pump is now ${state.toUpperCase()}`);
    await fetchSensorData();
  } catch (error) {
    showMessage(error.message, true);
    console.error(error);
  }
}

async function toggleAutoMode() {
  try {
    const response = await fetch(`${API_BASE}/auto-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !autoMode }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || err.error || "Update auto mode failed");
    }

    showMessage(`Auto mode ${!autoMode ? "ENABLED" : "DISABLED"}`);
    await fetchSensorData();
  } catch (error) {
    showMessage(error.message, true);
    console.error(error);
  }
}

function updateClock() {
  const now = new Date();
  el.clock.textContent = now.toLocaleTimeString();
}

el.pumpOnBtn.addEventListener("click", () => sendControl("on"));
el.pumpOffBtn.addEventListener("click", () => sendControl("off"));
el.toggleAutoBtn.addEventListener("click", toggleAutoMode);

updateClock();
setInterval(updateClock, 1000);
fetchSensorData();
setInterval(fetchSensorData, 2500);
