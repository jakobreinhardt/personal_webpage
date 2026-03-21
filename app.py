import os
import sqlite3
from datetime import datetime, timezone

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
    conn.commit()
    cur.close()
    conn.close()


def db_rows_to_dicts(conn, cur):
    """Convert cursor results to list of dicts for both SQLite and PostgreSQL."""
    if DATABASE_URL:
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    else:
        return [dict(row) for row in cur.fetchall()]


# ---------- routes ----------

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/tours", methods=["POST"])
def add_tour():
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

    return jsonify({"status": "ok", "created_at": created_at}), 201


@app.route("/api/tours", methods=["GET"])
def list_tours():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, text, created_at FROM tour_suggestions ORDER BY created_at DESC"
    )
    rows = db_rows_to_dicts(conn, cur)
    cur.close()
    conn.close()
    return jsonify(rows)


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
