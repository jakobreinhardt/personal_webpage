"""Daily weather service for mountain tours.

Reads tour suggestions from the database, extracts mountain names using
OpenAI, geocodes them with the free Open-Meteo geocoding API, then stores
one weather record per mountain per day using the free Open-Meteo forecast API.

Usage:
    python weather_service.py           # run once immediately
    called from app.py via APScheduler  # runs daily at 06:00 UTC
"""

import json
import logging
import os
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Mountains always tracked regardless of user submissions (from the static tour cards)
SEED_MOUNTAINS = ["Thaneller", "Daniel"]

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


# ---------- mountain extraction ----------

def extract_mountains(texts: list[str]) -> list[str]:
    """Use Anthropic Claude to extract unique mountain/peak names from a list of tour texts.

    Returns an empty list if ANTHROPIC_API_KEY is not set or no mountains are found.
    """
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — skipping LLM mountain extraction")
        return []
    if not texts:
        return []

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    combined = "\n".join(f"- {t}" for t in texts)

    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=(
            "You extract mountain and peak names from ski tour descriptions. "
            'Return ONLY a JSON array of unique mountain names, e.g. ["Zugspitze","Thaneller"]. '
            "Include only actual mountain or peak names — not valleys, passes, huts, or villages. "
            "If no mountains are found, return []."
        ),
        messages=[{"role": "user", "content": combined}],
    )

    raw = resp.content[0].text.strip()
    try:
        names = json.loads(raw)
        return [n.strip() for n in names if isinstance(n, str) and n.strip()]
    except json.JSONDecodeError:
        log.error("Failed to parse LLM response as JSON: %s", raw)
        return []


# ---------- geocoding & weather ----------

def geocode_mountain(name: str) -> tuple[float, float] | None:
    """Return (latitude, longitude) for a mountain name via Open-Meteo geocoding.

    Open-Meteo geocoding is free and requires no API key.
    Returns None if the mountain cannot be found.
    """
    resp = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": name, "count": 1, "language": "en", "format": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        log.warning("No geocoding result for mountain: %s", name)
        return None
    r = results[0]
    return float(r["latitude"]), float(r["longitude"])


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
    """Main entry point called by the scheduler (or directly as a script).

    Steps:
    1. Read all tour_suggestions texts from the DB.
    2. Extract mountain names with OpenAI (plus always include SEED_MOUNTAINS).
    3. Geocode any new mountains and persist them in the mountains table.
    4. Fetch today's weather for each mountain and store it in mountain_weather
       (skips mountains that already have a record for today).
    """
    log.info("Starting weather update")
    conn = _get_db()
    cur = conn.cursor()
    ph = _ph()

    # Collect tour texts from user submissions
    cur.execute("SELECT text FROM tour_suggestions")
    rows = cur.fetchall()
    texts = [r[0] if DATABASE_URL else r["text"] for r in rows]

    # LLM extraction + seed mountains (deduplicated)
    llm_mountains = extract_mountains(texts)
    all_mountains = list({m for m in llm_mountains + SEED_MOUNTAINS if m})
    log.info("Mountains to update: %s", all_mountains)

    today = date.today().isoformat()
    fetched_at = datetime.now(timezone.utc).isoformat()

    for name in all_mountains:
        # Look up or create the mountain record
        cur.execute(
            f"SELECT id, latitude, longitude FROM mountains WHERE name = {ph}", (name,)
        )
        row = cur.fetchone()

        if row is None:
            coords = geocode_mountain(name)
            if coords is None:
                continue
            lat, lon = coords
            if DATABASE_URL:
                cur.execute(
                    "INSERT INTO mountains (name, latitude, longitude, geocoded_at)"
                    " VALUES (%s, %s, %s, %s) RETURNING id",
                    (name, lat, lon, fetched_at),
                )
                mountain_id = cur.fetchone()[0]
            else:
                cur.execute(
                    "INSERT INTO mountains (name, latitude, longitude, geocoded_at)"
                    " VALUES (?, ?, ?, ?)",
                    (name, lat, lon, fetched_at),
                )
                mountain_id = cur.lastrowid
            conn.commit()
            log.info("Geocoded new mountain %s → %.4f, %.4f", name, lat, lon)
        else:
            mountain_id = row[0] if DATABASE_URL else row["id"]
            lat = row[1] if DATABASE_URL else row["latitude"]
            lon = row[2] if DATABASE_URL else row["longitude"]

        # Skip if today's weather already stored
        cur.execute(
            f"SELECT id FROM mountain_weather WHERE mountain_id = {ph} AND date = {ph}",
            (mountain_id, today),
        )
        if cur.fetchone():
            log.info("Weather already current for %s on %s", name, today)
            continue

        # Fetch and persist weather
        try:
            weather = fetch_weather(lat, lon)
        except Exception as exc:
            log.error("Weather fetch failed for %s: %s", name, exc)
            continue

        cur.execute(
            f"INSERT INTO mountain_weather"
            f" (mountain_id, date, temperature_c, weather_code, weather_desc, wind_speed_kmh, fetched_at)"
            f" VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (
                mountain_id,
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
            name,
            weather["temperature_c"] or 0,
            weather["weather_desc"],
            weather["wind_speed_kmh"] or 0,
        )

    cur.close()
    conn.close()
    log.info("Weather update complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    run_weather_update()
