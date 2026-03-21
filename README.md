# Personal Webpage — jakobreinhardt.eu

A personal website hosted on GitHub Pages with a Flask backend for dynamic features.

## Architecture

- **Frontend**: Static HTML/CSS/JS served by [GitHub Pages](https://pages.github.com/)
- **Backend**: Flask API deployed on [Render](https://dashboard.render.com/)
- **Database**: PostgreSQL hosted on [Neon](https://console.neon.tech/)

## Pages

| File | Content |
|------|---------|
| `index.html` | Landing page |
| `researcher.html` | Research profile & publications |
| `investor.html` | Investor profile |
| `activities.html` | Selected ski tours & visitor suggestion form |

## Backend (`app.py`)

A lightweight Flask API with one resource:

- `POST /api/tours` — submit a tour suggestion (stored in PostgreSQL)
- `GET /api/tours` — retrieve all suggestions (newest first)

CORS is configured to allow requests from `https://jakobreinhardt.eu`.

## Environment Variables (Render)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `ALLOWED_ORIGINS` | Comma-separated allowed origins (defaults to `https://jakobreinhardt.eu`) |

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The app runs on `http://localhost:5000` and falls back to a local SQLite database when `DATABASE_URL` is not set.
