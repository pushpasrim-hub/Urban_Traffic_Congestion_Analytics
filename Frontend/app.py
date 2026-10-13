import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from api_client import APIClient, APIError

st.set_page_config(
    page_title="Urban Traffic | Operations",
    page_icon="U",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --ink:#172b2a; --muted:#627572; --line:#dce6e2; --paper:#f5f8f6; --green:#146b58; --lime:#d8ed87; --coral:#c95c45; }
    .stApp { background:var(--paper); color:var(--ink); }
    [data-testid="stSidebar"] { background:#e8efeb; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2 { color:var(--ink); }
    h1,h2,h3 { color:var(--ink); letter-spacing:0; }
    h1 { font-family:Georgia,serif; font-size:2.1rem; }
    [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:6px; padding:14px 16px; }
    [data-testid="stMetricLabel"] { color:var(--muted); }
    [data-testid="stMetricValue"] { color:var(--green); }
    div[data-testid="stForm"] { background:#fff; border:1px solid var(--line); border-radius:6px; padding:18px; }
    .app-kicker { color:var(--green); text-transform:uppercase; font-size:0.76rem; font-weight:700; letter-spacing:0.12em; }
    .app-note { color:var(--muted); font-size:0.9rem; }
    div.stButton > button[kind="primary"] { background:var(--green); border-color:var(--green); }
    </style>
    """,
    unsafe_allow_html=True,
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")
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
    "Predictions & ML": {
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
    client.set_token(st.session_state.get("access_token"))
    return client


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


@st.fragment(run_every="60s")
def dashboard() -> None:
    st.markdown('<div class="app-kicker">Operations / live records</div>', unsafe_allow_html=True)
    st.title("Urban Traffic Congestion Analysis and Travel Time Prediction System")
    st.caption("Analysis reflects the records currently stored in urban_traffic_db.")
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
    if not segments:
        st.info("No road segments are stored yet. Add a segment in Road Segments to begin.")
        return

    left, start_date_col, start_time_col, end_date_col, end_time_col, refresh = st.columns([2, 1, 1, 1, 1, 0.8])
    with left:
        selected = st.selectbox("Road segment", segments, format_func=segment_display, key="dash_segment")
    today = datetime.now().date()
    with start_date_col:
        start_date = st.date_input("From date", value=today - timedelta(days=6), key="dash_start_date")
    with start_time_col:
        start_clock = st.time_input("From time", value=datetime.min.time(), key="dash_start_clock")
    with end_date_col:
        end_date = st.date_input("To date", value=today, key="dash_end_date")
    with end_time_col:
        end_clock = st.time_input("To time", value=datetime.max.time().replace(microsecond=0), key="dash_end_clock")
    with refresh:
        st.write("")
        if st.button("Refresh", icon=":material/refresh:", use_container_width=True):
            st.rerun()
    segment_id = int(selected["segment_id"])
    start = datetime.combine(start_date, start_clock).isoformat(timespec="seconds")
    end = datetime.combine(end_date, end_clock).isoformat(timespec="seconds")
    if start > end:
        st.error("The start date/time must be on or before the end date/time.")
        return
    st.caption(f"Reading window: {start} to {end}")
    try:
        client = api()
        readings = client.get("traffic-readings", params={"segment_id": segment_id, "start_time": start, "end_time": end, "limit": 500})
        active_incidents = client.get("incidents", params={"segment_id": segment_id, "active_only": "true", "limit": 100})
        weather = client.get("weather", params={"start_time": start, "end_time": end, "limit": 100})
        predictions = client.get("predictions", params={"segment_id": segment_id, "from_time": start, "to_time": end, "limit": 100})
        analysis = client.get("analytics/summary", params={"start_time": start, "end_time": end})
    except APIError as error:
        show_api_error(error)
        st.error(f"Could not refresh dashboard records: {error}")
        return
    readings_frame = pd.DataFrame.from_records(readings)
    if not readings_frame.empty and "recorded_at" in readings_frame:
        readings_frame["recorded_at"] = pd.to_datetime(readings_frame["recorded_at"], errors="coerce")
        readings_frame = readings_frame.sort_values("recorded_at", ascending=False)
    latest_row = readings_frame.iloc[0].to_dict() if not readings_frame.empty else {}
    latest_by_segment = analysis.get("latest_per_segment", [])
    latest_levels = analysis.get("latest_congestion_distribution", {})
    classified_segments = sum(int(latest_levels.get(level, 0)) for level in CONGESTION_LEVELS)
    high_traffic_segments = int(latest_levels.get("high", 0)) + int(latest_levels.get("severe", 0))
    network_cols = st.columns(4)
    network_cols[0].metric("Total road segments", analysis.get("total_road_segments", "N/A"))
    network_status = f"{high_traffic_segments}/{classified_segments} high/severe" if classified_segments else "N/A"
    network_cols[1].metric("Current network status", network_status)
    network_cols[2].metric("Segments with readings", len(latest_by_segment) if latest_by_segment else "N/A")
    network_cols[3].metric("Segments classified", classified_segments if classified_segments else "N/A")
    st.caption("Network status is calculated from the latest in-range reading for each road segment.")
    road_cols = st.columns(4)
    road_cols[0].metric("Latest speed", "N/A" if latest_row.get("speed_kmh") is None else f"{latest_row['speed_kmh']} km/h")
    road_cols[1].metric("Traffic volume", "N/A" if latest_row.get("vehicle_count") is None else f"{latest_row['vehicle_count']} vehicles per reading")
    road_cols[2].metric("Observed travel time", "N/A" if latest_row.get("travel_time_minutes") is None else f"{latest_row['travel_time_minutes']} min")
    road_cols[3].metric("Latest congestion", latest_row.get("congestion_level") or "N/A")

    chart_left, chart_right = st.columns(2)
    frame = readings_frame.copy()
    if frame.empty:
        st.info("No traffic readings exist in this time window.")
    else:
        for field in ("speed_kmh", "travel_time_minutes"):
            if field in frame:
                frame[field] = pd.to_numeric(frame[field], errors="coerce")
        with chart_left:
            st.subheader("Speed trend · km/h")
            if "speed_kmh" in frame:
                st.line_chart(frame.dropna(subset=["recorded_at"]).sort_values("recorded_at").set_index("recorded_at")["speed_kmh"])
            else:
                st.info("Speed column is unavailable in the existing readings.")
        with chart_right:
            st.subheader("Travel-time trend · minutes")
            if "travel_time_minutes" in frame:
                st.line_chart(frame.dropna(subset=["recorded_at"]).sort_values("recorded_at").set_index("recorded_at")["travel_time_minutes"])
            else:
                st.info("Travel-time column is unavailable in the existing readings.")
        st.subheader("Recent traffic readings")
        if "vehicle_count" in frame:
            frame["vehicle_count"] = pd.to_numeric(frame["vehicle_count"], errors="coerce")
        st.subheader("Historical readings · vehicle counts are per reading")
        st.dataframe(frame.sort_values("recorded_at", ascending=False), use_container_width=True, hide_index=True)

    st.subheader("Network analysis")
    analysis_cols = st.columns([1.4, 1, 1])
    comparisons = pd.DataFrame.from_records(analysis.get("segment_comparison", []))
    with analysis_cols[0]:
        st.caption("Segment comparison · average travel time (min)")
        if not comparisons.empty and "average_travel_time_minutes" in comparisons:
            comparisons["average_travel_time_minutes"] = pd.to_numeric(comparisons["average_travel_time_minutes"], errors="coerce")
            st.bar_chart(comparisons.set_index("name")["average_travel_time_minutes"])
        else:
            st.info("No segment comparison data in this time window.")
    with analysis_cols[1]:
        st.caption("Busiest observation hours · readings per hour block")
        busiest = analysis.get("busiest_hours", [])
        if busiest:
            busiest_frame = pd.DataFrame.from_records(busiest)
            busiest_frame["hour"] = busiest_frame["hour"].map(lambda hour: f"{int(hour):02d}:00")
            st.dataframe(busiest_frame, use_container_width=True, hide_index=True)
        else:
            st.info("No hourly traffic data.")
    with analysis_cols[2]:
        st.caption("Latest congestion by road segment")
        if classified_segments:
            congestion = pd.DataFrame({"congestion_level": CONGESTION_LEVELS, "segment_count": [int(latest_levels.get(level, 0)) for level in CONGESTION_LEVELS]})
            st.bar_chart(congestion.set_index("congestion_level")["segment_count"])
        else:
            st.info("No in-range latest congestion classifications are stored.")

    lower_left, lower_right = st.columns(2)
    with lower_left:
        st.subheader("Active incidents")
        st.caption("Currently active incidents for the selected road; status is evaluated now, independent of the historical reading window.")
        if active_incidents:
            st.dataframe(pd.DataFrame.from_records(active_incidents), use_container_width=True, hide_index=True)
        else:
            st.info("No active incidents for this segment.")
        st.subheader("Stored predictions")
        if predictions:
            st.dataframe(pd.DataFrame.from_records(predictions), use_container_width=True, hide_index=True)
        else:
            st.info("No stored predictions for this segment.")
    with lower_right:
        st.subheader("Recent weather observations")
        st.caption("Location-based observations; no road relationship is assumed.")
        if weather:
            latest_weather = weather[0]
            st.write(f"**{latest_weather.get('location') or 'Location unavailable'}** · {format_datetime(latest_weather.get('recorded_at'))}")
            weather_values = {key: latest_weather.get(key) for key in ("temperature_c", "rainfall_mm", "condition") if latest_weather.get(key) is not None}
            if weather_values:
                st.json(weather_values)
            st.dataframe(pd.DataFrame.from_records(weather), use_container_width=True, hide_index=True)
        else:
            st.info("No weather observations are stored.")
    recommendation = rule_based_recommendation(
        latest_row.get("congestion_level"),
        [item.get("predicted_congestion_level") for item in predictions],
    )
    st.info(f"Rule-based recommendation: {recommendation}")
    st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Refresh interval: 60 seconds")


def rule_based_recommendation(current_congestion: Any, predicted_levels: list[Any]) -> str:
    severity = {"low": 0, "moderate": 1, "high": 2, "severe": 3}
    actual_levels = [str(level).lower() for level in predicted_levels if str(level).lower() in severity]
    if actual_levels:
        forecast = max(actual_levels, key=severity.get)
        if severity[forecast] >= 2:
            return f"Stored model predictions include {forecast} congestion; allow extra travel time and monitor conditions. This is not an alternate-route recommendation."
    level = str(current_congestion).lower() if current_congestion is not None else ""
    if level in severity and severity[level] >= 2:
        return f"The latest selected-road reading is {level}; allow extra travel time and monitor the next reading. This is not an alternate-route recommendation."
    if level in severity:
        return f"The latest selected-road reading is {level}; continue monitoring the time-filtered traffic trend."
    return "There is not enough current or predicted congestion data to recommend an action."


def entity_page(entity_name: str) -> None:
    config = ENTITIES[entity_name]
    st.markdown('<div class="app-kicker">Data management</div>', unsafe_allow_html=True)
    st.title(entity_name)
    if entity_name == "Predictions & ML":
        st.caption("Create predictions through the trained backend model; stored prediction records remain editable and removable.")
    try:
        records = api().get(config["path"], params={"limit": 500})
        segments = fetch_segments() if entity_name != "Road Segments" else []
    except APIError as error:
        show_api_error(error)
        st.error(f"Could not load {config['label']} records: {error}")
        return

    if entity_name == "Predictions & ML":
        ml_panel(segments)

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

    if entity_name == "Predictions & ML":
        st.info("New prediction rows are created by the ML prediction form above; manual prediction values are not fabricated.")
    else:
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


def ml_panel(segments: list[dict[str, Any]]) -> None:
    st.subheader("Prediction models")
    try:
        status = api().get("ml/status")
    except APIError as error:
        show_api_error(error)
        st.error(f"Model status unavailable: {error}")
        return
    models = status.get("models", {})
    if status.get("available"):
        st.success(f"{status.get('model_name')} · trained {format_datetime(status.get('trained_at'))} · {status.get('total_rows', 'N/A')} historical readings")
    else:
        st.info(status.get("detail", "No loadable trained models are available. Historical data is still needed."))
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
                continue
            st.caption(f"Chronological holdout: {model.get('training_rows')} training rows, {model.get('validation_rows')} later validation rows.")
            metrics = model.get("metrics", {})
            if model_name == "congestion":
                metric_cols = st.columns(4)
                metric_cols[0].metric("Validation accuracy", f"{metrics['accuracy']:.3f}" if metrics.get("accuracy") is not None else "N/A")
                metric_cols[1].metric("Weighted precision", f"{metrics['precision_weighted']:.3f}" if metrics.get("precision_weighted") is not None else "N/A")
                metric_cols[2].metric("Weighted recall", f"{metrics['recall_weighted']:.3f}" if metrics.get("recall_weighted") is not None else "N/A")
                metric_cols[3].metric("Weighted F1", f"{metrics['f1_weighted']:.3f}" if metrics.get("f1_weighted") is not None else "N/A")
                labels = metrics.get("confusion_matrix_labels", [])
                matrix = metrics.get("confusion_matrix")
                if labels and matrix:
                    st.caption("Confusion matrix · rows are actual labels, columns are predicted labels.")
                    st.dataframe(pd.DataFrame(matrix, index=labels, columns=labels), use_container_width=True)
            else:
                unit = model.get("unit", "")
                metric_cols = st.columns(3)
                metric_cols[0].metric("Validation MAE", f"{metrics['mae']:.2f} {unit}" if metrics.get("mae") is not None else "N/A")
                metric_cols[1].metric("Validation RMSE", f"{metrics['rmse']:.2f} {unit}" if metrics.get("rmse") is not None else "N/A")
                metric_cols[2].metric("R²", f"{metrics['r2']:.3f}" if metrics.get("r2") is not None else "N/A")
                baseline = model.get("baseline", {}).get("metrics", {})
                if baseline:
                    st.caption(
                        f"Dummy baseline — MAE {baseline.get('mae', float('nan')):.2f} {unit}; "
                        f"RMSE {baseline.get('rmse', float('nan')):.2f} {unit}; "
                        f"R² {baseline.get('r2', float('nan')):.3f}."
                    )
            if model_name == "congestion":
                baseline = model.get("baseline", {}).get("metrics", {})
                if baseline:
                    st.caption(
                        f"Most-frequent baseline — accuracy {baseline.get('accuracy', float('nan')):.3f}; "
                        f"weighted precision {baseline.get('precision_weighted', float('nan')):.3f}; "
                        f"weighted recall {baseline.get('recall_weighted', float('nan')):.3f}; "
                        f"weighted F1 {baseline.get('f1_weighted', float('nan')):.3f}."
                    )
                unseen = model.get("validation_labels_not_seen_in_training", [])
                if unseen:
                    st.warning("The chronological validation period includes labels absent from the training period: " + ", ".join(unseen))
            st.caption("Features: " + ", ".join(model.get("feature_names", [])))
    for limitation in status.get("limitations", []):
        st.caption(f"Limitation: {limitation}")
    st.caption("Metrics are measured on a later chronological holdout and compared with simple dummy baselines; they are not guarantees of future performance.")
    if st.button("Train / retrain model", type="primary", key="train_model"):
        with st.spinner("Training from chronological traffic history..."):
            try:
                result = api().post("ml/train")
                st.success(f"Model service trained from {result['total_rows']} real traffic readings.")
                st.json(result)
                st.rerun()
            except APIError as error:
                show_api_error(error)
                st.error(f"Model was not trained: {error}")

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
            result = api().post("ml/predict", payload)
            st.markdown(f"**Selected road:** {result.get('segment_name') or segment_display(by_id[segment_id])}")
            prediction_cols = st.columns(4)
            prediction_values = [
                ("Estimated travel time", result.get("predicted_travel_time_minutes"), "min"),
                ("Predicted traffic volume", result.get("predicted_vehicle_count"), "vehicles per reading"),
                ("Predicted congestion", result.get("predicted_congestion_level"), ""),
                ("Average speed", result.get("average_speed_kmh"), "km/h"),
            ]
            for column, (label, value, unit) in zip(prediction_cols, prediction_values):
                display = "N/A" if value is None else f"{value:.2f} {unit}".strip() if isinstance(value, (int, float)) else str(value)
                column.metric(label, display)
            st.caption(f"Prediction for {format_datetime(result.get('predicted_for'))}. Average speed is calculated only from predicted travel time and the selected road's stored length.")
            st.markdown("**Model inputs used**")
            inputs = result.get("model_inputs", {})
            def input_display(value: Any) -> str:
                return "N/A" if value is None else str(value)

            st.dataframe(pd.DataFrame([
                {"Input": "Average speed (km/h)", "Value": input_display(inputs.get("speed_kmh")), "Source": inputs.get("speed_source", "N/A")},
                {"Input": "Average vehicle count", "Value": input_display(inputs.get("vehicle_count")), "Source": inputs.get("vehicle_count_source", "N/A")},
                {"Input": "Historical congestion", "Value": input_display(inputs.get("congestion_level")), "Source": inputs.get("congestion_source", "N/A")},
                {"Input": "Prediction hour / day", "Value": f"{inputs.get('prediction_hour', 'N/A')}:00 / {inputs.get('prediction_day_of_week', 'N/A')}", "Source": "Requested future time"},
                {"Input": "Road length (km)", "Value": input_display(inputs.get("road_length_km")), "Source": "Selected road record"},
                {"Input": "Historical readings used", "Value": input_display(inputs.get("historical_readings_used")), "Source": "Up to 10 latest stored readings"},
            ]), use_container_width=True, hide_index=True)
            feature_names = inputs.get("feature_names", {})
            if feature_names:
                st.caption("Trained feature sets: " + "; ".join(
                    f"{name}: {', '.join(names)}" for name, names in feature_names.items()
                ))
            context = result.get("context", {})
            weather = context.get("weather")
            if weather:
                st.write(f"Weather context: {weather.get('condition') or 'N/A'} · {weather.get('location') or 'Location N/A'} · {format_datetime(weather.get('recorded_at'))}. Not road-specific.")
            else:
                st.write("Weather context: N/A; no stored weather observation is available.")
            active_incidents = context.get("active_incidents", [])
            st.write(f"Active incidents for selected road: {len(active_incidents)}" if active_incidents else "Active incidents for selected road: none recorded.")
            if active_incidents:
                st.dataframe(pd.DataFrame.from_records(active_incidents), use_container_width=True, hide_index=True)
            st.info(f"Rule-based recommendation: {rule_based_recommendation(result.get('predicted_congestion_level'), [])}")
            unavailable = result.get("unavailable_outputs", {})
            if unavailable:
                st.warning("Some model outputs are unavailable: " + "; ".join(f"{name}: {detail}" for name, detail in unavailable.items()))
            if result.get("saved"):
                st.success("Supported prediction fields were saved to MySQL.")
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
                            "save": False,
                        })
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
            if result.get("saved"):
                st.rerun()
        except (APIError, ValueError) as error:
            if isinstance(error, APIError):
                show_api_error(error)
            st.error(f"Prediction unavailable: {error}")


def login_screen() -> None:
    login_copy, login_art = st.columns([1.3, 1], vertical_alignment="center")
    with login_copy:
        st.markdown('<div class="app-kicker">Traffic operations platform</div>', unsafe_allow_html=True)
        st.title("Urban Traffic Congestion Analysis and Travel Time Prediction System")
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
            st.rerun()
        except APIError as error:
            st.error("Invalid login." if error.status_code == 401 else str(error))


if not st.session_state.get("access_token"):
    login_screen()
    st.stop()

with st.sidebar:
    st.markdown("### Urban Traffic")
    st.caption(f"Signed in as {st.session_state.get('username', 'user')}")
    navigation = st.radio(
        "Workspace",
        ["Dashboard", *ENTITIES.keys()],
        label_visibility="collapsed",
    )
    st.caption("Dashboard refreshes every 60 seconds.")
    if st.button("Sign out", use_container_width=True):
        try:
            api().post("auth/logout")
        except APIError:
            pass
        st.session_state.pop("access_token", None)
        st.session_state.pop("username", None)
        st.rerun()

if navigation == "Dashboard":
    dashboard()
else:
    entity_page(navigation)