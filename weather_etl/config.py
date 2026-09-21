"""Settings in one place. Nothing secret is stored here: the API key comes from the
environment (or a local .env file that is never committed)."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; plain environment variables still work
    pass

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
DB_PATH = OUTPUT_DIR / "weather.db"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
TEMPLATE_DIR = ROOT / "templates"

CITIES = ["London", "Paris", "Tokyo", "New York", "Berlin"]

API_KEY = os.getenv("OWM_API_KEY", "").strip()
API_URL = "https://api.openweathermap.org/data/2.5/weather"
REQUEST_TIMEOUT = 10      # seconds per request
MAX_RETRIES = 3           # attempts per city on temporary failures
BACKOFF_SECONDS = 2       # wait doubles after each failed attempt

# Plausibility limits. A reading outside these is a bad reading, not weather.
LIMITS = {
    "temperature": (-90.0, 60.0),   # deg C, a little beyond the recorded extremes
    "humidity": (0, 100),           # %
    "wind_speed": (0.0, 120.0),     # m/s
    "pressure": (850, 1090),        # hPa
}

TEMP_BANDS = [(0, "Freezing"), (10, "Cold"), (20, "Mild"), (30, "Warm")]  # upper bounds, deg C
WIND_BANDS = [(1.6, "Calm"), (8.0, "Breezy"), (14.0, "Windy")]            # upper bounds, m/s
