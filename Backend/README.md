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
- `/api/ml/status`, `/api/ml/train`, `/api/ml/predict`, `/api/ml/what-if`

Road segments referenced by readings, incidents, or predictions cannot be deleted; the API returns 409 instead of cascading. Date/time inputs accept ISO 8601. Timezone-naive inputs are interpreted as MySQL `DATETIME` wall-clock values; timezone-aware inputs are converted to UTC and stored without timezone information.

## Model

The ML service reflects the live `traffic_readings` and `road_segments` tables through the existing SQLAlchemy connection. `/api/ml/status` and successful `/api/ml/train` responses include the discovered column names/types and preprocessing counts; no credentials are returned. Training needs `segment_id` and `recorded_at`. Each output is trained only if its target column and enough valid values actually exist:

- Congestion classification uses historical `congestion_level` labels present in the data. It reports accuracy, weighted precision/recall/F1, a confusion matrix, and comparison with a most-frequent `DummyClassifier`.
- Travel-time regression requires `travel_time_minutes`; vehicle-count regression requires `vehicle_count`. They report MAE, RMSE, and R² only when meaningful, compared with a mean `DummyRegressor`.
- Each eligible target needs at least 30 rows. Validation uses a chronological 80/20 holdout. Feature preprocessing fits inside scikit-learn pipelines; records are ordered chronologically, exact duplicate measurement rows (ignoring the surrogate `reading_id`) are dropped, invalid timestamps are excluded, and negative, non-numeric, or non-finite measurements are treated as missing. Numeric missing features are median-imputed and categorical missing values receive a preprocessing-only sentinel.
- Traffic features use up to ten earlier readings from the same segment. The reading being predicted is never used as its own input. Predictions use the corresponding recent stored readings; no real-time sensor feed is implied.
- Weather is not used: `weather_data` has no road-segment mapping in the documented schema. The what-if endpoint reports a rainy-weather scenario as unsupported rather than fabricating a road-specific weather input. The 20% traffic-volume scenario runs only when a trained model uses a valid traffic-volume input.

Trained preprocessing/model pipelines and measured holdout metadata are saved together with joblib under `Backend/artifacts/` (ignored by Git). A failed/insufficient training attempt does not create a success-shaped artifact. A saved artifact should be treated as a trusted local file and not loaded from an untrusted source.

Train from a PowerShell terminal in `Backend/` after configuring the existing local MySQL database and starting the backend:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/ml/train" -Headers @{ Authorization = "Bearer <token>" }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ml/status" -Headers @{ Authorization = "Bearer <token>" }
```

The login endpoint is `POST /api/auth/login`; use the access token returned by that endpoint. Training can return HTTP 409 when there is not enough suitable history. No evaluation scores are provided in this README because the live database was not available during implementation.

`POST /api/ml/what-if` accepts the same future segment/time context as prediction, does not save records, and returns a baseline plus hypothetical scenario results. All scenario changes are model simulations, not causal effects. The existing `POST /api/ml/predict` route and response fields are retained; its optional model outputs remain `null` when those outputs were not trained.

Example request (send the usual bearer token):

```json
{
  "segment_id": 1,
  "predicted_for": "2026-10-14T08:30:00",
  "save": false
}
```

The response includes the baseline prediction and each scenario's `supported` flag. Supported outputs include predictions from the trained pipeline, baseline values, and numeric differences; unsupported scenarios include an explanation instead of a fabricated value. Evaluation scores are returned from each actual training run rather than documented here as fixed sample numbers.

## Tests

The unit/integration tests use an isolated in-memory SQLite database and test-only records; they do not require or modify the production MySQL database:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests -q
```

They cover preprocessing and invalid measurements, chronological training/evaluation and simple baselines, artifact status/loading, predictions, scenario support/limitations, Pydantic request validation, and FastAPI what-if responses. For MySQL-backed manual verification, configure `Backend/.env`, start FastAPI as above, sign in through the existing frontend, then check **Predictions & ML** for live eligible-row counts and metrics.

## Frontend startup

The API has no public registration. Protect the host and rotate credentials before any public deployment. Model training or prediction can be unavailable if the installed scikit-learn/SciPy binaries are blocked by local application-control policy; in that case CRUD remains available and the ML endpoint reports a clear 503.

From `Frontend/` in a separate PowerShell terminal:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:API_BASE_URL = "http://127.0.0.1:8000/api"
streamlit run app.py
```