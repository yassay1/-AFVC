"""AFC Agent v0.3 八节点实现。

节点顺序：
prepare_context → understand_query → plan_tools → execute_tools
→ merge_evidence → evaluate_evidence → generate_answer → update_memory
"""

from backend.agent.nodes.prepare_context import prepare_context_node
from backend.agent.nodes.understand_query import understand_query_node
from backend.agent.nodes.plan_tools import plan_tools_node
from backend.agent.nodes.execute_tools import execute_tools_node
from backend.agent.nodes.merge_evidence import merge_evidence_node
from backend.agent.nodes.evaluate_evidence import evaluate_evidence_node
from backend.agent.nodes.generate_answer import generate_answer_node
from backend.agent.nodes.update_memory import update_memory_node

# ── 向后兼容：旧三节点 API ─────────────────────────────────────────
# 测试和旧代码仍然可以从 backend.agent.nodes 导入以下名称

from backend.agent.nodes.compat import (
    parse_intent_node,
    reason_act_node,
    generate_report_node,
    parse_question_node,
    resolve_asset_node,
    route_task_node,
    execute_tools_node as compat_execute_tools_node,
    merge_evidence_node as compat_merge_evidence_node,
    TASK_TOOL_MAP,
    _rule_based_parse_task_type,
    _extract_assetnum_from_query,
    _has_reference_pronoun,
    _has_device_switch,
    _is_global_question,
    _resolve_multiturn_context,
)

__all__ = [
    "prepare_context_node",
    "understand_query_node",
    "plan_tools_node",
    "execute_tools_node",
    "merge_evidence_node",
    "evaluate_evidence_node",
    "generate_answer_node",
    "update_memory_node",
    # 兼容
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
