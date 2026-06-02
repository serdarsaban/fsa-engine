import streamlit as st
import sys
import os

# ── PROJECT ROOT ─────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "core"))

st.set_page_config(
    page_title="FSA Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .main { background-color: #f5f6fa; }
  .stButton > button {
    width: 100%;
    background-color: #1a1a2e;
    color: white;
    border: none;
    padding: 12px;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 600;
  }
  .stButton > button:hover { background-color: #2d2d5e; }
  .title-block {
    background: #1a1a2e;
    color: white;
    padding: 24px;
    border-radius: 10px;
    margin-bottom: 20px;
  }
  .title-block h1 { font-size: 28px; font-weight: 700; margin: 0; }
  .title-block p  { color: #aaa; margin: 6px 0 0; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ── HEADER ───────────────────────────────────────────────────
st.markdown("""
<div class="title-block">
  <h1>📊 FSA Engine</h1>
  <p>Financial Statement Analysis · Penman &amp; Pope + Standard Practitioner Metrics</p>
</div>
""", unsafe_allow_html=True)

# ── SIDEBAR ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Analysis Settings")
    st.markdown("---")

    ticker = st.text_input(
        "Stock Ticker",
        value="AAPL",
        placeholder="e.g. MSFT, AAPL, NVDA",
        help="Enter any US-listed stock ticker"
    ).upper().strip()

    r = st.slider(
        "Required Return — %",
        min_value=5, max_value=15, value=9, step=1,
        help="Hurdle rate for Penman & Pope valuation"
    ) / 100

    st.markdown("---")
    run_button = st.button("Run Analysis", type="primary")

    st.markdown("---")
    st.markdown("**Tab 1 — Penman & Pope**")
    st.markdown("""
    - Residual earnings valuation
    - RNOA, PM, ATO decomposition
    - Leverage, quality, risk
    - Ch 6, 8, 9, 13 diagnostics
    """)
    st.markdown("**Tab 2 — Standard Analysis**")
    st.markdown("""
    - Revenue, EPS, FCF trends
    - ROIC, ROIIC, margins
    - Interactive DCF + EPS calculator
    - Valuation multiples
    """)
    st.markdown("---")
    st.markdown(
        "<div style='font-size:11px;color:#999'>"
        "Penman &amp; Pope: FSA for Value Investing<br>"
        "Data: SEC EDGAR + Yahoo Finance</div>",
        unsafe_allow_html=True
    )

# ── MAIN AREA ────────────────────────────────────────────────
if not run_button:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Tab 1 — Penman & Pope Report")
        st.markdown("""
        Reformulated financial statements based on the
        Penman & Pope textbook methodology.
        - Residual earnings valuation & implied g*
        - RNOA, PM × ATO DuPont decomposition
        - Leverage spread and ROE decomposition
        - Earnings quality, accruals, cash conversion
        - Ch 6, 8, 9/13 chapter diagnostics
        - EPS valuation calculator
        - Investment summary with strengths/risks
        """)
    with col2:
        st.markdown("#### Tab 2 — Standard Analysis")
        st.markdown("""
        Practitioner metrics used by value investors.
        - Snapshot: P/E, P/B, PEG, EV/Sales, FCF yield
        - 5-year trend tables with YoY % change
        - Revenue, EPS, FCF, ROIC, ROIIC, margins
        - Balance sheet & leverage trends
        - Interactive intrinsic value calculator
        - DCF (FCF-based) + EPS × exit multiple
        - Adjustable sliders with historical context
        """)
    st.markdown("---")
    st.markdown("Enter a ticker in the sidebar and click **Run Analysis** to start.")

else:
    if not ticker:
        st.error("Please enter a stock ticker.")
    else:
        # ── TWO TABS ──────────────────────────────────────────
        tab1, tab2 = st.tabs([
            "📚 Penman & Pope Report",
            "📈 Standard Analysis",
        ])

        with tab1:
            with st.spinner(f"Running Penman & Pope analysis on {ticker}..."):
                try:
                    from report import generate_report
                    import datetime

                    html     = generate_report(ticker, r=r,
                                               project_root=PROJECT_ROOT)
                    today    = datetime.date.today().strftime("%Y-%m-%d")
                    fname    = f"{ticker}_{today}.html"

                    st.success(f"Penman & Pope report generated for {ticker}")
                    st.download_button(
                        label="⬇️ Download Report",
                        data=html,
                        file_name=fname,
                        mime="text/html",
                    )
                    st.markdown("---")
                    st.components.v1.html(html, height=5000, scrolling=True)

                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.exception(e)

        with tab2:
            with st.spinner(f"Running standard analysis on {ticker}..."):
                try:
                    from standard import generate_standard_html
                    import datetime

                    std_html = generate_standard_html(ticker)
                    today    = datetime.date.today().strftime("%Y-%m-%d")
                    fname2   = f"{ticker}_standard_{today}.html"

                    st.success(f"Standard analysis generated for {ticker}")
                    st.download_button(
                        label="⬇️ Download Standard Report",
                        data=std_html,
                        file_name=fname2,
                        mime="text/html",
                        key="dl_standard",
                    )
                    st.markdown("---")
                    st.components.v1.html(
                        f"<div style='max-width:960px;margin:0 auto;"
                        f"font-family:-apple-system,sans-serif'>{std_html}</div>",
                        height=4000,
                        scrolling=True
                    )

                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.exception(e)
