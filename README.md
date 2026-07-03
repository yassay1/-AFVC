# 🚇 AFC 故障复发风险预测与智能维修建议系统

面向地铁 AFC（自动售检票）设备的智能运维系统。基于真实故障工单数据，通过 **LangGraph Agent + LangChain Tools** 编排，预测设备复发风险、生成红橙黄绿预警，并提供可解释的诊断报告。

> **项目定位**：面试演示型 MVP，重点在 Agent 工程编排与工具调用闭环，而非预测模型训练。
> **v0.2.1 更新**：支持多轮对话（LangGraph checkpointer + InMemorySaver），默认接入真实工单数据。

[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.139-green)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/langgraph-1.2.7-orange)](https://langchain-ai.github.io/langgraph/)
[![Tests](https://img.shields.io/badge/tests-93%20passed-brightgreen)](tests/)

---

## 项目结构

```
afc_fault_agent_system/
├── backend/
│   ├── main.py                     # FastAPI 入口
│   ├── api/                        # API 路由层
│   │   ├── upload_api.py           # 工单上传
│   │   ├── data_api.py             # 数据概览
│   │   ├── device_api.py           # 设备管理
│   │   ├── predict_api.py          # 风险预测
│   │   ├── advice_api.py           # 维修建议
│   │   ├── analysis_api.py         # 综合分析
│   │   └── agent_api.py            # Agent 诊断 (LangGraph)
│   ├── agent/                      # Agent 编排层 ★
│   │   ├── state.py                # AfcAgentState 定义
│   │   ├── tools.py                # 8 个 LangChain Tools
│   │   ├── prompts.py              # LLM Prompt 模板
│   │   ├── nodes.py                # 6 个 LangGraph 节点
│   │   ├── graph.py                # 工作流编排 + 入口
│   │   └── report_builder.py       # 报告生成器（模板兜底）
│   ├── services/                   # 业务服务层
│   │   ├── data_service.py         # 工单数据读取
│   │   ├── device_service.py       # 设备查询
│   │   ├── prediction_service.py   # 风险预测
│   │   ├── warning_service.py      # 预警等级
│   │   ├── advice_service.py       # 维修建议
│   │   ├── analysis_service.py     # 综合分析
│   │   └── model_adapter.py        # 外部模型适配
│   ├── core/                       # 核心配置
│   │   ├── config.py               # 环境变量
│   │   └── llm.py                  # LLM 统一封装
│   └── data/                       # 数据文件
│       ├── raw/                    # 上传的原始工单
│       ├── mock/                   # 外部预测结果 CSV
│       └── knowledge/              # 后续知识库
├── frontend/
│   └── streamlit_app.py            # Streamlit 前端（6 页面）
├── tests/
│   ├── test_services.py            # Service 层测试（22 用例）
│   ├── test_agent_tools.py         # Tools 层测试（16 用例）
│   └── test_agent_graph.py         # Agent 工作流测试（35 用例）
├── docs/                           # 参考文档
├── .env.example                    # 环境变量模板
├── requirements.txt
└── README.md
```

---

## 架构

```
Streamlit 前端 (6 页面)
    ↓ HTTP REST API
FastAPI API 层
    ↓
AFCDiagnosisAgent (LangGraph)
    ├── parse_question_node  ── LLM / 规则兜底
    ├── resolve_asset_node   ── 设备校验
    ├── route_task_node      ── 7 种任务类型 → 工具选择
    ├── execute_tools_node   ── 调用 LangChain Tools
    ├── merge_evidence_node  ── 证据整合
    └── generate_report_node ── LLM / 模板兜底
         ↓
LangChain Tools (8 个)
    ↓
Service 层 (7 个业务服务)
    ↓
工单数据 / 预测结果 CSV
```

### 设计原则

- **只有一个 `AFCDiagnosisAgent`**，不做多子 Agent
- **Agent 只通过 Tools 访问业务能力**，不直接读文件/操作 DataFrame
- **LLM 只负责解析问题和生成报告**，风险值/预警/设备信息必须来自工具结果
- **外挂模型适配器**，Mock 预测和真实模型用同一接口

---

## 快速开始

### 1. 环境准备

```bash
cd afc_fault_agent_system

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
OPENAI_API_KEY=sk-your-key-here       # 必需：LLM API Key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# 可选：LangSmith 追踪
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_your_key
LANGSMITH_PROJECT=afc-riskops-agent
```

> **注意**：不配置 LLM 也能运行——Agent 会自动使用规则兜底 + 模板生成报告。

### 3. 启动

```bash
# 终端 1：后端
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# 终端 2：前端
streamlit run frontend/streamlit_app.py
```

- 后端 API 文档：http://127.0.0.1:8000/docs
- 前端页面：http://localhost:8501

### 4. 使用流程

```
1. 打开 Streamlit → 数据上传 → 上传 AFC 工单 Excel（可选，已有默认数据）
2. 数据概览 → 查看 19994 条工单统计
3. 高风险设备 → 查看 Top N 预警设备
4. 单设备分析 → 选择设备查看完整分析
5. Agent 诊断工作台 → 自然语言提问，支持多轮连续对话
```

### 5. 多轮对话

Agent 工作台支持连续对话，Agent 自动记住上一轮的设备编号：

```
用户：帮我分析设备 1000029970
Agent：[返回设备分析报告]
用户：那它为什么是橙色预警？
Agent：[自动关联设备 1000029970，返回预警解释]
用户：那应该先检查什么？
Agent：[自动关联设备 1000029970，返回维修建议]
用户：换成 EX011115 呢？
Agent：[切换到 EX011115，返回新设备分析]
用户：那它最近有哪些故障？
Agent：[自动关联设备 EX011115，返回历史工单]
```

支持的指代词：`它`、`这个设备`、`该设备`、`刚才那个`、`这台`、`那它`、`那应该`
支持的切换词：`换成XXX`、`改成XXX`、`切换到XXX`

点击 **🆕 新建会话** 可清除对话历史重新开始。

---

## API 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/upload/workorders` | 上传工单文件 |
| `GET` | `/data/summary?top_n=10` | 数据概览 |
| `GET` | `/devices` | 设备列表 |
| `GET` | `/devices/{assetnum}/history?limit=50` | 设备历史工单 |
| `GET` | `/devices/high-risk?top_n=10` | 高风险设备 Top N |
| `GET` | `/predict/{assetnum}` | 单设备风险预测 |
| `GET` | `/advice/{assetnum}` | 维修建议 |
| `GET` | `/analysis/{assetnum}?history_limit=50` | 单设备综合分析 |
| `POST` | `/agent/diagnose` | Agent 智能诊断 (LangGraph) |

---

## Agent 支持的问题类型

| 类型 | 示例 | 调用工具 |
|------|------|----------|
| `data_overview` | "这批工单整体情况怎么样？" | data_summary |
| `high_risk_ranking` | "当前高风险设备有哪些？" | high_risk_devices |
| `full_diagnosis` | "帮我分析设备 1000029970" | integrated_analysis |
| `risk_query` | "设备 1000029970 未来 30 天风险高吗？" | predict_device_risk |
| `advice_query` | "设备 1000029970 建议检查什么？" | maintenance_advice |
| `history_query` | "设备 1000029970 最近有哪些故障？" | device_history |
| `risk_explanation` | "为什么设备 1000029970 是红色预警？" | predict + advice |
| `risk_and_advice_query` | "风险高不高，应该检查什么？" | history + predict + advice |

---

## 运行测试

```bash
pytest tests/ -v
```

```
73 passed in X.XXs
```

测试覆盖：Service 层 (22) + Tools 层 (16) + Agent 工作流 (35)

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | Streamlit |
| Agent 编排 | LangGraph |
| Agent 工具 | LangChain Tools |
| LLM | OpenAI-compatible (ChatOpenAI) |
| 可观测 | LangSmith |
| 数据处理 | Polars |
| 数据校验 | Pydantic |
| 数据科学 | Pandas / Altair |

---

## 预警规则

| 等级 | 条件 | 建议巡检窗口 |
|------|------|-------------|
| 🔴 红色预警 | risk_30d ≥ 0.75 或 risk_90d ≥ 0.90 | 3～7 天内 |
| 🟠 橙色预警 | risk_30d ≥ 0.55 或 risk_90d ≥ 0.75 | 7～14 天内 |
| 🟡 黄色预警 | risk_30d ≥ 0.35 或 risk_90d ≥ 0.55 | 14～30 天内 |
| 🟢 绿色关注 | 其他 | 常规周期 |

---

## 科学边界

1. `current_faildate` 表示工单记录时间，不一定等于物理故障发生时刻
2. 风险预测表示未来时间窗口内再次产生故障工单的风险，不等于设备一定会在某天发生故障
3. 维修建议是巡检方向参考，不是最终根因诊断结论
4. 最终维修判断仍需结合现场检测、设备日志和人工经验

---

## 后续升级方向

| 模块 | 当前 | 计划 |
|------|------|------|
| 预测模型 | Mock + 外部 CSV | 接入队友真实 ML 模型 |
| Agent | 规则路由 + LLM 解析/报告 | LangGraph tool-calling Agent |
| RAG | 预留接口 | 维修手册向量检索 |
| 数据存储 | 文件系统 | PostgreSQL / MySQL |
| 前端 | Streamlit | 可升级 React/Vue |
| 部署 | 本地 | Docker + 云部署 |

---

## 文档

详细架构设计和项目说明请查看 `docs/` 目录：

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统架构、Agent 工作流、工具与服务层设计 |
| [docs/project-brief.md](docs/project-brief.md) | 项目定位、用户场景、面试讲解口径 |
