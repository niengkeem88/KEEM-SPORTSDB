# ⚽ KEEM SportsDB — Global Soccer Data Platform

A production-grade, end-to-end soccer tracking platform built with **PostgreSQL**, **Python (FastAPI)**, and **Kotlin (Jetpack Compose)**. It ingests live match data from the [Scorebat v3](https://www.scorebat.com/) provider, serves it through a cached REST API, and renders live scores on an Android client.

## Architecture Overview

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Scorebat   │────▶│  Ingestion       │────▶│  PostgreSQL      │
│  (v3 external)        │  (async workers)  │     │  + Redis cache   │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                          │
                                                          ▼
                                                   ┌──────────────────┐
                                                   │  FastAPI REST    │
                                                   │  (uvicorn)       │
                                                   └──────────────────┘
                                                          │
                                                          ▼
                                                   ┌──────────────────┐
                                                   │  Android Client  │
                                                   │  (Jetpack Compose)│
                                                   └──────────────────┘
```

---

## Project Structure

```
KEEM-SPORTSDB/
├── 001_global_soccer_schema.sql    # PostgreSQL DDL (tables, indexes, triggers)
├── .env.example                     # Template for environment variables
├── ingestion/                       # Scorebat ingestion service
│   ├── client.py                    # Async HTTP client with rate limiting
│   ├── models.py                    # SQLAlchemy ORM models
│   ├── database.py                  # Upsert engine (ON CONFLICT DO UPDATE)
│   ├── workers.py                   # 3-tier sync (weekly, lineups, live)
│   ├── config.py                    # Environment-based settings
│   └── main.py                      # Orchestrator entrypoint
├── api/                             # FastAPI REST API
│   ├── main.py                      # App factory + lifespan
│   ├── routers/fixtures.py          # GET /fixtures/live, /{id}, /date/{date}
│   ├── routers/leagues.py           # GET /leagues
│   ├── redis_client.py              # redis.asyncio cache helpers
│   ├── middleware/error_handler.py  # Structured JSON error responses
│   ├── models/                      # Pydantic response schemas
│   └── database.py                  # Async SQLAlchemy session
├── android/                         # Android client (Kotlin + Compose)
│   ├── data/remote/api/SoccerApi.kt # Retrofit interface
│   ├── data/remote/dto/             # @Serializable DTOs (league, fixture, events)
│   ├── data/repository/             # Polling repository implementation
│   ├── domain/                      # Domain models and repository interface
│   └── presentation/               # ViewModel + Compose UI
└── README.md
```

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| [PostgreSQL](https://www.postgresql.org/download/) | 15+ | Primary database |
| [Redis](https://redis.io/download/) | 7+ | Cache layer |
| [Python](https://www.python.org/downloads/) | 3.11+ | Ingestion service & API |
| [JDK](https://jdk.java.net/) | 17+ | Android build |
| [Android Studio](https://developer.android.com/studio) | Hedgehog+ | Android client |

---

## 1. Database Setup

### 1.1 Create the database

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create the database and user
CREATE DATABASE soccerdb;
CREATE USER soccer_user WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE soccerdb TO soccer_user;
\c soccerdb
GRANT ALL ON SCHEMA public TO soccer_user;
\q
```

### 1.2 Apply the schema

```bash
psql -U soccer_user -d soccerdb -f 001_global_soccer_schema.sql
```

This creates all five tables (`leagues`, `seasons`, `teams`, `fixtures`, `standings`), along with indexes, constraints, and the `updated_at` trigger.

---

## 2. Python Environment (Ingestion + API)

### 2.1 Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate     # Linux / macOS
# or .venv\Scripts\activate    # Windows
```

### 2.2 Install dependencies

```bash
# Ingestion service
pip install -r ingestion/requirements.txt

# API server
pip install -r api/requirements-api.txt

# Or install everything at once
pip install -r ingestion/requirements.txt -r api/requirements-api.txt
```

### 2.3 Configure environment

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description | Default |
|---|---|---|
| `SCOREBAT_TOKEN` | Your Scorebat subscription key | *(required)* |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://soccer_user:password@localhost:5432/soccerdb` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `API_PORT` | FastAPI listen port | `8000` |

### 2.4 Run the ingestion service

```bash
# One-off: fetch and upsert all current leagues and teams
python -m ingestion.main
```

The ingestion service starts three workers:
- **Weekly fixtures** — polls every 24 h to sync the next 7 days of matches
- **Pre-match lineups** — disabled (Scorebat free tier does not provide lineups)
- **Live engine** — polls every 30 s, updates live scores and overwrites `live_events_cache`

Press `Ctrl+C` to stop gracefully — all connections are disposed cleanly.

### 2.5 Run the API server

```bash
# Development (with auto-reload)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Open the interactive docs:

| URL | Description |
|---|---|
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/redoc` | ReDoc |
| `http://localhost:8000/health` | Health check |

### 2.6 Verify the API

```bash
curl http://localhost:8000/api/v1/leagues
curl http://localhost:8000/api/v1/fixtures/live
curl http://localhost:8000/api/v1/fixtures/date/2026-06-04
```

---

## 3. Android Client

### 3.1 Open the project in Android Studio

1. Launch **Android Studio**
2. Select **Open an Existing Project**
3. Navigate to the `android/` directory inside the repo
4. Wait for Gradle sync to complete

### 3.2 Configure the API base URL

Edit `android/BuildConfig.kt`:

```kotlin
object BuildConfig {
    // For emulator → host machine
    const val API_BASE_URL = "http://10.0.2.2:8000/"
    // For physical device on same network:
    // const val API_BASE_URL = "http://192.168.x.x:8000/"
}
```

### 3.3 Run the app

- Select an emulator or connected device
- Click **Run** ▶️

The app opens to the **Live Scores** screen, which:
1. Shows a loading spinner on first launch
2. Polls `GET /api/v1/fixtures/live` every 30 seconds
3. Displays each live match as a card with team names, scores, and event count
4. Shows an error state with retry button if the network is unreachable

---

## API Endpoints Reference

| Method | Endpoint | Description | Cache TTL |
|---|---|---|---|
| `GET` | `/api/v1/leagues` | All tracked leagues | 1 hour |
| `GET` | `/api/v1/fixtures/date/{date}` | Fixtures for a specific day | 2 minutes |
| `GET` | `/api/v1/fixtures/live` | Currently in-play matches | 30 seconds |
| `GET` | `/api/v1/fixtures/{id}` | Full fixture detail + events | 30 s (live) / 24 h (finished) |

All endpoints return JSON. List endpoints wrap results in `{ "data": [...], "total": N }`.

---

## Caching Strategy

```
                    ┌──────────┐
                    │  Client   │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │  Redis   │  ← 30 s / 2 min / 1 h / 24 h TTL
                    └────┬─────┘
                         │ (miss)
                    ┌────▼─────┐
                    │PostgreSQL│
                    └──────────┘
```

- **Live fixtures** (`/fixtures/live`, `/fixtures/{id}` while live) → 30 s TTL. The ingestion live engine updates every 60 s, so 30 s ensures clients never see data older than two cycles.
- **Historical fixtures** → 24 h TTL. Once a match is finished, its data is immutable.
- **Leagues** → 1 h TTL. League metadata rarely changes.
- **Date-based fixtures** → 2 min TTL. Schedules are stable within a day.

Redis failures are logged but never break the API — a cache miss falls through to PostgreSQL automatically.

---

## Database Schema (Quick Reference)

```
leagues (id PK, name, country, logo_url, type)
    │
    ├── seasons (id PK, league_id FK, year, start/end_date, is_current)
    │
    └── fixtures (id PK, league_id FK, season_id FK,
                  home_team_id FK, away_team_id FK,
                  match_status, start_time,
                  home_score, away_score,
                  live_events_cache JSONB)
                        │
                   teams (id PK, name, short_code, logo_url)
                        │
                   standings (id PK, season_id FK, team_id FK,
                              rank, points, played, won, drawn, lost,
                              goals_for, goals_against)
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `Connection refused` on DB start | PostgreSQL not running | `sudo systemctl start postgresql` |
| `Upsert error: relation "leagues" does not exist` | Schema not applied | Run `psql -f 001_global_soccer_schema.sql` |
| `401 Unauthorized` from Scorebat | Invalid or missing `SCOREBAT_TOKEN` | Check `.env` and verify your Scorebat token |
| `429 Too Many Requests` | Exceeded rate limit | Lower `API_RATE_LIMIT_RPS` | Requests per second | `0.16` in `.env` to `8.0` |
| Android app shows empty screen | API base URL incorrect | Update `BuildConfig.API_BASE_URL` for your network |
| `git push` asks for password | SSH key not configured | Use `ssh -T git@github.com` to verify |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Database | PostgreSQL 15+ |
| Cache | Redis 7+ |
| Ingestion | Python 3.11+, httpx, SQLAlchemy 2.0 (async) |
| API | FastAPI, uvicorn, Pydantic v2 |
| Android | Kotlin, Jetpack Compose, Hilt, Retrofit, KotlinX Serialization |
| Auth | Scorebat subscription key (server-side only) |
