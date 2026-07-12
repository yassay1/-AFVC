# 发现与决策：AFVC 八节点 Agent 重构

## 初始状态
- 2026-07-12 开始审计。
- 工作区预存未提交修改：`README.md`，本任务不回滚或覆盖。

## 架构发现与实施决策
- 原实现对固定业务也调用规划与评估 LLM；现改为固定目标规则映射，只有 open_analysis 使用相应 LLM。
- 原 EvidenceEvaluation 混合“证据是否充分”和“下一步动作”；现拆为 evidence_sufficient 与 decision。
- 原 generate_answer 直接调用模型文本输出，只发送 HumanMessage，manual_search 强制模板；现统一通过 call_llm_json、SystemMessage 和 GeneratedAnswer，模板仅异常兜底。
- merge_evidence 保留原工具归一化逻辑，新增 available_evidence，并以 ToolPlan.expected_evidence 计算缺失证据。
- run_diagnosis 保留全部旧字段和 final_answer 字符串，新增 generated_answer。
- README.md 的工作区修改在任务开始前已存在，本任务未修改。

## 验证
- `python -m compileall -q backend tests`：通过。
- `pytest -q`：193 passed。
- `python scripts/check_text_integrity.py`：通过。
- 生产代码残留扫描确认不再读取旧 needs_tools、needs_rag、answerable、need_more_tools、suggested_next_tools。

## 前端 UI 审计
- 技术栈为 Streamlit，唯一入口是 `frontend/streamlit_app.py`，六个页面均由 `main()` 内的 sidebar radio 切换。
- Agent 聊天已使用官方 `st.chat_message` 和 `st.chat_input`，必须在其上增强样式。
- 会话状态使用 `st.session_state`；API 调用路径集中在同一文件的 requests 封装中。
- LLM 开关真实变量为 `AFVC_USE_LLM`，应复用 `backend.core.config.is_llm_enabled()`。
- 当前没有集中 CSS 模块，主题配置位于 `.streamlit/config.toml`。
- UI 技能建议采用 transit blue、amber accent、浅灰背景、清晰焦点、44px 交互高度和 1280px 最大内容宽度；避免复杂阴影、渐变和装饰动画。

## 前端实施结果
- 新增集中样式 `frontend/styles.py` 与展示组件 `frontend/ui_components.py`，避免 CSS 和枚举映射散落。
- 六页面导航、所有 API 路径、请求体、session_state 键和官方聊天组件保持不变。
- 首页不伪造统计值，仅展示能力说明、真实 LLM 模式和明确标注的路由展示示例。
- 工作台将最新 route、business_goal、assetnum 映射为友好状态卡；原值和完整响应保留在底部折叠 Debug。
- 未引入图标库；侧边栏使用纯 CSS AFC 字标，避免为少量图标增加依赖。
- AppTest 验证六个导航页面无运行异常；AFVC_USE_LLM=false/true 均无异常。

## LLM JSON 失败复现（当前高风险设备有哪些）
- 智谱 `glm-4-flash-250414` 三次请求均 HTTP 200，`AIMessage.content` 读取正常。
- 首次输出和两次 repair 输出都是 JSON array，并模仿 Prompt 示例返回 `input/output` 包装；目标 Schema 要求根对象直接是 QueryUnderstanding。
- 异常类型是 Pydantic SchemaValidationError，不是 JSONDecodeError；字段级错误为根字段缺失及 input/output extra_forbidden。
- repair 循环第二次仍把最初 raw_output 作为修复对象，没有串联第一次 repair 输出。
- 当前结构化方式不是 API native response_format，而是 Prompt 文本 JSON + 本地提取 + Pydantic + LLM repair；未发现 OpenAI-compatible 响应字段或协议不兼容。

## LLM 意图结构化修复结果
- understand Prompt 已改为普通文本分段示例，新增全局高风险查询示例、完整枚举、根对象骨架和禁止包装约束。
- JSON 根数组现在明确抛出 `期望 JSON object，实际收到 JSON array`，不再扫描内部包装对象。
- repair 使用 Pydantic `model_json_schema()`，第二轮基于第一轮输出串联修复。
- 真实 `glm-4-flash-250414` 对“当前高风险设备有哪些”首次返回无包装根对象，直接通过 QueryUnderstanding，errors 为空。

## Streamlit 加载提示生命周期修复
- 原实现使用 `st.spinner` 后立即由提交入口 `st.rerun()`，没有显式 placeholder 或 processing 状态，前端可能保留上一轮 spinner delta。
- 新增 `agent_is_processing` 防重复提交；加载文案仅写入 `st.empty()` placeholder。
- `_handle_agent_query()` 使用 try/except/finally，无论成功、后端兜底响应、空响应、超时或异常，finally 都先置 False 再调用 placeholder.empty()。
- 两个 st.rerun 调用均只在 handler 完整返回后执行；刷新时清除中断留下的 stale flag。
