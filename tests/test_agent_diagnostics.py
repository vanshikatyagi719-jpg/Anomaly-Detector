import backend.agent_diagnostics as ad


def test_rule_based_fallback_unknown_fault():
    readings = {
        "temperature": 60.0,
        "vibration": 2.0,
        "pressure": 40.0,
        "flowRate": 120.0,
    }
    # Call the internal rule-based fallback directly (sync)
    result = ad.AgentDiagnosticEngine._rule_based("UNKNOWN_FAULT", readings)
    assert isinstance(result, dict)
    assert "summary" in result
    assert "generatedAt" in result
    assert "actions" in result


def test_normal_blueprint_present():
    readings = {
        "temperature": 60.0,
        "vibration": 2.0,
        "pressure": 40.0,
        "flowRate": 120.0,
    }
    result = ad.AgentDiagnosticEngine._rule_based("NORMAL", readings)
    assert result.get("title") == "Normal Operation"
    assert result.get("severity") == "INFO"
