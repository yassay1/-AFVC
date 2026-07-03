# AFC RiskOps Agent System — 架构设计文档

> 面向地铁 AFC 设备的智能运维系统架构设计。
> 核心原则：**LLM-driven Context-Aware Tool Agent × 8 节点 LangGraph 状态流 × 维修手册 RAG**。

---

## 1. 总体架构（v0.3/v0.4）

```
Streamlit 前端 (6 页面)
    ↓ HTTP REST API
FastAPI API 层 (7 路由)
    ↓
AFCDiagnosisAgent (LangGraph 八节点)
    ↓ 调用 LangChain Tools
LangChain Tools (9 个工具，含 RAG)
    ↓ 封装业务服务
Service 业务服务层 (8 服务，含 RAG)
    ↓ 读取文件
数据与知识层 (工单 / 预测结果 / 维修手册知识库)
```

### 各层职责

| 层级 | 负责 | 不负责 |
|------|------|--------|
| Streamlit | 页面导航、上传、图表展示、Agent 交互 | 复杂业务逻辑、Agent 编排 |
| FastAPI | 接收请求、参数校验、调用 Service/Agent | 业务计算、文件读取 |
| Agent | 上下文整理、问题理解、工具规划、工具执行、证据合并、证据评估、答案生成、记忆更新 | 训练模型、读 Excel、编造数据 |
| Tools | 封装 Service 为 Agent 可调用的标准接口 | 业务逻辑实现 |
| Service | 稳定、可测试的业务逻辑（含 RAG 检索） | 前端展示、Agent 编排 |
| Data | 存储原始工单、预测结果、维修手册知识库 | — |

---

## 2. Agent 工作流（v0.3 八节点）

```
START
  ↓
prepare_context     → 整理上下文，输出 ContextPacket
  ↓
understand_query    → LLM 理解用户问题，输出 QueryUnderstanding
  ↓
plan_tools          → LLM 规划工具调用，输出 ToolPlan
  ↓
execute_tools       → 执行工具计划
  ↓
merge_evidence      → 合并工具结果为 EvidencePacket
  ↓
evaluate_evidence   → LLM 评估证据是否足够
  ├── need_more_tools → 回到 plan_tools（最多 2 轮）
  └── ready           → generate_answer
  ↓
generate_answer     → LLM 基于证据生成最终回答
  ↓
update_memory       → 更新多轮对话状态
  ↓
END
```

### LLM 的四个角色

| 角色 | 所在节点 | 职责 |
|------|---------|------|
| Query Understanding | understand_query_node | 将自然语言问题解析为结构化语义，含指代消解和设备切换识别 |
| Tool Planning | plan_tools_node | 根据问题理解和可用工具列表，规划工具调用，说明每步目的和预期证据 |
| Evidence Evaluation | evaluate_evidence_node | 判断当前证据是否足够回答用户，不足时建议补充工具 |
| Answer Generation | generate_answer_node | 基于 EvidencePacket 生成最终回答，受 AnswerPolicy 约束 |

### 关键设计原则

- **LLM 不直接编造答案**：所有风险数值、设备信息、历史工单和维修建议都来自工具结果
- **证据包约束回答**：generate_answer_node 只能基于 EvidencePacket 回答
- **RAG 是按需工具**：不是默认上下文，由 plan_tools / evaluate_evidence 决定是否调用
- **结构化输出工程**：LLM JSON 输出经过 extract → json.loads → Pydantic → repair 四步处理

---

## 3. Agent State（v0.3 升级版）

```python
class AfcAgentState(TypedDict, total=False):
    # v0.3 新增
    context_packet: dict[str, Any]
    query_understanding: dict[str, Any]
    tool_plan: dict[str, Any]
    evidence_packet: dict[str, Any]
    evidence_evaluation: dict[str, Any]
    tool_loop_count: int
    memory_update: dict[str, Any]
    last_evidence_summary: dict[str, Any]

    # 兼容字段
    query: str
    intent: dict[str, Any]
    assetnum: Optional[str]
    task_type: Optional[str]
    final_answer: str
    errors: list[str]
    messages: list[BaseMessage]
    last_assetnum: Optional[str]
    ...
```

---

## 4. 任务类型与工具路由（v0.3）

| task_type | 示例问题 | 调用工具 |
|-----------|---------|---------|
| capability_query | "你会干什么？" | 无 |
| data_overview | "这批工单整体情况怎么样？" | data_summary |
| high_risk_ranking | "当前高风险设备有哪些？" | high_risk_devices |
| full_diagnosis | "帮我分析设备 100023" | integrated_analysis |
| risk_query | "设备 100023 未来 30 天风险高吗？" | predict_device_risk |
| advice_query | "设备 100023 建议检查什么？" | maintenance_advice |
| history_query | "设备 100023 最近有哪些故障？" | device_history |
| risk_explanation | "为什么设备 100023 是红色预警？" | predict_device_risk |
| risk_and_advice_query | "风险高不高，应该检查什么？" | predict + advice |
| manual_query | "按维修手册应该查哪里？" | search_maintenance_manual |

**重要：** 这不是硬编码 task_type → 工具映射。LLM 通过 plan_tools_node 解释为什么调用、期望什么证据。

---

## 5. 工具层（9 个工具）

| 工具 | 输入 | 输出 |
|------|------|------|
| get_data_summary_tool | top_n | 工单概览统计 |
| list_devices_tool | — | 设备列表 |
| get_device_history_tool | assetnum, limit | 历史工单 |
| predict_device_risk_tool | assetnum | 6 时间窗口风险 |
| get_warning_level_tool | risk_30d, risk_90d | 预警等级 + 巡检窗口 |
| get_maintenance_advice_tool | assetnum | 维修建议 |
| get_integrated_analysis_tool | assetnum | 综合分析（聚合上述全部） |
| get_high_risk_devices_tool | top_n | 高风险设备 Top N |
| **search_maintenance_manual_tool** | query, assetnum, subsystem, fault_phenomenon | **维修手册 RAG 检索** |

---

## 6. RAG 服务

### 定位

RAG 不是默认上下文，而是维修手册检索工具。由 plan_tools_node / evaluate_evidence_node 决定是否调用。

### 触发场景

- advice_query / risk_and_advice_query / manual_query
- full_diagnosis 中需要维修建议增强时
- 用户明确说"按手册""按规程""按维修手册""按标准流程"

### 第一版实现

- 读取 `backend/data/knowledge/manuals` 下的 .txt / .md 文件
- 按段落切分，关键词 n-gram 匹配 + 相似度评分
- 返回 top_k 结果
- 后续可升级为向量数据库 + embedding 方案

---

## 7. 结构化输出策略

```
LLM 输出
  ↓
extract_json_from_text（支持纯 JSON / markdown 代码块 / 前后废话）
  ↓
json.loads
  ↓
Pydantic 校验
  ↓
失败 → repair_json_output（让 LLM 修复一次）
  ↓
仍失败 → 返回结构化错误 + 规则兜底
```

---

## 8. 多轮对话支持

- LangGraph InMemorySaver checkpointer 持久化状态
- 指代词检测（"它"、"这个设备"、"刚才那个"）→ 继承上一轮设备
- 设备切换词检测（"换成 XXX"、"切换到 XXX"）→ 更新设备
- 全局问题（data_overview / high_risk_ranking）不继承设备上下文
- 记忆更新节点负责保存精简 evidence summary

---

## 9. 目录结构（v0.3）

```
backend/
  main.py
  api/
    agent_api.py, upload_api.py, data_api.py, device_api.py,
    predict_api.py, advice_api.py, analysis_api.py
  agent/
    state.py              # Agent 状态（v0.3 升级版）
    schemas.py             # 新：所有 Pydantic Schema
    llm_json.py            # 新：结构化输出工具
    graph.py               # 八节点 LangGraph
    tools.py               # 9 个 LangChain Tools
    report_builder.py      # 报告生成模板
    prompts.py             # LLM Prompt 模板
    nodes/                 # 新：拆分后的节点实现
      __init__.py
      prepare_context.py
      understand_query.py
      plan_tools.py
      execute_tools.py
      merge_evidence.py
      evaluate_evidence.py
      generate_answer.py
      update_memory.py
      compat.py            # 向后兼容旧三节点 API
  services/
    data_service.py, device_service.py, prediction_service.py,
    warning_service.py, advice_service.py, analysis_service.py,
    model_adapter.py, rag_service.py   # 新：RAG 服务
  core/
    config.py, llm.py
  data/
    raw/, mock/, knowledge/manuals/
frontend/
  streamlit_app.py
tests/
  test_agent_graph.py, test_agent_v03_graph.py, test_agent_v03_nodes.py,
  test_agent_tools.py, test_services.py, test_llm_json.py, test_rag_service.py
docs/
  architecture.md, project-brief.md
```

---

## 10. 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | Streamlit |
| Agent | LangGraph + LangChain Tools |
| LLM | OpenAI-compatible API |
| 数据处理 | Polars + Pandas |
| 可观测 | LangSmith (可选) |
| 数据校验 | Pydantic |
| RAG | 第一版关键词匹配，后续升级向量数据库 |
