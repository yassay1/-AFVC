# 进度日志：AFC Agent 文本完整性治理

## 会话：2026-07-11

### 阶段 1：建立基线和扫描
- 状态：complete
- 阶段目标：记录 Git 状态，运行基线编译和测试，扫描目标文本文件的 UTF-8 解码能力、替换字符、私用区字符和常见乱码片段。
- 涉及文件：`backend/`、`frontend/`、`tests/`、`docs/`、`README.md`、`task_plan.md`、`findings.md`、`progress.md`、`pytest.ini`、`requirements.txt`、`.env.example`。
- 修改边界：只读扫描；不修改业务文件。
- 验证方式：`git status --short`、`python -m compileall -f backend frontend tests`、`pytest`、临时 Python 扫描。
- 已修改内容：无业务修改。
- 发现的问题：
  - 目标文本文件 74 个，非 UTF-8 文件 0 个。
  - 固化乱码集中在 `backend/agent/tools.py`、`task_plan.md`、`findings.md`、`progress.md`。
  - 初始聚合正则写法失败 2 次，原因是乱码片段中包含需要转义的特殊字符；随后改用固定片段包含判断。
  - `llm_json.py`、`understand_query.py`、`report_builder.py` 为扫描误报。
- 验证结果：
  - `compileall` 通过。
  - `pytest`：184 passed。
- 剩余问题：核心工具文案和根目录记录文件待修复，预防机制待建立。

### 阶段 2：修复 Agent 核心文本
- 状态：complete
- 阶段目标：优先修复影响 LLM 工具选择和最终回答的 Agent 核心工具描述、错误消息和注释。
- 涉及文件：`backend/agent/tools.py`。
- 修改边界：只改 docstring、工具描述、注释和错误消息；不改工具名称、参数、服务调用、返回结构和工具注册语义。
- 验证方式：乱码信号扫描、`compileall`、`pytest`。
- 已修改内容：
  - 从 `HEAD:backend/agent/tools.py` 恢复原有工具可读文案。
  - 保留工作区新增的 `predict_device_fault_type_tool`。
  - 按当前函数语义重写新增故障类型预测工具的 docstring 和错误消息。
- 发现的问题：`tools.py` 工作区版本包含 BOM、私用区字符和大量固化乱码；旧版本可从 Git 历史恢复，但新增工具需语义重写。
- 验证结果：
  - `backend/agent/tools.py` 私用区字符：0。
  - 常见乱码片段命中：0。
  - `compileall` 通过。
  - `pytest`：184 passed。
- 剩余问题：API/前端用户可见文本待确认，根目录记录文件待修复。

### 阶段 3：修复用户可见文本
- 状态：complete
- 阶段目标：确认 API message、错误提示、调试字段说明和前端页面文案不返回乱码。
- 涉及文件：`backend/api/`、`frontend/streamlit_app.py`。
- 修改边界：仅允许修改用户可见文案；不改 API 数据结构和前端交互流程。
- 验证方式：Unicode 转义抽查、乱码片段扫描、`compileall`、`pytest`。
- 已修改内容：无。
- 发现的问题：`backend/api/` 中文 docstring、Field description 和 HTTPException detail 均可读；`frontend/streamlit_app.py` 未发现乱码命中。
- 验证结果：
  - API/前端乱码命中：0。
  - `compileall` 通过。
  - `pytest`：184 passed。
- 剩余问题：维护性记录文件待恢复，预防机制待建立。

### 阶段 4：修复维护性文本
- 状态：complete
- 阶段目标：修复维护性文本，包括服务层、测试、文档和根目录过程记录文件。
- 涉及文件：`backend/services/`、`tests/`、`docs/`、`README.md`、`task_plan.md`、`findings.md`、`progress.md`。
- 修改边界：只改文档、注释和记录；不改测试断言行为或业务实现。
- 验证方式：扫描、`compileall`、`pytest`。
- 已修改内容：
  - `task_plan.md`：恢复为可读 UTF-8 文档，记录本次治理计划和阶段状态。
  - `findings.md`：恢复为可读 UTF-8 文档，记录扫描发现和修复决策。
  - `progress.md`：恢复为可读 UTF-8 文档，记录执行过程。
- 发现的问题：
  - `backend/services/`、`tests/`、`docs/`、`README.md` 未发现真实乱码。
  - 根目录三份过程记录当前工作区版本为固化乱码，但 Git 历史中可读。
- 验证结果：
  - 维护性文本扫描问题数：0。
  - `compileall` 通过。
  - `pytest`：184 passed。
- 剩余问题：预防机制和最终冒烟测试尚未完成。

### 阶段 5：建立预防机制
- 状态：complete
- 阶段目标：新增自动化检查，防止乱码再次进入项目。
- 涉及文件：`scripts/check_text_integrity.py`、`.editorconfig`、`tests/test_text_integrity.py`。
- 修改边界：只新增检查脚本、编辑器配置和测试守护，不改业务逻辑。
- 验证方式：运行新脚本、`compileall`、`pytest`。
- 已修改内容：
  - 新增 `scripts/check_text_integrity.py`。
  - 新增 `.editorconfig`，设置 UTF-8、LF、末尾换行。
  - 新增 `tests/test_text_integrity.py`，把文本完整性检查纳入默认 pytest。
  - 检查 Python 文本读写缺少 `encoding="utf-8"` 的情况；二进制 `Path.open("wb")` 被识别为允许场景。
- 发现的问题：
  - 初版脚本误把 `Path.open("wb")` 当作文本写入，已修正二进制模式判断。
- 验证结果：
  - `python scripts/check_text_integrity.py`：passed。
  - `compileall` 通过。
  - `pytest`：186 passed。
- 剩余问题：最终冒烟测试尚未完成。

### 阶段 6：全面验证
- 状态：complete
- 阶段目标：执行最终文本扫描、编译、测试和 Agent 冒烟测试。
- 涉及文件：全项目目标文本文件、Agent 调用、API 调用、前端调试文案。
- 修改边界：只记录结果。
- 验证方式：`python scripts/check_text_integrity.py`、`python -m compileall -f backend frontend tests`、`pytest`、Python 内部 Unicode 字符级冒烟测试。
- 已修改内容：仅更新计划/发现/进度记录。
- 发现的问题：
  - PowerShell here-string 会把中文查询传给 Python 时替换为 `?`，导致独立烟测误判路由；改用 Unicode escape 构造查询后通过。
  - PowerShell/GBK 控制台可能无法打印部分 UTF-8 字符；冒烟结果改为 ASCII-safe 输出。
- 验证结果：
  - `python scripts/check_text_integrity.py`：passed。
  - `python -m compileall -f backend frontend tests`：passed。
  - `pytest`：186 passed。
  - Agent 冒烟测试通过：能力介绍、设备历史查询、设备风险查询、维修建议、高风险设备排行、缺少设备编号追问。
  - API 错误提示通过：`POST /agent/diagnose` 空 query 返回 422，响应文本无乱码。
  - 前端调试信息通过：`Debug`、`Assetnum`、`Route`、`Business Goal`、`tool_trace` 等标签存在且无乱码。
- 剩余问题：
  - 未发现残留乱码。
  - 终端显示乱码不等同于文件乱码，后续以检查脚本为准。
