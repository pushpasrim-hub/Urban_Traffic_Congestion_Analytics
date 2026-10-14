# Urban Traffic Streamlit Frontend

The app communicates with FastAPI using `api_client.py`; it does not contain MySQL credentials or connect to MySQL directly. All tables, metrics and predictions come from the existing database through API calls.

## Setup and run

From `Frontend/` in a separate PowerShell terminal:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:API_BASE_URL = "http://localhost:8001/api"
streamlit run app.py
```

Configure MySQL, the JWT secret, and the first admin in `Backend/.env`, then start FastAPI in another terminal using `../Backend/README.md`.

Frontend: `http://localhost:8501`  
Backend API: `http://localhost:8001`; Swagger: `http://localhost:8001/docs`.

If `ERR_CONNECTION_REFUSED` appears, the corresponding process is stopped or the configured address/port is incorrect. Use `API_BASE_URL` to point the frontend at the API base ending in `/api`. The authenticated sidebar refresh button reloads the current page without changing its filters. The dashboard also retains its 60-second automatic refresh; record changes refresh after successful mutations.

## Screens

After sign-in, the application provides the dashboard, historical traffic analysis, congestion-cause comparisons, model-based what-if analysis, road segments, traffic readings, weather, incidents, and ML prediction/records. Dashboard filters apply to stored database readings and charts without losing the current login. Weather comparisons use matching date/hour aggregates only; no weather-to-road mapping is assumed. Prediction records are searchable and filterable but cannot be manually created or edited. Training starts only from the Train/Retrain button and runs as a background job; the page polls for progress and displays the actual completion or error. Predict runs only after the Predict button. The JWT is carried in a short-lived, one-use ticket to an HttpOnly browser cookie so page and login survive ordinary browser reloads; it is not placed in a URL. Stored readings are not represented as live traffic, and the UI does not fabricate model predictions or metrics.