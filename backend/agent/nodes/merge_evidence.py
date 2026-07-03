"""merge_evidence_node —— 证据合并节点。

职责：
把原始 tool_results 整理成统一的 EvidencePacket。
后续 generate_answer_node 只看 EvidencePacket，不直接看 tool_results。
"""

from __future__ import annotations

from typing import Any

from backend.agent.state import AfcAgentState


def merge_evidence_node(state: AfcAgentState) -> dict[str, Any]:
    """合并工具结果为统一证据包。

    输入：tool_results, tool_trace, query_understanding
    输出：evidence_packet
    """
    tool_results = state.get("tool_results", {})
    tool_trace = state.get("tool_trace", [])
    query_understanding = state.get("query_understanding", {})
    assetnum = query_understanding.get("assetnum")

    evidence_packet: dict[str, Any] = {
        "assetnum": assetnum,
        "device_profile": None,
        "history_summary": None,
        "risk_prediction": None,
        "warning": None,
        "maintenance_advice": None,
        "manual_evidence": None,
        "data_overview": None,
        "high_risk_devices": None,
        "sources": [t.get("tool") for t in tool_trace if t.get("status") == "success"],
        "missing_evidence": [],
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

    # ── 根据 query_understanding 初步判断缺失证据 ──
    task_type = query_understanding.get("task_type", "")
    missing: list[str] = []

    if task_type in ("risk_query", "risk_explanation", "risk_and_advice_query", "full_diagnosis"):
        if not evidence_packet["risk_prediction"]:
            missing.append("risk_prediction")

    if task_type in ("advice_query", "risk_and_advice_query", "full_diagnosis"):
        if not evidence_packet["maintenance_advice"]:
            missing.append("maintenance_advice")

    if task_type in ("history_query", "full_diagnosis"):
        if not evidence_packet["history_summary"]:
            missing.append("history_summary")

    if task_type == "manual_query" or (query_understanding.get("needs_rag")):
        if not evidence_packet["manual_evidence"]:
            missing.append("manual_evidence")

    evidence_packet["missing_evidence"] = missing

    return {"evidence_packet": evidence_packet}
