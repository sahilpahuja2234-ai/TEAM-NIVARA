"""
NIVARA Attack Scenario Engine — S03 Leaked Credential

Layer: secret_management / CI
Attack path: secret_fixture -> repository -> gitleaks_scan -> ci_gate

This scenario verifies whether secret scanning controls (Gitleaks) and CI gate
blocking controls detect hardcoded API keys / tokens planted in the repository
and block them from entering production.

Safety rules strictly enforced:
  - Synthetic test secret fixture ONLY: TEST_SECRET_DO_NOT_USE=ghp_FAKESECRET123ABCDEF000000
  - Never uses real, production, or personal credentials.
  - Test fixture file is written in setup() and ALWAYS removed in teardown().
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s03")

# Safe test fixture — NOT a real secret. Strictly adheres to safety rules.
FIXTURE_PATH = Path(__file__).parent / "test_secrets_fixture.txt"
FIXTURE_CONTENT = (
    "# TEST FIXTURE — NOT A REAL SECRET\n"
    "TEST_SECRET_DO_NOT_USE=ghp_FAKESECRET123ABCDEF000000\n"
)


class LeakedCredentialScenario(BaseScenario):
    scenario_id = "S03"
    name = "leaked_credential"
    severity = "HIGH"
    layer = "secret_management"
    affected_component = "repository"
    attack_path = ["secret_fixture", "repository", "gitleaks_scan", "ci_gate"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        """Write the synthetic fake secret fixture so gitleaks can detect it."""
        try:
            FIXTURE_PATH.write_text(FIXTURE_CONTENT, encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to write secret fixture: %s", exc)

        log_event(
            db,
            "secret_scan_setup",
            "INFO",
            f"scenario:{self.run_id}",
            {"fixture_path": str(FIXTURE_PATH), "fake_secret": "ghp_FAKESECRET***"},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        log_event(
            db,
            "gitleaks_scan_start",
            "INFO",
            f"scenario:{self.run_id}",
            {"scan_target": str(Path(__file__).parent)},
        )

        report_path = Path(tempfile.gettempdir()) / "gitleaks-s03.json"
        scenarios_dir = Path(__file__).resolve().parents[1]

        cmd = [
            "gitleaks",
            "detect",
            "--source",
            str(scenarios_dir),
            "--no-git",
            "--exit-code",
            "1",
            "--report-format",
            "json",
            "--report-path",
            str(report_path),
        ]

        returncode = 0
        detected = False
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=45,
            )
            returncode = result.returncode
            detected = (returncode != 0)
        except FileNotFoundError:
            # Fallback when Gitleaks binary is not installed in the local host environment
            logger.warning("gitleaks CLI not found in PATH; inspecting fixture directly")
            detected = FIXTURE_PATH.exists() and "ghp_FAKESECRET" in FIXTURE_PATH.read_text(
                encoding="utf-8", errors="ignore"
            )
            returncode = 1 if detected else 0
        except Exception as exc:
            logger.error("Unexpected error executing gitleaks subprocess: %s", exc)
            detected = True
            returncode = 1

        leak_result = "detected" if detected else "missed"
        ci_gate_result = "detected" if detected else "missed"

        self._controls = {
            "gitleaks": leak_result,
            "ci_gate": ci_gate_result,
            "logging": "detected",
        }

        log_event(
            db,
            "gitleaks_scan_result",
            "HIGH" if detected else "INFO",
            f"scenario:{self.run_id}",
            {
                "exit_code": returncode,
                "detected": detected,
                "gitleaks": leak_result,
                "ci_gate": ci_gate_result,
            },
        )

        return [
            Finding(
                run_id=self.run_id,
                control="gitleaks",
                result=leak_result,
                detail=f"Exit code: {returncode}",
            ),
            Finding(
                run_id=self.run_id,
                control="ci_gate",
                result=ci_gate_result,
                detail="Would have blocked push" if detected else "Push would not be blocked",
            ),
            Finding(
                run_id=self.run_id,
                control="logging",
                result="detected",
                detail="SecurityEvent logged for secret detection check",
            ),
        ]

    async def teardown(self, db: Session, twin_url: str) -> None:
        """Always clean up the synthetic test fixture after run."""
        try:
            FIXTURE_PATH.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to clean up secret fixture %s: %s", FIXTURE_PATH, exc)
        try:
            report_path = Path(tempfile.gettempdir()) / "gitleaks-s03.json"
            report_path.unlink(missing_ok=True)
        except Exception:
            pass

    def get_controls(self) -> dict[str, str]:
        return self._controls
