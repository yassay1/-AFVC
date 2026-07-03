# AFC Agent 开发报告 — 2026-07-03

## 本次修改目标

在不接入真实 ML 模型、不升级向量 RAG、不做部署的前提下，对八节点 LangGraph Agent 进行代码质量升级：修复 bug、清理旧版本包袱、统一版本号和文档，确保核心展示功能完整可用。

---

## 修改了哪些文件

### 代码修改

| 文件 | 修改内容 |
|------|---------|
| `backend/core/config.py` | `PROJECT_VERSION` 从 `"0.2.1"` 更正为 `"0.3.0"` |
| `backend/agent/state.py` | `CAPABILITY_BOUNDARY.can_retrieve_maintenance_manual` 从 `False` 更正为 `True`（RAG 已实现） |
| `backend/agent/prompts.py` | 添加 DEPRECATED 标记和说明，明确这两个 Prompt 是 v0.2 旧版，当前八节点 Agent 使用各节点内联 Prompt |
| `backend/agent/nodes/compat.py` | 消除与 `understand_query.py` 的大段重复代码（正则模式、关键词列表、辅助函数），改为从 `understand_query.py` 导入 |
| `backend/agent/nodes/plan_tools.py` | 移除重复的 `NO_DEVICE_TASKS` 局部定义，改为从 `state.py` 导入 |
| `backend/agent/nodes/execute_tools.py` | 添加工具去重机制说明文档（当前按 tool_name 去重，适用单设备场景） |
| `backend/agent/nodes/__init__.py` | 修复兼容函数名冲突问题：旧 `execute_tools_node` / `merge_evidence_node` 不再遮蔽 v0.3 同名函数 |

### 测试修改

| 文件 | 修改内容 |
|------|---------|
| `tests/test_agent_graph.py` | 1) 移除文件级 `pytestmark = pytest.mark.legacy`，改为仅在兼容测试类上加标记<br>2) 更新 `TestAgentState` 期望字段为 v0.3 状态形状<br>3) 更新 `TestHybridAgentAcceptance` 两个测试用例以匹配 v0.3 实际行为<br>4) 修复 `execute_tools_node`/`merge_evidence_node` 引用为 compat 版本 |

### 文档修改

| 文件 | 修改内容 |
|------|---------|
| `README.md` | 统一版本号为 v0.3.0；添加完整测试运行说明；标记 compat.py 为 LEGACY |
| `docs/architecture.md` | 统一版本号为 v0.3.0；更新 Agent State 定义；标注 RAG 为已实现 |
| `docs/project-brief.md` | 统一版本号为 v0.3.0；更新 RAG 状态为已实现 |
| `docs/dev-report-2026-07-03.md` | 本文件 |

---

## 修复了哪些 bug / 不一致

### 1. 版本号不一致
- **问题**：`config.py` 中 `PROJECT_VERSION = "0.2.1"`，但 README / docs 全部在讲 v0.3/v0.4 八节点 Agent
- **修复**：统一为 `"0.3.0"`

### 2. 能力边界声明过时
- **问题**：`CAPABILITY_BOUNDARY.can_retrieve_maintenance_manual = False`，但实际上 RAG 服务已实现并正常工作
- **修复**：改为 `True`，注释更新为"关键词检索维修手册"

### 3. 旧版 Prompt 误导读者
- **问题**：`prompts.py` 的 `QUESTION_PARSE_PROMPT` 和 `REPORT_GENERATION_PROMPT` 是 v0.2 版本，不了解代码的人可能误认为这就是当前主流程 Prompt
- **修复**：添加 DEPRECATED 标记，列出当前各节点的实际 Prompt 位置

### 4. compat.py 大段代码重复
- **问题**：`compat.py` 中 `_REFERENCE_PATTERNS`、`_SWITCH_PATTERNS`、`_has_reference_pronoun`、`_has_device_switch`、`_extract_assetnum_from_query` 等与 `understand_query.py` 完全重复
- **修复**：compat.py 改为从 `understand_query.py` 导入这些函数，只保留 compat 特有的逻辑

### 5. __init__.py 命名冲突
- **问题**：`backend/agent/nodes/__init__.py` 中，compat 模块的 `execute_tools_node` 和 `merge_evidence_node` 会在导入时覆盖 v0.3 的同名函数，导致调用行为不确定
- **修复**：只导出 v0.3 版本的同名函数，兼容版本通过 `compat` 子模块显式导入

### 6. 测试期望的旧字段
- **问题**：`test_agent_graph.py` 中 `TestAgentState` 测试期望旧版字段（`assetnum`、`selected_tools` 等），但 `create_initial_state` 已升级为 v0.3 状态
- **修复**：更新测试期望为新字段

### 7. test_agent_graph.py 全局 legacy 标记
- **问题**：文件级 `pytestmark = pytest.mark.legacy` 导致所有 test_agent_graph.py 的测试被默认跳过，但其中 `TestHybridAgentAcceptance` 等测试的是当前 v0.3 API
- **修复**：移除文件级 legacy 标记，仅在兼容测试类上加 `@pytest.mark.legacy`

---

## 当前八节点 Agent 工作流程

```
START
  ↓
prepare_context     → 整理上下文（无 LLM，确定性代码）
  ↓
understand_query    → LLM 理解用户问题，输出 QueryUnderstanding
  ↓
plan_tools          → LLM 规划工具调用，输出 ToolPlan（含 why / purpose / expected_evidence）
  ↓
execute_tools       → 执行工具计划（无 LLM，白名单校验 + 确定性执行）
  ↓
merge_evidence      → 合并原始 tool_results 为统一 EvidencePacket（无 LLM）
  ↓
evaluate_evidence   → LLM 评估证据是否足够
  ├── 不足且 tool_loop_count < 2 → 回到 plan_tools 补充工具
  └── 足够或达到最大循环 → generate_answer
  ↓
generate_answer     → LLM 基于 EvidencePacket 生成最终回答
  ↓
update_memory       → 更新多轮对话状态（无 LLM）
  ↓
END
```

**LLM 四个角色**：
1. **Query Understanding** (understand_query_node) — 结构化解析问题，含指代消解与设备切换
2. **Tool Planning** (plan_tools_node) — 解释 why → plan → expected evidence
3. **Evidence Evaluation** (evaluate_evidence_node) — 判断证据充分性
4. **Answer Generation** (generate_answer_node) — 基于 EvidencePacket 生成受约束回答

**确定性代码节点** (4 个)：prepare_context, execute_tools, merge_evidence, update_memory

**核心保障**：
- LLM 不直接编造答案 → 必须通过工具 → 工具结果 → EvidencePacket → 最终回答
- 工具调用白名单校验 → 只允许 `TOOL_BY_NAME` 注册的工具
- 结构化输出工程 → extract → json.loads → Pydantic → repair 四步
- 最大工具循环限制 → 防止无限循环（MAX_TOOL_LOOPS = 2）

---

## 当前仍未做的内容

按用户明确要求，本轮**没有**做以下事情（也不应该在本轮做）：

| 模块 | 未做内容 |
|------|---------|
| 预测模型 | 未接入真实 ML 模型（RandomForest / XGBoost / LightGBM），仍然使用 Mock + CSV adapter |
| RAG | 未升级为向量数据库 + embedding（ChromaDB / FAISS），仍然是关键词匹配 |
| 维修手册 | 未做 PDF / Word 解析，仅支持 .txt / .md |
| 部署 | 未做 Docker / K8s 部署 |
| 前端 UI | 未做大改 |
| 新依赖 | 未引入重型新依赖 |

---

## 如何运行项目

```bash
# 1. 环境准备
cd "D:\agentproject\地铁AFVC"
python -m venv .venv
source .venv/Scripts/activate   # Git Bash
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，配置 OPENAI_API_KEY（不配置也能运行，走规则兜底）

# 3. 启动后端
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# 4. 启动前端（新终端）
streamlit run frontend/streamlit_app.py
```

## 如何运行测试

```bash
# 所有非 legacy/非 LLM/非 slow 测试（推荐）
python -m pytest tests/ -m "not legacy and not llm and not slow" -q

# 分模块运行
python -m pytest tests/test_services.py -q       # 服务层 (24)
python -m pytest tests/test_agent_tools.py -q    # 工具层 (18)
python -m pytest tests/test_llm_json.py -q       # JSON 工具 (13)
python -m pytest tests/test_rag_service.py -q    # RAG 服务 (11)
python -m pytest tests/test_agent_v03_nodes.py -q # 八节点单元 (23)
python -m pytest tests/test_agent_v03_graph.py -q # 八节点端到端 (15)

# Legacy 测试（非主验收标准，仅用于旧三节点兼容校验）
python -m pytest tests/test_agent_graph.py -m legacy -q
```

测试结果：**104 passed**（不含 legacy/LLM/slow 标记）

---

## 后续建议

1. **compat.py 彻底移除**：当旧测试全部迁移到 v0.3 测试文件后，可删除 `compat.py` 及其在 `__init__.py` 中的引用

2. **execute_tools 去重升级**：如需支持单轮多设备查询（如 "对比设备 A 和 B 的风险"），应将去重键改为 `(tool_name, frozenset(args.items()))`

3. **前端调试面板对齐**：检查 Streamlit 前端 Agent 诊断面板是否使用了 `evidence_packet` / `query_understanding` 等 v0.3 新增字段

4. **预测模型接入**：这是下一步核心升级方向，通过 `model_adapter.py` 的 CSV 接口即可接入队友模型

5. **RAG 升级**：当前关键词匹配在手册内容较多时召回率不足，可升级为 ChromaDB + embedding
