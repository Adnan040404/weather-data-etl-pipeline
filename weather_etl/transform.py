"""TRANSFORM: check each raw reading, normalise it, and add simple categories.

A reading that fails a check is rejected with a reason. It is not silently fixed
or dropped, so a broken source shows up in the reject count instead of the charts.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from . import config


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Reading:
    city: str
    country: str
    observed_at: str          # UTC, ISO 8601
    temperature_c: float
    feels_like_c: float
    humidity_pct: int
    pressure_hpa: int
    wind_speed_ms: float
    conditions: str
    temp_category: str
    wind_category: str


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} is not a number: {value!r}")
    return float(value)


def _within(value, name, key):
    lo, hi = config.LIMITS[key]
    if not lo <= value <= hi:
        raise ValidationError(f"{name} out of range ({lo} to {hi}): {value}")
    return value


def categorise(value, bands, top):
    for upper, label in bands:
        if value < upper:
            return label
    return top


def transform(payload):
    """Turn one API payload into a Reading, or raise ValidationError."""
    try:
        if payload.get("cod") not in (200, "200"):
            raise ValidationError(f"API returned code {payload.get('cod')!r}")
        city = str(payload["name"]).strip()
        if not city:
            raise ValidationError("city name is empty")
        main, wind = payload["main"], payload["wind"]
        temp = _within(_number(main["temp"], "temperature"), "temperature", "temperature")
        feels = _within(_number(main.get("feels_like", main["temp"]), "feels_like"),
                        "feels_like", "temperature")
        humidity = _within(_number(main["humidity"], "humidity"), "humidity", "humidity")
        pressure = _within(_number(main.get("pressure", 1013), "pressure"), "pressure", "pressure")
        speed = _within(_number(wind["speed"], "wind speed"), "wind speed", "wind_speed")
        conditions = str(payload["weather"][0]["main"]).strip() or "Unknown"
        observed = datetime.fromtimestamp(int(payload["dt"]), tz=timezone.utc)
    except ValidationError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValidationError(f"missing or malformed field: {type(exc).__name__}: {exc}") from exc

    return Reading(
        city=city,
        country=str(payload.get("sys", {}).get("country", "")),
        observed_at=observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        temperature_c=round(temp, 2),
        feels_like_c=round(feels, 2),
        humidity_pct=int(humidity),
        pressure_hpa=int(pressure),
        wind_speed_ms=round(speed, 2),
        conditions=conditions,
        temp_category=categorise(temp, config.TEMP_BANDS, "Hot"),
        wind_category=categorise(speed, config.WIND_BANDS, "Storm"),
    )


def transform_all(payloads):
    """Return (readings, rejects). rejects is a list of (city, reason, raw_payload)."""
    readings, rejects = [], []
    for payload in payloads:
        try:
            readings.append(transform(payload))
        except ValidationError as exc:
            rejects.append((str(payload.get("name", "?")), str(exc), payload))
    return readings, rejects
