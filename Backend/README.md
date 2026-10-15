# FastAPI backend

The backend reads the existing `urban_traffic_db` MySQL tables. It uses runtime SQLAlchemy reflection and does not alter, seed, reset, or drop existing traffic tables. The missing `decision_recommendations` table was added separately and is not created automatically at startup.

## Configuration and run

From the repository root:

```powershell
if (-not (Test-Path Backend\.env)) { Copy-Item .env.example Backend\.env }
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --app-dir Backend --reload --host 127.0.0.1 --port 8000
```

Set database credentials in `Backend\.env`. The API uses `DB_HOST`, `DB_PORT`, `DB_NAME`, and `DB_USER`/`DB_PASSWORD`. Do not commit `.env`.

Open `http://localhost:8000/docs` for Swagger UI, `http://localhost:8000/redoc` for ReDoc, and `http://localhost:8000/health` for API/database status. A database connection failure is reported without returning connection credentials.

## API

The Streamlit frontend calls the read-only data endpoints and analytics routes under `/api`. `POST /api/recommendations/generate` evaluates actual latest high/severe readings and active incident records using explicit rules. It checks for a matching saved recommendation before inserting. Recommendation saving is skipped with a clear message if the optional `decision_recommendations` table is missing or has required fields the application cannot safely fill.

If another deployment lacks this table, run from the repository root:

```powershell
python Backend\scripts\ensure_decision_recommendations_table.py
```

This idempotent command creates only `decision_recommendations`, with an FK to the existing `road_segments` table and a unique deduplication key. It never modifies other tables.

No machine-learning model, traffic forecast, or future travel-time prediction is exposed by this application. The separate legacy modules in this repository are not mounted by `app.main`.

See the repository [README](../README.md) for the observed database schema, exact endpoint list, setup, and demonstration guidance.
