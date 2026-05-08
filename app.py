import atexit
import os
import sqlite3
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")

# In production, set ALLOWED_ORIGINS to your GitHub Pages domain
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "https://jakobreinhardt.eu"
).split(",")
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})

DATABASE_URL = os.environ.get("DATABASE_URL")  # set via env var on Render — never commit credentials


# ---------- database helpers ----------

def get_db():
    """Return a DB connection — PostgreSQL in production, SQLite locally."""
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(__file__), "tours.db")
        )
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Create all required tables if they don't exist yet.

    Called once at startup. Safe to call repeatedly — uses CREATE TABLE IF NOT EXISTS.
    Four tables are managed:
      - tour_suggestions: user-submitted tour texts from the activities page form
      - mountains: one row per unique mountain name, storing its coordinates
      - tour_mountains: links each tour suggestion to the mountains extracted from it
      - mountain_weather: daily weather snapshot per mountain (one row per mountain per day)
    """
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tour_suggestions (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mountains (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                latitude REAL,
                longitude REAL,
                geocoded_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tour_mountains (
                id SERIAL PRIMARY KEY,
                tour_suggestion_id INTEGER NOT NULL REFERENCES tour_suggestions(id),
                mountain_id INTEGER REFERENCES mountains(id),
                UNIQUE(tour_suggestion_id, mountain_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mountain_weather (
                id SERIAL PRIMARY KEY,
                mountain_id INTEGER REFERENCES mountains(id),
                date TEXT NOT NULL,
                temperature_c REAL,
                weather_code INTEGER,
                weather_desc TEXT,
                wind_speed_kmh REAL,
                fetched_at TEXT NOT NULL,
                UNIQUE(mountain_id, date)
            )
            """
        )
    else:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tour_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mountains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                latitude REAL,
                longitude REAL,
                geocoded_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tour_mountains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tour_suggestion_id INTEGER NOT NULL REFERENCES tour_suggestions(id),
                mountain_id INTEGER REFERENCES mountains(id),
                UNIQUE(tour_suggestion_id, mountain_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mountain_weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mountain_id INTEGER REFERENCES mountains(id),
                date TEXT NOT NULL,
                temperature_c REAL,
                weather_code INTEGER,
                weather_desc TEXT,
                wind_speed_kmh REAL,
                fetched_at TEXT NOT NULL,
                UNIQUE(mountain_id, date)
            )
            """
        )
    conn.commit()
    cur.close()
    conn.close()


def db_rows_to_dicts(conn, cur):
    """Convert cursor rows to a list of plain dicts.

    PostgreSQL (psycopg2) returns plain tuples, so column names are read from
    the cursor description. SQLite is configured with row_factory=sqlite3.Row
    which already supports dict-style access. Both paths produce the same output.
    """
    if DATABASE_URL:
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    else:
        return [dict(row) for row in cur.fetchall()]


# ---------- routes ----------

@app.route("/")
def index():
    """Serve the static index.html entry page.

    Used only during local development — in production GitHub Pages serves
    the static files directly and this route is never reached.
    """
    return send_from_directory(".", "index.html")


@app.route("/api/tours", methods=["POST"])
def add_tour():
    """Accept a new tour suggestion submitted via the activities page form.

    Expects JSON body: { "tour": "<text>" }
    Text is trimmed and capped at 500 characters before being stored.
    Returns 400 if the tour text is missing or blank.
    """
    data = request.get_json(silent=True)
    if not data or not data.get("tour", "").strip():
        return jsonify({"error": "tour text is required"}), 400

    text = data["tour"].strip()[:500]
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tour_suggestions (text, created_at) VALUES (%s, %s)"
        if DATABASE_URL
        else "INSERT INTO tour_suggestions (text, created_at) VALUES (?, ?)",
        (text, created_at),
    )
    conn.commit()
    cur.close()
    conn.close()

    from mountain_extraction_service import run_mountain_extraction
    run_mountain_extraction()

    return jsonify({"status": "ok", "created_at": created_at}), 201


@app.route("/api/tours", methods=["GET"])
def list_tours():
    """Return all tour suggestions, newest first.

    Used by the activities page to show recent suggestions below the form.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, text, created_at FROM tour_suggestions ORDER BY created_at DESC"
    )
    rows = db_rows_to_dicts(conn, cur)
    cur.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/mountain-mentions", methods=["GET"])
def get_mountain_mentions():
    """Return up to 10 mountains sorted by how many tour suggestions they were extracted from."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.name, COUNT(tm.id) AS mention_count
        FROM mountains m
        LEFT JOIN tour_mountains tm ON tm.mountain_id = m.id
        GROUP BY m.name
        ORDER BY mention_count DESC, m.name
        LIMIT 10
        """
    )
    rows = db_rows_to_dicts(conn, cur)
    cur.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/mountain-weather", methods=["GET"])
def get_mountain_weather():
    """Return weather for the top 3 mountains by extraction count."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.name, mw.date, mw.temperature_c, mw.weather_code,
               mw.weather_desc, mw.wind_speed_kmh, mw.fetched_at
        FROM mountains m
        JOIN mountain_weather mw ON mw.mountain_id = m.id
        WHERE mw.date = (
            SELECT MAX(mw2.date) FROM mountain_weather mw2
            WHERE mw2.mountain_id = m.id
        )
        AND m.id IN (
            SELECT m2.id
            FROM mountains m2
            LEFT JOIN tour_mountains tm ON tm.mountain_id = m2.id
            GROUP BY m2.id, m2.name
            ORDER BY COUNT(tm.id) DESC, m2.name
            LIMIT 3
        )
        ORDER BY m.name
        """
    )
    rows = db_rows_to_dicts(conn, cur)
    cur.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/admin/update-weather", methods=["POST"])
def trigger_weather_update():
    """Manually trigger the weather update pipeline in a background thread.

    Useful for testing or forcing a refresh outside of the daily 06:00 UTC schedule.
    The update runs asynchronously so this endpoint returns immediately.
    """
    from weather_service import run_weather_update
    threading.Thread(target=run_weather_update, daemon=True).start()
    return jsonify({"status": "update started"}), 202


init_db()

# ---------- daily weather scheduler ----------
# Guard against Flask debug reloader starting a second scheduler process.
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    from weather_service import run_weather_update as _run_weather_update
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_weather_update, "cron", hour=6, minute=0)
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
