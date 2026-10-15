import os
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import APIClient, APIError

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
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
        --ink: #173247;
        --muted: #526575;
        --line: #d7e2e5;
        --paper: #f3f7f8;
        --surface: #ffffff;
        --sidebar: #e9f0f2;
        --teal: #087e78;
        --teal-soft: #d8eeeb;
    }
    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        color: var(--ink);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(243, 247, 248, .96); }
    [data-testid="stMainBlockContainer"] { padding-top: 1.7rem; padding-bottom: 3rem; }
    h1, h2, h3, h4 { color: var(--ink); letter-spacing: -0.025em; }
    h1 { font-weight: 740; }
    h2, h3 { font-weight: 680; }
    p, li, [data-testid="stCaptionContainer"] p { color: var(--muted); }
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
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 5px 18px rgba(23, 50, 71, .06);
        min-height: 105px;
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
    div.stButton > button {
        border: 1px solid #b8cbd0;
        border-radius: 9px;
        color: var(--ink);
        font-weight: 620;
    }
    div.stButton > button[kind="primary"] {
        background: var(--teal);
        border-color: var(--teal);
        color: #fff;
    }
    div.stButton > button[kind="primary"]:hover {
        background: #066b66;
        border-color: #066b66;
        color: #fff;
    }
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
    @media (max-width: 700px) {
        [data-testid="stMainBlockContainer"] { padding: 1.2rem .9rem 2rem; }
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
    return APIClient(API_BASE_URL)


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


def get_all_recommendations() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        result = api().get(
            "recommendations",
            params={"limit": 500, "offset": offset},
        )
        if not isinstance(result, dict):
            raise APIError("The API returned an unexpected recommendations response.")
        if not result.get("available"):
            return result
        page = result.get("items")
        if not isinstance(page, list):
            raise APIError("The API returned an unreadable recommendations list.")
        items.extend(page)
        if len(page) < 500:
            return {**result, "items": items}
        offset += len(page)


def as_number(value: Any, precision: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):,.{precision}f}"
    except (TypeError, ValueError):
        return str(value)


def page_heading(title: str, subtitle: str) -> None:
    st.title(title)
    st.markdown(f'<p class="app-caption">{subtitle}</p>', unsafe_allow_html=True)


def metric_cards(summary: dict[str, Any]) -> None:
    metrics = [
        ("Road segments", summary.get("total_road_segments"), 0, "network"),
        ("Recorded vehicles", summary.get("total_recorded_vehicles"), 0, "selected period"),
        ("Average speed", summary.get("average_speed_kmh"), 1, "km/h"),
        ("Average travel time", summary.get("average_travel_time_minutes"), 1, "minutes"),
        ("High / severe readings", summary.get("high_or_severe_readings"), 0, "selected period"),
        ("Active incidents", summary.get("active_incidents"), 0, "current, by incident times"),
    ]
    columns = st.columns(3)
    for index, (label, value, precision, help_text) in enumerate(metrics):
        columns[index % 3].metric(label, as_number(value, precision), help=help_text)


def records_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    for column in frame.columns:
        if column.endswith("_at") or column.endswith("_time") or column in ("recorded_at", "created_at"):
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


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
                figure = px.bar(
                    volumes,
                    x="name",
                    y="total_vehicle_count",
                    color="total_vehicle_count",
                    color_continuous_scale="Teal",
                    labels={"name": "Road segment", "total_vehicle_count": "Vehicles recorded"},
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
                figure = px.bar(
                    speeds,
                    x="name",
                    y="average_speed_kmh",
                    color="average_speed_kmh",
                    color_continuous_scale="Blues",
                    labels={"name": "Road segment", "average_speed_kmh": "Average speed (km/h)"},
                    title="Average recorded speed by road",
                )
                figure.update_layout(showlegend=False, height=360, margin=dict(t=55, b=20))
                st.plotly_chart(style_chart(figure), width="stretch")

    if "average_travel_time_minutes" in road_frame:
        times = road_frame.dropna(subset=["average_travel_time_minutes"])
        if times.empty:
            st.info("Travel-time data is not available for the selected roads.")
        else:
            figure = px.bar(
                times,
                x="name",
                y="average_travel_time_minutes",
                color="average_travel_time_minutes",
                color_continuous_scale="Oranges",
                labels={"name": "Road segment", "average_travel_time_minutes": "Average recorded time (minutes)"},
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
            time.max.replace(microsecond=0),
        ).isoformat()
    return params


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
        st.dataframe(recent.head(20), width="stretch", hide_index=True)


def render_traffic_analytics(filters: dict[str, Any]) -> None:
    page_heading(
        "Traffic Analytics",
        "Compare observed traffic volume, speeds, travel times, and congestion in the selected period.",
    )
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
        st.info("No traffic readings match this selection.")
    else:
        st.dataframe(readings, width="stretch", hide_index=True)


def render_roads(filters: dict[str, Any], segments: list[dict[str, Any]]) -> None:
    page_heading(
        "Road Segments",
        "Network inventory enriched with traffic statistics for the selected date range.",
    )
    stats = pd.DataFrame(api().get("analytics/roads", params=filters))
    roads = pd.DataFrame(segments)
    if roads.empty:
        st.info("No road segments are recorded in the database.")
        return
    if not stats.empty:
        roads = roads.merge(
            stats.drop(columns=[
                column
                for column in ("name", "start_location", "end_location", "length_km", "road_type")
                if column in stats.columns and column in roads.columns
            ]),
            on="segment_id",
            how="left",
            suffixes=("", "_traffic"),
        )
    search = st.text_input("Search road names or locations", key="road_search")
    types = sorted(str(value) for value in roads.get("road_type", pd.Series(dtype=str)).dropna().unique())
    selected_types = st.multiselect("Road type", types, default=types, key="road_types")
    if selected_types and "road_type" in roads:
        roads = roads[roads["road_type"].astype(str).isin(selected_types)]
    if search.strip():
        text = roads.fillna("").astype(str).agg(" ".join, axis=1)
        roads = roads[text.str.contains(search.strip(), case=False, regex=False)]
    if roads.empty:
        st.info("No road segments match the search and road-type filters.")
    else:
        st.dataframe(roads, width="stretch", hide_index=True)


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
    for segment in segments:
        for location in (segment.get("start_location"), segment.get("end_location")):
            if location:
                location_rows.append({
                    "segment_id": segment.get("segment_id"),
                    "location_key": str(location).strip().casefold(),
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
    condition_column = "condition" if "condition" in matches else None
    group_columns = ["location"]
    if condition_column:
        group_columns.append(condition_column)
    return (
        matches.groupby(group_columns, dropna=False)
        .agg(
            matched_observations=("speed_kmh", "count"),
            average_speed_kmh=("speed_kmh", "mean"),
        )
        .reset_index()
    )


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
        st.info("No weather observations match the selected date range.")
        return

    locations = sorted(str(value) for value in frame.get("location", pd.Series(dtype=str)).dropna().unique())
    selected_location = st.selectbox("Weather location", ["All locations", *locations])
    if selected_location != "All locations":
        frame = frame[frame["location"].astype(str) == selected_location]
    st.dataframe(frame, width="stretch", hide_index=True)

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
    incidents = records_frame(
        get_records("incidents", {**filters, "limit": 500})
    )
    if incidents.empty:
        st.info("No incidents match the selected filters.")
        return
    now = pd.Timestamp.now()
    start = pd.to_datetime(incidents.get("start_time"), errors="coerce")
    end = pd.to_datetime(incidents.get("end_time"), errors="coerce")
    incidents["status_interpretation"] = "Scheduled"
    incidents.loc[(start <= now) & (end.isna() | (end >= now)), "status_interpretation"] = "Active"
    incidents.loc[end < now, "status_interpretation"] = "Ended"
    selected_status = st.selectbox(
        "Incident status",
        ["All statuses", "Active", "Scheduled", "Ended"],
    )
    if selected_status != "All statuses":
        incidents = incidents[incidents["status_interpretation"] == selected_status]
    if incidents.empty:
        st.info("No incidents match that status filter.")
        return
    st.dataframe(incidents, width="stretch", hide_index=True)


def render_recommendations(filters: dict[str, Any]) -> None:
    page_heading(
        "Decision Recommendations",
        "Transparent rules use recorded high/severe congestion readings and currently active incident records. No prediction or machine learning is used.",
    )
    stored = get_all_recommendations()
    if not stored.get("available"):
        st.warning(stored.get("detail") or "Recommendation storage is unavailable.")
    else:
        st.subheader("Saved recommendations")
        saved = pd.DataFrame(stored.get("items", []))
        if saved.empty:
            st.info("There are no saved recommendations yet.")
        else:
            st.dataframe(saved, width="stretch", hide_index=True)

    if st.button("Analyze current evidence", type="primary"):
        with st.spinner("Reviewing stored traffic readings and active incidents..."):
            result = api().request(
                "POST",
                "recommendations/generate",
                params=filters,
            )
        st.session_state["latest_generated_recommendations"] = result

    result = st.session_state.get("latest_generated_recommendations")
    if result:
        if result.get("detail"):
            st.warning(result["detail"])
        st.subheader("Evidence-based recommendations")
        items = pd.DataFrame(result.get("items", []))
        if items.empty:
            st.info("No recommendations were triggered by the selected records.")
        else:
            st.caption(
                f"{result.get('generated_count', len(items))} suggestion(s) based on stored evidence; "
                f"{result.get('saved_count', 0)} saved to the database."
            )
            st.dataframe(items, width="stretch", hide_index=True)


def main() -> None:
    try:
        health = api().get("health")
        segments = get_records("road-segments", {"limit": 500})
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

    st.sidebar.title("Urban Traffic")
    st.sidebar.caption("Congestion analytics & decision support")
    st.sidebar.caption(f"API status: {health.get('status', 'unknown')}")
    if health.get("recommendations_storage") == "missing":
        st.sidebar.warning("Recommendations cannot be saved: table missing.")
    if st.sidebar.button("Refresh dashboard", width="stretch"):
        st.rerun()

    segment_labels = {
        int(segment["segment_id"]): (
            f"{segment.get('name') or 'Unnamed road'} · #{segment['segment_id']}"
        )
        for segment in segments
        if segment.get("segment_id") is not None
    }
    segment_options: list[int | None] = [None, *segment_labels]
    selected_segment = st.sidebar.selectbox(
        "Road segment",
        segment_options,
        format_func=lambda value: "All road segments" if value is None else segment_labels[value],
    )
    today = datetime.now().date()
    use_date_filter = st.sidebar.checkbox(
        "Limit to date range",
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
    page = st.sidebar.radio("Navigate", NAVIGATION, label_visibility="collapsed")
    st.session_state["road_name_by_id"] = segment_labels

    filters = load_filter_parameters(selected_segment, start_date, end_date)
    try:
        with st.spinner("Loading selected records..."):
            if page == "Dashboard":
                render_dashboard(filters)
            elif page == "Traffic Analytics":
                render_traffic_analytics(filters)
            elif page == "Road Segments":
                render_roads(filters, segments)
            elif page == "Weather Monitoring":
                render_weather(filters, segments)
            elif page == "Incident Monitoring":
                render_incidents(filters)
            else:
                render_recommendations(filters)
    except APIError as error:
        st.error(f"The request could not be completed: {error}")


if __name__ == "__main__":
    main()
