import base64
import os
from html import escape
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import APIClient, APIError

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
TRAFFIC_ILLUSTRATION = base64.b64encode(
    (Path(__file__).parent / "assets" / "traffic_network.svg").read_bytes()
).decode("ascii")
TRAFFIC_ILLUSTRATION_URI = f"data:image/svg+xml;base64,{TRAFFIC_ILLUSTRATION}"
CONGESTION_LEVELS = ["low", "moderate", "high", "severe"]
NAVIGATION = [
    "Dashboard",
    "Traffic Analytics",
    "Road Segments",
    "Weather Monitoring",
    "Incident Monitoring",
    "Decision Recommendations",
]

st.set_page_config(
    page_title="Urban Traffic Analytics",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        color-scheme: light;
        --ink: #183548;
        --muted: #5d7180;
        --line: #dbe6e7;
        --paper: #f4f8f7;
        --surface: #ffffff;
        --sidebar: #edf4f3;
        --teal: #087f78;
        --teal-soft: #dff2ee;
        --coral: #e47c62;
        --shadow: 0 12px 32px rgba(24, 53, 72, .07);
    }
    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        color: var(--ink);
        font-family: Inter, "Segoe UI Variable", Aptos, ui-sans-serif, system-ui, sans-serif;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(244, 248, 247, .96); }
    [data-testid="stMainBlockContainer"] { max-width: 1540px; padding: 1.35rem 2.35rem 3rem; }
    h1, h2, h3, h4 { color: var(--ink); letter-spacing: -0.025em; }
    h1 { font-weight: 740; }
    h2, h3 { font-weight: 680; }
    p, li, [data-testid="stCaptionContainer"] p { color: var(--muted); }
    [data-testid="stSubheader"] { margin-top: 1.7rem; }
    .page-hero {
        display: flex; align-items: center; justify-content: space-between; gap: 1.6rem;
        min-height: 210px; margin: .15rem 0 1.55rem; padding: 1.7rem 2.1rem;
        overflow: hidden; border: 1px solid #d9e8e5; border-radius: 22px;
        background: linear-gradient(112deg, #fff 2%, #f1f8f6 58%, #e9f4f0 100%);
        box-shadow: var(--shadow);
    }
    .page-hero-copy { max-width: 760px; }
    .hero-eyebrow, .login-eyebrow {
        display: inline-flex; align-items: center; gap: .45rem; margin-bottom: .65rem;
        color: #08776f; font-size: .74rem; font-weight: 760; letter-spacing: .12em;
        text-transform: uppercase;
    }
    .page-hero h1 { margin: 0 0 .48rem; color: var(--ink); font-size: clamp(2rem, 3.1vw, 2.7rem); line-height: 1.12; }
    .page-hero p { max-width: 700px; margin: 0; font-size: 1.02rem; line-height: 1.6; }
    .hero-footnote { margin-top: 1rem; color: #617d83; font-size: .82rem; font-weight: 600; }
    .page-hero img { display: block; width: min(33%, 310px); min-width: 215px; border-radius: 16px; }
    .login-welcome {
        min-height: 430px; display: flex; flex-direction: column; justify-content: center;
        padding: 1rem .5rem 1rem 0;
    }
    .login-welcome h1 { margin: .15rem 0 .8rem; font-size: clamp(2.35rem, 4vw, 3.5rem); line-height: 1.08; }
    .login-welcome p { max-width: 600px; font-size: 1.08rem; line-height: 1.7; }
    .login-welcome img { width: min(100%, 550px); margin-top: 1rem; border: 1px solid #dbe9e5; border-radius: 20px; box-shadow: var(--shadow); }
    .login-panel { padding: .6rem .3rem; }
    .login-panel h2 { margin: 0 0 .35rem; }
    .login-panel [data-testid="stForm"] { margin-top: 1.2rem; }
    [data-testid="stSidebar"] {
        background: var(--sidebar);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] > div:first-child { background: transparent; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: var(--ink);
    }
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] legend {
        color: #233f51 !important;
        font-weight: 600;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        background: rgba(255, 255, 255, .52);
        border: 1px solid transparent;
        border-radius: 9px;
        padding: 7px 10px;
        margin: 2px 0;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {
        background: #fff;
        border-color: #b8d5d3;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label p {
        color: #233f51 !important;
        font-weight: 560;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
        background: var(--teal-soft);
        border-color: #9bcac5;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
        color: #075d58 !important;
        font-weight: 700;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="input"] > div,
    [data-testid="stSidebar"] [data-testid="stDateInput"] input {
        background: var(--surface);
        border-color: #bdcdd2;
        color: var(--ink);
    }
    [data-testid="stSidebar"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] [data-baseweb="input"] input,
    [data-testid="stSidebar"] [data-testid="stDateInput"] input {
        color: var(--ink);
    }
    [data-testid="stSidebar"] [data-testid="stCheckbox"] label p {
        color: #233f51 !important;
    }
    .side-brand { padding: .55rem .2rem 1rem; }
    .side-brand-mark { color: #08776f; font-size: .72rem; font-weight: 780; letter-spacing: .14em; }
    .side-brand-name { margin-top: .24rem; color: var(--ink); font-size: 1.22rem; font-weight: 760; letter-spacing: -.03em; }
    .side-brand-caption { margin-top: .12rem; color: var(--muted); font-size: .82rem; }
    .side-user { margin: .25rem 0 .35rem; color: #496270; font-size: .83rem; }
    .api-pill { display: inline-block; margin: .1rem 0 .7rem; padding: .28rem .62rem; border: 1px solid #b8ddd3; border-radius: 99px; background: #e3f4ed; color: #176d58; font-size: .76rem; font-weight: 700; }
    .side-section-label { margin: .7rem 0 .3rem; color: #72858e; font-size: .7rem; font-weight: 760; letter-spacing: .12em; }
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 17px 19px;
        box-shadow: 0 6px 20px rgba(24, 53, 72, .055);
        min-height: 112px;
    }
    [data-testid="stMetric"] [data-testid="stMetricLabel"],
    [data-testid="stMetric"] [data-testid="stMetricLabel"] p {
        color: #435969 !important;
        font-size: .88rem;
        font-weight: 620;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricValue"] div {
        color: #142f43 !important;
        font-size: 1.65rem;
        font-weight: 740;
    }
    [data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: #435969 !important;
    }
    [data-testid="stPlotlyChart"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 13px;
        padding: 5px;
        box-shadow: 0 4px 14px rgba(23, 50, 71, .04);
    }
    [data-testid="stDataFrame"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 12px;
        overflow: hidden;
    }
    [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] > div {
        border-radius: 15px;
    }
    [data-testid="stForm"] {
        padding: 1rem 1.1rem;
        border: 1px solid var(--line);
        background: rgba(255,255,255,.78);
    }
    div.stButton > button {
        border: 1px solid #b8cbd0;
        border-radius: 10px;
        color: var(--ink);
        font-weight: 680;
        min-height: 2.65rem;
        transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
    }
    div.stButton > button:hover { border-color: #80b8ae; color: #075d58; box-shadow: 0 4px 12px rgba(8,127,120,.12); transform: translateY(-1px); }
    div.stButton > button[kind="primary"] {
        background: var(--teal);
        border-color: var(--teal);
        color: #fff;
        box-shadow: 0 5px 13px rgba(8,127,120,.18);
    }
    div.stButton > button[kind="primary"]:hover {
        background: #066b66;
        border-color: #066b66;
        color: #fff;
    }
    [data-testid="stFormSubmitButton"] button[kind="primary"] {
        min-height: 2.8rem; border-radius: 10px; background: var(--teal); border-color: var(--teal);
        color: #fff; font-weight: 700; box-shadow: 0 5px 13px rgba(8,127,120,.16);
    }
    [data-testid="stFormSubmitButton"] button[kind="primary"]:hover { background: #066b66; color: #fff; }
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div {
        background: var(--surface);
        border-color: #bdcdd2;
        border-radius: 9px;
    }
    [data-baseweb="select"] *,
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea {
        color: var(--ink);
    }
    .app-caption { color: var(--muted); font-size: .96rem; line-height: 1.55; }
    @media (max-width: 900px) {
        [data-testid="stMainBlockContainer"] { padding: 1.15rem 1.2rem 2rem; }
        .page-hero { min-height: 185px; padding: 1.35rem 1.5rem; }
        .page-hero img { min-width: 180px; width: 30%; }
    }
    @media (max-width: 700px) {
        [data-testid="stMainBlockContainer"] { padding: 1.1rem .9rem 2rem; }
        .page-hero { align-items: flex-start; flex-direction: column; padding: 1.25rem; }
        .page-hero img { width: 100%; min-width: 0; max-height: 185px; object-fit: cover; }
        .login-welcome { min-height: 0; padding: .3rem 0 1rem; }
        .login-welcome img { max-height: 210px; object-fit: cover; }
        [data-testid="stMetric"] { padding: 13px 14px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def style_chart(figure: Any) -> Any:
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Inter, Arial, sans-serif", "size": 12, "color": "#294256"},
        title_font={"family": "Inter, Arial, sans-serif", "size": 17, "color": "#173247"},
        legend={
            "font": {"size": 11, "color": "#294256"},
            "title_font": {"size": 12, "color": "#173247"},
            "bgcolor": "rgba(255,255,255,0.82)",
        },
        xaxis={
            "title_font": {"size": 12, "color": "#294256"},
            "tickfont": {"size": 11, "color": "#435969"},
            "gridcolor": "#e6edef",
            "linecolor": "#cbd8dd",
            "zerolinecolor": "#cbd8dd",
        },
        yaxis={
            "title_font": {"size": 12, "color": "#294256"},
            "tickfont": {"size": 11, "color": "#435969"},
            "gridcolor": "#e6edef",
            "linecolor": "#cbd8dd",
            "zerolinecolor": "#cbd8dd",
        },
        hoverlabel={
            "bgcolor": "#173247",
            "font": {"family": "Inter, Arial, sans-serif", "color": "#ffffff"},
            "bordercolor": "#173247",
        },
    )
    return figure


def api() -> APIClient:
    client = APIClient(API_BASE_URL)
    client.set_token(st.session_state.get("access_token"))
    return client


def reset_filter_state(**values: Any) -> None:
    for key, value in values.items():
        st.session_state[key] = value


def get_records(path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    base_params = dict(params or {})
    page_size = min(int(base_params.pop("limit", 500)), 500)
    offset = int(base_params.pop("offset", 0))
    records: list[dict[str, Any]] = []
    while True:
        result = api().get(
            path,
            params={**base_params, "limit": page_size, "offset": offset},
        )
        if not isinstance(result, list):
            raise APIError(f"The API returned an unexpected response for {path}.")
        records.extend(result)
        if len(result) < page_size:
            return records
        offset += len(result)


def as_number(value: Any, precision: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):,.{precision}f}"
    except (TypeError, ValueError):
        return str(value)


def page_heading(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <section class="page-hero" aria-label="{escape(title)}">
            <div class="page-hero-copy">
                <div class="hero-eyebrow">Urban traffic · Observed data</div>
                <h1>{escape(title)}</h1>
                <p>{escape(subtitle)}</p>
                <div class="hero-footnote">Analytics and evidence-based decision support</div>
            </div>
            <img src="{TRAFFIC_ILLUSTRATION_URI}" alt="Illustration of an urban road network" />
        </section>
        """,
        unsafe_allow_html=True,
    )


def metric_cards(summary: dict[str, Any]) -> None:
    metrics = [
        ("Road segments", summary.get("total_road_segments"), 0, "network inventory"),
        ("Traffic readings", summary.get("total_traffic_readings"), 0, "selected period"),
        ("Recorded vehicles", summary.get("total_recorded_vehicles"), 0, "sum of vehicle_count"),
        ("Average observed speed (km/h)", summary.get("average_speed_kmh"), 1, "selected period"),
        ("Average observed travel time (minutes)", summary.get("average_travel_time_minutes"), 1, "selected period"),
        ("High / severe readings", summary.get("high_or_severe_readings"), 0, "selected period"),
        ("Active incidents", summary.get("active_incidents"), 0, "by incident start/end times"),
    ]
    columns = st.columns(4)
    for index, (label, value, precision, help_text) in enumerate(metrics):
        columns[index % 4].metric(label, as_number(value, precision), help=help_text)


def records_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    for column in frame.columns:
        if column.endswith("_at") or column.endswith("_time") or column in ("recorded_at", "created_at"):
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    for column in (
        "speed_kmh",
        "vehicle_count",
        "travel_time_minutes",
        "length_km",
        "temperature_c",
        "rainfall_mm",
    ):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def display_traffic_records(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={
        "recorded_at": "Recorded at",
        "speed_kmh": "Observed speed (km/h)",
        "travel_time_minutes": "Observed travel time (minutes)",
        "vehicle_count": "Recorded vehicles (vehicles)",
        "length_km": "Road length (km)",
    })


def render_road_charts(road_frame: pd.DataFrame) -> None:
    if road_frame.empty:
        st.info("No road segments are available for the selected filters.")
        return
    left, right = st.columns(2)
    if "total_vehicle_count" in road_frame:
        volumes = road_frame.dropna(subset=["total_vehicle_count"])
        with left:
            if volumes.empty:
                st.info("Vehicle-count data is not available for the selected roads.")
            else:
                road_column = "name" if "name" in volumes else "segment_id"
                figure = px.bar(
                    volumes,
                    x=road_column,
                    y="total_vehicle_count",
                    color="total_vehicle_count",
                    color_continuous_scale="Teal",
                    labels={road_column: "Road segment", "total_vehicle_count": "Vehicles recorded (vehicles)"},
                    title="Recorded vehicle volume by road",
                )
                figure.update_layout(showlegend=False, height=360, margin=dict(t=55, b=20))
                st.plotly_chart(style_chart(figure), width="stretch")
    if "average_speed_kmh" in road_frame:
        speeds = road_frame.dropna(subset=["average_speed_kmh"])
        with right:
            if speeds.empty:
                st.info("Speed data is not available for the selected roads.")
            else:
                road_column = "name" if "name" in speeds else "segment_id"
                figure = px.bar(
                    speeds,
                    x=road_column,
                    y="average_speed_kmh",
                    color="average_speed_kmh",
                    color_continuous_scale="Blues",
                    labels={road_column: "Road segment", "average_speed_kmh": "Average observed speed (km/h)"},
                    title="Average recorded speed by road",
                )
                figure.update_layout(showlegend=False, height=360, margin=dict(t=55, b=20))
                st.plotly_chart(style_chart(figure), width="stretch")

    if "average_travel_time_minutes" in road_frame:
        times = road_frame.dropna(subset=["average_travel_time_minutes"])
        if times.empty:
            st.info("Travel-time data is not available for the selected roads.")
        else:
            road_column = "name" if "name" in times else "segment_id"
            figure = px.bar(
                times,
                x=road_column,
                y="average_travel_time_minutes",
                color="average_travel_time_minutes",
                color_continuous_scale="Oranges",
                labels={road_column: "Road segment", "average_travel_time_minutes": "Average observed travel time (minutes)"},
                title="Recorded travel-time comparison by road",
            )
            figure.update_layout(showlegend=False, height=350, margin=dict(t=55, b=20))
            st.plotly_chart(style_chart(figure), width="stretch")


def render_time_series(readings: pd.DataFrame) -> None:
    if readings.empty or "recorded_at" not in readings:
        st.info("Traffic readings over time are not available for this selection.")
        return
    usable = readings.dropna(subset=["recorded_at"])
    if len(usable) < 2:
        st.info("At least two timestamped readings are needed to draw a time series.")
        return
    roads = st.session_state.get("road_name_by_id", {})
    usable = usable.copy()
    if "segment_id" in usable:
        usable["road_name"] = usable["segment_id"].map(roads).fillna("Unknown road")
    left, right = st.columns(2)
    for column, value_column, title, axis_label in (
        (left, "speed_kmh", "Observed speed over time", "Speed (km/h)"),
        (
            right,
            "travel_time_minutes",
            "Observed travel time over time",
            "Travel time (minutes)",
        ),
    ):
        with column:
            if value_column not in usable:
                st.info(f"{axis_label} is not available in the traffic readings.")
                continue
            figure = px.line(
                usable.sort_values("recorded_at"),
                x="recorded_at",
                y=value_column,
                color="road_name" if "road_name" in usable else None,
                markers=True,
                labels={
                    "recorded_at": "Recorded at",
                    value_column: axis_label,
                    "road_name": "Road",
                },
                title=title,
            )
            figure.update_layout(height=360, margin=dict(t=55, b=20))
            st.plotly_chart(style_chart(figure), width="stretch")


def load_filter_parameters(
    segment_id: int | None,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"segment_id": segment_id}
    if start_date is not None and end_date is not None:
        params["start_time"] = datetime.combine(start_date, time.min).isoformat()
        params["end_time"] = datetime.combine(
            end_date,
            time.max,
        ).isoformat()
    return params


def render_login() -> None:
    welcome, login = st.columns([1.12, .88], gap="large", vertical_alignment="center")
    with welcome:
        st.markdown(
            f"""
            <section class="login-welcome">
                <div class="login-eyebrow">🚦 Urban mobility intelligence</div>
                <h1>Understand traffic.<br/>Support better decisions.</h1>
                <p>Explore recorded road conditions, congestion patterns and incidents.
                Turn the evidence in your database into clear, practical actions.</p>
                <img src="{TRAFFIC_ILLUSTRATION_URI}" alt="Illustration of an urban road network" />
            </section>
            """,
            unsafe_allow_html=True,
        )
    with login:
        with st.container(border=True):
            st.markdown("### Welcome back")
            st.markdown("Sign in to open your traffic analytics workspace.")
            with st.form("login_form"):
                username = st.text_input("Username", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
    if submitted:
        if not username.strip() or not password:
            st.error("Enter both your username and password.")
        else:
            try:
                result = APIClient(API_BASE_URL).post(
                    "auth/login",
                    {"username": username.strip(), "password": password},
                )
                st.session_state["access_token"] = result["access_token"]
                st.session_state["authenticated_username"] = result["username"]
                st.rerun()
            except (APIError, KeyError, TypeError) as error:
                if isinstance(error, APIError):
                    st.error(str(error))
                else:
                    st.error("The API returned an invalid sign-in response.")


def render_dashboard(filters: dict[str, Any]) -> None:
    page_heading(
        "Urban Traffic Congestion Analytics",
        "A live view of recorded network activity and evidence-based operational signals.",
    )
    summary = api().get("analytics/summary", params=filters)
    metric_cards(summary)
    congestion = api().get("analytics/congestion", params=filters)
    roads = api().get("analytics/roads", params=filters)
    readings = get_records("traffic-readings", {**filters, "limit": 500})
    congestion_frame = pd.DataFrame(congestion.get("distribution", []))
    left, right = st.columns([0.85, 1.5])
    with left:
        st.subheader("Congestion distribution")
        if congestion_frame.empty or not congestion.get("total_readings"):
            st.info("No congestion readings are available for the selected filters.")
        else:
            figure = px.pie(
                congestion_frame,
                names="congestion_level",
                values="reading_count",
                hole=0.58,
                color="congestion_level",
                color_discrete_map={
                    "low": "#36a98c",
                    "moderate": "#e5b94c",
                    "high": "#e67b45",
                    "severe": "#c74747",
                },
            )
            figure.update_layout(height=330, margin=dict(t=20, b=10), legend_title_text="")
            st.plotly_chart(style_chart(figure), width="stretch")
    with right:
        st.subheader("Road performance")
        render_road_charts(pd.DataFrame(roads))

    st.subheader("Traffic readings over time")
    render_time_series(records_frame(readings))
    st.subheader("Recent recorded readings")
    recent = records_frame(readings)
    if recent.empty:
        st.info("No traffic readings match this selection.")
    else:
        if "data_source" in recent and recent["data_source"].astype(str).str.lower().eq("sample").any():
            st.caption("Some displayed records are labeled sample/demo data by their data_source field.")
        st.dataframe(display_traffic_records(recent.head(20)), width="stretch", hide_index=True)


def render_traffic_analytics(filters: dict[str, Any]) -> None:
    page_heading(
        "Traffic Analytics",
        "Compare observed traffic volume, speeds, travel times, and congestion in the selected period.",
    )
    segments = get_records("road-segments", {"limit": 500})
    road_types = sorted(
        {
            str(segment["road_type"])
            for segment in segments
            if segment.get("road_type")
        }
    )
    applied = st.session_state.get("traffic_page_filters", {})
    with st.form("traffic_analytics_filters"):
        selected_type = st.selectbox(
            "Road type",
            ["All road types", *road_types],
            index=(["All road types", *road_types].index(applied.get("road_type"))
                   if applied.get("road_type") in road_types else 0),
        )
        selected_congestion = st.selectbox(
            "Congestion level",
            ["All levels", *CONGESTION_LEVELS],
            index=(["All levels", *CONGESTION_LEVELS].index(applied.get("congestion_level"))
                   if applied.get("congestion_level") in CONGESTION_LEVELS else 0),
        )
        from_clock = st.time_input(
            "From time",
            value=time.fromisoformat(applied["from_time"])
            if applied.get("from_time")
            else time.min,
        )
        to_clock = st.time_input(
            "To time",
            value=time.fromisoformat(applied["to_time"])
            if applied.get("to_time")
            else time(23, 59, 59),
        )
        apply_filters, reset_filters = st.columns(2)
        apply_clicked = apply_filters.form_submit_button("Apply filters", type="primary")
        reset_clicked = reset_filters.form_submit_button("Reset filters")
    if apply_clicked:
        st.session_state["traffic_page_filters"] = {
            **({"road_type": selected_type} if selected_type != "All road types" else {}),
            **({"congestion_level": selected_congestion} if selected_congestion != "All levels" else {}),
            "from_time": from_clock.isoformat(),
            "to_time": to_clock.isoformat(),
        }
        st.rerun()
    if reset_clicked:
        st.session_state.pop("traffic_page_filters", None)
        st.rerun()

    filters = {**filters, **st.session_state.get("traffic_page_filters", {})}
    congestion = api().get("analytics/congestion", params=filters)
    roads = pd.DataFrame(api().get("analytics/roads", params=filters))
    readings = records_frame(get_records("traffic-readings", {**filters, "limit": 500}))

    st.subheader("Congestion-level distribution")
    counts = pd.DataFrame(congestion.get("distribution", []))
    if counts.empty or not congestion.get("total_readings"):
        st.info("No congestion readings are available for the selected filters.")
    else:
        figure = px.bar(
            counts,
            x="congestion_level",
            y="reading_count",
            color="congestion_level",
            category_orders={"congestion_level": CONGESTION_LEVELS},
            color_discrete_map={
                "low": "#36a98c",
                "moderate": "#e5b94c",
                "high": "#e67b45",
                "severe": "#c74747",
            },
            labels={"congestion_level": "Congestion level", "reading_count": "Readings"},
        )
        figure.update_layout(showlegend=False, height=330)
        st.plotly_chart(style_chart(figure), width="stretch")

    st.subheader("Road-by-road comparisons")
    render_road_charts(roads)
    st.subheader("Traffic readings over time")
    render_time_series(readings)
    st.subheader("Filtered traffic records")
    if readings.empty:
        st.info("No traffic data is available for the selected road and date range.")
    else:
        st.dataframe(display_traffic_records(readings), width="stretch", hide_index=True)


def render_roads(segments: list[dict[str, Any]]) -> None:
    clear_selection_for = st.session_state.pop("road_selection_to_clear", None)
    if clear_selection_for is not None:
        st.session_state.pop("road_edit_id", None)
        st.session_state.pop(f"confirm_delete_road_{clear_selection_for}", None)
        st.session_state.pop(f"confirm_reassign_road_{clear_selection_for}", None)
        st.session_state.pop(f"reassign_destination_road_{clear_selection_for}", None)
    road_success = st.session_state.pop("road_action_success", None)
    page_heading(
        "Road Segments",
        "Search the road network and manage road-segment records stored in MySQL.",
    )
    if road_success:
        st.success(road_success)
    if not segments:
        st.info("No road segments are recorded in the database.")
    roads = pd.DataFrame(segments)
    types = sorted(str(value) for value in roads.get("road_type", pd.Series(dtype=str)).dropna().unique())
    search = st.text_input("Search road names or locations", key="road_search")
    selected_types = st.multiselect("Road type", types, default=types, key="road_types")
    st.button(
        "Reset road filters",
        on_click=reset_filter_state,
        kwargs={"road_search": "", "road_types": types},
    )
    if selected_types and "road_type" in roads:
        roads = roads[roads["road_type"].astype(str).isin(selected_types)]
    if search.strip():
        text = roads.fillna("").astype(str).agg(" ".join, axis=1)
        roads = roads[text.str.contains(search.strip(), case=False, regex=False)]
    if roads.empty:
        st.info("No road segments match the search and road-type filters.")
    else:
        fields = [
            name for name in
            ("segment_id", "name", "start_location", "end_location", "length_km", "road_type")
            if name in roads.columns
        ]
        st.dataframe(
            roads[fields].rename(columns={
                "length_km": "Road length (km)",
                "segment_id": "Segment ID",
            }),
            width="stretch",
            hide_index=True,
        )

    segment_options = {
        int(segment["segment_id"]): segment
        for segment in segments
        if segment.get("segment_id") is not None
    }
    with st.expander("Add road segment"):
        with st.form("create_road_segment", clear_on_submit=True):
            name = st.text_input("Road name")
            start_location = st.text_input("Start location")
            end_location = st.text_input("End location")
            length_km = st.number_input("Road length (km)", min_value=0.001, step=0.1)
            road_type = st.text_input("Road type")
            create_clicked = st.form_submit_button("Create road segment", type="primary")
        if create_clicked:
            try:
                api().post("road-segments", {
                    "name": name.strip(),
                    "start_location": start_location.strip(),
                    "end_location": end_location.strip(),
                    "length_km": length_km,
                    "road_type": road_type.strip(),
                })
                st.success("Road segment saved to the database.")
                st.rerun()
            except APIError as error:
                st.error(f"Road segment was not saved: {error}")

    if segment_options:
        selected_id = st.selectbox(
            "Select a road segment to edit",
            list(segment_options),
            format_func=lambda item_id: (
                f"{segment_options[item_id].get('name', 'Unnamed road')} · #{item_id}"
            ),
            key="road_edit_id",
        )
        selected = segment_options[selected_id]
        with st.form(f"edit_road_segment_{selected_id}"):
            edited_name = st.text_input("Road name", value=str(selected.get("name") or ""))
            edited_start = st.text_input("Start location", value=str(selected.get("start_location") or ""))
            edited_end = st.text_input("End location", value=str(selected.get("end_location") or ""))
            edited_length = st.number_input(
                "Road length (km)",
                min_value=0.001,
                value=max(0.001, float(selected.get("length_km") or 0.001)),
                step=0.1,
            )
            edited_type = st.text_input("Road type", value=str(selected.get("road_type") or ""))
            save_clicked = st.form_submit_button("Save road changes", type="primary")
        if save_clicked:
            try:
                api().patch(f"road-segments/{selected_id}", {
                    "name": edited_name.strip(),
                    "start_location": edited_start.strip(),
                    "end_location": edited_end.strip(),
                    "length_km": edited_length,
                    "road_type": edited_type.strip(),
                })
                st.success("Road segment updated.")
                st.rerun()
            except APIError as error:
                st.error(f"Road segment was not updated: {error}")

        confirm_delete = st.checkbox(
            "I confirm deleting this road segment",
            key=f"confirm_delete_road_{selected_id}",
        )
        try:
            dependencies = api().get(f"road-segments/{selected_id}/dependencies")
        except APIError as error:
            dependencies = None
            st.error(f"Could not check linked records for road #{selected_id}: {error}")
        if dependencies is not None:
            linked_counts = dependencies.get("by_table", {})
            linked_total = int(dependencies.get("total", 0))
            if linked_total:
                linked_summary = ", ".join(
                    f"{count} in {table_name.replace('_', ' ')}"
                    for table_name, count in linked_counts.items()
                )
                st.warning(
                    f"Road #{selected_id} has {linked_total} linked record(s) "
                    f"({linked_summary}). It cannot be deleted until they are reassigned. "
                    "No linked records will be removed."
                )
                destinations = {
                    item_id: item
                    for item_id, item in segment_options.items()
                    if item_id != selected_id
                }
                with st.expander("Reassign Linked Records", expanded=False):
                    if not destinations:
                        st.info(
                            "Add another road segment before reassigning these linked records."
                        )
                    else:
                        destination_id = st.selectbox(
                            "Reassign linked records to",
                            list(destinations),
                            format_func=lambda item_id: (
                                f"{destinations[item_id].get('name', 'Unnamed road')} · #{item_id}"
                            ),
                            key=f"reassign_destination_road_{selected_id}",
                        )
                        st.write(
                            f"This will reassign {linked_total} linked record(s) "
                            f"({linked_summary}) to road "
                            f"#{destination_id} and then delete road #{selected_id}."
                        )
                        confirm_reassign = st.checkbox(
                            "I confirm reassigning these records and deleting the selected road",
                            key=f"confirm_reassign_road_{selected_id}",
                        )
                        if st.button(
                            "Reassign linked records and delete road",
                            disabled=not confirm_reassign,
                            key=f"reassign_delete_road_{selected_id}",
                        ):
                            try:
                                result = api().post(
                                    f"road-segments/{selected_id}/reassign-and-delete",
                                    {"destination_segment_id": destination_id},
                                )
                                reassigned = ", ".join(
                                    f"{count} {table_name.replace('_', ' ')}"
                                    for table_name, count
                                    in result.get("reassigned", {}).items()
                                )
                                st.session_state["road_action_success"] = (
                                    f"Road #{selected_id} was deleted after "
                                    f"{result.get('total_reassigned', 0)} linked record(s) "
                                    f"were reassigned to road #{destination_id}"
                                    + (f" ({reassigned})." if reassigned else ".")
                                )
                                st.session_state["road_selection_to_clear"] = selected_id
                                st.rerun()
                            except APIError as error:
                                st.error(
                                    f"Road #{selected_id} was not deleted; linked records "
                                    f"were not partially reassigned: {error}"
                                )
            else:
                st.caption("No linked records were found for this road.")
        if st.button("Delete road segment", disabled=not confirm_delete, key=f"delete_road_{selected_id}"):
            try:
                api().delete(f"road-segments/{selected_id}")
                st.session_state["road_action_success"] = (
                    f"Road segment #{selected_id} deleted."
                )
                st.session_state["road_selection_to_clear"] = selected_id
                st.rerun()
            except APIError as error:
                st.error(f"Road segment was not deleted: {error}")


def weather_traffic_comparison(
    weather: pd.DataFrame,
    readings: pd.DataFrame,
    segments: list[dict[str, Any]],
) -> pd.DataFrame:
    if weather.empty or readings.empty or not segments:
        return pd.DataFrame()
    if not {"location", "recorded_at"}.issubset(weather.columns):
        return pd.DataFrame()
    if not {"segment_id", "recorded_at", "speed_kmh"}.issubset(readings.columns):
        return pd.DataFrame()
    location_rows: list[dict[str, Any]] = []
    location_labels: dict[str, str] = {}
    for segment in segments:
        for location in (segment.get("start_location"), segment.get("end_location")):
            if location:
                location_key = str(location).strip().casefold()
                location_labels[location_key] = str(location).strip()
                location_rows.append({
                    "segment_id": segment.get("segment_id"),
                    "location_key": location_key,
                })
    if not location_rows:
        return pd.DataFrame()
    locations = pd.DataFrame(location_rows).drop_duplicates()
    weather_data = weather.copy()
    traffic_data = readings.copy()
    weather_data["location_key"] = weather_data["location"].astype(str).str.strip().str.casefold()
    weather_data["hour"] = pd.to_datetime(weather_data["recorded_at"], errors="coerce").dt.floor("h")
    traffic_data["hour"] = pd.to_datetime(traffic_data["recorded_at"], errors="coerce").dt.floor("h")
    weather_locations = weather_data.merge(locations, on="location_key", how="inner")
    if weather_locations.empty:
        return pd.DataFrame()
    matches = weather_locations.merge(
        traffic_data,
        on=["segment_id", "hour"],
        suffixes=("_weather", "_traffic"),
        how="inner",
    )
    if matches.empty:
        return pd.DataFrame()
    weather_group_columns = ["location_key", "segment_id", "hour"]
    if "condition" in weather_data:
        weather_group_columns.append("condition")
    weather_summary = (
        weather_locations.groupby(weather_group_columns, dropna=False)
        .agg(weather_observations=("recorded_at", "count"))
        .reset_index()
    )
    traffic_summary = (
        traffic_data.groupby(["segment_id", "hour"], dropna=False)
        .agg(
            matched_traffic_readings=("speed_kmh", "count"),
            average_speed_kmh=("speed_kmh", "mean"),
        )
        .reset_index()
    )
    matches = weather_summary.merge(
        traffic_summary,
        on=["segment_id", "hour"],
        how="inner",
        validate="many_to_one",
    )
    if matches.empty:
        return pd.DataFrame()
    group_columns = ["location_key"]
    if "condition" in matches:
        group_columns.append("condition")
    comparison = (
        matches.groupby(group_columns, dropna=False)
        .agg(
            matched_observations=("matched_traffic_readings", "sum"),
            average_speed_kmh=("average_speed_kmh", "mean"),
        )
        .reset_index()
    )
    comparison["location"] = comparison["location_key"].map(location_labels).fillna(
        comparison["location_key"]
    )
    return comparison.drop(columns=["location_key"])


def render_weather(
    filters: dict[str, Any],
    segments: list[dict[str, Any]],
) -> None:
    page_heading(
        "Weather Monitoring",
        "Weather observations are shown by recorded location; weather is not assumed to map to a road.",
    )
    weather_filters = {
        "start_time": filters.get("start_time"),
        "end_time": filters.get("end_time"),
        "limit": 500,
    }
    weather = get_records("weather", weather_filters)
    frame = records_frame(weather)
    if frame.empty:
        st.info("No weather data is available for the selected location and date range.")
        return
    available_fields = (
        "recorded_at",
        "location",
        "temperature_c",
        "rainfall_mm",
        "condition",
    )
    missing_fields = [field for field in available_fields if field not in frame]
    if missing_fields:
        st.caption(
            "Unavailable weather fields in this database: " + ", ".join(missing_fields)
        )
    if "location" not in frame:
        st.info("Weather location filtering and road comparison are unavailable because the location field is missing.")
        return

    locations = sorted(str(value) for value in frame.get("location", pd.Series(dtype=str)).dropna().unique())
    conditions = sorted(
        str(value)
        for value in frame.get("condition", pd.Series(dtype=str)).dropna().unique()
    )
    left_filter, right_filter = st.columns(2)
    selected_location = left_filter.selectbox(
        "Weather location", ["All locations", *locations], key="weather_location_filter"
    )
    selected_condition = right_filter.selectbox(
        "Weather condition", ["All conditions", *conditions], key="weather_condition_filter"
    )
    st.button(
        "Reset weather filters",
        on_click=reset_filter_state,
        kwargs={
            "weather_location_filter": "All locations",
            "weather_condition_filter": "All conditions",
        },
    )
    if selected_location != "All locations":
        frame = frame[frame["location"].astype(str) == selected_location]
    if selected_condition != "All conditions" and "condition" in frame:
        frame = frame[frame["condition"].astype(str) == selected_condition]
    if frame.empty:
        st.info("No weather data is available for the selected location and date range.")
        return
    for numeric_column in ("temperature_c", "rainfall_mm"):
        if numeric_column in frame:
            frame[numeric_column] = pd.to_numeric(frame[numeric_column], errors="coerce")

    metric_columns = [
        (column, label, unit)
        for column, label, unit in (
            ("temperature_c", "Average temperature", "°C"),
            ("rainfall_mm", "Average rainfall", "mm"),
        )
        if column in frame
    ]
    if metric_columns:
        weather_metrics = st.columns(len(metric_columns))
        for index, (column, label, unit) in enumerate(metric_columns):
            values = frame[column].dropna()
            weather_metrics[index].metric(
                label,
                f"{as_number(values.mean())} {unit}" if not values.empty else "N/A",
            )
    if "recorded_at" in frame:
        chart_data = frame.dropna(subset=["recorded_at"]).sort_values("recorded_at")
        chart_values = [name for name in ("temperature_c", "rainfall_mm") if name in chart_data]
        if not chart_data.empty and chart_values:
            weather_units = {"temperature_c": "Temperature (°C)", "rainfall_mm": "Rainfall (mm)"}
            for column in chart_values:
                figure = px.line(
                    chart_data,
                    x="recorded_at",
                    y=column,
                    markers=True,
                    labels={
                        "recorded_at": "Recorded at",
                        column: weather_units[column],
                    },
                    title=f"{weather_units[column]} over time",
                )
                figure.update_layout(height=330)
                st.plotly_chart(style_chart(figure), width="stretch")
    st.dataframe(
        frame.rename(columns={
            "temperature_c": "Temperature (°C)",
            "rainfall_mm": "Rainfall (mm)",
        }),
        width="stretch",
        hide_index=True,
    )

    readings = records_frame(
        get_records("traffic-readings", {**filters, "limit": 500})
    )
    comparison = weather_traffic_comparison(frame, readings, segments)
    st.subheader("Time- and location-aligned traffic comparison")
    if comparison.empty:
        st.info(
            "No exact road-endpoint location and same-hour traffic matches were found. "
            "No weather/traffic comparison is available for this selection."
        )
    else:
        st.caption(
            "Descriptive association only: observations share an exact road-endpoint location "
            "and recorded hour. This does not establish that weather caused traffic changes."
        )
        st.dataframe(comparison, width="stretch", hide_index=True)


def render_incidents(filters: dict[str, Any]) -> None:
    page_heading(
        "Incident Monitoring",
        "Incident status is derived from start_time and end_time: active records have started and have no end time or have not ended.",
    )
    incidents = records_frame(get_records("incidents", {**filters, "limit": 500}))
    required_columns = {"incident_id", "segment_id", "incident_type", "start_time", "end_time"}
    if not required_columns.issubset(incidents.columns) and not incidents.empty:
        st.info(
            "Incident monitoring is unavailable because the incidents table is missing "
            "required fields: " + ", ".join(sorted(required_columns.difference(incidents.columns)))
        )
        return
    incident_types = sorted(
        str(value)
        for value in incidents.get("incident_type", pd.Series(dtype=str)).dropna().unique()
    )
    filter_columns = st.columns(2)
    selected_type = filter_columns[0].selectbox(
        "Incident type", ["All types", *incident_types], key="incident_type_filter"
    )
    selected_status = filter_columns[1].selectbox(
        "Incident status",
        ["All statuses", "Active", "Scheduled", "Resolved"],
        key="incident_status_filter",
    )
    st.button(
        "Reset incident filters",
        on_click=reset_filter_state,
        kwargs={
            "incident_type_filter": "All types",
            "incident_status_filter": "All statuses",
        },
    )
    if selected_type != "All types" and "incident_type" in incidents:
        incidents = incidents[incidents["incident_type"].astype(str) == selected_type]
    now = pd.Timestamp.now()
    if not incidents.empty:
        if "status" in incidents:
            incidents["status_interpretation"] = (
                incidents["status"].fillna("Unknown").astype(str).str.title()
            )
            incidents["status_interpretation"] = incidents["status_interpretation"].replace(
                {"Ended": "Resolved"}
            )
        else:
            start = pd.to_datetime(incidents["start_time"], errors="coerce")
            end = pd.to_datetime(incidents["end_time"], errors="coerce")
            incidents["status_interpretation"] = "Scheduled"
            incidents.loc[
                (start <= now) & (end.isna() | (end >= now)),
                "status_interpretation",
            ] = "Active"
            incidents.loc[end < now, "status_interpretation"] = "Resolved"
    if selected_status != "All statuses":
        if "status_interpretation" in incidents:
            incidents = incidents[incidents["status_interpretation"] == selected_status]
    if incidents.empty:
        st.info("No incidents are available for the selected filters. Try changing the road, date range, or incident type.")
    else:
        if "segment_id" in incidents:
            incidents["road_segment"] = incidents["segment_id"].map(
                st.session_state.get("road_name_by_id", {})
            ).fillna("Unknown road")
        st.dataframe(incidents, width="stretch", hide_index=True)

    segments = get_records("road-segments", {"limit": 500})
    segment_names = {
        int(item["segment_id"]): str(item.get("name") or item["segment_id"])
        for item in segments
        if item.get("segment_id") is not None
    }
    if segment_names:
        with st.expander("Add incident"):
            with st.form("create_incident", clear_on_submit=True):
                segment_id = st.selectbox(
                    "Road segment",
                    list(segment_names),
                    format_func=lambda value: segment_names[value],
                )
                incident_type = st.text_input("Incident type")
                description = st.text_area("Description")
                start_date = st.date_input("Start date", value=datetime.now().date())
                start_clock = st.time_input("Start time", value=datetime.now().time().replace(second=0, microsecond=0))
                has_end = st.checkbox("Incident has an end time")
                if has_end:
                    end_date = st.date_input("End date", value=datetime.now().date())
                    end_clock = st.time_input("End time", value=datetime.now().time().replace(second=0, microsecond=0))
                create_clicked = st.form_submit_button("Create incident", type="primary")
            if create_clicked:
                start_at = datetime.combine(start_date, start_clock)
                end_at = datetime.combine(end_date, end_clock) if has_end else None
                try:
                    api().post("incidents", {
                        "segment_id": segment_id,
                        "incident_type": incident_type.strip(),
                        "description": description.strip(),
                        "start_time": start_at.isoformat(),
                        "end_time": end_at.isoformat() if end_at else None,
                    })
                    st.success("Incident saved to the database.")
                    st.rerun()
                except APIError as error:
                    st.error(f"Incident was not saved: {error}")

    all_incidents = get_records("incidents", {**filters, "limit": 500})
    incident_by_id = {
        int(item["incident_id"]): item
        for item in all_incidents
        if item.get("incident_id") is not None
    }
    if incident_by_id and segment_names:
        incident_id = st.selectbox(
            "Select an incident to edit",
            list(incident_by_id),
            format_func=lambda value: (
                f"{incident_by_id[value].get('incident_type', 'Incident')} · "
                f"{segment_names.get(incident_by_id[value].get('segment_id'), 'Unknown road')} "
                f"· #{value}"
            ),
        )
        record = incident_by_id[incident_id]
        with st.form(f"edit_incident_{incident_id}"):
            edit_segment = st.selectbox(
                "Road segment",
                list(segment_names),
                index=(list(segment_names).index(record["segment_id"])
                       if record.get("segment_id") in segment_names else 0),
            )
            edit_type = st.text_input("Incident type", value=str(record.get("incident_type") or ""))
            edit_description = st.text_area("Description", value=str(record.get("description") or ""))
            existing_start = pd.to_datetime(record.get("start_time"), errors="coerce")
            existing_end = pd.to_datetime(record.get("end_time"), errors="coerce")
            edit_start_date = st.date_input(
                "Start date",
                value=existing_start.date() if not pd.isna(existing_start) else datetime.now().date(),
                key=f"incident_start_date_{incident_id}",
            )
            edit_start_time = st.time_input(
                "Start time",
                value=existing_start.time() if not pd.isna(existing_start) else datetime.now().time().replace(second=0, microsecond=0),
                key=f"incident_start_time_{incident_id}",
            )
            edit_has_end = st.checkbox(
                "Incident has an end time",
                value=not pd.isna(existing_end),
                key=f"incident_has_end_{incident_id}",
            )
            if edit_has_end:
                edit_end_date = st.date_input(
                    "End date",
                    value=existing_end.date() if not pd.isna(existing_end) else datetime.now().date(),
                    key=f"incident_end_date_{incident_id}",
                )
                edit_end_time = st.time_input(
                    "End time",
                    value=existing_end.time() if not pd.isna(existing_end) else datetime.now().time().replace(second=0, microsecond=0),
                    key=f"incident_end_time_{incident_id}",
                )
            save_clicked = st.form_submit_button("Save incident changes", type="primary")
        if save_clicked:
            start_at = datetime.combine(edit_start_date, edit_start_time)
            end_at = datetime.combine(edit_end_date, edit_end_time) if edit_has_end else None
            try:
                api().patch(f"incidents/{incident_id}", {
                    "segment_id": edit_segment,
                    "incident_type": edit_type.strip(),
                    "description": edit_description.strip(),
                    "start_time": start_at.isoformat(),
                    "end_time": end_at.isoformat() if end_at else None,
                })
                st.success("Incident updated.")
                st.rerun()
            except APIError as error:
                st.error(f"Incident was not updated: {error}")
        confirm_delete = st.checkbox(
            "I confirm deleting this incident",
            key=f"confirm_delete_incident_{incident_id}",
        )
        if st.button(
            "Delete incident",
            disabled=not confirm_delete,
            key=f"delete_incident_{incident_id}",
        ):
            try:
                api().delete(f"incidents/{incident_id}")
                st.success("Incident deleted.")
                st.rerun()
            except APIError as error:
                st.error(f"Incident was not deleted: {error}")


def render_recommendations(segments: list[dict[str, Any]]) -> None:
    page_heading(
        "Decision Recommendations",
        "Analyze stored traffic observations for a selected road and time. This is not a live traffic feed.",
    )
    st.caption(
        "Analysis window: one hour from the selected date and time. At least 1 reading "
        "with a recognized congestion category is required. High = at least 50% high/severe; "
        "Moderate = at least 50% moderate-or-higher if the high threshold is not met; "
        "otherwise Low."
    )
    road_options = {
        int(segment["segment_id"]): str(segment.get("name") or "Unnamed road")
        for segment in segments
        if segment.get("segment_id") is not None
    }
    if not road_options:
        st.info("No road segments are available in the database. Add a road segment before generating a recommendation.")
        return

    with st.form("traffic_recommendation_analysis_form"):
        selected_segment = st.selectbox(
            "Road Name",
            list(road_options),
            format_func=lambda value: road_options[value],
        )
        selected_date = st.date_input("Date", value=date.today())
        selected_time = st.time_input("Time", value=datetime.now().replace(second=0, microsecond=0).time())
        analyze_clicked = st.form_submit_button("Analyze Traffic", type="primary", width="stretch")

    if analyze_clicked:
        selected_start = datetime.combine(selected_date, selected_time)
        st.session_state.pop("traffic_recommendation_analysis_result", None)
        try:
            with st.spinner("Analyzing stored traffic readings and matching incident records..."):
                st.session_state["traffic_recommendation_analysis_result"] = api().get(
                    "recommendations/analyze",
                    params={
                        "segment_id": selected_segment,
                        "start_time": selected_start.isoformat(timespec="seconds"),
                    },
                )
        except APIError as error:
            st.error(f"Traffic analysis could not be completed: {error}")

    result = st.session_state.get("traffic_recommendation_analysis_result")
    if not isinstance(result, dict):
        return

    st.subheader("Traffic analysis")
    st.write("**Road Name:**", result.get("road_name", ""))
    start_value = pd.to_datetime(result.get("start_time"), errors="coerce")
    end_value = pd.to_datetime(result.get("end_time"), errors="coerce")
    if not pd.isna(start_value) and not pd.isna(end_value):
        st.write(
            "**Selected time window:**",
            f"{start_value.strftime('%Y-%m-%d %H:%M')} – {end_value.strftime('%H:%M')} (one hour)",
        )
    if result.get("status") == "Insufficient Data":
        st.warning("Insufficient Data")
        st.write(result.get("evidence_summary", ""))
        return

    st.write("**Detected congestion level:**", result.get("congestion_level", ""))
    st.write(
        "**Readings used:**",
        f"{result.get('classified_reading_count', 0)} recognized "
        f"of {result.get('reading_count', 0)} stored readings.",
    )
    st.write("**Key evidence:**", result.get("evidence_summary", ""))
    st.write("**Recommendation:**", result.get("recommendation", ""))

def main() -> None:
    try:
        health = APIClient(API_BASE_URL).get("health")
    except APIError as error:
        st.title("Urban Traffic Congestion Analytics")
        if error.status_code == 503:
            st.error(f"The API is running but the database is unavailable or incomplete: {error}")
        else:
            st.error(f"FastAPI is unavailable: {error}")
        st.info(
            "Start the backend in a separate terminal and confirm API_BASE_URL "
            f"is set to {API_BASE_URL}."
        )
        st.stop()

    token = st.session_state.get("access_token")
    if not token:
        render_login()
        return
    try:
        current_user = api().get("auth/me")
        st.session_state["authenticated_username"] = current_user["username"]
        segments = get_records("road-segments", {"limit": 500})
    except APIError as error:
        if error.status_code == 401:
            st.session_state.pop("access_token", None)
            st.session_state.pop("authenticated_username", None)
            st.warning("Your session has expired. Please sign in again.")
            render_login()
            return
        st.error(f"Authenticated data could not be loaded: {error}")
        return

    st.sidebar.markdown(
        """
        <div class="side-brand">
            <div class="side-brand-mark">🚦 URBAN MOBILITY</div>
            <div class="side-brand-name">Traffic Insights</div>
            <div class="side-brand-caption">Analytics & decision support</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    username_label = escape(str(st.session_state.get("authenticated_username", "user")))
    st.sidebar.markdown(f'<div class="side-user">Signed in as <b>{username_label}</b></div>', unsafe_allow_html=True)
    api_status = escape(str(health.get("status", "unknown")).upper())
    st.sidebar.markdown(f'<div class="api-pill">● API {api_status}</div>', unsafe_allow_html=True)
    nav_labels = {
        "Dashboard": "🏠  Dashboard",
        "Traffic Analytics": "📊  Traffic Analytics",
        "Road Segments": "🛣️  Road Segments",
        "Weather Monitoring": "🌦️  Weather Monitoring",
        "Incident Monitoring": "🚧  Incident Monitoring",
        "Decision Recommendations": "💡  Decision Recommendations",
    }
    page = st.sidebar.radio(
        "Workspace",
        NAVIGATION,
        format_func=lambda item: nav_labels[item],
        label_visibility="collapsed",
    )
    if page != "Decision Recommendations" and health.get("recommendations_storage") == "missing":
        st.sidebar.warning("Recommendations cannot be saved: table missing.")
    st.sidebar.divider()
    if st.sidebar.button("Refresh data", width="stretch"):
        st.rerun()
    if st.sidebar.button("Log out", width="stretch"):
        try:
            api().post("auth/logout")
        except APIError as error:
            st.sidebar.error(f"Local sign-out completed; server token revocation failed: {error}")
        st.session_state.pop("access_token", None)
        st.session_state.pop("authenticated_username", None)
        st.rerun()

    segment_labels = {
        int(segment["segment_id"]): (
            f"{segment.get('name') or 'Unnamed road'} · #{segment['segment_id']}"
        )
        for segment in segments
        if segment.get("segment_id") is not None
    }
    segment_options: list[int | None] = [None, *segment_labels]
    st.session_state["road_name_by_id"] = segment_labels

    filters: dict[str, Any] = {}
    if page != "Decision Recommendations":
        st.sidebar.markdown('<div class="side-section-label">FILTER YOUR DATA</div>', unsafe_allow_html=True)
        st.sidebar.markdown('<div class="side-section-label">ROAD SEGMENT</div>', unsafe_allow_html=True)
        selected_segment = st.sidebar.selectbox(
            "Road segment",
            segment_options,
            format_func=lambda value: "All road segments" if value is None else segment_labels[value],
            label_visibility="collapsed",
        )
        today = datetime.now().date()
        use_date_filter = st.sidebar.checkbox(
            "Filter by date range",
            value=False,
            help="By default, analytics include all recorded history.",
        )
        start_date: date | None = None
        end_date: date | None = None
        if use_date_filter:
            start_date = st.sidebar.date_input(
                "From date",
                value=today - timedelta(days=6),
                key="global_start_date",
            )
            end_date = st.sidebar.date_input(
                "To date",
                value=today,
                key="global_end_date",
            )
            if start_date > end_date:
                st.sidebar.error("The start date must not be after the end date.")
                st.stop()

        filters = load_filter_parameters(selected_segment, start_date, end_date)
    try:
        with st.spinner("Loading selected records..."):
            if page == "Dashboard":
                render_dashboard(filters)
            elif page == "Traffic Analytics":
                render_traffic_analytics(filters)
            elif page == "Road Segments":
                render_roads(segments)
            elif page == "Weather Monitoring":
                render_weather(filters, segments)
            elif page == "Incident Monitoring":
                render_incidents(filters)
            else:
                render_recommendations(segments)
    except APIError as error:
        st.error(f"The request could not be completed: {error}")


if __name__ == "__main__":
    main()
