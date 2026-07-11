"""Pydantic schemas for the current eight-node AFC Agent.

The agent uses ``route`` and ``business_goal`` as the only semantic routing
standard.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextPacket(StrictModel):
    current_query: str
    active_assetnum: str | None = None
    active_route: str | None = None
    active_business_goal: str | None = None
    active_time_window: str | None = None
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    recent_messages_summary: str | None = None
    last_tool_results_summary: dict[str, Any] | None = None
    last_evidence_summary: dict[str, Any] | None = None
    conversation_focus: str | None = None
    known_entities: list[str] = Field(default_factory=list)
    capability_boundary: dict[str, Any] = Field(default_factory=dict)


Route = Literal[
    "direct_chat",
    "capability_query",
    "business_global",
    "business_device",
    "needs_clarification",
    "unsupported",
]

BusinessGoal = Literal[
    "data_overview",
    "high_risk_ranking",
    "device_risk",
    "device_history",
    "device_advice",
    "fault_type_prediction",
    "full_diagnosis",
    "manual_search",
    None,
]


class QueryUnderstanding(StrictModel):
    route: Route = "direct_chat"
    business_goal: BusinessGoal = None
    assetnum: str | None = None
    time_window: str | None = None
    needs_asset: bool
    needs_tools: bool
    needs_rag: bool
    context_used: bool
    information_need: str
    user_question_rewrite: str
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_business_consistency(self) -> "QueryUnderstanding":
        if self.route == "business_device":
            if not self.business_goal:
                raise ValueError("route=business_device requires business_goal")
            if not self.assetnum:
                raise ValueError("route=business_device requires assetnum")
            if not self.needs_asset:
                raise ValueError("route=business_device requires needs_asset=true")
            if not self.needs_tools:
                raise ValueError("route=business_device requires needs_tools=true")

        if self.route == "business_global":
            if self.business_goal not in {"data_overview", "high_risk_ranking"}:
                raise ValueError("route=business_global requires a global business_goal")
            if self.assetnum:
                raise ValueError("route=business_global must not include assetnum")
            if self.needs_asset:
                raise ValueError("route=business_global requires needs_asset=false")
            if not self.needs_tools:
                raise ValueError("route=business_global requires needs_tools=true")

        if self.route in {"direct_chat", "capability_query", "unsupported"}:
            if self.needs_tools:
                raise ValueError(f"route={self.route} requires needs_tools=false")
            if self.needs_asset:
                raise ValueError(f"route={self.route} requires needs_asset=false")
            if self.business_goal is not None:
                raise ValueError(f"route={self.route} requires business_goal=null")

        if self.route == "needs_clarification":
            if self.needs_tools:
                raise ValueError("route=needs_clarification requires needs_tools=false")
            if self.assetnum:
                raise ValueError("route=needs_clarification must not include assetnum")

        return self


class ToolCallPlanItem(StrictModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    purpose: str
    expected_evidence: list[str] = Field(default_factory=list)


class ToolPlan(StrictModel):
    tool_calls: list[ToolCallPlanItem] = Field(default_factory=list)
    use_existing_evidence: bool = False
    reason: str
    answer_mode: Literal[
        "direct_chat",
        "capability_intro",
        "ask_for_assetnum",
        "evidence_based",
        "unsupported",
    ] = "direct_chat"
    answer_policy: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(StrictModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None
    duration_ms: float | None = None


class EvidencePacket(StrictModel):
    assetnum: str | None = None
    device_profile: dict[str, Any] | None = None
    history_summary: dict[str, Any] | None = None
    risk_prediction: dict[str, Any] | None = None
    warning: dict[str, Any] | None = None
    maintenance_advice: dict[str, Any] | None = None
    manual_evidence: list[dict[str, Any]] | None = None
    fault_prediction: dict[str, Any] | None = None
    data_overview: dict[str, Any] | None = None
    high_risk_devices: list[dict[str, Any]] | None = None
    sources: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    tool_errors: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceEvaluation(StrictModel):
    answerable: bool
    need_more_tools: bool
    missing_evidence: list[str] = Field(default_factory=list)
    suggested_next_tools: list[ToolCallPlanItem] = Field(default_factory=list)
    reason: str


class AnswerPolicy(StrictModel):
    must_not_predict_exact_failure_date: bool = True
    must_answer_with_risk_window: bool = True
    must_cite_sources: bool = True
    must_state_uncertainty: bool = True
    must_not_fabricate_device_data: bool = True
    must_not_fabricate_manual_content: bool = True
    allowed_formats: list[str] = Field(default_factory=lambda: ["text", "markdown"])


class MemoryUpdate(StrictModel):
    last_assetnum: str | None = None
    last_route: str | None = None
    last_business_goal: str | None = None
    last_time_window: str | None = None
    last_tool_results_summary: dict[str, Any] | None = None
    last_evidence_summary: dict[str, Any] | None = None
    conversation_focus: str | None = None
    should_clear_active_asset: bool = False
