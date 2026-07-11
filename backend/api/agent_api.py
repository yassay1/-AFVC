"""Agent 智能诊断 API —— LangGraph v0.3 版。

POST /agent/diagnose → 调用 v0.3 八节点 Agent 工作流。
支持多轮对话：传入 session_id 可让 Agent 记住上下文。
"""

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from backend.agent.graph import run_diagnosis


class DiagnoseRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="用户输入的自然语言诊断问题",
    )
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description='多轮会话 ID。同一 session_id 下 Agent 会记住上一轮的设备和分析结果，'
                    '支持指代补全（如"那它风险高吗？"）。不传则每次独立诊断。',
    )


class DiagnoseResponse(BaseModel):
    status: str
    query: str
    intent: dict = Field(default_factory=dict)
    assetnum: str | None = None
    time_window: str | None = None
    requires_asset: bool | None = None
    is_global: bool | None = None
    asset_exists: bool | None = None
    selected_tools: list[str] = Field(default_factory=list)
    tool_results: dict = Field(default_factory=dict)
    tool_trace: list[dict] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    final_answer: str = ""
    errors: list[str] = Field(default_factory=list)
    session_id: str | None = None
    last_assetnum: str | None = None
    last_route: str | None = None
    last_business_goal: str | None = None
    # v0.3.0 新增字段
    context_packet: dict = Field(default_factory=dict, description="上下文包")
    query_understanding: dict = Field(default_factory=dict, description="问题理解结果")
    tool_plan: dict = Field(default_factory=dict, description="工具规划（含 answer_mode）")
    evidence_packet: dict = Field(default_factory=dict, description="统一证据包（含 tool_errors）")
    evidence_evaluation: dict = Field(default_factory=dict, description="证据评估结果")
    # v0.3.0 路由字段
    route: str | None = Field(default=None, description="粗粒度语义路由")
    business_goal: str | None = Field(default=None, description="细粒度业务目标")
    answer_mode: str | None = Field(default=None, description="回答模式")


router = APIRouter(
    prefix="/agent",
    tags=["Agent 智能诊断"],
)


@router.post("/diagnose", response_model=DiagnoseResponse)
def diagnose(request: DiagnoseRequest):
    """AFC 智能诊断 Agent 入口（LangGraph v0.3 八节点版，支持多轮对话）。

    工作流（v0.3）：
    1. prepare_context   → 整理上下文，输出 ContextPacket
    2. understand_query  → LLM 理解用户问题，输出 QueryUnderstanding
    3. plan_tools        → LLM 规划工具调用，输出 ToolPlan
    4. execute_tools     → 执行工具计划
    5. merge_evidence    → 合并工具结果为 EvidencePacket
    6. evaluate_evidence → LLM 评估证据是否足够（不足则回到 plan_tools）
    7. generate_answer   → LLM 基于证据生成最终回答
    8. update_memory     → 更新多轮对话状态

    LLM 四个角色：
    - Query Understanding：结构化理解用户问题
    - Tool Planning：规划工具调用
    - Evidence Evaluation：评估证据充分性
    - Answer Generation：基于证据生成回答

    多轮对话：
    - 传入 session_id 可让 Agent 记住上一轮的设备编号和分析结果
    - 支持指代补全：用户说"那它风险高吗？"可自动关联上一轮设备
    - 支持设备切换：用户说"换成 EX011115 呢？"可自动切换设备
    - 支持 RAG 维修手册检索：用户说"按维修手册应该查哪里？"

    科学边界：
    - 风险预测表示再次产生故障工单的风险，不等同于物理故障预测
    - 维修建议是巡检方向参考，不是根因诊断结论
    - 不能预测具体故障日期
    """
    try:
        result = run_diagnosis(request.query, session_id=request.session_id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Agent 服务不可用：{str(e)}。请确认 .env 中 OPENAI_API_KEY 已配置。",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 诊断异常：{str(e)}")
