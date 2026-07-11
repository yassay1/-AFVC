"""AFC 适配器层 —— 读取外部模型结果并转换为系统统一格式。

Adapter 负责：
- 定位和读取外部数据文件（CSV/数据库/API）
- 校验必要字段
- 清洗和标准化数据
- 返回经 Schema 校验的标准结果

Adapter 不负责：
- 调用 LLM
- 业务计算（综合概率等，由 domain/ 负责）
- 生成自然语言报告
- FastAPI 请求处理
"""

from backend.adapters.fault_prediction_adapter import (
    load_fault_prediction_table,
    get_fault_type_scores,
    has_fault_prediction_file,
)

__all__ = [
    "load_fault_prediction_table",
    "get_fault_type_scores",
    "has_fault_prediction_file",
]
