from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Simple prototype settings.
AUTO_MODE = True
SOIL_MOISTURE_THRESHOLD = 35.0

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
FRONTEND_DIR = BASE_DIR.parent / "frontend"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

app = FastAPI(title="Smart Farm Local Server", version="1.0.0")

# Allow browser access during LAN/local testing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SensorDataIn(BaseModel):
    temperature: float = Field(..., ge=-50, le=100)
    humidity: float = Field(..., ge=0, le=100)
    soil_moisture: float = Field(..., ge=0, le=100)
    light: float = Field(..., ge=0)


class ControlIn(BaseModel):
    device: str = Field(..., pattern=r"^pump$")
    state: str = Field(..., pattern=r"^(on|off)$")


class AutoModeIn(BaseModel):
    enabled: bool


state: Dict[str, Any] = {
    "latest_sensor_data": {
        "temperature": None,
        "humidity": None,
        "soil_moisture": None,
        "light": None,
    },
    "device_states": {
        "pump": "off",
    },
    "auto_mode": AUTO_MODE,
    "soil_moisture_threshold": SOIL_MOISTURE_THRESHOLD,
}


def save_state() -> None:
    DATA_FILE.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def load_state() -> None:
    if not DATA_FILE.exists():
        save_state()
        return

    try:
        loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            state.update(loaded)
            if "device_states" not in state or not isinstance(state["device_states"], dict):
                state["device_states"] = {"pump": "off"}
            if "latest_sensor_data" not in state or not isinstance(state["latest_sensor_data"], dict):
                state["latest_sensor_data"] = {
                    "temperature": None,
                    "humidity": None,
                    "soil_moisture": None,
                    "light": None,
                }
    except json.JSONDecodeError:
        logging.warning("data.json is corrupted. Recreating a clean state file.")
        save_state()


@app.on_event("startup")
def on_startup() -> None:
    load_state()
    logging.info("Smart Farm backend started.")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "Invalid request payload",
            "details": exc.errors(),
        },
    )


@app.post("/sensor-data")
def receive_sensor_data(payload: SensorDataIn) -> Dict[str, Any]:
    state["latest_sensor_data"] = payload.model_dump()

    # Auto mode: if soil is dry, switch pump on; otherwise off.
    if state.get("auto_mode", True):
        soil = payload.soil_moisture
        new_pump_state = "on" if soil < float(state.get("soil_moisture_threshold", SOIL_MOISTURE_THRESHOLD)) else "off"
        if state["device_states"].get("pump") != new_pump_state:
            logging.info("[AUTO] Pump changed to %s (soil_moisture=%.2f)", new_pump_state, soil)
        state["device_states"]["pump"] = new_pump_state

    save_state()
    logging.info("[SENSOR] %s", payload.model_dump())

    return {
        "message": "Sensor data received",
        "latest": state["latest_sensor_data"],
        "pump": state["device_states"]["pump"],
        "auto_mode": state["auto_mode"],
    }


@app.get("/sensor-data")
def get_latest_sensor_data() -> Dict[str, Any]:
    return {
        "latest": state["latest_sensor_data"],
        "pump": state["device_states"].get("pump", "off"),
        "auto_mode": bool(state.get("auto_mode", True)),
        "soil_moisture_threshold": float(state.get("soil_moisture_threshold", SOIL_MOISTURE_THRESHOLD)),
    }


@app.post("/control")
def control_device(payload: ControlIn) -> Dict[str, Any]:
    if payload.device != "pump":
        raise HTTPException(status_code=400, detail="Only 'pump' device is supported in this prototype")

    state["device_states"]["pump"] = payload.state
    save_state()

    # Simulate forwarding to IoT device.
    logging.info("[CONTROL] Forward command to IoT: device=%s state=%s", payload.device, payload.state)

    return {
        "message": "Control command accepted",
        "device": payload.device,
        "state": payload.state,
    }


@app.post("/auto-mode")
def set_auto_mode(payload: AutoModeIn) -> Dict[str, Any]:
    state["auto_mode"] = payload.enabled
    save_state()
    logging.info("[CONFIG] AUTO_MODE set to %s", payload.enabled)

    return {
        "message": "Auto mode updated",
        "auto_mode": state["auto_mode"],
    }


@app.get("/status")
def get_status() -> Dict[str, Any]:
    return {
        "pump": state["device_states"].get("pump", "off"),
        "auto_mode": bool(state.get("auto_mode", True)),
        "soil_moisture_threshold": float(state.get("soil_moisture_threshold", SOIL_MOISTURE_THRESHOLD)),
    }


if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.get("/")
def serve_index() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(index_file)
