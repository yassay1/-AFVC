# AFC 系统架构与 Agent 架构设计

> 本文件用于作为开发主目标参考，统一系统分层、目录结构、数据流、API 设计、Agent 工作流和 LangSmith 观测设计。  
> 设计原则：**一个中心诊断 Agent + 多个业务工具 + LangGraph 状态流 + LangSmith 可观测性**。

---

## 1. 总体架构

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
│ upload_api / data_api / device_api            │
│ predict_api / advice_api / analysis_api       │
│ agent_api                                     │
└──────────────────────┬───────────────────────┘
                       │ 调用业务服务或 Agent
                       ▼
┌──────────────────────────────────────────────┐
│             LangGraph Agent 编排层             │
│ AFCDiagnosisAgent                             │
│ parse → resolve → route → execute → merge     │
│ → report                                      │
└──────────────────────┬───────────────────────┘
                       │ 调用 LangChain Tools
                       ▼
┌──────────────────────────────────────────────┐
│              LangChain Tool 工具层             │
│ data_summary_tool                             │
│ device_history_tool                           │
│ risk_prediction_tool                          │
│ warning_level_tool                            │
│ maintenance_advice_tool                       │
│ integrated_analysis_tool                      │
│ high_risk_devices_tool                        │
└──────────────────────┬───────────────────────┘
                       │ 封装业务服务
                       ▼
┌──────────────────────────────────────────────┐
│                Service 业务服务层              │
│ data_service / device_service                 │
│ prediction_service / warning_service          │
│ advice_service / analysis_service             │
│ model_adapter                                 │
└──────────────────────┬───────────────────────┘
                       │ 读取文件 / 外部模型结果
                       ▼
┌──────────────────────────────────────────────┐
│                 数据与知识层                   │
│ backend/data/raw/      原始工单文件             │
│ backend/data/mock/     外部预测结果 CSV         │
│ backend/data/knowledge 后续维修知识库           │
└──────────────────────────────────────────────┘
```

---

## 2. 各层职责

### 2.1 Streamlit 前端展示层

负责：

- 页面导航；
- 文件上传；
- 表格和图表展示；
- 设备选择；
- Agent 诊断问题输入；
- 展示工具调用轨迹；
- 展示最终诊断报告。

不负责：

- 复杂业务逻辑；
- 风险预测计算；
- 直接读取原始文件；
- Agent 工具调用编排。

---

### 2.2 FastAPI API 层

负责：

- 接收前端请求；
- 参数校验；
- 调用 Service 或 Agent；
- 返回 JSON 结果；
- 自动生成 OpenAPI 文档。

推荐 API：

```text
GET  /health
POST /upload/workorders
GET  /data/summary
GET  /devices
GET  /devices/{assetnum}/history
GET  /devices/high-risk
GET  /predict/{assetnum}
GET  /advice/{assetnum}
GET  /analysis/{assetnum}
POST /agent/diagnose
```

---

### 2.3 LangGraph Agent 编排层

负责：

- 用户问题解析；
- 设备编号识别；
- 任务类型判断；
- 工具选择；
- 工具调用顺序控制；
- 工具结果整合；
- 诊断报告生成；
- 诊断边界说明；
- LangSmith 追踪。

不负责：

- 训练预测模型；
- 直接读取 Excel；
- 直接操作 Polars DataFrame；
- 编造风险值和设备信息。

---

### 2.4 LangChain Tool 工具层

负责把业务服务封装成 Agent 可以调用的工具。

工具示例：

```text
get_data_summary_tool
get_device_history_tool
predict_device_risk_tool
get_warning_level_tool
get_maintenance_advice_tool
get_integrated_analysis_tool
get_high_risk_devices_tool
```

工具层的作用：

> 隔离 Agent 与业务服务，让 Agent 只通过标准工具访问业务能力。

---

### 2.5 Service 业务服务层

负责稳定、可测试、可复用的业务逻辑。

| 服务 | 职责 |
|---|---|
| data_service.py | 读取工单文件、生成数据概览 |
| device_service.py | 设备列表、单设备历史工单 |
| prediction_service.py | 多时间窗口复发风险预测 |
| warning_service.py | 红橙黄绿预警等级生成 |
| advice_service.py | 维修建议生成 |
| analysis_service.py | 聚合历史、预测、预警、建议 |
| model_adapter.py | 外部模型预测结果适配 |

---

### 2.6 数据与知识层

当前 MVP：

```text
backend/data/raw/    上传的原始工单文件
backend/data/mock/   外部预测结果 prediction_results.csv
```

后续升级：

```text
PostgreSQL / MySQL
Redis
Chroma / FAISS / pgvector
维修手册知识库
历史维修案例库
```

---

## 3. 为什么采用“一个 Agent + 多工具”设计？

不采用多子 Agent 的原因：

1. 当前任务链路清楚：解析问题 → 调工具 → 生成报告；
2. 多 Agent 会带来额外 Prompt、状态同步和调试成本；
3. 业务服务本身已经拆分清楚，不需要再包装成多个子 Agent；
4. 工业运维场景更需要稳定、可追踪、可解释，而不是自由协作式 Agent；
5. 一个中心 Agent 更容易开发、演示和面试讲解。

最终设计：

```text
AFCDiagnosisAgent
    ├── LangGraph 状态流
    ├── LangChain 工具调用
    ├── Service 业务能力
    └── LangSmith 追踪评估
```

---

## 4. Agent 工作流设计

### 4.1 工作流总览

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

---

### 4.2 节点 1：parse_question_node

职责：

- 解析用户问题；
- 提取设备编号；
- 提取时间窗口；
- 判断用户大概意图。

输入示例：

```text
帮我分析设备 100023 未来一个月风险高不高，如果风险高应该先检查什么？
```

输出示例：

```json
{
  "assetnum": "100023",
  "task_type": "risk_and_advice_query",
  "time_window": "30d"
}
```

---

### 4.3 节点 2：resolve_asset_node

职责：

- 检查设备编号是否存在；
- 如果用户没有输入设备编号，则判断是否为全局问题；
- 如果设备不存在，返回错误或提示用户重新输入。

调用工具：

```text
list_devices_tool
```

---

### 4.4 节点 3：route_task_node

职责：

根据任务类型决定调用哪些工具。

| 任务类型 | 调用工具 |
|---|---|
| data_overview | get_data_summary_tool |
| high_risk_ranking | get_high_risk_devices_tool |
| history_query | get_device_history_tool |
| risk_query | predict_device_risk_tool + get_warning_level_tool |
| advice_query | get_maintenance_advice_tool |
| full_diagnosis | get_integrated_analysis_tool |
| risk_and_advice_query | predict + warning + advice + history |

---

### 4.5 节点 4：execute_tools_node

职责：

- 按路由结果调用工具；
- 捕获工具异常；
- 记录工具调用结果；
- 将结果写入 AgentState。

示例工具结果：

```json
{
  "prediction": {
    "risk_7d": 0.22,
    "risk_14d": 0.35,
    "risk_30d": 0.78,
    "risk_60d": 0.86,
    "risk_90d": 0.91
  },
  "warning": {
    "level": "红色预警",
    "inspection_window": "3～7 天内"
  }
}
```

---

### 4.6 节点 5：merge_evidence_node

职责：

- 把工具返回 JSON 整理成报告依据；
- 明确哪些数据来自哪个工具；
- 防止后续报告生成时丢失关键信息。

证据结构：

```json
{
  "device_info": {},
  "history_summary": {},
  "risk_prediction": {},
  "warning_result": {},
  "maintenance_advice": {},
  "evidence_sources": [
    "device_history_tool",
    "predict_device_risk_tool",
    "warning_level_tool",
    "maintenance_advice_tool"
  ]
}
```

---

### 4.7 节点 6：generate_report_node

职责：

- 使用 LLM 或模板生成最终诊断报告；
- 报告必须基于工具结果；
- 风险值、预警等级、设备信息不能编造。

报告结构：

```text
【AFC 设备智能诊断报告】

一、设备识别结果
二、历史工单摘要
三、多时间窗口复发风险
四、预警等级与原因
五、维修与巡检建议
六、工具调用记录
七、科学边界说明
```

---

## 5. Agent State 设计

建议定义：

```python
from typing import TypedDict, Optional, Any

class AfcAgentState(TypedDict, total=False):
    # 用户输入
    query: str

    # 解析结果
    assetnum: Optional[str]
    task_type: Optional[str]
    time_window: Optional[str]

    # 工具选择与调用
    selected_tools: list[str]
    tool_results: dict[str, Any]

    # 证据整合
    evidence: dict[str, Any]

    # 输出结果
    final_answer: str

    # 可观测与异常
    trace_id: Optional[str]
    errors: list[str]
```

设计原则：

1. 状态不要太复杂；
2. 每个节点只读写自己负责的字段；
3. 工具结果必须保留；
4. 最终报告必须能追溯到工具结果。

---

## 6. 工具设计

### 6.1 数据概览工具

```python
@tool
def get_data_summary(top_n: int = 10) -> dict:
    """获取 AFC 工单数据概览，包括工单总数、设备数、车站数、线路数、品牌分布等。"""
```

---

### 6.2 设备历史工具

```python
@tool
def get_device_history(assetnum: str, limit: int = 50) -> dict:
    """查询指定 AFC 设备的历史故障工单。"""
```

---

### 6.3 风险预测工具

```python
@tool
def predict_device_risk(assetnum: str) -> dict:
    """预测指定 AFC 设备未来 7/14/21/30/60/90 天再次产生故障工单的风险。"""
```

---

### 6.4 预警等级工具

```python
@tool
def get_warning_level(risk_30d: float, risk_90d: float) -> dict:
    """根据 30 天和 90 天风险值生成红橙黄绿预警等级。"""
```

---

### 6.5 维修建议工具

```python
@tool
def get_maintenance_advice(assetnum: str) -> dict:
    """根据设备历史故障描述生成维修与巡检建议。"""
```

---

### 6.6 综合分析工具

```python
@tool
def get_integrated_analysis(assetnum: str) -> dict:
    """聚合设备基础信息、历史工单、风险预测、预警等级和维修建议。"""
```

---

### 6.7 高风险设备工具

```python
@tool
def get_high_risk_devices(top_n: int = 10) -> dict:
    """获取当前高风险 AFC 设备列表。"""
```

---

## 7. Agent 任务类型

建议支持以下任务类型：

| task_type | 用户问题示例 | 工具调用 |
|---|---|---|
| data_overview | 这批工单整体情况怎么样？ | data_summary |
| high_risk_ranking | 今天优先巡检哪些设备？ | high_risk_devices |
| full_diagnosis | 帮我分析设备 100023 | integrated_analysis |
| risk_query | 设备 100023 未来 30 天风险高吗？ | predict + warning |
| advice_query | 设备 100023 建议检查什么？ | advice |
| history_query | 设备 100023 最近有哪些故障？ | history |
| risk_and_advice_query | 未来一个月风险高不高，应该检查什么？ | history + predict + warning + advice |

---

## 8. 前端页面设计

Streamlit 页面建议保持 6 个：

```text
1. 首页
2. 数据上传
3. 数据概览
4. 高风险设备
5. 单设备分析
6. Agent 诊断工作台
```

其中 Agent 页面不要只做普通聊天框，而要做成诊断工作台：

```text
用户问题输入区
        ↓
任务解析结果展示
        ↓
工具调用轨迹展示
        ↓
Agent 最终诊断报告
        ↓
工具结果 JSON 展开区
        ↓
LangSmith Trace ID 展示区
```

---

## 9. 项目目录结构

推荐目录：

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
│   └── agent_design.md
│
├── tests/
│   ├── test_services.py
│   ├── test_agent_tools.py
│   └── test_agent_graph.py
│
└── requirements.txt
```

---

## 10. LangSmith 设计

### 10.1 Trace

记录每次诊断的完整链路：

```text
用户问题
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
最终回答
```

Trace 中重点观察：

- 设备编号是否识别正确；
- 任务类型是否判断正确；
- 工具调用是否正确；
- 工具返回是否正常；
- 最终报告是否忠实使用工具结果。

---

### 10.2 Dataset

准备 10～20 条测试问题：

```text
帮我分析设备 100023
设备 100023 未来 30 天风险高吗？
为什么设备 100023 是红色预警？
现在高风险设备有哪些？
设备 100023 建议检查什么？
这批工单整体情况怎么样？
```

---

### 10.3 Evaluation

评估指标：

| 指标 | 说明 |
|---|---|
| 设备识别准确率 | 是否正确识别 assetnum |
| 任务分类准确率 | 是否正确判断 task_type |
| 工具调用正确率 | 是否调用正确工具 |
| 数值忠实度 | 报告风险值是否与工具结果一致 |
| 预警忠实度 | 预警等级是否与 warning_service 一致 |
| 边界合规性 | 是否避免“必然故障”“确定根因”等表述 |
| 报告完整性 | 是否包含历史、风险、预警、建议和边界说明 |

---

## 11. 第一阶段开发顺序

建议按以下顺序开发：

```text
1. 搭建 FastAPI 后端骨架
2. 实现 data_service 和 upload_api
3. 实现 device_service
4. 实现 prediction_service + model_adapter
5. 实现 warning_service
6. 实现 advice_service
7. 实现 analysis_service
8. 实现 LangChain Tools
9. 实现 AfcAgentState
10. 实现 LangGraph 节点
11. 实现 /agent/diagnose
12. 实现 Streamlit Agent 诊断工作台
13. 接入 LangSmith Trace
```

---

## 12. 面试讲解口径

可以这样讲：

> 我这个项目没有把 Agent 设计成很多子代理，因为 AFC 运维诊断的任务链路比较清楚，更适合一个中心诊断 Agent 加多个业务工具。  
>  
> 我使用 LangGraph 编排 Agent 的状态流，包括问题解析、设备识别、任务路由、工具调用、证据整合和报告生成。底层的数据概览、设备历史、风险预测、预警等级和维修建议都封装成 LangChain Tools。  
>  
> 预测模型不是 Agent 的重点，它只是 `predict_device_risk_tool` 的能力来源。Agent 的重点是根据用户问题选择合适工具，整合工单数据、预测结果和维修建议，生成可解释的诊断报告。  
>  
> 同时我接入 LangSmith，对每次诊断进行 Trace 和评估，保证工具调用过程可观测，报告中的风险数值和预警结论可追溯。

---

## 13. 最终设计原则

1. **不要为了复杂而复杂**：不做多 Agent 军团；
2. **业务服务先稳定**：data/device/predict/warning/advice/analysis 先跑通；
3. **Agent 只通过工具访问业务能力**；
4. **LangGraph 负责流程控制，不负责炫技**；
5. **预测模型只是工具，不是项目主讲重点**；
6. **报告必须基于工具结果，不能让 LLM 编造数据**；
7. **LangSmith 用于证明系统可追踪、可解释、可评估**。

---

## 14. 架构最终结论

```text
Streamlit 前端
    ↓
FastAPI API
    ↓
AFCDiagnosisAgent（LangGraph）
    ↓
LangChain Tools
    ↓
Service 业务服务
    ↓
工单数据 / 外部预测结果 / 维修知识库
```

一句话总结：

> 本项目的 Agent 不是替代预测模型，而是把设备历史、复发风险、预警等级和维修建议组织成用户能直接使用的运维诊断报告，并且全过程可追踪、可解释、可评估。
