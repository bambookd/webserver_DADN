# Old OhStem Step 2 Mapping

Bang mapping cu:

| Old topic / pin | Meaning |
| --- | --- |
| V1 | RT - Temperature from DHT20 |
| V2 | RH - Air humidity from DHT20 |
| V3 | SM - Soil moisture from P1 |
| V4 | LUX - Light from P2 |
| V5 | GDD |
| V7 | MODE control |
| V10 / P10 | Pump control in auto/manual |
| V11 / P13 | Pump/schedule output |
| P0 | RGB LED mode indicator |
| I2C | DHT20 + LCD1602 |

Mode mapping:
- MODE 0 = manual
- MODE 1 = auto sensor mode
- MODE 2 = scheduled mode

RGB mapping:
- MODE 0 => red
- MODE 1 => green
- MODE 2 => yellow

Auto rule (mode 1):
- SM < 45 and LUX < 600 => P10 ON
- SM > 80 => P10 OFF

Schedule rule (mode 2):
- 08:00-08:15
- 12:00-12:10
- 17:00-17:15

Trong local dashboard, mode duoc chon bang 3 nut (khong dung slider).
