# FastAPI Backend Build Specification

## Project

Build the backend for **Urban Traffic Congestion Analysis and Travel Time Prediction System**. Read the existing project first and reuse its files where practical.

## Database rules

- Connect to the existing MySQL database **`urban_traffic_db`**.
- Existing tables and records must be preserved. Do not create a different database, drop/truncate/rename/recreate tables, or overwrite records. Do not run destructive schema setup at startup.
- Use the existing tables: `road_segments`, `traffic_readings`, `weather_data`, `incidents`, `traffic_predictions`. Inspect the actual schema and map ORM models to it. If it differs from the fields below, adapt to the actual database and report the mismatch; do not silently alter the database.
- Known fields: `road_segments(segment_id, name, start_location, end_location, length_km, road_type)`; `traffic_readings(reading_id, segment_id, recorded_at, speed_kmh, vehicle_count, travel_time_minutes, congestion_level)`; `weather_data(weather_id, recorded_at, location, temperature_c, rainfall_mm, condition)`; `incidents(incident_id, segment_id, incident_type, description, start_time, end_time)`; `traffic_predictions(prediction_id, segment_id, predicted_for, created_at, predicted_speed_kmh, predicted_travel_time_minutes, predicted_congestion_level)`.

## Stack and structure

Use Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.x, PyMySQL, Pydantic v2, python-dotenv, pandas, numpy, scikit-learn, and joblib.

Keep database/session setup, ORM models, Pydantic schemas, routers, and ML service separate. A suitable structure is `app/main.py`, `app/database.py`, `app/models.py`, `app/schemas.py`, `app/routers/`, and `app/services/prediction_service.py`. Adapt to the existing Backend folder; do not create duplicate roots.

## Configuration

Read credentials from `.env` only; never hard-code or print them. Provide `.env.example` and ignore `.env` in Git.

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=urban_traffic_db
DB_USER=root
DB_PASSWORD=your_local_password
FRONTEND_ORIGIN=http://localhost:8501
MODEL_PATH=artifacts/travel_time_model.joblib
```

Build the SQLAlchemy URL safely, create a reusable DB-session dependency, and always close sessions. Do not create tables automatically. `/api/health` should report API and DB availability without exposing secrets.

## CRUD API (required for all five tables)

Use `/api` prefix, JSON, Pydantic validation, useful HTTP errors, and pagination (`limit`, `offset`) for list endpoints. Implement collection `GET` and `POST`, and item `GET`, `PUT`, `PATCH`, and `DELETE` for each:

- `/api/road-segments` with `{segment_id}`
- `/api/traffic-readings` with `{reading_id}`
- `/api/weather` with `{weather_id}`
- `/api/incidents` with `{incident_id}`
- `/api/predictions` with `{prediction_id}`

POST returns the inserted row and generated ID. PUT replaces editable fields; PATCH updates only supplied fields. Never allow primary-key edits. DELETE only the selected record; never cascade-delete unrelated data. Refuse road deletion when referenced by other records, with a clear 409 response. Return 404 for missing IDs and useful 409/422 errors for constraints/invalid input. Validate referenced segment IDs.

Validate positive road length; nonnegative speed, travel time, count, and rainfall; congestion in `low`, `moderate`, `high`, `severe`; and valid incident time ranges. Support useful list filters such as `segment_id`, `location`, time range, and congestion.

Also provide:

- `GET /api/traffic-readings/latest` — latest reading per segment or optional segment.
- `GET /api/incidents?active_only=true` — incidents whose start has passed and whose end is null or has not passed.
- Optional `GET /api/road-segments/{segment_id}/dashboard` summary for latest reading, active incidents, and latest prediction.

Ensure static routes such as `/latest` are not shadowed by `/{reading_id}`.

## ML travel-time prediction (required)

Implement real training and inference using scikit-learn. Target is `traffic_readings.travel_time_minutes`. Candidate features: `segment_id`, road length, speed, vehicle count, hour, day of week, and prior readings available at prediction time. Never use the target value from the same row as an input. Use chronological train/validation split to avoid future leakage. Persist preprocessing and estimator together with joblib. A `RandomForestRegressor` baseline is acceptable.

Weather is not linked to road segments in the current schema (`weather_data` has `location`, no `segment_id`). Do not falsely join weather to a segment; omit it unless there is an explicit, defensible location mapping.

Endpoints:

- `POST /api/ml/train`: load eligible history, train and persist a model, evaluate on a chronological holdout, return model name, row counts, MAE, RMSE and R² when defined.
- `GET /api/ml/status`: report whether a loadable model exists and available training metadata.
- `POST /api/ml/predict`: accept segment, prediction time and the live traffic inputs required by the trained feature pipeline; return predicted minutes and model metadata. Allow saving to `traffic_predictions` and return the saved record.

Reject negative/impossible inputs and never silently invent a prediction. If the model is missing or training data insufficient, return a clear 409/422 with next steps. The provided five-row demo set is likely too small for meaningful training; CRUD and dashboard data APIs must still work. Do not claim training succeeded when it did not.

## Reliability and setup

Configure CORS for `FRONTEND_ORIGIN` (local default `http://localhost:8501`). Enable `/docs` and `/redoc`. Handle DB outages without leaking secrets. Include setup/run instructions and example requests in README.

Dependencies should include `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `pymysql`, `python-dotenv`, `pydantic`, `pandas`, `numpy`, `scikit-learn`, and `joblib`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Copy .env.example to .env and set local credentials
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Document how to verify `/api/health` and `/docs`. Explain that `ERR_CONNECTION_REFUSED` means the API process is stopped or host/port is wrong; Streamlit and FastAPI run separately.

## Done when

The backend uses `urban_traffic_db` without destructive setup, all five entities support CRUD with FK safety, and ML training/evaluation/prediction uses a persisted real model with clear insufficient-data behavior.
