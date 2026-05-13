# pyright: reportMissingImports=false, reportUndefinedVariable=false
from yolobit import *
import time
import ujson
_rgb_strip = None  # WS2812 neopixel unavailable: RMT channels used by LED matrix

# MQTT helper from OhStem firmware (used for WiFi connection).
try:
    from mqtt import *
except Exception:
    mqtt = None

try:
    import network
except Exception:
    network = None

# Optional imports. If a sensor module is missing on the board,
# the script will fall back to simple simulated values.
try:
    from homebit3_dht20 import DHT20
except Exception:
    DHT20 = None

try:
    import urequests as requests
except Exception:
    requests = None

try:
    from homebit3_lcd1602 import LCD1602
except Exception:
    LCD1602 = None

# ---------------------------
# CONFIG: fill these at school
# ---------------------------
WIFI_SSID = "HCMUT-MEETING"
WIFI_PASSWORD = "hcmut@meeting"
SERVER_BASE_URL = "http://10.127.15.143:8000"
POST_PATH = "/api/sensor-data"
SEND_INTERVAL_SECONDS = 10

# Soil and light thresholds are only for quick local relay behavior display.
SOIL_LOW = 45
SOIL_HIGH = 80
LIGHT_LOW = 600

# Optional: relay output pins based on old Step 2 mapping.
PUMP_P10 = pin10
PUMP_P13 = pin13
lcd = None


def clamp(value, low, high):
    return max(low, min(high, value))


def read_temperature_humidity(dht):
    if dht is None:
        # Fallback values for board-only test
        t = 28 + (time.ticks_ms() % 50) / 10
        h = 55 + (time.ticks_ms() % 100) / 20
        return round(t, 1), round(clamp(h, 0, 100), 1)

    try:
        dht.read_dht20()
        t = dht.dht20_temperature()
        h = dht.dht20_humidity()
        return round(float(t), 1), round(float(h), 1)
    except Exception:
        return 28.0, 55.0


def read_soil_moisture_percent():
    # Old mapping: analog P1 from 0..4096 mapped to 0..100
    raw = pin1.read_analog()
    value = (raw / 4096.0) * 100.0
    return round(clamp(value, 0, 100), 1)


def read_light():
    raw = pin2.read_analog()
    return round(float(max(0, raw)), 1)


def update_local_relays(soil, light):
    # Local mirror of mode-1 style behavior for visible hardware check.
    if soil < SOIL_LOW and light < LIGHT_LOW:
        PUMP_P10.write_digital(1)
    if soil > SOIL_HIGH:
        PUMP_P10.write_digital(0)


def connect_wifi():
    if "<ip_laptop>" in SERVER_BASE_URL.lower() or "YOUR_" in WIFI_SSID:
        print("Please update WIFI_SSID/WIFI_PASSWORD/SERVER_BASE_URL before flashing.")
        display.scroll("Config?")
        return False

    display.scroll("WiFi")
    if mqtt is not None:
        try:
            mqtt.connect_wifi(WIFI_SSID, WIFI_PASSWORD)
            display.scroll("WiFi OK")
            return True
        except Exception as err:
            print("mqtt.connect_wifi failed:", err)

    # Fallback for firmware builds without mqtt helper.
    if network is not None:
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            if not wlan.isconnected():
                wlan.connect(WIFI_SSID, WIFI_PASSWORD)
                for _ in range(30):
                    if wlan.isconnected():
                        break
                    time.sleep(1)

            if wlan.isconnected():
                print("WiFi connected:", wlan.ifconfig())
                display.scroll("WiFi OK")
                return True
        except Exception as err:
            print("network WiFi failed:", err)

    print("WiFi connect failed")
    display.scroll("WiFi ERR")
    return False


def update_lcd(temperature, humidity, soil_moisture, light, post_ok):
    if lcd is None:
        return

    try:
        lcd.move_to(0, 0)
        line1 = "RT:{:.1f} RH:{:.1f}".format(temperature, humidity)
        lcd.putstr((line1 + " " * 16)[:16])

        lcd.move_to(0, 1)
        status = "OK" if post_ok else "ER"
        line2 = "L:{:4.0f} S:{:3.0f}{}".format(light, soil_moisture, status)
        lcd.putstr((line2 + " " * 16)[:16])
    except Exception as err:
        print("LCD update failed:", err)


def post_sensor_data(payload):
    if requests is None:
        print("requests module missing. Install firmware with urequests support.")
        return False

    url = SERVER_BASE_URL.rstrip("/") + POST_PATH
    resp = None
    try:
        resp = requests.post(url, json=payload)
        ok = 200 <= int(resp.status_code) < 300
        text = "OK" if ok else "ERR"
        print("POST", url, "status", resp.status_code, text)
        return ok
    except Exception as err:
        print("POST failed:", err)
        return False
    finally:
        try:
            if resp is not None:
                resp.close()
        except Exception:
            pass


RGB_COLOR_MAP = {
    "red":    "#ff0000",
    "green":  "#00ff00",
    "yellow": "#ffff00",
}

RGB_TUPLE_MAP = {
    "red":    (255, 0, 0),
    "green":  (0, 255, 0),
    "yellow": (255, 200, 0),
}

def set_rgb_strip(color_name):
    if _rgb_strip is None:
        return
    try:
        rgb = RGB_TUPLE_MAP.get(color_name, (0, 255, 0))
        for i in range(len(_rgb_strip)):
            _rgb_strip[i] = rgb
        _rgb_strip.write()
    except Exception as e:
        print("RGB strip failed:", e)

def sync_pump_from_server():
    """GET /api/pump-state and sync pump pins + RGB LED from server state."""
    if requests is None:
        return
    url = SERVER_BASE_URL.rstrip("/") + "/api/pump-state"
    resp = None
    try:
        resp = requests.get(url)
        if 200 <= int(resp.status_code) < 300:
            data = ujson.loads(resp.text)
            p10 = data.get("pump_p10", "off")
            p13 = data.get("pump_p13", "off")
            rgb = data.get("rgb_status", "green")
            try:
                PUMP_P10.write_digital(1 if p10 == "on" else 0)
            except Exception as e:
                print("P10 write failed:", e)
            # P13 is a JTAG pin on this ESP32 — write_digital causes hard fault, skip it
            print("P13 state (not written):", p13)
            color_hex = RGB_COLOR_MAP.get(rgb, "#00ff00")
            display.set_all(color_hex)
            set_rgb_strip(rgb)
            print("PUMP_P10 ->", p10, "PUMP_P13 ->", p13, "RGB ->", rgb)
    except Exception as err:
        print("sync_pump failed:", err)
    finally:
        try:
            if resp is not None:
                resp.close()
        except Exception:
            pass


def main():
    global lcd

    dht = DHT20() if DHT20 is not None else None
    lcd = LCD1602() if LCD1602 is not None else None
    if lcd is not None:
        try:
            lcd.clear()
            lcd.move_to(0, 0)
            lcd.putstr("Booting...")
        except Exception:
            pass

    wifi_ok = connect_wifi()
    if not wifi_ok:
        display.set_all("#ff0000")
        # Keep board alive for debugging, but do not spam requests.
        while True:
            time.sleep(1)

    while True:
        temperature, humidity = read_temperature_humidity(dht)
        soil_moisture = read_soil_moisture_percent()
        light = read_light()

        payload = {
            "temperature": temperature,
            "humidity": humidity,
            "soil_moisture": soil_moisture,
            "light": light,
        }

        print("payload:", payload)
        ok = post_sensor_data(payload)

        # Sync pump + RGB LED with server state
        if ok:
            sync_pump_from_server()
        else:
            display.set_all("#ff0000")  # red = POST failed

        update_lcd(temperature, humidity, soil_moisture, light, ok)
        update_local_relays(soil_moisture, light)
        time.sleep(SEND_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
