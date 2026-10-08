# NIVARA — Updated Architecture & Technology Stack
## CIPHER05: DevSecOps Digital Twin for Cyber Attack Simulation

### Updated according to team decisions

- Reduce the number of APIs and avoid microservices.
- Use SQLite instead of PostgreSQL.
- Use Rust for the frontend.
- Build a complete synthetic e-commerce bookstore as the sample application and its digital twin.
- Generate deterministic synthetic data for users, books, orders, reviews, coupons, inventory and other business entities.
- Use additional controlled scenarios: SQL injection, rate-limit failure, insecure API/access control, and price/coupon manipulation.
- Preserve the original NIVARA flow: **Create -> Attack -> Observe -> Fix -> Replay -> Before/After proof**.

---

# 1. Final NIVARA concept

> **NIVARA is an isolated DevSecOps security lab built around a realistic synthetic e-commerce bookstore. It creates a reproducible digital twin of the bookstore and its delivery pipeline, safely runs predefined security scenarios, visualizes the attack path and detection gaps, applies fixes, replays the same scenario, and proves improvement with before/after security scoring.**

The original project concept describes NIVARA as a one-stop DevSecOps platform with five major stages: create the digital twin, attack, observe, fix and replay. This updated architecture keeps that core but removes the mobile twin and focuses the demo on one complete bookstore ecosystem. [Source: provided project concept]

---

# 2. Our opinion on the six requested changes

| Decision | Recommendation | Reason |
|---|---|---|
| Reduce APIs | **Strong yes** | One FastAPI backend with a small set of route groups is easier to develop, test and explain than microservices. |
| SQLite | **Strong yes for hackathon** | Synthetic data and demo traffic do not need PostgreSQL. SQLite makes reset, backup and reproducibility much easier. |
| Rust frontend | **Yes, but keep it simple** | Leptos CSR + Trunk can compile Rust to WebAssembly for the browser. Keep the frontend as a pure UI client and keep all business/security logic in Python. |
| Full bookstore + synthetic data | **Strong yes** | Gives the judges a familiar system and lets every attack scenario have a visible business impact. |
| Extra scenarios | **Strong yes** | Adds coverage across infrastructure, dependency, secrets, API, application and business-logic layers. |
| Architecture from pasted plan | **Yes** | Keep Create -> Attack -> Observe -> Fix -> Replay as the product's main narrative. Remove unnecessary mobile complexity. |

### Important Rust opinion

Rust is the one decision that adds risk. Leptos officially supports client-side rendering where Rust code is compiled to WebAssembly, with Trunk handling the build and development loop. This is technically suitable for a browser frontend and works well with an existing backend/API. However, it introduces a learning curve for a team that is stronger in Python. Therefore, **Rust should be limited to presentation/state-management code; Python remains the core backend/orchestration language.**

---

# 3. Final product structure

NIVARA will contain one realistic synthetic e-commerce application named **NIVARA Bookstore** plus the NIVARA security-lab controls.

```text
NIVARA
│
├── Bookstore
│   ├── Home
│   ├── Catalog
│   ├── Search / Filters
│   ├── Book Details
│   ├── Login / Register
│   ├── Cart
│   ├── Checkout (fake payment only)
│   ├── Orders
│   ├── Reviews
│   ├── Coupons
│   └── Admin / Inventory
│
└── Security Lab
    ├── Digital Twin status
    ├── Scenario Library
    ├── Run Simulation
    ├── Attack Path
    ├── Security Control Matrix
    ├── Detection Gaps
    ├── Security Score
    ├── Fix
    ├── Replay
    └── Security Report
```

The main e-commerce website is not a disconnected mock UI. It is the actual sample application whose behavior is copied into the isolated twin.

---

# 4. Core product flow

```text
             ① CREATE
                 │
                 ▼
      Reproducible Bookstore Twin
                 │
                 ▼
             ② ATTACK
                 │
                 ▼
        Safe Scripted Scenario
                 │
                 ▼
             ③ OBSERVE
                 │
                 ▼
      Logs + Attack Path + Controls
                 │
                 ▼
             ④ FIX
                 │
                 ▼
      Remediation / Configuration Fix
                 │
                 ▼
             ⑤ REPLAY
                 │
                 ▼
       Before vs After Evidence
```

This preserves the original architecture concept and maps directly to the locked CIPHER05 requirements.

---

# 5. High-level architecture

```text
                         USER BROWSER
                              │
                              ▼
              ┌──────────────────────────────┐
              │  RUST / LEPTOS FRONTEND     │
              │                              │
              │  Store UI + NIVARA Lab UI   │
              └──────────────┬───────────────┘
                             │
                       ONE API ORIGIN
                             │
                             ▼
              ┌──────────────────────────────┐
              │       FASTAPI GATEWAY        │
              │                              │
              │ Store | Lab | Security      │
              │ Reports | Health            │
              └───────┬────────────┬─────────┘
                      │            │
                      │            ▼
                      │    ┌─────────────────┐
                      │    │ Python Scenario │
                      │    │ Runner / Engine │
                      │    └────────┬────────┘
                      │             │
                      ▼             ▼
              ┌────────────┐  ┌──────────────────┐
              │  SQLite    │  │ Isolated Docker  │
              │  Database  │  │ Digital Twin     │
              └────────────┘  │                  │
                              │ Rust Web Frontend │
                              │ FastAPI Backend   │
                              │ SQLite Twin DB    │
                              └────────┬─────────┘
                                       │
                        ┌──────────────┼──────────────┐
                        ▼              ▼              ▼
                     Trivy          Gitleaks      App Logs
                        │              │              │
                        └──────────────┴──────┬───────┘
                                             ▼
                                  Detection / Findings
                                             │
                                             ▼
                                    Score + Report
```

### Key architectural choice

The project deliberately avoids a microservice architecture. There is **one application backend**, one SQLite datastore for the active environment, and a Python scenario runner. The attack engine is a Python module/job rather than another public API.

---

# 6. API strategy — reduce APIs

## Previous direction

The earlier design allowed separate conceptual services for the dashboard, attacks, monitoring, reports and application.

## Updated direction

Use **one FastAPI application** and group routes logically.

```text
/api/store/*
    catalog, search, auth, cart, checkout, orders, reviews, coupons, admin

/api/lab/*
    scenarios, run, status, reset, replay

/api/security/*
    findings, attack-path, controls, scores

/api/reports/*
    generate, download

/health
```

The attack engine is **not exposed as a separate HTTP API**. The lab service invokes Python scenario modules/jobs directly.

### Why this is better for the team

- One server to run.
- One authentication boundary.
- Easier Docker setup.
- Easier testing.
- Fewer integration failures between team branches.
- Easier for judges to understand.

This still gives the UI clear separation between e-commerce functionality and security-lab functionality.

---

# 7. Database — SQLite

## Recommendation: keep SQLite

SQLite is the right choice for the hackathon version because the data is synthetic, the system is local/isolated, and the important requirement is reproducibility rather than high-concurrency production scaling.

Use:

```text
SQLite
  │
  ├── users
  ├── roles
  ├── books
  ├── authors
  ├── categories
  ├── inventory
  ├── carts
  ├── cart_items
  ├── orders
  ├── order_items
  ├── reviews
  ├── coupons
  ├── security_events
  ├── scenario_runs
  ├── findings
  ├── score_snapshots
  └── reports
```

### SQLite implementation rules

- Enable WAL mode for better concurrent read behavior.
- Use SQLAlchemy/SQLModel for clean schema management.
- Use deterministic seed scripts.
- Keep the database file in a Docker volume.
- Reset means deleting/recreating the twin DB and running the seed script.
- Never place real credentials or personal data in the database.

### Suggested files

```text
backend/
├── db/
│   ├── models.py
│   ├── session.py
│   └── seed.py
└── data/
    └── bookstore.db
```

---

# 8. Full synthetic e-commerce website

The bookstore should look and behave like a believable shopping site.

## Customer side

```text
Home
  ↓
Book Catalog
  ↓
Search / Filter
  ↓
Book Details
  ↓
Add to Cart
  ↓
Coupon
  ↓
Checkout
  ↓
Fake Payment
  ↓
Order Confirmation
  ↓
Order History
```

## Supporting features

- Registration/login with synthetic users.
- Roles: customer and admin.
- Book categories, authors and inventory.
- Book reviews and ratings.
- Coupon codes.
- Order tracking.
- Admin inventory and book management.
- Fake payment flow only; no real payment gateway.
- Audit events for important security actions.

---

# 9. Synthetic data strategy

The project will generate **deterministic synthetic data**, so every team member can recreate the same environment.

## Suggested initial dataset

| Entity | Approx. demo quantity |
|---|---:|
| Users | 200 |
| Admin users | 5 |
| Books | 500 |
| Authors | 250 |
| Categories | 20 |
| Inventory records | 500 |
| Orders | 1,500 |
| Order items | 3,000+ |
| Reviews | 1,500 |
| Coupons | 25 |
| Security events | Generated during simulations |

Use a fixed random seed so every reset produces the same dataset.

### Data generator

```text
scripts/seed_data.py
        │
        ├── Faker
        ├── deterministic random seed
        └── SQLite insertions
```

This is much better for the demo than using internet data or real user information.

---

# 10. Digital Twin model

The digital twin is a **reproducible Docker deployment of the bookstore codebase**.

```text
Source Repository
       │
       ▼
Build Images
       │
       ▼
┌─────────────────────────────┐
│ NIVARA Digital Twin         │
│                             │
│ Rust Frontend               │
│ FastAPI Backend             │
│ SQLite Twin Database        │
│ Audit/Event Logging         │
└─────────────────────────────┘
```

The twin is isolated from production/external systems and uses only synthetic data.

A reset restores:

```text
Code/config fixture
       ↓
Fresh SQLite database
       ↓
Seed synthetic data
       ↓
Clean Docker state
       ↓
Ready for replay
```

---

# 11. Attack Scenario Library

The expanded NIVARA scenario library should contain **7 controlled scenarios**.

## S1 — Misconfiguration

**Layer:** deployment/configuration

Example e-commerce impact:

- unsafe configuration enabled in the twin
- debug behavior or an overly permissive setting
- security control fails to stop the test condition

Goal: demonstrate a configuration-level detection gap.

---

## S2 — Weak Dependency

**Layer:** supply chain

Example:

```text
Bookstore dependency
        ↓
Known test vulnerability
        ↓
Trivy finding
        ↓
CI security gate
```

The scenario should use a controlled dependency fixture rather than a random live vulnerability.

---

## S3 — Leaked Credential

**Layer:** secret management / CI

Use a **fake test secret** only.

```text
Test secret fixture
       ↓
Repository / build context
       ↓
Gitleaks detection
       ↓
CI gate
```

No real credential is ever used.

---

## S4 — SQL Injection

**Layer:** application / data access

Use a deliberately vulnerable **test endpoint or test mode** in the twin and a predefined harmless test marker.

Demonstrate:

```text
Input
  ↓
Book Search Endpoint
  ↓
Unsafe Query Handling
  ↓
Detection / Finding
  ↓
Fix: parameterized query
  ↓
Replay
```

The scenario is restricted to the local synthetic bookstore.

---

## S5 — Rate-Limit Failure

**Layer:** authentication / API abuse

Example:

```text
Test account
     ↓
Repeated login attempts
     ↓
No throttling / weak throttling
     ↓
Monitoring observes abnormal request volume
```

After remediation:

```text
Repeated attempts
     ↓
Rate limiter
     ↓
Blocked / delayed
```

---

## S6 — Insecure API / Broken Access Control

**Layer:** API authorization

Bookstore example:

```text
Customer A
    ↓
Order API
    ↓
Another test customer's order
```

Expected fixed behavior:

```text
Customer A
    ↓
Order API
    ↓
Authorization check
    ↓
403 / access denied
```

This scenario should use only pre-created test accounts and fake orders.

---

## S7 — Price / Coupon Manipulation

**Layer:** business logic

Bookstore example:

```text
Book price = ₹799
Coupon rules = 20%

Client attempts inconsistent checkout values
          ↓
Server-side price validation
          ↓
Detection / rejection
```

The fix is to calculate authoritative prices/coupon eligibility on the server instead of trusting client-supplied totals.

### Why this scenario is important

It demonstrates that NIVARA can find not only infrastructure vulnerabilities, but also **business-logic security failures**.

---

# 12. Scenario coverage matrix

| Scenario | Infrastructure | Supply Chain | Secrets | API | App | Business Logic |
|---|---:|---:|---:|---:|---:|---:|
| Misconfiguration | ✅ | | | ✅ | | |
| Weak Dependency | | ✅ | | | | |
| Leaked Credential | | | ✅ | | | |
| SQL Injection | | | | | ✅ | |
| Rate Limit Failure | | | | ✅ | ✅ | |
| Insecure API / Access Control | | | | ✅ | ✅ | |
| Price / Coupon Manipulation | | | | ✅ | | ✅ |

This gives NIVARA broad coverage without adding unnecessary technologies.

---

# 13. Attack flow

```text
                     RUN SCENARIO
                           │
                           ▼
                 Python Scenario Engine
                           │
                           ▼
                  Safe Local Simulation
                           │
                           ▼
                    Bookstore Twin
                           │
                 ┌─────────┼─────────┐
                 ▼         ▼         ▼
               API      Database    Logs
                 │         │         │
                 └─────────┼─────────┘
                           ▼
                  Detection Collectors
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
            Trivy       Gitleaks    App Events
                           │
                           ▼
                    Finding Analyzer
                           │
                           ▼
                   Attack Path Graph
                           │
                           ▼
                   Security Score
```

---

# 14. Observe screen

For every scenario, NIVARA should present:

```text
SCENARIO: Price / Coupon Manipulation

Status:              DETECTED
Severity:            HIGH
Affected Component:  Checkout API

Attack Path
Customer
   ↓
Cart
   ↓
Checkout API
   ↓
Price/Coupon Logic

Detected by
✓ API validation
✓ Audit event

Missed by
✗ Client-side validation
```

The important output is not just "vulnerability found". It is:

**where the test entered, where it propagated, where it was stopped, and which control failed.**

---

# 15. Security Control Matrix

```text
┌────────────────────────────┬──────────────┐
│ Security Control           │ Result       │
├────────────────────────────┼──────────────┤
│ Dependency Scan            │ ✅ Detected  │
│ Secret Scan                │ ✅ Detected  │
│ API Authorization          │ ❌ Missed    │
│ Runtime/App Monitoring     │ ⚠ Partial    │
│ Business Validation        │ ❌ Missed    │
│ CI/CD Gate                 │ ✅/❌        │
└────────────────────────────┴──────────────┘
```

This becomes one of NIVARA's signature screens.

---

# 16. Security scoring

Use a transparent weighted model rather than an opaque AI score.

Suggested weights:

```text
Detection Coverage       30%
Application Controls     20%
API/Authorization        15%
Supply Chain             15%
Secrets                  10%
Configuration            10%
```

Example:

```text
BEFORE
58 / 100

AFTER
92 / 100

Improvement
+34 points
```

The exact weights can be changed, but the scoring formula must be documented and deterministic.

---

# 17. Fix -> Replay

This remains the most important demo sequence.

```text
Attack
  ↓
Detection Gap
  ↓
NIVARA Recommendation
  ↓
Apply Fix
  ↓
Reset / Prepare Clean State
  ↓
Replay SAME Scenario
  ↓
Compare Results
  ↓
Score Improvement
```

Example:

```text
                         BEFORE       AFTER
API Authorization        ❌           ✅
Price Validation         ❌           ✅
Rate Limiting            ⚠           ✅
Security Score           58           92
Detection Rate           71%          100%
```

---

# 18. AI usage

AI remains an **assistant**, not the product.

Use AI for:

- explaining findings in plain language
- summarizing attack paths
- prioritizing findings
- suggesting remediation steps
- writing the final security report

Do not make the core attack engine dependent on an LLM. The scenarios, scoring and pass/fail logic should remain deterministic.

---

# 19. Updated technology stack

| Layer | Technology | Role |
|---|---|---|
| Frontend | **Rust + Leptos CSR** | Bookstore UI + NIVARA lab UI |
| Frontend build | **Trunk** | Compile Rust/WASM and serve development builds |
| Backend | **Python + FastAPI** | Single backend/API |
| Database | **SQLite** | Synthetic bookstore + lab state |
| ORM | **SQLAlchemy/SQLModel** | Schema and database access |
| Containerization | **Docker + Compose** | Isolated digital twin |
| CI/CD | **GitHub Actions** | Test, scan, build, deploy |
| SCA/Image scanning | **Trivy** | Dependency/container/config scanning |
| Secret scanning | **Gitleaks** | Detect test-secret exposure in code |
| Runtime/app telemetry | **Python logging + structured security events** | MVP monitoring |
| Runtime security | **Falco** | Optional/next-stage runtime detection |
| Metrics | **Prometheus** | Optional stretch goal |
| Dashboard charts | **Rust UI** | Avoid separate Grafana dependency in MVP |
| Synthetic data | **Faker + deterministic seed** | Fake users/books/orders/etc. |
| Reports | **Python** | JSON/HTML/PDF report generation |
| AI analyst | **LLM API** | Explanation/recommendations only |

### Technologies intentionally removed from the core MVP

- PostgreSQL
- Kubernetes
- Jenkins
- separate microservices
- mandatory Grafana
- mandatory Prometheus
- separate attack HTTP API

These can become stretch integrations after the core loop works.

---

# 20. Why Rust frontend is acceptable

Leptos supports client-side rendering where the Rust application is compiled to WebAssembly and run in the browser; the official guide documents Trunk as a straightforward build/development path for this mode. This matches the requirement to keep the frontend in Rust while allowing the Python backend to remain independent. [See official Leptos documentation]

### Recommended frontend boundary

```text
Rust / Leptos
      │
      │ JSON over HTTP
      ▼
FastAPI
      │
      ▼
Python services/modules
```

Rust should **not** contain:

- attack logic
- security scoring rules
- database logic
- Docker control
- secret handling

That keeps the difficult security logic in Python where the team is more comfortable.

---

# 21. CI/CD pipeline for NIVARA

```text
Developer Push / Pull Request
              │
              ▼
       GitHub Actions
              │
      ┌───────┴────────┐
      ▼                ▼
 Rust Checks       Python Checks
 cargo check       pytest
 cargo test        lint/type checks
 wasm build        dependency install
      │                │
      └───────┬────────┘
              ▼
       Security Gates
        ├── Trivy
        ├── Gitleaks
        └── Docker scan
              │
             PASS
              │
              ▼
      Build Docker Images
              │
              ▼
      Deploy Isolated Twin
              │
              ▼
         Health Check
              │
              ▼
       Twin Ready for Demo
```

For the hackathon, the pipeline does not need a public cloud deployment. A local/isolated demo VM or machine is sufficient.

---

# 22. Docker Compose topology

```text
nivara-network
│
├── frontend
│   └── Rust/Leptos static build
│
├── backend
│   ├── FastAPI
│   ├── SQLite
│   ├── scoring
│   ├── lab controller
│   └── report generator
│
├── scenario-runner
│   └── Python safe scenarios
│
└── security-tools (on demand)
    ├── Trivy
    └── Gitleaks
```

Falco can be added as a runtime-security layer after the core architecture is stable.

---

# 23. Repository structure

```text
NIVARA/
│
├── frontend-rust/
│   ├── src/
│   ├── assets/
│   ├── Cargo.toml
│   └── Trunk.toml
│
├── backend-python/
│   ├── app/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── models/
│   │   ├── security/
│   │   └── lab/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── scenarios/
│   ├── S01_misconfiguration/
│   ├── S02_weak_dependency/
│   ├── S03_leaked_credential/
│   ├── S04_sql_injection/
│   ├── S05_rate_limit/
│   ├── S06_insecure_api/
│   └── S07_price_coupon/
│
├── scripts/
│   ├── seed_data.py
│   ├── reset_twin.py
│   └── generate_report.py
│
├── docker-compose.yml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── cd.yml
│
├── docs/
│   ├── architecture.md
│   ├── attack-model.md
│   └── scoring.md
│
└── README.md
```

---

# 24. Four-member branch allocation

## Member 1 — Rust Frontend + Bookstore UX

Branch:

`feature/frontend-rust`

Owns:

- Leptos application
- bookstore pages
- NIVARA lab dashboard
- scenario cards
- attack-path visualisation
- score screens
- before/after UI

Does not own backend logic.

---

## Member 2 — FastAPI + SQLite + Synthetic Data

Branch:

`feature/backend-db`

Owns:

- FastAPI
- route groups
- database models
- authentication
- catalog
- cart/checkout/orders
- reviews/coupons
- seed data
- admin operations

---

## Member 3 — Attack Engine + Monitoring

Branch:

`feature/attack-engine`

Owns:

- seven scenario modules
- scenario execution lifecycle
- event collection
- attack-path data
- detection gap representation
- reset/replay support

---

## Member 4 — CI/CD + Security + Scoring/Reports

Branch:

`feature/devsecops`

Owns:

- GitHub Actions
- Trivy
- Gitleaks
- Docker scanning
- security control matrix
- scoring engine
- report generation

---

# 25. Shared contract between members

To prevent branch integration problems, everyone must agree on one result schema.

```json
{
  "scenario_id": "S07",
  "scenario_name": "price_coupon_manipulation",
  "run_id": "RUN-0012",
  "status": "detected",
  "severity": "HIGH",
  "affected_component": "checkout",
  "attack_path": [
    "customer",
    "cart",
    "checkout",
    "pricing_logic"
  ],
  "controls": {
    "api_validation": "detected",
    "business_validation": "missed",
    "logging": "detected"
  },
  "before_score": 61,
  "after_score": 92
}
```

Member 3 produces scenario results. Member 4 scores/stores them. Member 1 displays them. Member 2 exposes the necessary backend routes.

---

# 26. Git workflow

```text
feature/frontend-rust ────────┐
feature/backend-db ───────────┤
feature/attack-engine ────────┼──► Pull Request ─► main
feature/devsecops ────────────┘
```

Rules:

1. Nobody pushes directly to `main`.
2. Every branch opens a Pull Request.
3. CI must pass before merge.
4. One owner reviews cross-module changes.
5. Shared schemas live in a stable folder and require team review before modification.
6. Never commit secrets, even fake-looking credentials that could be confused with real ones.

---

# 27. MVP vs stretch scope

## MUST HAVE

1. Full synthetic bookstore website.
2. Rust/Leptos frontend.
3. FastAPI backend.
4. SQLite database.
5. Dockerized digital twin.
6. GitHub Actions CI/CD.
7. Trivy + Gitleaks scanning.
8. Seven safe scripted scenarios.
9. Attack-path result.
10. Detection-gap matrix.
11. Security score.
12. Fix -> replay.
13. Before/after report.
14. Reset functionality.

## SHOULD HAVE

15. Falco runtime monitoring.
16. AI Security Analyst.
17. Historical run comparison.
18. Rich attack-path animation.
19. HTML/PDF report.

## STRETCH

20. Prometheus.
21. Grafana.
22. Kubernetes/kind.
23. Automated AI-generated code patches.
24. Multi-project support.
25. Advanced anomaly detection.

---

# 28. Main website demo flow

The judge should be able to open the bookstore and see a believable system before seeing any security attack.

```text
NIVARA BOOKSTORE
       │
       ▼
Browse Books
       │
       ▼
Search / Filter
       │
       ▼
Book Details
       │
       ▼
Add to Cart
       │
       ▼
Apply Coupon
       │
       ▼
Checkout
       │
       ▼
Fake Payment
       │
       ▼
Order Created
```

Then switch to:

```text
SECURITY LAB
       │
       ▼
Choose Scenario
       │
       ▼
Run
       │
       ▼
Observe
       │
       ▼
Fix
       │
       ▼
Replay
       │
       ▼
Score Improvement
```

This makes the security scenarios feel connected to a real product.

---

# 29. Recommended five-minute hackathon demo

### 0:00 — Show the bookstore

Open the synthetic bookstore, search for a book and add it to cart.

### 0:40 — Open NIVARA Security Lab

Show:

- twin status
- current score
- scenario count
- detection rate

### 1:10 — Run Price/Coupon Manipulation

Show the simulated business-logic failure and attack path.

### 2:00 — Show detection gap

Demonstrate which control missed the condition.

### 2:20 — Apply remediation

Use the controlled fix.

### 3:00 — Replay

Run the same scenario again.

### 3:40 — Show before/after

```text
61 / 100  →  92 / 100
```

### 4:00 — Run one technical scenario

Use SQL injection or insecure API as the second visual proof.

### 4:30 — Show CI/CD

Show GitHub Actions:

```text
Tests ✅
Trivy ✅
Gitleaks ✅
Docker ✅
Deploy ✅
```

### 4:50 — Final statement

> **NIVARA does not simply tell developers that a system is vulnerable. It gives them an isolated copy in which they can safely simulate the problem, see the attack path, identify the control gap, fix it, replay the same scenario and prove that security improved.**

---

# 30. Final architecture decision

## LOCK THIS VERSION

```text
                         NIVARA
                           │
            ┌──────────────┴──────────────┐
            │                             │
            ▼                             ▼
     BOOKSTORE UI                  SECURITY LAB UI
     Rust / Leptos                  Rust / Leptos
            │                             │
            └──────────────┬──────────────┘
                           ▼
                    ONE FASTAPI APP
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          Store          Lab          Security
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                         SQLite
                           │
                ┌──────────┴───────────┐
                ▼                      ▼
         Scenario Runner        Security Scans
             Python             Trivy/Gitleaks
                │                      │
                └──────────┬───────────┘
                           ▼
                   Findings / Events
                           │
                           ▼
                       Scoring
                           │
                     ┌─────┴─────┐
                     ▼           ▼
                    FIX        REPLAY
                     │           │
                     └─────┬─────┘
                           ▼
                    BEFORE / AFTER
```

### Final opinion

This architecture is **better for your team than the earlier PostgreSQL + multi-service + mobile direction** because it is narrower, more reproducible and easier to demonstrate. The one high-risk choice is Rust. Because the team explicitly wants Rust, use **Leptos CSR + Trunk** and do not let Rust spread into backend, database, attack execution or security logic.

The most important engineering principle is:

> **One codebase, one backend, one database technology, one frontend technology, one isolated twin, deterministic scenarios, and one clear Create -> Attack -> Observe -> Fix -> Replay loop.**

---

# References / implementation basis

- Provided NIVARA/CIPHER05 concept and feature plan supplied by the team.
- Leptos official guide: client-side rendering with Trunk and WebAssembly.
- OWASP Juice Shop official repository/documentation for the deliberately insecure e-commerce model and Docker deployment approach.
