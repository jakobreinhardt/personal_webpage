"""Query the tour_suggestions database and plot entries per minute."""

import os
import sqlite3
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv
import psycopg2
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_rows():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT created_at FROM tour_suggestions ORDER BY created_at")
        rows = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
    else:
        db_path = os.path.join(os.path.dirname(__file__), "tours.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT created_at FROM tour_suggestions ORDER BY created_at")
        rows = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
    return rows


def parse_timestamps(rows):
    timestamps = []
    for raw in rows:
        if isinstance(raw, datetime):
            timestamps.append(raw)
        else:
            ts = raw.replace("Z", "+00:00")
            timestamps.append(datetime.fromisoformat(ts))
    return timestamps


def bucket_per_minute(timestamps):
    buckets = Counter()
    for ts in timestamps:
        key = ts.replace(second=0, microsecond=0)
        buckets[key] += 1
    minutes = sorted(buckets)
    counts = [buckets[m] for m in minutes]
    return minutes, counts


def main():
    rows = get_rows()
    if not rows:
        print("No entries in the database yet.")
        return

    timestamps = parse_timestamps(rows)
    minutes, counts = bucket_per_minute(timestamps)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(minutes, counts, marker="o", linewidth=1.5, markersize=5)
    ax.set_xlabel("Time")
    ax.set_ylabel("Entries")
    ax.set_title("Tour Suggestions per Minute")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
