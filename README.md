# Urban Traffic Congestion Analytics & Decision Support System

A local traffic analytics dashboard backed by FastAPI and the existing MySQL database `urban_traffic_db`. The Streamlit application requests data from FastAPI; database queries and rule-based recommendation generation stay in the backend. The project does not seed data, create or modify traffic tables, predict future traffic, or use machine learning.

## Existing database

The configured MySQL schema was inspected directly. All listed columns are non-null unless marked nullable; `segment_id` fields named as primary keys are the table primary keys.

| Table | Columns and actual MySQL types |
|---|---|
| `road_segments` | `segment_id` INTEGER (PK); `name` VARCHAR(100); `start_location` VARCHAR(150); `end_location` VARCHAR(150); `length_km` DECIMAL(8,3); `road_type` VARCHAR(50) |
| `traffic_readings` | `reading_id` INTEGER (PK); `segment_id` INTEGER; `recorded_at` DATETIME; `speed_kmh` DECIMAL(7,2); `vehicle_count` INTEGER; `travel_time_minutes` DECIMAL(8,2); `congestion_level` VARCHAR(20); `data_source` VARCHAR(30), default `sample` |
| `weather_data` | `weather_id` INTEGER (PK); `recorded_at` DATETIME; `location` VARCHAR(255); `temperature_c` FLOAT NULL; `rainfall_mm` FLOAT NULL; `condition` VARCHAR(100) NULL |
| `incidents` | `incident_id` INTEGER (PK); `segment_id` INTEGER; `incident_type` VARCHAR(120); `description` TEXT; `start_time` DATETIME; `end_time` DATETIME NULL |
| `decision_recommendations` | `recommendation_id` INTEGER (PK, auto-increment); `segment_id` INTEGER (FK to `road_segments.segment_id`); `priority` VARCHAR(20); `recommendation_text` VARCHAR(500); `evidence_summary` TEXT; `created_at` DATETIME, default current timestamp; `status` VARCHAR(30), default `pending`; `deduplication_key` CHAR(64), unique |

The foreign keys are `traffic_readings.segment_id -> road_segments.segment_id` and `incidents.segment_id -> road_segments.segment_id`. Weather has no road foreign key. Weather comparisons are therefore shown only for exact road-endpoint location matches in the same recorded hour. These comparisons are descriptive and do not establish causation.

The live database differs from the expected setup in two ways: `traffic_readings.congestion_level` is `VARCHAR(20)` rather than a MySQL `ENUM`, and `decision_recommendations` was missing. The observed stored congestion values are `low`, `moderate`, `high`, and `severe`; filters and decision rules recognize those values, while analytics surface any other stored category as observed. The missing recommendation table was added without changing the existing tables or records. The idempotent schema script creates only that table if it is absent; it is not run automatically at application startup.

## Configure MySQL

If `Backend\.env` does not already exist, copy the example file and edit it with your local credentials:

```powershell
if (-not (Test-Path Backend\.env)) { Copy-Item .env.example Backend\.env }
```

Set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in `Backend\.env`. `DB_NAME` should remain `urban_traffic_db`. `FRONTEND_ORIGIN` defaults to `http://localhost:8501`. `.env` files are ignored by Git. Never commit real credentials.

## Install and run

Use Python 3.11 or newer. From the repository root, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start the FastAPI backend from the repository root:

```powershell
python -m uvicorn app.main:app --app-dir Backend --reload --host 127.0.0.1 --port 8000
```

In a second terminal, activate the same environment and start Streamlit:

```powershell
.\.venv\Scripts\Activate.ps1
$env:API_BASE_URL = "http://localhost:8000/api"
python -m streamlit run Frontend\app.py
```

Open the dashboard at **http://localhost:8501**, interactive API documentation at **http://localhost:8000/docs**, and API health at **http://localhost:8000/health**. The backend and frontend must both be running. `ERR_CONNECTION_REFUSED` means the relevant service is stopped or its host/port is incorrect.

Alternatively, `start_urban_traffic.bat` opens both services using the repository's local `.venv`.

## Dashboard

The sidebar provides Dashboard, Traffic Analytics, Road Segments, Weather Monitoring, Incident Monitoring, and Decision Recommendations pages. The road and date filters apply to traffic analytics and relevant incident views. Empty tables and unavailable optional fields are shown as empty states or `N/A`.

Dashboard KPIs and charts are calculated from current database records. The decision-support rules are intentionally transparent:

- Latest `high` readings suggest reviewing signal timing and increasing monitoring.
- Latest `severe` readings suggest reviewing diversion options and temporary traffic controls.
- Incidents whose start time has passed and whose end time is null or in the future suggest monitoring the incident response and reviewing diversion options.

Suggestions include the underlying reading/incident evidence. Generation requires an explicit button click and does not run during page refresh. Existing matching recommendation text, priority, road, and evidence are checked before insertion. If the recommendation table is absent or its required schema cannot be safely populated, the UI reports that suggestions were not saved.

To safely create only the recommendation table on a different database that lacks it, run from the repository root:

```powershell
python Backend\scripts\ensure_decision_recommendations_table.py
```

The table has a foreign key to `road_segments.segment_id` and a unique evidence digest so repeated generation cannot create duplicate recommendations, including under concurrent requests.

## API endpoints

- `GET /` and `GET /health`
- `GET /api/road-segments`
- `GET /api/traffic-readings`
- `GET /api/weather`
- `GET /api/incidents`
- `GET /api/recommendations`
- `POST /api/recommendations/generate`
- `GET /api/analytics/summary`
- `GET /api/analytics/congestion`
- `GET /api/analytics/roads`

Traffic and analytics endpoints accept supported filters such as `segment_id`, `start_time`, and `end_time`; collection endpoints support `limit` and `offset`. Timestamps use ISO 8601. The API uses SQLAlchemy parameter binding and validates query values.

## Validation

Run the focused project tests from the repository root:

```powershell
python -m pytest Backend\tests\test_decision_support.py
```

The application reads the configured existing MySQL tables. It does not insert demo records and does not initialize, reset, or migrate the database.
