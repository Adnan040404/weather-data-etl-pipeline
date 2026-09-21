"""LOAD: store readings in SQLite. Safe to run repeatedly."""

import json
import sqlite3
from datetime import datetime, timezone

from . import config


def connect(db_path=None):
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(readings, rejects, source, fetched, fetch_errors, db_path=None):
    """Insert readings (ignoring ones already stored), record rejects, log the run.

    Returns a dict with inserted / duplicates counts.
    """
    conn = connect(db_path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM weather_observations").fetchone()[0]
        conn.executemany(
            "INSERT OR IGNORE INTO weather_observations (city, country, observed_at, "
            "temperature_c, feels_like_c, humidity_pct, pressure_hpa, wind_speed_ms, conditions, "
            "temp_category, wind_category, source, loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r.city, r.country, r.observed_at, r.temperature_c, r.feels_like_c, r.humidity_pct,
              r.pressure_hpa, r.wind_speed_ms, r.conditions, r.temp_category, r.wind_category,
              source, _now()) for r in readings])
        after = conn.execute("SELECT COUNT(*) FROM weather_observations").fetchone()[0]
        inserted = after - before
        duplicates = len(readings) - inserted

        conn.executemany(
            "INSERT INTO rejected_records (city, reason, raw_json, source, rejected_at) "
            "VALUES (?,?,?,?,?)",
            [(city, reason, json.dumps(raw), source, _now()) for city, reason, raw in rejects])

        conn.execute(
            "INSERT INTO pipeline_runs (run_at, source, fetched, fetch_errors, rejected, inserted, "
            "duplicates) VALUES (?,?,?,?,?,?,?)",
            (_now(), source, fetched, fetch_errors, len(rejects), inserted, duplicates))
        conn.commit()

        # Every reading is either newly stored, already stored, or rejected.
        if len(readings) != inserted + duplicates:
            raise RuntimeError("Load accounting failed: readings != inserted + duplicates")
        return {"inserted": inserted, "duplicates": duplicates, "total_rows": after}
    finally:
        conn.close()
