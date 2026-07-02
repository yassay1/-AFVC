"""Agent 智能诊断 API —— LangGraph 版。

POST /agent/diagnose → 调用 AFCDiagnosisAgent 工作流。
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
    assetnum: str | None = None
    task_type: str | None = None
    time_window: str | None = None
    selected_tools: list[str] = Field(default_factory=list)
    tool_results: dict = Field(default_factory=dict)
    final_answer: str = ""
    errors: list[str] = Field(default_factory=list)
    session_id: str | None = None
    last_assetnum: str | None = None
    last_task_type: str | None = None


router = APIRouter(
    prefix="/agent",
    tags=["Agent 智能诊断"],
)


@router.post("/diagnose", response_model=DiagnoseResponse)
def diagnose(request: DiagnoseRequest):
    """AFC 智能诊断 Agent 入口（LangGraph 版，支持多轮对话）。

    工作流：
    1. parse_question  → LLM 解析用户问题（多轮模式下继承上下文）
    2. resolve_asset   → 校验设备编号
    3. route_task      → 匹配任务类型 → 选择工具
    4. execute_tools   → 调用 LangChain Tools
    5. merge_evidence  → 整合工具结果为证据
    6. generate_report → LLM / 模板生成诊断报告

    多轮对话：
    - 传入 session_id 可让 Agent 记住上一轮的设备编号和分析结果
    - 支持指代补全：用户说"那它风险高吗？"可自动关联上一轮设备
    - 支持设备切换：用户说"换成 EX011115 呢？"可自动切换设备

    支持的问题类型：
    - 数据概览："这批工单整体情况怎么样？"
    - 高风险设备："今天优先巡检哪些设备？"
    - 单设备分析："帮我分析设备 1000029970"
    - 风险查询："设备 1000029970 未来 30 天风险高吗？"
    - 历史查询："设备 1000029970 最近有哪些故障？"
    - 维修建议："设备 1000029970 建议检查什么？"
    - 预警解释："为什么设备 1000029970 是红色预警？"

    科学边界：
    - 风险预测表示再次产生故障工单的风险，不等同于物理故障预测
    - 维修建议是巡检方向参考，不是根因诊断结论
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
