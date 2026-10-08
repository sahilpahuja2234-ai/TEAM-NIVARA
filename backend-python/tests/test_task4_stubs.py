"""Comprehensive tests for Task 4 route stubs:
- /api/lab/*
- /api/security/*
- /api/reports/*
- /health
"""

import pytest


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data == {
        "status": "ok",
        "db": "connected",
        "version": "1.0.0",
        "twin": "running",
    }


def test_lab_status(client):
    r = client.get("/api/lab/status")
    assert r.status_code == 200
    data = r.json()
    assert data["twin_running"] is True
    assert data["db_seeded"] is True
    assert "last_reset" in data
    assert data["current_score"] == 72
    assert data["scenario_count"] == 7
    assert data["detection_rate"] == 0.71


def test_lab_scenarios(client):
    r = client.get("/api/lab/scenarios")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 7
    s01 = next(s for s in data if s["id"] == "S01")
    assert s01["name"] == "misconfiguration"
    assert s01["layer"] == "deployment/configuration"
    assert s01["severity"] == "MEDIUM"
    assert "description" in s01


def test_lab_run_and_poll_flow(client):
    # 1. Trigger scenario run
    run_res = client.post("/api/lab/run/S01")
    assert run_res.status_code == 202
    run_id = run_res.json()["run_id"]
    assert run_id.startswith("RUN-")

    # 2. Poll status for the run
    poll_res = client.get(f"/api/lab/status/{run_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["run_id"] == run_id
    assert poll_data["scenario_id"] == "S01"
    assert "status" in poll_data
    assert isinstance(poll_data["progress"], int)


def test_lab_reset(client):
    r = client.post("/api/lab/reset")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_lab_fix_and_apply_flow(client):
    # Create run
    run_id = client.post("/api/lab/run/S04").json()["run_id"]

    # Get fix
    fix_res = client.get(f"/api/lab/fix/{run_id}")
    assert fix_res.status_code == 200
    fix_data = fix_res.json()
    assert fix_data["run_id"] == run_id
    assert "recommendation" in fix_data
    assert "fix_description" in fix_data
    assert "fix_type" in fix_data

    # Apply fix
    apply_res = client.post(f"/api/lab/fix/{run_id}/apply")
    assert apply_res.status_code == 200
    assert apply_res.json()["applied"] is True


def test_lab_replay(client):
    original_run_id = client.post("/api/lab/run/S01").json()["run_id"]
    replay_res = client.post(f"/api/lab/replay/{original_run_id}")
    assert replay_res.status_code == 202
    new_run_id = replay_res.json()["run_id"]
    assert new_run_id != original_run_id


def test_security_findings(client):
    run_id = client.post("/api/lab/run/S01").json()["run_id"]
    r = client.get(f"/api/security/findings/{run_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "scenario_id" in data


def test_security_attack_path(client):
    run_id = client.post("/api/lab/run/S01").json()["run_id"]
    r = client.get(f"/api/security/attack-path/{run_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "nodes" in data
    assert "path" in data


def test_security_controls(client):
    run_id = client.post("/api/lab/run/S01").json()["run_id"]
    r = client.get(f"/api/security/controls/{run_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "controls" in data
    assert isinstance(data["controls"], list)


def test_security_scores(client):
    r = client.get("/api/security/scores")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_security_score_delta(client):
    run_id = client.post("/api/lab/run/S01").json()["run_id"]
    r = client.get(f"/api/security/scores/{run_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert "before_score" in data
    assert "after_score" in data
    assert "delta" in data


def test_reports_generate_and_download_flow(client):
    # 1. Create a completed run in DB to satisfy generate report precondition
    run_res = client.post("/api/lab/run/S01")
    run_id = run_res.json()["run_id"]

    # Generate JSON report
    gen_json = client.post(f"/api/reports/generate/{run_id}", json={"format": "json"})
    assert gen_json.status_code == 201
    report_id = gen_json.json()["report_id"]

    # Download JSON report
    dl_json = client.get(f"/api/reports/download/{report_id}")
    assert dl_json.status_code == 200
    assert dl_json.headers["content-type"].startswith("application/json")

    # Generate HTML report
    gen_html = client.post(f"/api/reports/generate/{run_id}", json={"format": "html"})
    assert gen_html.status_code == 201
    html_report_id = gen_html.json()["report_id"]

    # Download HTML report
    dl_html = client.get(f"/api/reports/download/{html_report_id}")
    assert dl_html.status_code == 200
    assert dl_html.headers["content-type"].startswith("text/html")
    assert b"<!DOCTYPE html>" in dl_html.content
