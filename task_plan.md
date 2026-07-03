# 任务计划：AFC 故障复发风险预测与智能维修建议系统

## 目标
完成 AFC RiskOps Agent System 的剩余工作，使其达到可演示、可部署的完整状态。

## 当前阶段
阶段 2：待用户选择下一步方向

## 项目当前状态总览

| 维度 | 状态 | 详情 |
|------|------|------|
| 后端 API (7个路由) | ✅ 完成 | FastAPI + Uvicorn，全部可用 |
| 业务服务层 (7个服务) | ✅ 完成 | 数据/设备/预测/预警/建议/分析/模型适配 |
| Agent 编排 (LangGraph) | ✅ 完成 | 6节点工作流 + 8个LangChain工具 |
| 多轮对话 | ✅ 完成 | InMemorySaver checkpointer + 指代补全 |
| 前端 (Streamlit) | ✅ 完成 | 6页面完整前端 |
| 测试 (93个用例) | ✅ 全部通过 | Service/Tools/Graph 三层覆盖 |
| 文档整理 | ✅ 完成 | 3份重叠文档→2份精简文档，移入docs/ |
| 数据清理 | ✅ 完成 | 重复文件删除，预测CSV扩展到240设备 |
| 代码质量 | ✅ 完成 | 版本号修正、LLM缓存、日志、前端优化 |
| 预测模型 | ⚠️ Mock | 规则兜底，待接入真实ML模型 |
| RAG 知识库 | ⚠️ 预留 | 接口已留，维修手册向量检索未接入 |
| 数据存储 | ⚠️ 文件系统 | 未迁移到 PostgreSQL/MySQL |
| 部署 | ⚠️ 本地 | 未容器化 |
| 前端框架 | ⚠️ Streamlit | 未升级到 React/Vue |

## 各阶段

### 阶段 1：需求评估与方向确定
- [x] 全面评估项目代码和架构
- [x] 运行全部测试确认基线状态 (93/93 passed)
- [x] 与用户确定优先完成的方向（文档+代码质量）
- **状态：** complete

### 阶段 2：文档整理与代码质量修复
- [x] 整合精简三个重叠设计文档 → docs/architecture.md + docs/project-brief.md
- [x] 处理 requirements.txt 编码问题（UTF-8 标准化）
- [x] 清理 raw 目录重复文件
- [x] 生成有意义的 prediction_results.csv（3条→240条真实设备）
- [x] 整理 docs 目录 + 更新 README 引用
- [x] 修复版本号 (config.py: 0.2.0→0.2.1)
- [x] 添加 LLM 实例懒加载缓存
- [x] 添加日志模块
- [x] 前端版本号动态读取后端
- [x] 清理前端未使用变量
- [x] 93/93 测试通过
- **状态：** complete

### 阶段 3：修复 Agent 诊断工作台三个异常
- [x] Bug 1：能力询问("你会干什么")返回空设备报告 → 新增 capability_query 任务类型
- [x] Bug 2：数据概览问题返回设备诊断格式 → generate_report_node 按 task_type 分支
- [x] Bug 3：多轮对话错误残留 → parse_question_node 重置 errors
- [x] 93/93 测试通过
- **状态：** complete

### 阶段 4：待定（根据用户选择）
- **状态：** pending

### 阶段 4：测试与验证
- **状态：** pending

### 阶段 5：交付
- **状态：** pending

## 关键问题
1. 用户希望优先完成哪个方向？（预测模型接入 / RAG / 部署 / 前端升级 / 其他）
2. 是否有真实的 ML 模型可以接入？
3. 面试演示的时间节点是什么？

## 已做决策
| 决策 | 理由 |
|------|------|
| 3份设计文档整合为2份 | 消除重叠，按"架构"和"项目说明"分类 |
| LLM 实例采用懒加载单例 | 避免每次调用重新创建 ChatOpenAI 连接 |
| prediction_results.csv 扩展到240设备 | 覆盖更多真实设备，使外部模型模式更可用 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| Explore Agent 模型适配失败 | 1 | 直接使用文件搜索和阅读工具完成代码审查 |
| 正则过宽导致测试失败 | 1 | 移除过宽的"分析"匹配模式，恢复原有多词精确匹配 |

## 修改的文件清单
- `backend/core/config.py` — 版本号 0.2.0→0.2.1
- `backend/core/llm.py` — 添加 LLM 实例懒加载缓存 + logging
- `backend/main.py` — 添加 logging 模块 + 启动/关闭日志
- `backend/agent/nodes.py` — 设备切换正则还原（避免误匹配）
- `frontend/streamlit_app.py` — 版本号动态读取 + 清理未使用变量
- `docs/architecture.md` — 新建：整合架构设计文档
- `docs/project-brief.md` — 新建：整合项目说明文档
- `backend/data/mock/prediction_results.csv` — 扩展到240设备
- `requirements.txt` — UTF-8 编码标准化
- `README.md` — 更新文档引用
- 删除：3个原始重叠文档 + 1个重复数据文件

## 备注
- 93个测试全部通过，代码基线健康
- .env 已配置智谱 GLM-4-Flash 模型，.gitignore 已排除 .env
- 如要启动验证，运行 `uvicorn backend.main:app` + `streamlit run frontend/streamlit_app.py`

## 2026-07-03 新增阶段：三节点混合型诊断 Agent 重构

### 阶段 4：架构重构
- [x] 全面阅读 `backend/agent`、`backend/services`、`backend/api`、`frontend`、`tests`
- [x] 输出架构诊断：旧实现为固定 6 节点流水线，工具选择过度依赖 `TASK_TOOL_MAP`
- [x] 将图重构为 `parse_intent -> reason_act -> generate_report`
- [x] `parse_intent` 支持规则优先、LLM structured output、多轮指代、设备切换、全局问题和能力询问
- [x] `reason_act` 支持工具白名单、设备校验、tool-calling 主路径、规则兜底、`tool_trace` 和标准化 evidence
- [x] `generate_report` 支持按场景生成报告和模板兜底
- [x] 每轮入口清空 `errors/selected_tools/tool_results/tool_trace/evidence/final_answer`
- [x] 保持 service 层业务逻辑不重写，API 和前端字段向后兼容
- 状态：complete

### 阶段 5：验收测试
- [x] 覆盖能力询问、数据概览、高风险设备、单设备诊断、风险查询、维修建议、风险+建议组合、多轮指代、设备切换、设备编号缺失、设备不存在、session 隔离、LLM 不可用规则兜底
- [x] `python -m pytest tests/test_agent_graph.py -q`：65 passed
- [x] `python -m pytest -q`：106 passed
- 状态：complete
