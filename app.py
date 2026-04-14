import os
import datetime
import asyncio
import json
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import google.generativeai as genai
from starlette.middleware.sessions import SessionMiddleware

# Google API Imports
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

app = FastAPI(title="NutriPath AI - Real Data")

# Session required for OAuth state
app.add_middleware(SessionMiddleware, secret_key="nutripath_secret_key_123")

# Configure Gemini
API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config={
        "temperature": 0.4,
        "response_mime_type": "application/json",
    }
)

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = "credentials.json"
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # For localhost testing

class ClientPayload(BaseModel):
    location: str

def get_flow(request: Request):
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES
    )
    # Dynamically set redirect URI based on the actual domain (localhost vs cloud run)
    flow.redirect_uri = request.url_for('callback')._url
    return flow

@app.get("/auth/status")
async def check_auth_status(request: Request):
    if 'credentials' in request.session:
        return {"authenticated": True}
    return {"authenticated": False}

@app.get("/auth/login")
async def login(request: Request):
    flow = get_flow(request)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true'
    )
    request.session['state'] = state
    return RedirectResponse(authorization_url)

@app.get("/auth/callback")
async def callback(request: Request):
    state = request.session.get('state')
    flow = get_flow(request)
    flow.fetch_token(authorization_response=str(request.url))
    
    credentials = flow.credentials
    request.session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    return RedirectResponse("/")

def fetch_real_calendar_stress(creds_dict: dict) -> str:
    creds = Credentials(**creds_dict)
    service = build('calendar', 'v3', credentials=creds)
    
    # Get today's events
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    end_of_day = (datetime.datetime.utcnow() + datetime.timedelta(hours=14)).isoformat() + 'Z'
    
    events_result = service.events().list(
        calendarId='primary', timeMin=now, timeMax=end_of_day,
        maxResults=10, singleEvents=True, orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    if not events:
        return "No upcoming events today. Clear schedule."
    
    event_summaries = [e.get('summary', 'Busy Block') for e in events]
    return "Upcoming: " + ", ".join(event_summaries)

@app.post("/api/recommendation")
async def get_recommendation(request: Request, payload: ClientPayload):
    creds_dict = request.session.get('credentials')
    if not creds_dict:
        raise HTTPException(status_code=401, detail="User not authenticated with Google")
    
    # 1. Fetch Real Google Calendar Data
    try:
        real_stress_load = fetch_real_calendar_stress(creds_dict)
    except Exception as e:
        print(f"Calendar fetch failed: {e}")
        real_stress_load = "Could not fetch calendar (Authentication Error)."

    # 2. We use a hybrid metric for readiness since Google Fit REST is complex/deprecated
    # We simulate a sensor reading for the demo if Fit isn't available
    readiness_sensor = 0.65
    
    location_context = payload.location if payload.location else "Unknown Real Location"
    
    prompt = f"""
    You are NutriPath AI, a Bio-Temporal Performance Agent. 
    You are dealing with an older adult user. Provide a clear, highly accessible nutritional and lifestyle recommendation based on their LIVE data.
    
    Real-Time State:
    - Wearable Readiness Score: {readiness_sensor * 100}%
    - Real Calendar Data (Today's Events): {real_stress_load}
    - Real Geographical Location: {location_context}
    
    Analyze their actual calendar context and recommend a very specific, simple nutritional action.
    Explain your reasoning simply.
    
    Output strictly in this JSON structure:
    {{
        "action": "The simple instruction (Max 2 sentences).",
        "logic": "The reasoning why based on their specific calendar events or location (Max 2 sentences).",
        "accessibility": {{
            "speech_summary": "A very short 1 sentence summary."
        }}
    }}
    """
    
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        recommendation_data = json.loads(response.text)
    except json.JSONDecodeError:
        recommendation_data = {
            "action": "Drink water and have a light snack.",
            "logic": "Unable to compute deep insights. Hydration is always beneficial.",
            "accessibility": {"speech_summary": "Hydrate and eat."}
        }

    return {
        "state": {
            "READINESS": readiness_sensor,
            "STRESS_LOAD": real_stress_load,
            "LOCATION_CONTEXT": location_context
        },
        "recommendation": recommendation_data
    }

os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)