# API Contract & Integration Notes

This document ground-truths the actual backend schemas and integration requirements based on `openapi.json` and the FastAPI source code. Do not assume any functionality not explicitly defined here.

## 1. Endpoints & Schemas

### POST `/auth/login`
- **Request Body**: `{"username": "<string>", "password": "<string>"}`
- **Response**: 
  ```json
  {
    "access_token": "string (the JWT)",
    "token_type": "bearer",
    "role": "string",
    "username": "string"
  }
  ```
- **Notes**: Expiry is NOT returned inline (it is embedded in the JWT `exp` claim). User info (role, username) DOES come back inline with the token.

### GET `/auth/me`
- **Auth**: `Authorization: Bearer <token>`
- **Response**:
  ```json
  {
    "id": 0,
    "username": "string",
    "role": "string"
  }
  ```

### GET / POST / PATCH / DELETE `/cameras`
- **Camera Object Shape**:
  ```json
  {
    "id": 0,
    "name": "string",
    "source_uri": "string",
    "status": "string",
    "created_at": "2023-10-01T12:00:00Z (or null)"
  }
  ```
- **Valid Status Strings**: The exact valid values defined by the backend state machine are `"unknown"`, `"active"`, and `"offline"`. These are all lowercase. Use these exactly for UI status badges. Note: There is no "location" field on the camera object.

### Camera Pipeline Operations
- **POST `/cameras/{id}/start`**: Returns `{"camera_id": 0, "status": "active"}`.
- **POST `/cameras/{id}/stop`**: Returns `{"camera_id": 0, "status": "offline"}`.
- **GET `/cameras/{id}/status`**: Returns `{"camera_id": 0, "state": "string", "pipeline": true/false}`.

### GET `/cameras/{id}/observations`
- **Query Params**: `limit` (int, default 50), `event_type` (str, optional)
- **Observation Object Shape**:
  ```json
  {
    "id": 0,
    "track_id": 0,
    "event_type": "string",
    "timestamp": "2023-10-01T12:00:00Z",
    "zone_id": "string",
    "confidence_score": 0.0,
    "impact_score": 0.0,
    "explanation": "string"
  }
  ```
- **Notes**: There are no "severity" or "incident_type" fields. Do not assume these map to a full "incident" tracking system; they are raw observations.

### GET `/stream/{camera_id}`
- **Response Content-Type**: `multipart/x-mixed-replace; boundary=frame` (MJPEG)

---

## 2. Technical Gotchas

### Stream Authentication
- **Mechanism**: The backend explicitly parses the `token` query parameter for this route. 
- **Implementation**: `<img src="http://127.0.0.1:8000/stream/1?token=<JWT>" />` will work directly. A complex fetch+blob approach is NOT required.

### CORS Configuration (Action Required)
- **Current State**: The backend currently only allows `http://localhost:3000` and `http://frontend:3000`. 
- **Issue**: Vite dev server defaults to `http://localhost:5173`. 
- **Required Fix**: The backend team MUST add `http://localhost:5173` to the `allow_origins` array in `backend/main.py`. Do NOT use a Vite proxy to mask this production issue.

### Base URL Configuration
- **Rule**: The base URL must be stored as one environment variable. 
- **Implementation**: Create a `.env` file containing `VITE_API_BASE_URL=http://127.0.0.1:8000` and only access it centrally via `services/api.ts`. Do not hardcode `localhost` ports anywhere in the UI.

---

## 3. Unsupported Features (UI-Only)
The following requirements must be built for the UI but lack backend support. Do not invent fake API calls for them:
- **Global Configuration Settings**
- **Governance / Audit Logs / Compliance Data**
- **Entry & Exit System**
- **Locations / Zones assignment** (Zone IDs exist on observations, but there is no CRUD API for Zones).
