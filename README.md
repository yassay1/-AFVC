# 🚇 AFC 故障复发风险预测与智能维修建议系统

面向地铁 AFC（自动售检票）设备的智能运维系统。基于真实故障工单数据，通过 **LLM-driven Context-Aware Tool Agent（LangGraph 八节点 + LangChain Tools + RAG）** 编排，预测设备复发风险、生成红橙黄绿预警，并提供可解释的诊断报告。

> **项目定位**：面试演示型 MVP，重点在 Agent 工程编排与工具调用闭环，而非预测模型训练。
> **v0.3.0 更新**：Agent 从三节点升级为八节点 LLM-driven 架构，LLM 承担四个角色（Query Understanding / Tool Planning / Evidence Evaluation / Answer Generation），新增维修手册 RAG 检索工具。旧三节点兼容代码（compat 模块）已标记为 LEGACY。

[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.139-green)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/langgraph-1.2.7-orange)](https://langchain-ai.github.io/langgraph/)

---

## Agent 架构升级（v0.2 → v0.3.0）

```
v0.2 三节点：                    v0.3.0 八节点：
parse_intent                     prepare_context     → 整理上下文
   ↓                             understand_query    → LLM 理解问题
reason_act                       plan_tools          → LLM 规划工具
   ↓                             execute_tools       → 执行工具
generate_report                  merge_evidence      → 合并证据
                                 evaluate_evidence   → LLM 评估证据
                                    ├── 不足 → 补充工具（最多 2 轮）
                                    └── 足够 → generate_answer  → LLM 生成回答
                                 update_memory       → 更新记忆
```

### LLM 四个角色

| 角色 | 节点 | 职责 |
|------|------|------|
| Query Understanding | understand_query | 结构化理解问题（含指代消解、设备切换） |
| Tool Planning | plan_tools | 解释 why→plan→expected evidence |
| Evidence Evaluation | evaluate_evidence | 判断证据是否足够，不足则建议补充 |
| Answer Generation | generate_answer | 基于 EvidencePacket 生成受约束回答 |

### 核心原则

- **LLM 不直接编造答案**：所有风险数值、设备信息、历史工单和维修建议都来自工具结果
- **RAG 是按需工具**：维修手册由 plan_tools / evaluate_evidence 决定是否调用
- **证据包约束回答**：generate_answer_node 只能基于 EvidencePacket 回答
- **结构化输出工程**：LLM JSON 经过 extract → json.loads → Pydantic → repair 四步处理

---

## 项目结构

```
afc_fault_agent_system/
├── backend/
│   ├── main.py                     # FastAPI 入口
│   ├── api/                        # API 路由层（7 路由）
│   ├── agent/                      # Agent 编排层 ★
│   │   ├── state.py                # AfcAgentState（v0.3 升级版）
│   │   ├── schemas.py              # 新：所有 Pydantic Schema
│   │   ├── llm_json.py             # 新：结构化 JSON 输出工具
│   │   ├── tools.py                # 9 个 LangChain Tools（含 RAG）
│   │   ├── prompts.py              # LLM Prompt 模板
│   │   ├── graph.py                # 八节点 LangGraph 工作流
│   │   ├── report_builder.py       # 报告生成器（模板兜底）
│   │   └── nodes/                  # 新：拆分后节点实现
│   │       ├── prepare_context.py
│   │       ├── understand_query.py
│   │       ├── plan_tools.py
│   │       ├── execute_tools.py
│   │       ├── merge_evidence.py
│   │       ├── evaluate_evidence.py
│   │       ├── generate_answer.py
│   │       ├── update_memory.py
│   │       └── compat.py           # ⚠️ LEGACY: 旧三节点兼容 API
│   ├── services/                   # 业务服务层（8 服务）
│   │   ├── rag_service.py          # 新：维修手册 RAG 检索
│   │   └── ...
│   ├── core/                       # 核心配置 + LLM 封装
│   └── data/                       # 数据文件
│       ├── raw/                    # 上传的原始工单
│       ├── mock/                   # 外部预测结果 CSV
│       └── knowledge/manuals/      # 维修手册知识库
├── frontend/
│   └── streamlit_app.py            # Streamlit 前端（6 页面）
├── tests/
│   ├── test_services.py
│   ├── test_agent_tools.py
│   ├── test_agent_graph.py         # ⚠️ LEGACY: 兼容旧三节点（部分测试标记 legacy）
│   ├── test_agent_v03_nodes.py     # v0.3: 八节点单元测试
│   ├── test_agent_v03_graph.py     # v0.3: 八节点端到端测试（fake LLM）
│   ├── test_llm_json.py            # v0.3: LLM JSON 工具测试
│   └── test_rag_service.py         # v0.3: RAG 服务测试
├── docs/
│   ├── architecture.md
│   └── project-brief.md
├── .env.example
├── requirements.txt
└── README.md
```

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

### 4. 多轮对话示例

```
用户：帮我分析设备 1000029970
Agent：[返回设备分析报告]
用户：那它为什么是橙色预警？
Agent：[自动关联设备 1000029970，返回预警解释]
用户：那应该先检查什么？
Agent：[自动关联设备 1000029970，返回维修建议]
用户：按维修手册说应该先查哪里？
Agent：[调用 RAG 检索维修手册，返回检查步骤]
用户：换成 EX011115 呢？
Agent：[切换到 EX011115，返回新设备分析]
```

### 5. 运行测试

```bash
# 运行核心测试（不含 legacy / LLM / slow）
python -m pytest tests/ -m "not legacy and not llm and not slow" -q

# 按模块运行
python -m pytest tests/test_services.py -q        # 服务层 (24 tests)
python -m pytest tests/test_agent_tools.py -q     # 工具层 (18 tests)
python -m pytest tests/test_llm_json.py -q        # JSON 工具 (13 tests)
python -m pytest tests/test_rag_service.py -q     # RAG 服务 (11 tests)
python -m pytest tests/test_agent_v03_nodes.py -q # 八节点单元 (23 tests)
python -m pytest tests/test_agent_v03_graph.py -q # 八节点端到端 (15 tests)

# 运行 legacy 测试（旧三节点兼容，非当前主验收标准）
python -m pytest tests/test_agent_graph.py -m legacy -q
```

> 注意：不配置 LLM API Key 也能运行大部分测试——Agent 会自动使用规则兜底。

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
| `POST` | `/agent/diagnose` | Agent 智能诊断（v0.3 八节点） |

---

## v0.3.0 路由与回答模式

### route（粗粒度语义路由）

| route | 适用场景 | 示例 | 调用工具 |
|-------|---------|------|---------|
| `direct_chat` | 闲聊/问候 | "你好""谢谢" | — |
| `capability_query` | 询问系统能力 | "你能做什么？" | — |
| `business_global` | 全局数据问题 | "数据概览""高风险排行" | data_summary / high_risk_devices |
| `business_device` | 单设备业务问题 | "分析设备1000029970" | 视 business_goal 而定 |
| `needs_clarification` | 缺少关键参数 | "帮我分析一下"（无设备号） | — |
| `unsupported` | 超出系统能力 | "帮我写论文" | — |

### answer_mode（回答模式）

| answer_mode | 说明 | 是否调工具 |
|-------------|------|-----------|
| `direct_chat` | 自然问候 + 简短能力介绍 | 否 |
| `capability_intro` | 系统功能说明 + 示例问题 | 否 |
| `ask_for_assetnum` | 请用户提供设备编号 | 否 |
| `evidence_based` | 基于 EvidencePacket 生成回答 | 是 |
| `unsupported` | 礼貌说明能力边界 | 否 |

### business_goal（细粒度业务目标）

| business_goal | 调用工具 |
|---------------|---------|
| `data_overview` | get_data_summary_tool |
| `high_risk_ranking` | get_high_risk_devices_tool |
| `device_risk` | predict_device_risk_tool |
| `device_history` | get_device_history_tool |
| `device_advice` | get_maintenance_advice_tool |
| `full_diagnosis` | get_integrated_analysis_tool |
| `manual_search` | search_maintenance_manual_tool |

> **核心改进（v0.3.0）**：通过 route + answer_mode 设计，确保"你好"不会调用业务工具，"帮我分析一下"（无设备号）会明确追问而不是报底层 validation error。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | Streamlit |
| Agent 编排 | LangGraph |
| Agent 工具 | LangChain Tools (9 个) |
| LLM | OpenAI-compatible API |
| RAG | 关键词匹配 + 段落切分（后续升级向量数据库） |
| 可观测 | LangSmith (可选) |
| 数据处理 | Polars |
| 数据校验 | Pydantic |

---

## 科学边界

1. `current_faildate` 表示工单记录时间，不一定等于物理故障发生时刻
2. **不能预测具体故障日期**，只能给风险窗口
3. 维修建议是巡检方向参考，**不是最终根因诊断结论**
4. RAG 检索的维修手册内容来自演示用示例文件
5. 最终维修判断仍需结合现场检测、设备日志和人工经验

---

## 后续升级方向

| 模块 | 当前（v0.3.0） | 计划 |
|------|-------------|------|
| 预测模型 | Mock + 外部 CSV adapter | 接入真实 ML 模型 |
| Agent | 八节点 LLM-driven Tool Agent | tool-calling Agent + multi-agent |
| RAG | 关键词匹配 .txt/.md（已实现） | 向量数据库 + embedding（ChromaDB/FAISS） |
| 数据存储 | 文件系统 | PostgreSQL / MySQL |
| 前端 | Streamlit | 可升级 React/Vue |
| 部署 | 本地 | Docker + 云部署 |

---

## 文档

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统架构、Agent 工作流、工具与服务层设计 |
| [docs/project-brief.md](docs/project-brief.md) | 项目定位、用户场景、面试讲解口径 |
