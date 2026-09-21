"""Sample data in the same shape as OpenWeatherMap's "current weather" response.

This lets the whole pipeline run with no API key and no internet. The values are
generated (deterministically, so results are repeatable) and are NOT real weather.
"""

import random
from datetime import datetime, timedelta, timezone

# city: (country, lat, lon, mean temp C, daily swing C, mean humidity %, mean wind m/s, tz offset s)
CLIMATE = {
    "London": ("GB", 51.51, -0.13, 15.0, 4.0, 72, 4.5, 3600),
    "Paris": ("FR", 48.85, 2.35, 17.0, 5.0, 65, 3.5, 7200),
    "Tokyo": ("JP", 35.68, 139.69, 24.0, 4.0, 70, 3.0, 32400),
    "New York": ("US", 40.71, -74.01, 21.0, 5.0, 62, 4.0, -14400),
    "Berlin": ("DE", 52.52, 13.40, 14.0, 5.5, 68, 3.8, 7200),
}
CONDITIONS = [("Clear", 800), ("Clouds", 803), ("Rain", 500), ("Drizzle", 300), ("Mist", 701)]

# Fixed anchor so the sample data never changes between runs.
ANCHOR = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
STEP_HOURS = 6


def _payload(city, when, rng):
    country, lat, lon, mean_t, swing, mean_h, mean_w, tz = CLIMATE[city]
    hour = when.hour
    # warmest mid-afternoon (~15:00 UTC-ish), coolest before dawn
    daily = swing * (1 if 12 <= hour < 18 else 0.4 if 6 <= hour < 12 else -0.6 if hour < 6 else 0)
    temp = round(mean_t + daily + rng.uniform(-2.0, 2.0), 2)
    humidity = max(20, min(100, int(mean_h + rng.uniform(-15, 15))))
    wind = round(max(0.2, mean_w + rng.uniform(-2.0, 2.5)), 2)
    main, code = rng.choices(CONDITIONS, weights=[30, 35, 15, 8, 12])[0]
    return {
        "coord": {"lon": lon, "lat": lat},
        "weather": [{"id": code, "main": main, "description": main.lower(), "icon": "01d"}],
        "base": "stations",
        "main": {
            "temp": temp,
            "feels_like": round(temp - (wind * 0.4), 2),
            "temp_min": round(temp - 1.0, 2),
            "temp_max": round(temp + 1.0, 2),
            "pressure": int(1013 + rng.uniform(-12, 12)),
            "humidity": humidity,
        },
        "wind": {"speed": wind, "deg": rng.randint(0, 359)},
        "dt": int(when.timestamp()),
        "sys": {"country": country},
        "timezone": tz,
        "name": city,
        "cod": 200,
    }


def sample_payloads(cities, days=7):
    """One reading every 6 hours per city for `days` days, oldest first."""
    steps = int(days * 24 / STEP_HOURS)
    out = []
    for city in cities:
        if city not in CLIMATE:
            continue  # no sample climate for this city
        for i in range(steps):
            when = ANCHOR + timedelta(hours=STEP_HOURS * i)
            rng = random.Random(f"{city}-{when.isoformat()}")
            out.append(_payload(city, when, rng))
    return out
