"""Reusable presentation helpers for the Streamlit frontend."""
from __future__ import annotations

from html import escape
from typing import Any

ROUTE_LABELS = {
    "direct_chat": "普通对话",
    "capability_query": "能力咨询",
    "conversation": "AFC 概念解释",
    "business_global": "全局业务",
    "business_device": "设备业务",
    "needs_clarification": "等待补充信息",
    "unsupported": "超出系统范围",
}

BUSINESS_GOAL_LABELS = {
    "data_overview": "数据概览",
    "high_risk_ranking": "高风险设备分析",
    "device_risk": "设备风险预测",
    "device_history": "设备历史分析",
    "device_advice": "维护建议",
    "fault_type_prediction": "故障类型预测",
    "full_diagnosis": "设备综合诊断",
    "manual_search": "维修手册检索",
    "general_explanation": "AFC 一般解释",
    "open_analysis": "开放组合分析",
}


def display_label(value: Any, mapping: dict[str, str], empty: str = "尚未识别") -> str:
    """Map an internal enum to a user-facing label with a safe fallback."""
    if value is None or value == "":
        return empty
    text = str(value)
    return mapping.get(text, text)


def render_sidebar_brand(st_module) -> None:
    st_module.markdown(
        """
        <div class="afc-brand">
          <div class="afc-brand-mark">AFC</div>
          <div class="afc-brand-title">AFC 智能运维</div>
          <div class="afc-brand-subtitle">Fault Prediction Agent</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(
    st_module,
    *,
    title: str,
    english_title: str,
    description: str,
    llm_enabled: bool,
    scene: str | None = None,
) -> None:
    mode = "LLM 模式" if llm_enabled else "规则兜底"
    scene_chip = f'<span class="afc-chip afc-chip--route">当前场景：{escape(scene)}</span>' if scene else ""
    st_module.markdown(
        f"""
        <header class="afc-page-header">
          <div>
            <div class="afc-eyebrow">AFC Operations Intelligence</div>
            <h1 class="afc-page-title">{escape(title)}</h1>
            <div class="afc-page-subtitle">{escape(english_title)}</div>
            <div class="afc-page-description">{escape(description)}</div>
          </div>
          <div class="afc-status-row" aria-label="系统状态">
            <span class="afc-chip afc-chip--online">Agent 在线</span>
            <span class="afc-chip afc-chip--mode">当前模式：{mode}</span>
            <span class="afc-chip">工作流：8 节点</span>
            {scene_chip}
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_mode_card(st_module, llm_enabled: bool) -> None:
    if llm_enabled:
        title = "当前使用 LLM 模式"
        copy = "模型能力已启用，系统会在结构化约束下完成需求理解、开放分析与回答生成。"
        class_name = "afc-mode-card afc-mode-card--enabled"
    else:
        title = "当前使用规则兜底模式"
        copy = "LLM 调用尚未启用，系统将通过内置规则完成基础意图识别与业务路由。设置 AFVC_USE_LLM=true 后可启用模型能力。"
        class_name = "afc-mode-card"
    st_module.markdown(
        f'<div class="{class_name}" role="status"><span class="afc-mode-indicator"></span><div><div class="afc-mode-title">{title}</div><div class="afc-mode-copy">{copy}</div></div></div>',
        unsafe_allow_html=True,
    )


def render_route_panel(
    st_module,
    route: Any,
    business_goal: Any,
    assetnum: Any = None,
) -> None:
    route_label = display_label(route, ROUTE_LABELS)
    goal_label = display_label(business_goal, BUSINESS_GOAL_LABELS)
    asset_label = str(assetnum) if assetnum else "未选择设备"
    st_module.markdown(
        f"""
        <section class="afc-route-panel" aria-label="当前业务状态">
          <div class="afc-route-item"><div class="afc-route-label">当前路由</div><div class="afc-route-value">{escape(route_label)}</div></div>
          <div class="afc-route-item"><div class="afc-route-label">业务目标</div><div class="afc-route-value">{escape(goal_label)}</div></div>
          <div class="afc-route-item"><div class="afc-route-label">当前设备</div><div class="afc-route-value">{escape(asset_label)}</div></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
