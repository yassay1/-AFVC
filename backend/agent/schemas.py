"""AFC Agent v0.3 统一结构化 Schema。

所有 LLM 输出、工具计划和证据包的统一数据模型。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── 上下文包 ──────────────────────────────────────────────────

class ContextPacket(BaseModel):
    """prepare_context_node 输出的上下文包。

    告诉后续 LLM 节点当前对话焦点、上一轮结果和能力边界。
    """

    current_query: str = Field(description="当前用户原始问题")
    active_assetnum: str | None = Field(default=None, description="当前活跃的设备编号")
    active_task_type: str | None = Field(default=None, description="当前任务类型")
    active_time_window: str | None = Field(default=None, description="当前时间窗口")

    recent_messages: list[dict[str, Any]] = Field(
        default_factory=list, description="最近几条对话消息（最多 6 条）"
    )
    recent_messages_summary: str | None = Field(
        default=None, description="对话历史摘要（长对话时压缩生成）"
    )

    last_tool_results_summary: dict[str, Any] | None = Field(
        default=None, description="上一轮工具结果精简摘要"
    )
    last_evidence_summary: dict[str, Any] | None = Field(
        default=None, description="上一轮证据包精简摘要"
    )

    conversation_focus: str | None = Field(
        default=None, description="当前对话焦点描述（如 '分析设备1000029970的风险'）"
    )
    known_entities: list[str] = Field(
        default_factory=list, description="本轮已知的实体列表（设备编号等）"
    )

    capability_boundary: dict[str, Any] = Field(
        default_factory=dict,
        description="系统能力边界声明（如不能预测精确故障日期等）",
    )


# ── 问题理解 ──────────────────────────────────────────────────

class QueryUnderstanding(BaseModel):
    """understand_query_node 的输出 —— LLM 结构化理解。"""

    task_type: Literal[
        "capability_query",
        "data_overview",
        "high_risk_ranking",
        "full_diagnosis",
        "risk_query",
        "history_query",
        "advice_query",
        "risk_explanation",
        "risk_and_advice_query",
        "manual_query",
        "followup_rewrite",
        "unknown",
    ] = Field(description="任务类型")

    assetnum: str | None = Field(default=None, description="识别到的设备编号")
    time_window: str | None = Field(default=None, description="识别到的时间窗口")

    needs_asset: bool = Field(description="该任务是否需要设备编号")
    needs_rag: bool = Field(description="是否需要维修手册 RAG 检索")
    context_used: bool = Field(description="是否使用了上下文中的信息（指代消解等）")

    information_need: str = Field(description="用户信息需求的自然语言描述")
    user_question_rewrite: str = Field(description="结合上下文重写后的可执行问题")

    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="解析置信度"
    )


# ── 工具计划 ──────────────────────────────────────────────────

class ToolCallPlanItem(BaseModel):
    """单个工具调用计划项。"""

    tool_name: str = Field(description="工具名称")
    args: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    purpose: str = Field(description="为什么调用这个工具")
    expected_evidence: list[str] = Field(
        default_factory=list, description="期望从该工具获取的证据字段"
    )


class ToolPlan(BaseModel):
    """plan_tools_node 的输出 —— LLM 工具规划结果。"""

    tool_calls: list[ToolCallPlanItem] = Field(
        default_factory=list, description="计划调用的工具列表"
    )
    use_existing_evidence: bool = Field(
        default=False, description="是否使用已有证据（不需再调工具）"
    )
    reason: str = Field(description="规划原因说明")
    answer_policy: dict[str, Any] = Field(
        default_factory=dict, description="回答策略约束（如不能预测具体日期等）"
    )


# ── 工具执行结果 ──────────────────────────────────────────────

class ToolExecutionResult(BaseModel):
    """单个工具的执行结果记录。"""

    tool_name: str = Field(description="工具名称")
    args: dict[str, Any] = Field(default_factory=dict, description="实际传入参数")
    status: str = Field(description="执行状态：success / error")
    result: dict[str, Any] | None = Field(default=None, description="工具返回结果")
    error: str | None = Field(default=None, description="错误信息")
    duration_ms: float | None = Field(default=None, description="执行耗时（毫秒）")


# ── 证据包 ────────────────────────────────────────────────────

class EvidencePacket(BaseModel):
    """merge_evidence_node 输出的统一证据包。"""

    assetnum: str | None = Field(default=None, description="目标设备编号")

    device_profile: dict[str, Any] | None = Field(
        default=None, description="设备基本信息"
    )
    history_summary: dict[str, Any] | None = Field(
        default=None, description="历史工单摘要"
    )
    risk_prediction: dict[str, Any] | None = Field(
        default=None, description="风险预测结果"
    )
    warning: dict[str, Any] | None = Field(default=None, description="预警信息")
    maintenance_advice: dict[str, Any] | None = Field(
        default=None, description="维修建议"
    )
    manual_evidence: list[dict[str, Any]] | None = Field(
        default=None, description="维修手册检索证据"
    )
    data_overview: dict[str, Any] | None = Field(
        default=None, description="数据概览"
    )
    high_risk_devices: list[dict[str, Any]] | None = Field(
        default=None, description="高风险设备列表"
    )

    sources: list[str] = Field(
        default_factory=list, description="证据来源工具列表"
    )
    missing_evidence: list[str] = Field(
        default_factory=list, description="缺失的证据类型"
    )


# ── 证据评估 ──────────────────────────────────────────────────

class EvidenceEvaluation(BaseModel):
    """evaluate_evidence_node 的输出 —— LLM 证据充分性评估。"""

    answerable: bool = Field(description="当前证据是否足够回答用户问题")
    need_more_tools: bool = Field(description="是否需要补充工具调用")
    missing_evidence: list[str] = Field(
        default_factory=list, description="缺失的证据类型"
    )
    suggested_next_tools: list[ToolCallPlanItem] = Field(
        default_factory=list, description="建议补充的工具调用"
    )
    reason: str = Field(description="评估理由")


# ── 回答策略 ──────────────────────────────────────────────────

class AnswerPolicy(BaseModel):
    """generate_answer_node 的回答约束策略。"""

    must_not_predict_exact_failure_date: bool = Field(
        default=True, description="禁止预测精确故障日期"
    )
    must_answer_with_risk_window: bool = Field(
        default=True, description="必须使用风险窗口表达"
    )
    must_cite_sources: bool = Field(
        default=True, description="必须注明证据来源"
    )
    must_state_uncertainty: bool = Field(
        default=True, description="必须说明科学边界"
    )
    must_not_fabricate_device_data: bool = Field(
        default=True, description="禁止编造设备数据"
    )
    must_not_fabricate_manual_content: bool = Field(
        default=True, description="禁止编造维修手册内容"
    )
    allowed_formats: list[str] = Field(
        default_factory=lambda: ["text", "markdown"],
        description="允许的回答格式",
    )


# ── 记忆更新 ──────────────────────────────────────────────────

class MemoryUpdate(BaseModel):
    """update_memory_node 的记忆更新数据。"""

    last_assetnum: str | None = Field(default=None, description="更新的活跃设备编号")
    last_task_type: str | None = Field(default=None, description="更新的任务类型")
    last_time_window: str | None = Field(default=None, description="更新的时间窗口")
    last_tool_results_summary: dict[str, Any] | None = Field(
        default=None, description="精简的工具结果摘要"
    )
    last_evidence_summary: dict[str, Any] | None = Field(
        default=None, description="精简的证据包摘要"
    )
    conversation_focus: str | None = Field(
        default=None, description="当前对话焦点描述"
    )
    should_clear_active_asset: bool = Field(
        default=False, description="是否清除活跃设备（全局问题等场景）"
    )
