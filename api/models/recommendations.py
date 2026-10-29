"""Structured, run-specific AI explanations; action instructions stay rule-based."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ActionExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_index: int = Field(ge=0, le=3, strict=True)
    explanation: str = Field(min_length=10, max_length=500)


class GuidanceContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=10, max_length=700)
    explanations: list[ActionExplanation] = Field(min_length=1, max_length=4)


class SimulationGuidance(BaseModel):
    status: Literal["pending", "ready", "unavailable"]
    run_id: str
    provider: str = "Gemini"
    model: str
    prompt_version: str = "mangopoint-guidance-v1"
    simulation_model_version: str
    requested_at: str
    expires_at: str
    generated_at: Optional[str] = None
    reason: Optional[Literal[
        "not_configured", "disabled", "no_actions", "busy", "request_failed",
        "invalid_response", "expired",
    ]] = None
    summary: Optional[str] = None
    explanations: list[ActionExplanation] = Field(default_factory=list)
