# NIVARA — DevSecOps Digital Twin for Cyber-Attack Simulation

[![CI](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/ci.yml)
[![CD](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/cd.yml/badge.svg?branch=main)](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/cd.yml)
![Backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20SQLite-009688)
![Frontend](https://img.shields.io/badge/frontend-Rust%20%2F%20Leptos%20(WASM)-orange)
![Docker](https://img.shields.io/badge/runtime-Docker%20Compose-2496ED)

> **NIVARA is an isolated security lab built around a realistic synthetic e-commerce bookstore.** It runs seven predefined, safe attack scenarios against a reproducible digital twin of the shop, shows the attack path and which security controls caught or missed it, applies a fix, replays the *same* scenario, and proves the improvement with a deterministic before/after security score and a printable report.

Built by **Team NIVARA** for the **Agnita 2026** hackathon (project code name *CIPHER05*).

```text
 ① CREATE  →  ② ATTACK  →  ③ OBSERVE  →  ④ FIX  →  ⑤ REPLAY  →  Before / After proof
 twin         safe          attack path   apply      same           score + HTML/JSON
 (Docker)     scenario      + control     the        scenario       report
                            matrix        remedy     again
```

---

## Table of contents

1. [Key features](#key-features)
2. [Architecture](#architecture)
3. [Tech stack](#tech-stack)
4. [Repository layout](#repository-layout)
5. [Getting started](#getting-started)
6. [Configuration](#configuration)
7. [The Security Lab: seven scenarios](#the-security-lab-seven-scenarios)
8. [Security scoring](#security-scoring)
9. [Reports](#reports)
10. [API reference](#api-reference)
11. [Data model and synthetic data](#data-model-and-synthetic-data)
12. [Frontend](#frontend)
13. [CI/CD and DevSecOps pipeline](#cicd-and-devsecops-pipeline)
14. [Safety guardrails](#safety-guardrails)
15. [Testing](#testing)
16. [Helper scripts](#helper-scripts)
17. [Five-minute demo script](#five-minute-demo-script)
18. [Current status and known limitations](#current-status-and-known-limitations)
19. [Team, ownership and Git workflow](#team-ownership-and-git-workflow)
20. [Troubleshooting](#troubleshooting)

---

## Key features

**NIVARA Bookstore, the sample application**
- Catalog with search, category filter, sorting and pagination
- Registration and login with JWT (24-hour tokens), roles `customer` and `admin`
- Cart, coupon preview, checkout with a **fake payment** only, order history
- Book reviews and ratings (one per user per book)
- Admin endpoints for books, inventory and users
- 500 books, 250 authors, 20 categories, 207 users, 1,500 orders, 1,500 reviews and 25 coupons, all generated **deterministically** from a fixed seed

**NIVARA Security Lab, the product**
- 7 scripted scenarios covering configuration, supply chain, secrets, application, API and business-logic layers
- Run, poll, observe, fix, replay, all driven from the UI or the REST API
- Attack-path graph and a **security control matrix** (`detected` / `partial` / `missed`)
- **Deterministic, transparent scoring** (0–100, six weighted dimensions, letter grade)
- HTML and JSON **security reports** with before/after scores and detection gaps
- One-command **twin reset** back to the clean seeded state
- Structured `SecurityEvent` telemetry written by every scenario

**DevSecOps pipeline**
- GitHub Actions CI: Rust checks, Python lint and tests, Trivy filesystem scan, Gitleaks, Docker image build and Trivy image scan
- GitHub Actions CD: build the full stack, wait for health checks, smoke-test `/health`, seed data
- On-demand Trivy and Gitleaks containers through a Compose `security` profile

---

## Architecture

NIVARA is deliberately **not** a microservice system: one frontend, one backend, one database technology, one isolated twin.

```text
                         USER BROWSER
                              │
                              ▼
              ┌──────────────────────────────────┐
              │ Rust / Leptos CSR frontend (WASM) │   served by nginx on :3000
              │ Bookstore UI  +  Security Lab UI  │   /api/* proxied to backend
              └────────────────┬─────────────────┘
                               │ JSON over HTTP (single API origin)
                               ▼
              ┌──────────────────────────────────┐
              │      FastAPI application :8000    │
              │ /api/store  /api/lab              │
              │ /api/security  /api/reports       │
              │ /health                           │
              └───────┬──────────────┬───────────┘
                      │              │
                      ▼              ▼
              ┌────────────┐   ┌─────────────────────────┐
              │   SQLite   │   │ Python scenario engine  │  (in-process module,
              │ (WAL mode, │   │ ScenarioRunner + S01–S07│   not a separate API)
              │  file in a │   └───────────┬─────────────┘
              │  Docker    │               │ HTTP calls to TWIN_URL
              │  volume)   │               ▼
              └────────────┘      the bookstore twin itself
                      ▲           (TWIN_URL → the same backend)
                      │                    │
                      │       Findings + SecurityEvents
                      │                    ▼
                      └──────────  Scoring engine  →  Control matrix  →  Report
                                   (app/security)

        On demand (Compose profile "security"):  Trivy   Gitleaks
```

**How the twin works.** `TWIN_URL` points at the backend itself (`http://localhost:8000`). A scenario flips a *deliberately vulnerable* code path on through the internal `POST /api/lab/_config` endpoint, attacks the bookstore API over HTTP with `httpx`, records `Finding` rows, then restores safe mode in a `finally` block. "Apply Fix" switches the vulnerable flag off and remembers that fix so the replay cannot switch it back on. "Reset" wipes every table and re-seeds the data.

**Design rules the team agreed on**
- Rust is used only for presentation and state. Attack logic, scoring, database access and secrets stay in Python.
- The attack engine is a Python module, **not** an HTTP service.
- Scenarios, scoring and pass/fail logic are deterministic and do not depend on an LLM.
- Only synthetic data and clearly fake secrets are ever used.

The full design rationale is in [`NIVARA_Updated_Architecture.md`](NIVARA_Updated_Architecture.md).

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Rust, **Leptos 0.6** (client-side rendering), `leptos_router`, `gloo-net`, compiled to WebAssembly with **Trunk** |
| Frontend serving | nginx (Alpine) with SPA fallback and an `/api/` reverse proxy |
| Backend | **Python 3.11**, **FastAPI**, Uvicorn, Pydantic v2 / `pydantic-settings` |
| Database | **SQLite** (WAL mode, foreign keys on) via **SQLModel** / SQLAlchemy |
| Auth | JWT (`python-jose`), bcrypt password hashing (`passlib`, `bcrypt<5`) |
| Synthetic data | **Faker** (`en_IN` locale, pinned to `faker==40.41.0`) with a fixed seed |
| Scenario HTTP client | `httpx` (async) |
| Reports | Jinja2 HTML template + JSON |
| Containers | Docker, Docker Compose |
| CI/CD | GitHub Actions |
| Security tooling | **Trivy** (dependencies, images), **Gitleaks** (secrets) |
| Tests | `pytest`, `pytest-asyncio`, `ruff` (lint) |

---

## Repository layout

```text
TEAM-NIVARA/
├── backend-python/              # FastAPI backend (single API)
│   ├── app/
│   │   ├── main.py              # app factory, CORS, router mounting, /health
│   │   ├── config.py            # settings from env / .env
│   │   ├── auth/jwt.py          # token creation, current-user dependencies
│   │   ├── db/                  # models.py, session.py, seed.py (deterministic)
│   │   ├── routes/
│   │   │   ├── store/           # auth, catalog, cart, orders, reviews, admin
│   │   │   ├── lab/             # scenario lifecycle (run/poll/fix/replay/reset)
│   │   │   ├── security/        # findings, attack path, controls, scores
│   │   │   └── reports/         # generate + download reports
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── lab/                 # ScenarioRunner, BaseScenario, event collector
│   │   └── security/            # scoring.py, control_matrix.py,
│   │                            #   report_generator.py, templates/report.html
│   ├── tests/                   # pytest suite (incl. tests/security/)
│   ├── env.example              # copy to .env
│   ├── requirements.txt
│   └── Dockerfile
├── frontend-rust/               # Leptos CSR app
│   ├── src/                     # app.rs, pages/, components/, api/, auth.rs, poll.rs, snapshot.rs
│   ├── assets/style.css
│   ├── index.html  Trunk.toml  Cargo.toml
│   ├── nginx.conf
│   └── Dockerfile               # multi-stage: Trunk build → nginx
├── scenarios/                   # one package per attack scenario (S01 … S07)
├── scripts/
│   ├── reset_twin.py            # reset the twin to the clean seeded state
│   └── generate_report.py       # CLI report generator
├── shared/                      # reserved for the shared result-schema contract
├── docs/scoring.md              # scoring formula reference
├── .github/
│   ├── workflows/ci.yml  cd.yml
│   └── CODEOWNERS
├── docker-compose.yml
├── NIVARA_Updated_Architecture.md
└── README.md
```

---

## Getting started

### Prerequisites

| Tool | Needed for |
|---|---|
| Docker and Docker Compose v2 | the recommended full-stack run |
| Python 3.11+ | running the backend, tests and scripts locally |
| Rust (stable) + `wasm32-unknown-unknown` target + [Trunk](https://trunkrs.dev) | only for local frontend development |
| Trivy and Gitleaks CLIs *(optional)* | scenarios S02 and S03 use them if they are on `PATH` |

### Option A: full stack with Docker (recommended)

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend (bookstore + Security Lab) | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Interactive API docs (Swagger UI) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

The backend image seeds the synthetic dataset at build time. The SQLite file lives in the `bookstore-data` Docker volume. The frontend container waits for the backend health check before it starts.

Stop everything with `docker compose down` (add `-v` to also delete the database volume).

### Option B: local development

**Backend**

```bash
cd backend-python
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp env.example .env                                    # then edit JWT_SECRET
python app/db/seed.py                                  # create + seed data/bookstore.db
uvicorn app.main:app --reload --port 8000
```

**Frontend** (in a second terminal)

```bash
cd frontend-rust
rustup target add wasm32-unknown-unknown
cargo install --locked trunk
trunk serve                                            # http://localhost:3000
```

`Trunk.toml` proxies `/api/*` to `http://localhost:8000/api/`, so the browser talks to one origin and no CORS setup is needed in dev.

### Sample accounts (synthetic, seeded)

| Role | Email | Password |
|---|---|---|
| Demo customer | `demo@nivara.dev` | `Demo@1234` |
| Demo admin | `demoadmin@nivara.dev` | `DemoAdmin@1234` |
| Customers (200) | `user1@nivara.dev` … `user200@nivara.dev` | `Test@1234` |
| Admins (5) | `admin1@nivara.dev` … `admin5@nivara.dev` | `Admin@1234` |

Coupon codes: `SAVE10`, `SAVE20`, `BOOK15`, `READ25`, `FEST30`, plus 20 generated codes.

> These credentials exist only in the synthetic dataset. Never reuse them anywhere real.

### Resetting the twin

```bash
python scripts/reset_twin.py            # asks for confirmation (type "reset")
python scripts/reset_twin.py --yes      # no prompt
python scripts/reset_twin.py --docker   # reset inside the running Compose backend
```

The same reset is available from the API: `POST /api/lab/reset`.

---

## Configuration

Settings are read from environment variables and from `backend-python/.env` (copy `backend-python/env.example`). Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/bookstore.db` | SQLite database. A relative path is anchored to `backend-python/`. |
| `JWT_SECRET` | `dev-only-placeholder-change-me` | JWT signing secret. **Always override.** Compose falls back to `nivara_dev_secret_change_in_prod`. |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token lifetime (24 h) |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `SEED` | `42` | Faker seed for the deterministic dataset |
| `TWIN_URL` | `http://localhost:8000` | Target URL for scenarios (must contain a safe host, see [guardrails](#safety-guardrails)) |
| `DEBUG` | `false` | Debug flag (also toggled by S01) |
| `DEBUG_SQLI_MODE` | `false` | Vulnerable code path for S04 |
| `DEBUG_PRICE_MODE` | `false` | Vulnerable code path for S07 (checkout trusts `client_total`) |
| `DEBUG_ACCESS_MODE` | `false` | Vulnerable code path for S06 (skips order ownership check) |
| `SQL_ECHO` | `false` | Log SQL statements |

The three `DEBUG_*_MODE` flags **must stay `false`** outside a lab run. The scenarios switch them on and off themselves.

---

## The Security Lab: seven scenarios

All scenarios live in [`scenarios/`](scenarios), extend `BaseScenario` (`setup → execute → teardown → get_controls`) and return the shared result schema.

| ID | Scenario | Layer | Severity (lab catalogue) | What it does | Controls scored |
|---|---|---|---|---|---|
| **S01** | Misconfiguration | deployment / config | MEDIUM | Turns on debug and wildcard-CORS in the twin, then checks `/docs` exposure, the CORS header and `/health` hints | `debug_mode_off`, `cors_restriction`, `jwt_secret_strength`, `logging` |
| **S02** | Weak dependency | supply chain | HIGH | Runs Trivy against the backend image or dependencies (simulated scan if the CLI is missing) | `trivy_scan`, `ci_gate`, `logging` |
| **S03** | Leaked credential | secrets / CI | CRITICAL | Writes a **fake** secret fixture (`ghp_FAKESECRET…`), scans it with Gitleaks, always removes the fixture | `gitleaks`, `ci_gate`, `logging` |
| **S04** | SQL injection | application | HIGH | Probes book search with the harmless marker `NIVARA_TEST_SQLI' OR '1'='1` and compares baseline vs injected result counts | `sql_injection_protection`, `logging` |
| **S05** | Rate-limit failure | authentication / API abuse | MEDIUM | Fires a burst of 50 failed logins at `demo@nivara.dev`, then checks for 429s and account lockout | `rate_limiting`, `account_lockout`, `logging` |
| **S06** | Insecure API / broken access control | API authorization | HIGH | Customer A (`user1@`) requests Customer B's (`user2@`) order using their own token | `api_authorization`, `logging` |
| **S07** | Price / coupon manipulation | business logic | HIGH | Adds the priciest in-stock book, previews `SAVE20`, then submits checkout with `client_total = 1.00` | `price_validation`, `business_validation`, `logging` |

Severity, layer and attack path shown in a run result come from each scenario class; the catalogue endpoint (`GET /api/lab/scenarios`) reports the values in the table above. S03 is listed as CRITICAL in the catalogue and HIGH in the scenario class.

### Attack paths

| ID | Path |
|---|---|
| S01 | configuration → debug_endpoint → application → data_exposure |
| S02 | supply_chain → requirements_file → trivy_scan → ci_gate |
| S03 | secret_fixture → repository → gitleaks_scan → ci_gate |
| S04 | attacker → search_endpoint → query_builder → sqlite_db |
| S05 | attacker → login_endpoint → auth_service → user_db |
| S06 | customer_a → order_api → authorization_check → order_db |
| S07 | customer → cart → checkout → pricing_logic |

### Run lifecycle

```text
POST /api/lab/run/{id}          → 202 {run_id}        (background task, status: pending → running → completed | failed)
GET  /api/lab/status/{run_id}   → poll progress (0 / 50 / 100)
GET  /api/security/findings/…   → shared-contract result, controls, attack path
GET  /api/lab/fix/{run_id}      → recommendation text
POST /api/lab/fix/{run_id}/apply → flips the vulnerable flag off and remembers the fix
POST /api/lab/replay/{run_id}   → new run of the same scenario; its findings become the "after" score of the original run
GET  /api/security/scores/{run_id} → {before_score, after_score, delta}
```

### Result schema (shared contract)

```json
{
  "scenario_id": "S07",
  "scenario_name": "price_coupon_manipulation",
  "run_id": "RUN-0012",
  "status": "partial",
  "severity": "HIGH",
  "affected_component": "checkout",
  "attack_path": ["customer", "cart", "checkout", "pricing_logic"],
  "controls": {
    "price_validation": "missed",
    "business_validation": "missed",
    "logging": "detected"
  },
  "before_score": 30,
  "after_score": 50
}
```

`status` is `detected` when every control caught the test, `missed` when none did, otherwise `partial`.

### Which scenarios currently demonstrate a fix

The fix → replay loop changes the outcome only when the scenario has a real vulnerable code path behind a flag.

| Scenario | Vulnerable path in the app | Observed before → after (fresh seeded twin) |
|---|---|---|
| S07 Price / coupon | ✅ `DEBUG_PRICE_MODE` in `orders.py` | `missed` → `detected` (score 30 → 50) |
| S06 Access control | ✅ `DEBUG_ACCESS_MODE` in `orders.py` | `missed` → `detected` (score 30 → 45) |
| S04 SQL injection | ⚠️ flag exists, but the catalog search is always parameterised | `detected` before and after |
| S05 Rate limit | ⚠️ no throttling or lockout implemented yet | `missed` before and after |
| S01 Misconfiguration | ⚠️ FastAPI `/docs` is always exposed; no fix flag | `debug_mode_off` stays `missed` |
| S02 / S03 | scan-based; no app change to fix | `detected` before and after |

See [Current status and known limitations](#current-status-and-known-limitations).

---

## Security scoring

The score is **deterministic and explainable**. Each finding's `control` maps to one dimension; results convert to numbers; numbers are averaged per dimension; dimensions are weighted.

| Result | Value |
|---|---|
| `detected` | 1.0 |
| `partial` | 0.5 |
| `missed` | 0.0 |

| Dimension | Weight | Controls |
|---|---:|---|
| Detection coverage | 30% | `logging`, `audit_trail`, `ci_gate` |
| Application controls | 20% | `rate_limiting`, `price_validation`, `business_validation`, `sql_injection_protection`, `account_lockout` |
| API authorization | 15% | `api_authorization` |
| Supply chain | 15% | `trivy_scan` |
| Secrets | 10% | `gitleaks` |
| Configuration | 10% | `debug_mode_off`, `cors_restriction`, `jwt_secret_strength` |

```text
final_score = round( Σ  weight[dim] × average(control scores in dim) × 100 )
```

- A dimension with **no findings contributes 0**. A single-scenario run therefore covers only a slice of the model. For example, S07 touches only *detection coverage* and *application controls*, so its maximum is 50. This is why live S07 scores are 30 → 50 rather than a value near 100.
- Unknown control keys are ignored with a warning, so new controls can be added safely.
- Weights are asserted to sum to `1.0` at import time.
- `aggregate_score()` combines all completed runs for the dashboard.

| Score | Grade |
|---|---|
| 90–100 | A |
| 75–89 | B |
| 60–74 | C |
| 45–59 | D |
| 0–44 | F |

Python API (`app/security/scoring.py`): `compute_score`, `score_breakdown`, `score_run`, `get_before_after`, `aggregate_score`. Full reference and a worked example: [`docs/scoring.md`](docs/scoring.md).

**Adding a control:** add it to `CONTROL_DIMENSION_MAP` in `scoring.py` and `CONTROL_DESCRIPTIONS` in `control_matrix.py`, make a scenario emit a `Finding` with that key, then run `pytest tests/security`.

---

## Reports

For any completed run NIVARA produces a **JSON** or print-ready **HTML** report containing scenario metadata, attack path, control matrix, detection gaps, before/after scores and grade.

```bash
# API
curl -X POST localhost:8000/api/reports/generate/RUN-0008 -H 'Content-Type: application/json' -d '{"format":"html"}'
curl -OJ    localhost:8000/api/reports/download/1

# CLI (uses the same generator as the API)
python scripts/generate_report.py RUN-0008                       # JSON to stdout
python scripts/generate_report.py RUN-0008 -f html -o report.html
python scripts/generate_report.py RUN-0008 --save                # also store in the DB
```

The UI's report page uses `GET /api/reports/generate/{run_id}`, which returns the HTML inline and stores it.

---

## API reference

Interactive docs: **http://localhost:8000/docs**. All routes are mounted under four prefixes plus `/health`. Routes marked 🔒 require `Authorization: Bearer <token>`.

### `/api/store`: the bookstore

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create a customer account |
| POST | `/auth/login` | Get a Bearer token |
| GET | `/auth/me` 🔒 | Current user profile |
| GET | `/categories` | List categories |
| GET | `/catalog` | Browse books. Query: `page`, `limit` (≤100), `category`, `search`, `sort` (`title_asc`, `price_asc`, `price_desc`, `rating_desc`, `newest`) |
| GET | `/catalog/{book_id}` | Book details |
| GET | `/catalog/{book_id}/reviews` | Reviews for a book |
| POST | `/reviews` 🔒 | Post a review (one per user per book) |
| GET | `/cart` 🔒 | View cart |
| POST | `/cart/add` 🔒 | Add a book |
| PUT | `/cart/{item_id}` 🔒 | Update quantity |
| DELETE | `/cart/{item_id}` 🔒 | Remove an item |
| POST | `/cart/coupon` 🔒 | Validate a coupon and preview the total |
| POST | `/orders/checkout` 🔒 | Convert cart to order (fake payment) |
| GET | `/orders` 🔒 | List my orders |
| GET | `/orders/{order_id}` 🔒 | Order details (owner only) |
| GET / POST / PUT | `/admin/books`, `/admin/books/{id}` 🔒 | Admin book management |
| GET / PUT | `/admin/inventory/{book_id}` 🔒 | Admin inventory |
| GET | `/admin/users` 🔒 | Admin user list |

### `/api/lab`: Security Lab control

| Method | Path | Description |
|---|---|---|
| GET | `/status` | Twin status, current score, scenario count, detection rate |
| GET | `/scenarios` | The seven scenario definitions |
| POST | `/run/{scenario_id}` | Start a run (202), returns `run_id` |
| GET | `/status/{run_id}` | Poll a run |
| GET | `/fix/{run_id}` | Remediation recommendation |
| POST | `/fix/{run_id}/apply` | Apply the fix |
| POST | `/replay/{run_id}` | Replay after a fix |
| POST | `/reset` | Wipe and re-seed the twin |
| POST | `/_config` | **Internal**: toggle the vulnerable flags (used by scenarios) |

### `/api/security`: findings and scores

| Method | Path | Description |
|---|---|---|
| GET | `/findings/{run_id}` | Full scenario result (shared contract) |
| GET | `/attack-path/{run_id}` | Attack-path graph |
| GET | `/controls/{run_id}` | Control matrix for the run |
| GET | `/scores` | All score snapshots |
| GET | `/scores/{run_id}` | Before/after/delta for one run |

### `/api/reports`

| Method | Path | Description |
|---|---|---|
| POST | `/generate/{run_id}` | Create a stored report. Body: `{"format": "json" \| "html"}` |
| GET | `/generate/{run_id}` | Create and return the HTML report inline |
| GET | `/download/{report_id}` | Download a stored report |

### Other

| Method | Path | Description |
|---|---|---|
| GET | `/health` | `{status, db, version, twin}`; returns 503 if the database is unreachable |

---

## Data model and synthetic data

SQLite tables (SQLModel, `backend-python/app/db/models.py`):

| Group | Tables |
|---|---|
| Store | `users`, `authors`, `categories`, `books`, `inventory`, `carts`, `cart_items`, `coupons`, `orders`, `order_items`, `reviews` |
| Lab | `security_events`, `scenario_runs`, `findings`, `score_snapshots`, `reports` |

**Deterministic seeding** (`python app/db/seed.py`, options `--reset`):

| Entity | Count |
|---|---:|
| Admin users | 5 (+1 demo admin) |
| Customers | 200 (+1 demo user) |
| Authors | 250 |
| Books | 500 |
| Categories | 20 |
| Coupons | 25 (5 named + 20 generated) |
| Orders | 1,500 (about 20% with a coupon, spread over 90 days) |
| Order items | about 7,400 |
| Reviews | 1,500 |
| Scenario stubs | 7 (one `pending` run per scenario) |

The same `SEED` and the same pinned Faker version reproduce the same dataset on every machine, and `dataset_fingerprint()` hashes the content so you can verify it. Bcrypt hashes and timestamps are excluded from the fingerprint because they are not reproducible by nature. Seeding is idempotent: it only seeds when the users table is empty unless `--reset` is passed.

---

## Frontend

A Leptos CSR single-page app. It is a pure UI client: all business and security logic stays in the backend. The JWT is kept in `localStorage` (`nivara_token`); the UI decodes it only for display, and the server remains the authority.

| Route | Page |
|---|---|
| `/` | Home |
| `/catalog`, `/book/:id` | Browse and book detail |
| `/cart`, `/checkout`, `/orders` | Authenticated shopping flow |
| `/login`, `/register` | Auth |
| `/admin` | Placeholder |
| `/lab` | Security Lab dashboard (twin status, score, scenario count) |
| `/lab/scenarios` | Scenario library |
| `/lab/run/:id` | Run a scenario with progress polling |
| `/lab/observe/:run_id` | Attack path, control matrix, detection gaps |
| `/lab/fix/:run_id` | Recommended fix and Apply Fix |
| `/lab/replay/:run_id` | Replay and before/after comparison |
| `/lab/report/:run_id` | Report viewer and download |

Reusable components include `score_ring`, `attack_path`, `controls_matrix`, `scenario_card`, `progress_panel`, `status_badge`, `book_card`, `cart_summary` and `require_auth`. The "before" score of a run is cached client-side (`snapshot.rs`) so the comparison survives navigation.

Production build: `trunk build --release` (size-optimised release profile with LTO).

---

## CI/CD and DevSecOps pipeline

### CI (`.github/workflows/ci.yml`)

Triggers on pushes to any branch and on pull requests to `main`. Runs are cancelled per ref when superseded.

```text
rust-checks ──┐
              ├──► security-scan ──► docker-build
python-checks ┘
```

| Job | What it does |
|---|---|
| `rust-checks` | `cargo check` and `cargo clippy -D warnings` for `wasm32-unknown-unknown`, then `trunk build --release` |
| `python-checks` | Python 3.11, `ruff check app/`, `pytest tests/ -v` with a test database and fake secret |
| `security-scan` | **Trivy** filesystem scan (HIGH + CRITICAL, hard gate, SARIF upload to the GitHub Security tab) and **Gitleaks** secret scan over full history |
| `docker-build` | Builds backend and frontend images, **Trivy image scan**: backend CRITICAL is a hard gate, frontend is informational |

A pull request cannot merge until CI passes.

### CD (`.github/workflows/cd.yml`)

Runs on pushes to `main` only, one deployment at a time:

1. `docker compose build --parallel`
2. `docker compose up -d --wait` (waits for health checks)
3. Smoke test: `curl -f http://localhost:8000/health` with retries
4. Seed the synthetic data inside the backend container
5. Dump logs on failure, then `docker compose down -v`

### On-demand security tools (local)

```bash
docker compose --profile security run --rm trivy image nivara-backend:latest
docker compose --profile security run --rm gitleaks
```

### Hardening already in place

- Backend container runs as an unprivileged user (UID 10001)
- `.env` and database files are git-ignored and excluded from the Docker build context
- Action versions for Trivy are pinned to a commit SHA
- `CODEOWNERS` routes reviews per area (see [Team](#team-ownership-and-git-workflow))

---

## Safety guardrails

NIVARA is an educational lab. It is built so that it cannot be pointed at anything real:

- **Target allow-list.** `BaseScenario._assert_safe_target` refuses to run unless `TWIN_URL` contains `twin`, `localhost`, `127.0.0.1` or `testserver`.
- **Synthetic data only.** No real users, credentials or payment data. Payment is a fake flow.
- **Fake secrets only.** S03 uses `ghp_FAKESECRET123ABCDEF000000` and always deletes the fixture in `teardown()`.
- **Harmless probes.** S04 uses a marker string, not a destructive payload; S07 submits an obviously fake total of ₹1.00; S05 only targets the seeded demo account.
- **Always restore safe mode.** Scenarios reset the vulnerable flags in a `finally` block.
- **Vulnerable paths default off** (`DEBUG_*_MODE=false`).

> ⚠️ **Do not expose this stack to the internet.** `POST /api/lab/_config`, `/api/lab/reset` and the other lab routes are intentionally unauthenticated so the demo can drive them, and the twin contains deliberately vulnerable code paths. Run it on localhost or an isolated network only.

---

## Testing

```bash
cd backend-python
pip install -r requirements.txt
pytest                      # whole suite
pytest tests/security -v    # scoring, control matrix, report generator
ruff check app/             # lint (same as CI)
```

The suite covers configuration, DB models, the deterministic seeder, store routes, the lab engine and scenario lifecycle, scoring, the control matrix and report generation (about 178 tests). CI sets `DATABASE_URL=sqlite:///./data/bookstore_test.db`, a throw-away `JWT_SECRET`, and `SEED=42`.

Frontend: `cargo check --target wasm32-unknown-unknown` and `cargo clippy --target wasm32-unknown-unknown -- -D warnings` (run in CI).

---

## Helper scripts

| Script | Purpose |
|---|---|
| `python scripts/reset_twin.py [--yes] [--seed N] [--docker]` | Wipe all tables and re-seed. Prints per-table counts and the dataset fingerprint. |
| `python scripts/generate_report.py RUN_ID [-f json\|html] [-o FILE] [--save]` | Generate a report from the database without the API. |
| `python backend-python/app/db/seed.py [--reset]` | Seed (or re-seed) the database directly. |

---

## Five-minute demo script

Flagship scenario: **S07, Price / Coupon Manipulation**. Reset first so the twin starts clean.

| Time | Step | What to show |
|---|---|---|
| 0:00 | **Reset** | `python scripts/reset_twin.py --yes`; open the bookstore at `localhost:3000` |
| 0:15 | **Create** | Browse and search books, add one to the cart, apply a coupon, check out (log in as `demo@nivara.dev`) |
| 1:15 | **Security Lab** | Open `/lab`, show the seven scenarios, pick **S07** |
| 1:45 | **Attack and observe** | Click Run, wait for completion, show the attack path, the missed controls and the **before score** |
| 2:45 | **Fix** | Open the recommended fix, explain it, click **Apply Fix** |
| 3:30 | **Replay** | Replay the same scenario: the tampered total is now rejected; show the **after score** and delta |
| 4:15 | **Report** | Open and download the HTML report |
| 4:40 | **CI proof** | Show the GitHub Actions run: tests, Trivy, Gitleaks, Docker build, deploy |

CLI fallback if the UI misbehaves: `python scripts/generate_report.py RUN_ID -f html -o report.html`.

> **A note on the numbers.** The original plan and the report/test fixtures use **61 → 92 (+31)** as the S07 headline. The scoring engine computes the score only from the findings of that one run, and an uncovered dimension counts as 0, so on a freshly reset twin a live S07 run produces **30 → 50 (+20)** today. Say whichever figures the screen shows. If you want the 61 → 92 story live, the scoring input needs to include a broader finding set (for example, the findings of several scenarios per run).

---

## Current status and known limitations

This is a hackathon snapshot, and the notes below describe what the code does today.

**Working end to end:** the bookstore API and UI, the seeded twin and reset, the run → observe → fix → replay → report loop for **S06 and S07**, scoring, control matrix, reports (HTML/JSON/CLI), CI and CD workflows, Docker packaging, and the Leptos lab UI.

**Known gaps**
- **S04** — `DEBUG_SQLI_MODE` has no effect yet: the catalog search is always parameterised, so S04 reports `detected` before and after the fix.
- **S05** — there is no rate limiter or account lockout on `/auth/login` yet, so both controls stay `missed`; the "fix" is advice only.
- **S01** — `/docs` is always exposed and `jwt_secret_strength` is a fixed `partial`; "Apply Fix" has no flag to flip.
- **S02 / S03** — outcomes depend on the Trivy/Gitleaks CLIs being on `PATH`; otherwise the scenarios fall back to a simulated scan or direct fixture inspection.
- **Lab status endpoint** — `current_score` falls back to a mock value (72), and `detection_rate` (0.71) and `twin_running` are hard-coded placeholders.
- **Fix state is in-process.** "Apply Fix" flips the settings in the running server only. It is cleared by `/api/lab/reset` or a fresh run of the scenario, and it is lost on restart.
- **Admin UI** (`/admin`) is a placeholder; the admin API exists.
- **Not built:** Falco runtime monitoring, Prometheus/Grafana, PDF reports, LLM-written explanations (all optional or stretch in the architecture doc). `scripts/seed_data.py` and `docs/architecture.md` / `docs/attack-model.md` mentioned in the architecture doc are not present; seeding is `backend-python/app/db/seed.py`.
- **CI Docker build context.** `docker-compose.yml` builds the backend from the repo root, but the `docker-build` CI job uses `./backend-python` as the context, while the Dockerfile copies `backend-python/…` and `scenarios/`. Align the CI context with Compose (`context: .`) if that job fails.
- **Housekeeping.** `frontend-rust/src` contains stray `* edited.rs` / `* unedited.rs` backup files that are not part of the build and can be deleted.
- **Tests.** `tests/test_config.py::test_anchored_path_is_not_percent_encoded` asserts a Windows-style path and fails on Linux/macOS. `tests/test_task4_stubs.py::test_lab_fix_and_apply_flow` needs a backend listening on `localhost:8000`; start one or skip it.

---

## Team, ownership and Git workflow

| Member | Area | Branch |
|---|---|---|
| Member 1 | Rust frontend, bookstore UX, lab UI | `feature/frontend-rust` |
| Member 2 | FastAPI, SQLite, auth, store routes, synthetic data | `feature/backend-db` |
| Member 3 | Attack engine, seven scenarios, event collection | `feature/attack-engine` |
| Member 4 | CI/CD, Trivy/Gitleaks, scoring, control matrix, reports | `feature/devsecops` |

`.github/CODEOWNERS` maps paths to owners (placeholder handles such as `@m1-handle` need to be replaced with real GitHub usernames before review rules take effect). The `shared/` folder is reserved for cross-team contracts and requires sign-off from all four members.

**Rules**
1. Nobody pushes directly to `main`; every branch opens a pull request.
2. CI must pass before merge.
3. Cross-module changes need an owner's review.
4. Shared schemas change only with team review.
5. Never commit secrets, including real-looking fake ones outside the scenario fixtures.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker compose up` hangs on the frontend | The frontend waits for the backend health check. Check `docker compose logs backend`. |
| Frontend loads but API calls fail in `trunk serve` | Make sure the backend is running on port 8000; Trunk proxies `/api/` to it. |
| CORS errors from a different origin | Add it to `CORS_ORIGINS` (comma-separated) and restart the backend. |
| Scenarios say "Refusing to run against non-twin target" | `TWIN_URL` must contain `twin`, `localhost`, `127.0.0.1` or `testserver`. |
| S06/S07 show no improvement after the fix | Run the fix **before** replaying, and replay the same run id. Or reset the twin and start again. |
| Dataset looks different from a teammate's | Check `SEED` and the Faker version (`faker==40.41.0`); compare `dataset_fingerprint`. |
| `passlib` / bcrypt errors | Keep `bcrypt<5` (see `requirements.txt`). |
| `no such table` | Run `python app/db/seed.py` or start the app once; it creates tables on startup. |
| Want a clean slate | `python scripts/reset_twin.py --yes` (local) or `docker compose down -v && docker compose up --build`. |

---

## Further reading

- [`NIVARA_Updated_Architecture.md`](NIVARA_Updated_Architecture.md) — architecture decisions, scenario design, MVP vs stretch scope
- [`docs/scoring.md`](docs/scoring.md) — scoring formula reference and worked example
