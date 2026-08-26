import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from flask import Flask, Response, request, jsonify, send_from_directory
from flask_cors import CORS

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")

# In production, set ALLOWED_ORIGINS to your GitHub Pages domain
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "https://jakobreinhardt.eu"
).split(",")
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})

log = logging.getLogger(__name__)

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
    Three tables are managed:
      - tour_suggestions: user-submitted tour texts from the activities page form
      - mountains: one row per unique mountain name, storing its coordinates
      - tour_mountains: links each tour suggestion to the mountains extracted from it
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


@app.route("/api/chat", methods=["POST"])
def chat():
    """Stream a Claude reply for a visitor chat message as Server-Sent Events.

    Expects JSON body: { "messages": [ {"role": "user"|"assistant", "content": str}, ... ] }
    The browser keeps the conversation and resends it each turn; the history is
    re-validated and trimmed server-side before it reaches the model.

    Responds with text/event-stream, one JSON object per event:
      {"delta": "..."}  a chunk of reply text
      {"done": true}    generation finished
      {"error": "..."}  something went wrong mid-stream

    Validation and rate-limit failures are returned as ordinary JSON with a 4xx
    status instead, since the status code can no longer change once streaming
    has started.

    The API key stays on the server — the browser never sees it.
    """
    import chat_service

    if not chat_service.ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY not set — chat endpoint unavailable")
        return jsonify({"error": "Chat is not configured right now."}), 503

    # Render sits behind a proxy, so the real client IP is the first entry of
    # X-Forwarded-For. Spoofable, which is why the daily total cap exists too.
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"

    allowed, reason = chat_service.check_rate_limit(ip)
    if not allowed:
        return jsonify({"error": reason}), 429

    data = request.get_json(silent=True) or {}
    messages = chat_service.sanitize_history(data.get("messages"))
    if not messages:
        return jsonify({"error": "a message is required"}), 400

    def event_stream():
        try:
            for chunk in chat_service.answer_stream(messages):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except anthropic.RateLimitError:
            log.warning("Anthropic rate limit hit on chat")
            yield f"data: {json.dumps({'error': 'The chat is busy right now — please try again shortly.'})}\n\n"
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            log.error("Anthropic API error on chat: %s", exc)
            yield f"data: {json.dumps({'error': 'The chat is unavailable right now.'})}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Stop nginx-style proxies from buffering the stream into one blob.
            "X-Accel-Buffering": "no",
        },
    )


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


init_db()

from mountain_extraction_service import run_mountain_extraction
run_mountain_extraction()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
