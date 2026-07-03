"""AFC Agent v0.3 八节点实现。

节点顺序：
prepare_context → understand_query → plan_tools → execute_tools
→ merge_evidence → evaluate_evidence → generate_answer → update_memory

⚠️ 注意：旧三节点兼容函数不在本模块默认导出中。
如需兼容旧 API，请显式从 compat 子模块导入：
    from backend.agent.nodes.compat import parse_intent_node, reason_act_node, ...
"""

from backend.agent.nodes.prepare_context import prepare_context_node
from backend.agent.nodes.understand_query import understand_query_node
from backend.agent.nodes.plan_tools import plan_tools_node
from backend.agent.nodes.execute_tools import execute_tools_node
from backend.agent.nodes.merge_evidence import merge_evidence_node
from backend.agent.nodes.evaluate_evidence import evaluate_evidence_node
from backend.agent.nodes.generate_answer import generate_answer_node
from backend.agent.nodes.update_memory import update_memory_node

# ── 向后兼容：旧三节点 API（⚠️ LEGACY — 仅用于旧测试）────────────
# 这些名称与 v0.3 节点函数同名（execute_tools_node, merge_evidence_node），
# 如果直接导入会遮蔽 v0.3 版本。因此只以 _compat 后缀导出，旧代码如需使用
# 请改为从 backend.agent.nodes.compat 显式导入。

from backend.agent.nodes import compat as _compat

# 兼容别名（带 _compat 后缀，避免名称冲突）
parse_intent_node = _compat.parse_intent_node
reason_act_node = _compat.reason_act_node
generate_report_node = _compat.generate_report_node
parse_question_node = _compat.parse_question_node
resolve_asset_node = _compat.resolve_asset_node
route_task_node = _compat.route_task_node

# 兼容工具函数（无冲突，可直接导出）
TASK_TOOL_MAP = _compat.TASK_TOOL_MAP
_rule_based_parse_task_type = _compat._rule_based_parse_task_type
_extract_assetnum_from_query = _compat._extract_assetnum_from_query
_has_reference_pronoun = _compat._has_reference_pronoun
_has_device_switch = _compat._has_device_switch
_is_global_question = _compat._is_global_question
_resolve_multiturn_context = _compat._resolve_multiturn_context

__all__ = [
    # v0.3 八节点
    "prepare_context_node",
    "understand_query_node",
    "plan_tools_node",
    "execute_tools_node",
    "merge_evidence_node",
    "evaluate_evidence_node",
    "generate_answer_node",
    "update_memory_node",
    # 兼容旧 API（⚠️ LEGACY）
    "parse_intent_node",
    "reason_act_node",
    "generate_report_node",
    "parse_question_node",
    "resolve_asset_node",
    "route_task_node",
    "TASK_TOOL_MAP",
    "_rule_based_parse_task_type",
    "_extract_assetnum_from_query",
    "_has_reference_pronoun",
    "_has_device_switch",
    "_is_global_question",
    "_resolve_multiturn_context",
]
