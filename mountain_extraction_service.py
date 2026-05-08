"""Mountain extraction service.

Processes each tour suggestion individually: extracts mountain/peak names using
Anthropic Claude, geocodes new mountains with the free Open-Meteo geocoding API,
and records the tour→mountain mappings in the tour_mountains table.

Only processes tours that haven't been processed yet (no rows in tour_mountains).

Called synchronously on tour submission so new mountains appear within seconds.

Usage:
    python mountain_extraction_service.py   # run once immediately
    called from app.py on every tour submission
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")


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


# ---------- LLM extraction ----------

def extract_mountains(text: str) -> list[str]:
    """Use Anthropic Claude to extract unique mountain/peak names from a tour text.

    Returns an empty list if ANTHROPIC_API_KEY is not set or no mountains are found.
    """
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — skipping LLM mountain extraction")
        return []
    if not text.strip():
        return []

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=(
            "You extract mountain and peak names from ski tour descriptions. "
            'Return ONLY a JSON array of unique mountain names, e.g. ["Zugspitze","Thaneller"]. '
            "Include only actual mountain or peak names — not valleys, passes, huts, or villages. "
            "If no mountains are found, return []."
        ),
        messages=[{"role": "user", "content": text}],
    )

    raw = resp.content[0].text.strip()
    # Strip markdown code fences if present (e.g. ```json ... ```)
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        names = json.loads(raw)
        return [n.strip() for n in names if isinstance(n, str) and n.strip()]
    except json.JSONDecodeError:
        log.error("Failed to parse LLM response as JSON: %s", raw)
        return []


# ---------- geocoding ----------

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


def _find_or_create_mountain(cur, conn, name: str) -> int | None:
    """Look up a mountain by name, or geocode and insert it. Returns the mountain id."""
    ph = _ph()
    cur.execute(f"SELECT id FROM mountains WHERE name = {ph}", (name,))
    row = cur.fetchone()
    if row:
        return row[0] if DATABASE_URL else row["id"]

    coords = geocode_mountain(name)
    if coords is None:
        return None
    lat, lon = coords
    fetched_at = datetime.now(timezone.utc).isoformat()
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
    return mountain_id


# ---------- main extraction routine ----------

def run_mountain_extraction() -> None:
    """Extract mountains from unprocessed tour suggestions and record the mappings."""
    log.info("Starting mountain extraction")
    try:
        _run_mountain_extraction()
    except Exception:
        log.exception("Unhandled error in mountain extraction")


def _run_mountain_extraction() -> None:
    conn = _get_db()
    cur = conn.cursor()
    ph = _ph()

    # Only process tours that have no entries in tour_mountains yet
    cur.execute(
        """
        SELECT ts.id, ts.text FROM tour_suggestions ts
        WHERE NOT EXISTS (
            SELECT 1 FROM tour_mountains tm WHERE tm.tour_suggestion_id = ts.id
        )
        ORDER BY ts.created_at ASC
        """
    )
    rows = cur.fetchall()
    if DATABASE_URL:
        unprocessed = [{"id": r[0], "text": r[1]} for r in rows]
    else:
        unprocessed = [dict(r) for r in rows]

    if not unprocessed:
        log.info("No unprocessed tour suggestions")
        cur.close()
        conn.close()
        return

    log.info("Processing %d unprocessed tour suggestion(s)", len(unprocessed))

    for tour in unprocessed:
        names = extract_mountains(tour["text"])
        log.info("Tour %d → extracted: %s", tour["id"], names)

        if not names:
            # Mark tour as processed even when no mountains were found
            cur.execute(
                f"INSERT INTO tour_mountains (tour_suggestion_id, mountain_id) VALUES ({ph}, NULL)",
                (tour["id"],),
            )
            conn.commit()
            continue

        for name in names:
            mountain_id = _find_or_create_mountain(cur, conn, name)
            if mountain_id is None:
                continue
            cur.execute(
                f"INSERT INTO tour_mountains (tour_suggestion_id, mountain_id) VALUES ({ph}, {ph})",
                (tour["id"], mountain_id),
            )
            conn.commit()

    cur.close()
    conn.close()
    log.info("Mountain extraction complete")


if __name__ == "__main__":
    run_mountain_extraction()
