from backend.agent_diagnostics import AgentDiagnosticEngine
import asyncio

readings = {
    "temperature": 95,
    "vibration": 4.5,
    "pressure": 18,
    "flowRate": 40
}

result = asyncio.run(
    AgentDiagnosticEngine.get_recommendation(
        "PIPE_BLOCKAGE",
        readings
    )
)

print(result)
