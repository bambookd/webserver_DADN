# Hardware Test Plan

## 1. Phase 1: Test local dashboard without hardware
- Run backend server.
- Open dashboard in browser.
- Click simulate.
- Verify cards, history, GDD, mode, pump status.

## 2. Phase 2: Test backend API with curl/Postman
- POST /api/sensor-data
- POST /api/control
- POST /api/mode

## 3. Phase 3: Test with real Yolo:Bit

Option A: Direct HTTP
- Laptop and Yolo:Bit on same WiFi.
- Find laptop IP with ipconfig.
- Send data to:
  - http://<LAPTOP_IP>:8000/api/sensor-data

Option B: OhStem MQTT bridge
- Keep old Yolo:Bit code publishing V1-V5.
- Enable backend MQTT bridge.
- Use V7 to set mode.
- Use V10/V11 to control pumps.
- Dashboard should update from MQTT messages.

## 4. Expected behavior
- Sensor cards update.
- LCD still works on hardware.
- Dashboard history changes.
- GDD increases when LUX >= 2000.
- Mode 1 controls P10 based on SM and LUX.
- Mode 2 controls P13 based on schedule.
- Manual pump button switches to mode 0.

## 5. Troubleshooting
- Server not reachable.
- Wrong laptop IP.
- Windows firewall blocks port 8000.
- Devices not on same WiFi.
- MQTT credentials missing.
- paho-mqtt not installed.
- data.json corrupted.
- Frontend not refreshing.
- Frontend blank page due to wrong static file path.
