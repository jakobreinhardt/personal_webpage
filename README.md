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

A lightweight Flask API:

- `POST /api/tours` — submit a tour suggestion (stored in PostgreSQL)
- `GET /api/tours` — retrieve all suggestions (newest first)
- `GET /api/mountain-mentions` — top 10 mountains by how often they appear in suggestions
- `POST /api/chat` — stream a Claude reply for a visitor chat message, as Server-Sent Events (`chat_service.py`)

CORS is configured to allow requests from `https://jakobreinhardt.eu`.

### Chat (`chat_service.py`)

The activities page has a chat widget backed by Claude. The browser holds the
conversation and resends it each turn; the server re-validates it and calls the
Anthropic API so the key never reaches the client.

The reply is streamed back as Server-Sent Events (`{"delta": "..."}` per chunk,
then `{"done": true}`) and rendered live under the input box, so the first words
appear within a second or two. Validation and rate-limit failures are returned as
ordinary JSON with a 4xx status instead, since the status code can no longer
change once streaming has begun.

Because the endpoint is public and billed to a personal API key, spend is capped
in `chat_service.py`:

| Limit | Value |
|-------|-------|
| Model | `claude-opus-5` |
| Max output tokens per reply | 2000 |
| Max characters per message | 1000 |
| History sent to the model | last 12 messages |
| Requests per IP per hour | 15 |
| Requests per day (all visitors) | 300 |

The rate-limit counters live in process memory, so they reset on restart and are
tracked per gunicorn worker. That is a spend brake, not an exact quota — move
them into PostgreSQL if the site ever runs more than one worker or needs the
limit enforced strictly.

## Environment Variables (Render)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `ALLOWED_ORIGINS` | Comma-separated allowed origins (defaults to `https://jakobreinhardt.eu`) |
| `ANTHROPIC_API_KEY` | Anthropic API key — used by mountain extraction and the chat endpoint |

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The app runs on `http://localhost:5000` and falls back to a local SQLite database when `DATABASE_URL` is not set.
