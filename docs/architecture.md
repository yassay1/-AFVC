# AFC RiskOps Agent System — 架构设计文档

> 面向地铁 AFC 设备的智能运维系统架构设计。
> 核心原则：**一个中心诊断 Agent + 多个业务工具 + LangGraph 状态流 + LangSmith 可观测性**。

---

## 1. 总体架构

```
Streamlit 前端 (6 页面)
    ↓ HTTP REST API
FastAPI API 层 (7 路由)
    ↓
AFCDiagnosisAgent (LangGraph, 6 节点)
    ↓ 调用 LangChain Tools
LangChain Tools (8 个工具)
    ↓ 封装业务服务
Service 业务服务层 (7 服务)
    ↓ 读取文件
数据与知识层 (工单 / 预测结果 / 知识库)
```

### 各层职责

| 层级 | 负责 | 不负责 |
|------|------|--------|
| Streamlit | 页面导航、上传、图表展示、Agent 交互 | 复杂业务逻辑、Agent 编排 |
| FastAPI | 接收请求、参数校验、调用 Service/Agent | 业务计算、文件读取 |
| Agent | 问题解析、设备识别、工具选择、证据整合、报告生成 | 训练模型、读 Excel、编造数据 |
| Tools | 封装 Service 为 Agent 可调用的标准接口 | 业务逻辑实现 |
| Service | 稳定、可测试的业务逻辑 | 前端展示、Agent 编排 |
| Data | 存储原始工单、预测结果、知识库 | — |

---

## 2. Agent 工作流

```
START → parse_question → resolve_asset → route_task
      → execute_tools → merge_evidence → generate_report → END
```

### 节点说明

| 节点 | 职责 | 关键输出 |
|------|------|---------|
| parse_question | LLM/规则提取 assetnum、task_type、time_window | 结构化解析 JSON |
| resolve_asset | 校验设备是否存在 | asset_exists |
| route_task | 按 task_type 选择工具 | selected_tools |
| execute_tools | 调用工具，捕获异常 | tool_results |
| merge_evidence | 整理工具结果为结构化证据 | evidence + sources |
| generate_report | LLM/模板生成诊断报告 | final_answer |

### 条件分支

- 全局问题（data_overview / high_risk_ranking）→ 跳过设备校验
- 设备不存在 → 跳过工具调用，直接生成错误报告
- 设备存在 → 正常路由 → 工具调用 → 报告

### 多轮对话支持

- LangGraph InMemorySaver checkpointer 持久化状态
- 指代词检测（"它"、"这个设备"、"刚才那个"）→ 继承上一轮设备
- 设备切换词检测（"换成 XXX"、"切换到 XXX"）→ 更新设备
- 全局问题不继承设备上下文

---

## 3. Agent State

```python
class AfcAgentState(TypedDict, total=False):
    query: str                          # 用户输入
    assetnum: Optional[str]             # 识别的设备编号
    task_type: Optional[str]            # 任务类型
    time_window: Optional[str]          # 时间窗口
    asset_exists: Optional[bool]        # 设备存在性
    selected_tools: list[str]          # 选中工具
    tool_results: dict[str, Any]       # 工具结果
    evidence: dict[str, Any]           # 整合证据
    final_answer: str                  # 最终报告
    errors: list[str]                  # 异常记录
    messages: list[BaseMessage]        # 对话历史
    last_assetnum: Optional[str]       # 上一轮设备
    last_task_type: Optional[str]      # 上一轮任务
```

---

## 4. 任务类型与工具路由

| task_type | 示例问题 | 调用工具 |
|-----------|---------|---------|
| data_overview | "这批工单整体情况怎么样？" | data_summary |
| high_risk_ranking | "当前高风险设备有哪些？" | high_risk_devices |
| full_diagnosis | "帮我分析设备 100023" | integrated_analysis |
| risk_query | "设备 100023 未来 30 天风险高吗？" | predict_device_risk |
| advice_query | "设备 100023 建议检查什么？" | maintenance_advice |
| history_query | "设备 100023 最近有哪些故障？" | device_history |
| risk_explanation | "为什么设备 100023 是红色预警？" | predict + advice |
| risk_and_advice_query | "风险高不高，应该检查什么？" | history + predict + advice |

---

## 5. 工具层

### 工具列表

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

**设计原则：** 工具只做薄封装，业务逻辑全在 Service 层。

---

## 6. Service 层

| 服务 | 职责 |
|------|------|
| data_service.py | 读取工单文件、数据概览、字段校验 |
| device_service.py | 设备列表、单设备历史、设备信息 |
| prediction_service.py | 多时间窗口风险预测（Mock + 外部模型） |
| warning_service.py | 红橙黄绿预警等级 |
| advice_service.py | 关键词规则维修建议 |
| analysis_service.py | 聚合：设备信息 + 历史 + 风险 + 预警 + 建议 |
| model_adapter.py | 外部预测 CSV 读写适配 |

---

## 7. 预警规则

| 等级 | 条件 | 巡检窗口 |
|------|------|---------|
| 🔴 红色 | risk_30d ≥ 0.75 或 risk_90d ≥ 0.90 | 3～7 天 |
| 🟠 橙色 | risk_30d ≥ 0.55 或 risk_90d ≥ 0.75 | 7～14 天 |
| 🟡 黄色 | risk_30d ≥ 0.35 或 risk_90d ≥ 0.55 | 14～30 天 |
| 🟢 绿色 | 其他 | 常规周期 |

---

## 8. 预测模型双模式

| 模式 | 来源 | 触发条件 |
|------|------|---------|
| external_model | `backend/data/mock/prediction_results.csv` | CSV 存在且设备在其中 |
| baseline_mock | 规则引擎（工单数 + 近期密度 + 平均间隔） | 无外部结果时兜底 |

---

## 9. 目录结构

```
afc_fault_agent_system/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── api/                  # 7 个 API 路由
│   ├── agent/                # LangGraph 编排 (state/graph/nodes/tools/prompts/report_builder)
│   ├── services/             # 7 个业务服务 + 模型适配器
│   ├── core/                 # config.py + llm.py
│   └── data/                 # raw/ + mock/ + knowledge/
├── frontend/
│   └── streamlit_app.py      # 6 页 Streamlit 前端
├── tests/                    # 93 个测试用例
├── docs/                     # 架构 + 项目说明
├── .env.example
├── requirements.txt
└── README.md
```

---

## 10. 科学边界

1. `current_faildate` 是工单记录时间，不等于物理故障发生时刻
2. 风险预测表示未来窗口内再次产生故障工单的风险，不等于精确预测故障日期
3. 维修建议是巡检方向参考，不是最终根因诊断结论
4. 最终判断需结合现场检测、设备日志和人工经验

---

## 11. 报告结构

```
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

## 12. 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | Streamlit |
| Agent | LangGraph + LangChain Tools |
| LLM | OpenAI-compatible (智谱 GLM-4-Flash) |
| 数据处理 | Polars + Pandas |
| 图表 | Altair |
| 可观测 | LangSmith (可选) |
| 数据校验 | Pydantic |
