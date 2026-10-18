# Streamlit frontend

The dashboard communicates with FastAPI through `api_client.py`. It does not connect directly to MySQL or contain database credentials.

From the repository root, after configuring `Backend\.env` and starting FastAPI:

```powershell
.\.venv\Scripts\Activate.ps1
$env:API_BASE_URL = "http://localhost:8000/api"
python -m streamlit run Frontend\app.py
```

Open **http://localhost:8501** and sign in with the administrator created by `Backend\scripts\create_admin.py`. Set `API_BASE_URL` to the API base ending in `/api` if FastAPI is running on a different host or port. If the backend cannot be reached, the interface shows a friendly service/database message.

The app includes dashboard KPIs, applied road/date/congestion filters, interactive Plotly analytics, road-segment create/update/delete, weather trends and only supported time/location comparisons, incident filters and CRUD, and persistent rule-based recommendation management. Decision Recommendations accepts a road, issue type, reported severity, and description; it adds available database traffic and incident evidence, saves the recommendation, and supports status updates. Safe alternative routes are only suggested for verification, never invented. Saved recommendations survive refreshes because they are loaded from MySQL. Traffic readings remain read-only. It does not perform machine-learning or future traffic predictions.

See the repository [README](../README.md) for full setup and API details.
