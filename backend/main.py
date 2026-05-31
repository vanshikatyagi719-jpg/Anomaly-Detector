import os
import sys
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
from datetime import datetime

# Add root folder to sys.path so we can import anomaly_detection
anomaly_history = []
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from anomaly_detection import detector
from backend.agent_diagnostics import AgentDiagnosticEngine

app = FastAPI(title="AegisIoT Agentic Monitoring API")
# Enable CORS for local cross-origin connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global State Variables
class OperationalState:
    def __init__(self):
        self.active_fault = "NORMAL"
        self.asset_health = {"bearing": 98.0, "coolant": 94.0, "piping": 97.0}


state = OperationalState()


# WebSocket Client Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(
                f"[WS] Client disconnected. Total active: {len(self.active_connections)}"
            )

    async def broadcast(self, message: str):
        # Broadcast to all connected clients
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Remove dead sockets
                pass


manager = ConnectionManager()


# Data models
class FaultInjection(BaseModel):
    fault_type: str


class DiagnoseRequest(BaseModel):
    temperature: float
    vibration: float
    pressure: float
    flowRate: float


# REST API Endpoint Routes
@app.get("/api/status")
async def get_status():
    return {"active_fault": state.active_fault, "asset_health": state.asset_health}


@app.post("/api/inject-fault")
async def inject_fault(payload: FaultInjection):
    valid_faults = ["NORMAL", "BEARING_WEAR", "COOLANT_LEAK", "PIPE_BLOCKAGE"]
    if payload.fault_type not in valid_faults:
        raise HTTPException(status_code=400, detail="Invalid fault type injected")

    state.active_fault = payload.fault_type
    print(f"[API] Active Failure Mode updated to: {state.active_fault}")
    return {"status": "success", "active_fault": state.active_fault}


@app.post("/api/diagnose")
async def diagnose(payload: DiagnoseRequest):
    readings = {
        "temperature": payload.temperature,
        "vibration": payload.vibration,
        "pressure": payload.pressure,
        "flowRate": payload.flowRate,
    }

    # 1. Run live Machine Learning and Statistical Anomaly Engine
    analytics = detector.score_telemetry(readings)

    # 2. Get LLM (Gemini) or fallback rule-based maintenance recommendation
    recommendation = await AgentDiagnosticEngine.get_recommendation(
        state.active_fault, readings
    )

    return {"analytics": analytics, "recommendation": recommendation}


@app.get("/api/export-dataset")
async def export_dataset():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_path = os.path.join(root_dir, "datasets", "sensor_data.csv")

    # Auto-train / auto-generate if missing
    if not os.path.exists(dataset_path):
        os.makedirs(os.path.dirname(dataset_path), exist_ok=True)
        from datasets.generator import generate_historical_dataset

        generate_historical_dataset(dataset_path, row_count=1000)

    return FileResponse(
        path=dataset_path,
        media_type="text/csv",
        filename="aegisiot_sensor_telemetry_dataset.csv",
    )


@app.get("/api/anomaly-history")
async def get_anomaly_history():
    return anomaly_history[-100:]


# WebSocket streaming gateway endpoint


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Receive data (can be from simulation producer or dashboard ping)
            data_str = await websocket.receive_text()
            data = json.loads(data_str)

            # Check if this is an incoming telemetry stream packet from the simulation
            if "type" in data and data["type"] == "telemetry":
                # Inject the server-side failure state into the packet
                data["payload"]["status"] = state.active_fault

                # Apply degradation logic to health metrics based on active fault
                if state.active_fault == "BEARING_WEAR":
                    state.asset_health["bearing"] = max(
                        22.0, state.asset_health["bearing"] - 0.15
                    )
                elif state.active_fault == "COOLANT_LEAK":
                    state.asset_health["coolant"] = max(
                        12.0, state.asset_health["coolant"] - 0.20
                    )
                elif state.active_fault == "PIPE_BLOCKAGE":
                    state.asset_health["piping"] = max(
                        34.0, state.asset_health["piping"] - 0.12
                    )
                else:
                    # Nominal: Slowly recover health
                    if state.asset_health["bearing"] < 98.0:
                        state.asset_health["bearing"] = min(
                            98.0, state.asset_health["bearing"] + 0.25
                        )
                    if state.asset_health["coolant"] < 94.0:
                        state.asset_health["coolant"] = min(
                            94.0, state.asset_health["coolant"] + 0.25
                        )
                    if state.asset_health["piping"] < 97.0:
                        state.asset_health["piping"] = min(
                            97.0, state.asset_health["piping"] + 0.25
                        )

                # Append live health variables to payload
                data["payload"]["health"] = state.asset_health

                bearing_rul = int(state.asset_health["bearing"] / 2)
                coolant_rul = int(state.asset_health["coolant"] / 2)
                piping_rul = int(state.asset_health["piping"] / 2)

                data["payload"]["predictive_maintenance"] = {
                    "bearing_rul": bearing_rul,
                    "coolant_rul": coolant_rul,
                    "piping_rul": piping_rul,
                }

                # Run the math Z-Score and Isolation Forest anomaly detector on the server!
                # Run anomaly detector
                readings = {
                    "temperature": data["payload"]["readings"]["temperature"],
                    "vibration": data["payload"]["readings"]["vibration"],
                    "pressure": data["payload"]["readings"]["pressure"],
                    "flowRate": data["payload"]["readings"]["flowRate"],
                }

                analytics = detector.score_telemetry(readings)
                print("GLOBAL ANOMALY:", analytics["global_anomaly"])
                print("ML ANOMALY:", analytics["ml_anomaly"])
                print("ALARMS:", analytics["alarms"])

                if analytics["global_anomaly"]:
                    max_z = max(abs(v) for v in analytics["z_scores"].values())

                    if max_z > 5:
                      severity = "CRITICAL"
                    elif max_z > 3:
                      severity = "WARNING"
                    else:
                     severity = "HIGH"
                else:
                        severity = "NORMAL"
                        
                data["payload"]["severity"] = severity
                if analytics["global_anomaly"]:
                    data["payload"]["status"] = "ANOMALY_DETECTED"
                else:
                    data["payload"]["status"] = "NORMAL"
                print("READINGS:", readings)
                print("ANALYTICS:", analytics)

                print("STATUS:", data["payload"]["status"])

                anomaly_type = None

                if analytics["global_anomaly"]:

                    z_scores = analytics["z_scores"]

                    max_sensor = max(z_scores, key=lambda k: abs(z_scores[k]))

                    anomaly_map = {
                        "temperature": "TEMPERATURE_ANOMALY",
                        "vibration": "VIBRATION_ANOMALY",
                        "pressure": "PRESSURE_ANOMALY",
                        "flowRate": "FLOWRATE_ANOMALY",
                    }

                    anomaly_type = anomaly_map[max_sensor]
                    data["payload"]["anomaly_type"] = anomaly_type

                    root_cause = "System operating normally"

                    if anomaly_type == "TEMPERATURE_ANOMALY":
                        root_cause = "Temperature reading is significantly deviating from normal baseline, indicating potential overheating or cooling system failure."
                    elif anomaly_type == "VIBRATION_ANOMALY":
                        root_cause = "Vibration reading is significantly deviating from normal baseline, indicating potential mechanical wear or imbalance."
                    elif anomaly_type == "PRESSURE_ANOMALY":
                        root_cause = "Pressure reading is significantly deviating from normal baseline, indicating potential system malfunction or blockage."
                    elif anomaly_type == "FLOWRATE_ANOMALY":
                        root_cause = "Flow rate reading is significantly deviating from normal baseline, indicating potential system malfunction or blockage."
                    elif anomaly_type == "MULTIVARIATE_ANOMALY":
                        root_cause = "Multiple sensor readings are deviating from normal baselines, indicating potential systemic failure or cascading issues."

                    data["payload"]["root_cause"] = root_cause
                if anomaly_type != None:

                    record = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d   %H:%M:%S"),
                        "anomaly_type": anomaly_type,
                        "temperature": readings["temperature"],
                        "vibration": readings["vibration"],
                        "pressure": readings["pressure"],
                        "flowRate": readings["flowRate"],
                    }

                    anomaly_history.append(record)

                    pd.DataFrame(anomaly_history).to_csv(
                        "datasets/anomaly_history.csv", index=False
                    )

                    print(f"[ALERT] {anomaly_type}")

                # Broadcast live telemetry stream + server-side analytics to all web screens!
                data["payload"]["anomaly_type"] = (
                    anomaly_type if analytics["global_anomaly"] else "NONE"
                )
                print("ANOMALY:", data["payload"]["anomaly_type"])

                data["payload"]["anomaly_history"] = anomaly_history[-10:]
                await manager.broadcast(json.dumps(data))

            # If dashboard sends an API request (e.g. handshake)
            elif "type" in data and data["type"] == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Connection Error: {e}")
        manager.disconnect(websocket)


# Mount Frontend Assets to serve Dashboard directly on root URL
frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"[API] Warning: Frontend directory not found at {frontend_dir}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
