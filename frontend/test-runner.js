const API = {
  health: "/api/health",
  state: "/api/state",
  simulate: "/api/simulate",
  reset: "/api/reset",
  mode: "/api/mode",
  control: "/api/control",
  sensorData: "/api/sensor-data",
  applySchedule: "/api/apply-schedule-now",
};

const resultBody = document.getElementById("result-body");
const summary = document.getElementById("summary");

function setSummary(text, ok = true) {
  summary.textContent = text;
  summary.style.color = ok ? "#0f2954" : "#bb1b3f";
  summary.style.background = ok ? "#eaf1ff" : "#ffeef3";
}

function rowHtml(index, name, status, detail) {
  const statusClass = status === "PASS" ? "status-pass" : status === "FAIL" ? "status-fail" : "status-wait";
  return `<tr>
    <td>${index}</td>
    <td>${name}</td>
    <td class="${statusClass}">${status}</td>
    <td>${detail}</td>
  </tr>`;
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  }
  return body;
}

function testCases() {
  return [
    {
      name: "Health endpoint online",
      run: async () => {
        const data = await request(API.health);
        if (data.status !== "ok") throw new Error("status khong phai ok");
        return "health ok";
      },
    },
    {
      name: "Reset ve state mac dinh",
      run: async () => {
        const data = await request(API.reset, { method: "POST" });
        if (data.mode.value !== 1) throw new Error("mode reset khong dung");
        return "mode=1, rgb=green";
      },
    },
    {
      name: "Mode 2 -> Scheduled + RGB yellow",
      run: async () => {
        const data = await request(API.mode, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: 2 }),
        });
        if (data.mode.value !== 2) throw new Error("mode != 2");
        if (data.devices.rgb_status !== "yellow") throw new Error("rgb khong yellow");
        return "mode 2 ok";
      },
    },
    {
      name: "Mode 1 auto rule bat P10",
      run: async () => {
        await request(API.mode, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: 1 }),
        });

        const data = await request(API.sensorData, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            temperature: 30,
            humidity: 60,
            soil_moisture: 20,
            light: 500,
          }),
        });

        if (data.devices.pump_p10 !== "on") throw new Error("P10 khong on");
        return "P10 on dung rule";
      },
    },
    {
      name: "Mode 1 auto rule tat P10",
      run: async () => {
        const data = await request(API.sensorData, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            temperature: 30,
            humidity: 60,
            soil_moisture: 90,
            light: 1200,
          }),
        });

        if (data.devices.pump_p10 !== "off") throw new Error("P10 khong off");
        return "P10 off dung rule";
      },
    },
    {
      name: "Manual control ve mode 0",
      run: async () => {
        const data = await request(API.control, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device: "pump_p13", state: "on" }),
        });
        if (data.mode.value !== 0) throw new Error("mode khong ve 0");
        if (data.devices.rgb_status !== "red") throw new Error("rgb khong red");
        return "manual override ok";
      },
    },
    {
      name: "Simulate tao history",
      run: async () => {
        const data = await request(API.simulate, { method: "POST" });
        if (!data.history || data.history.temperature.length === 0) {
          throw new Error("history temperature rong");
        }
        return `history len=${data.history.temperature.length}`;
      },
    },
    {
      name: "Apply schedule endpoint hoat dong",
      run: async () => {
        await request(API.mode, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: 2 }),
        });
        const data = await request(API.applySchedule, { method: "POST" });
        if (!data.devices || !data.mode) throw new Error("response thieu field");
        return "endpoint tra ve state hop le";
      },
    },
  ];
}

async function runAllTests() {
  const tests = testCases();
  resultBody.innerHTML = "";
  setSummary("Dang chay test...", true);

  let pass = 0;
  let fail = 0;

  for (let i = 0; i < tests.length; i += 1) {
    const test = tests[i];
    resultBody.insertAdjacentHTML("beforeend", rowHtml(i + 1, test.name, "WAIT", "Dang chay"));

    try {
      const detail = await test.run();
      pass += 1;
      resultBody.rows[i].cells[2].className = "status-pass";
      resultBody.rows[i].cells[2].textContent = "PASS";
      resultBody.rows[i].cells[3].textContent = detail;
    } catch (error) {
      fail += 1;
      resultBody.rows[i].cells[2].className = "status-fail";
      resultBody.rows[i].cells[2].textContent = "FAIL";
      resultBody.rows[i].cells[3].textContent = error.message;
      console.error("Test failed:", test.name, error);
    }
  }

  if (fail === 0) {
    setSummary(`Hoan tat: PASS ${pass}/${tests.length}, FAIL 0`, true);
  } else {
    setSummary(`Hoan tat: PASS ${pass}/${tests.length}, FAIL ${fail}`, false);
  }
}

async function resetFirst() {
  try {
    await request(API.reset, { method: "POST" });
    setSummary("Da reset state thanh cong.", true);
  } catch (error) {
    setSummary(`Reset that bai: ${error.message}`, false);
  }
}

document.getElementById("run-all").addEventListener("click", runAllTests);
document.getElementById("reset-first").addEventListener("click", resetFirst);
document.getElementById("open-dashboard").addEventListener("click", () => {
  window.open("/", "_blank");
});
