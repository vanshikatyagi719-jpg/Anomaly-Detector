import os
import datetime
import json
from groq import Groq
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Configure the Groq client if key is present
if GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here":
    client = Groq(api_key=GROQ_API_KEY)
    LLM_ENABLED = True
    print("[LLM] Groq API connected successfully.")
else:
    client = None
    LLM_ENABLED = False
    print("[LLM] No API key found. Falling back to rule-based recommendations.")


# ----------------------------------------------------------------
# RULE-BASED FALLBACK (used when LLM is not configured)
# ----------------------------------------------------------------
FAULT_BLUEPRINTS = {
    'NORMAL': {
        'title': 'Nominal Operations',
        'category': 'Baseline Normal',
        'severity': 'NOMINAL',
        'confidence': '100%',
        'summary': 'All telemetry arrays are within their designated normal operating range.',
        'actions': ['Continue standard continuous monitoring cycles.'],
        'parts': 'None required.',
        'tools': 'None required.',
        'llm_powered': False
    },
    'BEARING_WEAR': {
        'title': 'Mechanical Bearing Structural Fatigue',
        'category': 'Rotational Mechanical Fatigue',
        'severity': 'CRITICAL',
        'confidence': '96%',
        'summary': 'Vibration spike and thermal rise indicate advanced degradation of the Turbine Shaft Journal Bearing assembly. Consistent with severe friction or lubrication viscosity breakdown.',
        'actions': [
            '⚠️ URGENT: Initiate controlled turbine RPM shutdown sequence.',
            'Perform Lockout-Tagout (LOTO) protocols on the main circuit breaker.',
            'Inspect the bearing race for metal filings, pitting, or discoloration.',
            'Flush old lubrication and inspect casing for structural cracks.'
        ],
        'parts': 'Journal Bearing Assembly (JB-880-XT), High-Temp Lubricant (ISO VG 220).',
        'tools': 'Hydraulic bearing puller, laser alignment tool, torque wrench set.',
        'llm_powered': False
    },
    'COOLANT_LEAK': {
        'title': 'Thermal Overload / Coolant Flow Failure',
        'category': 'Fluid Mechanics & Thermal Overload',
        'severity': 'CRITICAL',
        'confidence': '98%',
        'summary': 'Temperature surge combined with flow rate drop and pressure loss confirms major coolant containment loss or pump mechanical failure.',
        'actions': [
            '⚠️ URGENT: Immediately shut down the turbine and isolate main heaters.',
            'Deploy technician to check for coolant pooling at the secondary heat exchanger.',
            'Inspect coolant pump power feed and pressure-relief valve.',
            'Confirm integrity of inlet/outlet hoses and tighten joint clamps.'
        ],
        'parts': 'EPDM reinforced coolant hoses (2.5"), Solenoid valve (SV-309).',
        'tools': 'Infrared thermal camera, mechanical pressure gauge, hose clamp wrenches.',
        'llm_powered': False
    },
    'PIPE_BLOCKAGE': {
        'title': 'Systemic Fluid Flow Pipe Blockage',
        'category': 'Fluid Hydraulics Blockage',
        'severity': 'WARNING',
        'confidence': '94%',
        'summary': 'Significant pressure spike with flow rate collapse indicates a major downstream blockage. Pump is operating against dangerously high backpressure.',
        'actions': [
            '⚠️ WARNING: Reduce inlet feed pump speed to decrease pipeline pressure.',
            'Inspect inline screen filters (Y-strainer) for particle build-up.',
            'Verify all inline gate valves are fully open.',
            'Conduct acoustic inspection along pipeline joints for cavitation zones.'
        ],
        'parts': 'High-performance mesh strainer basket, EPDM piping seals (4").',
        'tools': 'Ultrasonic flow meter, Y-strainer socket wrench, line flush kit.',
        'llm_powered': False
    }
}


class AgentDiagnosticEngine:

    @staticmethod
    async def get_recommendation(fault_mode: str, readings: dict) -> dict:
        """
        Attempts to generate an LLM-powered recommendation using Groq.
        Falls back to rule-based templates if the API key is not set.
        """
        if LLM_ENABLED and fault_mode != 'NORMAL':
            try:
                return await AgentDiagnosticEngine._call_groq(fault_mode, readings)
            except Exception as e:
                print(f"[LLM] Groq call failed: {e}. Using fallback rules.")
                return AgentDiagnosticEngine._rule_based(fault_mode, readings)
        else:
            return AgentDiagnosticEngine._rule_based(fault_mode, readings)

    @staticmethod
    async def _call_groq(fault_mode: str, readings: dict) -> dict:
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
                {"role": "system", "content": "You are a precise industrial diagnostics agent. Always respond with valid JSON only, no markdown formatting."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        response_text = response.choices[0].message.content.strip()

        # Strip markdown code blocks if the model adds them anyway
        if response_text.startswith("```"):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1])

        rec = json.loads(response_text)
        rec['llm_powered'] = True
        rec['generatedAt'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return rec

    @staticmethod
    def _rule_based(fault_mode: str, readings: dict) -> dict:
        """
        Returns a static rule-based recommendation when Groq is unavailable.
        """
        blueprint = FAULT_BLUEPRINTS.get(fault_mode, FAULT_BLUEPRINTS['NORMAL'])
        result = dict(blueprint)
        result['generatedAt'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        result['summary'] = (
            result['summary'] +
            f" [Live Readings → Temp: {readings.get('temperature')}°C, "
            f"Vib: {readings.get('vibration')} mm/s, "
            f"Pres: {readings.get('pressure')} bar, "
            f"Flow: {readings.get('flowRate')} L/min]"
        )
        return result