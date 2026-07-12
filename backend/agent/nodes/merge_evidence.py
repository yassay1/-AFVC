"""merge_evidence_node —— 证据合并节点（v0.3.0 升级）。

职责：
把原始 tool_results 整理成统一的 EvidencePacket。
后续 generate_answer_node 只看 EvidencePacket，不直接看 tool_results。

v0.3.0 升级：
- 新增 tool_errors 字段，承载工具执行失败信息
- 区分成功结果和失败结果
- 空证据包对于 direct_chat/capability_intro/ask_for_assetnum 是正常的
"""

from __future__ import annotations

from typing import Any

from backend.agent.state import AfcAgentState


def merge_evidence_node(state: AfcAgentState) -> dict[str, Any]:
    """合并工具结果为统一证据包（v0.3.0 升级版）。

    输入：tool_results, tool_trace, query_understanding
    输出：evidence_packet（含 tool_errors）
    """
    tool_results = state.get("tool_results", {})
    tool_trace = state.get("tool_trace", [])
    query_understanding = state.get("query_understanding", {})
    assetnum = query_understanding.get("assetnum")

    # ── 收集工具错误 ──
    tool_errors: list[dict[str, Any]] = []
    for trace_item in tool_trace:
        if trace_item.get("status") == "error":
            tool_errors.append({
                "tool": trace_item.get("tool", ""),
                "error_type": trace_item.get("error_type", "tool_execution_error"),
                "message": trace_item.get("message", "未知工具错误"),
                "args": trace_item.get("args", {}),
            })

    # 也从 tool_results 中收集错误（有些错误可能在调用前就产生了）
    for tool_name, result in tool_results.items():
        if isinstance(result, dict) and result.get("status") == "error":
            already_recorded = any(e.get("tool") == tool_name for e in tool_errors)
            if not already_recorded:
                tool_errors.append({
                    "tool": tool_name,
                    "error_type": result.get("error_type", "tool_execution_error"),
                    "message": result.get("message", str(result)),
                    "args": {},
                })

    evidence_packet: dict[str, Any] = {
        "assetnum": assetnum,
        "device_profile": None,
        "history_summary": None,
        "risk_prediction": None,
        "warning": None,
        "maintenance_advice": None,
        "manual_evidence": None,
        "fault_prediction": None,
        "data_overview": None,
        "high_risk_devices": None,
        "available_evidence": [],
        "sources": [t.get("tool") for t in tool_trace if t.get("status") == "success"],
        "missing_evidence": [],
        "tool_errors": tool_errors,
    }

    # ── 从 get_integrated_analysis_tool 提取 ──
    integrated = tool_results.get("get_integrated_analysis_tool", {})
    if isinstance(integrated, dict) and integrated.get("status") == "success":
        evidence_packet["device_profile"] = integrated.get("device_profile", {})
        evidence_packet["assetnum"] = (
            evidence_packet["assetnum"]
            or integrated.get("assetnum")
            or evidence_packet["device_profile"].get("assetnum")
        )
        evidence_packet["history_summary"] = integrated.get("history_summary", {})
        evidence_packet["risk_prediction"] = integrated.get("risk_prediction", {})
        risk = integrated.get("risk_prediction", {})
        evidence_packet["warning"] = {
            "warning_level": risk.get("warning_level"),
            "suggested_inspection_window": risk.get("suggested_inspection_window"),
            "warning_reason": risk.get("warning_reason"),
        }
        evidence_packet["maintenance_advice"] = integrated.get("maintenance_advice", {})
        evidence_packet["fault_prediction"] = integrated.get("fault_prediction")

    # ── 从 predict_device_risk_tool 提取 ──
    risk = tool_results.get("predict_device_risk_tool", {})
    if isinstance(risk, dict) and risk.get("status") == "success":
        evidence_packet["assetnum"] = evidence_packet["assetnum"] or risk.get("assetnum")
        if not evidence_packet["risk_prediction"]:
            evidence_packet["risk_prediction"] = risk
        if not evidence_packet["device_profile"]:
            evidence_packet["device_profile"] = {
                "assetnum": risk.get("assetnum"),
                "station_name": risk.get("station_name"),
                "line": risk.get("line"),
                "brand": risk.get("brand"),
                "subsystem": risk.get("subsystem"),
            }
        if not evidence_packet["warning"]:
            evidence_packet["warning"] = {
                "warning_level": risk.get("warning_level"),
                "suggested_inspection_window": risk.get("suggested_inspection_window"),
                "warning_reason": risk.get("warning_reason"),
            }

    # ── 从 get_maintenance_advice_tool 提取 ──
    advice = tool_results.get("get_maintenance_advice_tool", {})
    if isinstance(advice, dict) and advice.get("status") == "success":
        evidence_packet["assetnum"] = evidence_packet["assetnum"] or advice.get("assetnum")
        evidence_packet["maintenance_advice"] = advice
        if not evidence_packet["device_profile"]:
            evidence_packet["device_profile"] = {
                "assetnum": advice.get("assetnum"),
                "station_name": advice.get("station_name"),
                "line": advice.get("line"),
                "brand": advice.get("brand"),
                "subsystem": advice.get("subsystem"),
            }

    # ── 从 predict_device_fault_type_tool 提取 ──
    fault_type = tool_results.get("predict_device_fault_type_tool", {})
    if isinstance(fault_type, dict) and fault_type.get("status") in ("success", "unavailable"):
        if not evidence_packet["fault_prediction"]:
            evidence_packet["fault_prediction"] = fault_type

    # ── 从 search_maintenance_manual_tool 提取 ──
    manual = tool_results.get("search_maintenance_manual_tool", {})
    if isinstance(manual, dict) and manual.get("status") == "success":
        evidence_packet["manual_evidence"] = manual.get("results", [])

    # ── 从 get_device_history_tool 提取 ──
    history = tool_results.get("get_device_history_tool", {})
    if isinstance(history, dict) and history.get("status") == "success":
        if not evidence_packet["history_summary"]:
            evidence_packet["history_summary"] = {"raw": history}

    # ── 从 get_data_summary_tool 提取 ──
    data_summary = tool_results.get("get_data_summary_tool", {})
    if isinstance(data_summary, dict) and data_summary.get("status") == "success":
        evidence_packet["data_overview"] = data_summary

    # ── 从 get_high_risk_devices_tool 提取 ──
    high_risk = tool_results.get("get_high_risk_devices_tool", {})
    if isinstance(high_risk, dict) and high_risk.get("status") == "success":
        evidence_packet["high_risk_devices"] = high_risk.get("devices", [])

    evidence_fields = (
        "risk_prediction", "history_summary", "maintenance_advice",
        "manual_evidence", "fault_prediction", "data_overview",
        "high_risk_devices", "device_profile", "warning",
    )
    evidence_packet["available_evidence"] = [
        name for name in evidence_fields if evidence_packet.get(name)
    ]

    # ── 根据当前工具计划计算预期与缺失证据 ──
    answer_mode = state.get("tool_plan", {}).get("answer_mode", "")
    # 只有 evidence_based 才需要检查缺失证据
    if answer_mode == "evidence_based":
        business_goal = query_understanding.get("business_goal")
        expected = []
        for call in state.get("tool_plan", {}).get("tool_calls", []):
            for item in call.get("expected_evidence", []):
                if item not in expected:
                    expected.append(item)
        fallback = {
            "device_risk": ["risk_prediction"], "device_history": ["history_summary"],
            "device_advice": ["maintenance_advice"], "manual_search": ["manual_evidence"],
            "fault_type_prediction": ["fault_prediction"], "data_overview": ["data_overview"],
            "high_risk_ranking": ["high_risk_devices"],
            "full_diagnosis": ["device_profile", "history_summary", "risk_prediction", "maintenance_advice"],
        }
        if not expected:
            expected = fallback.get(business_goal, [])
        available = set(evidence_packet["available_evidence"])
        evidence_packet["missing_evidence"] = [item for item in expected if item not in available]

    return {"evidence_packet": evidence_packet}
