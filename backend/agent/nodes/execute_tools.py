"""execute_tools_node —— 工具执行节点。

职责：
只执行 tool_plan 中的工具调用，不做任何推理。
"""

from __future__ import annotations

import time
from typing import Any

from backend.agent.state import AfcAgentState
from backend.agent.tools import TOOL_BY_NAME

MAX_TOOL_CALLS = 5


def execute_tools_node(state: AfcAgentState) -> dict[str, Any]:
    """执行工具计划。

    输入：tool_plan, query_understanding
    输出：tool_results, tool_trace, tool_loop_count
    """
    tool_plan = state.get("tool_plan", {})
    tool_calls = tool_plan.get("tool_calls", [])
    query_understanding = state.get("query_understanding", {})
    assetnum = query_understanding.get("assetnum")
    errors: list[str] = list(state.get("errors", []))
    tool_loop_count = state.get("tool_loop_count", 0) + 1

    tool_results: dict[str, Any] = dict(state.get("tool_results", {}))
    tool_trace: list[dict[str, Any]] = list(state.get("tool_trace", []))

    if not tool_calls:
        return {
            "tool_results": tool_results,
            "tool_trace": tool_trace,
            "errors": errors,
            "tool_loop_count": tool_loop_count,
        }

    for call_item in tool_calls[:MAX_TOOL_CALLS]:
        tool_name = call_item.get("tool_name", "")
        args = dict(call_item.get("args", {}))
        purpose = call_item.get("purpose", "")

        # 白名单校验
        if tool_name not in TOOL_BY_NAME:
            errors.append(f"工具 {tool_name} 不在白名单中，跳过")
            continue

        # 去重：同一个工具不重复执行（除非参数不同）
        if tool_name in tool_results and isinstance(tool_results[tool_name], dict):
            if tool_results[tool_name].get("status") == "success":
                continue
        elif tool_name in tool_results:
            continue

        t_start = time.time()
        try:
            tool = TOOL_BY_NAME[tool_name]

            # 为需要 assetnum 的工具自动注入 assetnum
            if tool_name in {
                "get_device_history_tool", "get_integrated_analysis_tool",
                "predict_device_risk_tool", "get_maintenance_advice_tool",
            }:
                args.setdefault("assetnum", assetnum)
            if tool_name == "get_data_summary_tool":
                args.setdefault("top_n", 10)
            if tool_name == "get_high_risk_devices_tool":
                args.setdefault("top_n", 10)
            if tool_name == "get_device_history_tool":
                args.setdefault("limit", 50)
            if tool_name == "get_integrated_analysis_tool":
                args.setdefault("history_limit", 50)

            result = tool.invoke(args)
            duration_ms = (time.time() - t_start) * 1000

            tool_results[tool_name] = result
            tool_trace.append({
                "tool": tool_name,
                "args": args,
                "purpose": purpose,
                "status": result.get("status", "success") if isinstance(result, dict) else "success",
                "duration_ms": round(duration_ms, 1),
            })
        except Exception as exc:
            duration_ms = (time.time() - t_start) * 1000
            error_msg = str(exc)
            tool_results[tool_name] = {"status": "error", "message": error_msg}
            tool_trace.append({
                "tool": tool_name,
                "args": args,
                "purpose": purpose,
                "status": "error",
                "message": error_msg,
                "duration_ms": round(duration_ms, 1),
            })
            errors.append(f"工具 {tool_name} 调用失败：{error_msg}")

    return {
        "tool_results": tool_results,
        "tool_trace": tool_trace,
        "errors": errors,
        "tool_loop_count": tool_loop_count,
    }
