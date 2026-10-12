# Streamlit Frontend Build Specification

## Project

Build the frontend for **Urban Traffic Congestion Analysis and Travel Time Prediction System**. This is a specification for GitHub Copilot. Inspect the existing workspace and reuse its Frontend folder/files where practical.

## Architecture rules

- Backend is FastAPI; frontend is Streamlit; database is the existing MySQL database `urban_traffic_db`.
- Streamlit must communicate with FastAPI over HTTP. Do not connect directly to MySQL and do not put database credentials in frontend files.
- Use the existing records and five tables through APIs: `road_segments`, `traffic_readings`, `weather_data`, `incidents`, `traffic_predictions`. Do not fabricate records or predictions.
- UI title: **Urban Traffic Congestion Analysis and Travel Time Prediction System**.

## Technology and files

Use Python 3.11+, Streamlit, requests, and pandas. Keep API calls/error handling in `api_client.py` and UI in `app.py`. Reuse existing project structure rather than making duplicate roots.

```env
API_BASE_URL=http://127.0.0.1:8000/api
```

Use request timeouts and configurable API URL. Dependencies: `streamlit`, `requests`, `pandas`.

## Pages and CRUD

Build a clean sidebar navigation with these sections:

1. Dashboard
2. Road Segments
3. Traffic Readings
4. Weather
5. Incidents
6. Predictions & ML

Backend API collections are `/api/road-segments`, `/api/traffic-readings`, `/api/weather`, `/api/incidents`, `/api/predictions`; ML routes are `/api/ml/train`, `/api/ml/status`, `/api/ml/predict`. Follow the backend's exact schemas and field names.

For **each of the five data entities**, implement create, read, update, and delete UI flows. List records in searchable/filterable tables; add forms; allow selecting a record to edit; provide delete action with confirmation; show success/error feedback and refresh after mutations. Do not mutate records merely because a page reruns or a filter changes. Handle foreign-key rejection when deleting a referenced road. Use `st.session_state` to avoid duplicate submissions.

Forms must match existing schema:

- Road segment: `name`, `start_location`, `end_location`, `length_km`, `road_type`.
- Traffic reading: `segment_id`, `recorded_at`, `speed_kmh`, `vehicle_count`, `travel_time_minutes`, `congestion_level`.
- Weather: `recorded_at`, `location`, `temperature_c`, `rainfall_mm`, `condition`.
- Incident: `segment_id`, `incident_type`, `description`, `start_time`, `end_time`.
- Prediction: view/manage stored records; create predictions using the ML prediction workflow.

Populate segment selectors from the API rather than requiring typed IDs. Congestion choices are `low`, `moderate`, `high`, `severe`. Support optional/null values correctly.

## Dashboard

- Road-segment selector, time-window filter, and refresh button.
- Latest speed (km/h), vehicle count, observed travel time (minutes), and congestion metrics.
- Chronological charts for speed and travel time, plus recent readings table.
- Active incidents for selected segment.
- Stored predictions and timestamps for the selected segment.
- Latest weather with its location and time. Since weather has no segment key, label it general/location-based and do not claim it exactly matches a selected road.
- Show units. Missing values render as `N/A`, never silently as zero. Provide useful empty states.

## ML workflow (required)

In Predictions & ML:

1. Call `GET /api/ml/status` and show whether a trained model is available and its metadata.
2. Provide **Train model** action calling `POST /api/ml/train`; show row counts, MAE, RMSE, and R² when returned. Explain insufficient historical data without claiming success.
3. Provide a form with road segment, prediction time, and current traffic inputs required by backend (for example speed and vehicle count).
4. Call `POST /api/ml/predict`, display the predicted travel time in minutes and model metadata, and state whether it was saved.
5. Refresh predictions after a successful save. Never calculate a fake prediction in the frontend.

The five-row example data may be insufficient to train a meaningful model. Say that more historical readings are needed while keeping dashboard and CRUD available.

## UX and errors

- Use wide layout, readable metric cards, simple charts, consistent timestamp formatting, and a laptop-friendly design.
- Show spinners during requests; handle timeout, connection refused, non-2xx responses, invalid JSON, validation errors, and empty data without crashing.
- If backend is unreachable, ask user to start FastAPI in a separate terminal and check `API_BASE_URL`. Do not report MySQL failure unless backend health says so.
- Do not show stack traces, secrets, or raw internal errors.
- Make destructive actions explicit and confirmed.

## Run instructions

Run backend and frontend as separate processes. From Frontend:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Typical addresses: dashboard `http://localhost:8501`, API docs `http://127.0.0.1:8000/docs`. Explain `ERR_CONNECTION_REFUSED`: the corresponding service is stopped or host/port is incorrect. README should explain configuration and starting both services in separate terminals.

## Done when

The dashboard reads real data via FastAPI, CRUD exists for all five entities, prediction training/status/inference use the backend's real ML model, and empty data/offline backend/insufficient training data are explained clearly.
