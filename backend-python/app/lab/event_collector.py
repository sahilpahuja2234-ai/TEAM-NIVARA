"""
NIVARA Attack Scenario Engine — Event Collector

Thin helper scenarios call while they run to emit structured
SecurityEvent rows, independent of the Finding rows / final
result_json. Use this for "what happened, moment by moment" (requests
sent, responses received, controls checked); use Finding for "here is
a concrete security issue we found".
"""
from __future__ import annotations

import json
import logging

from sqlmodel import Session, select

from app.db.models import SecurityEvent

logger = logging.getLogger("nivara.lab.events")

# SecurityEvent.severity has no CHECK constraint in the schema, but we
# still validate client-side against our own fixed vocabulary.
# INFO is included since scenarios log routine telemetry, not just
# attack-severity findings.
VALID_SEVERITIES = {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}


def log_event(
    db: Session,
    event_type: str,
    severity: str,
    source: str,
    detail: dict,
) -> SecurityEvent:
    """Create, commit, and return a SecurityEvent row.

    `source` should embed the run_id (e.g. f"scenario:{run_id}") so
    get_events() can filter events down to a single run.
    """
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity {severity!r}, expected one of {VALID_SEVERITIES}"
        )

    event = SecurityEvent(
        event_type=event_type,
        severity=severity,
        source=source,
        detail_json=json.dumps(detail),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(json.dumps({
        "event": "security_event_logged",
        "event_type": event_type,
        "severity": severity,
        "source": source,
    }))

    return event


def get_events(run_id: str, db: Session) -> list[SecurityEvent]:
    """Return all SecurityEvent rows whose source references this run_id,
    oldest first."""
    return list(
        db.exec(
            select(SecurityEvent)
            .where(SecurityEvent.source.contains(run_id))
            .order_by(SecurityEvent.id)
        ).all()
    )
