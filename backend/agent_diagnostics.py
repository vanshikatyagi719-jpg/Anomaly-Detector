import os
import datetime
from groq import Groq
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Configure the Gemini client if key is present
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)
    LLM_ENABLED = True
    print("[LLM] GROQ API key found. LLM-powered recommendations enabled.")
else:
    LLM_ENABLED = False
    print("[LLM] No API key found. Falling back to rule-based recommendations.")


# ----------------------------------------------------------------
# RULE-BASED FALLBACK (used when LLM is not configured)
# ----------------------------------------------------------------
FAULT_BLUEPRINTS = {
    "NORMAL": {
        "title": "Normal Operation",
        "category": "No Fault Detected",
        "severity": "INFO",
        "confidence": "100%",
        "summary": "System operating within normal parameters.",
        "actions": ["No action required."],
        "parts": "N/A",
        "tools": "N/A",
        "llm_powered": False,
    },
    "PRESSURE_ANOMALY": {
        "title": "Pressure System Instability",
        "category": "Hydraulic Pressure Failure",
        "severity": "HIGH",
        "confidence": "95%",
        "summary": "Abnormal pressure detected indicating possible blockage, leakage, or valve malfunction.",
        "actions": [
            "Inspect pressure relief valves.",
            "Check hydraulic lines for leaks.",
            "Verify pressure sensor calibration.",
            "Inspect downstream flow restrictions.",
        ],
        "parts": "Pressure relief valve, pressure sensor.",
        "tools": "Pressure gauge, calibration kit.",
        "llm_powered": False,
    },
    "TEMPERATURE_ANOMALY": {
        "title": "Thermal Overload Condition",
        "category": "Heat Management Failure",
        "severity": "HIGH",
        "confidence": "94%",
        "summary": "Abnormal temperature rise detected indicating overheating or cooling inefficiency.",
        "actions": [
            "Inspect cooling system.",
            "Check coolant circulation.",
            "Inspect heat exchanger.",
            "Verify temperature sensor calibration.",
        ],
        "parts": "Coolant pump, thermal sensor.",
        "tools": "Thermal camera, thermometer.",
        "llm_powered": False,
    },
    "VIBRATION_ANOMALY": {
        "title": "Mechanical Vibration Anomaly",
        "category": "Rotating Equipment Failure",
        "severity": "CRITICAL",
        "confidence": "96%",
        "summary": "Excessive vibration detected indicating bearing wear, shaft imbalance, or misalignment.",
        "actions": [
            "Inspect bearings.",
            "Check shaft alignment.",
            "Verify lubrication levels.",
            "Perform vibration spectrum analysis.",
        ],
        "parts": "Bearing assembly.",
        "tools": "Vibration analyzer.",
        "llm_powered": False,
    },
    "FLOWRATE_ANOMALY": {
        "title": "Flow Restriction Detected",
        "category": "Fluid Transport Failure",
        "severity": "WARNING",
        "confidence": "93%",
        "summary": "Abnormal flow rate detected indicating blockage, leakage, or pump degradation.",
        "actions": [
            "Inspect pipeline blockages.",
            "Check pump performance.",
            "Inspect valves.",
            "Verify flow meter calibration.",
        ],
        "parts": "Flow sensor, pipeline seals.",
        "tools": "Flow meter.",
        "llm_powered": False,
    },
    "MULTIVARIATE_ANOMALY": {
        "title": "System-Wide Operational Deviation",
        "category": "Multi-Sensor Failure",
        "severity": "CRITICAL",
        "confidence": "90%",
        "summary": "Multiple telemetry variables indicate abnormal machine behavior.",
        "actions": [
            "Perform complete diagnostic inspection.",
            "Review maintenance history.",
            "Inspect all critical subsystems.",
            "Escalate to maintenance team.",
        ],
        "parts": "To be determined.",
        "tools": "Full diagnostic toolkit.",
        "llm_powered": False,
    },
}


class AgentDiagnosticEngine:

    @staticmethod
    async def get_recommendation(fault_mode: str, readings: dict) -> dict:
        """
        Attempts to generate an LLM-powered recommendation using openrouter.
        Falls back to rule-based templates if the API key is not set.
        """
        if LLM_ENABLED and fault_mode != "NORMAL":
            try:
                return await AgentDiagnosticEngine._call_llm(fault_mode, readings)
            except Exception as e:
                print(f"[LLM] Groq call failed: {e}. Using fallback rules.")
                return AgentDiagnosticEngine._rule_based(fault_mode, readings)
        else:
            return AgentDiagnosticEngine._rule_based(fault_mode, readings)

    @staticmethod
    async def _call_llm(fault_mode: str, readings: dict) -> dict:
        """
        Calls the Groq API with a rich industrial context prompt
        and returns a structured, dynamic maintenance recommendation.
        """
        prompt = f"""
You are an expert industrial machinery maintenance engineer and AI diagnostics agent.

A factory turbine system has triggered a critical fault alert with the following live sensor readings:

Fault Type: {fault_mode.replace('_', ' ')}
Temperature: {readings['temperature']}°C  (Normal baseline: ~60°C)
Vibration: {readings['vibration']} mm/s  (Normal baseline: ~2.0 mm/s)
Pressure: {readings['pressure']} bar     (Normal baseline: ~40 bar)
Flow Rate: {readings['flowRate']} L/min  (Normal baseline: ~120 L/min)

Based on this data, respond in this EXACT JSON format and nothing else:
{{
  "title": "Short name of the mechanical fault",
  "category": "Engineering classification of the failure type",
  "severity": "CRITICAL or WARNING",
  "confidence": "Percentage string like 97%",
  "summary": "2-3 sentence root-cause analysis explaining what is happening physically inside the machine and why these exact sensor values confirm it",
  "actions": [
    "Step 1 action with specific technical detail",
    "Step 2 action with specific technical detail",
    "Step 3 action",
    "Step 4 action"
  ],
  "parts": "Specific replacement parts with model numbers if applicable",
  "tools": "Specific tools required for repair"
}}

Be precise, technical, and specific to the exact sensor values provided. Reference the actual readings in your summary.
"""
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": "You must respond ONLY with valid JSON. No markdown. No explanations.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )

        response_text = response.choices[0].message.content

        # Strip markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        import json

        rec = json.loads(response_text)
        rec["llm_powered"] = True
        rec["generatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return rec

    @staticmethod
    def _rule_based(fault_mode: str, readings: dict) -> dict:
        """
        Returns a static rule-based recommendation when Gemini is unavailable.
        """
        # Use a sensible fallback if the specific fault blueprint is not defined
        blueprint = FAULT_BLUEPRINTS.get(
            fault_mode, FAULT_BLUEPRINTS.get("MULTIVARIATE_ANOMALY")
        )
        result = dict(blueprint)
        result["generatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Dynamically inject real readings into summary
        # Safely append live readings to the summary
        live_readings = (
            f" [Live Readings → Temp: {readings.get('temperature')}°C, "
            f"Vib: {readings.get('vibration')} mm/s, "
            f"Pres: {readings.get('pressure')} bar, "
            f"Flow: {readings.get('flowRate')} L/min]"
        )
        result["summary"] = (result.get("summary", "") + live_readings).strip()
        return result
