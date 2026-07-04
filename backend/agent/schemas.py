"""AFC Agent v0.3.0 统一结构化 Schema。

v0.3.0 升级：
- QueryUnderstanding 增加 route + business_goal（粗粒度语义路由）
- ToolPlan 增加 answer_mode（回答模式）
- EvidencePacket 增加 tool_errors（工具错误承载）
- 保留 task_type 用于向后兼容，但主逻辑优先使用 route/business_goal
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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


# ── 问题理解（v0.3.0 升级）──────────────────────────────────

class QueryUnderstanding(BaseModel):
    """understand_query_node 的输出 —— LLM 结构化理解。

    v0.3.0 升级：新增 route 和 business_goal 作为主路由字段。
    task_type 保留用于向后兼容，但 plan_tools 等下游节点应优先使用 route。
    """

    # ── v0.3.0 新增：粗粒度语义路由 ──
    route: Literal[
        "direct_chat",           # 闲聊/问候
        "capability_query",      # 询问系统能力
        "business_global",       # 全局业务问题（数据概览/高风险排行）
        "business_device",       # 单设备业务问题
        "needs_clarification",   # 缺少关键参数（如设备编号）
        "unsupported",           # 超出系统能力
    ] = Field(
        default="direct_chat",
        description="粗粒度语义路由，决定后续节点行为",
    )

    business_goal: Literal[
        "data_overview",         # 数据概览
        "high_risk_ranking",     # 高风险设备排行
        "device_risk",           # 单设备风险查询
        "device_history",        # 单设备历史查询
        "device_advice",         # 单设备维修建议
        "full_diagnosis",        # 单设备完整诊断
        "manual_search",         # 维修手册检索
        None,
    ] = Field(
        default=None,
        description="细粒度业务目标（business_global / business_device 时有效）",
    )

    # ── 兼容字段：task_type（保留用于旧 API 和前端）──────────
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
        "direct_chat",
        "unknown",
    ] = Field(
        default="unknown",
        description="旧 task_type 字段，由 route + business_goal 自动映射生成",
    )

    # ── 参数提取 ──
    assetnum: str | None = Field(default=None, description="识别到的设备编号")
    time_window: str | None = Field(default=None, description="识别到的时间窗口")

    needs_asset: bool = Field(description="该任务是否需要设备编号")
    needs_tools: bool = Field(description="是否需要调用业务工具")
    needs_rag: bool = Field(description="是否需要维修手册 RAG 检索")
    context_used: bool = Field(description="是否使用了上下文中的信息（指代消解等）")

    information_need: str = Field(description="用户信息需求的自然语言描述")
    user_question_rewrite: str = Field(description="结合上下文重写后的可执行问题")

    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="解析置信度"
    )

    @model_validator(mode="after")
    def validate_business_consistency(self) -> "QueryUnderstanding":
        """校验 route/business_goal/assetnum/needs_* 的业务一致性。"""
        if self.route == "business_device":
            if not self.business_goal:
                raise ValueError("route=business_device 时 business_goal 不能为空")
            if not self.assetnum:
                raise ValueError("route=business_device 时 assetnum 不能为空；如果没有设备编号应使用 route=needs_clarification")
            if not self.needs_asset:
                raise ValueError("route=business_device 时 needs_asset 必须为 true")
            if not self.needs_tools:
                raise ValueError("route=business_device 时 needs_tools 必须为 true")

        if self.route == "business_global":
            if self.business_goal not in {"data_overview", "high_risk_ranking"}:
                raise ValueError("route=business_global 时 business_goal 必须是 data_overview 或 high_risk_ranking")
            if self.assetnum:
                raise ValueError("route=business_global 不应包含 assetnum")
            if self.needs_asset:
                raise ValueError("route=business_global 时 needs_asset 必须为 false")
            if not self.needs_tools:
                raise ValueError("route=business_global 时 needs_tools 必须为 true")

        if self.route in {"direct_chat", "capability_query", "unsupported"}:
            if self.needs_tools:
                raise ValueError(f"route={self.route} 时 needs_tools 必须为 false")
            if self.needs_asset:
                raise ValueError(f"route={self.route} 时 needs_asset 必须为 false")
            if self.business_goal is not None:
                raise ValueError(f"route={self.route} 时 business_goal 必须为 null")

        if self.route == "needs_clarification":
            if self.needs_tools:
                raise ValueError("route=needs_clarification 时 needs_tools 必须为 false")
            if self.assetnum:
                raise ValueError("route=needs_clarification 不应包含 assetnum")

        return self


# ── 工具计划（v0.3.0 升级）──────────────────────────────────

class ToolCallPlanItem(BaseModel):
    """单个工具调用计划项。"""

    tool_name: str = Field(description="工具名称")
    args: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    purpose: str = Field(description="为什么调用这个工具")
    expected_evidence: list[str] = Field(
        default_factory=list, description="期望从该工具获取的证据字段"
    )


class ToolPlan(BaseModel):
    """plan_tools_node 的输出 —— LLM 工具规划结果。

    v0.3.0 升级：新增 answer_mode，决定最终回答的生成方式。
    """

    tool_calls: list[ToolCallPlanItem] = Field(
        default_factory=list, description="计划调用的工具列表"
    )
    use_existing_evidence: bool = Field(
        default=False, description="是否使用已有证据（不需再调工具）"
    )
    reason: str = Field(description="规划原因说明")

    # ── v0.3.0 新增：回答模式 ──
    answer_mode: Literal[
        "direct_chat",           # 普通闲聊
        "capability_intro",      # 系统能力介绍
        "ask_for_assetnum",      # 缺少设备编号，追问用户
        "evidence_based",        # 基于证据包回答
        "unsupported",           # 超出系统能力
    ] = Field(
        default="direct_chat",
        description="回答模式，决定 generate_answer 的行为",
    )

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
    error_type: str | None = Field(
        default=None,
        description="错误类型（如 missing_required_argument / tool_execution_error）",
    )
    duration_ms: float | None = Field(default=None, description="执行耗时（毫秒）")


# ── 证据包（v0.3.0 升级）────────────────────────────────────

class EvidencePacket(BaseModel):
    """merge_evidence_node 输出的统一证据包。

    v0.3.0 升级：新增 tool_errors，承载工具执行失败信息。
    """

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
        default_factory=list, description="证据来源工具列表（仅成功）"
    )
    missing_evidence: list[str] = Field(
        default_factory=list, description="缺失的证据类型"
    )

    # ── v0.3.0 新增：工具错误 ──
    tool_errors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="工具执行过程中产生的错误，每个元素包含 tool/error_type/message",
    )


# ── 证据评估 ──────────────────────────────────────────────────

class EvidenceEvaluation(BaseModel):
    """evaluate_evidence_node 的输出 —— LLM 证据充分性评估。

    v0.3.0 更新：非 evidence_based 模式不要求业务证据。
    """

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


# ── route → task_type 映射（兼容旧代码）─────────────────────

def route_to_task_type(route: str, business_goal: str | None) -> str:
    """将 v0.3.0 route + business_goal 映射为旧版 task_type。

    这允许 plan_tools 等下游节点继续使用旧 task_type 做工具路由，
    同时也让旧 API 返回兼容的 task_type。
    """
    if route == "direct_chat":
        return "direct_chat"
    if route == "capability_query":
        return "capability_query"
    if route == "unsupported":
        return "unknown"
    if route == "needs_clarification":
        return "unknown"
    if route == "business_global":
        if business_goal == "data_overview":
            return "data_overview"
        if business_goal == "high_risk_ranking":
            return "high_risk_ranking"
        return "data_overview"
    if route == "business_device":
        if business_goal == "device_risk":
            return "risk_query"
        if business_goal == "device_history":
            return "history_query"
        if business_goal == "device_advice":
            return "advice_query"
        if business_goal == "full_diagnosis":
            return "full_diagnosis"
        if business_goal == "manual_search":
            return "manual_query"
        return "full_diagnosis"
    return "unknown"
