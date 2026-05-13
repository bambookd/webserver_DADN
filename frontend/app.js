const API = {
  health: "/api/health",
  state: "/api/state",
  sensorData: "/api/sensor-data",
  control: "/api/control",
  mode: "/api/mode",
  thresholds: "/api/thresholds",
  schedule: "/api/schedule",
  applySchedule: "/api/apply-schedule-now",
  simulate: "/api/simulate",
  reset: "/api/reset",
};

const ui = {
  serverStatus: document.getElementById("server-status"),
  connectionMode: document.getElementById("connection-mode"),
  lastUpdated: document.getElementById("last-updated"),
  temperature: document.getElementById("temperature"),
  humidity: document.getElementById("humidity"),
  soilMoisture: document.getElementById("soil-moisture"),
  light: document.getElementById("light"),
  gdd: document.getElementById("gdd"),
  cropStatus: document.getElementById("crop-status"),
  modeLabel: document.getElementById("mode-label"),
  rgbStatus: document.getElementById("rgb-status"),
  pumpP10: document.getElementById("pump-p10"),
  pumpP13: document.getElementById("pump-p13"),
  soilLow: document.getElementById("soil-low"),
  soilHigh: document.getElementById("soil-high"),
  lightLow: document.getElementById("light-low"),
  gddThreshold: document.getElementById("gdd-threshold"),
  scheduleText: document.getElementById("schedule-text"),
  message: document.getElementById("message"),
  historyLight: document.getElementById("history-light"),
  historySoil: document.getElementById("history-soil"),
  historyTemp: document.getElementById("history-temp"),
  historyHumidity: document.getElementById("history-humidity"),
};

const modeButtons = {
  0: document.getElementById("mode-0"),
  1: document.getElementById("mode-1"),
  2: document.getElementById("mode-2"),
};

let currentState = null;
let autoRefreshTimer = null;

function showMessage(text, isError = false) {
  ui.message.textContent = text;
  ui.message.classList.toggle("error", isError);
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined) {
    return "--";
  }
  return Number(value).toFixed(digits);
}

function formatTime(isoText) {
  if (!isoText) {
    return "--";
  }
  const date = new Date(isoText);
  if (Number.isNaN(date.getTime())) {
    return isoText;
  }
  return date.toLocaleString();
}

function minuteToHHMM(minute) {
  const h = Math.floor(minute / 60)
    .toString()
    .padStart(2, "0");
  const m = (minute % 60).toString().padStart(2, "0");
  return `${h}:${m}`;
}

function renderSchedule(slots) {
  if (!Array.isArray(slots) || slots.length === 0) {
    ui.scheduleText.textContent = "Chua co lich.";
    return;
  }
  ui.scheduleText.textContent = slots.map((slot) => `${minuteToHHMM(slot.start)}-${minuteToHHMM(slot.end)}`).join(", ");
}

function applyModeButtonState(modeValue) {
  Object.entries(modeButtons).forEach(([value, button]) => {
    const isActive = Number(value) === Number(modeValue);
    button.classList.toggle("active", isActive);
  });
}

function renderHistoryBars(container, values, maxValue) {
  container.innerHTML = "";
  const data = Array.isArray(values) ? values : [];

  if (data.length === 0) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = "Chua co du lieu";
    container.appendChild(empty);
    return;
  }

  const computedMax = maxValue || Math.max(...data, 1);
  data.forEach((item) => {
    const bar = document.createElement("div");
    bar.className = "history-bar";

    const fill = document.createElement("span");
    const width = Math.max(4, Math.min(100, (Number(item) / computedMax) * 100));
    fill.style.width = `${width}%`;

    const label = document.createElement("small");
    label.textContent = Number(item).toFixed(1);

    bar.appendChild(fill);
    bar.appendChild(label);
    container.appendChild(bar);
  });
}

function renderState(state) {
  currentState = state;

  ui.temperature.textContent = formatNumber(state.sensors.temperature);
  ui.humidity.textContent = formatNumber(state.sensors.humidity);
  ui.soilMoisture.textContent = formatNumber(state.sensors.soil_moisture);
  ui.light.textContent = formatNumber(state.sensors.light);
  ui.gdd.textContent = String(state.sensors.gdd ?? 0);
  ui.cropStatus.textContent = state.status.crop_status || "--";

  ui.connectionMode.textContent = state.status.connection || "simulation";
  ui.lastUpdated.textContent = formatTime(state.status.last_updated);

  ui.modeLabel.textContent = state.mode.label;
  const rgb = state.devices.rgb_status || "green";
  ui.rgbStatus.textContent = rgb;
  ui.rgbStatus.className = `rgb-indicator rgb-${rgb}`;
  applyModeButtonState(state.mode.value);

  ui.pumpP10.textContent = state.devices.pump_p10;
  ui.pumpP13.textContent = state.devices.pump_p13;
  ui.pumpP10.className = `pump-state ${state.devices.pump_p10}`;
  ui.pumpP13.className = `pump-state ${state.devices.pump_p13}`;

  ui.soilLow.value = state.thresholds.soil_low;
  ui.soilHigh.value = state.thresholds.soil_high;
  ui.lightLow.value = state.thresholds.light_low;
  ui.gddThreshold.value = state.thresholds.gdd_light_threshold;

  renderSchedule(state.schedule.slots || []);

  renderHistoryBars(ui.historyLight, state.history.light, Math.max(state.thresholds.gdd_light_threshold, 5000));
  renderHistoryBars(ui.historySoil, state.history.soil_moisture, 100);
  renderHistoryBars(ui.historyTemp, state.history.temperature, 45);
  renderHistoryBars(ui.historyHumidity, state.history.humidity, 100);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail || body.error || `Request failed: ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

async function refreshState() {
  try {
    const state = await requestJson(API.state);
    ui.serverStatus.textContent = "Online";
    ui.serverStatus.classList.remove("offline");
    renderState(state);
  } catch (error) {
    ui.serverStatus.textContent = "Offline";
    ui.serverStatus.classList.add("offline");
    showMessage(`Khong ket noi duoc backend: ${error.message}`, true);
    console.error("[Dashboard] refreshState error", error);
  }
}

async function sendMode(modeValue) {
  try {
    const state = await requestJson(API.mode, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: modeValue }),
    });
    renderState(state);
    showMessage(`Da chuyen sang Mode ${modeValue}.`);
  } catch (error) {
    showMessage(`Loi doi mode: ${error.message}`, true);
    console.error(error);
  }
}

async function sendControl(device, stateValue) {
  try {
    const state = await requestJson(API.control, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device, state: stateValue }),
    });
    renderState(state);
    showMessage(`${device} => ${stateValue}. Mode da ve Manual.`);
  } catch (error) {
    showMessage(`Loi dieu khien bom: ${error.message}`, true);
    console.error(error);
  }
}

async function saveThresholds() {
  const payload = {
    soil_low: Number(ui.soilLow.value),
    soil_high: Number(ui.soilHigh.value),
    light_low: Number(ui.lightLow.value),
    gdd_light_threshold: Number(ui.gddThreshold.value),
  };

  try {
    const state = await requestJson(API.thresholds, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderState(state);
    showMessage("Da luu nguong cam bien.");
  } catch (error) {
    showMessage(`Loi luu nguong: ${error.message}`, true);
    console.error(error);
  }
}

async function simulateSensorData() {
  try {
    const state = await requestJson(API.simulate, { method: "POST" });
    renderState(state);
    showMessage("Da tao du lieu gia lap moi.");
  } catch (error) {
    showMessage(`Loi simulate: ${error.message}`, true);
    console.error(error);
  }
}

async function applyScheduleNow() {
  try {
    const state = await requestJson(API.applySchedule, { method: "POST" });
    renderState(state);
    showMessage("Da ap dung lich tuoi tai thoi diem hien tai.");
  } catch (error) {
    showMessage(`Loi apply schedule: ${error.message}`, true);
    console.error(error);
  }
}

async function resetData() {
  const confirmed = window.confirm("Ban co chac chan muon reset toan bo data?");
  if (!confirmed) {
    return;
  }

  try {
    const state = await requestJson(API.reset, { method: "POST" });
    renderState(state);
    showMessage("Da reset du lieu ve mac dinh.");
  } catch (error) {
    showMessage(`Loi reset: ${error.message}`, true);
    console.error(error);
  }
}

async function checkHealth() {
  try {
    await requestJson(API.health);
    ui.serverStatus.textContent = "Online";
    ui.serverStatus.classList.remove("offline");
  } catch (error) {
    ui.serverStatus.textContent = "Offline";
    ui.serverStatus.classList.add("offline");
    showMessage(`Khong ping duoc server: ${error.message}`, true);
  }
}

function bindEvents() {
  modeButtons[0].addEventListener("click", () => sendMode(0));
  modeButtons[1].addEventListener("click", () => sendMode(1));
  modeButtons[2].addEventListener("click", () => sendMode(2));

  document.getElementById("p10-on").addEventListener("click", () => sendControl("pump_p10", "on"));
  document.getElementById("p10-off").addEventListener("click", () => sendControl("pump_p10", "off"));
  document.getElementById("p13-on").addEventListener("click", () => sendControl("pump_p13", "on"));
  document.getElementById("p13-off").addEventListener("click", () => sendControl("pump_p13", "off"));

  document.getElementById("save-thresholds").addEventListener("click", saveThresholds);
  document.getElementById("refresh-btn").addEventListener("click", refreshState);
  document.getElementById("simulate-btn").addEventListener("click", simulateSensorData);
  document.getElementById("apply-schedule").addEventListener("click", applyScheduleNow);
  document.getElementById("reset-btn").addEventListener("click", resetData);
}

function setupGlobalErrorLogging() {
  window.addEventListener("error", (event) => {
    showMessage("Frontend gap loi JavaScript. Mo Console de xem chi tiet.", true);
    console.error("[Dashboard] JS error", event.error || event.message);
  });

  window.addEventListener("unhandledrejection", (event) => {
    showMessage("Frontend gap loi Promise chua duoc xu ly. Mo Console de xem chi tiet.", true);
    console.error("[Dashboard] Unhandled Promise rejection", event.reason);
  });
}

async function init() {
  setupGlobalErrorLogging();
  bindEvents();
  await checkHealth();
  await refreshState();
  showMessage("Dashboard san sang.");
  autoRefreshTimer = window.setInterval(refreshState, 2000);
}

init();
