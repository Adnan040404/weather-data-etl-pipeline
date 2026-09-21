-- SQLite schema for the weather pipeline.
-- The UNIQUE constraint makes loading safe to repeat: the same city and timestamp
-- can only be stored once, so re-running never creates duplicate rows.

CREATE TABLE IF NOT EXISTS weather_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    city           TEXT    NOT NULL,
    country        TEXT,
    observed_at    TEXT    NOT NULL,                    -- UTC, ISO 8601
    temperature_c  REAL    NOT NULL CHECK (temperature_c BETWEEN -90 AND 60),
    feels_like_c   REAL    NOT NULL,
    humidity_pct   INTEGER NOT NULL CHECK (humidity_pct BETWEEN 0 AND 100),
    pressure_hpa   INTEGER NOT NULL,
    wind_speed_ms  REAL    NOT NULL CHECK (wind_speed_ms >= 0),
    conditions     TEXT    NOT NULL,
    temp_category  TEXT    NOT NULL,
    wind_category  TEXT    NOT NULL,
    source         TEXT    NOT NULL,                    -- 'live' or 'sample'
    loaded_at      TEXT    NOT NULL,
    UNIQUE (city, observed_at)
);
CREATE INDEX IF NOT EXISTS ix_obs_city_time ON weather_observations(city, observed_at);

-- Readings that failed validation, kept with the reason.
CREATE TABLE IF NOT EXISTS rejected_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    city         TEXT,
    reason       TEXT NOT NULL,
    raw_json     TEXT,
    source       TEXT NOT NULL,
    rejected_at  TEXT NOT NULL
);

-- One row per pipeline run.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at        TEXT    NOT NULL,
    source        TEXT    NOT NULL,
    fetched       INTEGER NOT NULL,
    fetch_errors  INTEGER NOT NULL,
    rejected      INTEGER NOT NULL,
    inserted      INTEGER NOT NULL,
    duplicates    INTEGER NOT NULL
);

DROP VIEW IF EXISTS v_city_summary;
CREATE VIEW v_city_summary AS
SELECT city,
       COUNT(*)                        AS readings,
       ROUND(AVG(temperature_c), 1)    AS avg_temp_c,
       MIN(temperature_c)              AS min_temp_c,
       MAX(temperature_c)              AS max_temp_c,
       ROUND(AVG(humidity_pct), 0)     AS avg_humidity_pct,
       ROUND(AVG(wind_speed_ms), 1)    AS avg_wind_ms
FROM weather_observations
GROUP BY city;

DROP VIEW IF EXISTS v_latest_by_city;
CREATE VIEW v_latest_by_city AS
SELECT city, country, observed_at, temperature_c, humidity_pct, wind_speed_ms,
       conditions, temp_category, wind_category
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY city ORDER BY observed_at DESC) AS rn
    FROM weather_observations
)
WHERE rn = 1;
