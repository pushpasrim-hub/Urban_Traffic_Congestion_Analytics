import json
import os
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from api_client import APIClient, APIError

st.set_page_config(
    page_title="Urban Traffic Congestion Analytics & Decision Support System",
    page_icon="U",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        color-scheme: light;
        --ink: #173247;
        --muted: #405666;
        --line: #d9e3e6;
        --surface: #ffffff;
        --surface-raised: #f7faf9;
        --paper: #f3f7f6;
        --teal: #006b65;
        --warm: #93421f;
    }
    .stApp {
        background: var(--paper);
        color: var(--ink);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: transparent; }
    [data-testid="stHeader"] { background: rgba(243, 247, 246, 0.94); }
    [data-testid="stMainBlockContainer"] { padding-top: 2rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] {
        background: #eaf1f0;
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] > div:first-child { background: transparent; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: var(--ink); }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { color: var(--ink); }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { color: var(--teal); }
    h1, h2, h3 {
        color: var(--ink);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        letter-spacing: -0.025em;
    }
    h1 { font-size: clamp(1.8rem, 3vw, 2.55rem); font-weight: 720; line-height: 1.15; }
    h2 { font-size: clamp(1.35rem, 2vw, 1.75rem); font-weight: 680; }
    h3 { font-size: 1.15rem; font-weight: 640; }
    p, label, small, [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    [data-testid="stMarkdownContainer"] p { color: var(--muted); }
    .app-note { color: var(--muted); font-size: 0.9rem; }
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 5px 18px rgba(23, 50, 71, 0.06);
        min-height: 105px;
    }
    [data-testid="stMetricLabel"] { color: var(--muted); font-size: 0.82rem; }
    [data-testid="stMetricValue"] { color: var(--ink); font-weight: 700; }
    [data-testid="stMetricDelta"] { color: var(--warm); }
    div[data-testid="stForm"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 20px;
        box-shadow: 0 5px 18px rgba(23, 50, 71, 0.06);
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        border-bottom: 1px solid var(--line);
        gap: 0.4rem;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] { color: var(--muted); }
    [data-testid="stTabs"] [aria-selected="true"] {
        color: var(--teal);
        border-bottom-color: var(--teal);
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid var(--line);
        border-radius: 12px;
        overflow: visible;
    }
    [data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 8px;
    }
    [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 12px;
    }
    [data-testid="stAlert"] { border-radius: 12px; }
    [data-testid="stAlert"] * { color: var(--ink); }
    [data-testid="stVegaLiteChart"] svg text,
    [data-testid="stArrowVegaLiteChart"] svg text { fill: var(--ink) !important; }
    [data-baseweb="input"] > div,
    [data-baseweb="select"] > div,
    [data-baseweb="textarea"] > div {
        background-color: var(--surface);
        border-color: #bdcdd2;
        border-radius: 9px;
    }
    [data-baseweb="input"] input, [data-baseweb="textarea"] textarea { color: var(--ink); }
    [data-baseweb="input"] > div:focus-within,
    [data-baseweb="select"] > div:focus-within,
    [data-baseweb="textarea"] > div:focus-within {
        border-color: var(--teal);
        box-shadow: 0 0 0 1px rgba(8, 126, 120, 0.2);
    }
    div.stButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        border: 1px solid #b8c9ce;
        border-radius: 9px;
        color: var(--ink);
        transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
    }
    div.stButton > button *,
    div[data-testid="stFormSubmitButton"] > button * { color: inherit; }
    div[data-testid="stButton"] > button[kind^="primary"],
    div[data-testid="stFormSubmitButton"] > button[kind^="primary"] {
        background: var(--teal) !important;
        border-color: var(--teal) !important;
        color: #ffffff !important;
        box-shadow: 0 3px 10px rgba(8, 126, 120, 0.18);
    }
    div[data-testid="stButton"] > button[kind^="primary"] *,
    div[data-testid="stFormSubmitButton"] > button[kind^="primary"] * {
        color: #ffffff !important;
    }
    div.stButton > button:disabled,
    div[data-testid="stFormSubmitButton"] > button:disabled { opacity: 0.86; }
    div.stButton > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {
        border-color: var(--teal);
        box-shadow: 0 0 12px rgba(8, 126, 120, 0.16);
        transform: translateY(-1px);
    }
    @media (max-width: 900px) {
        [data-testid="stMainBlockContainer"] { padding: 1.4rem 1.25rem 2rem; }
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.8rem; }
        [data-testid="column"] { min-width: min(100%, 175px) !important; flex: 1 1 175px !important; }
    }
    @media (max-width: 520px) {
        [data-testid="stMainBlockContainer"] { padding: 1rem 0.8rem 1.5rem; }
        [data-testid="stHorizontalBlock"] { gap: 0.55rem; }
        [data-testid="column"] { min-width: 100% !important; flex-basis: 100% !important; }
        div[data-testid="stForm"] { padding: 14px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001/api")
AUTH_COOKIE_NAME = "urban_traffic_session"
CONGESTION_LEVELS = ["low", "moderate", "high", "severe"]

ENTITIES: dict[str, dict[str, Any]] = {
    "Road Segments": {
        "path": "road-segments", "pk": "segment_id", "label": "road segment",
        "fields": [
            ("name", "Road name", "text", True),
            ("start_location", "Start location", "text", True),
            ("end_location", "End location", "text", True),
            ("length_km", "Length (km)", "float", True),
            ("road_type", "Road type", "text", True),
        ],
    },
    "Traffic Readings": {
        "path": "traffic-readings", "pk": "reading_id", "label": "traffic reading",
        "fields": [
            ("segment_id", "Road segment", "segment", True),
            ("recorded_at", "Recorded at (ISO 8601)", "datetime", True),
            ("speed_kmh", "Speed (km/h)", "float", True),
            ("vehicle_count", "Vehicle count", "int", True),
            ("travel_time_minutes", "Travel time (min)", "float", True),
            ("congestion_level", "Congestion", "congestion", True),
        ],
    },
    "Weather": {
        "path": "weather", "pk": "weather_id", "label": "weather observation",
        "fields": [
            ("recorded_at", "Recorded at (ISO 8601)", "datetime", True),
            ("location", "Location", "text", True),
            ("temperature_c", "Temperature (C)", "optional_float", False),
            ("rainfall_mm", "Rainfall (mm)", "optional_float", False),
            ("condition", "Condition", "optional_text", False),
        ],
    },
    "Incidents": {
        "path": "incidents", "pk": "incident_id", "label": "incident",
        "fields": [
            ("segment_id", "Road segment", "segment", True),
            ("incident_type", "Incident type", "text", True),
            ("description", "Description", "textarea", True),
            ("start_time", "Start time (ISO 8601)", "datetime", True),
            ("end_time", "End time (ISO 8601, optional)", "optional_datetime", False),
        ],
    },
    "ML Prediction": {
        "path": "predictions", "pk": "prediction_id", "label": "prediction",
        "fields": [
            ("segment_id", "Road segment", "segment", True),
            ("predicted_for", "Predicted for (ISO 8601)", "datetime", True),
            ("predicted_speed_kmh", "Predicted speed (km/h)", "float", True),
            ("predicted_travel_time_minutes", "Predicted travel time (min)", "float", True),
            ("predicted_congestion_level", "Predicted congestion", "congestion", True),
        ],
    },
}


def api() -> APIClient:
    client = APIClient(API_BASE_URL)
    token = st.session_state.get("access_token")
    if not token and not st.session_state.get("ignore_auth_cookie"):
        token = st.context.cookies.get(AUTH_COOKIE_NAME)
    client.set_token(token)
    return client


def browser_host_matches_api() -> bool:
    frontend_host = urlsplit(f"//{st.context.headers.get('Host', '')}").hostname
    api_host = urlsplit(API_BASE_URL).hostname
    return frontend_host is not None and frontend_host.casefold() == (api_host or "").casefold()


def persist_browser_session() -> None:
    ticket = st.session_state.pop("browser_cookie_ticket", None)
    if not ticket:
        return
    if not browser_host_matches_api():
        st.error(
            "Browser-refresh sign-in requires API_BASE_URL and the Streamlit page to use the same hostname. "
            "The current sign-in remains active until this page session ends."
        )
        return
    api_base = json.dumps(API_BASE_URL.rstrip("/"))
    ticket_json = json.dumps(ticket)
    components.html(
        f"""
        <div id="session-status" style="font: 13px sans-serif; color: #506879">
          Securing this browser session…
        </div>
        <script>
        const status = document.getElementById("session-status");
        fetch({api_base} + "/auth/browser-session", {{
          method: "POST",
          credentials: "include",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ ticket: {ticket_json} }})
        }}).then(response => {{
          if (!response.ok) throw new Error("The API rejected the session request.");
          status.textContent = "Secure browser session saved.";
        }}).catch(() => {{
          status.textContent = "Refresh-session storage failed. This sign-in remains active until this page session ends.";
          status.style.color = "#9b3d2b";
        }});
        </script>
        """,
        height=32,
    )


def clear_browser_session_cookie() -> None:
    if not browser_host_matches_api():
        st.warning("The saved browser cookie could not be cleared because the API and Streamlit hostnames differ.")
        return
    api_base = json.dumps(API_BASE_URL.rstrip("/"))
    components.html(
        f"""
        <div id="session-clear-status" style="font: 13px sans-serif; color: #506879">
          Ending the saved browser session…
        </div>
        <script>
        const status = document.getElementById("session-clear-status");
        fetch({api_base} + "/auth/browser-logout", {{
          method: "POST",
          credentials: "include"
        }}).then(response => {{
          if (!response.ok) throw new Error("The API rejected the logout request.");
          status.textContent = "Saved browser session ended.";
        }}).catch(() => {{
          status.textContent = "The server-side session was ended; the browser cookie could not be cleared.";
          status.style.color = "#9b3d2b";
        }});
        </script>
        """,
        height=32,
    )


def restore_authentication() -> bool:
    token = st.session_state.get("access_token")
    if token:
        return True
    if st.session_state.get("ignore_auth_cookie"):
        return False
    token = st.context.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return False
    client = APIClient(API_BASE_URL)
    client.set_token(token)
    try:
        identity = client.get("auth/me")
    except APIError as error:
        if error.status_code == 401:
            st.session_state["ignore_auth_cookie"] = True
            st.session_state["clear_browser_session_cookie"] = True
            st.session_state["session_expired"] = True
            return False
        st.error(f"The saved sign-in could not be verified: {error}")
        st.stop()
    st.session_state["access_token"] = token
    st.session_state["username"] = identity["username"]
    return True


def parse_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()


def format_datetime(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    parsed = pd.to_datetime(value, errors="coerce")
    return "N/A" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d %H:%M")


def show_api_error(error: APIError) -> None:
    if error.status_code == 401:
        st.session_state.pop("access_token", None)
        st.session_state.pop("username", None)
        st.session_state["ignore_auth_cookie"] = True
        st.session_state["clear_browser_session_cookie"] = True
        st.session_state["session_expired"] = True
        st.rerun()
    st.error(str(error))


def fetch_segments() -> list[dict[str, Any]]:
    return api().get("road-segments", params={"limit": 500})


def segment_display(segment: dict[str, Any]) -> str:
    name = segment.get("name") or "Unnamed road"
    return f"{name} · #{segment.get('segment_id', '?')}"


def record_display(record: dict[str, Any], primary_key: str) -> str:
    description = next((str(record[key]) for key in ("name", "location", "incident_type", "congestion_level", "predicted_congestion_level") if record.get(key)), "Record")
    timestamp = next((format_datetime(record[key]) for key in ("recorded_at", "predicted_for", "start_time") if record.get(key)), "")
    return f"#{record.get(primary_key)} · {description} · {timestamp}"


def input_field(field: tuple[str, str, str, bool], value: Any, segments: list[dict[str, Any]], widget_key: str) -> Any:
    name, label, kind, required = field
    if kind == "segment":
        if not segments:
            st.warning("Add a road segment before creating linked records.")
            return None
        ids = [int(segment["segment_id"]) for segment in segments]
        labels = {int(segment["segment_id"]): segment_display(segment) for segment in segments}
        default = int(value) if value in ids else ids[0]
        selected = st.selectbox(label, ids, index=ids.index(default), format_func=lambda item: labels[item], key=widget_key)
        return selected
    if kind == "text":
        return st.text_input(label, value="" if value is None else str(value), key=widget_key)
    if kind == "textarea":
        return st.text_area(label, value="" if value is None else str(value), key=widget_key)
    if kind == "optional_text":
        return st.text_input(label, value="" if value is None else str(value), key=widget_key)
    if kind in ("datetime", "optional_datetime"):
        default = "" if value is None else str(value).replace("Z", "+00:00")
        return st.text_input(label, value=default, placeholder="2026-10-12T08:30:00", key=widget_key)
    if kind == "congestion":
        options = CONGESTION_LEVELS if required else ["N/A", *CONGESTION_LEVELS]
        selected = value if value in options else options[0]
        return st.selectbox(label, options, index=options.index(selected), key=widget_key)
    if kind in ("float", "optional_float"):
        default = 0.0 if value is None else float(value)
        optional = kind == "optional_float"
        provided = st.checkbox(f"Set {label.lower()}", value=value is not None, key=f"{widget_key}_set") if optional else True
        entered = st.number_input(label, min_value=0.0, value=max(0.0, default), step=0.5, key=widget_key, disabled=optional and not provided)
        return entered if provided else None
    if kind == "int":
        return st.number_input(label, min_value=0, value=0 if value is None else int(value), step=1, key=widget_key)
    return value


def normalize_form_value(kind: str, value: Any, required: bool) -> Any:
    if kind in ("datetime", "optional_datetime"):
        result = parse_datetime(value)
        if required and result is None:
            raise ValueError("A timestamp is required.")
        return result
    if kind == "optional_text":
        return value.strip() or None
    if kind == "congestion" and value == "N/A":
        return None
    if kind == "text" or kind == "textarea":
        result = value.strip()
        if required and not result:
            raise ValueError("Required text fields cannot be blank.")
        return result
    return value


def road_filter(segments: list[dict[str, Any]], key: str) -> int | None:
    options: list[dict[str, Any] | None] = [None, *segments]
    selected = st.selectbox(
        "Road segment",
        options,
        format_func=lambda item: "All road segments" if item is None else segment_display(item),
        key=key,
    )
    return None if selected is None else int(selected["segment_id"])


def date_time_window(key: str) -> tuple[str, str]:
    today = datetime.now().date()
    date_col, time_col, end_date_col, end_time_col = st.columns(4)
    with date_col:
        start_date = st.date_input("From date", value=today - timedelta(days=6), key=f"{key}_start_date")
    with time_col:
        start_clock = st.time_input("From time", value=datetime.min.time(), key=f"{key}_start_time")
    with end_date_col:
        end_date = st.date_input("To date", value=today, key=f"{key}_end_date")
    with end_time_col:
        end_clock = st.time_input(
            "To time",
            value=datetime.max.time().replace(microsecond=0),
            key=f"{key}_end_time",
        )
    return (
        datetime.combine(start_date, start_clock).isoformat(timespec="seconds"),
        datetime.combine(end_date, end_clock).isoformat(timespec="seconds"),
    )


@st.fragment(run_every="60s")
def dashboard() -> None:
    st.title("Urban Traffic Congestion Analytics & Decision Support System")
    st.caption("Analytics use records stored in urban_traffic_db; this application does not provide live traffic feeds.")
    try:
        health = APIClient(API_BASE_URL).get("health")
        segments = fetch_segments()
    except APIError as error:
        show_api_error(error)
        st.error(f"Dashboard data is unavailable: {error}")
        return
    if health.get("database") != "connected":
        st.error("MySQL is unavailable or required traffic tables are missing. Check Backend/.env and the existing database.")
        return
    filter_col, date_col = st.columns([1, 4])
    with filter_col:
        segment_id = road_filter(segments, "dash_segment")
    with date_col:
        start, end = date_time_window("dash")
    if start > end:
        st.error("The start date/time must be on or before the end date/time.")
        return
    st.caption(f"Reading window: {start} to {end}")
    params: dict[str, Any] = {"start_time": start, "end_time": end}
    if segment_id is not None:
        params["segment_id"] = segment_id
    try:
        client = api()
        readings = client.get("traffic-readings", params={**params, "limit": 500})
        analysis = client.get("analytics/summary", params=params)
    except APIError as error:
        show_api_error(error)
        st.error(f"Could not refresh dashboard records: {error}")
        return
    readings_frame = pd.DataFrame.from_records(readings)
    if not readings_frame.empty and "recorded_at" in readings_frame:
        readings_frame["recorded_at"] = pd.to_datetime(readings_frame["recorded_at"], errors="coerce")
        readings_frame = readings_frame.sort_values("recorded_at", ascending=False)
    latest_by_segment = analysis.get("latest_per_segment", [])
    latest_levels = analysis.get("latest_congestion_distribution", {})
    high_traffic_segments = int(latest_levels.get("high", 0)) + int(latest_levels.get("severe", 0))
    network_cols = st.columns(4)
    network_cols[0].metric("Total road segments", analysis.get("total_road_segments", 0))
    network_cols[1].metric("Total readings in range", analysis.get("total_traffic_readings", 0))
    network_cols[2].metric("Roads with high/severe congestion", high_traffic_segments)
    average_speed = analysis.get("average_traffic_speed_kmh")
    reading_count = analysis.get("total_traffic_readings", 0)
    average_speed_label = (
        ("No speed values" if reading_count else "No readings")
        if average_speed is None
        else f"{average_speed:.1f} km/h"
    )
    network_cols[3].metric("Average speed", average_speed_label)
    st.caption("High/severe roads use each road's latest reading in the selected range; the other reading metrics use all matching records.")
    if not latest_by_segment:
        st.info("No traffic readings match this road and date/time range. Select a wider range or another road.")

    st.subheader("Congestion-level distribution")
    congestion = pd.DataFrame.from_records(analysis.get("congestion_distribution", []))
    if congestion.empty:
        st.info("No congestion classifications are available in this filtered range.")
    else:
        st.bar_chart(congestion.set_index("congestion_level")["reading_count"], color="#087e78")

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.subheader("Traffic volume by time")
        volume_frame = pd.DataFrame.from_records(analysis.get("traffic_volume_by_time", []))
        if not analysis.get("traffic_volume_supported"):
            st.info("Vehicle-count data is not available in the existing traffic_readings table.")
        elif volume_frame.empty:
            st.info("No traffic-volume observations match these filters.")
        else:
            volume_frame["total_vehicle_count"] = pd.to_numeric(
                volume_frame["total_vehicle_count"], errors="coerce"
            )
            volume_frame["time"] = (
                volume_frame["date"].astype(str)
                + " "
                + volume_frame["hour"].astype(int).map(lambda hour: f"{hour:02d}:00")
            )
            st.line_chart(
                volume_frame.set_index("time")["total_vehicle_count"],
                color="#087e78",
            )
    with chart_right:
        st.subheader("Average speed by road segment")
        comparisons = pd.DataFrame.from_records(analysis.get("road_wise_average_speed", []))
        if comparisons.empty:
            st.info("No road-speed averages are available in this filtered range.")
        else:
            comparisons["average_speed_kmh"] = pd.to_numeric(
                comparisons["average_speed_kmh"], errors="coerce"
            )
            st.bar_chart(
                comparisons.set_index("name")["average_speed_kmh"],
                color="#087e78",
            )

    st.subheader("Weather versus traffic patterns")
    weather_patterns = analysis.get("weather_vs_traffic_patterns", {})
    st.caption(
        "Observed association only: weather observations are compared with readings at the same date and hour. "
        "Weather has no road-segment mapping in this database; this is not evidence of cause."
    )
    if not weather_patterns.get("available"):
        st.info(weather_patterns.get("detail", "The available weather and traffic columns do not support this comparison."))
    elif not weather_patterns.get("patterns"):
        st.info("No time-aligned weather and traffic observations are available for this filtered range.")
    else:
        pattern_frame = pd.DataFrame.from_records(weather_patterns["patterns"])
        pattern_frame["average_speed_kmh"] = pd.to_numeric(
            pattern_frame["average_speed_kmh"], errors="coerce"
        )
        pattern_frame["high_or_severe_reading_share"] = pd.to_numeric(
            pattern_frame["high_or_severe_reading_share"], errors="coerce"
        )
        weather_left, weather_right = st.columns(2)
        with weather_left:
            st.caption("Average speed by observed weather category (km/h)")
            st.bar_chart(
                pattern_frame.set_index("weather_category")["average_speed_kmh"],
                color="#087e78",
            )
        with weather_right:
            st.caption("High/severe share by observed weather category")
            st.bar_chart(
                pattern_frame.set_index("weather_category")["high_or_severe_reading_share"],
                color="#b85e34",
            )
        st.dataframe(
            pattern_frame[[
                "weather_category", "matched_readings", "weather_observations",
                "average_speed_kmh", "high_or_severe_reading_share",
            ]],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Matching traffic readings")
    if readings_frame.empty:
        st.info("No traffic readings are available for this filtered range.")
    else:
        st.dataframe(readings_frame, use_container_width=True, hide_index=True)
    st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Automatic refresh interval: 60 seconds")


def historical_analysis_page(segments: list[dict[str, Any]]) -> None:
    st.title("Historical Traffic Analysis")
    filter_col, period_col, congestion_col = st.columns([1, 1, 1])
    with filter_col:
        segment_id = road_filter(segments, "history_segment")
    with period_col:
        period = st.selectbox(
            "Time period",
            ["all", "peak", "morning_peak", "evening_peak", "off_peak", "daytime", "overnight"],
            format_func=lambda value: value.replace("_", " ").title(),
            key="history_period",
        )
    with congestion_col:
        congestion = st.selectbox("Congestion level", ["All levels", *CONGESTION_LEVELS], key="history_congestion")
    start, end = date_time_window("history")
    if start > end:
        st.error("The start date/time must be on or before the end date/time.")
        return
    params: dict[str, Any] = {
        "start_time": start,
        "end_time": end,
        "time_period": period,
        "limit": 5000,
    }
    if segment_id is not None:
        params["segment_id"] = segment_id
    if congestion != "All levels":
        params["congestion_level"] = congestion
    try:
        result = api().get("analytics/historical", params=params)
    except APIError as error:
        show_api_error(error)
        st.error(f"Historical analysis is unavailable: {error}")
        return
    records = result.get("readings", [])
    stats = result.get("statistics", {})
    st.metric("Matching readings", result.get("total_matching_readings", 0))
    if not records:
        st.info("No traffic readings match these road, date/time, time-period, and congestion filters.")
        return
    metric_cols = st.columns(3)
    metric_cols[0].metric(
        "Average speed",
        "No speed values" if stats.get("average_speed_kmh") is None else f"{stats['average_speed_kmh']:.1f} km/h",
    )
    metric_cols[1].metric(
        "Average vehicle count",
        (
            "Unsupported"
            if not stats.get("vehicle_count_supported")
            else "No vehicle counts"
            if stats.get("average_vehicle_count") is None
            else f"{stats['average_vehicle_count']:.1f} per reading"
        ),
    )
    metric_cols[2].metric(
        "Average travel time",
        "No travel-time values" if stats.get("average_travel_time_minutes") is None else f"{stats['average_travel_time_minutes']:.1f} min",
    )
    frame = pd.DataFrame.from_records(records)
    frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], errors="coerce")
    frame = frame.sort_values("recorded_at")
    trend_cols = st.columns(3)
    for column, field, label, color in (
        (trend_cols[0], "speed_kmh", "Speed (km/h)", "#087e78"),
        (trend_cols[1], "vehicle_count", "Vehicle count per reading", "#b85e34"),
        (trend_cols[2], "travel_time_minutes", "Travel time (minutes)", "#315f83"),
    ):
        with column:
            st.subheader(label)
            if field not in frame or frame[field].dropna().empty:
                st.info(f"No {label.lower()} values are available in these readings.")
            else:
                values = pd.to_numeric(frame[field], errors="coerce")
                st.line_chart(
                    pd.DataFrame({label: values.to_numpy()}, index=frame["recorded_at"]),
                    color=color,
                )
    columns = [
        name for name in (
            "recorded_at", "segment_id", "speed_kmh", "vehicle_count",
            "travel_time_minutes", "congestion_level",
        )
        if name in frame
    ]
    st.subheader("Filtered traffic readings")
    st.dataframe(
        frame[columns].sort_values("recorded_at", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def congestion_causes_page(segments: list[dict[str, Any]]) -> None:
    st.title("Congestion Cause Analysis")
    filter_col, date_col = st.columns([1, 4])
    with filter_col:
        segment_id = road_filter(segments, "causes_segment")
    with date_col:
        start, end = date_time_window("causes")
    if start > end:
        st.error("The start date/time must be on or before the end date/time.")
        return
    params: dict[str, Any] = {"start_time": start, "end_time": end}
    if segment_id is not None:
        params["segment_id"] = segment_id
    try:
        result = api().get("analytics/causes", params=params)
    except APIError as error:
        show_api_error(error)
        st.error(f"Cause analysis is unavailable: {error}")
        return
    st.caption(result.get("causality", "Observed relationships do not prove causation."))
    st.subheader("Peak versus outside-peak readings")
    peak = pd.DataFrame.from_records(result.get("peak_hour_traffic", []))
    if peak.empty:
        st.info("No traffic readings are available for this comparison and time range.")
    else:
        st.dataframe(peak, use_container_width=True, hide_index=True)
    st.subheader("Readings during versus outside recorded incident windows")
    incidents = result.get("incident_associated_congestion", {})
    incident_rows = pd.DataFrame.from_records(incidents.get("comparison", []))
    if not incidents.get("available"):
        st.info(incidents.get("detail", "Incident columns do not support this comparison."))
    elif incident_rows.empty:
        st.info("No readings are available for the incident-window comparison.")
    else:
        st.dataframe(incident_rows, use_container_width=True, hide_index=True)
        st.caption(incidents.get("interpretation", "Incident overlap is an association, not proof of cause."))
    weather = result.get("weather_related_patterns", {})
    st.subheader("Time-aligned weather and traffic")
    st.caption("No weather-to-road relationship is inferred; grouped comparisons use matching calendar date and hour only.")
    patterns = pd.DataFrame.from_records(weather.get("patterns", []))
    if not weather.get("available"):
        st.info(weather.get("detail", "Weather/traffic comparison is unavailable."))
    elif patterns.empty:
        st.info("No time-aligned weather and traffic observations are available for these filters.")
    else:
        st.dataframe(patterns, use_container_width=True, hide_index=True)


def scenario_analysis_page(segments: list[dict[str, Any]]) -> None:
    st.title("What-if Scenario Analysis & Recommendations")
    st.caption("Scenarios use the currently trained model and its supported features. They are estimates, not causal claims.")
    if not segments:
        st.info("Add a road segment and historical readings before running a scenario.")
        return
    segment_col, date_col, time_col = st.columns([2, 1, 1])
    with segment_col:
        options = {int(item["segment_id"]): item for item in segments}
        segment_id = st.selectbox(
            "Road segment",
            list(options),
            format_func=lambda item: segment_display(options[item]),
            key="scenario_segment",
        )
    with date_col:
        prediction_date = st.date_input(
            "Scenario date",
            value=datetime.now().date() + timedelta(days=1),
            key="scenario_date",
        )
    with time_col:
        prediction_time = st.time_input(
            "Scenario time",
            value=datetime.now().replace(minute=0, second=0, microsecond=0).time(),
            key="scenario_time",
        )
    if not st.button("Run model scenarios", type="primary", key="run_scenario"):
        return
    timestamp = datetime.combine(prediction_date, prediction_time).isoformat(timespec="seconds")
    try:
        result = api().post(
            "analytics/what-if",
            {"segment_id": segment_id, "predicted_for": timestamp},
            timeout=120,
        )
    except APIError as error:
        show_api_error(error)
        st.error(f"Scenario analysis was not completed: {error}")
        return
    st.write(f"**Road:** {segment_display(options[segment_id])} · **Scenario time:** {format_datetime(result.get('predicted_for'))}")
    baseline = result.get("baseline", {})
    increased = result.get("traffic_volume_increase_20_percent", {})
    baseline_cols = st.columns(3)
    for column, key, label, unit in (
        (baseline_cols[0], "predicted_travel_time_minutes", "Baseline travel time", "min"),
        (baseline_cols[1], "predicted_vehicle_count", "Baseline vehicle count", "vehicles per reading"),
        (baseline_cols[2], "predicted_congestion_level", "Baseline congestion", ""),
    ):
        value = baseline.get(key)
        display = (
            "Unavailable"
            if value is None
            else f"{value:.2f} {unit}".strip()
            if isinstance(value, (int, float))
            else str(value)
        )
        column.metric(label, display)
    if not increased.get("available"):
        st.info(increased.get("detail", "A 20% vehicle-count scenario is not supported by the available model and baseline data."))
    else:
        scenario = increased.get("prediction", {})
        st.subheader("Baseline versus 20% vehicle-count increase")
        st.caption(
            f"Modeled vehicle count: {increased.get('input_vehicle_count')} per reading. "
            "The trained model uses vehicle count as an input; this hypothetical change is not a causal estimate."
        )
        rows = []
        for key, label in (
            ("predicted_travel_time_minutes", "Travel time (minutes)"),
            ("predicted_vehicle_count", "Vehicle count (per reading)"),
            ("predicted_congestion_level", "Congestion"),
        ):
            rows.append({
                "Model output": label,
                "Baseline": baseline.get(key),
                "Scenario": scenario.get(key),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.info(result.get("rainy_weather_scenario", {}).get("detail", "Weather scenarios are unsupported by the current model."))
    st.subheader("Recommendations from this evidence")
    recommendations = result.get("recommendations", [])
    if not recommendations:
        st.info("No recommendations were generated from the available evidence.")
    else:
        for item in recommendations:
            st.markdown(f"**{item.get('recommendation', 'No recommendation')}**")
            st.caption(
                f"Evidence for {segment_display(options[segment_id])} at "
                f"{format_datetime(result.get('predicted_for'))}: "
                f"{item.get('basis', 'No supporting evidence was returned.')}"
            )
    observed_evidence = result.get("observed_evidence", {})
    if observed_evidence.get("reading_count"):
        st.caption(
            f"Measured evidence for {segment_display(options[segment_id])}: "
            f"{observed_evidence.get('high_or_severe_count', 0)} of "
            f"{observed_evidence.get('classified_reading_count', 0)} classified readings "
            f"were high/severe, from {format_datetime(observed_evidence.get('from_recorded_at'))} "
            f"through {format_datetime(observed_evidence.get('through_recorded_at'))}. "
            + result.get("recommendation_basis", "")
        )
    else:
        st.info(
            f"No recent measured readings are available for {segment_display(options[segment_id])}; "
            "recommendations rely only on supported model outputs."
        )


def rule_based_recommendation(
    result: dict[str, Any],
    road_name: str,
    predicted_for: str,
) -> tuple[str, str]:
    evidence = result.get("observed_evidence", {})
    reading_count = int(evidence.get("classified_reading_count") or 0)
    high_count = int(evidence.get("high_or_severe_count") or 0)
    observed_basis = (
        f"{high_count} of {reading_count} classified recent readings were high or severe "
        f"({evidence.get('from_recorded_at')} through {evidence.get('through_recorded_at')})."
        if reading_count
        else "No classified recent readings were available for an observed-pattern comparison."
    )
    level = str(result.get("predicted_congestion_level") or "").lower()
    if level in {"high", "severe"}:
        return (
            f"Monitor {road_name} at {format_datetime(predicted_for)} and compare the next stored reading.",
            f"The trained model estimates {level} congestion for the selected prediction time. {observed_basis}",
        )
    if reading_count and high_count:
        return (
            f"Continue monitoring {road_name} at {format_datetime(predicted_for)} against new readings.",
            observed_basis,
        )
    return (
        f"Insufficient evidence for a congestion recommendation for {road_name} at {format_datetime(predicted_for)}.",
        f"No high/severe model output or elevated recent-reading pattern was available. {observed_basis}",
    )


def entity_page(entity_name: str) -> None:
    config = ENTITIES[entity_name]
    st.title(entity_name)
    if entity_name == "ML Prediction":
        st.caption("Predictions are produced by the trained model; stored model outputs are searchable and filterable, not manually editable.")
        try:
            segments = fetch_segments()
            ml_panel(segments)
        except APIError as error:
            show_api_error(error)
            st.error(f"Could not load model or road-segment data: {error}")
            return
        st.subheader("Model-generated prediction records")
        filter_cols = st.columns([1, 1])
        with filter_cols[0]:
            segment_id = road_filter(segments, "prediction_records_segment")
        with filter_cols[1]:
            search = st.text_input("Search predictions", key="prediction_records_search")
        start, end = date_time_window("prediction_records")
        if start > end:
            st.error("The start date/time must be on or before the end date/time.")
            return
        params: dict[str, Any] = {
            "from_time": start,
            "to_time": end,
            "limit": 500,
        }
        if segment_id is not None:
            params["segment_id"] = segment_id
        if search:
            params["search"] = search
        try:
            records = api().get(config["path"], params=params)
        except APIError as error:
            show_api_error(error)
            st.error(f"Could not load prediction records: {error}")
            return
        if records:
            st.dataframe(pd.DataFrame.from_records(records), use_container_width=True, hide_index=True)
        else:
            st.info("No model-generated prediction records match these filters.")
        return
    try:
        records = api().get(config["path"], params={"limit": 500})
        segments = fetch_segments() if entity_name != "Road Segments" else []
    except APIError as error:
        show_api_error(error)
        st.error(f"Could not load {config['label']} records: {error}")
        return
    view_tab, create_tab, edit_tab, delete_tab = st.tabs(["Records", "Create", "Edit", "Delete"])
    with view_tab:
        search = st.text_input("Search records", key=f"{entity_name}_search")
        visible = records
        if search:
            needle = search.casefold()
            visible = [row for row in records if needle in str(row).casefold()]
        if visible:
            st.dataframe(pd.DataFrame.from_records(visible), use_container_width=True, hide_index=True)
        else:
            st.info("No matching records are available in MySQL.")

    with create_tab:
        with st.form(f"create_{config['path']}", clear_on_submit=True):
            st.subheader(f"Add {config['label']}")
            values = {}
            for field in config["fields"]:
                name, _, kind, required = field
                values[name] = input_field(field, None, segments, f"new_{config['path']}_{name}")
            submitted = st.form_submit_button("Save record", type="primary")
        if submitted:
            try:
                payload = {name: normalize_form_value(kind, values[name], required) for name, _, kind, required in config["fields"]}
                api().post(config["path"], payload)
                st.success("Record saved to MySQL.")
                st.rerun()
            except (APIError, ValueError) as error:
                if isinstance(error, APIError):
                    show_api_error(error)
                st.error(str(error))

    primary_key = config["pk"]
    if records:
        options = {record_display(row, primary_key): row for row in records}
        chosen_label = st.selectbox("Select a record", list(options), key=f"selected_{config['path']}")
        chosen = options[chosen_label]
        record_id = chosen[primary_key]
        with edit_tab:
            with st.form(f"edit_{config['path']}"):
                st.subheader(f"Edit {config['label']} #{record_id}")
                values = {}
                for field in config["fields"]:
                    name, _, kind, required = field
                    values[name] = input_field(field, chosen.get(name), segments, f"edit_{config['path']}_{name}")
                submitted = st.form_submit_button("Update record", type="primary")
            if submitted:
                try:
                    payload = {name: normalize_form_value(kind, values[name], required) for name, _, kind, required in config["fields"]}
                    api().put(f"{config['path']}/{record_id}", payload)
                    st.success("Record updated in MySQL.")
                    st.rerun()
                except (APIError, ValueError) as error:
                    if isinstance(error, APIError):
                        show_api_error(error)
                    st.error(str(error))
        with delete_tab:
            st.warning(f"Delete {record_display(chosen, primary_key)}? This cannot be undone.")
            confirmed = st.checkbox("I confirm this deletion", key=f"confirm_delete_{config['path']}")
            if st.button("Delete selected record", disabled=not confirmed, key=f"delete_{config['path']}"):
                try:
                    api().delete(f"{config['path']}/{record_id}")
                    st.success("Record deleted.")
                    st.rerun()
                except APIError as error:
                    show_api_error(error)
                    st.error(str(error))
    else:
        with edit_tab:
            st.info("There are no records to edit.")
        with delete_tab:
            st.info("There are no records to delete.")


def metric_display(value: Any, precision: int = 3) -> str:
    if not isinstance(value, (int, float)) or not isfinite(value):
        return "Unavailable"
    return f"{value:.{precision}f}"


def metric_percentage(value: Any) -> str:
    if not isinstance(value, (int, float)) or not isfinite(value):
        return "Unavailable"
    return f"{value:.1%}"


@st.fragment(run_every="2s")
def show_training_progress(job_id: str) -> None:
    try:
        job = api().get(f"ml/train/{job_id}")
    except APIError as error:
        if error.status_code == 404:
            st.session_state.pop("training_job_id", None)
            st.query_params.pop("training_job_id", None)
            st.session_state["model_training_error"] = (
                "Training status is no longer available. The backend may have restarted; "
                "check model status before starting another run."
            )
            st.rerun()
        show_api_error(error)
        st.error(f"Could not check model-training progress: {error}")
        return

    if job["status"] in {"queued", "running"}:
        st.info(f"Model training {job['status']}: {job['progress']}")
    elif job["status"] == "completed":
        result = job.get("result")
        if not isinstance(result, dict) or "total_rows" not in result:
            st.session_state.pop("training_job_id", None)
            st.query_params.pop("training_job_id", None)
            st.session_state["model_training_error"] = (
                "The training worker marked the job complete without returning its training-row result."
            )
            st.rerun()
        st.session_state["model_training_notice"] = (
            f"Training completed from {result['total_rows']} eligible historical database readings."
        )
        st.session_state.pop("training_job_id", None)
        st.query_params.pop("training_job_id", None)
        st.rerun()
    else:
        detail = job.get("error") or "The training worker returned no error detail."
        st.session_state.pop("training_job_id", None)
        st.query_params.pop("training_job_id", None)
        st.session_state["model_training_error"] = detail
        st.rerun()


def ml_panel(segments: list[dict[str, Any]]) -> None:
    st.subheader("Prediction models")
    training_notice = st.session_state.pop("model_training_notice", None)
    if training_notice:
        st.success(training_notice)
    training_error = st.session_state.pop("model_training_error", None)
    if training_error:
        st.error(f"Model training failed: {training_error}")
    job_id = st.session_state.get("training_job_id") or st.query_params.get("training_job_id")
    if job_id:
        st.session_state["training_job_id"] = job_id
        show_training_progress(job_id)
    try:
        status = api().get("ml/status")
    except APIError as error:
        show_api_error(error)
        st.error(f"Model status unavailable: {error}")
        return
    models = status.get("models", {})
    if status.get("available"):
        st.success(f"{status.get('model_name')} · trained {format_datetime(status.get('trained_at'))} · {status.get('total_rows', 'N/A')} historical readings")
        if status.get("validation_method"):
            st.caption(status["validation_method"])
    else:
        st.info(status.get("detail", "No loadable trained models are available. Historical data is still needed."))
        st.caption(
            "No model output or holdout metric can be verified until training completes with eligible historical rows."
        )
        eligible = status.get("eligible_rows", {})
        if eligible:
            st.caption(
                f"Historical eligible rows: travel time {eligible.get('travel_time', 'N/A')}, "
                f"vehicle count {eligible.get('traffic_volume', 'N/A')}, "
                f"congestion {eligible.get('congestion', 'N/A')}; minimum per output: "
                f"{status.get('minimum_training_rows', 'N/A')}."
            )
    output_labels = {
        "travel_time": "Travel-time regression · target minutes",
        "traffic_volume": "Traffic-volume regression · target vehicles per reading",
        "congestion": "Congestion classification",
    }
    for model_name, label in output_labels.items():
        model = models.get(model_name, {})
        with st.expander(label, expanded=not model.get("available", False)):
            if not model.get("available"):
                st.caption(model.get("detail", "This model has not been trained."))
                st.caption("Validation metrics are unavailable because this model was not evaluated on eligible holdout rows.")
                continue
            validation_period = model.get("validation_period", {})
            period_label = (
                f"{format_datetime(validation_period.get('start'))}–"
                f"{format_datetime(validation_period.get('end'))}"
                if validation_period
                else "date range unavailable in this artifact"
            )
            st.caption(
                f"Chronological holdout: {model.get('training_rows', 'Unavailable')} earlier training rows and "
                f"{model.get('validation_rows', 'Unavailable')} later validation rows "
                f"({period_label}). Evaluation metrics below are measured on this holdout only."
            )
            metrics = model.get("metrics", {})
            if not metrics:
                st.warning("No valid holdout metrics are available for this model; its accuracy cannot be assessed from the saved artifact.")
            elif model_name == "congestion":
                metric_cols = st.columns(4)
                metric_cols[0].metric("Holdout accuracy", metric_percentage(metrics.get("accuracy")))
                metric_cols[1].metric("Weighted precision", metric_percentage(metrics.get("precision_weighted")))
                metric_cols[2].metric("Weighted recall", metric_percentage(metrics.get("recall_weighted")))
                metric_cols[3].metric("Weighted F1", metric_percentage(metrics.get("f1_weighted")))
                labels = metrics.get("confusion_matrix_labels", [])
                matrix = metrics.get("confusion_matrix")
                if labels and matrix:
                    st.caption("Confusion matrix · rows are actual labels, columns are predicted labels.")
                    st.dataframe(pd.DataFrame(matrix, index=labels, columns=labels), use_container_width=True)
            else:
                unit = model.get("unit", "")
                metric_cols = st.columns(3)
                metric_cols[0].metric("Holdout MAE", f"{metric_display(metrics.get('mae'), 2)} {unit}".strip())
                metric_cols[1].metric("Holdout RMSE", f"{metric_display(metrics.get('rmse'), 2)} {unit}".strip())
                metric_cols[2].metric("Holdout R²", metric_display(metrics.get("r2")))
                if not isinstance(metrics.get("r2"), (int, float)):
                    st.caption(
                        model.get("validation_details", {}).get(
                            "r2",
                            "R² is unavailable because the saved artifact does not contain a valid holdout R² score.",
                        )
                    )
                baseline = model.get("baseline", {}).get("metrics", {})
                if baseline:
                    baseline_parts = [
                        f"{label} {metric_display(baseline.get(key), precision)}"
                        for key, label, precision in (
                            ("mae", "MAE", 2),
                            ("rmse", "RMSE", 2),
                            ("r2", "R²", 3),
                        )
                        if isinstance(baseline.get(key), (int, float)) and isfinite(baseline[key])
                    ]
                    if baseline_parts:
                        st.caption(f"Dummy baseline — {'; '.join(baseline_parts)} {unit}.")
            if model_name == "congestion":
                baseline = model.get("baseline", {}).get("metrics", {})
                if baseline:
                    baseline_parts = [
                        f"{label} {metric_percentage(baseline.get(key))}"
                        for key, label in (
                            ("accuracy", "accuracy"),
                            ("precision_weighted", "weighted precision"),
                            ("recall_weighted", "weighted recall"),
                            ("f1_weighted", "weighted F1"),
                        )
                        if isinstance(baseline.get(key), (int, float)) and isfinite(baseline[key])
                    ]
                    if baseline_parts:
                        st.caption(f"Most-frequent baseline — {'; '.join(baseline_parts)}.")
                unseen = model.get("validation_labels_not_seen_in_training", [])
                if unseen:
                    st.warning("The chronological validation period includes labels absent from the training period: " + ", ".join(unseen))
            st.caption("Features: " + ", ".join(model.get("feature_names", [])))
    for limitation in status.get("limitations", []):
        st.caption(f"Limitation: {limitation}")
    st.caption(
        "Holdout metrics are measured before the final model is refit on all eligible history; they describe "
        "past held-out readings, not the verified accuracy of any future prediction. A prediction's accuracy "
        "cannot be checked until an actual reading exists for its requested time."
    )
    if st.button(
        "Train / retrain model",
        type="primary",
        key="train_model",
        disabled=bool(job_id),
    ):
        try:
            job = api().post("ml/train", timeout=20)
            job_id = job["job_id"]
            st.session_state["training_job_id"] = job_id
            st.query_params["training_job_id"] = job_id
            st.rerun()
        except (APIError, KeyError) as error:
            if isinstance(error, APIError):
                show_api_error(error)
            st.error(f"Model training could not be started: {error}")

    st.subheader("Predict future traffic")
    st.caption("Inputs are derived from the selected road's latest stored readings; no sample values are inserted.")
    if not segments:
        st.info("Add a road segment before predicting.")
        return
    segment_ids = [int(item["segment_id"]) for item in segments]
    by_id = {int(item["segment_id"]): item for item in segments}
    with st.form("predict_travel_time"):
        segment_id = st.selectbox("Road segment", segment_ids, format_func=lambda key: segment_display(by_id[key]))
        prediction_date = st.date_input("Prediction date", value=datetime.now().date() + timedelta(days=1), key="prediction_date")
        prediction_time = st.time_input("Prediction time", value=datetime.now().replace(minute=0, second=0, microsecond=0).time(), key="prediction_time")
        save = st.checkbox("Save prediction to MySQL", value=True)
        include_what_if = st.checkbox("Include hypothetical what-if comparisons", value=True)
        submit = st.form_submit_button("Predict", type="primary")
    if submit:
        try:
            payload = {
                "segment_id": segment_id,
                "predicted_for": datetime.combine(prediction_date, prediction_time).isoformat(timespec="seconds"),
                "save": save,
            }
            fingerprint = json.dumps(payload, sort_keys=True)
            submitted_at = monotonic()
            previous_submission = st.session_state.get("prediction_submission")
            if (
                previous_submission
                and previous_submission["fingerprint"] == fingerprint
                and submitted_at - previous_submission["submitted_at"] < 5
            ):
                idempotency_key = previous_submission["idempotency_key"]
            else:
                idempotency_key = str(uuid4())
            st.session_state["prediction_submission"] = {
                "fingerprint": fingerprint,
                "idempotency_key": idempotency_key,
                "submitted_at": submitted_at,
            }
            with st.spinner("Loading the trained models and calculating prediction outputs…"):
                result = api().post(
                    "ml/predict",
                    payload,
                    headers={"Idempotency-Key": idempotency_key},
                )
            st.session_state["prediction_submission"]["submitted_at"] = monotonic()
            if result.get("idempotent_replay"):
                st.info(
                    "This repeat submission was recognized as the same prediction action; "
                    "the existing result was returned without inserting another history row."
                )
            selected_road = result.get("segment_name") or segment_display(by_id[segment_id])
            selected_prediction_time = result.get("predicted_for") or payload["predicted_for"]
            prediction_day = datetime.fromisoformat(
                str(selected_prediction_time).replace("Z", "+00:00")
            ).date()
            today = datetime.now().date()
            record_start_key = "prediction_records_start_date"
            record_end_key = "prediction_records_end_date"
            current_start = st.session_state.get(record_start_key, today - timedelta(days=6))
            current_end = st.session_state.get(record_end_key, today)
            st.session_state[record_start_key] = min(current_start, prediction_day)
            st.session_state[record_end_key] = max(current_end, prediction_day)
            st.markdown(f"**Selected road:** {selected_road}")
            prediction_cols = st.columns([1.15, 1.8, 1.1])
            prediction_values = [
                ("Travel time · model output", result.get("predicted_travel_time_minutes"), "min"),
                ("Vehicle count per reading · model output", result.get("predicted_vehicle_count"), "vehicles"),
                ("Congestion · model output", result.get("predicted_congestion_level"), ""),
            ]
            for column, (label, value, unit) in zip(prediction_cols, prediction_values):
                display = "Unavailable" if value is None else f"{value:.2f} {unit}".strip() if isinstance(value, (int, float)) else str(value)
                column.metric(label, display)
            speed = result.get("average_speed_kmh")
            speed_display = "Unavailable" if speed is None else f"{speed:.2f} km/h"
            st.metric("Derived speed (not a model output)", speed_display)
            st.caption(
                f"Prediction for {format_datetime(selected_prediction_time)}. "
                "This is a model estimate, not a verified outcome. It cannot be checked for accuracy "
                "until an observed reading for this time is available."
            )
            inputs = result.get("model_inputs", {})
            def input_display(value: Any) -> str:
                return "Unavailable" if value is None else str(value)

            with st.expander("Model inputs, supported features & limitations"):
                st.dataframe(pd.DataFrame([
                    {"Input": "Average speed (km/h)", "Value": input_display(inputs.get("speed_kmh")), "Source": inputs.get("speed_source", "Unavailable")},
                    {"Input": "Average vehicle count", "Value": input_display(inputs.get("vehicle_count")), "Source": inputs.get("vehicle_count_source", "Unavailable")},
                    {"Input": "Historical congestion", "Value": input_display(inputs.get("congestion_level")), "Source": inputs.get("congestion_source", "Unavailable")},
                    {"Input": "Prediction hour / day", "Value": f"{inputs.get('prediction_hour', 'Unavailable')}:00 / {inputs.get('prediction_day_of_week', 'Unavailable')}", "Source": "Requested future time"},
                    {"Input": "Road length (km)", "Value": input_display(inputs.get("road_length_km")), "Source": "Selected road record"},
                    {"Input": "Historical readings used", "Value": input_display(inputs.get("historical_readings_used")), "Source": "Up to 10 latest stored readings"},
                ]), use_container_width=True, hide_index=True)
                feature_names = inputs.get("feature_names", {})
                if feature_names:
                    st.caption("Trained feature sets: " + "; ".join(
                        f"{name}: {', '.join(names)}" for name, names in feature_names.items()
                    ))
                st.caption(
                    "Vehicle count is an estimate returned by the model, but traffic_predictions has no "
                    "predicted_vehicle_count column, so it is not persisted. Weather is not a trained feature "
                    "and weather rows are not mapped to roads."
                )
                context = result.get("context", {})
                weather = context.get("weather")
                if weather:
                    st.write(f"Weather context: {weather.get('condition') or 'Unavailable'} · {weather.get('location') or 'Location unavailable'} · {format_datetime(weather.get('recorded_at'))}. Not road-specific.")
                else:
                    st.write("Weather context: no stored observation is available; no road-specific weather effect is inferred.")
                active_incidents = context.get("active_incidents", [])
                st.write(f"Active incidents for selected road: {len(active_incidents)}" if active_incidents else "Active incidents for selected road: none recorded.")
                if active_incidents:
                    st.dataframe(pd.DataFrame.from_records(active_incidents), use_container_width=True, hide_index=True)
            recommendation, recommendation_basis = rule_based_recommendation(
                result, selected_road, str(selected_prediction_time)
            )
            st.info(f"Recommendation: {recommendation}")
            st.caption(f"Evidence for {selected_road} at {format_datetime(selected_prediction_time)}: {recommendation_basis}")
            observed_evidence = result.get("observed_evidence", {})
            if observed_evidence.get("reading_count"):
                st.caption(
                    f"Observed pattern: {observed_evidence.get('high_or_severe_count', 0)} of "
                    f"{observed_evidence.get('classified_reading_count', 0)} classified readings "
                    f"were high/severe, from {format_datetime(observed_evidence.get('from_recorded_at'))} "
                    f"through {format_datetime(observed_evidence.get('through_recorded_at'))}."
                )
            else:
                st.caption("Observed pattern: no recent readings were available for comparison.")
            unavailable = result.get("unavailable_outputs", {})
            if unavailable:
                st.warning("Model outputs unavailable: " + "; ".join(f"{name}: {detail}" for name, detail in unavailable.items()))
            if result.get("saved"):
                st.success("Supported prediction fields were saved to MySQL; the filtered records table below was reloaded.")
            elif save:
                st.warning("No prediction field supported by the existing traffic_predictions columns was available to save; no record was inserted.")
            if result.get("unsupported_persistence_fields"):
                st.warning("Predicted vehicle count was returned for this request but not saved: traffic_predictions has no predicted_vehicle_count column. The existing schema was not changed.")
            st.caption("Model outputs and metrics are based only on the trained pipeline and historical MySQL readings.")
            if include_what_if:
                st.subheader("Hypothetical what-if comparisons")
                st.caption("Scenario changes are model simulations, not proven causal effects.")
                try:
                    with st.spinner("Comparing supported hypothetical scenarios..."):
                        scenario_result = api().post("ml/what-if", {
                            "segment_id": segment_id,
                            "predicted_for": payload["predicted_for"],
                        }, timeout=120)
                except APIError as scenario_error:
                    show_api_error(scenario_error)
                    st.warning(f"The prediction succeeded, but scenario analysis is unavailable: {scenario_error}")
                else:
                    st.caption(scenario_result.get("interpretation", "Hypothetical scenario results."))
                    for scenario in scenario_result.get("scenarios", []):
                        st.markdown(f"**{scenario.get('name', 'Scenario').replace('_', ' ').title()}**")
                        if not scenario.get("supported"):
                            st.info(scenario.get("detail", "This scenario is not supported by the trained model and available data."))
                            continue
                        st.caption("Hypothetical scenario input: " + str(scenario.get("input_vehicle_count", "N/A")) + " vehicles per reading.")
                        predictions = scenario.get("predictions", {})
                        comparison_rows = [
                            {"Output": label, **predictions.get(key, {})}
                            for key, label in (
                                ("predicted_travel_time_minutes", "Travel time (minutes)"),
                                ("predicted_vehicle_count", "Traffic volume (vehicles per reading)"),
                                ("predicted_congestion_level", "Congestion level"),
                            )
                            if key in predictions
                        ]
                        if comparison_rows:
                            st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)
        except (APIError, ValueError) as error:
            if isinstance(error, APIError):
                show_api_error(error)
            st.error(f"Prediction unavailable: {error}")


def login_screen() -> None:
    login_copy, login_art = st.columns([1.3, 1], vertical_alignment="center")
    with login_copy:
        st.title("Urban Traffic Congestion Analytics & Decision Support System")
        st.caption("Sign in to view database-backed traffic analysis and manage records.")
        if st.session_state.pop("session_expired", False):
            st.warning("Your session expired. Sign in again.")
    with login_art:
        asset_path = Path(__file__).parent / "assets" / "traffic_network.svg"
        if asset_path.is_file():
            st.image(str(asset_path), use_container_width=True)
        st.caption("Illustration only; all analytics come from your database.")
    try:
        status = APIClient(API_BASE_URL).get("health")
        if status.get("database") != "connected":
            st.error("FastAPI is online, but MySQL is unavailable or its existing traffic tables are missing.")
    except APIError as error:
        st.error(str(error))
        st.info("Start FastAPI in a separate terminal and verify API_BASE_URL. ERR_CONNECTION_REFUSED means that service is stopped or its host/port is incorrect.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        try:
            response = APIClient(API_BASE_URL).post("auth/login", {"username": username, "password": password})
            st.session_state["access_token"] = response["access_token"]
            st.session_state["username"] = response["username"]
            st.session_state.pop("ignore_auth_cookie", None)
            try:
                ticket = api().post("auth/browser-cookie-ticket")
                st.session_state["browser_cookie_ticket"] = ticket["ticket"]
                st.session_state.pop("auth_persistence_error", None)
            except (APIError, KeyError) as error:
                st.session_state["auth_persistence_error"] = str(error)
            st.rerun()
        except APIError as error:
            st.error("Invalid login." if error.status_code == 401 else str(error))


if st.session_state.pop("clear_browser_session_cookie", False):
    clear_browser_session_cookie()

if not restore_authentication():
    login_screen()
    st.stop()

persist_browser_session()

if st.session_state.get("auth_persistence_error"):
    st.warning(
        "You are signed in for this Streamlit session, but browser-refresh sign-in could not be saved: "
        + st.session_state.pop("auth_persistence_error")
    )

with st.sidebar:
    st.markdown("### Urban Traffic Congestion Analytics & Decision Support System")
    st.caption(f"Signed in as {st.session_state.get('username', 'user')}")
    pages = [
        "Dashboard",
        "Historical Traffic Analysis",
        "Congestion Cause Analysis",
        "What-if Scenario Analysis",
        *ENTITIES.keys(),
    ]
    selected_page = st.query_params.get("page", "Dashboard")
    if selected_page not in pages:
        selected_page = "Dashboard"
    if "page" not in st.query_params:
        st.query_params["page"] = selected_page

    def persist_selected_page() -> None:
        st.query_params["page"] = st.session_state["workspace_page"]

    navigation = st.radio(
        "Workspace",
        pages,
        index=pages.index(selected_page),
        key="workspace_page",
        on_change=persist_selected_page,
        label_visibility="collapsed",
    )
    st.caption("Refresh reloads this page's database-backed data without changing its filters.")
    if st.button("Refresh current page", icon=":material/refresh:", use_container_width=True):
        st.rerun()
    if st.button("Sign out", use_container_width=True):
        try:
            api().post("auth/logout")
        except APIError as error:
            show_api_error(error)
            st.error(f"Sign-out was not confirmed by the backend: {error}")
        else:
            st.session_state.pop("access_token", None)
            st.session_state.pop("username", None)
            st.session_state.pop("training_job_id", None)
            st.query_params.pop("training_job_id", None)
            st.session_state["ignore_auth_cookie"] = True
            st.session_state["clear_browser_session_cookie"] = True
            st.rerun()

if navigation == "Dashboard":
    dashboard()
elif navigation == "Historical Traffic Analysis":
    try:
        historical_analysis_page(fetch_segments())
    except APIError as error:
        show_api_error(error)
        st.error(f"Could not load road-segment filters: {error}")
elif navigation == "Congestion Cause Analysis":
    try:
        congestion_causes_page(fetch_segments())
    except APIError as error:
        show_api_error(error)
        st.error(f"Could not load road-segment filters: {error}")
elif navigation == "What-if Scenario Analysis":
    try:
        scenario_analysis_page(fetch_segments())
    except APIError as error:
        show_api_error(error)
        st.error(f"Could not load road-segment filters: {error}")
else:
    entity_page(navigation)