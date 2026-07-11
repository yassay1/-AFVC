# 发现与决策：AFC Agent 文本完整性治理

## 需求边界
- 目标是全项目文本完整性治理，不改变业务逻辑。
- 修复范围包括中文乱码、替换字符、私用区字符、错误编码文本、不可读 docstring/注释/Prompt/工具描述/日志/错误消息/API 文案/前端文案/文档。
- 文件编码目标是 UTF-8 strict 可解码。
- 预防目标是新增自动扫描脚本、编辑器配置和测试集成。

## 基线发现

### Git 状态
工作区在本次治理开始前已有大量未提交变化，包括修改、删除和新增文件。本次治理遵循“不回滚用户已有改动”的原则，仅处理文本完整性相关文件和新增预防机制。

### 编译与测试
- `python -m compileall -f backend frontend tests`：通过。
- `pytest`：184 passed。

### UTF-8 strict 解码
- 扫描目标文本文件 74 个。
- 非 UTF-8 文件：0 个。
- 说明：当前问题主要是“UTF-8 文件中固化了错误解码后的乱码”，而不是文件本身无法用 UTF-8 解码。

## 乱码分类

### 固化乱码
- `backend/agent/tools.py`：工具 docstring、工具描述、错误消息、注释中存在严重乱码和私用区字符。
- `task_plan.md`：过程记录文件整体乱码。
- `findings.md`：过程记录文件整体乱码。
- `progress.md`：过程记录文件整体乱码。

### 私用区字符
- `backend/agent/tools.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### 不可逆替换字符
- 暂未发现 U+FFFD。

### 非 UTF-8 文件
- 暂未发现。

### 扫描误报
- `backend/agent/llm_json.py`：代码块提取正则包含反引号，属于正常代码。
- `backend/agent/nodes/understand_query.py`：中文正则以 unicode escape 形式存在，属于正常代码。
- `backend/agent/report_builder.py`：示例问题是正常中文文本。

## 修复来源

### 从 Git 历史恢复
- `backend/agent/tools.py` 的原有工具文案来自 `HEAD:backend/agent/tools.py` 的可读版本。
- `task_plan.md`、`findings.md`、`progress.md` 的历史内容可从 `HEAD` 读取为正常中文；本次未逐字恢复旧计划，而是基于可读版本重建为当前治理记录。

### 按代码语义重写
- `backend/agent/tools.py` 新增的 `predict_device_fault_type_tool` 不在旧版本中，按当前函数签名、服务调用和返回字段语义重写 docstring 与错误消息。
- 根目录三份过程记录改写为本次治理计划、发现和进度记录。

## 阶段结论

### 阶段 1
- 发现文件编码均可 UTF-8 解码。
- 真实乱码问题集中，未发现需要盲目批量转码的证据。
- 初始扫描的宽松模式会误报部分正常代码，最终脚本需要分级规则降低误报。

### 阶段 2
- `backend/agent/tools.py` 已修复。
- 工具注册表、工具名称、参数、服务调用保持不变。
- 验证：`tools.py` 私用区字符为 0，常见乱码片段命中 0，编译通过，测试 184 passed。

### 阶段 3
- `backend/api/` 和 `frontend/streamlit_app.py` 未发现乱码。
- 未修改 API 或前端文件。
- 验证：编译通过，测试 184 passed。

### 阶段 4
- `backend/services/`、`tests/`、`docs/`、`README.md` 未发现真实乱码。
- `task_plan.md`、`findings.md`、`progress.md` 已恢复为可读文本并记录本次治理。

## 待完成
- 无待完成项。

## 预防机制
- `scripts/check_text_integrity.py`：检查 UTF-8 strict 解码、BOM、U+FFFD 替换字符、私用区字符、常见乱码强信号和 Python 文本读写缺少 `encoding="utf-8"` 的情况。
- `.editorconfig`：设置 `charset = utf-8`、LF 换行、文件末尾换行。
- `tests/test_text_integrity.py`：把文本完整性检查和 Agent 核心文案检查纳入默认 `pytest` 流程。

## 最终验证
- `python scripts/check_text_integrity.py`：passed。
- `python -m compileall -f backend frontend tests`：passed。
- `pytest`：186 passed。
- Agent 冒烟测试：能力介绍、设备历史查询、设备风险查询、维修建议、高风险设备排行、缺少设备编号追问、API 422 错误提示和前端 Debug 文案均通过乱码检查。

## 残留风险
- 未发现残留乱码。
- Windows PowerShell 控制台可能把正常 UTF-8 中文渲染为乱码；治理判断以文件 UTF-8 strict 解码和 Python 字符级检查为准。
