# AFC RiskOps Agent System — 项目说明书（v0.3.0）

> 项目定位、目标用户、核心价值与面试讲解口径。

---

## 1. 项目一句话介绍

面向地铁 AFC（自动售检票）设备的智能运维系统：基于历史故障工单数据预测复发风险，通过 LLM-driven Context-Aware Tool Agent 自动整合设备历史、风险预测、预警等级、维修手册 RAG 检索和维修建议，生成可解释的运维诊断报告。

---

## 2. 架构升级（v0.2 → v0.3.0）

| 维度 | v0.2（旧） | v0.3.0（新） |
|------|-----------|----------------|
| Agent 节点 | 三节点（parse_intent / reason_act / generate_report） | 八节点（prepare_context → understand_query → plan_tools → execute_tools → merge_evidence → evaluate_evidence → generate_answer → update_memory） |
| LLM 角色 | 1 个（报告生成） | 4 个（Query Understanding / Tool Planning / Evidence Evaluation / Answer Generation） |
| 工具规划 | 规则硬编码 task_type → tool | LLM 解释 why + what evidence + 按需调用 |
| RAG | 无 | 维修手册关键词检索工具 |
| JSON 处理 | with_structured_output | 四步工程（extract → json.loads → Pydantic → repair） |
| 证据约束 | 无 | EvidencePacket → generate_answer 只能基于证据回答 |

---

## 3. 核心创新点

### 3.1 LLM 不直接编造答案

LLM 在结构化约束下完成四个角色，所有风险数值、设备信息、历史工单和维修建议都来自工具结果。维修手册通过 RAG 工具按需检索，最终回答受 EvidencePacket 约束。

### 3.2 粗粒度路由 + answer_mode（v0.3.0 新增）

不是简单的 task_type 分类游戏，而是通过三层设计决定行为：
- **route**（6 种）决定"怎么处理"：闲聊/能力/全局/单设备/缺参数/不支持
- **business_goal**（7 种）决定"具体做什么"：概览/排行/风险/历史/建议/诊断/手册
- **answer_mode**（5 种）决定"如何回答"：直接聊天/能力介绍/追问编号/证据回答/能力边界

### 3.3 工具规划由 LLM 解释

不是简单的 task_type → tool 映射，而是让 LLM 解释：为什么调用这个工具？希望拿到什么证据？已有证据够不够？需不需要 RAG？

### 3.4 证据评估循环

evaluate_evidence_node 尊重 answer_mode：非 evidence_based 模式直接可回答。evidence_based 模式才检查证据充分性。不足时回到 plan_tools 补充工具（最多 2 轮），形成反馈闭环。工具错误（missing_required_argument）不再触发补充循环。

### 3.5 RAG 是按需工具

维修手册 RAG 不是默认上下文，而是由 plan_tools / evaluate_evidence 决定是否调用。这避免了不相关手册内容干扰 LLM 推理。

---

## 4. 解决的痛点

| 痛点 | 本系统方案 |
|------|-----------|
| 历史工单多，难以判断哪些设备易复发 | 多时间窗口风险预测 + 红橙黄绿预警 + Top N 排序 |
| 运维人员不知道今天优先巡检什么 | 高风险设备列表 + 巡检窗口建议 |
| 单设备异常后需快速了解全貌 | 综合分析聚合历史、风险、预警、建议 + 维修手册 |
| 预测值不直观 | Agent 将风险值翻译为业务可理解的预警和建议 |
| 维修建议依赖经验 | 基于历史故障描述的关键词规则 + RAG 维修手册检索 |
| 多轮追问需重新输入设备编号 | 指代消解 + 设备切换 + 上下文继承 |

---

## 5. 目标用户与使用场景

### 运维主管 — "今天优先巡检哪些设备？"
- 高风险设备 Top N 列表
- 每台设备的车站、线路、品牌、6 时间窗口风险
- 红橙黄绿预警 + 建议巡检窗口

### 一线维修人员 — "帮我分析设备 XXX，风险高不高，按维修手册应该先检查什么？"
- 设备基础信息 + 历史工单摘要
- 30/90 天风险 + 预警等级
- 维修手册 RAG 检索的检查步骤
- 维修检查方向 + 备件建议 + 科学边界

### 设备管理人员 — "为什么这台设备是红色预警？"
- 风险值是否超过阈值
- 历史工单数量和近期密度依据
- 高频故障现象 + 巡检建议

---

## 6. 面试讲解口径

> 这个项目不是简单调用大模型回答维修问题，而是把 AFC 运维任务拆成**上下文整理、问题理解、工具规划、工具执行、证据合并、证据评估、答案生成和记忆更新**八个 LangGraph 节点。
>
> LLM 不直接编造答案，而是在结构化约束下完成 **Query Understanding、Tool Planning、Evidence Evaluation 和 Answer Generation** 四个角色。所有风险数值、设备信息、历史工单和维修建议都来自工具结果，维修手册通过 RAG 工具按需检索，最终回答受 **EvidencePacket** 约束。
>
> 我的重点不是训练复杂预测模型，而是做 **Agent 工程编排**。通过 LangGraph 把上下文、理解、工具规划、证据合并、回答生成拆开，保证每一步都可追踪、可调试、可评估。同时接入 LangSmith 追踪每次 Agent 调用了哪些工具、拿到了什么结果、最终报告是否忠实使用工具输出。

---

## 7. 科学边界声明

1. `current_faildate` 是工单记录时间，不直接等同于物理故障发生时刻
2. **不能预测具体故障日期**，只能给风险窗口（如"未来30天约有X%概率再次产生故障工单"）
3. 维修建议是巡检方向参考，**不是最终根因诊断结论**
4. RAG 检索的维修手册内容来自演示用示例文件，不代表真实官方维修规程
5. 最终维修判断仍需结合现场检测、设备日志和人工经验

---

## 8. 后续升级方向

| 模块 | 当前（v0.3.0） | 计划 |
|------|-------------|------|
| 预测模型 | Mock + 外部 CSV adapter | 接入真实 ML 模型 |
| Agent | 八节点 LLM-driven Agent | tool-calling Agent + multi-agent |
| RAG | 关键词匹配 .txt/.md（已实现） | 向量数据库 + embedding（ChromaDB/FAISS） |
| 数据存储 | 文件系统 | PostgreSQL/MySQL |
| 前端 | Streamlit | 可升级 React/Vue |
| 部署 | 本地 | Docker + 云部署 |
| 可观测 | LangSmith (可选) | 完整 trace + 评估 |

---

## 9. 验收标准（v0.3.0）

### 后端
- 八节点 Agent 图正确编译和运行
- 支持 12 种问题类型（含 manual_query / followup_rewrite）
- 结构化 JSON 输出 + repair 机制正常工作

### Agent
- 能继承上下文（指代消解）
- 能切换设备（"换成 XXX 呢？"）
- 能规划工具（LLM 规划 + 规则兜底）
- 能调用多个工具
- 能根据证据回答（EvidencePacket 约束）
- 能在需要时调用 RAG（manual_query / advice_query）
- 能说明科学边界（不预测具体日期）

### RAG
- 维修手册检索工具可用
- 示例手册文件包含 5 类常见故障检查步骤

### 多轮对话
- 5 轮连续对话：分析设备 → 追问风险 → 追问建议 → 切换设备 → 追问历史
