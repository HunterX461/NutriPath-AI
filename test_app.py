from fastapi.testclient import TestClient
from app import app, generate_mock_state
import json
from httpx import Response

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_generate_mock_state():
    state = generate_mock_state()
    assert 0.0 <= state.READINESS <= 1.0
    assert isinstance(state.STRESS_LOAD, str)
    assert isinstance(state.LOCATION_CONTEXT, str)

# We won't test the live Gemini API endpoint by default in strict CI 
# to avoid hitting quotas, but we can do a mock patch or test the fallback.
# For now, let's just test that the health/status is good.
