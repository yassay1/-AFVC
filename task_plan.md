# 任务计划：AFC Agent 全项目文本完整性治理

## 目标
清理 AFC Agent 项目中的中文乱码、替换字符、私用区字符、错误编码文本和不可读文案，统一文本文件为 UTF-8，并建立自动检查机制，防止乱码再次进入项目。

## 修改边界
- 只处理 docstring、注释、Prompt、工具描述、日志、错误消息、API 文案、前端文案、测试文本和文档。
- 不修改 Agent 流程、路由逻辑、证据评估逻辑、业务算法、工具名称和参数、API 数据结构、数据处理规则、风险预测结果、前端业务交互流程。
- 不进行无差别批量转码；能从 Git 历史恢复的优先恢复，无法恢复的按代码语义重写。

## 阶段计划

### 阶段 1：建立基线和扫描
- [x] 记录当前 Git 状态。
- [x] 运行 `python -m compileall -f backend frontend tests`。
- [x] 运行 `pytest`。
- [x] 扫描 `backend`、`frontend`、`tests`、`docs`、`README.md` 和根目录记录文件。
- [x] 检查 UTF-8 strict 解码。
- [x] 搜索替换字符、私用区字符和常见乱码片段。
- 状态：complete

### 阶段 2：修复 Agent 核心文本
- [x] 修复 `backend/agent/tools.py` 工具描述、docstring、错误消息和注释。
- [x] 保留新增故障类型预测工具，不改工具参数、服务调用和返回结构。
- [x] 验证核心工具文案无乱码。
- 状态：complete

### 阶段 3：修复用户可见文本
- [x] 检查 `backend/api/`。
- [x] 检查 `frontend/streamlit_app.py`。
- [x] 确认 API message、错误提示、调试字段说明和前端文本无乱码。
- 状态：complete

### 阶段 4：修复维护性文本
- [x] 检查 `backend/services/`、`tests/`、`docs/`、`README.md`。
- [x] 从 Git 历史恢复 `task_plan.md`、`findings.md`、`progress.md` 的可读内容，并改写为本次治理记录。
- [x] 验证维护性文本无乱码。
- 状态：complete

### 阶段 5：建立预防机制
- [x] 新增 `scripts/check_text_integrity.py`。
- [x] 新增 `.editorconfig` 并设置 UTF-8。
- [x] 检查文本文件读写是否显式使用 `encoding="utf-8"`。
- [x] 增加工具描述和核心文案无乱码测试。
- [x] 将文本完整性检查加入测试流程。
- 状态：complete

### 阶段 6：全面验证
- [x] 运行 `python scripts/check_text_integrity.py`。
- [x] 运行 `python -m compileall -f backend frontend tests`。
- [x] 运行 `pytest`。
- [x] 执行 Agent 冒烟测试：能力介绍、历史查询、风险查询、维修建议、高风险排行、缺少设备编号追问、API 错误提示、前端调试信息。
- 状态：complete

## 初始扫描结果
- 当前 Git 状态：工作区已有较多未提交修改、删除和新增文件；本次治理不回滚已有用户改动。
- 基线编译：`python -m compileall -f backend frontend tests` 通过。
- 基线测试：`pytest` 收集 184 个用例，184 passed。
- 目标文本文件 UTF-8 strict 解码：74 个目标文本文件全部可解码，非 UTF-8 文件 0 个。
- 固化乱码集中位置：
  - `backend/agent/tools.py`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
- 扫描误报：
  - `backend/agent/llm_json.py` 的 Markdown 代码块正则。
  - `backend/agent/nodes/understand_query.py` 的中文正则 unicode escape。
  - `backend/agent/report_builder.py` 的正常中文示例问题。

## 问题分类
| 分类 | 文件 | 处理 |
|------|------|------|
| 非 UTF-8 文件 | 无 | 无需转码 |
| UTF-8 文件中的固化乱码 | `backend/agent/tools.py`、`task_plan.md`、`findings.md`、`progress.md` | 修复 |
| 不可逆替换字符 | 暂未发现 U+FFFD | 无 |
| 私用区字符 | `backend/agent/tools.py`、根目录三份记录文件 | 修复 |
| 可疑但需人工判断 | 无新增残留 | 持续扫描 |
| 扫描误报 | `llm_json.py`、`understand_query.py`、`report_builder.py` | 加入脚本排除/降噪规则 |

## 阶段验证记录
| 阶段 | 编译 | 测试 | 文本扫描 |
|------|------|------|------|
| 阶段 1 | 通过 | 184 passed | 初始命中 4 个真实问题文件 |
| 阶段 2 | 通过 | 184 passed | `backend/agent/tools.py` 命中 0 |
| 阶段 3 | 通过 | 184 passed | `backend/api/`、`frontend/` 命中 0 |
| 阶段 4 | 通过 | 184 passed | 维护性文本命中 0 |
| 阶段 5 | 通过 | 186 passed | `check_text_integrity.py` 通过 |
| 阶段 6 | 通过 | 186 passed | 最终扫描通过 |

## 修改记录
- `backend/agent/tools.py`：从 Git 历史恢复原有可读文案；按新增工具语义重写 `predict_device_fault_type_tool` 的 docstring 和错误消息。
- `task_plan.md`：恢复为可读 UTF-8 文档并记录本次治理计划和结果。
- `findings.md`：恢复为可读 UTF-8 文档并记录扫描发现。
- `progress.md`：恢复为可读 UTF-8 文档并记录执行日志。
- `scripts/check_text_integrity.py`：新增文本完整性检查脚本。
- `.editorconfig`：新增 UTF-8 编辑器配置。
- `tests/test_text_integrity.py`：新增默认 pytest 文本完整性守护测试。

## 剩余问题
- 未发现残留乱码。
- 当前 PowerShell 控制台可能把正常 UTF-8 中文显示成乱码；最终判断以 Python strict 解码和脚本检查为准。
