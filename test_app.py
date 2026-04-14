import pytest
from fastapi.testclient import TestClient
from app import app, get_current_user_creds

# Bypass OAuth locally for testing core endpoints
async def mock_get_current_user_creds():
    return {
        "client_id": "test_id",
        "client_secret": "test_secret",
        "token": "valid_token",
        "refresh_token": "valid_refresh"
    }

app.dependency_overrides[get_current_user_creds] = mock_get_current_user_creds
client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_auth_status_unauthenticated():
    response = client.get("/auth/status")
    assert response.status_code == 200
    assert response.json()["authenticated"] == False

@pytest.mark.asyncio
async def test_get_recommendation_graceful_mock(mocker):
    # Mocking actual Google Calendar Build response to simulate real data without crashing or needing network
    mock_service = mocker.patch("app.build")
    mock_events = mock_service.return_value.events.return_value.list.return_value.execute
    mock_events.return_value = {
        "items": [{"summary": "Test Meeting"}]
    }

    # Mocking Gemini to avoid quota hits
    mock_genai = mocker.patch("app.model.generate_content")
    mock_genai.return_value.text = '{"action": "Drink water", "logic": "Tests fast", "accessibility": {"speech_summary": "Water"}}'

    payload = {"location": "Lat: 10, Lng: 10"}
    response = client.post("/api/recommendation", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "Test Meeting" in data["state"]["STRESS_LOAD"]
    assert data["recommendation"]["action"] == "Drink water"
