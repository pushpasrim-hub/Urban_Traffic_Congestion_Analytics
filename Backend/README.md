# Urban Traffic FastAPI Backend

FastAPI connects to the existing MySQL database `urban_traffic_db`. It reflects `road_segments`, `traffic_readings`, `weather_data`, `incidents`, and `traffic_predictions` at runtime and never creates, alters, seeds, or deletes those traffic tables. If the database is unreachable, `/api/health` reports that without returning connection details.

## Setup

From `Backend/` in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `Backend/.env` with your local MySQL host, port, database (`urban_traffic_db`), username and password. Generate a strong JWT secret locally, for example with `python -c "import secrets; print(secrets.token_urlsafe(48))"`, and set it as `JWT_SECRET_KEY`. Set a non-empty `INITIAL_ADMIN_PASSWORD` of at least 12 characters and `INITIAL_ADMIN_USERNAME` before the first successful API start. The password is hashed; no default user password is committed. Do not share or commit `.env`.

The API creates only the separate `traffic_app_users` authentication table with SQLAlchemy `CREATE TABLE IF NOT EXISTS` behavior. It does not create or modify the five traffic tables. Weather is not associated with segments because the documented schema has no mapping.

## Run

Start FastAPI from `Backend/`:

```powershell
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health: `http://127.0.0.1:8000/api/health`  
Swagger: `http://127.0.0.1:8000/docs`  
ReDoc: `http://127.0.0.1:8000/redoc`

Start Streamlit separately using `Frontend/README.md`. If a URL returns `ERR_CONNECTION_REFUSED`, that service is stopped or its host/port is incorrect.

## API

All data APIs require a bearer token from `POST /api/auth/login`. Use `POST /api/auth/logout` to end the UI session; tokens expire according to `ACCESS_TOKEN_MINUTES`.

Each collection below has `GET`, `POST`, item `GET`, `PUT`, `PATCH`, and `DELETE` routes. List endpoints accept `limit` (1-500), `offset`, search and supported entity filters.

- `/api/road-segments` (`segment_id`)
- `/api/traffic-readings` (`reading_id`), plus `/api/traffic-readings/latest`
- `/api/weather` (`weather_id`)
- `/api/incidents` (`incident_id`), including `active_only=true`
- `/api/predictions` (`prediction_id`)
- `/api/ml/status`, `/api/ml/train`, `/api/ml/predict`
- `/api/analytics/summary` — network counts, latest congestion by road, speed/volume by hour, road comparison and a time-aligned weather/traffic association.
- `/api/analytics/historical` — optional `segment_id`, `start_time`, `end_time`, `time_period` (`peak`, `morning_peak`, `evening_peak`, `off_peak`, `daytime`, `overnight`), `congestion_level`, `limit` and `offset`; returns matching readings and aggregate statistics.
- `/api/analytics/causes` — peak-hour, weather-time-association and incident-window comparisons from stored records.
- `POST /api/analytics/what-if` — compares the model baseline with a 20% vehicle-count increase when a loadable model and real baseline inputs are available; returns rainy-weather as unsupported while the current model/schema do not support it.

Road segments referenced by readings, incidents, or predictions cannot be deleted; the API returns 409 instead of cascading. Date/time inputs accept ISO 8601. Timezone-naive inputs are interpreted as MySQL `DATETIME` wall-clock values; timezone-aware inputs are converted to UTC and stored without timezone information.

Analytics use only stored records. Historical traffic-volume summaries are marked unsupported if `vehicle_count` is absent from the actual table. Weather has no segment mapping, so weather comparisons match observations only at the same calendar date and hour across the network. Weather and incident comparisons are descriptive associations, not proof of causation. The current ML features do not include weather; prediction requests may include `weather_condition` and `rainfall_mm` as context, but the response reports that the model did not use them. The rainy-weather what-if therefore returns a clear unsupported status rather than a fabricated prediction.

## Model

Training uses historical `traffic_readings.travel_time_minutes` as the target with speed, vehicle count, segment, optional road length, congestion, hour, and weekday as features. Newest chronological records are held out for validation; MAE and RMSE are minutes and R² is included only when meaningful. At least 30 eligible readings are required. The persisted pipeline is stored under `Backend/artifacts/` and ignored by Git. Weather is deliberately excluded because no road-to-weather relation exists in the schema.

The API has no public registration. Protect the host and rotate credentials before any public deployment. Model training or prediction can be unavailable if the installed scikit-learn/SciPy binaries are blocked by local application-control policy; in that case CRUD remains available and the ML endpoint reports a clear 503.