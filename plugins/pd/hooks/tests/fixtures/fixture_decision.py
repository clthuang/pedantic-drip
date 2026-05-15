"""Test fixture decision module — minimal allow stub."""


def decide(file_path, tool_name, payload) -> dict:
    """Stub decision: always allow. Used by dispatcher unit tests."""
    return {"permissionDecision": "allow"}
