# Yolo:Farm Local Dashboard (OhStem Step 2)

Du an nay la webserver/dashboard local mo rong tu bai Yolo:Farm Step 2 tren app.ohstem.vn.

Muc tieu:
- Chay duoc demo nhanh tren laptop Windows khong can phan cung that.
- Mo rong san de ket noi Yolo:Bit qua HTTP hoac MQTT (tuy chon).
- Giu logic cu theo Step 2: mode 0/1/2, quy tac bom, GDD, lich tuoi.

Luu y quan trong:
- Dashboard khong dung slider mode.
- Dashboard dung 3 nut mode ro rang: Mode 0, Mode 1, Mode 2.

## 1. Cau truc thu muc

```text
web_server/
	backend/
		main.py
		data.json
	firmware/
		old-ohstem-mapping.md
		hardware-test-plan.md
	frontend/
		index.html
		app.js
		style.css
	README.md
```

## 2. Cai dat

Yeu cau Python 3.10+.

```bash
pip install fastapi uvicorn pydantic
```

MQTT la tuy chon:

```bash
pip install paho-mqtt
```

## 3. Chay server

Chay dung nhu sau:

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Mo dashboard:
- http://localhost:8000

Thu LAN:
- http://<LAPTOP_IP>:8000

## 4. Bien moi truong cho MQTT (khong bat buoc)

Khong hardcode secret vao code.

```powershell
$env:ENABLE_MQTT="false"
$env:OHSTEM_MQTT_HOST="mqtt.ohstem.vn"
$env:OHSTEM_MQTT_PORT="1883"
$env:OHSTEM_MQTT_USERNAME=""
$env:OHSTEM_MQTT_PASSWORD=""
```

Neu `ENABLE_MQTT=false`, he thong van chay binh thuong o che do simulation.

## 5. Windows LAN troubleshooting

1. Tim IP laptop bang `ipconfig`.
2. Dam bao laptop, dien thoai, Yolo:Bit cung WiFi.
3. Cho phep Python/Uvicorn qua Windows Firewall.
4. Tu thiet bi khac, dung `http://<LAPTOP_IP>:8000`, khong dung localhost.
5. Neu trang mo len nhung khong cap nhat, mo Browser Console de xem loi JS.

## 6. API chinh

- GET `/api/health`
- GET `/api/state`
- POST `/api/simulate`
- POST `/api/sensor-data`
- POST `/api/control`
- POST `/api/mode`
- POST `/api/thresholds`
- POST `/api/schedule`
- POST `/api/apply-schedule-now`
- POST `/api/reset`

## 7. Test nhanh khong can phan cung

Tao du lieu mo phong:

```bash
curl -X POST http://localhost:8000/api/simulate
```

Gui du lieu cam bien that:

```bash
curl -X POST http://localhost:8000/api/sensor-data \
	-H "Content-Type: application/json" \
	-d "{\"temperature\":27.5,\"humidity\":42,\"soil_moisture\":26,\"light\":3417}"
```

Chuyen mode:

```bash
curl -X POST http://localhost:8000/api/mode \
	-H "Content-Type: application/json" \
	-d "{\"mode\":1}"
```

Bat bom P10:

```bash
curl -X POST http://localhost:8000/api/control \
	-H "Content-Type: application/json" \
	-d "{\"device\":\"pump_p10\",\"state\":\"on\"}"
```

Cap nhat nguong:

```bash
curl -X POST http://localhost:8000/api/thresholds \
	-H "Content-Type: application/json" \
	-d "{\"soil_low\":45,\"soil_high\":80,\"light_low\":600,\"gdd_light_threshold\":2000}"
```

Cap nhat lich:

```bash
curl -X POST http://localhost:8000/api/schedule \
	-H "Content-Type: application/json" \
	-d "{\"enabled\":true,\"slots\":[{\"start\":480,\"end\":495},{\"start\":720,\"end\":730},{\"start\":1020,\"end\":1035}]}"
```

## 8. Checklist demo tren dashboard

1. Mo dashboard.
2. Bam `Simulate Sensor Data`.
3. Kiem tra card: nhiet do, do am, do am dat, anh sang, GDD, tinh trang cay.
4. Kiem tra lich su thay doi du lieu.
5. Chuyen 3 mode bang nut Mode 0/1/2.
6. Kiem tra dieu khien bom P10/P13 (manual se ve Mode 0).
7. Giai thich quy tac Mode 1:
	 - `SM < 45` va `LUX < 600` thi P10 ON
	 - `SM > 80` thi P10 OFF
8. Giai thich quy tac Mode 2 theo khung gio.
9. Giai thich mapping topic V1-V11 theo tai lieu firmware.
10. Xac nhan ro rang: khong co mode slider, chi co 3 nut mode.

## 9. Ghi chu map voi Step 2

- V1: Nhiet do
- V2: Do am khong khi
- V3: Do am dat
- V4: Anh sang
- V5: GDD
- V7: Mode 0/1/2
- V10: Pump P10
- V11: Pump P13

Chi tiet xem them trong `firmware/old-ohstem-mapping.md`.

## 10. Test tu dong localhost (khong can cam mach)

### Cach test bang browser (de dung nhat)

Neu ban muon test tren web app thay vi terminal, dung trang test runner:

1. Chay backend nhu binh thuong.
2. Mo URL:
	- `http://localhost:8000/frontend/test-runner.html`
3. Bam `Run all tests`.
4. Xem bang ket qua PASS/FAIL tung test.

Trang nay se tu goi API local de test:
- health
- reset
- mode 0/1/2 + rgb
- auto rule P10
- manual override mode 0
- simulate + history
- apply schedule

Neu FAIL, cot Detail se hien ly do loi de ban debug nhanh.

---

Da co san script test:
- `scripts/localhost-smoke-test.ps1`

Script se kiem tra tu dong:
1. `/api/health` va trang `/` co song.
2. `/api/reset` dua he thong ve trang thai mac dinh.
3. Mode 0/1/2 doi dung mau RGB.
4. Auto rule mode 1:
	- `SM thap + LUX thap` => P10 ON
	- `SM cao` => P10 OFF
5. Manual control:
	- dieu khien bom thu cong => mode ve 0.
6. Simulate cap nhat history.
7. Validation reject payload sai.

### Cach chay nhanh (khuyen nghi)

Mo PowerShell tai root project va chay:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\localhost-smoke-test.ps1 -AutoStartServer
```

Y nghia:
- `-AutoStartServer`: script tu bat backend, test xong tu tat backend.

### Neu ban da tu chay backend san

1. Chay backend o 1 terminal:

```powershell
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. Chay test o terminal khac:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\localhost-smoke-test.ps1
```

### Doc ket qua

Script in tung dong:
- `[PASS] ...`
- `[FAIL] ...`

Cuoi cung co tong ket:
- `Passed: N`
- `Failed: M`

Neu `Failed > 0`, script tra ve exit code 1.

### Doi host/port neu can

Mac dinh script dung `http://127.0.0.1:8000`.

Neu ban chay cong khac:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\localhost-smoke-test.ps1 -BaseUrl http://127.0.0.1:9000 -AutoStartServer
```
