# Streamlit frontend

The dashboard communicates with FastAPI through `api_client.py`. It does not connect directly to MySQL or contain database credentials.

From the repository root, after configuring `Backend\.env` and starting FastAPI:

```powershell
.\.venv\Scripts\Activate.ps1
$env:API_BASE_URL = "http://localhost:8000/api"
python -m streamlit run Frontend\app.py
```

Open **http://localhost:8501**. Set `API_BASE_URL` to the API base ending in `/api` if FastAPI is running on a different host or port. If the backend cannot be reached, the dashboard explains how to check the URL and start the service.

The app includes dashboard KPIs, date/road filters, interactive Plotly analytics, road-segment inventory, weather observations with only supported time/location matches, incident monitoring, and rule-based decision recommendations. It does not perform machine-learning or future traffic predictions.

See the repository [README](../README.md) for full setup and API details.
