# 任务计划：AFVC 八节点 Agent 重构

## 目标
在保持八节点拓扑、业务工具、预测模型、API、会话机制和最大工具循环次数不变的前提下，重构四个 LLM 节点、Schema、State、条件边与测试，实现结构化理解、规划、证据评估和回答生成。

## 阶段

1. [complete] 完整阅读指定源码、现有测试和调用关系，建立兼容性基线。
2. [complete] 修改 Schema、State 与 LLM 配置，补齐结构化数据契约。
3. [complete] 重构 understand_query、plan_tools、merge_evidence、evaluate_evidence。
4. [complete] 重构 generate_answer、统一渲染与模板异常兜底。
5. [complete] 修改 graph 条件边与 API 返回兼容层。
6. [complete] 更新/新增 Fake LLM 测试，覆盖核心结构化场景。
7. [complete] 运行定向测试、完整测试与静态检查，修复回归并形成交付说明。

## 约束
- 不修改业务工具核心实现、预测算法、数据处理算法和外部 API。
- 不删除 report_builder，仅降级为模型失败兜底。
- 保留 final_answer 字符串兼容，并新增 generated_answer。
- 保留 InMemorySaver、session_id、八节点拓扑和 MAX_TOOL_LOOPS=2。
- 不执行 git push，不覆盖用户已有 README.md 修改。

## 错误记录

| 错误 | 次数 | 处理 |
|---|---:|---|
| manual_search 被开放分析规则抢先识别 | 1 | 调整业务目标判断优先级，手册请求保持固定目标 |
| “推荐一部电影”与“为什么风险高不代表”规则短语过窄 | 1 | 增加组合语义识别并通过测试 |
| Streamlit 启动检查使用 `$home` 变量与 PowerShell 内置 `$HOME` 冲突 | 1 | 改用 `$pageResponse` 后重新验证 |
| AppTest here-string 中中文导航标签被终端替换为问号 | 1 | 使用 Unicode escape 构造标签，六个页面全部验证通过 |

## 新任务：Streamlit 前端视觉与交互优化

### 目标
在不改变六页面导航、session_state、API 路径和 Agent 聊天调用关系的前提下，将默认 Streamlit 页面优化为专业、紧凑、响应式的 AFC 智能运维工作台。

### 阶段
1. [complete] 审计前端技术栈、页面入口、导航、状态、API、LLM 配置与测试。
2. [complete] 新增集中样式和可复用展示组件。
3. [complete] 重构页面布局、侧边栏、头部、路由状态、聊天、模式提示和 Debug。
4. [complete] 新增前端静态测试并完成启动、全量测试和文本完整性验证。
