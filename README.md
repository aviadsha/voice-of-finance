# 🎙️ Voice of Finance

**AI-powered financial news platform that turns YouTube interviews into high-quality, source-cited financial articles — with a community and a freemium model built in.**

Paste a YouTube link to an interview with a CEO, fund manager or economist. Voice of Finance downloads the audio,
transcribes it with **OpenAI Whisper**, extracts topics, companies, quotes and insights with **Claude**, and then writes
three article formats (summary, deep-dive and analysis). Every quote in every article is checked against the
transcript and linked to the exact second of the video.

| | |
|---|---|
| **Backend** | FastAPI (async) · SQLAlchemy 2 (asyncpg) · Alembic · Pydantic v2 |
| **Frontend** | Next.js 16 (App Router, React Server Components) · TypeScript · Tailwind CSS · NextAuth.js |
| **Database** | PostgreSQL 16 (local Docker, Supabase, Railway, Fly, Neon…) |
| **AI** | OpenAI Whisper (transcription) · Anthropic Claude (insight extraction + article writing) |
| **Media** | yt-dlp + ffmpeg |
| **Hosting** | Vercel (frontend) · Fly.io or Railway (backend) · Supabase (Postgres) |

---

## Table of contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Quick start (Docker)](#quick-start-docker)
4. [Local development](#local-development)
5. [Configuration](#configuration)
6. [The agents](#the-agents)
7. [Freemium & community rules](#freemium--community-rules)
8. [API documentation](#api-documentation)
9. [Data model](#data-model)
10. [Testing & CI](#testing--ci)
11. [Deployment](#deployment)
12. [Project structure](#project-structure)
13. [Security notes](#security-notes)
14. [Roadmap](#roadmap)

---

## Features

### 1. YouTube interview extraction agent
- Validates and canonicalises any YouTube URL (`watch`, `youtu.be`, `shorts`, `embed`, `live`).
- Downloads audio only with **yt-dlp**, converts to 16 kHz mono MP3 with ffmpeg and splits long interviews into
  chunks that fit Whisper's 25 MB upload limit.
- Transcribes with **Whisper** (`verbose_json`) keeping **timestamped segments**.
- Uses Claude to extract a summary, speakers, **topics**, **companies + tickers**, **key quotes**, **insights** and
  overall **sentiment**. Quotes are verified against the transcript and receive a timestamp.
- Everything is stored in PostgreSQL with full video metadata (title, channel, thumbnail, duration, publish date).

### 2. Article generation agent
- Generates three formats with Claude: **Summary** (free), **Deep Dive** and **Analysis** (premium).
- Each article gets a compelling **headline**, an SEO **meta description** (≤160 chars), a summary, tags and tickers.
- **Factual-accuracy guardrails:** the model may only quote the transcript; every citation is fuzzy-matched against
  the transcript, marked `verified`/unverified, linked to `youtube.com/watch?v=…&t=123s`, and the article stores a
  `citation_accuracy` score.
- Regenerate any format at any time from the admin UI/API.

### 3. Community & freemium
- Email/password signup & login (JWT backend tokens, NextAuth sessions on the frontend).
- **Follow companies (tickers) and topics** → personalised feed.
- **Freemium:** free users read summary articles plus the headline, summary and sample citations of premium articles; Premium unlocks full deep-dives &
  analyses, full transcripts, every citation, **portfolio tracking** and **verified-analyst insights**.
- **Threaded comments** with up/down votes and automatic moderation (scam/spam patterns and link-stuffing are rejected; shouting and repeated characters are flagged).
- **Reputation system** & leaderboard; high-reputation members can apply to become **verified analysts**, who can then
  publish their own (optionally premium) insights and submit interviews for processing.
- Admin workflow for reviewing analyst applications and moderating articles.

---

## Architecture

```mermaid
flowchart LR
    subgraph Client
        B[Browser]
    end

    subgraph Vercel["Frontend · Next.js (Vercel)"]
        RSC[React Server Components]
        NA[NextAuth.js<br/>encrypted session cookie]
        PX["/api/backend/* proxy<br/>(same-origin, adds JWT)"]
    end

    subgraph API["Backend · FastAPI (Fly.io / Railway)"]
        R[REST API /api/v1<br/>OpenAPI docs /docs]
        BG[Background tasks]
        subgraph Agents
            A1[YouTube Extraction Agent]
            A2[Article Generation Agent]
            A3[Community Agent]
        end
    end

    DB[(PostgreSQL<br/>Supabase)]
    YT[(YouTube)]
    W[[OpenAI Whisper]]
    C[[Anthropic Claude]]

    B --> RSC & NA & PX
    RSC -->|server-side fetch + JWT| R
    NA -->|/auth/login| R
    PX --> R
    R --> A3
    R -->|POST /interviews| BG
    BG --> A1 --> A2
    A1 -->|yt-dlp + ffmpeg| YT
    A1 -->|audio chunks| W
    A1 -->|insights JSON| C
    A2 -->|articles JSON| C
    A1 & A2 & A3 & R --> DB
```

### Processing pipeline

```mermaid
sequenceDiagram
    participant U as Admin / verified analyst
    participant API as FastAPI
    participant X as Extraction agent
    participant G as Article agent
    participant DB as PostgreSQL
    U->>API: POST /api/v1/interviews {youtube_url, formats}
    API->>DB: Interview(status=pending)
    API-->>U: 202 Accepted (interview id)
    API->>X: background task
    X->>X: downloading → yt-dlp audio (chunked)
    X->>X: transcribing → Whisper (timestamped segments)
    X->>X: analyzing → Claude: topics, companies, quotes, insights
    X->>DB: transcript + insights (quotes verified)
    X->>G: generating
    loop summary · deep_dive · analysis
        G->>G: Claude writes article (JSON)
        G->>G: verify citations against transcript
        G->>DB: Article(published, citation_accuracy)
    end
    G->>DB: Interview(status=completed)
```

**Key design decisions**

- **Async end-to-end.** FastAPI + SQLAlchemy asyncpg; blocking work (yt-dlp, ffmpeg) runs in worker threads.
- **The backend JWT never reaches the browser.** NextAuth keeps it inside its encrypted, HTTP-only cookie. Server
  components call FastAPI directly; client components go through the same-origin `/api/backend/*` proxy, which
  rejects cross-origin mutating requests (CSRF protection).
- **Paywall enforced on the server.** The API itself truncates premium content for non-premium users — the UI only
  renders what it receives.
- **Agents are plain classes with injected clients** (`LLMClient`, `Transcriber`, `AudioDownloader`), so the whole
  pipeline is unit-tested with fakes and no network access.
- **Portable JSON columns.** `JSON` on SQLite, `JSONB` + GIN indexes on PostgreSQL for ticker/tag filtering.

---

## Quick start (Docker)

Requirements: Docker with Compose v2.

```bash
git clone https://github.com/aviadsha/voice-of-finance.git
cd voice-of-finance
cp .env.example .env          # optional: add OPENAI_API_KEY and ANTHROPIC_API_KEY
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | Web app |
| http://localhost:8000/docs | Interactive API docs (Swagger UI) |
| http://localhost:8000/redoc | API reference (ReDoc) |
| http://localhost:8000/health | Health check (includes DB connectivity) |

The stack runs migrations automatically and seeds a **demo interview with two articles** (one free, one premium),
so you can explore everything without any API keys.

Create an admin account (needed to ingest interviews and review analyst applications):

```bash
docker compose exec backend python -m app.cli create-admin admin@example.com
```

Then log in at http://localhost:3000/login and open **Ingest** to process a real YouTube interview (requires
`OPENAI_API_KEY` and `ANTHROPIC_API_KEY`).

> **Tip:** Premium is a mock checkout in development — click **Upgrade** on the Pricing page to unlock everything.

---

## Local development

### Backend (Python 3.12+, ffmpeg)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # edit as needed

docker compose up -d db              # or point DATABASE_URL at Supabase/any Postgres
alembic upgrade head
python -m app.cli seed               # optional demo content
python -m app.cli create-admin admin@example.com
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

Process an interview from the command line (synchronously, prints progress):

```bash
python -m app.cli ingest "https://www.youtube.com/watch?v=VIDEO_ID" --formats summary analysis
```

Create a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe change"
```

### Frontend (Node 20+)

```bash
cd frontend
cp .env.example .env.local           # API_URL, NEXTAUTH_URL, NEXTAUTH_SECRET
npm install
npm run dev                          # http://localhost:3000
```

### Using Supabase as the database

1. Create a project at [supabase.com](https://supabase.com).
2. **Project Settings → Database → Connection string**. Copy the **Session pooler** URI (port 5432) and set it as
   `DATABASE_URL` in `backend/.env` (the `postgres://` scheme is converted to `postgresql+asyncpg://` automatically).
   If you use the **Transaction pooler** (port 6543) also set `DATABASE_PGBOUNCER=true`.
3. Run `alembic upgrade head` once to create the schema.

Authentication is handled by the app itself (FastAPI JWT + NextAuth), so Supabase Auth is not required.

---

## Configuration

All settings are environment variables. See the annotated examples:
[`/.env.example`](.env.example) (docker compose), [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example).

### Backend

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` refuses to start with the default JWT secret |
| `DATABASE_URL` | built from `POSTGRES_*` | Full Postgres URL (Supabase, Railway, Fly, Neon…) |
| `POSTGRES_USER/PASSWORD/HOST/PORT/DB` | `postgres/postgres/localhost/5432/voice_of_finance` | Used when `DATABASE_URL` is empty |
| `DATABASE_PGBOUNCER` | `false` | Disable prepared-statement cache for transaction poolers |
| `JWT_SECRET_KEY` | dev value | **Required in production.** Long random string |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 days) | API token lifetime |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `OPENAI_API_KEY` / `WHISPER_MODEL` | – / `whisper-1` | Transcription |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | – / `claude-sonnet-4-5` | Insight extraction & article generation |
| `ANTHROPIC_MAX_TOKENS` | `8000` | Max tokens per Claude response |
| `MAX_VIDEO_DURATION_SECONDS` | `10800` | Reject videos longer than this |
| `WHISPER_MAX_CHUNK_MB` / `WHISPER_CHUNK_SECONDS` | `24` / `600` | Audio chunking for Whisper |
| `ANALYST_VERIFICATION_THRESHOLD` | `100` | Reputation needed to apply as verified analyst |
| `BILLING_MOCK_ENABLED` | `true` | Self-service upgrade without payment (disable in production until Stripe is wired) |
| `RUN_MIGRATIONS` / `SEED_DEMO_DATA` | `true` / `false` | Container entrypoint behaviour |

### Frontend

| Variable | Description |
|---|---|
| `API_URL` | Backend base URL as reachable from the Next.js server (e.g. `https://voice-of-finance-api.fly.dev`) |
| `NEXTAUTH_URL` | Public URL of the frontend |
| `NEXTAUTH_SECRET` | Random secret for encrypting session cookies (`openssl rand -base64 32`) |

---

## The agents

All agents live in [`backend/app/agents`](backend/app/agents).

| Agent | File | Responsibilities |
|---|---|---|
| **YouTube Extraction Agent** | `youtube_extractor.py` | Metadata → audio download → chunked Whisper transcription → Claude insight extraction → quote verification. Updates interview `status` at each stage (`pending → downloading → transcribing → analyzing → generating → completed/failed`). |
| **Article Generation Agent** | `article_generator.py` | Builds format-specific prompts from transcript + insights, calls Claude for structured JSON, verifies citations, computes `citation_accuracy`, generates unique slugs, reading time, tags and tickers. |
| **Community Agent** | `community.py` | Comment moderation, threaded comments, voting & reputation, leaderboard, analyst applications/review, personalised feed (follows → tickers/tags). |
| **Pipeline** | `pipeline.py` | Orchestrates extraction + generation as a background task with its own DB session; failures are recorded on the interview so they can be retried via `POST /interviews/{id}/reprocess`. |

Shared helpers: [`text_utils.py`](backend/app/agents/text_utils.py) (transcript index for quote verification,
ticker/topic normalisation), [`services/ai.py`](backend/app/services/ai.py) (Claude & Whisper clients with robust JSON
parsing) and [`services/youtube.py`](backend/app/services/youtube.py) (yt-dlp wrapper).

---

## Freemium & community rules

| | Free | Premium ($12/mo) |
|---|---|---|
| Summary articles | ✅ | ✅ |
| Deep Dive & Analysis articles | Headline + summary | ✅ Full |
| Premium article citations | First 2 | ✅ All |
| Full interview transcripts | – | ✅ |
| Follow companies & topics, personalised feed | ✅ | ✅ |
| Comments, votes, reputation | ✅ | ✅ |
| Portfolio tracking (+ coverage of holdings) | – | ✅ |
| Premium verified-analyst insights | – | ✅ |

Reputation: **+1** per comment, **+5** per upvote received, **−2** per downvote received (never below 0). Members
reaching `ANALYST_VERIFICATION_THRESHOLD` can apply to become verified analysts; an admin approves or rejects the
application. Verified analysts get a badge, can publish insights and can submit interviews for processing.

Roles: `user`, `analyst`, `admin`. Interview ingestion is restricted to admins and verified analysts because every
run consumes paid AI credits.

---

## API documentation

FastAPI generates interactive documentation automatically:

- Swagger UI: **`/docs`** · ReDoc: **`/redoc`** · OpenAPI schema: **`/api/v1/openapi.json`**

Use the **Authorize** button in Swagger UI (OAuth2 password flow → `POST /api/v1/auth/token`) to try authenticated
endpoints.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/signup` · `POST /auth/login` · `POST /auth/token` |
| Users | `GET/PATCH /users/me` · `GET /users/{id}` · `PATCH /admin/users/{id}` |
| Follows & feed | `GET/POST /me/follows` · `DELETE /me/follows/{id}` · `GET /me/feed` |
| Portfolio (premium) | `GET/POST /me/portfolio` · `DELETE /me/portfolio/{id}` |
| Subscription | `GET /subscription/plans` · `POST /subscription/upgrade` · `POST /subscription/cancel` |
| Interviews | `POST /interviews` · `GET /interviews` · `GET/DELETE /interviews/{id}` · `GET /interviews/{id}/transcript` (premium) · `POST /interviews/{id}/reprocess` · `POST /interviews/{id}/articles` |
| Articles | `GET /articles` (filters: `format`, `ticker`, `tag`, `premium`, `interview_id`, `q`) · `POST /articles` (verified analysts) · `GET /articles/{slug}` · `POST /articles/{slug}/status` (admin) |
| Community | `GET/POST /articles/{slug}/comments` · `POST /comments/{id}/vote` · `DELETE /comments/{id}` · `GET /community/leaderboard` · `GET/POST /community/analyst-applications` · `POST /community/analyst-applications/{id}/review` |

All paths are prefixed with `/api/v1`. `GET /health` reports API and database status.

---

## Data model

```mermaid
erDiagram
    USERS ||--o{ FOLLOWS : follows
    USERS ||--o{ PORTFOLIO_HOLDINGS : owns
    USERS ||--o{ COMMENTS : writes
    USERS ||--o{ COMMENT_VOTES : casts
    USERS ||--o{ ANALYST_APPLICATIONS : submits
    USERS ||--o{ ARTICLES : authors
    USERS ||--o{ INTERVIEWS : submits
    INTERVIEWS ||--o{ ARTICLES : "generates"
    ARTICLES ||--o{ COMMENTS : has
    COMMENTS ||--o{ COMMENTS : replies
    COMMENTS ||--o{ COMMENT_VOTES : receives

    USERS { uuid id string email string role string tier int reputation bool is_verified_analyst }
    INTERVIEWS { uuid id string youtube_video_id string status text transcript jsonb transcript_segments jsonb topics jsonb companies jsonb key_quotes jsonb insights }
    ARTICLES { uuid id string slug string format bool is_premium string headline string meta_description text content jsonb citations float citation_accuracy jsonb tickers jsonb tags }
    COMMENTS { uuid id uuid article_id uuid parent_id text body int score }
    FOLLOWS { uuid id string follow_type string value }
    PORTFOLIO_HOLDINGS { uuid id string ticker numeric shares numeric average_cost }
    ANALYST_APPLICATIONS { uuid id text credentials string status }
```

The schema is managed with Alembic ([`backend/alembic/versions`](backend/alembic/versions)).

---

## Testing & CI

```bash
cd backend
pytest -q                                   # fast, in-process SQLite
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/vof_test pytest -q   # against PostgreSQL
ruff format --check app tests alembic && ruff check app tests alembic

cd ../frontend
npm run lint && npm run typecheck && npm run build
```

The tests exercise the full HTTP API including the complete extraction → article pipeline using fake Whisper,
Claude and yt-dlp clients (no network or API keys needed).

[GitHub Actions](.github/workflows/ci.yml) runs backend lint + tests (SQLite and PostgreSQL), verifies migrations
match the models (`alembic check`), lints/type-checks/builds the frontend and builds both Docker images.

---

## Deployment

### Database — Supabase
Create a project and copy the connection string as described in [Using Supabase](#using-supabase-as-the-database).

### Backend — Fly.io
```bash
cd backend
fly launch --no-deploy --copy-config        # choose a unique app name
fly secrets set \
  DATABASE_URL="postgresql://..." \
  JWT_SECRET_KEY="$(openssl rand -base64 48)" \
  OPENAI_API_KEY="sk-..." ANTHROPIC_API_KEY="sk-ant-..." \
  CORS_ORIGINS="https://your-app.vercel.app" \
  BILLING_MOCK_ENABLED=false
fly deploy
```
[`fly.toml`](backend/fly.toml) runs `alembic upgrade head` as a release command and health-checks `/health`.

### Backend — Railway (alternative)
Create a service from this repo with **root directory `backend`**. [`railway.json`](backend/railway.json) builds the
Dockerfile and health-checks `/health`. Add a Railway Postgres (or Supabase) and set the same variables as above
(`ENVIRONMENT=production`, `DATABASE_URL`, `JWT_SECRET_KEY`, AI keys, `CORS_ORIGINS`). Migrations run on start
(`RUN_MIGRATIONS=true`).

### Frontend — Vercel
1. Import the repository in Vercel and set **Root Directory** to `frontend` (framework auto-detected: Next.js).
2. Environment variables: `API_URL` (your backend URL), `NEXTAUTH_URL` (your Vercel URL), `NEXTAUTH_SECRET`.
3. Deploy. Add the Vercel URL to the backend's `CORS_ORIGINS`.

The frontend also ships a standalone [`Dockerfile`](frontend/Dockerfile) for any container host.

### Production checklist
- [ ] `ENVIRONMENT=production` and a strong `JWT_SECRET_KEY` / `NEXTAUTH_SECRET`
- [ ] `BILLING_MOCK_ENABLED=false` (until a payment provider is integrated)
- [ ] `CORS_ORIGINS` set to your frontend domain
- [ ] Create an admin: `python -m app.cli create-admin you@example.com` (e.g. `fly ssh console`)
- [ ] Database backups enabled (Supabase does this by default)

---

## Project structure

```
voice-of-finance/
├── backend/
│   ├── app/
│   │   ├── agents/            # extraction, article generation, community, pipeline
│   │   ├── api/               # deps (auth/roles) + routes
│   │   ├── core/              # settings, database, security
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── services/          # Claude, Whisper and yt-dlp clients
│   │   ├── cli.py             # create-admin · ingest · seed
│   │   └── main.py            # FastAPI app
│   ├── alembic/               # migrations
│   ├── tests/                 # pytest suite with AI/YouTube fakes
│   ├── Dockerfile · fly.toml · railway.json
│   └── .env.example
├── frontend/
│   ├── src/app/               # pages: home, articles/[slug], interviews/[id], login, signup,
│   │                          #        dashboard, portfolio, pricing, community, admin/ingest
│   ├── src/app/api/           # NextAuth route + backend proxy
│   ├── src/components/        # UI components
│   ├── src/lib/               # API clients, auth config, types
│   ├── Dockerfile
│   └── .env.example
├── docker-compose.yml
├── .env.example
└── .github/workflows/ci.yml
```

---

## Security notes

- Passwords hashed with bcrypt; API tokens are signed JWTs (HS256) with expiry.
- The API token is stored only inside NextAuth's encrypted HTTP-only cookie; the browser never sees it.
- The `/api/backend` proxy only forwards to the configured backend, validates path segments and rejects
  cross-origin state-changing requests.
- Role checks (`user` / `analyst` / `admin`) and the premium paywall are enforced by the API.
- Login redirects only accept same-site relative URLs (no open redirects).
- Containers run as non-root users.
- AI-generated content can be wrong. Citations are verified against the transcript, but articles are not financial
  advice — keep a human in the loop for anything you publish.

---

## Roadmap

- Stripe checkout & webhooks for Premium (replace the mock billing endpoints)
- Durable job queue (e.g. Arq/Celery + Redis) and retries for long interviews
- Email notifications for followed companies/topics
- Real-time market data for portfolio valuation
- Speaker diarisation and multi-language transcripts
- Full-text search with PostgreSQL `tsvector`

---

## License

No license has been chosen yet — all rights reserved by the repository owner until one is added.
