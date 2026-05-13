from __future__ import annotations

import copy
import importlib
import json
import logging
import os
import random
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
FRONTEND_DIR = BASE_DIR.parent / "frontend"
HISTORY_MAX = 30

MODE_LABELS = {
    0: "Manual mode",
    1: "Auto sensor mode",
    2: "Scheduled mode",
}

MODE_RGB = {
    0: "red",
    1: "green",
    2: "yellow",
}

CONTROL_TOPIC_BY_DEVICE = {
    "pump_p10": "V10",
    "pump_p13": "V11",
}

MQTT_TOPICS = ["V1", "V2", "V3", "V4", "V5", "V7", "V10", "V11"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

app = FastAPI(title="Yolo:Farm Local Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_lock = threading.Lock()
state: Dict[str, Any] = {}
mqtt_client: Any = None


class SensorDataPayload(BaseModel):
    temperature: float = Field(..., ge=-50, le=100)
    humidity: float = Field(..., ge=0, le=100)
    soil_moisture: float = Field(..., ge=0, le=100)
    light: float = Field(..., ge=0)


class ControlPayload(BaseModel):
    device: str = Field(..., pattern=r"^(pump_p10|pump_p13)$")
    state: str = Field(..., pattern=r"^(on|off)$")


class ModePayload(BaseModel):
    mode: int = Field(..., ge=0, le=2)


class ThresholdPayload(BaseModel):
    soil_low: float = Field(..., ge=0, le=100)
    soil_high: float = Field(..., ge=0, le=100)
    light_low: float = Field(..., ge=0)
    gdd_light_threshold: float = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_soil_range(self) -> "ThresholdPayload":
        if self.soil_low >= self.soil_high:
            raise ValueError("soil_low must be smaller than soil_high")
        return self


class ScheduleSlotPayload(BaseModel):
    start: int = Field(..., ge=0, le=1440)
    end: int = Field(..., ge=0, le=1440)

    @model_validator(mode="after")
    def validate_slot(self) -> "ScheduleSlotPayload":
        if self.start >= self.end:
            raise ValueError("slot.start must be smaller than slot.end")
        return self


class SchedulePayload(BaseModel):
    enabled: bool
    slots: list[ScheduleSlotPayload]


def default_state() -> Dict[str, Any]:
    return {
        "sensors": {
            "temperature": 0.0,
            "humidity": 0.0,
            "soil_moisture": 0.0,
            "light": 0.0,
            "gdd": 0,
        },
        "devices": {
            "pump_p10": "off",
            "pump_p13": "off",
            "rgb_status": "green",
        },
        "mode": {
            "value": 1,
            "label": "Auto sensor mode",
        },
        "thresholds": {
            "soil_low": 10,
            "soil_high": 20,
            "light_low": 600,
            "gdd_light_threshold": 2000,
        },
        "schedule": {
            "enabled": True,
            "slots": [
                {"start": 480, "end": 495},
                {"start": 720, "end": 730},
                {"start": 1020, "end": 1035},
            ],
        },
        "status": {
            "crop_status": "Chua co du lieu",
            "last_updated": None,
            "connection": "simulation",
        },
        "history": {
            "temperature": [],
            "humidity": [],
            "soil_moisture": [],
            "light": [],
            "gdd": [],
        },
    }


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save_state() -> None:
    DATA_FILE.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def merge_state(current: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(current)
    for key, value in loaded.items():
        if key not in merged:
            continue
        if isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def load_state() -> None:
    global state

    base = default_state()
    if not DATA_FILE.exists():
        state = base
        save_state()
        logging.info("data.json not found. Created new state file.")
        return

    try:
        loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("data.json root must be an object")

        state = merge_state(base, loaded)
        update_mode_metadata()
        update_crop_status()
        save_state()
        logging.info("State loaded from data.json")
    except Exception as err:
        logging.warning("Failed to load data.json (%s). Resetting to default state.", err)
        state = base
        save_state()


def append_history(key: str, value: float | int) -> None:
    history = state["history"].setdefault(key, [])
    history.append(round(float(value), 2) if key != "gdd" else int(value))
    if len(history) > HISTORY_MAX:
        del history[0 : len(history) - HISTORY_MAX]


def update_mode_metadata() -> None:
    mode_value = int(state["mode"].get("value", 1))
    if mode_value not in MODE_LABELS:
        mode_value = 1
    state["mode"]["value"] = mode_value
    state["mode"]["label"] = MODE_LABELS[mode_value]
    state["devices"]["rgb_status"] = MODE_RGB[mode_value]


def update_crop_status() -> None:
    soil = float(state["sensors"].get("soil_moisture", 0))
    thresholds = state["thresholds"]
    if soil < thresholds["soil_low"]:
        state["status"]["crop_status"] = "Dat kho"
    elif soil > thresholds["soil_high"]:
        state["status"]["crop_status"] = "Qua am"
    else:
        state["status"]["crop_status"] = "Binh thuong"


def apply_mode_rules() -> None:
    if state["mode"]["value"] != 1:
        return

    soil = float(state["sensors"]["soil_moisture"])
    thresholds = state["thresholds"]

    # C24: only soil moisture decides pump (ideal range 50-80% for chrysanthemum)
    if soil < thresholds["soil_low"]:
        if state["devices"]["pump_p10"] != "on":
            state["devices"]["pump_p10"] = "on"
            publish_control_placeholder("V10", "1")
            logging.info("[AUTO] pump_p10 -> on (soil=%.2f < soil_low=%.2f)", soil, thresholds["soil_low"])

    if soil > thresholds["soil_high"]:
        if state["devices"]["pump_p10"] != "off":
            state["devices"]["pump_p10"] = "off"
            publish_control_placeholder("V10", "0")
            logging.info("[AUTO] pump_p10 -> off (soil=%.2f > soil_high=%.2f)", soil, thresholds["soil_high"])


def current_minutes_of_day() -> int:
    now = datetime.now()
    return now.hour * 60 + now.minute


def apply_schedule_rules() -> None:
    if state["mode"]["value"] != 2 or not state["schedule"].get("enabled", False):
        return

    minute_now = current_minutes_of_day()
    in_slot = False
    for slot in state["schedule"].get("slots", []):
        if int(slot["start"]) <= minute_now < int(slot["end"]):
            in_slot = True
            break

    new_state = "on" if in_slot else "off"
    if state["devices"]["pump_p13"] != new_state:
        state["devices"]["pump_p13"] = new_state
        publish_control_placeholder("V11", "1" if new_state == "on" else "0")
        logging.info("[SCHEDULE] pump_p13 -> %s at minute=%s", new_state, minute_now)


def apply_sensor_update(payload: SensorDataPayload | Dict[str, float]) -> None:
    values = payload.model_dump() if isinstance(payload, SensorDataPayload) else payload
    for key in ("temperature", "humidity", "soil_moisture", "light"):
        state["sensors"][key] = round(float(values[key]), 2)
        append_history(key, state["sensors"][key])

    if state["sensors"]["light"] >= state["thresholds"]["gdd_light_threshold"]:
        state["sensors"]["gdd"] = int(state["sensors"]["gdd"]) + 1
        append_history("gdd", state["sensors"]["gdd"])

    update_crop_status()
    apply_mode_rules()
    apply_schedule_rules()
    state["status"]["last_updated"] = now_iso()


def get_state_copy() -> Dict[str, Any]:
    return copy.deepcopy(state)


def parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def publish_control_placeholder(topic: str, value: str) -> None:
    global mqtt_client
    if mqtt_client is None:
        logging.info("[SIM] publish placeholder topic=%s value=%s", topic, value)
        return

    try:
        mqtt_client.publish(topic, value)
        logging.info("[MQTT] published topic=%s value=%s", topic, value)
    except Exception as err:
        logging.warning("[MQTT] publish failed for %s: %s", topic, err)


def coerce_mode_value(raw: str) -> Optional[int]:
    if raw not in {"0", "1", "2"}:
        return None
    return int(raw)


def maybe_start_mqtt_bridge() -> None:
    global mqtt_client

    if not parse_bool_env("ENABLE_MQTT", False):
        state["status"]["connection"] = "simulation"
        logging.info("MQTT bridge disabled (ENABLE_MQTT=false)")
        return

    try:
        mqtt = importlib.import_module("paho.mqtt.client")
    except Exception:
        state["status"]["connection"] = "simulation"
        logging.warning("ENABLE_MQTT=true but paho-mqtt is not installed. Running simulation mode.")
        return

    host = os.getenv("OHSTEM_MQTT_HOST", "mqtt.ohstem.vn")
    port = parse_int_env("OHSTEM_MQTT_PORT", 1883)
    username = os.getenv("OHSTEM_MQTT_USERNAME", "")
    password = os.getenv("OHSTEM_MQTT_PASSWORD", "")

    client = mqtt.Client()
    if username:
        client.username_pw_set(username=username, password=password or None)

    def on_connect(client_obj: Any, _: Any, __: Any, rc: int) -> None:
        if rc != 0:
            logging.warning("[MQTT] connect failed rc=%s", rc)
            with state_lock:
                state["status"]["connection"] = "simulation"
                save_state()
            return

        logging.info("[MQTT] connected to %s:%s", host, port)
        for topic in MQTT_TOPICS:
            client_obj.subscribe(topic)
        with state_lock:
            state["status"]["connection"] = "mqtt"
            save_state()

    def on_disconnect(_: Any, __: Any, rc: int) -> None:
        logging.warning("[MQTT] disconnected rc=%s", rc)
        with state_lock:
            state["status"]["connection"] = "simulation"
            save_state()

    def on_message(_: Any, __: Any, msg: Any) -> None:
        topic = str(msg.topic)
        raw = msg.payload.decode("utf-8", errors="ignore").strip()

        with state_lock:
            try:
                if topic == "V1":
                    value = float(raw)
                    state["sensors"]["temperature"] = value
                    append_history("temperature", value)
                elif topic == "V2":
                    value = float(raw)
                    state["sensors"]["humidity"] = value
                    append_history("humidity", value)
                elif topic == "V3":
                    value = float(raw)
                    state["sensors"]["soil_moisture"] = value
                    append_history("soil_moisture", value)
                elif topic == "V4":
                    value = float(raw)
                    state["sensors"]["light"] = value
                    append_history("light", value)
                elif topic == "V5":
                    value = int(float(raw))
                    state["sensors"]["gdd"] = value
                    append_history("gdd", value)
                elif topic == "V7":
                    mode_value = coerce_mode_value(raw)
                    if mode_value is not None:
                        state["mode"]["value"] = mode_value
                        update_mode_metadata()
                elif topic == "V10":
                    state["devices"]["pump_p10"] = "on" if raw == "1" else "off"
                elif topic == "V11":
                    state["devices"]["pump_p13"] = "on" if raw == "1" else "off"

                update_crop_status()
                apply_mode_rules()
                apply_schedule_rules()
                state["status"]["last_updated"] = now_iso()
                save_state()
            except Exception as err:
                logging.warning("[MQTT] failed to process message topic=%s payload=%s err=%s", topic, raw, err)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        client.connect(host, port, keepalive=60)
        client.loop_start()
        mqtt_client = client
    except Exception as err:
        mqtt_client = None
        state["status"]["connection"] = "simulation"
        logging.warning("MQTT bridge failed to start: %s", err)


@app.on_event("startup")
def on_startup() -> None:
    with state_lock:
        load_state()
        maybe_start_mqtt_bridge()
    logging.info("Yolo:Farm local backend started")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "Invalid request payload",
            "details": exc.errors(),
        },
    )


@app.get("/api/health")
def api_health() -> Dict[str, str]:
    return {
        "status": "ok",
        "message": "YoloFarm local server is running",
    }


@app.get("/api/state")
def api_get_state() -> Dict[str, Any]:
    with state_lock:
        return get_state_copy()


@app.get("/api/pump-state")
def api_pump_state() -> Dict[str, Any]:
    """Lightweight endpoint for firmware to sync pump pins and RGB status."""
    with state_lock:
        return {
            "pump_p10": state["devices"]["pump_p10"],
            "pump_p13": state["devices"]["pump_p13"],
            "rgb_status": state["devices"]["rgb_status"],
        }


@app.post("/api/sensor-data")
def api_sensor_data(payload: SensorDataPayload) -> Dict[str, Any]:
    with state_lock:
        apply_sensor_update(payload)
        save_state()
        return get_state_copy()


@app.post("/api/control")
def api_control(payload: ControlPayload) -> Dict[str, Any]:
    with state_lock:
        state["mode"]["value"] = 0
        update_mode_metadata()

        state["devices"][payload.device] = payload.state
        state["status"]["last_updated"] = now_iso()

        topic = CONTROL_TOPIC_BY_DEVICE[payload.device]
        publish_control_placeholder(topic, "1" if payload.state == "on" else "0")

        save_state()
        return get_state_copy()


@app.post("/api/mode")
def api_mode(payload: ModePayload) -> Dict[str, Any]:
    with state_lock:
        # Reset both pumps when switching mode to avoid leftover states
        state["devices"]["pump_p10"] = "off"
        state["devices"]["pump_p13"] = "off"
        publish_control_placeholder("V10", "0")
        publish_control_placeholder("V11", "0")

        state["mode"]["value"] = payload.mode
        update_mode_metadata()
        state["status"]["last_updated"] = now_iso()

        publish_control_placeholder("V7", str(payload.mode))
        if payload.mode == 1:
            apply_mode_rules()
        elif payload.mode == 2:
            apply_schedule_rules()

        save_state()
        return get_state_copy()


@app.post("/api/thresholds")
def api_thresholds(payload: ThresholdPayload) -> Dict[str, Any]:
    with state_lock:
        state["thresholds"] = payload.model_dump()
        update_crop_status()
        apply_mode_rules()
        state["status"]["last_updated"] = now_iso()
        save_state()
        return get_state_copy()


@app.post("/api/schedule")
def api_schedule(payload: SchedulePayload) -> Dict[str, Any]:
    with state_lock:
        slots = [slot.model_dump() for slot in payload.slots]
        state["schedule"] = {
            "enabled": payload.enabled,
            "slots": slots,
        }
        apply_schedule_rules()
        state["status"]["last_updated"] = now_iso()
        save_state()
        return get_state_copy()


@app.post("/api/apply-schedule-now")
def api_apply_schedule_now() -> Dict[str, Any]:
    with state_lock:
        if state["mode"]["value"] == 2 and state["schedule"].get("enabled", False):
            apply_schedule_rules()
            state["status"]["last_updated"] = now_iso()
            save_state()
        return get_state_copy()


@app.post("/api/simulate")
def api_simulate() -> Dict[str, Any]:
    payload = SensorDataPayload(
        temperature=round(random.uniform(25.0, 38.0), 1),
        humidity=round(random.uniform(40.0, 90.0), 1),
        soil_moisture=round(random.uniform(0.0, 100.0), 1),
        light=round(random.uniform(300.0, 5000.0), 1),
    )

    with state_lock:
        apply_sensor_update(payload)
        save_state()
        return get_state_copy()


@app.post("/api/reset")
def api_reset() -> Dict[str, Any]:
    with state_lock:
        global state
        state = default_state()
        save_state()
        return get_state_copy()


if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.get("/")
def root_page() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(index_file)
