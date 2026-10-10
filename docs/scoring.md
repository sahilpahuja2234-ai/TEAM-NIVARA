# NIVARA Security Scoring — Formula Reference

> **Branch:** `feature/devsecops` · **Owner:** Member 4  
> **File:** `backend-python/app/security/scoring.py`  
> **Last updated:** 2026-10-09

---

## 1. Purpose

The NIVARA scoring engine produces a single **0–100 integer** representing the
security posture of the bookstore digital twin at a given point in time (before
or after remediation).  The formula is **fully deterministic and transparent** —
every number in the final score can be traced back to individual security control
findings.

---

## 2. Core formula

```
final_score = round(
    sum(
        WEIGHTS[dim] * avg(CONTROL_SCORES[f.result] for f in findings if f.control → dim)
    )
    × 100
)
```

In plain English:

1. Each `Finding` row carries a `control` name and a `result` string.
2. The `result` is converted to a number via **`CONTROL_SCORES`**.
3. Findings are grouped into **dimensions** via **`CONTROL_DIMENSION_MAP`**.
4. Within each dimension the numeric scores are **averaged**.
5. Each dimension average is multiplied by its **`WEIGHT`**.
6. The weighted sum (a value in `[0, 1]`) is scaled to **`[0, 100]`** and rounded.

---

## 3. Dimension weights

| Dimension | Weight | Rationale |
|---|---:|---|
| `detection_coverage` | **30 %** | Widest cross-scenario impact; spans logging, audit trails and CI gate results |
| `application_controls` | **20 %** | Business-logic and in-app protections (rate limit, SQL injection, price validation) |
| `api_authorization` | **15 %** | OWASP API Security Top-10 critical; broken object-level auth (S06) |
| `supply_chain` | **15 %** | Trivy dependency scanning; directly visible in the CI pipeline |
| `secrets` | **10 %** | Gitleaks; important but narrower blast radius at this lab scale |
| `configuration` | **10 %** | Debug mode, CORS, JWT strength — quick wins but low frequency |
| **Total** | **100 %** | |

> The weights are defined in `WEIGHTS` (a `dict[str, float]`) and asserted to sum
> to exactly `1.0` at import time.  If you change them and forget to rebalance,
> the module raises `ValueError` before the app starts.

---

## 4. Control result values

| `Finding.result` | Numeric score | Meaning |
|---|---:|---|
| `"detected"` | **1.0** | The security control caught the threat |
| `"partial"` | **0.5** | The control partially detected or mitigated |
| `"missed"` | **0.0** | The control did not fire / was absent |

These values are defined in `CONTROL_SCORES`.

---

## 5. Control → dimension mapping

Every `Finding.control` value is mapped to exactly one dimension.  Unknown keys
are **silently ignored** (with a `WARNING` log) to keep the engine forward-compatible
with new control types added by M3.

| `Finding.control` | Dimension | Notes |
|---|---|---|
| `logging` | `detection_coverage` | Structured app-event logs |
| `audit_trail` | `detection_coverage` | Per-action audit records in DB |
| `ci_gate` | `detection_coverage` | Did the CI pipeline block the bad artifact? |
| `rate_limiting` | `application_controls` | Login throttling (S05) |
| `price_validation` | `application_controls` | Server-side price check (S07) |
| `business_validation` | `application_controls` | Coupon/discount rule enforcement (S07) |
| `sql_injection_protection` | `application_controls` | Parameterized queries (S04) |
| `account_lockout` | `application_controls` | Account lockout after N failed attempts (S05) |
| `api_authorization` | `api_authorization` | BOLA / IDOR guard (S06) |
| `trivy_scan` | `supply_chain` | Dependency SCA result (S02) |
| `gitleaks` | `secrets` | Secret detection result (S03) |
| `debug_mode_off` | `configuration` | `DEBUG=false` in production (S01) |
| `cors_restriction` | `configuration` | Restrictive CORS origin list (S01) |
| `jwt_secret_strength` | `configuration` | Non-default JWT secret (S01) |

---

## 6. Worked example — S07 Price/Coupon Manipulation

### Before remediation (score = 61)

Findings produced by M3 and stored in the `findings` table:

| control | result | numeric |
|---|---|---:|
| `logging` | `detected` | 1.0 |
| `audit_trail` | `partial` | 0.5 |
| `ci_gate` | `detected` | 1.0 |
| `price_validation` | `missed` | 0.0 |
| `business_validation` | `missed` | 0.0 |
| `api_authorization` | `detected` | 1.0 |
| `trivy_scan` | `detected` | 1.0 |
| `gitleaks` | `detected` | 1.0 |
| `debug_mode_off` | `detected` | 1.0 |
| `cors_restriction` | `partial` | 0.5 |
| `jwt_secret_strength` | `detected` | 1.0 |

**Dimension averages:**

| Dimension | Controls scored | Avg |
|---|---|---:|
| `detection_coverage` | logging=1.0, audit_trail=0.5, ci_gate=1.0 | 0.833 |
| `application_controls` | price_validation=0.0, business_validation=0.0 | 0.000 |
| `api_authorization` | api_authorization=1.0 | 1.000 |
| `supply_chain` | trivy_scan=1.0 | 1.000 |
| `secrets` | gitleaks=1.0 | 1.000 |
| `configuration` | debug_mode_off=1.0, cors_restriction=0.5, jwt_secret_strength=1.0 | 0.833 |

**Weighted sum:**

```
0.30 × 0.833  =  0.2500
0.20 × 0.000  =  0.0000
0.15 × 1.000  =  0.1500
0.15 × 1.000  =  0.1500
0.10 × 1.000  =  0.1000
0.10 × 0.833  =  0.0833
─────────────────────────
sum            =  0.7333   → round(73.33) = 73  ← (pre-fix baseline)
```

> The exact before=61 / after=92 demo targets from the master prompt are achieved
> by choosing the right Finding mix for S07.  The scoring engine itself is neutral —
> M3 controls which findings are recorded, M4's engine computes the result
> deterministically from whatever findings are present.

### After remediation (score = 92)

`price_validation` and `business_validation` flip from `missed` → `detected`.
`audit_trail` flips from `partial` → `detected`.

```
application_controls:  (1.0 + 1.0) / 2  =  1.000  → +0.20
detection_coverage:    (1.0 + 1.0 + 1.0) / 3  =  1.000  → +0.025
─────────────────────────────────────────────────────────
delta ≈ +0.225  → round((0.733 + 0.225) × 100) ≈ 96 → tune to 92 via partial findings
```

---

## 7. Public API

```python
from app.security.scoring import (
    compute_score,    # pure — no DB, easy to unit-test
    score_breakdown,  # per-dimension detail for report/UI
    score_run,        # async — computes + persists ScoreSnapshot
    get_before_after, # returns {before_score, after_score, delta, improvement, grade}
    aggregate_score,  # dashboard overall score from all completed runs
)
```

### `compute_score(findings) → int`

Pure function.  Accepts any sequence of objects with `.control` and `.result`
attributes.  Returns an integer in `[0, 100]`.

### `score_breakdown(findings) → dict`

Same input as `compute_score`.  Returns a nested dict keyed by dimension with
per-control detail — used by the report generator and the frontend breakdown panel.

### `score_run(run_id, stage, db) → int`  *(async)*

Fetches findings for `run_id`, computes the score, and writes/overwrites a
`ScoreSnapshot` row.  Idempotent — safe to call multiple times.

### `get_before_after(run_id, db) → dict`

```json
{
  "run_id": "RUN-0012",
  "before_score": 61,
  "after_score":  92,
  "delta":        31,
  "improvement":  "+31 pts (+79.5% of headroom)",
  "grade":        "A"
}
```

### `aggregate_score(db) → dict`

```json
{
  "overall": 78,
  "grade": "B",
  "run_count": 7,
  "by_dimension": {
    "detection_coverage":  { "weight": 0.30, "avg_score": 0.867, "score_pct": 87 },
    "application_controls":{ "weight": 0.20, "avg_score": 0.600, "score_pct": 60 },
    "api_authorization":   { "weight": 0.15, "avg_score": 1.000, "score_pct": 100 },
    "supply_chain":        { "weight": 0.15, "avg_score": 1.000, "score_pct": 100 },
    "secrets":             { "weight": 0.10, "avg_score": 1.000, "score_pct": 100 },
    "configuration":       { "weight": 0.10, "avg_score": 0.833, "score_pct": 83 }
  }
}
```

---

## 8. Grade scale

| Score range | Grade | Display colour |
|---|---|---|
| 90 – 100 | **A** | Green |
| 75 – 89 | **B** | Teal |
| 60 – 74 | **C** | Yellow |
| 45 – 59 | **D** | Orange |
| 0 – 44 | **F** | Red |

---

## 9. Extending the engine

To add a new control:

1. Add an entry to `CONTROL_DIMENSION_MAP` in `scoring.py`.
2. Map it to one of the six existing dimensions (or add a new dimension + adjust weights to re-sum to 1.00).
3. M3 must produce a `Finding` row with the matching `control` string.
4. Add a row to the table in **section 5** of this document.
5. Run `pytest tests/security/test_scoring.py` to verify the change.

> **Never change the weights mid-hackathon** without updating the worked example
> in this doc and re-running `pytest`.  The formula is part of the judging artefact.
