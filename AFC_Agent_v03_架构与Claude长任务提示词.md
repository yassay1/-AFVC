# AFC Agent v0.3/v0.4 最终架构与 Claude Code 长任务提示词

## 一、项目下一阶段目标

项目下一阶段建议命名为：

```text
v0.3 / v0.4：LLM-driven AFC Context-Aware Tool Agent
```

中文名称：

```text
上下文感知型 AFC 工具调用智能体
```

核心目标：

```text
把当前 parse_intent → reason_act → generate_report
升级为
prepare_context → understand_query → plan_tools → execute_tools → merge_evidence → evaluate_evidence → generate_answer → update_memory
```

这一版不再围绕“规则兜底”展开，而是把重点放在：

```text
LLM 理解问题
LLM 规划工具
工具提供真实数据
证据包约束回答
RAG 提供维修手册依据
LangGraph 管理状态流
LangSmith 追踪每一步
```

---

## 二、最终 Agent 架构

推荐最终流程：

```text
用户问题
  ↓
FastAPI /agent/diagnose
  ↓
LangGraph Agent
  ↓
prepare_context_node
  ↓
understand_query_node
  ↓
plan_tools_node
  ↓
execute_tools_node
  ↓
merge_evidence_node
  ↓
evaluate_evidence_node
  ├── 证据不足 → 回到 plan_tools_node 补充工具
  └── 证据足够 → generate_answer_node
  ↓
update_memory_node
  ↓
返回最终回答
```

LangGraph 图：

```text
START
↓
prepare_context
↓
understand_query
↓
plan_tools
↓
execute_tools
↓
merge_evidence
↓
evaluate_evidence
   ├── need_more_tools → plan_tools
   └── ready_to_answer → generate_answer
↓
update_memory
↓
END
```

---

## 三、每个节点职责

### 1. prepare_context_node

它不是规则兜底，也不是意图判断节点。

它只负责整理上下文，输出 `ContextPacket`。

```python
class ContextPacket(BaseModel):
    current_query: str

    active_assetnum: str | None
    active_task_type: str | None
    active_time_window: str | None

    recent_messages: list[dict]
    recent_messages_summary: str | None

    last_tool_results_summary: dict | None
    last_evidence_summary: dict | None

    conversation_focus: str | None
    known_entities: list[str]

    capability_boundary: dict
```

它要告诉后面的 LLM：

```text
当前对话焦点是谁？
上一轮查过什么？
上一轮工具结果是什么？
系统能不能预测精确故障日期？
系统能不能确认真实根因？
```

如果只记 `last_assetnum`，这个节点太轻。  
最终版要让它承担 Context Engineering。

---

### 2. understand_query_node

这是第一个核心 LLM 节点。

它负责把用户自然语言变成结构化语义。

```python
class QueryUnderstanding(BaseModel):
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
        "unknown"
    ]

    assetnum: str | None
    time_window: str | None

    needs_asset: bool
    needs_rag: bool
    context_used: bool

    information_need: str
    user_question_rewrite: str

    confidence: float
```

例子：

用户问：

```text
他大约什么时候会再次故障？
```

在上下文中 active_assetnum 是 `1000029970`，则输出：

```json
{
  "task_type": "risk_query",
  "assetnum": "1000029970",
  "time_window": null,
  "needs_asset": true,
  "needs_rag": false,
  "context_used": true,
  "information_need": "用户想了解设备1000029970未来再次故障的大致风险窗口，而不是精确日期",
  "user_question_rewrite": "查询设备1000029970未来7/14/21/30/60/90天复发风险",
  "confidence": 0.92
}
```

---

### 3. plan_tools_node

这是第二个核心 LLM 节点。

它不回答用户，只负责规划工具调用。

```python
class ToolCallPlanItem(BaseModel):
    tool_name: str
    args: dict
    purpose: str
    expected_evidence: list[str]

class ToolPlan(BaseModel):
    tool_calls: list[ToolCallPlanItem]
    use_existing_evidence: bool
    reason: str
    answer_policy: dict
```

例子：

```json
{
  "tool_calls": [
    {
      "tool_name": "predict_device_risk_tool",
      "args": {
        "assetnum": "1000029970"
      },
      "purpose": "获取该设备未来多个时间窗口的复发风险",
      "expected_evidence": [
        "risk_7d",
        "risk_14d",
        "risk_30d",
        "risk_60d",
        "risk_90d",
        "warning_level"
      ]
    }
  ],
  "use_existing_evidence": false,
  "reason": "用户询问再次故障时间，应通过风险预测工具回答风险窗口",
  "answer_policy": {
    "must_not_predict_exact_failure_date": true,
    "must_answer_with_risk_window": true
  }
}
```

这个节点决定项目像不像真正的 Agent。

不要做简单的：

```text
task_type → tool
```

而是让 LLM 解释：

```text
为什么调用这个工具？
希望拿到什么证据？
已有证据够不够？
需不需要 RAG？
```

---

### 4. execute_tools_node

这个节点不要思考，只执行工具计划。

职责：

```text
检查工具名是否在白名单
按 tool_calls 顺序调用 LangChain Tool
记录成功/失败
保存工具输入输出
```

输出：

```python
tool_results
tool_trace
```

---

### 5. merge_evidence_node

这个节点把原始工具结果整理成统一证据包。

```python
class EvidencePacket(BaseModel):
    assetnum: str | None

    device_profile: dict | None
    history_summary: dict | None
    risk_prediction: dict | None
    warning: dict | None
    maintenance_advice: dict | None
    manual_evidence: list[dict] | None
    data_overview: dict | None
    high_risk_devices: list[dict] | None

    sources: list[str]
    missing_evidence: list[str]
```

最终回答不能直接看原始 `tool_results`，而应该看 `EvidencePacket`。

---

### 6. evaluate_evidence_node

这是第三个 LLM 节点。

它判断证据是否足够回答用户。

```python
class EvidenceEvaluation(BaseModel):
    answerable: bool
    need_more_tools: bool
    missing_evidence: list[str]
    suggested_next_tools: list[ToolCallPlanItem]
    reason: str
```

例子：

用户问：

```text
那应该先检查什么？按维修手册说
```

如果已有维修建议但没有维修手册证据，则输出：

```json
{
  "answerable": false,
  "need_more_tools": true,
  "missing_evidence": ["manual_evidence"],
  "suggested_next_tools": [
    {
      "tool_name": "search_maintenance_manual_tool",
      "args": {
        "query": "AFC设备票卡处理异常优先检查步骤"
      },
      "purpose": "检索维修手册中的检查依据",
      "expected_evidence": ["manual_steps", "manual_cause", "manual_checklist"]
    }
  ],
  "reason": "用户明确要求按维修手册回答，当前缺少手册依据"
}
```

---

### 7. generate_answer_node

最后才回答用户。

输入必须包括：

```text
query
context_packet
query_understanding
evidence_packet
answer_policy
```

Prompt 必须强调：

```text
只能基于 evidence_packet 回答
不能编造设备数据
不能编造维修手册内容
不能把风险预测说成确定故障
不能预测具体故障日期
用户问“什么时候再次故障”时，要转化为风险窗口回答
如果证据不足，要明确说明证据不足
```

---

### 8. update_memory_node

最后更新多轮状态。

保存：

```python
last_assetnum
last_task_type
last_time_window
last_tool_results_summary
last_evidence_summary
messages
conversation_focus
```

要求：

```text
如果本轮有明确 assetnum，则更新 active asset
如果是 data_overview/high_risk_ranking/capability_query，不要错误覆盖 active asset
保存精简 evidence summary，不要把大型 tool_results 全部塞进长期 state
```

---

## 四、RAG 在最终架构中的位置

RAG 不应该默认塞进 `prepare_context_node`。

正确位置：

```text
RAG 是一个工具
由 plan_tools_node / evaluate_evidence_node 决定是否调用
```

新增工具：

```python
search_maintenance_manual_tool
```

输入：

```python
query: str
assetnum: str | None = None
subsystem: str | None = None
fault_phenomenon: str | None = None
top_k: int = 5
```

输出：

```json
{
  "status": "success",
  "query": "...",
  "results": [
    {
      "content": "检查票卡通道是否有异物...",
      "source": "AFC闸机维护手册.pdf",
      "page": 12,
      "score": 0.82
    }
  ]
}
```

RAG 触发场景：

```text
advice_query
risk_and_advice_query
manual_query
full_diagnosis 中需要维修建议增强时
用户明确说“按手册”“规程”“维修手册”“标准流程”
```

---

## 五、推荐目录结构

```text
backend/
  agent/
    state.py
    graph.py

    schemas.py
    llm_json.py
    prompts.py

    context.py
    planner.py
    evidence.py
    memory.py
    tool_registry.py

    nodes/
      __init__.py
      prepare_context.py
      understand_query.py
      plan_tools.py
      execute_tools.py
      merge_evidence.py
      evaluate_evidence.py
      generate_answer.py
      update_memory.py

    tools.py
    report_builder.py

  services/
    rag_service.py
    data_service.py
    device_service.py
    prediction_service.py
    advice_service.py
    analysis_service.py
    model_adapter.py

  data/
    raw/
    mock/
    knowledge/
      manuals/
    vector_store/
```

---

## 六、结构化输出策略

不要迷信 LLM 100% 输出合法 JSON。

要做：

```text
LLM 输出
↓
硬编码提取 JSON
↓
json.loads
↓
Pydantic 校验
↓
失败后 repair 一次
↓
仍失败则返回结构化错误
```

新增文件：

```text
backend/agent/llm_json.py
```

负责：

```python
extract_json_from_text()
parse_json_with_schema()
call_llm_json()
repair_json_output()
```

这不是规则兜底，这是结构化输出工程。

---

## 七、最终验收目标

这一版完成后，应该能跑通这些问题：

```text
1. 你能干什么？
2. 这批工单整体情况怎么样？
3. 当前高风险设备有哪些？
4. 帮我分析设备 1000029970
5. 他大约什么时候会再次故障？
6. 那为什么是黄色预警？
7. 那应该先检查什么？
8. 按维修手册说应该先查哪里？
9. 换成 EX011115 呢？
10. 它最近有哪些故障？
11. 再简短一点告诉我三步
12. 这个建议有什么依据？
```

预期能力：

```text
能继承上下文
能识别指代
能规划工具
能调用多个工具
能根据证据回答
能在需要时调用 RAG
能说明科学边界
能保存多轮会话焦点
```

---

# 八、Claude Code 总任务提示词

下面内容可以直接复制给 Claude Code。

---

```text
你现在接手一个 FastAPI + Streamlit + LangGraph + LangChain Tools 的 AFC 故障复发风险预测与智能维修建议系统。

仓库当前已有结构大致如下：

- backend/main.py
- backend/api/agent_api.py
- backend/agent/state.py
- backend/agent/tools.py
- backend/agent/nodes.py
- backend/agent/graph.py
- backend/agent/report_builder.py
- backend/services/data_service.py
- backend/services/device_service.py
- backend/services/prediction_service.py
- backend/services/advice_service.py
- backend/services/analysis_service.py
- backend/services/model_adapter.py
- frontend/streamlit_app.py
- tests/

当前 Agent 架构大致是三节点：

parse_intent -> reason_act -> generate_report

我要你把它升级成一个真正的 LLM-driven Context-Aware Tool Agent。

重要要求：

1. 不要把重点放在规则兜底上。
2. 不要继续让 reason_act_node 同时做规划、执行、证据合并。
3. 把 Agent 改成清晰的 LangGraph 状态流。
4. LLM 要用于：
   - understand_query_node：结构化理解用户问题
   - plan_tools_node：规划工具调用
   - evaluate_evidence_node：判断证据是否足够
   - generate_answer_node：基于证据生成最终回答
5. 所有 LLM 输出都必须是结构化 JSON。
6. 但不要天真相信 LLM 永远输出合法 JSON。
7. 请实现一个 llm_json.py，用于：
   - 从 LLM 文本中提取 JSON
   - json.loads
   - Pydantic 校验
   - 失败后调用 repair prompt 修复一次
   - 最终返回结构化对象或结构化错误
8. 不要破坏现有 FastAPI 接口。
9. 尽量保持前端可用。
10. 尽量保持已有 tests 能通过，同时新增新的 Agent 架构测试。
11. 预测模型暂时不要升级，继续使用现有 prediction_service/model_adapter。
12. 要为 RAG 预留并尽量实现第一版维修手册检索工具。
13. 如果本地没有真实维修手册，就做一个可运行的轻量 rag_service，允许读取 backend/data/knowledge/manuals 下的 .txt/.md 文件，后续再扩展 PDF。
14. 最终要保证 Agent 能稳定处理多轮上下文、工具规划、证据约束回答。

请按照下面阶段执行。每个阶段完成后自测，继续下一阶段，不要只做表面改名。

==================================================
阶段 1：重构 Agent Schema 和 State
==================================================

目标：
建立下一代 Agent 的统一数据结构，不再混用 intent/task_type。

请新增或重构：

backend/agent/schemas.py

至少包含以下 Pydantic 模型：

1. ContextPacket
2. QueryUnderstanding
3. ToolCallPlanItem
4. ToolPlan
5. ToolExecutionResult
6. EvidencePacket
7. EvidenceEvaluation
8. AnswerPolicy
9. MemoryUpdate

字段要求：

ContextPacket:
- current_query: str
- active_assetnum: str | None
- active_task_type: str | None
- active_time_window: str | None
- recent_messages: list[dict]
- recent_messages_summary: str | None
- last_tool_results_summary: dict | None
- last_evidence_summary: dict | None
- conversation_focus: str | None
- known_entities: list[str]
- capability_boundary: dict

QueryUnderstanding:
- task_type: Literal[
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
    "unknown"
  ]
- assetnum: str | None
- time_window: str | None
- needs_asset: bool
- needs_rag: bool
- context_used: bool
- information_need: str
- user_question_rewrite: str
- confidence: float

ToolCallPlanItem:
- tool_name: str
- args: dict
- purpose: str
- expected_evidence: list[str]

ToolPlan:
- tool_calls: list[ToolCallPlanItem]
- use_existing_evidence: bool
- reason: str
- answer_policy: dict

EvidencePacket:
- assetnum: str | None
- device_profile: dict | None
- history_summary: dict | None
- risk_prediction: dict | None
- warning: dict | None
- maintenance_advice: dict | None
- manual_evidence: list[dict] | None
- data_overview: dict | None
- high_risk_devices: list[dict] | None
- sources: list[str]
- missing_evidence: list[str]

EvidenceEvaluation:
- answerable: bool
- need_more_tools: bool
- missing_evidence: list[str]
- suggested_next_tools: list[ToolCallPlanItem]
- reason: str

然后重构 backend/agent/state.py。

AfcAgentState 需要新增：
- context_packet
- query_understanding
- tool_plan
- tool_results
- tool_trace
- evidence_packet
- evidence_evaluation
- answer_policy
- final_answer
- memory_update
- tool_loop_count
- last_evidence_summary

保留兼容字段：
- query
- assetnum
- task_type
- time_window
- selected_tools
- evidence
- errors
- messages
- last_assetnum
- last_task_type
- last_time_window
- last_tool_results_summary

这样可以兼容现有前端和测试。

==================================================
阶段 2：实现 LLM JSON 结构化输出工具
==================================================

新增：

backend/agent/llm_json.py

实现以下函数：

1. extract_json_from_text(text: str) -> dict
   - 支持模型输出纯 JSON
   - 支持 ```json ... ``` 代码块
   - 支持前后有多余解释文字
   - 提取第一个合法 JSON 对象
   - 注意大括号嵌套

2. parse_json_with_schema(data: dict, schema: type[BaseModel]) -> BaseModel

3. call_llm_json(
      llm,
      prompt: str,
      schema: type[BaseModel],
      repair_prompt: str | None = None,
      max_repair_attempts: int = 1,
   ) -> BaseModel

4. repair_json_output(...)
   - 当 json.loads 或 Pydantic 校验失败时，把原始输出、错误信息、目标 schema 发给 LLM
   - 要求它只返回修复后的 JSON

注意：
- 这不是规则兜底。
- 这是结构化输出工程。
- 所有 understand_query_node / plan_tools_node / evaluate_evidence_node 都要尽量使用这个工具。
- 如果现有项目已经用 with_structured_output，也可以保留，但仍建议用 llm_json.py 做统一封装，方便 OpenAI-compatible 模型兼容。

请新增 tests/test_llm_json.py，至少测试：
- 纯 JSON
- markdown json 代码块
- 前后带废话的 JSON
- 嵌套 JSON
- 非法 JSON 抛出清晰错误

==================================================
阶段 3：拆分 Agent Nodes
==================================================

新增目录：

backend/agent/nodes/

新增以下文件：

1. prepare_context.py
2. understand_query.py
3. plan_tools.py
4. execute_tools.py
5. merge_evidence.py
6. evaluate_evidence.py
7. generate_answer.py
8. update_memory.py

不要继续把所有逻辑塞进 backend/agent/nodes.py。
可以保留旧 nodes.py 做兼容导出，但新实现要放进 nodes/ 目录。

----------------------------------------
3.1 prepare_context_node
----------------------------------------

职责：
只整理上下文，不判断意图，不调用业务工具。

输入 state：
- query
- messages
- last_assetnum
- last_task_type
- last_time_window
- last_tool_results_summary
- last_evidence_summary

输出：
- context_packet

要求：
- recent_messages 最多保留最近 6 条
- 如果 messages 很长，生成 recent_messages_summary
- 第一版 summary 可以用简单截断，后续可改 LLM summarizer
- capability_boundary 要写清楚：
  - can_predict_exact_failure_date: false
  - can_predict_risk_window: true
  - can_confirm_root_cause: false
  - can_provide_inspection_suggestions: true

----------------------------------------
3.2 understand_query_node
----------------------------------------

职责：
调用 LLM，把用户问题 + context_packet 解析成 QueryUnderstanding。

Prompt 要包含：
- 当前用户问题
- context_packet
- 任务类型定义
- JSON 输出示例
- 明确要求只输出 JSON
- 允许使用 context_packet 中 active_assetnum 解决“他/它/这个设备”等指代
- 明确“什么时候再次故障”应理解为 risk_query，而不是预测精确日期
- 明确“按维修手册/规程/标准流程”应 needs_rag=true 或 manual_query

输出：
- query_understanding
- 同步兼容字段：
  - assetnum
  - task_type
  - time_window
  - requires_asset
  - is_global

不要只靠关键词判断。
重点是 LLM 结构化理解。

----------------------------------------
3.3 plan_tools_node
----------------------------------------

职责：
调用 LLM，根据 QueryUnderstanding + ContextPacket + AvailableTools + existing Evidence 规划工具。

Prompt 要包含工具列表：
- get_data_summary_tool
- list_devices_tool
- get_device_history_tool
- predict_device_risk_tool
- get_warning_level_tool
- get_maintenance_advice_tool
- get_integrated_analysis_tool
- get_high_risk_devices_tool
- search_maintenance_manual_tool 如果已实现

要求 LLM 输出 ToolPlan JSON。

规划原则：
- capability_query 可以不调用工具
- data_overview 调 get_data_summary_tool
- high_risk_ranking 调 get_high_risk_devices_tool
- full_diagnosis 优先 get_integrated_analysis_tool
- risk_query 调 predict_device_risk_tool
- history_query 调 get_device_history_tool
- advice_query 调 get_maintenance_advice_tool
- manual_query 调 search_maintenance_manual_tool
- risk_and_advice_query 可调用 predict_device_risk_tool + get_maintenance_advice_tool + 必要时 search_maintenance_manual_tool
- 如果用户明确说“按维修手册/规程”，必须规划 search_maintenance_manual_tool
- 如果已有 evidence 足够回答，可以 tool_calls 为空，use_existing_evidence=true

注意：
这不是硬编码 task_type 到工具。
LLM 需要输出 reason 和 purpose。

----------------------------------------
3.4 execute_tools_node
----------------------------------------

职责：
只执行 tool_plan。

要求：
- 检查工具白名单
- 按 tool_calls 顺序调用
- 保存 tool_results
- 保存 tool_trace
- 每个工具结果要记录：
  - tool_name
  - args
  - status
  - result
  - error
- 不要生成最终回答
- 不要理解用户意图

----------------------------------------
3.5 merge_evidence_node
----------------------------------------

职责：
把 tool_results 整理成 EvidencePacket。

要求：
- 从 get_integrated_analysis_tool 拆出：
  - device_profile
  - history_summary
  - risk_prediction
  - warning
  - maintenance_advice
- 从 predict_device_risk_tool 提取：
  - risk_prediction
  - warning
  - device_profile
- 从 get_maintenance_advice_tool 提取：
  - maintenance_advice
- 从 search_maintenance_manual_tool 提取：
  - manual_evidence
- 从 get_data_summary_tool 提取：
  - data_overview
- 从 get_high_risk_devices_tool 提取：
  - high_risk_devices
- sources 记录所有成功工具
- missing_evidence 根据 query_understanding 初步判断

----------------------------------------
3.6 evaluate_evidence_node
----------------------------------------

职责：
判断证据够不够回答。

第一版可以用 LLM JSON 输出 EvidenceEvaluation。

输入：
- query
- query_understanding
- tool_plan
- evidence_packet
- context_packet

输出：
- evidence_evaluation

规则思想可以写在 prompt 里，不要做复杂 Python 规则。

要求：
- 如果用户问风险，但没有 risk_prediction，则 need_more_tools=true，建议 predict_device_risk_tool
- 如果用户问维修手册，但没有 manual_evidence，则 need_more_tools=true，建议 search_maintenance_manual_tool
- 如果用户问历史，但没有 history_summary，则 need_more_tools=true，建议 get_device_history_tool
- 如果用户问完整诊断但缺历史/风险/建议，则 need_more_tools=true
- 否则 answerable=true

LangGraph 中要根据 need_more_tools 做条件边：
- true: 回到 plan_tools 或直接 execute suggested_next_tools
- false: generate_answer

为了避免死循环，state 中加入 tool_loop_count，最多允许 2 轮工具补充。

----------------------------------------
3.7 generate_answer_node
----------------------------------------

职责：
调用 LLM，根据 evidence_packet 生成最终答案。

Prompt 必须强调：
- 只能基于 evidence_packet 回答
- 不要编造设备数据
- 不要编造维修手册内容
- 不要把风险预测说成确定故障
- 不要预测具体故障日期
- 用户问“什么时候再次故障”时，要转化为风险窗口回答
- 如果证据不足，要明确说明证据不足
- 回答要自然、简洁、偏运维人员口吻

输出：
- final_answer

----------------------------------------
3.8 update_memory_node
----------------------------------------

职责：
更新多轮状态。

保存：
- messages
- last_assetnum
- last_task_type
- last_time_window
- last_tool_results_summary
- last_evidence_summary
- conversation_focus

要求：
- 如果本轮有明确 assetnum，则更新 active asset
- 如果是 data_overview/high_risk_ranking/capability_query，不要错误覆盖 active asset
- 保存精简 evidence summary，不要把大型 tool_results 全部塞进长期 state

==================================================
阶段 4：重构 LangGraph
==================================================

重构 backend/agent/graph.py。

最终图：

START
↓
prepare_context
↓
understand_query
↓
plan_tools
↓
execute_tools
↓
merge_evidence
↓
evaluate_evidence
↓
条件判断：
  - need_more_tools 且 tool_loop_count < 2 → plan_tools 或 execute_tools
  - 否则 → generate_answer
↓
update_memory
↓
END

要求：
- 保留 InMemorySaver checkpointer
- 保留 session_id/thread_id 多轮能力
- run_diagnosis(query, session_id=None) 的返回格式尽量兼容现有 agent_api.py
- 新增返回字段：
  - context_packet
  - query_understanding
  - tool_plan
  - evidence_packet
  - evidence_evaluation

兼容字段仍要返回：
- status
- query
- intent
- assetnum
- task_type
- time_window
- requires_asset
- is_global
- asset_exists
- selected_tools
- tool_results
- tool_trace
- evidence
- final_answer
- errors
- session_id
- last_assetnum
- last_task_type

==================================================
阶段 5：实现第一版 RAG 工具
==================================================

新增：

backend/services/rag_service.py

第一版先支持：
- 读取 backend/data/knowledge/manuals 下的 .txt 和 .md
- 按段落切分
- 用简单关键词/包含匹配 + 简单相似度评分
- 返回 top_k
- 后续再接向量数据库

新增工具：

search_maintenance_manual_tool

放入 backend/agent/tools.py 和 TOOL_BY_NAME。

输入：
- query: str
- assetnum: str | None = None
- subsystem: str | None = None
- fault_phenomenon: str | None = None
- top_k: int = 5

输出：
- status
- query
- results: list
  - content
  - source
  - score

如果 manuals 目录没有文件：
- 返回 status="empty"
- message="未找到维修手册文件，请将 .txt/.md 手册放入 backend/data/knowledge/manuals"

新增一个示例手册文件：

backend/data/knowledge/manuals/afc_maintenance_manual_sample.md

内容可以包含：
- 票卡不接收检查步骤
- 扇门异常检查步骤
- 通信异常检查步骤
- 黑屏/死机检查步骤
- 暂停服务检查步骤

注意：
这是演示用知识库，不要假装是真实官方手册。

==================================================
阶段 6：更新 Agent API 和前端展示
==================================================

backend/api/agent_api.py：
- 保持原有请求响应可用
- 响应模型可以新增字段：
  - context_packet
  - query_understanding
  - tool_plan
  - evidence_packet
  - evidence_evaluation

frontend/streamlit_app.py：
- Agent 工作台的调试 expander 中展示：
  - query_understanding
  - tool_plan
  - evidence_packet
  - evidence_evaluation
- 页面文案从“三节点/六节点旧版”改成：
  - LLM-driven Context-Aware Tool Agent
  - prepare_context → understand_query → plan_tools → execute_tools → merge_evidence → evaluate_evidence → generate_answer → update_memory

不要大改 UI，只补充调试信息和架构说明。

==================================================
阶段 7：测试
==================================================

新增 tests：

1. test_llm_json.py
2. test_agent_v03_nodes.py
3. test_agent_v03_graph.py
4. test_rag_service.py

至少覆盖：

LLM JSON：
- 纯 JSON
- markdown JSON
- 多余文字包裹 JSON
- 嵌套 JSON
- 非法 JSON

Context：
- 有上一轮 assetnum 时 context_packet 正确
- 全局问题不覆盖 active asset
- recent_messages 被压缩

Understand：
- “他大约什么时候会再次故障？” 在上下文 active_assetnum=1000029970 时解析为 risk_query
- “那应该先检查什么？” 解析为 advice_query
- “按维修手册应该查哪里？” needs_rag=true
- “当前高风险设备有哪些？” needs_asset=false

Plan：
- risk_query 规划 predict_device_risk_tool
- advice_query 规划 get_maintenance_advice_tool
- manual_query 规划 search_maintenance_manual_tool
- full_diagnosis 规划 get_integrated_analysis_tool
- 已有 evidence 足够时 use_existing_evidence=true

Graph：
- 第一轮：帮我分析设备 1000029970
- 第二轮：他大约什么时候会再次故障？
- 第三轮：那应该先检查什么？
- 第四轮：按维修手册说呢？
- 第五轮：换成 EX011115 呢？
- 第六轮：它最近有哪些故障？

要求：
- 能继承上下文
- 能切换设备
- 能调用 RAG
- 能基于 evidence 回答
- 不要预测具体故障日期
- final_answer 中要有科学边界或风险窗口表达

==================================================
阶段 8：文档更新
==================================================

更新：

README.md
docs/architecture.md
docs/project-brief.md

重点写清楚：

1. 当前 Agent 架构已经从三节点升级为八节点。
2. LLM 的四个角色：
   - Query Understanding
   - Tool Planning
   - Evidence Evaluation
   - Answer Generation
3. RAG 的定位：
   - 不是默认上下文
   - 是维修手册检索工具
   - 由 plan_tools/evaluate_evidence 决定是否调用
4. 风险预测边界：
   - 不能预测具体故障日期
   - 只能给风险窗口
5. 维修建议边界：
   - 不是最终根因
   - 是基于历史工单和手册片段的检查方向
6. 面试讲解口径：
   - 本项目重点是 Agent 工程编排，不是训练复杂模型
   - 通过 LangGraph 把上下文、理解、工具规划、证据合并、回答生成拆开
   - 所有回答都受工具证据约束

==================================================
最终验收命令
==================================================

请最终运行：

python -m pytest tests -q

然后启动后端：

python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

如果可以，也启动前端：

streamlit run frontend/streamlit_app.py

最后请在总结中告诉我：

1. 修改了哪些文件
2. 新增了哪些文件
3. 新 Agent 图是什么
4. RAG 工具是否可用
5. 哪些测试通过
6. 还有哪些限制
7. 后续如何继续升级真实向量 RAG 和真实预测模型
```

---

# 九、分阶段提示词

如果不想一次性执行，可以按下面阶段发给 Claude Code。

---

## 阶段 1：Schema + LLM JSON

```text
请先完成 AFC Agent v0.3 重构的第一阶段。

目标：
建立新的 Agent schema 和 LLM JSON 结构化输出工具。

请做两件事：

1. 新增 backend/agent/schemas.py
2. 新增 backend/agent/llm_json.py

schemas.py 中实现：
- ContextPacket
- QueryUnderstanding
- ToolCallPlanItem
- ToolPlan
- ToolExecutionResult
- EvidencePacket
- EvidenceEvaluation
- AnswerPolicy
- MemoryUpdate

要求字段完整，支持后续节点使用。

llm_json.py 中实现：
- extract_json_from_text
- parse_json_with_schema
- call_llm_json
- repair_json_output

要求：
- 能从纯 JSON、markdown json 代码块、前后有废话的文本中提取 JSON
- 能处理嵌套 JSON
- 使用 Pydantic 校验
- 失败后允许 repair 一次
- 不要用业务规则兜底，这是结构化输出工程

然后新增 tests/test_llm_json.py。
请运行测试并修复问题。
```

---

## 阶段 2：拆节点

```text
继续 AFC Agent v0.3 重构第二阶段。

目标：
把原来的三节点拆成新的节点文件。

请新增目录：

backend/agent/nodes/

并实现：

1. prepare_context.py
2. understand_query.py
3. plan_tools.py
4. execute_tools.py
5. merge_evidence.py
6. evaluate_evidence.py
7. generate_answer.py
8. update_memory.py

要求：
- prepare_context_node 只整理上下文，不判断意图
- understand_query_node 调 LLM JSON 输出 QueryUnderstanding
- plan_tools_node 调 LLM JSON 输出 ToolPlan
- execute_tools_node 只执行工具
- merge_evidence_node 整理 EvidencePacket
- evaluate_evidence_node 判断是否需要补充工具
- generate_answer_node 基于 evidence 生成最终回答
- update_memory_node 更新 last_assetnum、last_task_type、messages、last_evidence_summary

不要继续把大量逻辑写进一个 nodes.py。
旧 nodes.py 可以保留兼容导出，但核心实现要拆出去。

请新增 tests/test_agent_v03_nodes.py，至少覆盖每个节点的基本输入输出。
```

---

## 阶段 3：重构 LangGraph

```text
继续 AFC Agent v0.3 重构第三阶段。

目标：
重构 backend/agent/graph.py，把 Agent 流程升级为：

START
→ prepare_context
→ understand_query
→ plan_tools
→ execute_tools
→ merge_evidence
→ evaluate_evidence
→ 条件判断：
   - need_more_tools 且 tool_loop_count < 2：继续补充工具
   - 否则 generate_answer
→ update_memory
→ END

要求：
- 保留 InMemorySaver
- 保留 session_id/thread_id 多轮上下文能力
- run_diagnosis(query, session_id=None) 不要破坏原 API
- 返回兼容字段：
  status, query, intent, assetnum, task_type, time_window, selected_tools, tool_results, tool_trace, evidence, final_answer, errors, session_id, last_assetnum, last_task_type
- 新增字段：
  context_packet, query_understanding, tool_plan, evidence_packet, evidence_evaluation

请新增 tests/test_agent_v03_graph.py。

重点测试：
1. 第一轮：帮我分析设备 1000029970
2. 第二轮：他大约什么时候会再次故障？
3. 第三轮：那应该先检查什么？
4. 第四轮：换成 EX011115 呢？
5. 第五轮：它最近有哪些故障？

要求：
- 能继承上下文
- 能切换设备
- 能正确规划工具
- final_answer 不要预测具体故障日期
```

---

## 阶段 4：加 RAG 工具

```text
继续 AFC Agent v0.3/v0.4 重构第四阶段。

目标：
加入第一版维修手册 RAG 工具。

请新增：

backend/services/rag_service.py

第一版先做轻量可运行版本：
- 读取 backend/data/knowledge/manuals 下的 .txt 和 .md
- 按段落切分
- 用关键词匹配和简单相似度评分
- 返回 top_k 结果

然后在 backend/agent/tools.py 中新增：

search_maintenance_manual_tool

输入：
- query
- assetnum
- subsystem
- fault_phenomenon
- top_k

输出：
- status
- query
- results

如果没有手册文件，返回 empty 状态，不要报错。

新增示例文件：

backend/data/knowledge/manuals/afc_maintenance_manual_sample.md

内容包括：
- 票卡不接收
- 扇门异常
- 通信异常
- 黑屏/死机
- 暂停服务

然后修改 plan_tools_node 和 evaluate_evidence_node：
- 用户问“按维修手册”“规程”“标准流程”时，必须规划 search_maintenance_manual_tool
- advice_query 和 risk_and_advice_query 可以在需要时调用 RAG

新增 tests/test_rag_service.py。
```

---

## 阶段 5：更新前端和文档

```text
继续 AFC Agent v0.3 重构第五阶段。

目标：
更新前端调试信息和文档说明。

请修改 frontend/streamlit_app.py：

1. Agent 工作台调试 expander 里展示：
   - query_understanding
   - tool_plan
   - evidence_packet
   - evidence_evaluation
2. 页面架构说明改成新流程：
   prepare_context → understand_query → plan_tools → execute_tools → merge_evidence → evaluate_evidence → generate_answer → update_memory
3. 删除或修正旧的“三节点/六节点”不一致文案。

请更新：
- README.md
- docs/architecture.md
- docs/project-brief.md

重点写：
- LLM-driven Context-Aware Tool Agent
- LLM 四个角色：
  Query Understanding、Tool Planning、Evidence Evaluation、Answer Generation
- RAG 是维修手册检索工具，不是默认上下文
- 风险预测不能预测具体日期，只能给风险窗口
- 维修建议不是最终根因，只是检查方向

最后运行测试，修复失败。
```

---

# 十、最终面试/答辩口径

完成后可以这样介绍：

```text
这个项目不是简单调用大模型回答维修问题，而是把 AFC 运维任务拆成上下文整理、问题理解、工具规划、工具执行、证据合并、证据评估、答案生成和记忆更新八个 LangGraph 节点。

LLM 不直接编造答案，而是在结构化约束下完成 Query Understanding、Tool Planning、Evidence Evaluation 和 Answer Generation。所有风险数值、设备信息、历史工单和维修建议都来自工具结果，维修手册通过 RAG 工具按需检索，最终回答受 EvidencePacket 约束。
```
