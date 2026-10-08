import pytest

from app.schemas.scenario import ScenarioResult

CORS_ORIGIN = "http://localhost:3000"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_cors_allows_trunk_dev_server(client):
    r = client.options(
        "/api/store/ping",
        headers={"Origin": CORS_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == CORS_ORIGIN


def test_cors_rejects_other_origins(client):
    r = client.get("/api/store/ping", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("group", ["store", "security", "reports"])
def test_route_groups_mounted(client, group):
    r = client.get(f"/api/{group}/ping")
    assert r.status_code == 200
    assert r.json()["group"] == group


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/lab/scenarios"),
        ("post", "/api/lab/run"),
        ("get", "/api/lab/status/RUN-0001"),
        ("post", "/api/lab/reset"),
        ("post", "/api/lab/replay/RUN-0001"),
    ],
)
def test_lab_stubs_return_501(client, method, path):
    assert getattr(client, method)(path).status_code == 501


def test_shared_result_schema_accepts_contract_example():
    result = ScenarioResult.model_validate(
        {
            "scenario_id": "S07",
            "scenario_name": "price_coupon_manipulation",
            "run_id": "RUN-0012",
            "status": "detected",
            "severity": "HIGH",
            "affected_component": "checkout",
            "attack_path": ["customer", "cart", "checkout", "pricing_logic"],
            "controls": {
                "api_validation": "detected",
                "business_validation": "missed",
                "logging": "detected",
            },
            "before_score": 61,
            "after_score": 92,
        }
    )
    assert result.after_score - result.before_score == 31


def test_shared_result_schema_appears_in_openapi(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert "ScenarioResult" in schemas
