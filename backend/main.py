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


# Alert escalation helper
def get_escalation_action(severity: str, anomaly_type: str) -> dict:
    s = (severity or "NORMAL").upper()
    if s == "NORMAL":
        return {
            "level": "NORMAL",
            "action": "Monitor and log; no immediate action required.",
            "team": "Operations",
            "response_time": "N/A",
        }
    if s == "WARNING":
        return {
            "level": "WARNING",
            "action": "Notify maintenance team and schedule inspection.",
            "team": "Maintenance",
            "response_time": "4 hours",
        }
    if s == "HIGH":
        return {
            "level": "HIGH",
            "action": "Immediate engineer inspection recommended.",
            "team": "Engineering",
            "response_time": "1 hour",
        }
    if s == "CRITICAL":
        return {
            "level": "CRITICAL",
            "action": "Recommend emergency shutdown and dispatch emergency response.",
            "team": "Emergency Response",
            "response_time": "Immediate",
        }
    # default fallback
    return {
        "level": "NORMAL",
        "action": "Monitor and log; no immediate action required.",
        "team": "Operations",
        "response_time": "N/A",
    }


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
        self.current_system_state = "NORMAL"
        self.previous_system_state = "NORMAL"
        self.anomaly_count = 0
        self.normal_count = 0
        self.last_observed_anomaly_type = "NONE"
        self.persisted_anomaly_type = "NONE"
        self.current_severity = "NORMAL"
        self.last_recommendation = None
        self.last_root_cause = "System operating normally."
        self.last_explainability = {}

    def update_persistence(
        self, raw_anomaly: bool, raw_severity: str, anomaly_type: str = None
    ):
        prev_state = self.current_system_state

        if raw_anomaly:
            self.anomaly_count += 1
            self.normal_count = 0
            if anomaly_type:
                self.last_observed_anomaly_type = anomaly_type
            if raw_severity and raw_severity != "NORMAL":
                self.current_severity = raw_severity
        else:
            self.normal_count += 1
            self.anomaly_count = 0

        if self.current_system_state == "NORMAL" and self.anomaly_count >= 3:
            self.previous_system_state = prev_state
            self.current_system_state = "ANOMALY_DETECTED"
            self.persisted_anomaly_type = (
                self.last_observed_anomaly_type or "MULTIVARIATE_ANOMALY"
            )
            if self.current_severity == "NORMAL" and raw_severity != "NORMAL":
                self.current_severity = raw_severity
        elif self.current_system_state == "ANOMALY_DETECTED" and self.normal_count >= 5:
            self.previous_system_state = prev_state
            self.current_system_state = "NORMAL"
            self.persisted_anomaly_type = "NONE"
            self.current_severity = "NORMAL"
            self.last_recommendation = None
            self.last_root_cause = "System operating normally."
            self.last_explainability = {}

        if prev_state != self.current_system_state:
            print(
                f"[STATE TRANSITION] previous_state={prev_state} new_state={self.current_system_state} "
                f"anomaly_count={self.anomaly_count} normal_count={self.normal_count} "
                f"persisted_anomaly_type={self.persisted_anomaly_type} severity={self.current_severity}"
            )

        return self.current_system_state


state = OperationalState()

# Repository root (used for safe absolute file paths)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
        # Broadcast to all connected clients. Remove any dead sockets.
        to_remove = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                # Mark dead sockets for removal and log the error
                print(f"[WS] Broadcast error, removing connection: {e}")
                to_remove.append(connection)

        for conn in to_remove:
            self.disconnect(conn)


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
    global anomaly_history
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
                        22.0, min(100, state.asset_health["bearing"] - 0.15)
                    )
                elif state.active_fault == "COOLANT_LEAK":
                    state.asset_health["coolant"] = max(
                        12.0, min(100, state.asset_health["coolant"] - 0.20)
                    )
                elif state.active_fault == "PIPE_BLOCKAGE":
                    state.asset_health["piping"] = max(
                        34.0, min(100, state.asset_health["piping"] - 0.12)
                    )
                else:
                    # Nominal: Slowly recover health (with proper bounds)
                    if state.asset_health["bearing"] < 98.0:
                        state.asset_health["bearing"] = min(
                            98.0, max(0, state.asset_health["bearing"] + 0.25)
                        )
                    if state.asset_health["coolant"] < 94.0:
                        state.asset_health["coolant"] = min(
                            94.0, max(0, state.asset_health["coolant"] + 0.25)
                        )
                    if state.asset_health["piping"] < 97.0:
                        state.asset_health["piping"] = min(
                            97.0, max(0, state.asset_health["piping"] + 0.25)
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
                readings = {
                    "temperature": data["payload"]["readings"]["temperature"],
                    "vibration": data["payload"]["readings"]["vibration"],
                    "pressure": data["payload"]["readings"]["pressure"],
                    "flowRate": data["payload"]["readings"]["flowRate"],
                }

                analytics = detector.score_telemetry(readings)
                data["payload"]["analytics"] = analytics
                print("GLOBAL ANOMALY:", analytics["global_anomaly"])
                print("ML ANOMALY:", analytics["ml_anomaly"])
                print("ALARMS:", analytics["alarms"])

                raw_anomaly = analytics["global_anomaly"]
                raw_anomaly_type = "MULTIVARIATE_ANOMALY"  # Guaranteed default
                raw_severity = "NORMAL"
                max_z = 0
                if raw_anomaly:
                    z_scores = analytics.get("z_scores", {}) or {}
                    max_z = max(abs(v) for v in z_scores.values()) if z_scores else 0
                    if max_z > 5:
                        raw_severity = "CRITICAL"
                    elif max_z > 3:
                        raw_severity = "HIGH"
                    elif max_z > 2.5:
                        raw_severity = "WARNING"

                    significant = {k: v for k, v in z_scores.items() if abs(v) > 2.5}
                    anomaly_map = {
                        "temperature": "TEMPERATURE_ANOMALY",
                        "vibration": "VIBRATION_ANOMALY",
                        "pressure": "PRESSURE_ANOMALY",
                        "flowRate": "FLOWRATE_ANOMALY",
                    }
                    if significant:
                        max_sensor = max(significant, key=lambda k: abs(significant[k]))
                        raw_anomaly_type = anomaly_map.get(
                            max_sensor, "MULTIVARIATE_ANOMALY"
                        )

                confidence_pct = (
                    min(99, max(65, 70 + int(max_z * 3))) if raw_anomaly else 95
                )
                # Ensure z_scores always exists and has valid values
                z_scores_payload = analytics.get("z_scores", {})
                if not z_scores_payload or not isinstance(z_scores_payload, dict):
                    z_scores_payload = {
                        "temperature": 0,
                        "vibration": 0,
                        "pressure": 0,
                        "flowRate": 0,
                    }

                explainability = {
                    "z_scores": z_scores_payload,
                    "ml_anomaly": analytics.get("ml_anomaly", False),
                    "confidence_pct": f"{confidence_pct}%",
                    "isolation_label": (
                        "Isolation Forest detected"
                        if analytics.get("ml_anomaly")
                        else "No isolation point detected"
                    ),
                }

                state.update_persistence(raw_anomaly, raw_severity, raw_anomaly_type)
                data["payload"]["severity"] = state.current_severity
                data["payload"]["status"] = state.current_system_state
                data["payload"]["current_system_state"] = state.current_system_state
                data["payload"]["previous_state"] = state.previous_system_state
                data["payload"]["anomaly_count"] = state.anomaly_count
                data["payload"]["normal_count"] = state.normal_count
                data["payload"]["active_fault"] = state.active_fault
                data["payload"]["explainability"] = explainability

                if state.current_system_state == "ANOMALY_DETECTED":
                    data["payload"]["anomaly_type"] = (
                        state.persisted_anomaly_type or "MULTIVARIATE_ANOMALY"
                    )
                    data["payload"]["anomaly_detection_mode"] = "PERSISTED"
                elif raw_anomaly:
                    # Show detected anomaly even if not yet persisted (raw detection)
                    data["payload"]["anomaly_type"] = (
                        raw_anomaly_type or "MULTIVARIATE_ANOMALY"
                    )
                    data["payload"]["anomaly_detection_mode"] = "DETECTED_RAW"
                else:
                    data["payload"]["anomaly_type"] = "NONE"
                    data["payload"]["anomaly_detection_mode"] = "NORMAL"

                effective_anomaly_type = None
                if state.current_system_state == "ANOMALY_DETECTED":
                    effective_anomaly_type = state.persisted_anomaly_type
                elif raw_anomaly:
                    effective_anomaly_type = raw_anomaly_type

                # ==================== DEBUGGING LOGS ====================
                print(f"[ANOMALY PIPELINE] Current State: {state.current_system_state}")
                print(
                    f"[ANOMALY PIPELINE] Persisted Type: {state.persisted_anomaly_type}"
                )
                print(
                    f"[ANOMALY PIPELINE] Raw Anomaly: {raw_anomaly}, Raw Type: {raw_anomaly_type}"
                )
                print(f"[ANOMALY PIPELINE] Effective Type: {effective_anomaly_type}")
                print(
                    f"[ANOMALY PIPELINE] Payload Anomaly Type: {data['payload']['anomaly_type']}"
                )
                print(
                    f"[ANOMALY PIPELINE] Detection Mode: {data['payload'].get('anomaly_detection_mode')}"
                )

                if effective_anomaly_type:
                    if raw_anomaly or not state.last_recommendation:
                        state.last_recommendation = (
                            await AgentDiagnosticEngine.get_recommendation(
                                effective_anomaly_type, readings
                            )
                        )
                    recommendation = state.last_recommendation
                    root_cause = "System operating normally."

                    if effective_anomaly_type == "TEMPERATURE_ANOMALY":
                        root_cause = "Temperature is deviating beyond expected bounds, indicating potential overheating or cooling failure."
                    elif effective_anomaly_type == "VIBRATION_ANOMALY":
                        root_cause = "Vibration levels are outside safe operating limits, indicating possible bearing wear or mechanical imbalance."
                    elif effective_anomaly_type == "PRESSURE_ANOMALY":
                        root_cause = "Pressure readings are abnormal, indicating possible blockage, leak, or valve malfunction."
                    elif effective_anomaly_type == "FLOWRATE_ANOMALY":
                        root_cause = "Flow rate measures outside expected thresholds, indicating flow restriction or pump degradation."
                    elif effective_anomaly_type == "MULTIVARIATE_ANOMALY":
                        root_cause = "Multiple telemetry signals are in abnormal states, indicating a systemic deviation across the asset."

                    state.last_root_cause = root_cause
                    state.last_explainability = explainability
                    data["payload"]["recommendation"] = recommendation
                    data["payload"]["root_cause"] = root_cause
                else:
                    data["payload"]["recommendation"] = (
                        await AgentDiagnosticEngine.get_recommendation(
                            "NORMAL", readings
                        )
                    )
                    data["payload"]["root_cause"] = "System operating normally."
                    state.last_root_cause = data["payload"]["root_cause"]
                    state.last_explainability = explainability

                if raw_anomaly and effective_anomaly_type:
                    record = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "anomaly_type": effective_anomaly_type,
                        "severity": state.current_severity,
                        "root_cause": data["payload"].get("root_cause", "Unknown"),
                        "recommendation": data["payload"].get("recommendation", "N/A"),
                        "temperature": readings["temperature"],
                        "vibration": readings["vibration"],
                        "pressure": readings["pressure"],
                        "flowRate": readings["flowRate"],
                    }
                    anomaly_history.append(record)
                    # Prevent memory leak: maintain circular buffer max 1000 records
                    if len(anomaly_history) > 1000:
                        anomaly_history = anomaly_history[-1000:]
                    os.makedirs(os.path.join(ROOT_DIR, "datasets"), exist_ok=True)
                    pd.DataFrame(anomaly_history).to_csv(
                        os.path.join(ROOT_DIR, "datasets", "anomaly_history.csv"),
                        index=False,
                    )
                    print(f"[ALERT] {effective_anomaly_type}")

                data["payload"]["anomaly_history"] = anomaly_history[-10:]
                if data["payload"]["anomaly_history"]:
                    try:
                        data["payload"]["anomaly_history"][-1]["escalation"] = (
                            get_escalation_action(
                                data["payload"].get("severity"),
                                data["payload"].get("anomaly_type"),
                            )
                        )
                    except Exception:
                        pass

                escalation = get_escalation_action(
                    data["payload"].get("severity"), data["payload"].get("anomaly_type")
                )
                data["payload"]["escalation"] = escalation

                # Emit clear broadcast-level logs to help frontend sync issues
                print(
                    f"[BROADCAST] anomaly_type={data['payload']['anomaly_type']} severity={data['payload'].get('severity')} escalation={escalation.get('level')} recommendation_present={'yes' if data['payload'].get('recommendation') else 'no'}"
                )

                # Ensure anomaly_history items include escalation summary for the feed
                data["payload"]["anomaly_history"] = anomaly_history[-10:]
                # attach escalation to most recent history item if exists
                if data["payload"]["anomaly_history"]:
                    try:
                        data["payload"]["anomaly_history"][-1][
                            "escalation"
                        ] = escalation
                    except Exception:
                        pass

                # Validate critical payload fields before broadcast
                if "anomaly_type" not in data.get("payload", {}):
                    data["payload"]["anomaly_type"] = "NONE"
                if "severity" not in data.get("payload", {}):
                    data["payload"]["severity"] = "NORMAL"
                if "anomaly_detection_mode" not in data.get("payload", {}):
                    data["payload"]["anomaly_detection_mode"] = "NORMAL"
                if "explainability" not in data.get("payload", {}):
                    data["payload"]["explainability"] = {
                        "z_scores": {},
                        "ml_anomaly": False,
                        "confidence_pct": "80%",
                        "isolation_label": "--",
                    }

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
