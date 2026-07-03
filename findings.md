# 发现与决策

## 需求
- 用户希望"完成"这个 AFC 项目
- 项目定位：面试演示型 MVP，重点在 Agent 工程编排与工具调用闭环

## 研究发现

### 代码架构
- 严格分层：Streamlit → FastAPI → LangGraph Agent → LangChain Tools → Service → Data
- 唯一 Agent (AFCDiagnosisAgent)，不做多子 Agent
- Agent 只通过 Tools 访问业务能力，不直接读文件
- LLM 只负责解析问题和生成报告，风险值/预警/设备信息来自工具结果

### 技术栈
- Python 3.13 + FastAPI + Uvicorn + Streamlit
- LangGraph 1.2.7 + LangChain + LangSmith
- Polars + Pandas + Altair
- 智谱 GLM-4-Flash (OpenAI-compatible)

### 数据
- 真实 AFC 工单数据：afc非首次故障-L01线.xlsx (1.3MB, 约19994条)
- 设备编号格式：纯数字(10位) 和 字母+数字(如 EX011115)

### 测试状态
- 93/93 测试全部通过
- Service 层: 22 用例
- Tools 层: 16 用例
- Agent 工作流: 35 用例
- 多轮对话: 完整的指代补全测试覆盖

### 待完成方向（按 README 后续升级方向）
1. 预测模型：Mock → 接入真实 ML 模型
2. Agent：规则路由 → tool-calling Agent
3. RAG：预留接口 → 维修手册向量检索
4. 数据存储：文件系统 → PostgreSQL/MySQL
5. 前端：Streamlit → React/Vue 升级
6. 部署：本地 → Docker + 云部署

## 技术决策
| 决策 | 理由 |
|------|------|
| 待用户选择方向后记录 | |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| Explore subagent 模型不兼容 | 直接使用 Glob/Read/Grep 等工具手动探索 |

## 资源
- 项目根目录: D:\agentproject\地铁AFVC
- 后端入口: backend/main.py
- 前端入口: frontend/streamlit_app.py
- 测试目录: tests/
- 架构文档: AFC系统架构与Agent架构设计_主目标参考.md
- 实施说明书: AFC项目开发实施说明书.md
- 项目解释: AFC项目解释文件_主目标参考.md
- 对话报告: 地铁AFC闸机故障工单预测项目对话整理报告.pdf

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*

## 2026-07-03 三节点混合型 Agent 重构发现

- 当前旧架构本质是 `parse -> validate -> route -> execute -> merge -> report` 的固定流水线，`TASK_TOOL_MAP` 是工具选择主路径，LLM 主要承担意图解析和成文。
- 多轮污染根因在于 LangGraph checkpointer 会恢复完整状态；如果本轮只传 `query`，上一轮 `selected_tools/tool_results/evidence/errors/final_answer` 有机会残留。解决方案是每轮入口显式重置临时字段，只继承 `last_assetnum/last_task_type/last_time_window/messages`。
- 能力询问和全局概览必须规则优先，否则 LLM 解析漂移时容易被误判为设备诊断。
- 报告兜底不能只有完整设备诊断模板；需要按 `capability/data_overview/high_risk/full/risk/history/advice/risk_explanation/risk_and_advice/error` 分场景生成。
- service 层数据读取、风险预测、预警、维修建议逻辑可以保留；Agent 只通过 8 个 LangChain Tools 访问业务能力。
