"""Weather service for mountain tours.

Fetches current weather for all mountains stored in the database and saves
one weather record per mountain per day using the free Open-Meteo forecast API.

Mountain extraction and geocoding live in mountain_extraction_service.py.

Usage:
    python weather_service.py           # run once immediately
    called from Render cron job         # runs hourly
"""

import logging
import os
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}


# ---------- database ----------

def _get_db():
    """Return a DB connection — PostgreSQL in production, SQLite locally."""
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    import sqlite3
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "tours.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _ph() -> str:
    """Return the correct SQL placeholder for the active DB backend."""
    return "%s" if DATABASE_URL else "?"


# ---------- weather ----------

def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current weather from Open-Meteo (free, no API key required).

    Returns a dict with temperature_c, weather_code, weather_desc, wind_speed_kmh.
    """
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        },
        timeout=10,
    )
    resp.raise_for_status()
    current = resp.json().get("current", {})
    code = current.get("weather_code")
    return {
        "temperature_c": current.get("temperature_2m"),
        "weather_code": code,
        "weather_desc": WMO_DESCRIPTIONS.get(code, "Unknown"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
    }


# ---------- main update routine ----------

def run_weather_update() -> None:
    """Fetch today's weather for every mountain already in the DB.

    Mountains are populated by mountain_extraction_service.py.
    Skips mountains that already have a record for today.
    """
    log.info("Starting weather update")
    try:
        _run_weather_update()
    except Exception:
        log.exception("Unhandled error in weather update")


def _run_weather_update() -> None:
    conn = _get_db()
    cur = conn.cursor()
    ph = _ph()

    cur.execute("SELECT id, name, latitude, longitude FROM mountains")
    rows = cur.fetchall()
    if DATABASE_URL:
        mountains = [{"id": r[0], "name": r[1], "latitude": r[2], "longitude": r[3]} for r in rows]
    else:
        mountains = [dict(r) for r in rows]

    log.info("Mountains to update weather for: %s", [m["name"] for m in mountains])

    today = date.today().isoformat()
    fetched_at = datetime.now(timezone.utc).isoformat()

    for m in mountains:
        if m["latitude"] is None or m["longitude"] is None:
            log.warning("Skipping %s — no coordinates", m["name"])
            continue

        cur.execute(
            f"SELECT id FROM mountain_weather WHERE mountain_id = {ph} AND date = {ph}",
            (m["id"], today),
        )
        if cur.fetchone():
            log.info("Weather already current for %s on %s", m["name"], today)
            continue

        try:
            weather = fetch_weather(m["latitude"], m["longitude"])
        except Exception as exc:
            log.error("Weather fetch failed for %s: %s", m["name"], exc)
            continue

        cur.execute(
            f"INSERT INTO mountain_weather"
            f" (mountain_id, date, temperature_c, weather_code, weather_desc, wind_speed_kmh, fetched_at)"
            f" VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (
                m["id"],
                today,
                weather["temperature_c"],
                weather["weather_code"],
                weather["weather_desc"],
                weather["wind_speed_kmh"],
                fetched_at,
            ),
        )
        conn.commit()
        log.info(
            "Stored weather for %s: %.1f°C, %s, %.0f km/h",
            m["name"],
            weather["temperature_c"] or 0,
            weather["weather_desc"],
            weather["wind_speed_kmh"] or 0,
        )

    cur.close()
    conn.close()
    log.info("Weather update complete")


if __name__ == "__main__":
    run_weather_update()
