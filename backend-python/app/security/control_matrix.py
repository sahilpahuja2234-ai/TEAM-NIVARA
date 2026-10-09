"""Security control matrix for the NIVARA security lab.

Single source of truth stays in ``scoring.py`` (WEIGHTS, CONTROL_SCORES,
CONTROL_DIMENSION_MAP) so the scoring formula and its tests are untouched.
This module adds the *human-readable* layer on top of it: one record per
control (key, dimension, weight, description) plus lookup helpers that the
report generator and M2's ``/api/security/controls`` route can call.

Public API
----------
CONTROL_MATRIX                      dict[str, Control]
DIMENSIONS                          tuple of dimension names, in weight order
dimension_of(control_key)           -> str | None
controls_in_dimension(dimension)    -> list[Control]
get_control_matrix()                -> list[dict]   (JSON-serialisable)
validate_matrix()                   -> None         (raises ValueError on drift)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.security.scoring import CONTROL_DIMENSION_MAP, CONTROL_SCORES, WEIGHTS

# One-line explanation per control key. Add a line here whenever a new key is
# added to CONTROL_DIMENSION_MAP in scoring.py (validate_matrix() checks this).
CONTROL_DESCRIPTIONS: dict[str, str] = {
    # detection_coverage
    "logging": "Security-relevant events are logged with enough context to investigate.",
    "audit_trail": "Sensitive actions (orders, admin changes) leave a tamper-evident audit record.",
    "ci_gate": "CI blocks the merge when tests or security scans fail.",
    # application_controls
    "rate_limiting": "Repeated requests from one client are throttled.",
    "price_validation": "Prices and totals are recomputed server-side, never trusted from the client.",
    "business_validation": "Business rules (coupon limits, stock, quantities) are enforced on the server.",
    "sql_injection_protection": "Database queries are parameterised; user input never reaches raw SQL.",
    "account_lockout": "Accounts are locked or slowed after repeated failed logins.",
    # api_authorization
    "api_authorization": "Every API route checks that the caller may access the requested object or action.",
    # supply_chain
    "trivy_scan": "Dependencies and container images are scanned for known vulnerabilities.",
    # secrets
    "gitleaks": "The repository is scanned for committed secrets.",
    # configuration
    "debug_mode_off": "Debug behaviour is disabled in the running application.",
    "cors_restriction": "CORS allows only the expected frontend origin(s).",
    "jwt_secret_strength": "The JWT signing secret is long, random and not a default value.",
}


@dataclass(frozen=True)
class Control:
    key: str
    dimension: str
    weight: float  # weight of the whole dimension, not of this control alone
    description: str


def _build() -> dict[str, Control]:
    return {
        key: Control(
            key=key,
            dimension=dim,
            weight=WEIGHTS.get(dim, 0.0),
            description=CONTROL_DESCRIPTIONS.get(key, "(no description yet)"),
        )
        for key, dim in CONTROL_DIMENSION_MAP.items()
    }


CONTROL_MATRIX: dict[str, Control] = _build()
DIMENSIONS: tuple[str, ...] = tuple(WEIGHTS)


def dimension_of(control_key: str) -> str | None:
    """Dimension a control belongs to, or None for unknown keys."""
    return CONTROL_DIMENSION_MAP.get(control_key)


def controls_in_dimension(dimension: str) -> list[Control]:
    """All controls scored inside one dimension (stable, insertion order)."""
    return [c for c in CONTROL_MATRIX.values() if c.dimension == dimension]


def get_control_matrix() -> list[dict]:
    """JSON-serialisable rows, grouped by dimension in weight order."""
    rows: list[dict] = []
    for dim in DIMENSIONS:
        for control in controls_in_dimension(dim):
            row = asdict(control)
            row["max_score"] = max(CONTROL_SCORES.values())
            rows.append(row)
    return rows


def validate_matrix() -> None:
    """Raise ValueError if the matrix and scoring constants have drifted apart."""
    problems: list[str] = []

    unknown_dims = {c.dimension for c in CONTROL_MATRIX.values()} - set(WEIGHTS)
    if unknown_dims:
        problems.append(f"controls point at dimensions with no weight: {sorted(unknown_dims)}")

    empty_dims = [d for d in WEIGHTS if not controls_in_dimension(d)]
    if empty_dims:
        problems.append(f"dimensions with no controls (they would always score 0): {empty_dims}")

    undocumented = [k for k in CONTROL_DIMENSION_MAP if k not in CONTROL_DESCRIPTIONS]
    if undocumented:
        problems.append(f"controls missing a description: {undocumented}")

    stale = [k for k in CONTROL_DESCRIPTIONS if k not in CONTROL_DIMENSION_MAP]
    if stale:
        problems.append(f"descriptions for controls that no longer exist: {stale}")

    if problems:
        raise ValueError("Control matrix is out of sync with scoring.py: " + "; ".join(problems))
