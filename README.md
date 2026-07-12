# 🚇 AFC 故障复发风险预测与智能维修建议系统

面向地铁 AFC（自动售检票）设备的智能运维系统。基于真实故障工单数据，通过 **LLM-driven Context-Aware Tool Agent（LangGraph 八节点 + LangChain 10 工具 + RAG）** 编排，预测设备复发风险、生成红橙黄绿四级预警、识别最可能故障类别，并提供可解释的诊断报告。

> **项目定位**：重点在 Agent 工程编排与工具调用闭环，兼顾领域建模（domain/adapters/schemas 分层）。
> **v0.3.0 更新**：Agent 从三节点升级为八节点 LLM-driven 架构，LLM 承担四个角色（Query Understanding / Tool Planning / Evidence Evaluation / Answer Generation），新增故障类型预测工具、维修手册 RAG 检索工具、domain/adapters/schemas 分层架构，以及全项目文本完整性治理机制。

[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.139-green)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/langgraph-1.2.7-orange)](https://langchain-ai.github.io/langgraph/)
[![Tests](https://img.shields.io/badge/tests-186%20passed-brightgreen)]()

---

## 一、Agent 架构（v0.3.0 八节点）

```
v0.2 三节点：                       v0.3.0 八节点：
parse_intent                        prepare_context     → 整理跨轮上下文
   ↓                                understand_query    → LLM 理解问题
reason_act                          plan_tools          → LLM 规划工具
   ↓                                execute_tools       → 执行工具
generate_report                     merge_evidence      → 合并证据为统一包
                                    evaluate_evidence   → LLM 评估证据充分性
                                       ├── 不足 且 loop < 2 → 回到 plan_tools（补充工具）
                                       └── 足够 → generate_answer  → LLM 生成回答
                                    update_memory       → 更新多轮对话记忆
```

### LLM 四个角色

| 角色 | 节点 | LLM 实例 | 职责 |
|------|------|----------|------|
| **Query Understanding** | `understand_query` | parse LLM (temp=0.0) | 结构化理解问题：路由分类、业务目标识别、设备编号提取、指代消解、设备切换检测 |
| **Tool Planning** | `plan_tools` | parse LLM (temp=0.0) | 根据 route + business_goal 规划工具调用：选工具、填参数、设 answer_mode |
| **Evidence Evaluation** | `evaluate_evidence` | parse LLM (temp=0.0) | 判断证据是否足够回答用户问题，不足则建议补充工具 |
| **Answer Generation** | `generate_answer` | report LLM (temp=0.3) | 基于 EvidencePacket 生成受约束的自然语言回答 |

### 核心设计原则

- **LLM 不编造答案**：所有风险数值、设备信息、历史工单、维修建议、故障类型概率都必须来自工具结果
- **每个 LLM 节点都有规则兜底**：LLM 调用失败时自动降级到 rule-based fallback，保证系统可用
- **RAG 是按需工具**：维修手册检索由 plan_tools / evaluate_evidence 决定是否调用
- **证据包约束回答**：generate_answer_node 只能基于 EvidencePacket 中的数据回答
- **结构化输出工程**：LLM JSON 经过 `LLM 生成 → extract_json → Pydantic 校验 → repair 修复` 四步处理
- **科学边界硬约束**：不能预测故障日期、不能编造手册内容、不能把条件概率说成实际发生概率

---

## 二、语义路由标准

系统统一使用 `route` + `business_goal` 作为语义路由字段。

### route（粗粒度语义路由）

| route | 适用场景 | 是否调工具 | 示例 |
|-------|---------|-----------|------|
| `direct_chat` | 闲聊/问候 | 否 | "你好""谢谢" |
| `capability_query` | 询问系统能力 | 否 | "你能做什么？""怎么用？" |
| `business_global` | 全局数据问题 | 是 | "工单整体情况""高风险设备有哪些" |
| `business_device` | 单设备业务问题 | 是 | "分析设备 1000029970" |
| `needs_clarification` | 缺少设备编号 | 否 | "帮我分析一下风险"（没给设备号） |
| `unsupported` | 超出系统能力 | 否 | "帮我写论文""今天天气" |

### business_goal（细粒度业务目标）

| business_goal | 调用工具 | 说明 |
|---------------|---------|------|
| `data_overview` | `get_data_summary_tool` | 工单数据整体概览 |
| `high_risk_ranking` | `get_high_risk_devices_tool` | 高风险设备 Top N 排行 |
| `device_risk` | `predict_device_risk_tool` | 单设备 6 窗口复发风险预测 |
| `device_history` | `get_device_history_tool` | 设备历史故障工单查询 |
| `device_advice` | `get_maintenance_advice_tool` | 维修与巡检建议 |
| `fault_type_prediction` | `predict_device_fault_type_tool` | **新增**：故障类别预测 |
| `full_diagnosis` | `get_integrated_analysis_tool` | 单设备综合诊断（聚合以上全部） |
| `manual_search` | `search_maintenance_manual_tool` | 维修手册 RAG 检索 |

### answer_mode（回答模式）

| answer_mode | 说明 | 是否调工具 |
|-------------|------|-----------|
| `direct_chat` | 自然问候 + 功能简介 | 否 |
| `capability_intro` | 系统功能介绍 + 示例问题 | 否 |
| `ask_for_assetnum` | 请用户提供设备编号 | 否 |
| `evidence_based` | 基于 EvidencePacket 生成回答 | 是 |
| `unsupported` | 礼貌说明能力边界 | 否 |

---

## 三、10 个 Agent 工具

| # | 工具名 | 用途 | 关键参数 |
|---|--------|------|----------|
| 1 | `get_data_summary_tool` | 工单数据概览统计 | `top_n` |
| 2 | `list_devices_tool` | 设备列表（按工单数降序） | — |
| 3 | `get_device_history_tool` | 设备历史故障工单 | `assetnum`, `limit` |
| 4 | `predict_device_risk_tool` | 6 时间窗口复发风险预测（7/14/21/30/60/90 天） | `assetnum` |
| 5 | `get_warning_level_tool` | 红橙黄绿预警等级判定 | `risk_30d`, `risk_90d` |
| 6 | `get_maintenance_advice_tool` | 维修与巡检建议（含 SOP） | `assetnum` |
| 7 | `get_integrated_analysis_tool` | **核心聚合工具**：单设备综合诊断 | `assetnum`, `history_limit` |
| 8 | `get_high_risk_devices_tool` | 高风险设备 Top N 排行 | `top_n` |
| 9 | `search_maintenance_manual_tool` | 维修手册 RAG 检索 | `query`, `assetnum`, `subsystem` |
| 10 | `predict_device_fault_type_tool` | **新增**：故障类别预测 | `assetnum`, `window_days`, `top_k` |

### 工具去重与安全保护

- **工具去重**：同一工具名不重复执行（首次 error 除外）
- **白名单校验**：不在 `TOOL_BY_NAME` 中的工具名直接跳过
- **参数保护**：缺少 `assetnum` 的必参工具返回结构化错误，不暴露 Pydantic crash
- **最大调用限制**：单轮最多执行 5 个工具调用
- **工具循环限制**：最多 2 轮工具补充（`MAX_TOOL_LOOPS = 2`）

---

## 四、项目结构（v0.3.0 最新）

```
地铁AFVC/
├── backend/
│   ├── main.py                          # FastAPI 应用入口
│   ├── api/                             # API 路由层
│   │   ├── agent_api.py                 # POST /agent/diagnose — Agent 智能诊断
│   │   └── predict_api.py               # GET /predict/{assetnum}、/predict/fault-type/{assetnum}
│   ├── agent/                           # Agent 编排层 ★
│   │   ├── state.py                     # AfcAgentState + 跨轮记忆字段 + 路由常量
│   │   ├── schemas.py                   # Pydantic Schema：QueryUnderstanding、ToolPlan、EvidencePacket 等
│   │   ├── llm_json.py                  # 结构化 JSON 输出工具（提取 → 校验 → 修复）
│   │   ├── tools.py                     # 10 个 LangChain Tools 注册
│   │   ├── graph.py                     # 八节点 LangGraph 工作流 + run_diagnosis 入口
│   │   ├── report_builder.py            # 10 种报告模板（LLM 失败时的兜底方案）
│   │   └── nodes/                       # 八个节点实现
│   │       ├── prepare_context.py       # 节点 1：整理跨轮上下文
│   │       ├── understand_query.py      # 节点 2：LLM 理解用户问题
│   │       ├── plan_tools.py            # 节点 3：LLM 规划工具调用
│   │       ├── execute_tools.py         # 节点 4：执行工具计划
│   │       ├── merge_evidence.py        # 节点 5：合并工具结果为 EvidencePacket
│   │       ├── evaluate_evidence.py     # 节点 6：LLM 评估证据充分性
│   │       ├── generate_answer.py       # 节点 7：LLM 生成最终回答
│   │       └── update_memory.py         # 节点 8：更新多轮对话记忆
│   ├── services/                        # 业务服务层
│   │   ├── data_service.py              # 工单数据概览
│   │   ├── device_service.py            # 设备列表 + 历史查询
│   │   ├── prediction_service.py        # 风险预测
│   │   ├── warning_service.py           # 预警等级判定
│   │   ├── advice_service.py            # 维修建议生成
│   │   ├── analysis_service.py          # 单设备综合分析（聚合）
│   │   ├── fault_prediction_service.py  # ★ 新增：故障类型预测完整流程
│   │   ├── rag_service.py               # 维修手册 RAG 检索
│   │   └── model_adapter.py             # 外部模型结果适配
│   ├── adapters/                        # ★ 新增：数据适配层
│   │   └── fault_prediction_adapter.py  # 读取 CSV → 清洗 → 校验 → FaultTypeScore
│   ├── domain/                          # ★ 新增：领域定义层
│   │   ├── fault.py                     # FaultCategory 枚举 + 故障代码校验
│   │   ├── risk.py                      # 预测窗口、综合概率计算、单调性校验
│   │   └── warning.py                   # WarningLevel 枚举 + 四级预警规则
│   ├── schemas/                         # ★ 新增：业务 Schema 层
│   │   ├── risk_prediction.py           # RiskPredictionResult（6 窗口风险值）
│   │   ├── fault_prediction.py          # FaultTypeScore + FaultTypePredictionResult
│   │   └── device_analysis.py           # DeviceAnalysisResult
│   ├── core/                            # 核心配置
│   │   ├── config.py                    # 环境变量配置
│   │   └── llm.py                       # LLM 实例封装（parse/report 双实例懒加载）
│   └── data/                            # 数据文件
│       ├── raw/                         # 上传的原始工单 Excel/CSV
│       ├── mock/                         # 外部预测结果 CSV
│       │   └── fault_prediction_results.csv  # ★ 新增：故障类型预测 mock 数据
│       └── knowledge/manuals/           # 维修手册知识库（.txt/.md）
├── frontend/
│   └── streamlit_app.py                 # Streamlit 前端（6 页面）
├── tests/                               # 测试（186 passed）
│   ├── test_agent_graph.py              # 路由 + 多轮对话冒烟测试
│   ├── test_agent_v03_graph.py          # 八节点端到端测试
│   ├── test_agent_v03_nodes.py          # 八节点单元测试
│   ├── test_agent_tools.py              # 工具注册与调用测试
│   ├── test_agent_fault_prediction.py   # ★ 新增：故障类型预测 Agent 集成测试
│   ├── test_services.py                 # 服务层测试
│   ├── test_llm_json.py                 # LLM JSON 解析测试
│   ├── test_rag_service.py              # RAG 服务测试
│   ├── test_fault_domain.py             # ★ 新增：领域层测试
│   ├── test_fault_prediction_adapter.py # ★ 新增：Adapter 层测试
│   ├── test_fault_prediction_schema.py  # ★ 新增：Schema 校验测试
│   ├── test_fault_prediction_service.py # ★ 新增：故障预测服务完整流程测试
│   └── test_text_integrity.py           # ★ 新增：文本完整性守护测试
├── scripts/
│   └── check_text_integrity.py           # ★ 新增：文本完整性检查脚本
├── docs/
│   ├── architecture.md                   # 系统架构文档
│   └── project-brief.md                  # 项目定位与面试讲解口径
├── task_plan.md                          # 任务计划（文本治理记录）
├── findings.md                           # 发现与决策记录
├── progress.md                           # 进度日志
├── encoding_guidelines.txt               # ★ 新增：编码规范三层约束指南
├── .editorconfig                         # ★ 新增：UTF-8 + LF 编辑器配置
├── .env.example                          # 环境变量模板
├── pytest.ini                            # Pytest 配置
├── requirements.txt                      # Python 依赖
└── README.md                             # 本文件
```

---

## 五、架构分层详解（v0.3.0 新增）

v0.3.0 引入了 **domain / schemas / adapters** 三层架构，实现关注点分离：

```
┌─────────────────────────────────────────────┐
│  API 层         agent_api.py / predict_api   │
├─────────────────────────────────────────────┤
│  Agent 层       graph.py / nodes / tools     │
├─────────────────────────────────────────────┤
│  Service 层     fault_prediction_service.py  │  ← 组装业务流程
├─────────────────────────────────────────────┤
│  Adapter 层     fault_prediction_adapter.py  │  ← 数据读取 + 清洗 + 校验
├─────────────────────────────────────────────┤
│  Schema 层      fault_prediction.py 等       │  ← Pydantic 业务 Schema
├─────────────────────────────────────────────┤
│  Domain 层      fault.py / risk.py / warning │  ← 纯业务规则（无 IO）
└─────────────────────────────────────────────┘
```

### 各层职责

| 层 | 职责 | 不负责 |
|----|------|--------|
| **Domain** | 故障枚举、风险计算公式、预警规则、概率校验 | IO、数据库、LLM 调用 |
| **Schemas** | Pydantic 数据校验、字段约束、兼容性转换 | 业务逻辑 |
| **Adapters** | 读取外部数据文件、清洗、转换、校验格式 | 组装业务流程 |
| **Services** | 组合 Adapter + Domain + Schema，完成完整业务用例 | 直接操作文件 IO |
| **Agent** | LangGraph 编排、工具注册、LLM 调用 | 具体业务计算 |

---

## 六、快速开始

### 1. 环境准备

```bash
cd 地铁AFVC

# 创建虚拟环境
python -m venv .venv
source .venv/Scripts/activate   # Git Bash
# 或 .venv\Scripts\activate    # CMD

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# LLM 配置（OpenAI 兼容接口，默认指向智谱）
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://openapi.zhipu.ai/v1
OPENAI_MODEL=zhipu-cheapest

# 是否启用 LLM 调用（false 时使用规则兜底）
AFVC_USE_LLM=true

# 可选：LangSmith 追踪
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_your_key
LANGSMITH_PROJECT=afc-riskops-agent
```

> **注意**：即使不配置 LLM（`AFVC_USE_LLM=false`）也能运行——Agent 每个 LLM 节点都有规则兜底 + 模板报告生成。所有测试默认禁用 LLM 调用。

### 3. 启动

```bash
# 终端 1：后端 API
uvicorn backend.main:app --reload

# 终端 2：前端 UI
streamlit run frontend/streamlit_app.py
```

### 4. 多轮对话示例

```
用户：帮我分析设备 1000029970
Agent：[返回完整诊断报告：设备信息 + 历史工单 + 6 窗口风险 + 预警 + 维修建议]
用户：那它为什么是橙色预警？
Agent：[自动关联设备 1000029970，返回预警原因解释]
用户：那应该先检查什么？
Agent：[自动关联设备 1000029970，返回维修 SOP：优先排查顺序 → 现场步骤 → 异常判定 → 处理动作]
用户：按维修手册说应该先查哪里？
Agent：[调用 RAG 检索维修手册，返回手册中的检查步骤和来源文件]
用户：未来 30 天最可能发生什么故障？
Agent：[返回故障类型预测：总体风险 + 条件概率 + 综合估计发生概率]
用户：换成 EX011115 呢？
Agent：[切换到 EX011115，返回新设备的完整分析]
```

### 5. 运行测试

```bash
# 运行全部测试（186 个）
pytest

# 按模块运行
pytest tests/test_services.py -q                   # 服务层
pytest tests/test_agent_tools.py -q                # 工具层
pytest tests/test_agent_v03_graph.py -q            # 八节点端到端
pytest tests/test_agent_v03_nodes.py -q            # 八节点单元
pytest tests/test_agent_fault_prediction.py -q     # 故障类型预测 Agent 集成
pytest tests/test_fault_prediction_service.py -q   # 故障预测服务
pytest tests/test_fault_domain.py -q               # 领域层
pytest tests/test_llm_json.py -q                   # JSON 解析
pytest tests/test_rag_service.py -q                # RAG 检索
pytest tests/test_text_integrity.py -q             # 文本完整性守护
```

> 测试默认禁用 LLM 调用（通过 monkeypatch），不依赖外部 API。

---

## 七、API 文档

### Agent 智能诊断

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/agent/diagnose` | **核心 API**：八节点 Agent 诊断，支持多轮对话 |

**请求体**：
```json
{
  "query": "帮我分析设备 1000029970",
  "session_id": "optional-session-id"
}
```

**响应体**（关键字段）：
```json
{
  "status": "success",
  "query": "帮我分析设备 1000029970",
  "route": "business_device",
  "business_goal": "full_diagnosis",
  "answer_mode": "evidence_based",
  "assetnum": "1000029970",
  "query_understanding": { "route": "business_device", "business_goal": "full_diagnosis", "confidence": 0.85 },
  "tool_plan": { "tool_calls": [...], "answer_mode": "evidence_based" },
  "tool_trace": [{ "tool": "get_integrated_analysis_tool", "status": "success", "duration_ms": 12.3 }],
  "evidence_packet": { "risk_prediction": {...}, "maintenance_advice": {...}, "fault_prediction": {...} },
  "final_answer": "【AFC 设备智能诊断报告】...",
  "session_id": "test-session-abc123",
  "last_assetnum": "1000029970"
}
```

### 其他 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/upload/workorders` | 上传工单文件（Excel/CSV） |
| `GET` | `/data/summary?top_n=10` | 工单数据概览 |
| `GET` | `/devices` | 设备列表 |
| `GET` | `/devices/{assetnum}/history?limit=50` | 设备历史工单 |
| `GET` | `/devices/high-risk?top_n=10` | 高风险设备 Top N |
| `GET` | `/predict/{assetnum}` | 单设备 6 窗口风险预测 |
| `GET` | `/predict/fault-type/{assetnum}?window_days=30&top_k=3` | ★ 新增：故障类型预测 |
| `GET` | `/advice/{assetnum}` | 维修建议 |
| `GET` | `/analysis/{assetnum}?history_limit=50` | 单设备综合分析 |

---

## 八、核心数据结构

### AgentState（LangGraph 图状态）

```python
class AfcAgentState(TypedDict, total=False):
    # 本轮流转变量的数据
    query: str                                  # 用户输入
    context_packet: dict                        # 跨轮上下文包
    query_understanding: dict                   # 问题理解结果
    tool_plan: dict                             # 工具调用计划（含 answer_mode）
    tool_results: dict                          # 工具执行结果
    tool_trace: list[dict]                      # 工具调用追踪
    evidence_packet: dict                       # 统一证据包
    evidence_evaluation: dict                   # 证据评估结果
    answer_policy: dict                         # 回答策略约束
    final_answer: str                           # 最终回答
    memory_update: dict                         # 记忆更新信息
    tool_loop_count: int                        # 工具循环计数
    errors: list[str]                           # 错误收集

    # 跨轮记忆（由 checkpointer 持久化）
    messages: list[BaseMessage]                 # 对话历史（最近 20 条）
    last_assetnum: str | None                   # 上一轮设备编号
    last_route: str | None                      # 上一轮路由
    last_business_goal: str | None              # 上一轮业务目标
    last_time_window: str | None                # 上一轮时间窗口
    last_tool_results_summary: dict             # 上一轮工具结果摘要
    last_evidence_summary: dict                 # 上一轮证据摘要
```

### EvidencePacket（统一证据包）

```python
class EvidencePacket(StrictModel):
    assetnum: str | None                        # 设备编号
    device_profile: dict | None                 # 设备档案信息
    history_summary: dict | None                # 历史工单摘要
    risk_prediction: dict | None                # 风险预测结果
    warning: dict | None                        # 预警等级信息
    maintenance_advice: dict | None             # 维修建议
    manual_evidence: list[dict] | None          # 手册检索结果
    fault_prediction: dict | None               # ★ 新增：故障类型预测
    data_overview: dict | None                  # 数据概览
    high_risk_devices: list[dict] | None        # 高风险设备列表
    sources: list[str]                          # 成功工具列表
    missing_evidence: list[str]                 # 缺失证据列表
    tool_errors: list[dict]                     # ★ 新增：工具错误列表
```

### 故障类型预测三层概率

```python
# FaultTypeScore — 单个故障类别的预测结果
class FaultTypeScore(BaseModel):
    fault_code: str                             # 故障代码，如 "TICKET_CARD"
    fault_name: str                             # 中文名称，如 "票卡处理异常"
    conditional_probability: float              # 条件概率 P(category | failure)
    estimated_occurrence_probability: float     # 综合估计 = overall_risk × conditional_probability
```

三个关键概率概念：
1. **overall_failure_risk**：预测窗口内发生任何故障工单的总体风险
2. **conditional_probability**：如果发生故障，属于某一类别的条件概率
3. **estimated_occurrence_probability**：`overall_failure_risk × conditional_probability`，该类别实际发生的综合估计

---

## 九、多轮对话机制

### 跨轮记忆由 LangGraph InMemorySaver 管理

| 能力 | 实现方式 | 示例 |
|------|---------|------|
| **指代消解** | `prepare_context` 传入 `active_assetnum`，LLM 识别代词后关联 | "那它风险高吗？" → 自动关联上一轮设备 |
| **设备切换** | `understand_query` 检测"换成""切换到"等模式 | "换成 EX011115 呢？" → 自动切换到新设备 |
| **上下文记忆** | `update_memory` 保存 `last_assetnum/route/business_goal` | 对话历史保留最近 20 条消息 |
| **工具摘要复用** | `last_tool_results_summary` 提供给后续轮次参考 | 追问时无需重新调用全部工具 |

### 记忆更新规则

| 本轮 route | last_assetnum 行为 |
|-----------|-------------------|
| `business_device` + 有 assetnum | 更新为该设备 |
| `business_global` | 清空（全局问题不绑定设备） |
| `needs_clarification` | 保持上一轮设备 |
| `direct_chat` / `capability_query` / `unsupported` | 保持上一轮设备 |

---

## 十、技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI + Uvicorn | API 服务 |
| 前端 | Streamlit | 6 页面交互式 UI |
| Agent 编排 | LangGraph | 八节点状态图 + 条件边 + InMemorySaver |
| Agent 工具 | LangChain Tools | 10 个 `@tool` 装饰的工具函数 |
| LLM | OpenAI-compatible API | 默认指向智谱，温度 parse=0.0 / report=0.3 |
| LLM JSON | 自研 `llm_json.py` | extract → json.loads → Pydantic → repair 四步 |
| RAG | 关键词匹配 + 段落切分 | 后续可升级向量数据库 |
| 数据校验 | Pydantic (StrictModel) | `extra="forbid"` 严格模式 |
| 数据处理 | Polars | CSV 读取与清洗 |
| 可观测 | LangSmith（可选） | LLM 调用追踪 |
| 文本检查 | 自研 `check_text_integrity.py` | UTF-8 / BOM / 私用区 / 乱码检测 |

---

## 十一、科学边界（硬约束）

1. `current_faildate` 表示工单记录时间，不一定等于物理故障发生时刻
2. **不能预测具体故障日期**，只能给出"未来 N 天约有 X% 概率再次产生故障工单"
3. 维修建议是巡检方向参考，**不是最终根因诊断结论**
4. RAG 检索的维修手册内容来自演示用示例文件，不能替代完整手册
5. 故障类型概率表示相对可能性，**不代表故障一定发生**
6. **禁止**把 `conditional_probability` 直接说成实际发生概率
7. **禁止**使用"一定发生""即将损坏"等确定性表述
8. 最终维修判断需结合现场检测、设备日志和人工经验

---

## 十二、文本完整性治理

项目已完成全量中文文本治理（6 阶段），建立了预防机制：

| 机制 | 文件 | 作用 |
|------|------|------|
| UTF-8 配置 | `.editorconfig` | 统一编辑器编码为 UTF-8 |
| 自动检查脚本 | `scripts/check_text_integrity.py` | 扫描 UTF-8 解码、BOM、私用区、乱码信号 |
| 测试守护 | `tests/test_text_integrity.py` | 每次 `pytest` 自动运行文本检查 |
| 编码指南 | `encoding_guidelines.txt` | 编辑器 + Git + PowerShell + Python 四层规范 |

运行检查：
```bash
python scripts/check_text_integrity.py   # 独立运行
pytest tests/test_text_integrity.py -q   # 随测试运行
```

---

## 十三、后续升级方向

| 模块 | 当前（v0.3.0） | 计划 |
|------|-------------|------|
| 预测模型 | Mock + CSV adapter | 接入真实 ML 模型训练 pipeline |
| Agent | 八节点 LLM-driven Tool Agent | tool-calling Agent + multi-agent 协作 |
| RAG | 关键词匹配 .txt/.md | 向量数据库 + embedding（ChromaDB / FAISS） |
| 工具去重 | 按 tool_name 去重 | 按 (tool_name, args_hash) 去重，支持多设备并行 |
| 数据存储 | 文件系统 | PostgreSQL / MySQL |
| 前端 | Streamlit 6 页面 | 可升级 React / Vue |
| 部署 | 本地开发 | Docker + 云部署 |
| 编码规范 | .editorconfig + 检查脚本 | CI 集成 + pre-commit hook |

---

## 十四、文档索引

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统架构、Agent 工作流、路由设计 |
| [docs/project-brief.md](docs/project-brief.md) | 项目定位、用户场景、面试讲解口径 |
| [task_plan.md](task_plan.md) | 任务计划与执行记录 |
| [findings.md](findings.md) | 问题发现与决策记录 |
| [progress.md](progress.md) | 分阶段进度日志 |
| [encoding_guidelines.txt](encoding_guidelines.txt) | 编码规范三层约束指南 |
