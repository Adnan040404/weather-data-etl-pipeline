"""EXTRACT: get raw weather readings, either from the live API or from sample data."""

import time

import requests

from . import config
from .sample_data import sample_payloads


class ApiKeyError(RuntimeError):
    """The key is missing or was rejected. Retrying will not help."""


def fetch_city(city, session=None, sleep=time.sleep):
    """Fetch one city from the live API.

    Temporary problems (timeouts, connection errors, HTTP 429 and 5xx) are retried
    with a growing wait. A bad key (401) or an unknown city (404) is not retried.
    """
    if not config.API_KEY:
        raise ApiKeyError("OWM_API_KEY is not set. Copy .env.example to .env and add your key, "
                          "or run with --source sample.")
    http = session or requests
    params = {"q": city, "appid": config.API_KEY, "units": "metric"}
    wait = config.BACKOFF_SECONDS
    last_error = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = http.get(config.API_URL, params=params, timeout=config.REQUEST_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = f"{type(exc).__name__}"
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                raise ApiKeyError("The API rejected the key (HTTP 401).")
            if resp.status_code == 404:
                raise ValueError(f"City not found: {city}")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
            else:
                raise ValueError(f"Unexpected HTTP {resp.status_code} for {city}")
        if attempt < config.MAX_RETRIES:
            sleep(wait)
            wait *= 2
    raise RuntimeError(f"{city}: gave up after {config.MAX_RETRIES} attempts ({last_error})")


def extract(source, cities, days=7):
    """Return (payloads, errors). One bad city never stops the others."""
    if source == "sample":
        return sample_payloads(cities, days=days), []
    payloads, errors = [], []
    with requests.Session() as session:
        for city in cities:
            try:
                payloads.append(fetch_city(city, session=session))
            except ApiKeyError:
                raise  # every city would fail the same way, so stop early
            except Exception as exc:  # noqa: BLE001 - record the reason and carry on
                errors.append((city, str(exc)))
    return payloads, errors
