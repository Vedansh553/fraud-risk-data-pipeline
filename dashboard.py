"""
Fraud Risk Command Center (Streamlit).   Run:  streamlit run app/dashboard.py
Run `python src/run_pipeline.py` once first. Press the Play buttons on charts to animate them.
"""
import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent.parent
DB, REPORTS, DATA = ROOT / "data" / "fraud_risk.db", ROOT / "reports", ROOT / "data"
BLUE, CYAN, RED, GREEN, AMBER = "#38bdf8", "#22d3ee", "#f87171", "#34d399", "#fbbf24"

st.set_page_config(page_title="Fraud Risk Command Center", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
.block-container {padding-top: 1.4rem; animation: fadeUp .7s ease both;}
@keyframes fadeUp {from {opacity:0; transform: translateY(14px);} to {opacity:1; transform:none;}}
@keyframes glow {0%,100% {box-shadow: 0 0 0 rgba(56,189,248,0);} 50% {box-shadow: 0 0 18px rgba(56,189,248,.35);}}
.hero {background: linear-gradient(120deg,#0f2747 0%,#13396b 45%,#0e7490 100%); border-radius: 16px;
       padding: 22px 28px; margin-bottom: 14px; border: 1px solid rgba(56,189,248,.25);}
.hero h1 {margin:0; font-size: 1.9rem; background: linear-gradient(90deg,#fff,#7dd3fc);
          -webkit-background-clip:text; -webkit-text-fill-color:transparent;}
.hero p {margin:.25rem 0 0; color:#a8c4e6; font-size:.95rem;}
.live {display:inline-block; width:9px; height:9px; border-radius:50%; background:#34d399; margin-right:8px;
       animation: glow 1.8s infinite;}
div[data-testid="stMetric"] {background:#121c33; border:1px solid #1f2d4d; border-radius:14px; padding:14px 16px;
       transition: transform .25s ease, border-color .25s ease; animation: fadeUp .6s ease both;}
div[data-testid="stMetric"]:hover {transform: translateY(-4px); border-color:#38bdf8;}
button[data-baseweb="tab"] {font-weight:600; font-size:1rem;}
.stTabs [data-baseweb="tab-panel"] {animation: fadeUp .5s ease both;}
.section {color:#7dd3fc; font-weight:700; letter-spacing:.04em; text-transform:uppercase; font-size:.8rem; margin:.6rem 0 .2rem;}
</style>
<div class="hero"><h1>🛡️ Fraud Risk Command Center</h1>
<p><span class="live"></span>Synthetic card-transaction data &nbsp;|&nbsp; data quality &middot; fraud patterns &middot; model decisions &middot; drift monitoring</p></div>
""", unsafe_allow_html=True)

if not DB.exists():
    st.error("Run `python src/run_pipeline.py` first to build the database.")
    st.stop()


@st.cache_data
def q(sql):
    con = sqlite3.connect(DB)
    try:
        return pd.read_sql(sql, con)
    finally:
        con.close()


def style(fig, h=380, title=None):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=h, margin=dict(l=10, r=10, t=50 if title else 20, b=10), title=title,
                      font=dict(color="#cbd5e1"), transition=dict(duration=500, easing="cubic-in-out"),
                      legend=dict(orientation="h", y=1.12))
    fig.update_xaxes(gridcolor="#1f2d4d"); fig.update_yaxes(gridcolor="#1f2d4d")
    return fig


def with_play(fig, frames, label="▶ Play", ms=60):
    fig.frames = frames
    fig.update_layout(updatemenus=[dict(type="buttons", showactive=False, x=0.0, y=1.18, xanchor="left", direction="left",
        bgcolor="#1f2d4d", font=dict(color="#e6edf7"),
        buttons=[dict(label=label, method="animate",
                      args=[None, dict(frame=dict(duration=ms, redraw=True), transition=dict(duration=ms // 2), fromcurrent=True)])])])
    return fig


def kpi_strip(items):
    """Animated count-up KPI cards (JS runs inside a component iframe)."""
    cards = "".join(
        f'<div class="c"><div class="l">{lbl}</div><div class="v" data-v="{v}" data-d="{d}" data-s="{s}">0</div></div>'
        for lbl, v, d, s in items)
    page = f"""
    <style>
    body{{margin:0;font-family:Inter,Segoe UI,sans-serif}} .g{{display:grid;grid-template-columns:repeat({len(items)},1fr);gap:12px}}
    .c{{background:linear-gradient(145deg,#121c33,#0f1a30);border:1px solid #1f2d4d;border-radius:14px;padding:16px 18px;
        opacity:0;transform:translateY(16px);animation:in .6s ease forwards;transition:transform .25s,border-color .25s}}
    .c:nth-child(2){{animation-delay:.1s}} .c:nth-child(3){{animation-delay:.2s}} .c:nth-child(4){{animation-delay:.3s}}
    .c:hover{{transform:translateY(-4px);border-color:#38bdf8}} .l{{color:#8ba3c7;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em}}
    .v{{color:#f1f5f9;font-size:1.9rem;font-weight:700;margin-top:4px}} @keyframes in{{to{{opacity:1;transform:none}}}}
    </style><div class="g">{cards}</div>
    <script>
    document.querySelectorAll('.v').forEach(el=>{{
      const to=parseFloat(el.dataset.v), dec=parseInt(el.dataset.d), suf=el.dataset.s, t0=performance.now(), dur=1400;
      (function tick(t){{const p=Math.min((t-t0)/dur,1), e=1-Math.pow(1-p,3);
        el.textContent=(to*e).toLocaleString(undefined,{{minimumFractionDigits:dec,maximumFractionDigits:dec}})+suf;
        if(p<1) requestAnimationFrame(tick);}})(t0);
    }});
    </script>"""
    if hasattr(st, "iframe"):                    # newer Streamlit
        st.iframe(page, height=118)
    else:                                        # older Streamlit
        components.html(page, height=118)


metrics = json.loads((REPORTS / "model_metrics.json").read_text())
sc_dq = pd.read_csv(REPORTS / "data_quality_scorecard.csv")
tot = q("SELECT COUNT(*) n, SUM(is_fraud) f, SUM(CASE WHEN is_fraud=1 THEN amount END) fa FROM transactions").iloc[0]
quar = int(q("SELECT COALESCE(SUM(rows_rejected),0) n FROM v_quarantine_summary").iloc[0, 0])
dq_after = float(sc_dq.loc[sc_dq.dimension == "OVERALL", "score_pct_after"].iloc[0])

kpi_strip([("Transactions analysed", tot.n, 0, ""), ("Fraud rate", 100 * tot.f / tot.n, 2, "%"),
           ("Fraud value", tot.fa / 1000, 0, "K"), ("Data quality score", dq_after, 2, "%")])

t1, t2, t3, t4 = st.tabs(["📈 Overview", "🔎 Fraud patterns", "🤖 Model and threshold", "🧪 Quality and drift"])

# ---------------- Overview ----------------
with t1:
    daily = q("SELECT date(transaction_ts) d, 100.0*SUM(is_fraud)/COUNT(*) r FROM transactions GROUP BY d ORDER BY d")
    daily["ma"] = daily.r.rolling(7, min_periods=1).mean()
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown('<div class="section">Daily fraud rate with 7-day average</div>', unsafe_allow_html=True)
        fig = go.Figure([go.Scatter(x=daily.d[:2], y=daily.r[:2], name="Daily", mode="lines", line=dict(color="#475569", width=1.5)),
                         go.Scatter(x=daily.d[:2], y=daily.ma[:2], name="7-day avg", mode="lines", fill="tozeroy",
                                    line=dict(color=CYAN, width=3), fillcolor="rgba(34,211,238,.12)")])
        frames = [go.Frame(data=[go.Scatter(x=daily.d[:k], y=daily.r[:k]), go.Scatter(x=daily.d[:k], y=daily.ma[:k])])
                  for k in range(2, len(daily) + 1, 2)]
        fig.update_xaxes(range=[daily.d.iloc[0], daily.d.iloc[-1]]); fig.update_yaxes(range=[0, daily.r.max() * 1.15], title="%")
        st.plotly_chart(with_play(style(fig, 360), frames), width="stretch")
    with c2:
        st.markdown('<div class="section">Fraud rate by merchant category</div>', unsafe_allow_html=True)
        cat = q("SELECT merchant_category c, fraud_rate_pct r FROM v_fraud_by_category ORDER BY r").reset_index(drop=True)
        fig = go.Figure(go.Bar(x=[0] * len(cat), y=cat.c, orientation="h",
                               marker=dict(color=cat.r, colorscale=[[0, "#1e40af"], [1, RED]])))
        frames = [go.Frame(data=[go.Bar(x=cat.r * k / 12, y=cat.c, orientation="h", marker=dict(color=cat.r, colorscale=[[0, "#1e40af"], [1, RED]]))])
                  for k in range(1, 13)]
        fig.update_xaxes(range=[0, cat.r.max() * 1.1], title="%")
        st.plotly_chart(with_play(style(fig, 360), frames, "▶ Grow", 45), width="stretch")

# ---------------- Fraud patterns ----------------
with t2:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section">When does fraud happen? (hour x channel, %)</div>', unsafe_allow_html=True)
        hm = q("""SELECT CAST(strftime('%H', transaction_ts) AS INTEGER) h, channel,
                  100.0*SUM(is_fraud)/COUNT(*) r FROM transactions GROUP BY h, channel""").pivot(index="channel", columns="h", values="r")
        fig = go.Figure(go.Heatmap(z=hm.values, x=hm.columns, y=hm.index, colorscale="Turbo", colorbar=dict(title="%")))
        fig.update_xaxes(title="Hour of day", dtick=2)
        st.plotly_chart(style(fig, 340), width="stretch")
    with c2:
        st.markdown('<div class="section">Domestic versus foreign, by channel (%)</div>', unsafe_allow_html=True)
        g = q("SELECT * FROM v_fraud_by_channel_geo")
        fig = go.Figure([go.Bar(name=geo, x=d.channel, y=d.fraud_rate_pct, marker_color=col)
                         for (geo, d), col in zip(g.groupby("geo"), [BLUE, RED])])
        fig.update_layout(barmode="group")
        st.plotly_chart(style(fig, 340), width="stretch")
    st.markdown('<div class="section">Run your own SQL (read-only, single SELECT)</div>', unsafe_allow_html=True)
    sql = st.text_area("Query", "SELECT merchant_category, COUNT(*) AS txns, ROUND(100.0*SUM(is_fraud)/COUNT(*),2) AS fraud_pct\nFROM transactions GROUP BY 1 ORDER BY 3 DESC", height=90, label_visibility="collapsed")
    if st.button("▶ Run query"):
        s = sql.strip().rstrip(";")
        if s.lower().startswith("select") and ";" not in s:
            try:
                st.dataframe(q(s), width="stretch")
            except Exception as e:
                st.error(str(e))
        else:
            st.warning("Only a single SELECT statement is allowed.")

# ---------------- Model and threshold ----------------
with t3:
    sc = pd.read_csv(DATA / "test_scores.csv")
    y, a, s = sc.is_fraud.values, sc.amount.values, sc.score.values
    left, right = st.columns([1, 2])
    with left:
        st.markdown('<div class="section">Decision settings</div>', unsafe_allow_html=True)
        cost_fd = st.slider("Cost of declining a good transaction", 1, 200, 25)
        grid = np.linspace(0.01, 0.99, 99)
        curve = np.array([a[(y == 1) & (s < t)].sum() + ((y == 0) & (s >= t)).sum() * cost_fd for t in grid])
        best = float(grid[int(curve.argmin())])
        thr = st.slider("Decline threshold (fraud score)", 0.01, 0.99, round(best, 2), 0.01)
        pred = s >= thr
        fd = ((y == 0) & pred).sum()
        cost = a[(y == 1) & ~pred].sum() + fd * cost_fd
        m1, m2 = st.columns(2)
        m1.metric("Fraud caught", f"{(y[pred] == 1).sum() / (y == 1).sum():.1%}")
        m2.metric("Precision", f"{(y[pred] == 1).mean() if pred.sum() else 0:.1%}")
        m3, m4 = st.columns(2)
        m3.metric("Good txns declined", f"{fd / (y == 0).sum():.1%}")
        m4.metric("Cost vs approve-all", f"{1 - cost / a[y == 1].sum():.1%} lower")
    with right:
        st.markdown('<div class="section">Total cost across thresholds</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Scatter(x=grid, y=curve, mode="lines", line=dict(color=BLUE, width=3), fill="tozeroy",
                                   fillcolor="rgba(56,189,248,.10)", name="Total cost"))
        fig.add_trace(go.Scatter(x=[thr], y=[curve[int(np.argmin(abs(grid - thr)))]], mode="markers", name="Your threshold",
                                 marker=dict(size=14, color=AMBER, line=dict(width=2, color="white"))))
        fig.add_trace(go.Scatter(x=[best], y=[curve.min()], mode="markers", name="Cost-minimising",
                                 marker=dict(size=14, color=GREEN, symbol="diamond", line=dict(width=2, color="white"))))
        fig.update_xaxes(title="Threshold"); fig.update_yaxes(title="Cost")
        st.plotly_chart(style(fig, 360), width="stretch")
    st.markdown('<div class="section">Highest-risk transactions in the test period</div>', unsafe_allow_html=True)
    st.dataframe(sc.sort_values("score", ascending=False).head(25), width="stretch", hide_index=True,
                 column_config={"score": st.column_config.ProgressColumn("fraud score", min_value=0, max_value=1, format="%.2f"),
                                "is_fraud": st.column_config.CheckboxColumn("actual fraud")})

# ---------------- Quality and drift ----------------
with t4:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section">Data quality by dimension</div>', unsafe_allow_html=True)
        d = sc_dq[sc_dq.dimension != "OVERALL"]
        fig = go.Figure([go.Bar(name="Before cleaning", x=d.dimension, y=d.score_pct_before, marker_color=RED),
                         go.Bar(name="After cleaning", x=d.dimension, y=d.score_pct_after, marker_color=GREEN)])
        fig.update_layout(barmode="group"); fig.update_yaxes(range=[97, 100.2], title="Pass rate %")
        st.plotly_chart(style(fig, 340), width="stretch")
    with c2:
        st.markdown('<div class="section">Quarantined records by reason</div>', unsafe_allow_html=True)
        qs = q("SELECT * FROM v_quarantine_summary")
        fig = go.Figure(go.Pie(labels=qs.reject_reason, values=qs.rows_rejected, hole=.55,
                               marker=dict(colors=[RED, AMBER, BLUE, "#a78bfa"])))
        st.plotly_chart(style(fig, 340), width="stretch")
    st.markdown('<div class="section">Feature drift (PSI, train versus test)</div>', unsafe_allow_html=True)
    psi = pd.read_csv(REPORTS / "drift_psi.csv").sort_values("psi")
    col = [GREEN if v < .1 else AMBER if v < .2 else RED for v in psi.psi]
    fig = go.Figure(go.Bar(x=psi.psi, y=psi.feature, orientation="h", marker_color=col))
    fig.add_vline(x=.1, line_dash="dash", line_color=AMBER); fig.add_vline(x=.2, line_dash="dash", line_color=RED)
    st.plotly_chart(style(fig, 360), width="stretch")
    st.caption("Below 0.1 stable, 0.1 to 0.2 watch, above 0.2 significant shift.")
    with st.expander("Rule-level data quality results"):
        res = pd.read_csv(REPORTS / "data_quality_results.csv")
        st.dataframe(res.pivot(index=["rule_id", "dimension", "rule"], columns="stage", values="failed_rows").reset_index(),
                     width="stretch", hide_index=True)
