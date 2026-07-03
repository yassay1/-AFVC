"""execute_tools_node —— 工具执行节点（v0.3.0 升级）。

职责：
只执行 tool_plan 中的工具调用，不做任何推理。

v0.3.0 升级：
- 参数保护：缺少 assetnum 返回结构化错误，不暴露 Pydantic crash
- 空 tool_calls 正常跳过
- 工具去重：当前按 tool_name 去重（单设备场景足够）

工具去重说明：
当前按 tool_name 去重（同一工具名不重复执行，除非首次返回 error）。
这一设计限制在"单设备单轮诊断"场景下合理——每个工具通常只调用一次。
如需在单轮内对多设备分别调用同一工具，应改为以 (tool_name, args_hash) 作为去重键。
当前 MVP 暂不实现此增强。
"""

from __future__ import annotations

import time
from typing import Any

from backend.agent.state import AfcAgentState
from backend.agent.tools import TOOL_BY_NAME

MAX_TOOL_CALLS = 5

# 必须有有效 assetnum 的工具
_ASSET_REQUIRED_TOOLS = {
    "get_integrated_analysis_tool",
    "predict_device_risk_tool",
    "get_device_history_tool",
    "get_maintenance_advice_tool",
}


def _validate_tool_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """校验工具参数。返回 None 表示通过，返回 dict 表示错误。"""
    if tool_name in _ASSET_REQUIRED_TOOLS:
        assetnum = args.get("assetnum", "").strip() if isinstance(args.get("assetnum"), str) else ""
        if not assetnum:
            return {
                "status": "error",
                "error_type": "missing_required_argument",
                "tool": tool_name,
                "message": f"调用 {tool_name} 需要设备编号 assetnum，但当前问题没有提供设备编号。请先提供设备编号（如 1000029970）后再查询。",
            }
    return None


def execute_tools_node(state: AfcAgentState) -> dict[str, Any]:
    """执行工具计划（v0.3.0 升级版）。

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

    # 空工具列表 → 正常跳过
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

        # ── 白名单校验 ──
        if tool_name not in TOOL_BY_NAME:
            err_msg = f"工具 {tool_name} 不在白名单中，跳过"
            errors.append(err_msg)
            tool_trace.append({
                "tool": tool_name, "args": args, "purpose": purpose,
                "status": "error", "error_type": "not_in_whitelist", "message": err_msg,
                "duration_ms": 0,
            })
            continue

        # ── 参数校验 ──
        validation_error = _validate_tool_args(tool_name, args)
        if validation_error is not None:
            tool_results[tool_name] = validation_error
            tool_trace.append({
                "tool": tool_name, "args": args, "purpose": purpose,
                "status": "error",
                "error_type": validation_error["error_type"],
                "message": validation_error["message"],
                "duration_ms": 0,
            })
            errors.append(validation_error["message"])
            continue

        # ── 去重：同一个工具不重复执行（除非首次返回 error）──
        if tool_name in tool_results and isinstance(tool_results[tool_name], dict):
            if tool_results[tool_name].get("status") == "success":
                continue
        elif tool_name in tool_results:
            continue

        t_start = time.time()
        try:
            tool = TOOL_BY_NAME[tool_name]

            # ── 自动注入默认参数 ──
            if tool_name in _ASSET_REQUIRED_TOOLS:
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
            tool_results[tool_name] = {
                "status": "error",
                "error_type": "tool_execution_error",
                "tool": tool_name,
                "message": f"工具 {tool_name} 执行异常：{error_msg}",
            }
            tool_trace.append({
                "tool": tool_name,
                "args": args,
                "purpose": purpose,
                "status": "error",
                "error_type": "tool_execution_error",
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
