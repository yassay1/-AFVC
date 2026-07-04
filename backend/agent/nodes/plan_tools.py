"""plan_tools_node —— 工具规划节点（v0.3.0 升级）。

职责：
根据 QueryUnderstanding（route + business_goal）+ ContextPacket + 已有证据，
规划工具调用并决定 answer_mode。

v0.3.0 升级：
- 使用 route + business_goal 替代 task_type 做路由
- 新增 answer_mode 字段
- unknown/fallback 不再默认调用 get_integrated_analysis_tool
"""

from __future__ import annotations

import json
from typing import Any

from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import ToolPlan, route_to_task_type
from backend.agent.state import AfcAgentState, NO_DEVICE_ROUTES, NO_TOOL_ROUTES
from backend.agent.tools import TOOL_BY_NAME
from backend.core.llm import get_parse_llm


# ── 工具描述 ──────────────────────────────────────────────────────

def _build_tool_descriptions() -> str:
    """构建可用工具列表描述。"""
    lines: list[str] = []
    for name, tool in TOOL_BY_NAME.items():
        desc = getattr(tool, "description", "无描述")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


# ── route + business_goal → (tools, answer_mode) 映射 ─────────

# 需要 assetnum 的工具白名单
_ASSET_REQUIRED_TOOLS = {
    "get_integrated_analysis_tool",
    "predict_device_risk_tool",
    "get_device_history_tool",
    "get_maintenance_advice_tool",
}

ROUTE_TOOL_PLAN: dict[str, dict[str, Any]] = {
    # ── 不需要工具 ──
    "direct_chat": {
        "tool_names": [],
        "answer_mode": "direct_chat",
        "reason": "用户闲聊/问候，不需要调用业务工具",
    },
    "capability_query": {
        "tool_names": [],
        "answer_mode": "capability_intro",
        "reason": "用户询问系统能力，不需要调用业务工具",
    },
    "needs_clarification": {
        "tool_names": [],
        "answer_mode": "ask_for_assetnum",
        "reason": "用户想做业务分析但缺少设备编号，需要追问",
    },
    "unsupported": {
        "tool_names": [],
        "answer_mode": "unsupported",
        "reason": "用户问题超出系统能力范围",
    },

    # ── 全局业务 ──
    "business_global__data_overview": {
        "tool_names": ["get_data_summary_tool"],
        "answer_mode": "evidence_based",
        "reason": "用户需要全局数据概览",
    },
    "business_global__high_risk_ranking": {
        "tool_names": ["get_high_risk_devices_tool"],
        "answer_mode": "evidence_based",
        "reason": "用户需要高风险设备清单",
    },

    # ── 单设备业务 ──
    "business_device__device_risk": {
        "tool_names": ["predict_device_risk_tool"],
        "answer_mode": "evidence_based",
        "reason": "用户查询单设备复发风险",
    },
    "business_device__device_history": {
        "tool_names": ["get_device_history_tool"],
        "answer_mode": "evidence_based",
        "reason": "用户查询单设备历史工单",
    },
    "business_device__device_advice": {
        "tool_names": ["get_maintenance_advice_tool"],
        "answer_mode": "evidence_based",
        "reason": "用户查询单设备维修建议",
    },
    "business_device__full_diagnosis": {
        "tool_names": ["get_integrated_analysis_tool"],
        "answer_mode": "evidence_based",
        "reason": "用户需要单设备完整诊断",
    },
    "business_device__manual_search": {
        "tool_names": ["search_maintenance_manual_tool"],
        "answer_mode": "evidence_based",
        "reason": "用户需要维修手册检索",
    },
}


def _plan_by_route(
    query_understanding: dict[str, Any],
    state: AfcAgentState,
) -> dict[str, Any]:
    """根据 route + business_goal 规划工具调用和 answer_mode。"""
    route = query_understanding.get("route", "direct_chat")
    business_goal = query_understanding.get("business_goal")
    assetnum = query_understanding.get("assetnum")

    # business_device 但缺少 assetnum → 追问
    if route == "business_device" and not assetnum:
        return {
            "tool_calls": [],
            "use_existing_evidence": False,
            "reason": "缺少设备编号，无法规划工具",
            "answer_mode": "ask_for_assetnum",
            "answer_policy": {"missing_asset": True},
        }

    # 查找规划表
    plan_key = route if route not in ("business_global", "business_device") else f"{route}__{business_goal}"
    plan = ROUTE_TOOL_PLAN.get(plan_key)

    if plan is None:
        # 未知组合：不默认调用工具
        if route in NO_TOOL_ROUTES:
            return {
                "tool_calls": [],
                "use_existing_evidence": False,
                "reason": f"非业务路由 {route}，不需要工具",
                "answer_mode": "direct_chat",
                "answer_policy": {},
            }
        # 业务路由但无匹配 plan → 回退为 full_diagnosis（仅当有 assetnum）
        if assetnum:
            plan = ROUTE_TOOL_PLAN.get("business_device__full_diagnosis", {})
        else:
            return {
                "tool_calls": [],
                "use_existing_evidence": False,
                "reason": f"未知业务组合 route={route} goal={business_goal} 且无设备编号",
                "answer_mode": "ask_for_assetnum",
                "answer_policy": {},
            }

    # 构建 tool_calls
    tool_calls = []
    for tool_name in plan.get("tool_names", []):
        args: dict[str, Any] = {}
        if assetnum and tool_name in _ASSET_REQUIRED_TOOLS:
            args["assetnum"] = assetnum
        if tool_name == "get_data_summary_tool":
            args["top_n"] = 10
        if tool_name == "get_high_risk_devices_tool":
            args["top_n"] = 10
        if tool_name == "get_device_history_tool":
            args["assetnum"] = assetnum
            args["limit"] = 50
        if tool_name == "get_integrated_analysis_tool":
            args["assetnum"] = assetnum
            args["history_limit"] = 50
        if tool_name == "search_maintenance_manual_tool":
            args["query"] = state.get("query", "")
            args["assetnum"] = assetnum

        tool_calls.append({
            "tool_name": tool_name,
            "args": args,
            "purpose": plan.get("reason", ""),
            "expected_evidence": [],
        })

    return {
        "tool_calls": tool_calls,
        "use_existing_evidence": len(tool_calls) == 0,
        "reason": plan.get("reason", ""),
        "answer_mode": plan.get("answer_mode", "direct_chat"),
        "answer_policy": {
            "must_not_predict_exact_failure_date": True,
            "must_answer_with_risk_window": business_goal == "device_risk" or business_goal == "full_diagnosis",
        },
    }


TOOL_PLAN_OUTPUT_CONTRACT = """## ToolPlan JSON output contract
Return exactly one JSON object that validates against ToolPlan.

Root object MUST contain all of these fields:
- tool_calls: array
- use_existing_evidence: boolean
- reason: non-empty string
- answer_mode: one of direct_chat, capability_intro, ask_for_assetnum, evidence_based, unsupported
- answer_policy: object

Each item in tool_calls MUST contain all of these fields:
- tool_name: string, must be one of the available tool names
- args: object
- purpose: non-empty string
- expected_evidence: array of strings

Field name rules:
- NEVER use a field named "tool".
- ALWAYS use "tool_name" for the tool name.
- If repairing invalid JSON that used "tool", rename it to "tool_name" and add any missing required fields.
"""


TOOL_PLAN_JSON_SKELETON = """## Required JSON skeleton
{
  "tool_calls": [
    {
      "tool_name": "<available_tool_name>",
      "args": {},
      "purpose": "<why this tool is needed>",
      "expected_evidence": ["<evidence_field_name>"]
    }
  ],
  "use_existing_evidence": false,
  "reason": "<why this plan satisfies the query>",
  "answer_mode": "evidence_based",
  "answer_policy": {}
}

For no-tool plans, use:
{
  "tool_calls": [],
  "use_existing_evidence": true,
  "reason": "<why no tool is needed>",
  "answer_mode": "<direct_chat|capability_intro|ask_for_assetnum|unsupported>",
  "answer_policy": {}
}
"""


DEVICE_ADVICE_FEW_SHOT = """## Few-shot examples
Input:
{
  "route": "business_device",
  "business_goal": "device_advice",
  "assetnum": "1000029970",
  "needs_tools": true
}

Correct ToolPlan output:
{
  "tool_calls": [
    {
      "tool_name": "get_maintenance_advice_tool",
      "args": {"assetnum": "1000029970"},
      "purpose": "Get maintenance and inspection advice for device 1000029970.",
      "expected_evidence": ["maintenance_advice"]
    }
  ],
  "use_existing_evidence": false,
  "reason": "business_goal=device_advice requires maintenance advice evidence for the target device.",
  "answer_mode": "evidence_based",
  "answer_policy": {
    "must_not_predict_exact_failure_date": true,
    "must_answer_with_risk_window": false
  }
}

Incorrect output, do not imitate:
{
  "tool_calls": [
    {"tool": "get_maintenance_advice_tool", "args": {"assetnum": "1000029970"}}
  ],
  "answer_mode": "evidence_based"
}
"""


PLAN_TOOLS_SYSTEM = """你是 AFC 智能运维 Agent 的工具规划器。

你的任务是：根据问题理解和上下文，规划需要调用的工具并决定 answer_mode。
你只规划工具，不回答用户问题。

## 可用工具
{tool_descriptions}

## answer_mode 语义
- direct_chat: 闲聊，不调工具
- capability_intro: 系统能力介绍，不调工具
- ask_for_assetnum: 缺设备编号，追问
- evidence_based: 需要工具证据
- unsupported: 超出能力范围

## 规划原则（按 route 决定）
1. direct_chat → tool_calls=[], answer_mode=direct_chat
2. capability_query → tool_calls=[], answer_mode=capability_intro
3. needs_clarification → tool_calls=[], answer_mode=ask_for_assetnum
4. unsupported → tool_calls=[], answer_mode=unsupported
5. business_global + data_overview → get_data_summary_tool, answer_mode=evidence_based
6. business_global + high_risk_ranking → get_high_risk_devices_tool, answer_mode=evidence_based
7. business_device + 缺 assetnum → tool_calls=[], answer_mode=ask_for_assetnum
8. business_device + device_risk → predict_device_risk_tool, answer_mode=evidence_based
9. business_device + device_history → get_device_history_tool, answer_mode=evidence_based
10. business_device + device_advice → get_maintenance_advice_tool, answer_mode=evidence_based
11. business_device + full_diagnosis → get_integrated_analysis_tool, answer_mode=evidence_based
12. business_device + manual_search → search_maintenance_manual_tool, answer_mode=evidence_based
13. unknown / fallback → 不要默认调用 get_integrated_analysis_tool

## 输出
{output_contract}

{json_skeleton}

{few_shot}

只输出一个合法的 ToolPlan JSON 对象，不要输出 markdown 或解释文字。"""


def _build_plan_tools_prompt(query_understanding: dict[str, Any], evidence_packet: dict[str, Any]) -> str:
    """Build the user prompt for ToolPlan generation."""
    return (
        f"{TOOL_PLAN_OUTPUT_CONTRACT}\n"
        f"{TOOL_PLAN_JSON_SKELETON}\n"
        f"{DEVICE_ADVICE_FEW_SHOT}\n"
        f"## 问题理解\n{json.dumps(query_understanding, ensure_ascii=False, indent=2)}\n"
        f"\n## 已有证据\n{json.dumps(evidence_packet, ensure_ascii=False, indent=2) if evidence_packet else '无'}\n"
        "\n请输出完整 ToolPlan JSON。必须使用 tool_name 字段，禁止使用 tool 字段。"
    )


def plan_tools_node(state: AfcAgentState) -> dict[str, Any]:
    """规划工具调用（v0.3.0 升级版）。

    输入：query_understanding (route + business_goal), context_packet, evidence_packet
    输出：tool_plan (含 answer_mode) + answer_policy
    """
    query_understanding = state.get("query_understanding", {})
    route = query_understanding.get("route", "direct_chat")
    business_goal = query_understanding.get("business_goal")
    assetnum = query_understanding.get("assetnum")
    needs_tools = query_understanding.get("needs_tools", route in ("business_global", "business_device"))
    errors: list[str] = list(state.get("errors", []))
    evidence_packet = state.get("evidence_packet", {})

    # ── 不需要工具的 route → 直接返回 ──
    if route in NO_TOOL_ROUTES:
        plan = _plan_by_route(query_understanding, state)
        return {
            "tool_plan": plan,
            "answer_policy": plan.get("answer_policy", {}),
            "errors": errors,
        }

    # ── business_device 但缺少 assetnum ──
    if route == "business_device" and not assetnum:
        plan = _plan_by_route(query_understanding, state)
        return {
            "tool_plan": plan,
            "answer_policy": plan.get("answer_policy", {}),
            "errors": errors,
        }

    # ── 需要工具：尝试 LLM 规划 ──
    tool_plan: dict[str, Any] | None = None
    try:
        llm = get_parse_llm()
        tool_descriptions = _build_tool_descriptions()
        system_prompt = PLAN_TOOLS_SYSTEM.format(
            tool_descriptions=tool_descriptions,
            output_contract=TOOL_PLAN_OUTPUT_CONTRACT,
            json_skeleton=TOOL_PLAN_JSON_SKELETON,
            few_shot=DEVICE_ADVICE_FEW_SHOT,
        )

        prompt = _build_plan_tools_prompt(query_understanding, evidence_packet)
        repair_context = (
            f"{prompt}\n\n"
            "Repair reminder: convert any tool_calls[].tool field to tool_calls[].tool_name. "
            "Every tool call must include tool_name, args, purpose, expected_evidence. "
            "The root object must include tool_calls, use_existing_evidence, reason, answer_mode, answer_policy. "
            "Do not return the short schema {tool_calls:[{tool,args}],answer_mode}. "
            "Use this exact shape:\n"
            f"{TOOL_PLAN_JSON_SKELETON}"
        )

        result = call_llm_json(
            llm=llm,
            prompt=prompt,
            schema=ToolPlan,
            system_prompt=system_prompt,
            max_repair_attempts=2,
            repair_context=repair_context,
        )
        tool_plan = result.model_dump()
    except Exception as exc:
        errors.append(f"LLM 工具规划不可用，使用规则兜底：{str(exc)}")

    # 规则兜底
    if tool_plan is None:
        tool_plan = _plan_by_route(query_understanding, state)

    # 如果 tool_calls 为空，使用规则兜底
    if not tool_plan.get("tool_calls") and needs_tools:
        tool_plan = _plan_by_route(query_understanding, state)

    # ── 后处理：确保 answer_mode 存在 ──
    if not tool_plan.get("answer_mode"):
        tool_plan["answer_mode"] = _plan_by_route(query_understanding, state).get("answer_mode", "direct_chat")

    # ── 后处理：manual_query 确保有 RAG 工具 ──
    if business_goal == "manual_search" or query_understanding.get("needs_rag"):
        has_rag = any(
            tc.get("tool_name") == "search_maintenance_manual_tool"
            for tc in tool_plan.get("tool_calls", [])
        )
        if not has_rag and "search_maintenance_manual_tool" in TOOL_BY_NAME:
            tool_plan.setdefault("tool_calls", []).append({
                "tool_name": "search_maintenance_manual_tool",
                "args": {"query": state.get("query", ""), "assetnum": assetnum},
                "purpose": "按用户要求检索维修手册",
                "expected_evidence": ["manual_steps", "manual_cause"],
            })

    # ── 后处理：为需要 assetnum 的工具补齐参数 ──
    if assetnum:
        for tc in tool_plan.get("tool_calls", []):
            if not tc.get("args", {}).get("assetnum") and tc.get("tool_name") in _ASSET_REQUIRED_TOOLS:
                tc.setdefault("args", {})["assetnum"] = assetnum

    return {
        "tool_plan": tool_plan,
        "answer_policy": tool_plan.get("answer_policy", {}),
        "errors": errors,
    }
