# Urban Traffic Congestion Analytics & Decision Support System

A web-based traffic analytics dashboard that analyzes existing urban traffic data and provides transparent, rule-based recommendations to support traffic management decisions.

The application uses **Python, FastAPI, Streamlit, and MySQL**. Streamlit provides the interactive frontend, FastAPI handles API requests and backend processing, and MySQL stores the existing traffic data.

The system analyzes available traffic readings, road segments, weather observations, and incidents. It does **not** seed demo data, modify existing traffic tables, predict future traffic, or use machine learning.

## Features

- **Dashboard Overview:** Key metrics and charts based on available database records.
- **Traffic Analytics:** Analyze vehicle counts, speeds, travel times, and congestion levels.
- **Road Segment Monitoring:** Review road names, endpoints, lengths, and road types.
- **Weather Monitoring:** View weather observations and descriptive comparisons with traffic readings.
- **Incident Monitoring:** Review incidents and their recorded durations.
- **Decision Support:** Generate evidence-backed recommendations using predefined rules.
- **API Documentation:** Explore and test endpoints through FastAPI's interactive Swagger UI.
- **Filtering and Pagination:** Use supported road, time-range, limit, and offset parameters.

## Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python 3.11+ |
| Frontend | Streamlit |
| Backend API | FastAPI |
| Database | MySQL |
| Database integration | SQLAlchemy |
| Testing | Pytest |

## System Architecture

```text
Streamlit Frontend
        |
        | HTTP API requests
        v
FastAPI Backend
        |
        | SQLAlchemy queries
        v
Existing MySQL Database
(urban_traffic_db)
        |
        v
Analytics and rule-based recommendations
        |
        v
Results displayed in Streamlit
```

Database queries and recommendation generation remain in the backend. The Streamlit application communicates with FastAPI rather than querying MySQL directly.

## Database

The application connects to the existing MySQL database, `urban_traffic_db`.

| Table | Purpose |
|---|---|
| `road_segments` | Road segment names, locations, lengths, and road types |
| `traffic_readings` | Recorded speed, vehicle count, travel time, congestion level, and data source |
| `weather_data` | Recorded weather conditions, temperature, and rainfall |
| `incidents` | Incident types, descriptions, associated road segments, and times |
| `decision_recommendations` | Saved recommendations, priorities, supporting evidence, status, and deduplication key |

### Database relationships and notes

- `traffic_readings.segment_id` references `road_segments.segment_id`.
- `incidents.segment_id` references `road_segments.segment_id`.
- `decision_recommendations.segment_id` references `road_segments.segment_id`.
- Weather records do not have a road-segment foreign key. Weather comparisons are limited to exact road-endpoint location matches in the same recorded hour. These comparisons are descriptive and do not establish causation.
- The observed congestion categories are `low`, `moderate`, `high`, and `severe`. Other stored categories are surfaced as observed in analytics.
- The recommendation table is created separately only if needed. Its schema script is not automatically run at application startup.

**Data safety:** The application does not seed demo records, recreate existing traffic tables, or reset the database. The recommendation-table setup script creates only that table if it is absent.

## Decision-Support Rules

Recommendations use explicit, predefined rules rather than machine learning.

| Observed condition | Example suggested action |
|---|---|
| Latest reading is `high` | Review signal timing and increase monitoring |
| Latest reading is `severe` | Review diversion options and temporary traffic controls |
| An incident may still be active | Monitor incident response and review diversion options |

Recommendations include supporting reading or incident evidence. Generation requires an explicit user action and does not occur on page refresh. Existing matching recommendations are checked before insertion, and a unique evidence digest helps prevent duplicate records, including concurrent inserts.

If the recommendation table is missing or cannot safely accept the required data, the application reports that recommendations were not saved.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Root endpoint |
| GET | `/health` | Backend health check |
| GET | `/api/road-segments` | Retrieve road segments |
| GET | `/api/traffic-readings` | Retrieve traffic readings |
| GET | `/api/weather` | Retrieve weather observations |
| GET | `/api/incidents` | Retrieve incident records |
| GET | `/api/recommendations` | Retrieve saved recommendations |
| POST | `/api/recommendations/generate` | Generate eligible recommendations |
| GET | `/api/analytics/summary` | Retrieve analytics summary |
| GET | `/api/analytics/congestion` | Retrieve congestion analytics |
| GET | `/api/analytics/roads` | Retrieve road-level analytics |

Applicable traffic and analytics endpoints accept supported filters such as `segment_id`, `start_time`, and `end_time`. Collection endpoints support `limit` and `offset`. Timestamps use ISO 8601. The API validates query values and uses SQLAlchemy parameter binding.

## Requirements

- Python 3.11 or newer
- MySQL Server
- Access to the existing `urban_traffic_db` database
- Git (optional, for repository management)

## Installation and Setup

Run the following commands from the repository root in PowerShell.

### 1. Configure environment variables

If `Backend\.env` does not already exist, copy the example file:

```powershell
if (-not (Test-Path Backend\.env)) {
    Copy-Item .env.example Backend\.env
}
```

Edit `Backend\.env` and set your local MySQL credentials:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=urban_traffic_db
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password

FRONTEND_ORIGIN=http://localhost:8501
```

Replace the example username and password with your own credentials. Do not commit real credentials or `.env` files to GitHub.

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Start the FastAPI backend

From the repository root:

```powershell
python -m uvicorn app.main:app --app-dir Backend --reload --host 127.0.0.1 --port 8000
```

The backend will be available at:

- API root: `http://localhost:8000`
- Interactive API documentation: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 5. Start the Streamlit frontend

Open a second PowerShell terminal in the repository root and activate the same virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Set the API base URL:

```powershell
$env:API_BASE_URL = "http://localhost:8000/api"
```

Run Streamlit:

```powershell
python -m streamlit run Frontend\app.py
```

Open the dashboard at **http://localhost:8501**.

Both FastAPI and Streamlit must be running. The repository's `start_urban_traffic.bat` can also be used if it is configured for your local environment.

## Optional: Create the Recommendation Table

If a compatible database does not contain `decision_recommendations`, run this script from the repository root:

```powershell
python Backend\scripts\ensure_decision_recommendations_table.py
```

This script creates only the recommendation table if it is absent. It does not modify existing road, traffic, weather, or incident tables. It is not run automatically when the application starts.

## Testing

Run the focused decision-support tests from the repository root:

```powershell
python -m pytest Backend\tests\test_decision_support.py
```

## Troubleshooting

| Problem | What to check |
|---|---|
| `ERR_CONNECTION_REFUSED` | Confirm the relevant service is running and the host/port are correct. |
| Database connection error | Check MySQL is running and verify the host, port, database name, username, and password in `Backend\.env`. |
| Dashboard has empty tables | Check whether matching records exist and whether the selected filters are too restrictive. |
| API request fails | Open `http://localhost:8000/docs` and inspect the backend terminal for errors. |
| Frontend cannot reach backend | Verify `API_BASE_URL` is set to `http://localhost:8000/api` and FastAPI is running. |
| Recommendations are not saved | Check the recommendation table, schema compatibility, database permissions, and whether eligible supporting records exist. |

## Design Principles and Limitations

- **Existing-data first:** Uses the configured database rather than inserting demo records.
- **Preserves existing tables:** Does not initialize, reset, or migrate existing traffic tables.
- **Transparent recommendations:** Uses understandable, predefined rules and includes supporting evidence.
- **No machine learning:** Does not train or run ML models.
- **No forecasting:** Analyzes available records and does not predict future traffic.
- **Backend-controlled database access:** The frontend calls the API; database queries stay in the backend.
- **Descriptive weather comparisons:** Matching weather and traffic observations do not prove causation.
- **Graceful empty states:** Missing records and optional values are presented as empty states or `N/A`.

## Deployment Note

GitHub Pages hosts static websites and cannot run the complete FastAPI and Streamlit application. To make the interactive dashboard available online, deploy the Streamlit frontend and FastAPI backend to services that support them, and configure secure access to the MySQL database. Keep credentials in environment variables or the hosting provider's secret manager.

## License

Add the license that applies to this project, if one has been selected.
