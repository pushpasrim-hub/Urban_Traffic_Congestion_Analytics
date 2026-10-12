# Urban Traffic Streamlit Frontend

The app communicates with FastAPI using `api_client.py`; it does not contain MySQL credentials or connect to MySQL directly. All tables, metrics and predictions come from the existing database through API calls.

## Setup and run

From `Frontend/` in a separate PowerShell terminal:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:API_BASE_URL = "http://127.0.0.1:8000/api"
streamlit run app.py
```

Configure MySQL, the JWT secret, and the first admin in `Backend/.env`, then start FastAPI in another terminal using `../Backend/README.md`.

Frontend: `http://localhost:8501`  
Backend API: `http://127.0.0.1:8000`  
Swagger: `http://127.0.0.1:8000/docs`

If `ERR_CONNECTION_REFUSED` appears, the corresponding process is stopped or the configured address/port is incorrect. Use `API_BASE_URL` to point the frontend at the API base ending in `/api`. The dashboard refreshes every 60 seconds; record changes also refresh immediately after successful mutations.

## Screens

Dashboard, Road Segments, Traffic Readings, Weather, Incidents, and Predictions & ML are available after sign-in. Forms use road-segment selectors from the API, and deletions require explicit confirmation. Weather is presented by its stored location and time, not attributed to a selected road. The prediction UI calls the backend model and never calculates or fills in demo predictions.