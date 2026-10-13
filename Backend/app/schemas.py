from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CongestionLevel = Literal["low", "moderate", "high", "severe"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoadSegmentCreate(InputModel):
    name: str = Field(min_length=1, max_length=255)
    start_location: str = Field(min_length=1, max_length=255)
    end_location: str = Field(min_length=1, max_length=255)
    length_km: float = Field(gt=0)
    road_type: str = Field(min_length=1, max_length=100)


class RoadSegmentPatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    start_location: str | None = Field(default=None, min_length=1, max_length=255)
    end_location: str | None = Field(default=None, min_length=1, max_length=255)
    length_km: float | None = Field(default=None, gt=0)
    road_type: str | None = Field(default=None, min_length=1, max_length=100)


class TrafficReadingCreate(InputModel):
    segment_id: int = Field(gt=0)
    recorded_at: datetime
    speed_kmh: float = Field(ge=0)
    vehicle_count: int = Field(ge=0)
    travel_time_minutes: float = Field(ge=0)
    congestion_level: CongestionLevel

    @field_validator("recorded_at")
    @classmethod
    def normalize_recorded_at(cls, value: datetime) -> datetime:
        return to_database_datetime(value)


class TrafficReadingPatch(InputModel):
    segment_id: int | None = Field(default=None, gt=0)
    recorded_at: datetime | None = None
    speed_kmh: float | None = Field(default=None, ge=0)
    vehicle_count: int | None = Field(default=None, ge=0)
    travel_time_minutes: float | None = Field(default=None, ge=0)
    congestion_level: CongestionLevel | None = None


class WeatherCreate(InputModel):
    recorded_at: datetime
    location: str = Field(min_length=1, max_length=255)
    temperature_c: float | None = None
    rainfall_mm: float | None = Field(default=None, ge=0)
    condition: str | None = Field(default=None, max_length=100)

    @field_validator("recorded_at")
    @classmethod
    def normalize_recorded_at(cls, value: datetime) -> datetime:
        return to_database_datetime(value)


class WeatherPatch(InputModel):
    recorded_at: datetime | None = None
    location: str | None = Field(default=None, min_length=1, max_length=255)
    temperature_c: float | None = None
    rainfall_mm: float | None = Field(default=None, ge=0)
    condition: str | None = Field(default=None, max_length=100)


class IncidentCreate(InputModel):
    segment_id: int = Field(gt=0)
    incident_type: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return to_database_datetime(value) if value else None

    def validate_range(self) -> None:
        if self.end_time is not None and self.end_time < self.start_time:
            raise ValueError("end_time must be greater than or equal to start_time")


class IncidentPatch(InputModel):
    segment_id: int | None = Field(default=None, gt=0)
    incident_type: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1)
    start_time: datetime | None = None
    end_time: datetime | None = None


class PredictionCreate(InputModel):
    segment_id: int = Field(gt=0)
    predicted_for: datetime
    predicted_speed_kmh: float = Field(ge=0)
    predicted_travel_time_minutes: float = Field(ge=0)
    predicted_congestion_level: CongestionLevel

    @field_validator("predicted_for")
    @classmethod
    def normalize_predicted_for(cls, value: datetime) -> datetime:
        return to_database_datetime(value)


class PredictionPatch(InputModel):
    segment_id: int | None = Field(default=None, gt=0)
    predicted_for: datetime | None = None
    predicted_speed_kmh: float | None = Field(default=None, ge=0)
    predicted_travel_time_minutes: float | None = Field(default=None, ge=0)
    predicted_congestion_level: CongestionLevel | None = None


class LoginRequest(InputModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class PredictionRequest(InputModel):
    segment_id: int = Field(gt=0)
    predicted_for: datetime
    speed_kmh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    vehicle_count: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    current_congestion_level: CongestionLevel | None = None
    weather_condition: str | None = Field(default=None, max_length=100)
    rainfall_mm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    save: bool = True

    @field_validator("predicted_for")
    @classmethod
    def normalize_predicted_for(cls, value: datetime) -> datetime:
        return to_database_datetime(value)


class TrafficScenarioRequest(InputModel):
    segment_id: int = Field(gt=0)
    predicted_for: datetime
    speed_kmh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    vehicle_count: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    current_congestion_level: CongestionLevel | None = None
    weather_condition: str | None = Field(default=None, max_length=100)
    rainfall_mm: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("predicted_for")
    @classmethod
    def normalize_predicted_for(cls, value: datetime) -> datetime:
        return to_database_datetime(value)


def to_database_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value