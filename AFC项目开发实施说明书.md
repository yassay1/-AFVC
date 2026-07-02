# AFC 项目开发实施说明书

> 面向 Claude Code / Codex 的开发实施主文档  
> 项目名称：**AFC 故障复发风险预测与智能维修建议系统**  
> 推荐简称：**AFC RiskOps Agent System**  
> 当前目标：基于真实 AFC 工单数据，完成一个可演示、可解释、可追踪的智能运维 Agent MVP。  
> 重要原则：**预测模型不是主讲重点，Agent 工程编排与工具调用闭环才是主线。**

---

## 0. 写给 AI 编程助手的执行说明

本文件不是逐行代码说明书，而是项目开发的主目标与实施约束。  
请根据本文件完成工程实现，但允许在具体代码组织、函数拆分、异常处理细节、UI 布局细节上做合理工程判断。

开发时需要遵守以下原则：

1. 不要把所有逻辑堆在 Streamlit 页面里；
2. 不要把 Agent 写成简单聊天接口；
3. 不要设计多个没有必要的子 Agent；
4. 不要让 LLM 编造风险值、设备信息、预警等级；
5. 不要把真实预测模型作为当前项目的唯一阻塞点；
6. 优先做出完整闭环，再优化页面、模型和 RAG；
7. 所有风险、预警、设备历史、维修建议都应来自工具或业务服务；
8. Agent 负责理解问题、选择工具、整合证据、生成报告；
9. LangSmith 用于记录 Agent 诊断链路，而不是事后装饰；
10. 项目必须能被面试演示：上传数据、查看高风险设备、分析单设备、使用 Agent 诊断。

---

## 1. 项目阶段定位

当前项目不是生产级成熟产品，而是：

> **面向面试演示和工程能力展示的 AFC 智能运维 Agent MVP。**

它要验证的核心闭环是：

```text
真实 AFC 工单数据
    ↓
数据读取与概览
    ↓
设备历史分析
    ↓
多时间窗口复发风险预测
    ↓
红橙黄绿预警
    ↓
维修建议
    ↓
Agent 调用工具并生成诊断报告
    ↓
LangSmith 追踪诊断过程
```

---

## 2. 用户视角：软件应该如何被使用

### 2.1 运维主管：查看今日巡检重点

用户问题：

```text
今天最需要优先巡检的 AFC 设备有哪些？
```

系统应支持：

- 读取当前最新工单数据；
- 生成高风险设备 Top N；
- 显示设备编号、车站、线路、品牌；
- 显示 7/14/21/30/60/90 天风险；
- 显示红橙黄绿预警；
- 给出建议巡检窗口。

---

### 2.2 维修人员：分析某台设备

用户问题：

```text
帮我分析设备 100023 未来一个月风险高不高，如果风险高应该先检查什么？
```

Agent 应完成：

- 识别设备编号；
- 理解“未来一个月”对应 30 天风险；
- 调用设备历史工具；
- 调用风险预测工具；
- 调用预警等级工具；
- 调用维修建议工具；
- 生成结构化诊断报告。

---

### 2.3 设备管理人员：解释预警原因

用户问题：

```text
为什么设备 100023 是红色预警？
```

Agent 应解释：

- 30 天风险是否超过红色阈值；
- 90 天风险是否超过红色阈值；
- 历史工单是否偏多；
- 近期工单密度是否偏高；
- 高频故障现象是什么；
- 建议巡检窗口是什么；
- 结论边界是什么。

---

## 3. 技术栈建议

### 3.1 后端

```text
FastAPI
Uvicorn
Pydantic
Polars
Fastexcel
Python-dotenv
```

### 3.2 前端

```text
Streamlit
Requests
Altair / Plotly（二选一，优先使用实现更顺手的）
```

### 3.3 Agent

```text
LangChain
LangGraph
LangSmith
OpenAI-compatible LLM client / 其他可用 LLM
```

### 3.4 Python 版本建议

优先建议：

```text
Python 3.12
```

如果当前项目环境已经是 Python 3.13，可以先尝试兼容。  
如果 LangChain、LangGraph、Polars、Fastexcel 等依赖安装或运行出现兼容问题，应回退到 Python 3.12。

---

## 4. 总体架构

```text
┌──────────────────────────────────────────────┐
│              Streamlit 前端展示层              │
│ 首页 / 数据上传 / 数据概览 / 高风险设备         │
│ 单设备分析 / Agent 诊断工作台                  │
└──────────────────────┬───────────────────────┘
                       │ HTTP REST API
                       ▼
┌──────────────────────────────────────────────┐
│                FastAPI API 层                 │
│ upload / data / devices / predict             │
│ advice / analysis / agent                     │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│           AFCDiagnosisAgent 编排层             │
│ LangGraph: parse → resolve → route            │
│ → execute tools → merge evidence → report     │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│              LangChain Tools 工具层            │
│ data / device / risk / warning / advice        │
│ analysis / high-risk                          │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│               Service 业务服务层               │
│ data_service / device_service                 │
│ prediction_service / warning_service          │
│ advice_service / analysis_service             │
│ model_adapter                                 │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                 数据与知识层                   │
│ backend/data/raw/       真实工单文件            │
│ backend/data/mock/      外部预测结果            │
│ backend/data/knowledge/ 后续维修知识库          │
└──────────────────────────────────────────────┘
```

---

## 5. 推荐目录结构

可以按以下目录组织。允许根据实际实现微调，但不要破坏分层思想。

```text
afc_fault_agent_system/
├── backend/
│   ├── main.py
│   ├── api/
│   │   ├── upload_api.py
│   │   ├── data_api.py
│   │   ├── device_api.py
│   │   ├── predict_api.py
│   │   ├── advice_api.py
│   │   ├── analysis_api.py
│   │   └── agent_api.py
│   │
│   ├── services/
│   │   ├── data_service.py
│   │   ├── device_service.py
│   │   ├── prediction_service.py
│   │   ├── warning_service.py
│   │   ├── advice_service.py
│   │   ├── analysis_service.py
│   │   └── model_adapter.py
│   │
│   ├── agent/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   ├── tools.py
│   │   ├── prompts.py
│   │   └── report_builder.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   └── llm.py
│   │
│   └── data/
│       ├── raw/
│       ├── mock/
│       └── knowledge/
│
├── frontend/
│   └── streamlit_app.py
│
├── docs/
│   ├── project_explanation.md
│   ├── architecture_design.md
│   └── implementation_plan.md
│
├── tests/
│   ├── test_services.py
│   ├── test_agent_tools.py
│   └── test_agent_graph.py
│
├── .env.example
├── requirements.txt
└── README.md
```

---

## 6. 数据字段规范

项目使用真实 AFC 工单数据。  
开发时不要假设字段一定完全干净，应先做数据探查和字段适配。

核心字段优先参考：

| 字段 | 含义 | 重要性 |
|---|---|---|
| assetnum | 设备编号 | 必需 |
| station_name | 车站名称 | 重要 |
| cust_linenum | 线路编号 | 重要 |
| current_faildate | 工单记录时间 | 必需 |
| prev_faildate | 上次故障时间 | 可选但重要 |
| total_failure_count | 累计故障次数 | 可选但重要 |
| description | 故障现象描述 | 必需 |
| cust_brand | 设备品牌 | 展示/分析 |
| cust_subsys | 所属子系统 | 展示/分析 |
| worktype | 工单类型 | 展示/分析 |
| pre_type / pre_value | 预防性维护字段 | 第一阶段不作为核心 |

### 6.1 字段处理原则

1. `assetnum` 缺失的记录不能用于单设备分析；
2. `current_faildate` 需要安全转换为时间类型；
3. `description` 缺失时可保留记录，但维修建议质量会下降；
4. 品牌、线路、子系统字段缺失时应显示为“未知”；
5. 不要把 `current_faildate` 解释为真实物理故障发生时刻，只能称为工单记录时间。

---

## 7. 后端 API 目标

### 7.1 健康检查

```text
GET /health
```

返回后端运行状态。

---

### 7.2 上传工单

```text
POST /upload/workorders
```

职责：

- 接收 Excel / CSV；
- 保存到 `backend/data/raw/`；
- 添加时间戳前缀；
- 返回保存路径、文件名、基本状态。

---

### 7.3 数据概览

```text
GET /data/summary?top_n=10
```

返回：

- 工单总数；
- 设备数量；
- 车站数量；
- 线路数量；
- 品牌数量；
- 时间范围；
- 品牌分布；
- 线路分布；
- 故障描述 Top N；
- 工单类型分布。

---

### 7.4 设备列表

```text
GET /devices
```

返回设备列表，建议按工单数量降序。

---

### 7.5 单设备历史

```text
GET /devices/{assetnum}/history?limit=50
```

返回指定设备历史工单，按时间倒序。

---

### 7.6 高风险设备

```text
GET /devices/high-risk?top_n=10
```

优先使用外部预测结果；没有外部预测结果时使用 Mock / baseline 预测。

---

### 7.7 单设备风险预测

```text
GET /predict/{assetnum}
```

返回：

```text
risk_7d
risk_14d
risk_21d
risk_30d
risk_60d
risk_90d
prediction_source
```

`prediction_source` 可取：

```text
external_model
baseline_mock
```

---

### 7.8 维修建议

```text
GET /advice/{assetnum}
```

返回：

- 故障现象类别；
- 可能原因；
- 检查方向；
- 备件建议；
- 依据字段或匹配关键词。

---

### 7.9 单设备综合分析

```text
GET /analysis/{assetnum}?history_limit=50
```

聚合：

- 设备基础信息；
- 历史工单摘要；
- 多时间窗口风险预测；
- 预警等级；
- 维修建议；
- 科学边界说明。

---

### 7.10 Agent 诊断

```text
POST /agent/diagnose
```

请求：

```json
{
  "query": "帮我分析设备 100023 未来一个月风险高不高，如果风险高应该先检查什么？"
}
```

返回建议包含：

```json
{
  "query": "...",
  "assetnum": "100023",
  "task_type": "risk_and_advice_query",
  "selected_tools": [],
  "tool_results": {},
  "final_answer": "...",
  "trace_id": "optional"
}
```

---

## 8. Service 层实施说明

### 8.1 data_service.py

职责：

- 自动查找最新上传的数据文件；
- 使用 Polars 读取 Excel / CSV；
- 输出 DataFrame；
- 提供数据概览；
- 处理字段缺失、时间转换、空值展示。

建议能力：

```text
get_latest_raw_file()
load_latest_workorders()
get_data_summary(top_n)
validate_core_fields()
```

注意：  
真实数据字段可能不完全符合预期，data_service 应该尽量稳健，而不是一遇到字段缺失就整体崩溃。

---

### 8.2 device_service.py

职责：

- 获取设备列表；
- 查询单设备历史工单；
- 生成设备基础信息；
- 支撑 Agent 设备编号校验。

建议能力：

```text
list_devices()
get_device_history(assetnum, limit)
get_device_profile(assetnum)
device_exists(assetnum)
```

---

### 8.3 prediction_service.py

职责：

- 提供单设备多时间窗口风险预测；
- 优先读取外部模型结果；
- 外部结果不存在时回退 baseline/mock；
- 返回预测来源。

建议保留两种模式：

```text
external_model mode
baseline_mock mode
```

baseline 不需要追求学术最优，只要合理、可解释、可演示。

---

### 8.4 model_adapter.py

职责：

- 读取 `backend/data/mock/prediction_results.csv`；
- 校验是否包含标准字段；
- 根据 assetnum 返回预测结果；
- 支持高风险设备排序。

标准字段建议：

```text
assetnum
risk_7d
risk_14d
risk_21d
risk_30d
risk_60d
risk_90d
```

---

### 8.5 warning_service.py

职责：

根据 30 天和 90 天风险值生成预警等级。

规则：

| 等级 | 条件 | 巡检窗口 |
|---|---|---|
| red | risk_30d ≥ 0.75 或 risk_90d ≥ 0.90 | 3～7 天内 |
| orange | risk_30d ≥ 0.55 或 risk_90d ≥ 0.75 | 7～14 天内 |
| yellow | risk_30d ≥ 0.35 或 risk_90d ≥ 0.55 | 14～30 天内 |
| green | 其他 | 常规周期 |

---

### 8.6 advice_service.py

职责：

- 根据设备历史 `description` 生成巡检建议；
- 第一阶段可使用关键词规则；
- 后续可接入 RAG 知识库；
- 输出时要明确这是“检查方向参考”。

可覆盖的故障类别：

```text
票卡处理异常
设备暂停服务
主控/显示异常
通信异常
通行控制异常
```

---

### 8.7 analysis_service.py

职责：

聚合以下结果：

```text
device_profile
device_history_summary
prediction_result
warning_result
maintenance_advice
boundary_notes
```

这是 Agent 最重要的工具来源之一。

---

## 9. Agent 设计：AFCDiagnosisAgent

### 9.1 设计结论

不做多子 Agent。  
采用：

```text
一个 AFCDiagnosisAgent
+ 一组 LangChain Tools
+ 一个 LangGraph 工作流
+ LangSmith Trace
```

### 9.2 Agent 职责

Agent 负责：

1. 解析用户问题；
2. 识别设备编号；
3. 判断任务类型；
4. 选择工具；
5. 调用工具；
6. 整合工具结果；
7. 生成诊断报告；
8. 输出边界说明；
9. 记录 LangSmith Trace。

Agent 不负责：

1. 训练预测模型；
2. 直接读取 Excel；
3. 直接操作 Polars；
4. 编造风险值；
5. 编造设备信息；
6. 代替现场根因诊断。

---

## 10. Agent State

建议状态结构：

```python
class AfcAgentState(TypedDict, total=False):
    query: str

    assetnum: str | None
    task_type: str | None
    time_window: str | None

    selected_tools: list[str]
    tool_results: dict

    evidence: dict

    final_answer: str
    trace_id: str | None
    errors: list[str]
```

实现时可根据 LangGraph 需要微调，但不要让状态变得过度复杂。

---

## 11. LangGraph 工作流

### 11.1 主流程

```text
START
  ↓
parse_question_node
  ↓
resolve_asset_node
  ↓
route_task_node
  ↓
execute_tools_node
  ↓
merge_evidence_node
  ↓
generate_report_node
  ↓
END
```

### 11.2 parse_question_node

第一版直接接 LLM。

职责：

- 从自然语言中提取 assetnum；
- 识别任务类型；
- 识别时间窗口；
- 输出结构化 JSON。

应支持的问题类型：

```text
data_overview
high_risk_ranking
full_diagnosis
risk_query
history_query
advice_query
risk_explanation
risk_and_advice_query
```

要求：

- LLM 只做解析；
- 解析失败时进入兜底逻辑；
- 不要让 LLM 在该节点生成诊断结论。

---

### 11.3 resolve_asset_node

职责：

- 如果任务是单设备相关，则校验 assetnum；
- 如果 assetnum 不存在，返回提示；
- 如果是全局任务，则跳过设备校验。

---

### 11.4 route_task_node

职责：

根据 task_type 选择工具。

示例：

```text
data_overview → get_data_summary_tool
high_risk_ranking → get_high_risk_devices_tool
full_diagnosis → get_integrated_analysis_tool
risk_query → predict_device_risk_tool + get_warning_level_tool
advice_query → get_maintenance_advice_tool
history_query → get_device_history_tool
risk_and_advice_query → history + predict + warning + advice
```

---

### 11.5 execute_tools_node

职责：

- 调用 LangChain Tools；
- 保存工具结果；
- 捕获异常；
- 记录 selected_tools。

---

### 11.6 merge_evidence_node

职责：

- 整理工具结果；
- 保留原始工具结果；
- 准备给报告生成节点使用；
- 明确证据来源。

---

### 11.7 generate_report_node

第一版直接接 LLM 生成报告。

但必须约束：

1. 风险值必须来自工具结果；
2. 预警等级必须来自 warning_service；
3. 设备信息必须来自 device_service；
4. 维修建议必须来自 advice_service 或 analysis_service；
5. 不能说“设备一定会故障”；
6. 不能说“根因已经确定”；
7. 必须包含科学边界说明。

---

## 12. LangChain Tools

建议在 `backend/agent/tools.py` 中封装。

工具列表：

```text
get_data_summary_tool
list_devices_tool
get_device_history_tool
predict_device_risk_tool
get_warning_level_tool
get_maintenance_advice_tool
get_integrated_analysis_tool
get_high_risk_devices_tool
```

工具实现可以调用 Service 层。  
不要在 Tool 内写太多业务逻辑。

---

## 13. LLM 接入设计

### 13.1 llm.py

建议在 `backend/core/llm.py` 中统一封装 LLM。

要求：

- 通过 `.env` 配置 API Key；
- 支持 OpenAI-compatible 接口；
- 不要在代码中硬编码 Key；
- 方便切换模型；
- 为 parse 和 report 分别保留调用入口。

`.env.example` 可包含：

```text
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
LANGSMITH_TRACING=
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=
```

### 13.2 Prompt 设计

`prompts.py` 中至少包含：

```text
QUESTION_PARSE_PROMPT
REPORT_GENERATION_PROMPT
```

QUESTION_PARSE_PROMPT 要求输出 JSON。  
REPORT_GENERATION_PROMPT 要求基于工具结果生成报告，不得编造数据。

---

## 14. LangSmith 接入

### 14.1 第一阶段目标

第一阶段至少完成 Trace。

记录：

- 用户问题；
- parse 输出；
- resolve 结果；
- route 结果；
- 工具调用；
- 工具返回；
- 最终报告。

### 14.2 后续评估目标

后续可增加 Dataset 和 Evaluation。

评估指标：

| 指标 | 说明 |
|---|---|
| 设备识别准确率 | assetnum 是否正确 |
| 任务分类准确率 | task_type 是否正确 |
| 工具调用正确率 | 是否调用合适工具 |
| 数值忠实度 | 报告风险值是否来自工具 |
| 预警忠实度 | 报告预警等级是否与工具一致 |
| 边界合规性 | 是否避免绝对化表述 |
| 报告完整性 | 是否包含历史、风险、预警、建议、边界 |

---

## 15. Streamlit 前端实施说明

前端页面建议：

```text
首页
数据上传
数据概览
高风险设备
单设备分析
Agent 诊断工作台
```

### 15.1 首页

展示：

- 项目定位；
- 系统流程；
- 当前阶段；
- 科学边界；
- 技术栈摘要。

---

### 15.2 数据上传

功能：

- 上传 Excel / CSV；
- 调用 `/upload/workorders`；
- 展示上传结果；
- 提示用户进入数据概览。

---

### 15.3 数据概览

功能：

- 调用 `/data/summary`；
- 展示指标卡片；
- 展示品牌、线路、故障描述、工单类型分布。

---

### 15.4 高风险设备

功能：

- 调用 `/devices/high-risk`；
- 支持选择 Top N；
- 展示风险值和预警等级；
- 支持跳转或复制设备编号用于 Agent 诊断。

---

### 15.5 单设备分析

功能：

- 选择或输入 assetnum；
- 调用 `/analysis/{assetnum}`；
- 展示设备信息、历史摘要、风险预测、预警、维修建议。

---

### 15.6 Agent 诊断工作台

不要只做聊天框。  
建议展示：

```text
用户问题输入
解析结果
任务类型
识别设备
调用工具列表
最终诊断报告
工具结果 JSON 展开区
LangSmith Trace 信息
```

---

## 16. 测试与验收标准

### 16.1 后端基础验收

- `/health` 正常；
- 可以上传真实工单；
- 可以读取最新上传文件；
- `/data/summary` 能返回概览；
- `/devices` 能返回设备列表；
- `/devices/{assetnum}/history` 能返回历史记录。

---

### 16.2 预测与预警验收

- `/predict/{assetnum}` 能返回 6 个时间窗口风险；
- 有外部预测 CSV 时优先使用外部结果；
- 无外部预测 CSV 时回退 baseline；
- `/devices/high-risk` 能返回排序结果；
- 预警等级规则正确。

---

### 16.3 Agent 验收

至少支持以下问题：

```text
这批工单整体情况怎么样？
当前高风险设备有哪些？
帮我分析设备 100023
设备 100023 未来 30 天风险高吗？
为什么设备 100023 是红色预警？
设备 100023 建议检查什么？
设备 100023 最近有哪些故障？
```

验收标准：

- 能识别设备编号；
- 能判断任务类型；
- 能调用正确工具；
- 报告能引用工具结果；
- 不编造风险数值；
- 不做绝对化故障判断；
- LangSmith 能看到调用链路。

---

## 17. 面试演示流程

推荐演示顺序：

```text
1. 启动 FastAPI 后端
2. 打开 Streamlit 前端
3. 上传真实 AFC 工单
4. 查看数据概览
5. 查看高风险设备列表
6. 选择一台红色/橙色预警设备
7. 查看单设备分析
8. 打开 Agent 诊断工作台
9. 输入：帮我分析设备 XXX 未来一个月风险高不高，如果风险高应该先检查什么？
10. 展示 Agent 解析结果、工具调用结果、最终报告
11. 展示 LangSmith Trace
12. 解释预测模型不是主线，Agent 工程编排和工具调用才是主线
```

---

## 18. 开发里程碑

### Milestone 1：工程骨架

目标：

- FastAPI 可启动；
- Streamlit 可启动；
- 目录结构完整；
- `.env.example` 完整；
- `/health` 可访问。

---

### Milestone 2：真实数据读取

目标：

- 支持上传真实工单；
- Polars 能读取最新文件；
- 字段校验和数据概览可用。

---

### Milestone 3：设备与分析服务

目标：

- 设备列表；
- 单设备历史；
- 单设备基础信息；
- 数据概览图表。

---

### Milestone 4：预测与预警

目标：

- Mock / baseline 预测；
- 外部预测 CSV 适配；
- 红橙黄绿预警；
- 高风险设备排序。

---

### Milestone 5：维修建议与综合分析

目标：

- 维修建议规则；
- 单设备综合分析；
- 维修建议边界说明。

---

### Milestone 6：LangChain Tools

目标：

- Service 封装为 Tools；
- Tool 输出结构稳定；
- 工具异常可控。

---

### Milestone 7：LangGraph Agent

目标：

- 完成 Agent State；
- 完成 6 个节点；
- 第一版直接接 LLM；
- `/agent/diagnose` 可用。

---

### Milestone 8：LangSmith

目标：

- 开启 Trace；
- 每次 Agent 调用可追踪；
- 前端展示 Trace 信息或运行 ID。

---

### Milestone 9：面试演示优化

目标：

- 页面顺序顺畅；
- 演示数据稳定；
- 准备 5～7 个固定问题；
- 准备异常兜底截图或说明；
- README 完整。

---

## 19. 给 Claude Code / Codex 的开发约束

请在开发时遵守：

1. 保持架构分层；
2. 不把业务逻辑写进前端；
3. 不让 Agent 直接读文件；
4. 不让 LLM 编造工具结果；
5. 保留工具调用结果；
6. Agent 报告要包含边界说明；
7. 外部模型结果优先，baseline 兜底；
8. 保持接口返回结构清晰；
9. 保证项目能本地启动；
10. 代码实现可以灵活，但不要偏离项目主线。

---

## 20. 最终交付目标

项目最终应达到：

```text
用户可以上传真实 AFC 工单；
系统可以展示数据概览和高风险设备；
系统可以对单设备进行风险预测和预警；
系统可以生成维修检查建议；
Agent 可以理解自然语言问题；
Agent 可以调用工具生成诊断报告；
LangSmith 可以追踪 Agent 调用链路；
项目可以用于面试演示和技术讲解。
```

一句话总结：

> 本项目不是为了证明预测模型多强，而是为了证明你能把真实工单数据、预测结果、预警规则、维修建议和 LLM Agent 编排成一个可解释、可追踪、可演示的智能运维系统。
