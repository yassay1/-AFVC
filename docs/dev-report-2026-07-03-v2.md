# AFC Agent 成熟架构升级开发报告 — 2026-07-03 (Round 2)

## 本轮开发目标

在不推翻现有八节点 Agent 架构、不新增任何 LangGraph 节点的前提下，把项目从"容易被 unknown 带歪的意图分类系统"升级为"route 清晰、answer_mode 清晰、工具边界清晰、证据约束清晰"的成熟 Agent 架构。

核心原则：问题类型增加，不增加节点。新增能力通过 schema、prompt、策略、校验和 answer_mode 扩展。

---

## 阅读了哪些核心文件

全部核心文件在上一轮已通读，本轮重点重读了各节点实现和测试。

---

## 修改了哪些文件（14 个）

### Schema 层

| 文件 | 修改内容 |
|------|---------|
| `backend/agent/schemas.py` | QueryUnderstanding 新增 `route`（6 种）和 `business_goal`（7 种）；ToolPlan 新增 `answer_mode`（5 种）；EvidencePacket 新增 `tool_errors`；ToolExecutionResult 新增 `error_type`；新增 `route_to_task_type()` 映射函数 |
| `backend/agent/state.py` | 新增 `NO_DEVICE_ROUTES`、`NO_TOOL_ROUTES`、`CHAT_ROUTES` 常量 |

### 节点层（8 个节点全部修改）

| 文件 | 修改内容 |
|------|---------|
| `backend/agent/nodes/understand_query.py` | **完全重构**：从细粒度 task_type 升级为 route + business_goal 双字段。新增 6 种 route 检测逻辑（含 _detect_route / _detect_business_goal）。LLM prompt 更新。rule fallback 更新。后处理增强指代继承逻辑 |
| `backend/agent/nodes/plan_tools.py` | **完全重构**：使用 route + business_goal 替代 task_type 做工具路由。新增 `ROUTE_TOOL_PLAN` 映射表。新增 answer_mode 决策。unknown/fallback 不再默认调用 get_integrated_analysis_tool。LLM prompt 更新 |
| `backend/agent/nodes/execute_tools.py` | 新增 `_validate_tool_args()` 参数保护：缺少 assetnum 返回结构化 `missing_required_argument` 错误，不再暴露 Pydantic crash。空 tool_calls 正常跳过。错误 trace 包含 error_type |
| `backend/agent/nodes/merge_evidence.py` | 新增 `tool_errors` 收集逻辑。区分成功和失败工具。非 evidence_based 模式跳过缺失证据检查 |
| `backend/agent/nodes/evaluate_evidence.py` | 新增 answer_mode 感知：非 evidence_based 模式直接 answerable=true。missing_required_argument 错误不触发补工具循环。所有工具失败时不无限重试 |
| `backend/agent/nodes/generate_answer.py` | **重大重构**：新增 5 种 answer_mode 回答模板（_direct_chat_answer / _capability_intro_answer / _ask_for_assetnum_answer / _unsupported_answer / evidence_based）。严格按 answer_mode 分派 |
| `backend/agent/nodes/update_memory.py` | 新增 route 感知：direct_chat/capability_intro/unsupported 保留原业务上下文；business_global 清除设备绑定；needs_clarification 不设置设备 |

### API 和编排层

| 文件 | 修改内容 |
|------|---------|
| `backend/agent/graph.py` | evidence 兼容转换包含 `tool_errors`。`_compat_asset_exists` 使用 route 判断。输出新增 `route`、`business_goal`、`answer_mode` |
| `backend/api/agent_api.py` | DiagnoseResponse 新增 `route`、`business_goal`、`answer_mode` 字段 |

### 测试层

| 文件 | 修改内容 |
|------|---------|
| `tests/test_agent_v03_nodes.py` | 更新所有测试 mock 包含 route/business_goal/answer_mode。新增 3 个测试类（TestV030RouteChat / TestV030Capability / TestV030MissingAsset / TestV030AnswerMode）共 11 个新测试 |
| `tests/test_agent_v03_graph.py` | FakeLLM 更新：_understanding 输出 route + business_goal；_tool_plan 输出 answer_mode |

### 文档层

| 文件 | 修改内容 |
|------|---------|
| `README.md` | 新增"v0.3.0 路由与回答模式"章节，替换旧的 12 种 task_type 表格 |
| `docs/architecture.md` | 新增 answer_mode 设计原则说明 |
| `docs/project-brief.md` | 更新核心创新点，新增粗粒度路由 + answer_mode 说明 |

---

## 当前最终 Agent 架构

```
START
  ↓
prepare_context     → 确定性整理上下文（无 LLM）
  ↓
understand_query    → LLM: route + business_goal + 参数提取
  ↓
plan_tools          → LLM: 规划工具 + 决定 answer_mode
  ↓
execute_tools       → 确定性执行工具（白名单 + 参数保护）
  ↓
merge_evidence      → 确定性整理证据（含 tool_errors）
  ↓
evaluate_evidence   → LLM: 评估证据（尊重 answer_mode）
  ├── 不足 → 回到 plan_tools（最多 2 轮）
  └── 足够 → generate_answer
  ↓
generate_answer     → LLM: 按 answer_mode 分派回答
  ↓
update_memory       → 确定性更新多轮记忆（闲聊不污染）
  ↓
END
```

**LLM 节点（4 个）**：understand_query / plan_tools / evaluate_evidence / generate_answer
**确定性节点（4 个）**：prepare_context / execute_tools / merge_evidence / update_memory

---

## QueryUnderstanding 改成了什么

**旧设计**：12 种 task_type 细粒度分类（risk_query, history_query, advice_query...）

**新设计**：三层结构

1. **route**（粗粒度，6 种）：决定"怎么处理"
   - `direct_chat` — 闲聊/问候
   - `capability_query` — 询问系统能力
   - `business_global` — 全局数据问题
   - `business_device` — 单设备业务问题
   - `needs_clarification` — 缺少关键参数
   - `unsupported` — 超出系统能力

2. **business_goal**（细粒度，7 种）：决定"具体做什么"
   - `data_overview` / `high_risk_ranking` / `device_risk` / `device_history` / `device_advice` / `full_diagnosis` / `manual_search`

3. **task_type**（保留兼容）：由 route + business_goal 自动映射生成

---

## ToolPlan / answer_mode 怎么设计

**answer_mode**（5 种）由 plan_tools 决定，generate_answer 执行：

| answer_mode | 触发条件 | 是否调工具 | generate_answer 行为 |
|-------------|---------|-----------|---------------------|
| `direct_chat` | route=direct_chat | 否 | 自然问候 + 简短能力介绍 |
| `capability_intro` | route=capability_query | 否 | 系统功能列表 + 示例问题 |
| `ask_for_assetnum` | route=needs_clarification | 否 | 请用户提供设备编号 |
| `evidence_based` | business_global / business_device | 是 | 基于 EvidencePacket 生成回答 |
| `unsupported` | route=unsupported | 否 | 礼貌说明能力边界 |

---

## 如何处理各种场景

### 1. 闲聊（"你好"）
- understand_query → route=direct_chat, needs_tools=false
- plan_tools → tool_calls=[], answer_mode=direct_chat
- execute_tools → 跳过
- merge_evidence → 空证据包（正常）
- evaluate_evidence → answerable=true（不需要业务证据）
- generate_answer → "你好，我是地铁 AFC 故障复发风险预测与智能维修建议助手..."
- update_memory → 保留原业务上下文

### 2. 能力询问（"你能做什么？"）
- understand_query → route=capability_query
- plan_tools → answer_mode=capability_intro
- generate_answer → 系统功能列表

### 3. 缺少设备编号（"帮我分析一下这个设备"）
- understand_query → route=needs_clarification
- plan_tools → tool_calls=[], answer_mode=ask_for_assetnum
- generate_answer → "请先提供设备编号，例如 1000029970..."

### 4. 业务问题（"分析设备1000029970"）
- understand_query → route=business_device, business_goal=full_diagnosis, assetnum=1000029970
- plan_tools → answer_mode=evidence_based, tool=get_integrated_analysis_tool
- execute_tools → 调用工具，参数校验通过
- merge_evidence → 整理证据
- evaluate_evidence → 检查证据充分性
- generate_answer → 基于 EvidencePacket 生成诊断报告

### 5. 工具错误（缺少 assetnum 时调用工具）
- execute_tools → 返回结构化错误 `{error_type: "missing_required_argument", message: "..."}`
- merge_evidence → 错误进入 tool_errors
- evaluate_evidence → 检测到 missing_required_argument → 不补工具
- generate_answer → 转为 ask_for_assetnum 回答

---

## 如何避免 LLM 编造业务数据

1. **只有 evidence_based 模式才调工具** — direct_chat/capability_intro/ask_for_assetnum/unsupported 不经过工具
2. **工具调用经过白名单** — 只允许 TOOL_BY_NAME 注册的 9 个工具
3. **参数保护** — execute_tools 检查 assetnum 有效性
4. **EvidencePacket 约束** — generate_answer 在 evidence_based 模式下只基于 EvidencePacket
5. **科学边界自动追加** — 如果 LLM 回答缺少科学边界声明，自动追加

---

## 运行了哪些测试与结果

```bash
# 全部核心测试（不含 legacy/LLM/slow）
python -m pytest tests/test_llm_json.py tests/test_services.py \
    tests/test_agent_tools.py tests/test_rag_service.py \
    tests/test_agent_v03_nodes.py tests/test_agent_v03_graph.py -q
```

**结果：115 passed**

分模块：
- test_llm_json.py: 13 passed
- test_services.py: 24 passed
- test_agent_tools.py: 18 passed
- test_rag_service.py: 11 passed
- test_agent_v03_nodes.py: 30 passed（含 11 个新增 v0.3.0 测试）
- test_agent_v03_graph.py: 19 passed（fake LLM 已更新）

---

## 当前仍未完成的内容

| 模块 | 状态 |
|------|------|
| 真实 ML 预测模型 | 未接入（Mock + CSV adapter） |
| 向量数据库 RAG | 未升级（关键词匹配） |
| PDF/Word 维修手册 | 未解析（仅 .txt/.md） |
| Docker 部署 | 未做 |
| 前端 UI 大改 | 未做 |
| compat.py 移除 | 保留作为 LEGACY 参考 |

---

## 后续建议

1. **前端调试面板更新**：Streamlit 前端 Agent 面板应展示 route / business_goal / answer_mode / tool_errors
2. **预测模型接入**：通过 model_adapter.py CSV 接口接入队友模型
3. **RAG 升级**：关键词匹配 → ChromaDB/FAISS + embedding
4. **compat.py 清理**：当旧测试完全迁移后可删除
5. **多设备对比**：如需支持"对比设备A和B"，需升级 execute_tools 去重键
