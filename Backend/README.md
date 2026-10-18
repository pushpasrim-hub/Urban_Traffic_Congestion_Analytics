# FastAPI backend

The backend reads the existing `urban_traffic_db` traffic tables using SQLAlchemy reflection. It never seeds, resets, or migrates those tables. The additive migrations create only `traffic_app_users` and `decision_recommendations`.

## Configuration and run

From the repository root:

```powershell
if (-not (Test-Path Backend\.env)) { Copy-Item .env.example Backend\.env }
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --app-dir Backend --reload --host 127.0.0.1 --port 8000
```

Set the database connection values and a unique, random `JWT_SECRET_KEY` in `Backend\.env`. Generate a secret locally with:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not commit `.env` or expose its contents.

Apply the safe additive migrations from the repository root, after the existing `road_segments` table is present:

```powershell
mysql -u your_mysql_username -p -D urban_traffic_db < Backend\migrations\001_traffic_app_users.sql
mysql -u your_mysql_username -p -D urban_traffic_db < Backend\migrations\002_decision_recommendations.sql
.\Backend\.venv\Scripts\python.exe Backend\scripts\add_recommendation_context_columns.py
.\.venv\Scripts\python.exe Backend\scripts\create_admin.py
```

Migration 002 creates the recommendation table and all fields required by the recommendation form. The context-column script is safe to run after it: it is a no-op for a new table and adds only missing nullable context columns to an older table, preserving existing records. The administrator script prompts for a username and password, hashes it with Argon2, and never prints the password.

Open `http://localhost:8000/docs` for Swagger UI, `http://localhost:8000/redoc` for ReDoc, and `http://localhost:8000/health` for API/database status. A database connection failure is reported without returning connection credentials.

## API

The Streamlit frontend authenticates at `/api/auth/login`; all `/api` traffic, analytics, CRUD, and recommendation-management endpoints require the resulting bearer token. `/health` is public for diagnostics.

`POST /api/recommendations` accepts a road segment, problem type, user-reported severity, and description. It combines those details with available traffic readings and recorded incidents, returns rule-based actions and evidence, and saves the item with status `Suggested`. It never claims an alternative route exists; it asks staff to verify a safe route from current closure information. `GET /api/recommendations` lists saved items and supports road, date, priority, and status filters. `PATCH /api/recommendations/{id}` updates actions or status (`Suggested`, `Reviewed`, or `Implemented`); `DELETE` remains available. Both the new-table migration and the additive upgrade script use nullable `problem_type` (VARCHAR(40)), `congestion_severity` (VARCHAR(20)), and `problem_description` (VARCHAR(500)) columns, matching the API's validated input limits while preserving older rows.

`GET /api/recommendations/analysis` continues to report actual reading totals, congestion-category counts, and available observed averages. The rule-based `/api/recommendations/generate` endpoint remains available for category-based suggestions.

`GET /api/recommendations/analyze` is used by the Decision Recommendations page. It analyzes the selected road for the one-hour window beginning at `start_time`, requires at least three recognized congestion readings, and returns the classified level, evidence, and an unsaved rule-based recommendation. High requires at least 50% high/severe readings; otherwise Moderate requires at least 50% moderate-or-higher readings; all other sufficient windows classify as Low. The endpoint uses stored observations only and explicitly does not represent a live feed.

For an existing deployment that only needs the recommendation table, either apply its migration or run this idempotent helper:

```powershell
python Backend\scripts\ensure_decision_recommendations_table.py
```

This helper creates only `decision_recommendations`, with an FK to `road_segments` and a unique deduplication key. It never modifies traffic tables.

No machine-learning model, traffic forecast, or future travel-time prediction is exposed by this application. The separate legacy modules in this repository are not mounted by `app.main`.

See the repository [README](../README.md) for the observed database schema, exact endpoint list, setup, and demonstration guidance.
