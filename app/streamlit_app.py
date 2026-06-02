import streamlit as st
import sys
import os

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

st.markdown("""
<div class="title-block">
  <h1>📊 FSA Engine</h1>
  <p>Financial Statement Analysis · Penman &amp; Pope + Standard Metrics + 10-K/Q Text Analysis</p>
</div>
""", unsafe_allow_html=True)

# ── SESSION STATE ─────────────────────────────────────────────
if "analysed" not in st.session_state:
    st.session_state.analysed = False
if "ticker" not in st.session_state:
    st.session_state.ticker = "AAPL"
if "r" not in st.session_state:
    st.session_state.r = 0.09

# ── SIDEBAR ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Settings")
    st.markdown("---")

    ticker = st.text_input(
        "Stock Ticker",
        value=st.session_state.ticker,
        placeholder="e.g. MSFT, AAPL, NVDA",
    ).upper().strip()

    r = st.slider(
        "Required Return (%)",
        min_value=5, max_value=15,
        value=int(st.session_state.r * 100),
        step=1,
    ) / 100

    st.markdown("---")
    st.markdown("**Tab 3 — Text Analysis**")
    gemini_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="Paste your Google AI Studio key",
        help="Required for 10-K/Q text analysis only"
    )

    st.markdown("---")

    if st.button("Run Analysis", type="primary"):
        st.session_state.analysed = True
        st.session_state.ticker   = ticker
        st.session_state.r        = r

    if st.session_state.analysed:
        if st.button("Reset / New Ticker"):
            st.session_state.analysed = False
            st.rerun()

    st.markdown("---")
    st.markdown(
        "<div style='font-size:11px;color:#999'>"
        "Penman &amp; Pope: FSA for Value Investing<br>"
        "Data: SEC EDGAR + Yahoo Finance + Gemini AI</div>",
        unsafe_allow_html=True
    )

# ── MAIN AREA ─────────────────────────────────────────────────
if not st.session_state.analysed:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### 📚 Tab 1 — Penman & Pope")
        st.markdown("""
        - Residual earnings valuation & g*
        - RNOA, PM × ATO decomposition
        - Leverage, quality, risk diagnostics
        - Ch 6, 8, 9/13 chapter analysis
        - Investment summary
        """)
    with col2:
        st.markdown("#### 📈 Tab 2 — Standard Analysis")
        st.markdown("""
        - Snapshot: P/E, P/B, PEG, FCF yield
        - 5-year trend tables with YoY change
        - ROIC, ROIIC, margins
        - Interactive DCF + EPS calculator
        - Adjustable sliders
        """)
    with col3:
        st.markdown("#### 📄 Tab 3 — 10-K/Q Analysis")
        st.markdown("""
        - Business overview & segments
        - Risk factors & management guidance
        - M&A activity & legal disputes
        - Capital allocation & accounting
        - Analyst flags — items to investigate
        - Powered by Gemini AI
        """)
    st.markdown("---")
    st.markdown("Enter a ticker and click **Run Analysis** to start.")

else:
    # Use the saved ticker/r from session state
    active_ticker = st.session_state.ticker
    active_r      = st.session_state.r

    st.markdown(
        f"**Analysing: {active_ticker}** "
        f"&nbsp;|&nbsp; Required return: {active_r:.0%} "
        f"&nbsp;|&nbsp; *Use sidebar to change settings*"
    )
    st.markdown("---")

    tab1, tab2, tab3 = st.tabs([
        "📚 Penman & Pope",
        "📈 Standard Analysis",
        "📄 10-K/Q Text Analysis",
    ])

    # ── TAB 1 ──────────────────────────────────────────────────
    with tab1:
        with st.spinner(f"Running Penman & Pope analysis on {active_ticker}..."):
            try:
                from report import generate_report
                import datetime

                html  = generate_report(active_ticker, r=active_r,
                                        project_root=PROJECT_ROOT)
                today = datetime.date.today().strftime("%Y-%m-%d")
                st.success(f"Report generated for {active_ticker}")
                st.download_button(
                    label="⬇️ Download Report",
                    data=html,
                    file_name=f"{active_ticker}_{today}.html",
                    mime="text/html",
                )
                st.markdown("---")
                st.components.v1.html(html, height=5000, scrolling=True)
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.exception(e)

    # ── TAB 2 ──────────────────────────────────────────────────
    with tab2:
        with st.spinner(f"Running standard analysis on {active_ticker}..."):
            try:
                from standard import generate_standard_html
                import datetime

                std_html = generate_standard_html(active_ticker)
                today    = datetime.date.today().strftime("%Y-%m-%d")
                st.success(f"Standard analysis generated for {active_ticker}")
                st.download_button(
                    label="⬇️ Download Standard Report",
                    data=std_html,
                    file_name=f"{active_ticker}_standard_{today}.html",
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

    # ── TAB 3 ──────────────────────────────────────────────────
    with tab3:
        if not gemini_key:
            st.warning(
                "Enter your Gemini API key in the sidebar to use text analysis. "
                "Get a free key at aistudio.google.com"
            )
        else:
            try:
                from text_analysis import get_recent_filings

                with st.spinner("Loading available filings..."):
                    filings = get_recent_filings(active_ticker, n=8)

                st.markdown(f"**{len(filings)} filings found for {active_ticker}:**")

                selected_idx = st.selectbox(
                    "Select filing to analyse:",
                    range(len(filings)),
                    format_func=lambda i: filings[i]["label"],
                    key="filing_selector",
                )

                selected = filings[selected_idx]
                st.info(
                    f"**{selected['form']}** · Period: {selected['period']} "
                    f"· Filed: {selected['filed']} · "
                    f"[View on SEC EDGAR]({selected['doc_url']})"
                )

                if st.button("Analyse This Filing", type="primary",
                             key="analyse_btn"):
                    with st.spinner(
                        f"Analysing {selected['form']} {selected['period']} "
                        f"with Gemini... (~30 seconds)"
                    ):
                        try:
                            from google import genai
                            from text_analysis import run_text_analysis
                            import datetime

                            g_client = genai.Client(api_key=gemini_key)
                            g_model  = "models/gemini-2.5-flash"

                            result = run_text_analysis(
                                active_ticker, selected_idx,
                                g_client, g_model
                            )

                            today    = datetime.date.today().strftime("%Y-%m-%d")
                            fname    = (f"{active_ticker}_{selected['form']}_"
                                       f"{selected['period']}_{today}.html")
                            full_html = (
                                "<html><body style='max-width:900px;"
                                "margin:20px auto;font-family:-apple-system,sans-serif'>"
                                + result["html"] + "</body></html>"
                            )

                            st.success(
                                f"Analysis complete — {selected['form']} "
                                f"{selected['period']}"
                            )
                            st.download_button(
                                label="⬇️ Download Text Analysis",
                                data=full_html,
                                file_name=fname,
                                mime="text/html",
                                key="dl_text",
                            )
                            st.markdown("---")
                            st.components.v1.html(
                                result["html"],
                                height=5000,
                                scrolling=True
                            )

                        except Exception as e:
                            st.error(f"Analysis failed: {str(e)}")
                            st.exception(e)

            except Exception as e:
                st.error(f"Could not load filings: {str(e)}")
                st.exception(e)
