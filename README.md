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

The application expects the database and its core tables to be provisioned already. It does not seed demo records, initialize or migrate the core schema, or change existing traffic tables at startup.

## Objectives

- Present historical traffic data and road-segment information in an accessible dashboard.
- Summarize recorded traffic measurements using descriptive statistics and congestion categories.
- Show weather and incident records alongside relevant traffic information without overstating what those records prove.
- Provide explainable operational suggestions based on stored evidence and fixed rules.
- Keep the frontend, API, and database responsibilities separate.

## Key features

- **Dashboard:** current database-derived KPIs and visual summaries.
- **Traffic analytics:** inspect traffic readings by road segment and time range, including speed, travel time, vehicle counts, and congestion levels.
- **Road segments:** browse the available road-segment inventory.
- **Weather monitoring:** review weather observations and, where records match, compare weather and traffic by exact road-endpoint location and recorded hour.
- **Incident monitoring:** review incidents and filter for active incidents.
- **Decision recommendations:** explicitly generate recommendations from latest high/severe readings and active incidents, with evidence summaries and duplicate protection.
- **API health and interactive documentation:** check service/database status and explore the FastAPI schema.

## System architecture

```text
[Streamlit frontend: Frontend/app.py]
    -- HTTP / JSON (API_BASE_URL) -->
[FastAPI backend: Backend/app/main.py]
    -- SQLAlchemy + PyMySQL -->
[Existing MySQL database: urban_traffic_db]
```

The frontend does not connect directly to MySQL. The backend uses SQLAlchemy to reflect and query the existing schema. The `app.main` entry point mounts the status routes and decision-support API; other router and prediction-related modules present in the source tree are not mounted in this running application.

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
├── pytest.ini
└── start_urban_traffic.bat
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

Edit `Backend\.env` locally and set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` for your MySQL installation. Keep `DB_NAME=urban_traffic_db`. The example also sets `FRONTEND_ORIGIN` to `http://localhost:8501`; change it only if the Streamlit origin is different. Do not commit `.env` or share database credentials.

The application requires an existing database with the tables listed under [Database schema](#database-schema). To verify that MySQL can see the configured schema and its tables, use your local MySQL username:

```powershell
mysql -u your_mysql_username -p -D urban_traffic_db -e "SHOW TABLES;"
```

The `-p` option prompts for the password; do not put a password in the command. The application does not create or migrate the core tables. An empty database is not sufficient.

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

Alternatively, after creating `.venv` and configuring `Backend\.env`, run `.\start_urban_traffic.bat` from the repository root to open both services.

## Dashboard guide

The sidebar contains **Dashboard**, **Traffic Analytics**, **Road Segments**, **Weather Monitoring**, **Incident Monitoring**, and **Decision Recommendations**. Road and date filters are applied to supported analytics and monitoring views. The dashboard reads the records currently in MySQL; displayed metrics are not forecasts.

### Traffic analytics

The backend calculates summaries from saved readings, including total readings, recorded vehicle counts, average speed, average travel time, and high/severe reading counts. Congestion distribution and road-level aggregates can be filtered by road segment and time range. Results describe the selected records and depend on the data present in the database.

### Weather monitoring

Weather records are displayed by their stored location and recorded time. Weather has no road-segment foreign key. The frontend only creates a comparison when a weather location exactly matches a road segment's start or end location (case-insensitive, with surrounding whitespace ignored) and the observations are in the same recorded hour. The comparison is descriptive and does not establish that weather caused traffic changes.

### Incident monitoring

Incident records include their type, description, road segment, start time, and optional end time. An incident is treated as active when its start time is not in the future and its end time is either null or not yet passed.

### Decision recommendations

Recommendations are generated only when a user clicks **Analyze current evidence**. The rules are:

| Stored evidence | Rule-based suggestion |
|---|---|
| Latest reading for a road segment is `high` | Medium priority: review signal timing and increase traffic monitoring. |
| Latest reading for a road segment is `severe` | High priority: review diversion options and temporary traffic controls. |
| Incident is currently active | High priority: monitor the incident response and review diversion options. |

Generated suggestions include an evidence summary based on the underlying reading or incident. When the `decision_recommendations` table is available, matching evidence is protected against duplicate insertion. Generation is not run on page refresh. If recommendation storage is missing, the API can return generated suggestions but does not save them.

The optional helper `Backend\scripts\ensure_decision_recommendations_table.py` creates only the recommendation table if it is missing; it does not modify the other tables. It is not run automatically. Do not run it unless you intentionally want to add that optional table to your database.

## API reference

The running backend exposes the following routes. The other router modules in the source tree are not mounted by the current `app.main` entry point.

| Method and path | Purpose | Supported query parameters |
|---|---|---|
| `GET /` | Service name and status | - |
| `GET /health` | MySQL connectivity and required-table status | - |
| `GET /api/health` | Alias for the health response; omitted from the OpenAPI schema | - |
| `GET /api/road-segments` | List road segments | `search`, `limit`, `offset` |
| `GET /api/traffic-readings` | List traffic readings | `segment_id`, `start_time`, `end_time`, `congestion_level`, `limit`, `offset` |
| `GET /api/weather` | List weather observations | `location`, `start_time`, `end_time`, `search`, `limit`, `offset` |
| `GET /api/incidents` | List incidents | `segment_id`, `start_time`, `end_time`, `active_only`, `search`, `limit`, `offset` |
| `GET /api/recommendations` | List saved recommendations and storage availability | `limit`, `offset` |
| `POST /api/recommendations/generate` | Evaluate reading and active-incident rules; save when storage is available | `segment_id`, `start_time`, `end_time` |
| `GET /api/analytics/summary` | Summary metrics from stored readings and incidents | `segment_id`, `start_time`, `end_time` |
| `GET /api/analytics/congestion` | Counts grouped by congestion level | `segment_id`, `start_time`, `end_time` |
| `GET /api/analytics/roads` | Aggregates grouped by road segment | `segment_id`, `start_time`, `end_time` |

`start_time` and `end_time` accept ISO 8601 datetimes and must form a valid range (`start_time` on or before `end_time`). Collection endpoints that support pagination default to a bounded result size; `limit` is at most 500. The OpenAPI docs at `/docs` provide request and response schemas.

## Database schema

The application reads the existing MySQL schema `urban_traffic_db`. The table and column details below document the schema currently recorded for this project. Unless marked nullable or given a default, columns are non-null.

| Table | Columns |
|---|---|
| `road_segments` | `segment_id` INTEGER (primary key); `name` VARCHAR(100); `start_location` VARCHAR(150); `end_location` VARCHAR(150); `length_km` DECIMAL(8,3); `road_type` VARCHAR(50) |
| `traffic_readings` | `reading_id` INTEGER (primary key); `segment_id` INTEGER; `recorded_at` DATETIME; `speed_kmh` DECIMAL(7,2); `vehicle_count` INTEGER; `travel_time_minutes` DECIMAL(8,2); `congestion_level` VARCHAR(20); `data_source` VARCHAR(30), default `sample` |
| `weather_data` | `weather_id` INTEGER (primary key); `recorded_at` DATETIME; `location` VARCHAR(255); `temperature_c` FLOAT (nullable); `rainfall_mm` FLOAT (nullable); `condition` VARCHAR(100) (nullable) |
| `incidents` | `incident_id` INTEGER (primary key); `segment_id` INTEGER; `incident_type` VARCHAR(120); `description` TEXT; `start_time` DATETIME; `end_time` DATETIME (nullable) |
| `decision_recommendations` | `recommendation_id` INTEGER (auto-increment primary key); `segment_id` INTEGER (foreign key); `priority` VARCHAR(20); `recommendation_text` VARCHAR(500); `evidence_summary` TEXT; `created_at` DATETIME, default current timestamp; `status` VARCHAR(30), default `pending`; `deduplication_key` CHAR(64), unique |

The recorded foreign keys are `traffic_readings.segment_id` and `incidents.segment_id` to `road_segments.segment_id`, and `decision_recommendations.segment_id` to `road_segments.segment_id`. Weather records are not linked to road segments.

In the configured schema documented for this project, `traffic_readings.congestion_level` is VARCHAR rather than MySQL ENUM. The observed values are `low`, `moderate`, `high`, and `severe`. The application does not create, reset, or migrate the core tables. The recommendation table is optional for reading/analytics functionality, but required to persist generated recommendations.

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
