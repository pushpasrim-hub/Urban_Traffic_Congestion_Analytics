# Urban Traffic Congestion Analytics & Decision Support System

A local, data-driven dashboard for exploring recorded urban traffic conditions. The **Streamlit** frontend communicates with a **FastAPI** backend, which reads existing records from the **MySQL** database `urban_traffic_db` and calculates descriptive analytics. Transparent rule-based recommendations highlight selected high-congestion readings and active incidents.

> **Scope:** Analytics use records already stored in the database. Recommendations are rule-based, not predictive. This application does not implement artificial intelligence, machine learning, traffic forecasting, or future traffic prediction.

## Table of contents

- [Project overview](#project-overview)
- [Objectives](#objectives)
- [Key features](#key-features)
- [System architecture](#system-architecture)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation and setup](#installation-and-setup)
- [Dashboard guide](#dashboard-guide)
- [API reference](#api-reference)
- [Database schema](#database-schema)
- [Screenshots](#screenshots)
- [Troubleshooting](#troubleshooting)
- [Tests](#tests)

## Project overview

This college project provides a single dashboard for examining traffic readings, road segments, weather observations, and incidents from an existing MySQL database. The backend queries and summarizes stored data; the frontend presents it through tables, metrics, filters, and interactive charts. A separate decision-support view can generate evidence-linked recommendations using explicit rules.

The application expects the MySQL database and core traffic tables to be provisioned already. It does not seed or modify traffic records. Two additive migrations create only the authentication and recommendation tables needed by this application.

## Objectives

- Present historical traffic data and road-segment information in an accessible dashboard.
- Summarize recorded traffic measurements using descriptive statistics and congestion categories.
- Show weather and incident records alongside relevant traffic information without overstating what those records prove.
- Provide explainable operational suggestions based on stored evidence and fixed rules.
- Keep the frontend, API, and database responsibilities separate.

## Key features

- **Secure sign-in:** Argon2 password hashing, database-backed users, expiring signed sessions, and logout.
- **Dashboard:** database-derived KPIs and visual summaries.
- **Traffic analytics:** inspect traffic readings by road segment and time range, including speed, travel time, vehicle counts, and congestion levels.
- **Road segments:** browse, search, and manage road inventory, with dependent-record deletion protection.
- **Weather monitoring:** review weather observations and, where records match, compare weather and traffic by exact road-endpoint location and recorded hour.
- **Incident monitoring:** filter and manage incidents; active/resolved/scheduled status is derived from start/end times.
- **Decision recommendations:** explicitly generate and manage persistent recommendations from observed congestion, speed, vehicle-count, period, and active-incident evidence, with duplicate protection.
- **API health and interactive documentation:** check service/database status and explore the FastAPI schema.

## System architecture

```text
[Streamlit frontend: Frontend/app.py]
    -- HTTP / JSON (API_BASE_URL) -->
[FastAPI backend: Backend/app/main.py]
    -- SQLAlchemy + PyMySQL -->
[Existing MySQL database: urban_traffic_db]
```

The frontend does not connect directly to MySQL. The backend uses SQLAlchemy to reflect and query the existing schema. The `app.main` entry point mounts authentication, analytics, road, incident, weather, and recommendation-management routes. Prediction and machine-learning routers remain unmounted.

## Technology stack

| Area | Technology |
|---|---|
| Programming language | Python |
| Backend API | FastAPI, served with Uvicorn |
| Frontend and dashboard | Streamlit |
| Database | MySQL (`urban_traffic_db`) |
| Database access | SQLAlchemy and PyMySQL |
| Data and visualization | Pandas, Plotly |
| Frontend HTTP client | Requests |
| Configuration | `python-dotenv` |
| Tests | pytest |

The root `requirements.txt` also contains packages used by other/legacy modules in the repository. Their presence in the dependency file does not mean that machine-learning or prediction features are enabled in the current application.

## Project structure

```text
.
├── Backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── dependencies.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── security.py
│   │   ├── routers/
│   │   │   ├── decision_support.py
│   │   │   ├── analytics.py
│   │   │   ├── auth.py
│   │   │   ├── crud.py
│   │   │   ├── incidents.py
│   │   │   ├── ml.py
│   │   │   ├── predictions.py
│   │   │   ├── roads.py
│   │   │   ├── traffic.py
│   │   │   └── weather.py
│   │   └── services/
│   │       └── prediction_service.py
│   ├── scripts/
│   │   └── ensure_decision_recommendations_table.py
│   ├── tests/
│   │   ├── test_decision_support.py
│   │   └── test_prediction_service.py
│   ├── .env.example
│   ├── .gitignore
│   ├── README.md
│   └── requirements.txt
├── Frontend/
│   ├── app.py
│   ├── api_client.py
│   ├── assets/
│   │   └── traffic_network.svg
│   ├── .gitignore
│   ├── README.md
│   └── requirements.txt
├── docs/
│   ├── urban_traffic_fastapi_backend_spec.md
│   └── urban_traffic_streamlit_frontend_spec.md
├── .env.example
├── .gitignore
├── requirements.txt
└── pytest.ini
```

The prediction and machine-learning named files above are present in the repository, but they are not included by `Backend/app/main.py` and do not provide features in the running API described here.

## Prerequisites

- Windows with PowerShell (commands below use PowerShell syntax).
- Python 3.11 or newer.
- MySQL Server and access to the pre-existing `urban_traffic_db` database.
- The required core tables and records already loaded into that database.

## Installation and setup

Run commands from the repository root.

### 1. Configure MySQL connection settings

Create `Backend\.env` from the example if it does not exist:

```powershell
if (-not (Test-Path Backend\.env)) { Copy-Item .env.example Backend\.env }
```

Edit `Backend\.env` locally and set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and `JWT_SECRET_KEY` for your environment. Keep `DB_NAME=urban_traffic_db`. Generate a secret locally (do not copy a sample value into production):

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

The example sets `FRONTEND_ORIGIN` to `http://localhost:8501`; change it only if the Streamlit origin is different. Do not commit `.env` or share database credentials/secrets.

The application requires an existing database with the tables listed under [Database schema](#database-schema). To verify that MySQL can see the configured schema and its tables, use your local MySQL username:

```powershell
mysql -u your_mysql_username -p -D urban_traffic_db -e "SHOW TABLES;"
```

The `-p` option prompts for the password; do not put a password in the command. The application does not create or migrate the core tables. An empty database is not sufficient.

### Create the additive application tables and initial administrator

Run these two safe, additive migrations after the existing `road_segments` table is present:

```powershell
mysql -u your_mysql_username -p -D urban_traffic_db < Backend\migrations\001_traffic_app_users.sql
mysql -u your_mysql_username -p -D urban_traffic_db < Backend\migrations\002_decision_recommendations.sql
```

The `-p` option prompts for the MySQL password. Then create the first administrator through the secure prompt (the password is not echoed or stored in source):

```powershell
.\.venv\Scripts\python.exe Backend\scripts\create_admin.py
```

The script also creates the authentication table if needed. Passwords are stored as Argon2 hashes. Set a unique `JWT_SECRET_KEY` in `Backend\.env` before starting the backend.

### 2. Create a Python environment and install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, use the Python executable inside `.venv` directly in the commands below, or follow your organization's PowerShell execution-policy guidance.

### 3. Start the FastAPI backend

In a PowerShell terminal from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --app-dir Backend --reload --host 127.0.0.1 --port 8000
```

Check the backend at:

- API status: <http://localhost:8000/>
- Database health: <http://localhost:8000/health>
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

### 4. Start the Streamlit frontend

Open a second PowerShell terminal at the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:API_BASE_URL = "http://localhost:8000/api"
python -m streamlit run Frontend\app.py
```

Open the dashboard at <http://localhost:8501>. Keep both terminals running while using the application.

## Dashboard guide

Sign in with the administrator created above. All data and management API endpoints require a valid bearer session; logout revokes the current token. The sidebar contains **Dashboard**, **Traffic Analytics**, **Road Segments**, **Weather Monitoring**, **Incident Monitoring**, and **Decision Recommendations**. Road/date and page-specific filters apply to the selected records; the dashboard reports only observed database values.

### Traffic analytics

The backend calculates summaries from saved readings, including total readings, recorded vehicle counts, average speed, average travel time, and high/severe reading counts. Congestion distribution and road-level aggregates can be filtered by road segment and time range. Results describe the selected records and depend on the data present in the database.

### Weather monitoring

Weather records are displayed by their stored location and recorded time. Weather has no road-segment foreign key. The frontend only creates a comparison when a weather location exactly matches a road segment's start or end location (case-insensitive, with surrounding whitespace ignored) and the observations are in the same recorded hour. The comparison is descriptive and does not establish that weather caused traffic changes.

### Incident monitoring

Incident records include their type, description, road segment, start time, and optional end time. An incident is treated as active when its start time is not in the future and its end time is either null or not yet passed.

### Decision recommendations

Choose a road, date, and time, then select **Analyze Traffic**. The backend analyzes the one-hour window starting at that time (inclusive, with the end exclusive) using stored traffic readings and recorded incidents for that road. This is a historical database analysis, not a live traffic feed. At least one reading with a recognized `low`, `moderate`/`medium`, `high`, or `severe` congestion label is needed; the result reports how many recognized readings were used. Readings with missing or unrecognized congestion labels are excluded from classification.

Classification thresholds are based on the share of those recognized readings: **High** when at least 50% are `high` or `severe`; otherwise **Moderate** when at least 50% are `moderate`, `high`, or `severe`; otherwise **Low**. If no classified readings exist, the page displays **Insufficient Data** and does not generate a recommendation. Recommendations are explainable rule-based suggestions, informed by recorded speed/vehicle metrics when available and incidents overlapping the selected window; an incident record is contextual evidence, not proof of cause.

Migration 002 creates the recommendation table with the form's nullable context fields. Run `Backend\scripts\add_recommendation_context_columns.py` after the migration as a compatibility step for existing tables; it adds only missing nullable fields and preserves saved recommendations. The alternative helper `Backend\scripts\ensure_decision_recommendations_table.py` creates only that table if missing.

## API reference

All `/api` data routes below require authentication. `/health` remains available for service diagnostics.

| Method and path | Purpose | Supported query parameters |
|---|---|---|
| `GET /` | Service name and status | - |
| `GET /health` | MySQL connectivity and required-table status | - |
| `GET /api/health` | Alias for the health response; omitted from the OpenAPI schema | - |
| `POST /api/auth/login` | Verify username/password and issue an expiring bearer token | JSON username/password |
| `GET /api/auth/me` | Validate the current session | Bearer token |
| `POST /api/auth/logout` | Revoke the current token | Bearer token |
| `GET/POST /api/road-segments`, `GET/PATCH/PUT/DELETE /api/road-segments/{segment_id}` | Search/read/manage road segments; referenced roads cannot be silently removed | List: `search`, `limit`, `offset` |
| `GET /api/traffic-readings` | Read-only traffic readings | `segment_id`, `road_type`, `start_time`, `end_time`, `from_time`, `to_time`, `congestion_level`, `limit`, `offset` |
| `GET /api/weather`, `GET /api/weather/{weather_id}` | Read weather observations (monitoring only) | `location`, `start_time`, `end_time`, `condition`, `search`, `limit`, `offset` |
| `GET/POST /api/incidents`, `GET/PATCH/PUT/DELETE /api/incidents/{incident_id}` | Read/manage incidents | `segment_id`, `start_time`, `end_time`, `active_only`, `incident_type`, `incident_status`, `search`, `limit`, `offset` |
| `GET /api/recommendations` | List saved recommendations | `segment_id`, `start_time`, `end_time`, `priority`, `recommendation_status`, `limit`, `offset` |
| `GET /api/recommendations/analyze` | Analyze one selected road and the one-hour window starting at `start_time`; returns observed classification, evidence, and a rule-based suggestion without saving a recommendation | `segment_id`, `start_time` |
| `GET /api/recommendations/analysis` | Actual reading counts, averages, findings, and suggested actions by congestion category | `segment_id`, `start_time`, `end_time` |
| `PATCH/DELETE /api/recommendations/{recommendation_id}` | Manage saved recommendations | JSON patch or ID |
| `POST /api/recommendations/generate` | Generate and save category-based suggestions from selected readings | `segment_id`, `start_time`, `end_time` |
| `GET /api/analytics/summary` | Summary metrics from stored readings and incidents | `segment_id`, `road_type`, `congestion_level`, `start_time`, `end_time`, `from_time`, `to_time` |
| `GET /api/analytics/congestion` | Counts grouped by congestion level | `segment_id`, `road_type`, `congestion_level`, `start_time`, `end_time`, `from_time`, `to_time` |
| `GET /api/analytics/roads` | Aggregates grouped by road segment | `segment_id`, `road_type`, `congestion_level`, `start_time`, `end_time`, `from_time`, `to_time` |

`start_time` and `end_time` accept ISO 8601 datetimes and must form a valid range (`start_time` on or before `end_time`). `from_time` and `to_time` filter by time of day and support ranges that cross midnight. Collection endpoints that support pagination default to a bounded result size; `limit` is at most 500. The OpenAPI docs at `/docs` provide request and response schemas.

## Database schema

The application reads the existing MySQL schema `urban_traffic_db`. The table and column details below document the schema currently recorded for this project. Unless marked nullable or given a default, columns are non-null.

| Table | Columns |
|---|---|
| `road_segments` | `segment_id` INTEGER (primary key); `name` VARCHAR(100); `start_location` VARCHAR(150); `end_location` VARCHAR(150); `length_km` DECIMAL(8,3); `road_type` VARCHAR(50) |
| `traffic_readings` | `reading_id` INTEGER (primary key); `segment_id` INTEGER; `recorded_at` DATETIME; `speed_kmh` DECIMAL(7,2); `vehicle_count` INTEGER; `travel_time_minutes` DECIMAL(8,2); `congestion_level` VARCHAR(20); `data_source` VARCHAR(30), default `sample` |
| `weather_data` | `weather_id` INTEGER (primary key); `recorded_at` DATETIME; `location` VARCHAR(255); `temperature_c` FLOAT (nullable); `rainfall_mm` FLOAT (nullable); `condition` VARCHAR(100) (nullable) |
| `incidents` | `incident_id` INTEGER (primary key); `segment_id` INTEGER; `incident_type` VARCHAR(120); `description` TEXT; `start_time` DATETIME; `end_time` DATETIME (nullable) |
| `decision_recommendations` | `recommendation_id` INTEGER (auto-increment primary key); `segment_id` INTEGER (foreign key); `priority` VARCHAR(20); `recommendation_text` VARCHAR(500); `evidence_summary` TEXT; `problem_type` VARCHAR(40) (nullable); `congestion_severity` VARCHAR(20) (nullable); `problem_description` VARCHAR(500) (nullable); `created_at` DATETIME, default current timestamp; `status` VARCHAR(30), default `pending`; `deduplication_key` CHAR(64), unique |
| `traffic_app_users` | `user_id` INTEGER (auto-increment primary key); `username` VARCHAR(120), unique; `password_hash` VARCHAR(255); `is_active` BOOLEAN; `token_version` INTEGER; `created_at` DATETIME |

The recorded foreign keys are `traffic_readings.segment_id` and `incidents.segment_id` to `road_segments.segment_id`, and `decision_recommendations.segment_id` to `road_segments.segment_id`. Weather records are not linked to road segments.

In the configured schema documented for this project, `traffic_readings.congestion_level` is VARCHAR rather than MySQL ENUM. The documented values are `low`, `moderate`, `high`, and `severe`. `traffic_readings.data_source` defaults to `sample`; treat such records as demonstration/sample data, not verified Chennai measurements. Core traffic tables are never migrated by this application. Run the two additive migrations to enable persistent login and recommendation management.

## Screenshots

Screenshots are not currently included in the repository. Add dashboard screenshots here when available.

> Screenshot placeholder — Dashboard overview
>
> Screenshot placeholder — Traffic analytics and filters
>
> Screenshot placeholder — Decision recommendations with evidence

## Troubleshooting

| Symptom | Checks |
|---|---|
| `ERR_CONNECTION_REFUSED` at port 8000 or 8501 | Confirm the corresponding FastAPI or Streamlit terminal is still running and that the URL/port is correct. Both services are needed for the dashboard. |
| Backend reports MySQL unavailable | Confirm MySQL Server is running; check `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in `Backend\.env`; then verify access with the MySQL `SHOW TABLES` command above. |
| Health response lists missing tables | The configured database must already contain `road_segments`, `traffic_readings`, `weather_data`, and `incidents`. This application does not create or migrate those core tables. |
| Dashboard cannot reach FastAPI | Set `API_BASE_URL` in the Streamlit terminal to the backend API base URL, including `/api`, then restart Streamlit. |
| Weather comparison is empty | Check that weather location text matches a road segment's start or end location and that both records fall within the same recorded hour. |
| No recommendations are saved | Confirm `decision_recommendations` exists and follows the documented required fields. Missing recommendation storage prevents persistence; it does not trigger automatic table creation. |
| PowerShell activation is blocked | Use `.venv\Scripts\python.exe` directly to run `-m pip`, `-m uvicorn`, or `-m streamlit`, or follow local execution-policy guidance. |

## Tests

From the repository root, run the focused rule-based decision-support tests:

```powershell
python -m pytest Backend\tests\test_decision_support.py
```

The repository also contains prediction-service tests for separate modules that are not mounted by the current API entry point.
