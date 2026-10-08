"""Shared scenario result contract.

M3 (attack engine) produces it, M4 (scoring/reports) consumes it, M1 (frontend)
renders it. Changes need team review.
"""

from pydantic import BaseModel, Field


class ScenarioResult(BaseModel):
    scenario_id: str = Field(examples=["S07"])
    scenario_name: str = Field(examples=["price_coupon_manipulation"])
    run_id: str = Field(examples=["RUN-0012"])
    status: str = Field(examples=["detected"])
    severity: str = Field(examples=["HIGH"])
    affected_component: str = Field(examples=["checkout"])
    attack_path: list[str] = Field(examples=[["customer", "cart", "checkout", "pricing_logic"]])
    controls: dict[str, str] = Field(
        examples=[{"api_validation": "detected", "business_validation": "missed", "logging": "detected"}]
    )
    # None until the scenario has been scored / replayed.
    before_score: int | None = Field(default=None, ge=0, le=100, examples=[61])
    after_score: int | None = Field(default=None, ge=0, le=100, examples=[92])
