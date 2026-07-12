"""Centralized Streamlit styles for the AFC operations console."""

APP_CSS = r"""
<style>
:root {
  --afc-navy: #0b1f3a;
  --afc-blue: #1d4ed8;
  --afc-blue-soft: #eaf1ff;
  --afc-amber: #b45309;
  --afc-amber-soft: #fff7e8;
  --afc-green: #047857;
  --afc-green-soft: #ecfdf5;
  --afc-bg: #f5f7fb;
  --afc-surface: #ffffff;
  --afc-text: #172033;
  --afc-muted: #5e6b80;
  --afc-border: #dfe5ef;
  --afc-radius: 8px;
  --afc-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 20px rgba(15, 23, 42, .035);
}

html, body, [class*="css"] {
  font-family: Inter, "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
}

[data-testid="stAppViewContainer"] { background: var(--afc-bg); }
[data-testid="stHeader"] { background: rgba(245, 247, 251, .92); }
[data-testid="stMainBlockContainer"], .block-container {
  max-width: 1280px;
  padding-top: 1.5rem;
  padding-bottom: 3.5rem;
  padding-left: clamp(1rem, 3vw, 2rem);
  padding-right: clamp(1rem, 3vw, 2rem);
}

h1, h2, h3 { color: var(--afc-navy); letter-spacing: -.015em; }
p, li { line-height: 1.65; }

[data-testid="stSidebar"] {
  background: var(--afc-navy);
  border-right: 1px solid rgba(255,255,255,.08);
}
[data-testid="stSidebar"] * { color: #e8eef8; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #b9c6d8; }
.afc-brand { padding: .6rem .35rem 1.35rem; border-bottom: 1px solid rgba(255,255,255,.12); margin-bottom: 1rem; }
.afc-brand-mark { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid #60a5fa; color: #fff; font-weight: 800; letter-spacing: .04em; border-radius: 7px; margin-bottom: .75rem; }
.afc-brand-title { color: #fff; font-size: 1.05rem; font-weight: 700; }
.afc-brand-subtitle { color: #9fb0c7; font-size: .76rem; margin-top: .2rem; letter-spacing: .02em; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: .35rem; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  min-height: 44px; padding: .62rem .75rem; border-radius: 7px; transition: background-color .18s ease, color .18s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.08); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background: #1d4ed8; box-shadow: inset 3px 0 0 #f59e0b; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }

.afc-page-header { display: flex; justify-content: space-between; gap: 1.5rem; align-items: flex-start; padding: 1.15rem 1.25rem; background: var(--afc-surface); border: 1px solid var(--afc-border); border-radius: var(--afc-radius); box-shadow: var(--afc-shadow); margin-bottom: 1rem; }
.afc-eyebrow { color: var(--afc-blue); font-size: .74rem; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; margin-bottom: .35rem; }
.afc-page-title { color: var(--afc-navy); font-size: clamp(1.55rem, 2.5vw, 2.05rem); line-height: 1.2; font-weight: 750; margin: 0; }
.afc-page-subtitle { color: #526179; font-size: .9rem; margin-top: .25rem; }
.afc-page-description { color: var(--afc-muted); margin-top: .65rem; max-width: 720px; font-size: .94rem; }
.afc-status-row { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .45rem; min-width: 250px; }
.afc-chip { display: inline-flex; align-items: center; gap: .4rem; min-height: 30px; padding: .3rem .62rem; border-radius: 999px; border: 1px solid var(--afc-border); background: #f8fafc; color: #334155; font-size: .77rem; font-weight: 650; white-space: nowrap; }
.afc-chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: #64748b; }
.afc-chip--online::before { background: var(--afc-green); }
.afc-chip--mode::before { background: var(--afc-amber); }
.afc-chip--route::before { background: var(--afc-blue); }

.afc-route-panel { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; margin: .8rem 0 1rem; }
.afc-route-item { background: var(--afc-surface); border: 1px solid var(--afc-border); border-radius: var(--afc-radius); padding: .72rem .85rem; }
.afc-route-label { color: var(--afc-muted); font-size: .72rem; margin-bottom: .18rem; }
.afc-route-value { color: var(--afc-navy); font-weight: 700; font-size: .9rem; overflow-wrap: anywhere; }

.afc-mode-card { display: flex; gap: .75rem; align-items: flex-start; border: 1px solid #f1d7a8; background: var(--afc-amber-soft); border-radius: var(--afc-radius); padding: .7rem .85rem; margin: .7rem 0 1rem; }
.afc-mode-card--enabled { background: var(--afc-green-soft); border-color: #b7e4d2; }
.afc-mode-indicator { width: 9px; height: 9px; border-radius: 50%; background: var(--afc-amber); margin-top: .42rem; flex: 0 0 auto; }
.afc-mode-card--enabled .afc-mode-indicator { background: var(--afc-green); }
.afc-mode-title { color: var(--afc-navy); font-size: .86rem; font-weight: 750; }
.afc-mode-copy { color: #596579; font-size: .79rem; line-height: 1.55; margin-top: .12rem; }

.afc-section-label { color: var(--afc-navy); font-size: 1rem; font-weight: 750; margin: 1rem 0 .55rem; }
[data-testid="stChatMessage"] { max-width: min(860px, 88%); border: 1px solid var(--afc-border); border-radius: 9px; padding: .35rem .55rem; margin-bottom: .7rem; background: var(--afc-surface); box-shadow: 0 1px 2px rgba(15,23,42,.025); }
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) { margin-left: auto; background: var(--afc-blue-soft); border-color: #cad9fb; }
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { overflow-wrap: anywhere; }
[data-testid="stChatMessage"] pre { overflow-x: auto; }
[data-testid="stChatInput"] { max-width: 1280px; margin: 0 auto; }
[data-testid="stChatInput"] textarea { min-height: 48px; }

.stButton > button, [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] { min-height: 44px; border-radius: 7px; font-weight: 650; }
.stButton > button:focus-visible, textarea:focus-visible, input:focus-visible { outline: 3px solid rgba(37,99,235,.3) !important; outline-offset: 2px; }
[data-testid="stExpander"] { border-color: var(--afc-border); background: rgba(255,255,255,.75); border-radius: var(--afc-radius); }
[data-testid="stDataFrame"], [data-testid="stFileUploader"], [data-testid="stForm"] { border-radius: var(--afc-radius); }

@media (max-width: 760px) {
  [data-testid="stMainBlockContainer"], .block-container { padding-top: 1rem; padding-left: .85rem; padding-right: .85rem; }
  .afc-page-header { flex-direction: column; padding: 1rem; }
  .afc-status-row { justify-content: flex-start; min-width: 0; }
  .afc-route-panel { grid-template-columns: 1fr; }
  [data-testid="stChatMessage"] { max-width: 96%; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; scroll-behavior: auto !important; }
}
</style>
"""


def inject_app_styles(st_module) -> None:
    """Inject the app stylesheet once per Streamlit rerun."""
    st_module.markdown(APP_CSS, unsafe_allow_html=True)
