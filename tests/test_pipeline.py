"""Tests run with no network and no API key: the live API is replaced by a fake."""

import copy
import os
import sqlite3
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from weather_etl import config, extract as ex  # noqa: E402
from weather_etl.load import load  # noqa: E402
from weather_etl.sample_data import sample_payloads  # noqa: E402
from weather_etl.transform import ValidationError, categorise, transform, transform_all  # noqa: E402


def good_payload():
    return copy.deepcopy(sample_payloads(["London"], days=1)[0])


# ------------------------------------------------------------------ transform
def test_valid_payload_becomes_a_reading():
    r = transform(good_payload())
    assert r.city == "London" and r.country == "GB"
    assert r.observed_at.endswith("Z")
    assert r.temp_category in {"Freezing", "Cold", "Mild", "Warm", "Hot"}


def test_categories():
    assert categorise(-3, config.TEMP_BANDS, "Hot") == "Freezing"
    assert categorise(15, config.TEMP_BANDS, "Hot") == "Mild"
    assert categorise(35, config.TEMP_BANDS, "Hot") == "Hot"
    assert categorise(0.5, config.WIND_BANDS, "Storm") == "Calm"
    assert categorise(20, config.WIND_BANDS, "Storm") == "Storm"


@pytest.mark.parametrize("field,value", [
    (("main", "temp"), 500),          # impossible temperature
    (("main", "humidity"), 140),      # humidity above 100%
    (("wind", "speed"), -4),          # negative wind
    (("main", "temp"), "warm"),       # not a number
])
def test_bad_values_are_rejected(field, value):
    p = good_payload()
    p[field[0]][field[1]] = value
    with pytest.raises(ValidationError):
        transform(p)


def test_missing_field_is_rejected_not_crashing():
    p = good_payload()
    del p["main"]
    with pytest.raises(ValidationError):
        transform(p)


def test_api_error_code_is_rejected():
    p = good_payload()
    p["cod"] = 401
    with pytest.raises(ValidationError):
        transform(p)


def test_transform_all_separates_good_from_bad():
    bad = good_payload()
    bad["main"]["humidity"] = 999
    readings, rejects = transform_all([good_payload(), bad])
    assert len(readings) == 1 and len(rejects) == 1
    assert "humidity" in rejects[0][1]


# ------------------------------------------------------------------ sample data
def test_sample_data_is_repeatable_and_api_shaped():
    a = sample_payloads(["Tokyo", "Paris"], days=2)
    b = sample_payloads(["Tokyo", "Paris"], days=2)
    assert a == b and len(a) == 2 * 8               # 2 cities x 2 days x 4 readings
    assert {"main", "wind", "weather", "dt", "name", "cod"} <= set(a[0])
    assert all(transform(p) for p in a)             # every generated reading is valid


# ------------------------------------------------------------------ extract (fake API)
class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


class FakeHttp:
    """Returns the queued responses in order and counts calls."""
    def __init__(self, queue):
        self.queue, self.calls = list(queue), 0

    def get(self, *args, **kwargs):
        self.calls += 1
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "test-key")


def test_retries_temporary_failures_then_succeeds():
    http = FakeHttp([FakeResponse(500), requests.Timeout(), FakeResponse(200, good_payload())])
    waits = []
    out = ex.fetch_city("London", session=http, sleep=waits.append)
    assert out["name"] == "London" and http.calls == 3
    assert waits == [config.BACKOFF_SECONDS, config.BACKOFF_SECONDS * 2]   # waits grow


def test_gives_up_after_max_retries():
    http = FakeHttp([FakeResponse(503)] * config.MAX_RETRIES)
    with pytest.raises(RuntimeError, match="gave up"):
        ex.fetch_city("London", session=http, sleep=lambda s: None)
    assert http.calls == config.MAX_RETRIES


def test_bad_key_is_not_retried():
    http = FakeHttp([FakeResponse(401)])
    with pytest.raises(ex.ApiKeyError):
        ex.fetch_city("London", session=http, sleep=lambda s: None)
    assert http.calls == 1


def test_missing_key_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    with pytest.raises(ex.ApiKeyError, match="OWM_API_KEY"):
        ex.fetch_city("London", session=FakeHttp([]))


def test_unknown_city_is_not_retried():
    http = FakeHttp([FakeResponse(404)])
    with pytest.raises(ValueError, match="not found"):
        ex.fetch_city("Atlantis", session=http, sleep=lambda s: None)
    assert http.calls == 1


# ------------------------------------------------------------------ load
def test_loading_twice_does_not_duplicate(tmp_path):
    db = tmp_path / "w.db"
    readings, rejects = transform_all(sample_payloads(["London", "Paris"], days=2))
    first = load(readings, rejects, "sample", len(readings), 0, db_path=db)
    second = load(readings, rejects, "sample", len(readings), 0, db_path=db)
    assert first["inserted"] == len(readings) and first["duplicates"] == 0
    assert second["inserted"] == 0 and second["duplicates"] == len(readings)
    assert second["total_rows"] == len(readings)


def test_rejects_are_stored_with_a_reason(tmp_path):
    db = tmp_path / "w.db"
    bad = good_payload()
    bad["main"]["temp"] = 900
    readings, rejects = transform_all([good_payload(), bad])
    load(readings, rejects, "sample", 2, 0, db_path=db)
    conn = sqlite3.connect(db)
    reason = conn.execute("SELECT reason FROM rejected_records").fetchone()[0]
    conn.close()
    assert "temperature" in reason


def test_database_rejects_impossible_rows_on_its_own(tmp_path):
    """Second safety net: even if validation were skipped, the CHECK constraint refuses it."""
    from weather_etl.load import connect
    conn = connect(tmp_path / "w.db")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO weather_observations (city, observed_at, temperature_c, feels_like_c, "
                     "humidity_pct, pressure_hpa, wind_speed_ms, conditions, temp_category, wind_category, "
                     "source, loaded_at) VALUES ('X','2026-01-01T00:00:00Z', 999, 0, 50, 1000, 1, 'Clear', "
                     "'Hot', 'Calm', 'sample', 'now')")
    conn.close()


# ------------------------------------------------------------------ whole pipeline
def test_pipeline_end_to_end_sample_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "w.db")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    import run_pipeline
    assert run_pipeline.main(["--source", "sample", "--days", "3"]) == 0
    for name in ("weather_report.html", "weather_data.xlsx", "temperature_trend.png",
                 "latest_temperature.png", "conditions.png"):
        assert (tmp_path / name).exists(), name
    conn = sqlite3.connect(tmp_path / "w.db")
    total = conn.execute("SELECT COUNT(*) FROM weather_observations").fetchone()[0]
    latest = conn.execute("SELECT COUNT(*) FROM v_latest_by_city").fetchone()[0]
    conn.close()
    assert total == 5 * 3 * 4 and latest == 5
